import re

from flask import current_app

from .data_scope import user_dept_ids
from .errors import APIError
from .extensions import db
from .models import StudentInfo, SysRole, SysUser
from .security import password_hash


SYSTEM_ROLE_CODES = ("admin", "teacher", "reviewer", "student")
ROLE_LABEL_TO_CODE = {
    "系统管理员": "admin",
    "管理员": "admin",
    "admin": "admin",
    "竞赛教师": "teacher",
    "竞赛管理员": "teacher",
    "教师": "teacher",
    "teacher": "teacher",
    "审核人员": "reviewer",
    "审核员": "reviewer",
    "审核人": "reviewer",
    "reviewer": "reviewer",
    "学生用户": "student",
    "学生": "student",
    "student": "student",
}
DEPT_LABELS = {
    11: "系统管理员",
    12: "教师与负责人",
    13: "审核人员",
    14: "学生账号",
}


def default_user_password():
    return current_app.config.get("DEFAULT_USER_PASSWORD", "Demo123!")


def enabled_status_label(value):
    return "0" if int(value or 0) == 1 else "1"


def parse_enabled_status(value, default=1):
    if value in (None, ""):
        return int(default)
    normalized = str(value).strip().lower()
    if normalized in {"0", "true", "yes", "y", "on", "active", "enabled", "启用"}:
        return 1
    if normalized in {"1", "false", "no", "n", "off", "inactive", "disabled", "停用"}:
        return 0
    raise APIError("账号状态不合法")


def system_roles():
    return SysRole.query.order_by(SysRole.id.asc()).all()


def system_role_map():
    return {item.role_code: item for item in system_roles()}


def serialize_role(role, selected_role_ids=None):
    return {
        "roleId": role.id,
        "roleName": role.role_name,
        "roleKey": role.role_code,
        "status": enabled_status_label(role.status),
        "createTime": role.created_at.isoformat() if role.created_at else None,
        "flag": bool(selected_role_ids and role.id in selected_role_ids),
    }


