from datetime import datetime

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import or_

from ..account_service import (
    apply_user_form,
    default_user_password,
    enabled_status_label,
    parse_enabled_status,
    parse_role_codes,
    resolve_bound_student,
    resolve_roles,
    serialize_role,
    serialize_user,
    sync_student_account,
    system_roles,
)
from ..common import paginate_query
from ..data_scope import apply_user_data_scope, build_scope_dept_tree, can_access_user, filter_assignable_roles, role_assignable_by_user
from ..errors import APIError
from ..excel_utils import XLSX_MIMETYPE, create_export_file, create_workbook_bytes, parse_tabular_file, save_uploaded_attachment
from ..extensions import db
from ..models import ImportTask, StudentInfo, SysRole, SysUser
from ..security import auth_required, password_hash, verify_password
from ..system_compat_store import get_config_value


bp = Blueprint("admin_users", __name__, url_prefix="/system")
USER_IMPORT_TASK_TYPE = "system_user_import"


def ruoyi_ok(payload=None, msg="操作成功"):
    data = {"code": 200, "msg": msg}
    if payload:
        data.update(payload)
    return jsonify(data)


def parse_datetime_query(value):
    if not value:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def serialize_role_list(selected_role_ids=None):
    current_user = getattr(g, "current_user", None)
    roles = system_roles() if current_user is None else filter_assignable_roles(system_roles(), current_user)
    return [serialize_role(item, selected_role_ids) for item in roles]


def find_users(role_code=None):
    params = request.values
    query = apply_user_data_scope(SysUser.query, getattr(g, "current_user", None))
    keyword = (params.get("keyword") or params.get("userName") or "").strip()
    mobile = (params.get("phonenumber") or "").strip()
    status = params.get("status")
    begin_time = parse_datetime_query(params.get("beginTime"))
    end_time = parse_datetime_query(params.get("endTime"))

    if keyword:
        query = query.filter(
            or_(
                SysUser.username.like(f"%{keyword}%"),
                SysUser.real_name.like(f"%{keyword}%"),
                SysUser.mobile.like(f"%{keyword}%"),
                SysUser.email.like(f"%{keyword}%"),
            )
        )
    if mobile:
        query = query.filter(SysUser.mobile.like(f"%{mobile}%"))
    if status not in (None, ""):
        query = query.filter(SysUser.status == parse_enabled_status(status))
    if role_code:
        query = query.filter(SysUser.roles.any(SysRole.role_code == role_code))
    if begin_time:
        query = query.filter(SysUser.created_at >= begin_time)
    if end_time:
        query = query.filter(SysUser.created_at <= end_time)
    return query.order_by(SysUser.id.desc())


def ensure_user_in_scope(user):
    if not can_access_user(getattr(g, "current_user", None), user):
        raise APIError("当前数据权限不允许访问该账号", code=403)
    return user


def ensure_assignable_roles(payload):
    current_user = getattr(g, "current_user", None)
    if current_user is None or "admin" in current_user.role_codes:
        return
    roles = resolve_roles(role_ids=payload.get("roleIds") or [], role_codes=payload.get("roleCodes") or payload.get("roles") or [])
    disallowed = [role.role_name for role in roles if not role_assignable_by_user(role, current_user)]
    if disallowed:
        raise APIError(f"当前数据权限不允许分配角色：{'、'.join(disallowed)}", code=403)


def bound_student_options():
    return [
        {
            "id": item.id,
            "studentNo": item.student_no,
            "name": item.name,
            "label": f"{item.student_no} / {item.name}",
            "status": item.status,
        }
        for item in StudentInfo.query.order_by(StudentInfo.student_no.asc()).all()
    ]


def user_detail_payload(user=None):
    payload = serialize_user(user) if user else {}
    selected_role_ids = payload.get("roleIds") if payload else []
    return {
        "data": payload,
        "roles": serialize_role_list(selected_role_ids),
        "roleIds": selected_role_ids,
        "posts": [],
        "postIds": [],
        "students": bound_student_options(),
        "initPassword": default_user_password(),
    }


def sync_student_status_from_user(user):
    if not user.student_id:
        return
    student = StudentInfo.query.get(user.student_id)
    if not student:
        return
    student.status = int(user.status or 0)
    sync_student_account(student)


def parse_import_record(record):
    user_name = str(record.get("登录账号") or record.get("userName") or "").strip()
    nick_name = str(record.get("姓名") or record.get("nickName") or "").strip()
    phone = str(record.get("手机") or record.get("phonenumber") or "").strip()
    email = str(record.get("邮箱") or record.get("email") or "").strip()
    status = record.get("状态") if record.get("状态") not in (None, "") else record.get("status")
    role_value = record.get("角色") or record.get("roleCodes") or record.get("roles")
    student_no = record.get("关联学号") or record.get("studentNo")
    return {
        "userName": user_name,
        "nickName": nick_name,
        "phonenumber": phone,
        "email": email,
        "status": status if status not in (None, "") else "0",
        "roleCodes": parse_role_codes(role_value),
        "studentNo": str(student_no).strip() if student_no not in (None, "") else None,
    }


def upsert_user_record(record, overwrite):
    payload = parse_import_record(record)
    role_codes = payload.get("roleCodes") or []
    if not role_codes:
        raise APIError("导入账号必须指定至少一个角色")

    if "student" in role_codes:
        student = resolve_bound_student(student_no=payload.get("studentNo"), required=True)
        payload["studentId"] = student.id
        payload["userName"] = student.student_no
    elif not payload.get("userName"):
        raise APIError("登录账号不能为空")

    user = SysUser.query.filter_by(username=payload.get("userName")).first()
    if payload.get("studentId") and not user:
        user = SysUser.query.filter_by(student_id=payload.get("studentId")).first()

    if user and not overwrite:
        raise APIError("账号已存在，且未开启覆盖")

    if not user:
        user = SysUser(
            username=payload.get("userName"),
            real_name=payload.get("nickName") or payload.get("userName"),
            password_hash=password_hash(default_user_password()),
            status=1,
        )
        db.session.add(user)

    return apply_user_form(user, payload, creating=False)


@bp.get("/config/configKey/<path:config_key>")
@auth_required()
def get_config_key(config_key):
    if config_key == "sys.user.initPassword":
        return ruoyi_ok(msg=get_config_value(config_key) or default_user_password())
    return ruoyi_ok(msg=get_config_value(config_key))


@bp.get("/user/list")
@auth_required(["admin"])
def list_users():
    role_code = (request.args.get("roleCode") or "").strip()
    query = find_users(role_code=role_code or None)
    items, total, _, _ = paginate_query(query)
    return ruoyi_ok({"rows": [serialize_user(item) for item in items], "total": total})


@bp.get("/user/")
@auth_required(["admin"])
def get_user_options():
    return ruoyi_ok(user_detail_payload())


@bp.get("/user/<int:user_id>")
@auth_required(["admin"])
def get_user_detail(user_id):
    user = ensure_user_in_scope(SysUser.query.get_or_404(user_id))
    return ruoyi_ok(user_detail_payload(user))


@bp.post("/user")
@auth_required(["admin"])
def create_user():
    payload = request.get_json(silent=True) or {}
    ensure_assignable_roles(payload)
    user = SysUser(
        username="",
        real_name="",
        password_hash=password_hash(payload.get("password") or default_user_password()),
        status=1,
    )
    db.session.add(user)
    apply_user_form(user, payload, creating=True)
    db.session.commit()
    return ruoyi_ok(msg="新增账号成功")


@bp.put("/user")
@auth_required(["admin"])
def update_user():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("userId")
    if not user_id:
        raise APIError("用户编号不能为空")
    user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
    ensure_assignable_roles(payload)
    apply_user_form(user, payload, creating=False)
    if user.id == g.current_user.id and "admin" not in user.role_codes:
        raise APIError("当前登录管理员账号不能移除管理员角色")
    db.session.commit()
    return ruoyi_ok(msg="修改账号成功")