def parse_role_codes(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = re.split(r"[，,、/\s]+", str(value))
    role_codes = []
    for raw_item in raw_items:
        normalized = ROLE_LABEL_TO_CODE.get(str(raw_item or "").strip().lower()) or ROLE_LABEL_TO_CODE.get(str(raw_item or "").strip())
        if normalized and normalized not in role_codes:
            role_codes.append(normalized)
    return role_codes


def resolve_roles(role_ids=None, role_codes=None):
    role_map = system_role_map()
    selected = []
    seen = set()
    if role_ids:
        items = SysRole.query.filter(SysRole.id.in_([int(item) for item in role_ids])).all()
        for item in items:
            if item.role_code in role_map and item.id not in seen:
                selected.append(item)
                seen.add(item.id)
    for role_code in parse_role_codes(role_codes):
        role = role_map.get(role_code)
        if not role:
            continue
        if role.id in seen:
            continue
        selected.append(role)
        seen.add(role.id)
    if not selected:
        raise APIError("请至少选择一个角色")
    return selected


def resolve_bound_student(student_id=None, student_no=None, required=False):
    student = None
    if student_id not in (None, ""):
        student = StudentInfo.query.get(int(student_id))
    elif student_no not in (None, ""):
        student = StudentInfo.query.filter_by(student_no=str(student_no).strip()).first()
    if required and not student:
        raise APIError("关联学生不存在")
    return student


def bound_student_payload(student):
    if not student:
        return {}
    return {
        "studentId": student.id,
        "studentNo": student.student_no,
        "studentName": student.name,
    }


def serialize_user(user):
    student = resolve_bound_student(student_id=user.student_id)
    role_codes = user.role_codes
    role_names = [role.role_name for role in user.roles]
    dept_ids = sorted(user_dept_ids(user))
    dept_id = dept_ids[0] if dept_ids else 1
    payload = {
        "userId": user.id,
        "userName": user.username,
        "nickName": user.real_name,
        "phonenumber": user.mobile or "",
        "email": user.email or "",
        "status": enabled_status_label(user.status),
        "roleIds": [role.id for role in user.roles],
        "roleCodes": role_codes,
        "roleNames": role_names,
        "roleLabel": "、".join(role_names) if role_names else "未分配",
        "accountSource": "student_sync" if user.student_id else "manual",
        "accountSourceLabel": "学生档案联动" if user.student_id else "手工维护",
        "createTime": user.created_at.isoformat() if user.created_at else None,
        "updateTime": user.updated_at.isoformat() if user.updated_at else None,
        "dept": {"deptName": DEPT_LABELS.get(dept_id, "竞赛管理平台")},
        "deptId": dept_id,
    }
    payload.update(bound_student_payload(student))
    return payload


def ensure_unique_username(username, user_id=None):
    query = SysUser.query.filter(SysUser.username == username)
    if user_id:
        query = query.filter(SysUser.id != int(user_id))
    if query.first():
        raise APIError("登录账号已存在")


def ensure_unique_bound_student(student_id, user_id=None):
    if student_id in (None, ""):
        return
    query = SysUser.query.filter(SysUser.student_id == int(student_id))
    if user_id:
        query = query.filter(SysUser.id != int(user_id))
    if query.first():
        raise APIError("该学生已绑定其他登录账号")


def sync_student_account(student):
    if not student:
        return None
    student_role = system_role_map().get("student")
    if not student_role:
        raise APIError("学生角色不存在，无法自动创建账号")

    bound_user = SysUser.query.filter_by(student_id=student.id).first()
    username_user = SysUser.query.filter_by(username=student.student_no).first()
    if bound_user and username_user and bound_user.id != username_user.id:
        raise APIError("该学生存在冲突账号，请先清理重复账号后再同步")

    user = bound_user or username_user
    if user and user.student_id not in (None, student.id):
        raise APIError("学号已被其他账号占用，无法自动创建学生账号")

    if not user:
        user = SysUser(
            username=student.student_no,
            password_hash=password_hash(default_user_password()),
            real_name=student.name,
            mobile=student.mobile,
            email=student.email,
            student_id=student.id,
            status=int(student.status or 1),
        )
        db.session.add(user)
        db.session.flush()
    else:
        ensure_unique_username(student.student_no, user.id)
        user.username = student.student_no
        user.real_name = student.name
        user.mobile = student.mobile
        user.email = student.email
        user.student_id = student.id
        user.status = int(student.status or 1)

    if student_role.id not in {role.id for role in user.roles}:
        user.roles.append(student_role)
    return user


def reconcile_student_accounts():
    synced_count = 0
    errors = []
    students = StudentInfo.query.order_by(StudentInfo.id.asc()).all()
    for student in students:
        try:
            with db.session.begin_nested():
                sync_student_account(student)
            synced_count += 1
        except Exception as error:
            errors.append(f"{student.student_no}: {error}")
    if errors:
        current_app.logger.warning("student account reconcile warnings: %s", "; ".join(errors))
    return {"syncedCount": synced_count, "errors": errors}


def apply_user_form(user, payload, creating=False):
    role_ids = payload.get("roleIds") or []
    role_codes = payload.get("roleCodes") or payload.get("roles") or []
    roles = resolve_roles(role_ids=role_ids, role_codes=role_codes)
    selected_role_codes = {role.role_code for role in roles}

    student = None
    if "student" in selected_role_codes:
        student = resolve_bound_student(
            student_id=payload.get("studentId"),
            student_no=payload.get("studentNo"),
            required=True,
        )
        ensure_unique_bound_student(student.id, user.id if user.id else None)
        username = student.student_no
    else:
        username = str(payload.get("userName") or user.username or "").strip()
        if not username:
            raise APIError("登录账号不能为空")

    ensure_unique_username(username, user.id if user.id else None)

    if creating:
        raw_password = payload.get("password") or default_user_password()
        if not raw_password or len(str(raw_password)) < 5:
            raise APIError("登录密码长度不能少于 5 位")
        user.password_hash = password_hash(str(raw_password))

    if student:
        user.username = student.student_no
        user.real_name = student.name
        user.mobile = student.mobile
        user.email = student.email
        user.student_id = student.id
        user.status = int(student.status or 1)
    else:
        user.username = username
        user.real_name = str(payload.get("nickName") or user.real_name or "").strip()
        if not user.real_name:
            raise APIError("姓名不能为空")
        user.mobile = str(payload.get("phonenumber") or "").strip() or None
        user.email = str(payload.get("email") or "").strip() or None
        user.student_id = None
        user.status = parse_enabled_status(payload.get("status"), user.status if user.status is not None else 1)

    user.roles = roles
    return user