@bp.delete("/user/<user_ids>")
@auth_required(["admin"])
def delete_users(user_ids):
    ids = [int(item) for item in str(user_ids).split(",") if str(item).strip()]
    for user in SysUser.query.filter(SysUser.id.in_(ids)).all():
        ensure_user_in_scope(user)
        if user.id == g.current_user.id:
            raise APIError("不能删除当前登录账号")
        if user.student_id:
            raise APIError("学生账号由学生档案自动维护，不允许直接删除")
        db.session.delete(user)
    db.session.commit()
    return ruoyi_ok(msg="删除成功")


@bp.put("/user/changeStatus")
@auth_required(["admin"])
def change_user_status():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("userId")
    if not user_id:
        raise APIError("用户编号不能为空")
    user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
    user.status = parse_enabled_status(payload.get("status"), user.status)
    if user.id == g.current_user.id and int(user.status or 0) != 1:
        raise APIError("当前登录账号不能被停用")
    sync_student_status_from_user(user)
    db.session.commit()
    return ruoyi_ok(msg="状态更新成功")


@bp.put("/user/resetPwd")
@auth_required(["admin"])
def reset_user_password():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("userId")
    password = payload.get("password") or ""
    if not user_id:
        raise APIError("用户编号不能为空")
    if len(str(password)) < 5:
        raise APIError("用户密码长度必须介于 5 和 20 之间")
    user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
    user.password_hash = password_hash(str(password))
    db.session.commit()
    return ruoyi_ok(msg="密码重置成功")


@bp.get("/user/profile")
@auth_required()
def get_user_profile():
    user = SysUser.query.get_or_404(g.current_user.id)
    payload = serialize_user(user)
    payload["avatar"] = ""
    return ruoyi_ok({"data": payload, "roleGroup": payload["roleLabel"], "postGroup": "竞赛平台"})


@bp.put("/user/profile")
@auth_required()
def update_user_profile():
    payload = request.get_json(silent=True) or {}
    user = SysUser.query.get_or_404(g.current_user.id)
    if user.student_id:
        student = StudentInfo.query.get(user.student_id)
        if student:
            student.mobile = str(payload.get("phonenumber") or "").strip() or None
            student.email = str(payload.get("email") or "").strip() or None
            sync_student_account(student)
    else:
        nick_name = str(payload.get("nickName") or "").strip()
        if not nick_name:
            raise APIError("用户昵称不能为空")
        user.real_name = nick_name
        user.mobile = str(payload.get("phonenumber") or "").strip() or None
        user.email = str(payload.get("email") or "").strip() or None
    db.session.commit()
    return ruoyi_ok(msg="个人信息更新成功")


@bp.put("/user/profile/updatePwd")
@auth_required()
def update_profile_password():
    payload = request.get_json(silent=True) or {}
    old_password = payload.get("oldPassword") or ""
    new_password = payload.get("newPassword") or ""
    user = SysUser.query.get_or_404(g.current_user.id)
    if not verify_password(old_password, user.password_hash):
        raise APIError("旧密码错误")
    if len(str(new_password)) < 6:
        raise APIError("新密码长度不能少于 6 位")
    user.password_hash = password_hash(str(new_password))
    db.session.commit()
    return ruoyi_ok(msg="密码修改成功")


@bp.post("/user/profile/avatar")
@auth_required()
def upload_profile_avatar():
    return ruoyi_ok({"imgUrl": ""}, msg="头像上传成功")


@bp.get("/user/authRole/<int:user_id>")
@auth_required(["admin"])
def get_auth_role(user_id):
    user = ensure_user_in_scope(SysUser.query.get_or_404(user_id))
    payload = serialize_user(user)
    return ruoyi_ok(
        {
            "user": {
                "userId": payload["userId"],
                "userName": payload["userName"],
                "nickName": payload["nickName"],
            },
            "roles": serialize_role_list(payload["roleIds"]),
        }
    )


@bp.put("/user/authRole")
@auth_required(["admin"])
def update_auth_role():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("userId") or request.args.get("userId")
    role_ids_raw = payload.get("roleIds") or request.args.get("roleIds") or ""
    if not user_id:
        raise APIError("用户编号不能为空")
    user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
    role_ids = [int(item) for item in str(role_ids_raw).split(",") if str(item).strip()]
    if not role_ids:
        raise APIError("请至少选择一个角色")
    role_payload = {"roleIds": role_ids, "studentId": user.student_id, "userName": user.username, "nickName": user.real_name, "phonenumber": user.mobile, "email": user.email, "status": enabled_status_label(user.status)}
    ensure_assignable_roles(role_payload)
    apply_user_form(user, role_payload, creating=False)
    if user.id == g.current_user.id and "admin" not in user.role_codes:
        raise APIError("当前登录管理员账号不能移除管理员角色")
    db.session.commit()
    return ruoyi_ok(msg="角色授权成功")


@bp.get("/user/deptTree")
@auth_required(["admin"])
def get_user_dept_tree():
    return ruoyi_ok({"data": build_scope_dept_tree()})


@bp.post("/user/importTemplate")
@auth_required(["admin"])
def download_user_import_template():
    content = create_workbook_bytes(
        [
            {
                "title": "账号导入模板",
                "headers": ["登录账号", "姓名", "手机", "邮箱", "角色", "关联学号", "状态"],
                "rows": [
                    ["teacher_01", "张老师", "13800000011", "teacher01@example.com", "teacher", "", "0"],
                    ["reviewer_01", "审核员王", "13800000012", "reviewer01@example.com", "reviewer", "", "0"],
                    ["20260001", "张三", "", "", "student", "20260001", "0"],
                ],
            }
        ]
    )
    _, _, target_path = create_export_file("账号导入模板.xlsx", content, "system_user_import_template", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="账号导入模板.xlsx", mimetype=XLSX_MIMETYPE)


@bp.post("/user/importData")
@auth_required(["admin"])
def import_users():
    overwrite = str(request.args.get("updateSupport") or request.form.get("overwrite") or "0").strip() in {"1", "true", "yes", "on"}
    file = request.files.get("file")
    if not file:
        raise APIError("请上传导入文件")

    task = ImportTask(task_type=USER_IMPORT_TASK_TYPE, status="processing", created_by=g.current_user.id)
    db.session.add(task)
    db.session.flush()

    records = parse_tabular_file(file)
    if hasattr(file.stream, "seek"):
        file.stream.seek(0)
    attachment = save_uploaded_attachment(file, "system_user_import_source", g.current_user.id)
    task.source_file_id = attachment.id

    success_count = 0
    fail_count = 0
    errors = []
    for index, record in enumerate(records, start=2):
        try:
            with db.session.begin_nested():
                upsert_user_record(record, overwrite)
            success_count += 1
        except Exception as error:
            fail_count += 1
            errors.append(f"第 {index} 行：{error}")

    task.success_count = success_count
    task.fail_count = fail_count
    task.status = "completed" if fail_count == 0 else "partial_success"
    db.session.commit()

    message = f"导入完成，成功 {success_count} 条，失败 {fail_count} 条。"
    if errors:
        message = f"{message}<br/>{'<br/>'.join(errors)}"
    return ruoyi_ok(msg=message)


@bp.post("/user/export")
@auth_required(["admin"])
def export_users():
    role_code = (request.form.get("roleCode") or request.args.get("roleCode") or "").strip()
    items = find_users(role_code=role_code or None).all()
    rows = [
        [
            item.username,
            item.real_name,
            item.mobile or "",
            item.email or "",
            "、".join(role.role_name for role in item.roles),
            resolve_bound_student(student_id=item.student_id).student_no if item.student_id else "",
            "启用" if int(item.status or 0) == 1 else "停用",
            item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
        ]
        for item in items
    ]
    content = create_workbook_bytes(
        [
            {
                "title": "账号列表",
                "headers": ["登录账号", "姓名", "手机", "邮箱", "角色", "关联学号", "状态", "创建时间（北京时间）"],
                "rows": rows,
            }
        ]
    )
    _, _, target_path = create_export_file("账号列表.xlsx", content, "system_user_export", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="账号列表.xlsx", mimetype=XLSX_MIMETYPE)
