from copy import deepcopy
from datetime import datetime

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import or_

from ..account_service import parse_enabled_status, serialize_user
from ..audit_store import clean_login_events, clean_oper_events, delete_login_events, delete_oper_events, list_login_events, list_oper_events
from ..common import paginate_items
from ..data_scope import apply_user_data_scope, build_scope_dept_tree, can_access_user, role_assignable_by_user
from ..errors import APIError
from ..excel_utils import XLSX_MIMETYPE, create_export_file, create_workbook_bytes
from ..extensions import db
from ..models import SysRole, SysUser
from ..platform_ops import backup_file_path, create_system_backup, restore_system_backup, storage_runtime_profile
from ..security import auth_required
from ..system_compat_store import (
    delete_config_items,
    delete_dict_data_items,
    delete_dict_types,
    delete_menu,
    delete_role_meta,
    ensure_role_meta,
    get_config_item,
    get_dict_data_item,
    get_dict_type,
    get_menu,
    list_config_items,
    list_dict_data_items,
    list_dict_types,
    list_menu_items,
    menu_tree_for_select,
    save_config_item,
    save_dict_data_item,
    save_dict_type,
    save_menu,
    save_role_meta,
    serialize_role_with_meta,
)


bp = Blueprint("system_compat", __name__)


SYSTEM_ROLE_CODES = {"admin", "teacher", "reviewer", "student"}


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


def filter_by_date(items, begin_time, end_time, field_name):
    rows = []
    for item in items:
        raw_value = item.get(field_name)
        if not raw_value:
            rows.append(item)
            continue
        try:
            current = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except ValueError:
            rows.append(item)
            continue
        if begin_time and current < begin_time:
            continue
        if end_time and current > end_time:
            continue
        rows.append(item)
    return rows


def sort_rows(items, default_field):
    order_by = (request.args.get("orderByColumn") or default_field or "").strip()
    direction = (request.args.get("isAsc") or "descending").strip().lower()
    reverse = direction != "ascending"
    if not order_by:
        return items
    return sorted(items, key=lambda item: (item.get(order_by) is None, item.get(order_by)), reverse=reverse)


def export_rows(file_name, sheet_title, headers, rows, biz_type):
    content = create_workbook_bytes([{"title": sheet_title, "headers": headers, "rows": rows}])
    _, _, target_path = create_export_file(file_name, content, biz_type, g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name=file_name, mimetype=XLSX_MIMETYPE)


def serialize_role_row(role):
    payload = serialize_role_with_meta(role)
    payload["flag"] = False
    return payload


def query_roles():
    params = request.args
    role_name = (params.get("roleName") or "").strip()
    role_key = (params.get("roleKey") or "").strip()
    status = params.get("status")
    begin_time = parse_datetime_query(params.get("beginTime"))
    end_time = parse_datetime_query(params.get("endTime"))

    query = SysRole.query.order_by(SysRole.id.asc())
    if role_name:
        query = query.filter(SysRole.role_name.like(f"%{role_name}%"))
    if role_key:
        query = query.filter(SysRole.role_code.like(f"%{role_key}%"))
    if status not in (None, ""):
        query = query.filter(SysRole.status == parse_enabled_status(status))
    if begin_time:
        query = query.filter(SysRole.created_at >= begin_time)
    if end_time:
        query = query.filter(SysRole.created_at <= end_time)
    return query


def role_tree_checked_keys(role):
    return list(ensure_role_meta(role).get("menuIds", []))


def dept_checked_keys(role):
    return list(ensure_role_meta(role).get("deptIds", []))


def query_users_for_role(role_id, allocated=True):
    params = request.args
    user_name = (params.get("userName") or "").strip()
    phone = (params.get("phonenumber") or "").strip()
    role = ensure_role_assignable(SysRole.query.get_or_404(int(role_id)))
    query = apply_user_data_scope(SysUser.query, getattr(g, "current_user", None))
    if allocated:
        query = query.filter(SysUser.roles.any(SysRole.id == role.id))
    else:
        query = query.filter(~SysUser.roles.any(SysRole.id == role.id))
    if user_name:
        query = query.filter(or_(SysUser.username.like(f"%{user_name}%"), SysUser.real_name.like(f"%{user_name}%")))
    if phone:
        query = query.filter(SysUser.mobile.like(f"%{phone}%"))
    return query.order_by(SysUser.id.asc())


def ensure_user_in_scope(user):
    if not can_access_user(getattr(g, "current_user", None), user):
        raise APIError("当前数据权限不允许访问该账号", code=403)
    return user


def ensure_role_assignable(role):
    current_user = getattr(g, "current_user", None)
    if current_user is None or "admin" in current_user.role_codes:
        return role
    if not role_assignable_by_user(role, current_user):
        raise APIError("当前数据权限不允许操作该角色", code=403)
    return role


def ensure_role_editable(role):
    if role.role_code == "admin":
        raise APIError("管理员角色不允许执行该操作")
    return role


@bp.get("/system/role/list")
@auth_required(["admin"])
def list_roles():
    items, total, _, _ = paginate_items([serialize_role_row(item) for item in query_roles().all()])
    return ruoyi_ok({"rows": items, "total": total})


@bp.get("/system/role/<int:role_id>")
@auth_required(["admin"])
def get_role(role_id):
    role = SysRole.query.get_or_404(role_id)
    return ruoyi_ok({"data": serialize_role_row(role)})


@bp.post("/system/role")
@auth_required(["admin"])
def create_role():
    payload = request.get_json(silent=True) or {}
    role_name = str(payload.get("roleName") or "").strip()
    role_key = str(payload.get("roleKey") or "").strip()
    if not role_name or not role_key:
        raise APIError("角色名称和权限字符不能为空")
    if SysRole.query.filter_by(role_code=role_key).first():
        raise APIError("权限字符已存在")
    role = SysRole(role_name=role_name, role_code=role_key, status=parse_enabled_status(payload.get("status"), 1))
    db.session.add(role)
    db.session.flush()
    save_role_meta(role.id, payload)
    db.session.commit()
    return ruoyi_ok(msg="新增成功")


@bp.put("/system/role")
@auth_required(["admin"])
def update_role():
    payload = request.get_json(silent=True) or {}
    role_id = payload.get("roleId")
    if not role_id:
        raise APIError("角色编号不能为空")
    role = ensure_role_assignable(SysRole.query.get_or_404(int(role_id)))
    role_name = str(payload.get("roleName") or "").strip()
    role_key = str(payload.get("roleKey") or "").strip()
    if not role_name or not role_key:
        raise APIError("角色名称和权限字符不能为空")
    if role.role_code in SYSTEM_ROLE_CODES and role_key != role.role_code:
        raise APIError("系统内置角色不允许修改权限字符")
    duplicated = SysRole.query.filter(SysRole.role_code == role_key, SysRole.id != role.id).first()
    if duplicated:
        raise APIError("权限字符已存在")
    role.role_name = role_name
    role.role_code = role_key
    role.status = parse_enabled_status(payload.get("status"), role.status)
    save_role_meta(role.id, payload)
    db.session.commit()
    return ruoyi_ok(msg="修改成功")


@bp.put("/system/role/dataScope")
@auth_required(["admin"])
def update_role_data_scope():
    payload = request.get_json(silent=True) or {}
    role_id = payload.get("roleId")
    if not role_id:
        raise APIError("角色编号不能为空")
    save_role_meta(role_id, payload)
    db.session.commit()
    return ruoyi_ok(msg="修改成功")


@bp.put("/system/role/changeStatus")
@auth_required(["admin"])
def change_role_status():
    payload = request.get_json(silent=True) or {}
    role_id = payload.get("roleId")
    if not role_id:
        raise APIError("角色编号不能为空")
    role = ensure_role_assignable(SysRole.query.get_or_404(int(role_id)))
    ensure_role_editable(role)
    role.status = parse_enabled_status(payload.get("status"), role.status)
    db.session.commit()
    return ruoyi_ok(msg="修改成功")


@bp.delete("/system/role/<role_ids>")
@auth_required(["admin"])
def delete_roles(role_ids):
    ids = [int(item) for item in str(role_ids).split(",") if str(item).strip()]
    roles = SysRole.query.filter(SysRole.id.in_(ids)).all()
    for role in roles:
        ensure_role_editable(role)
    for role in roles:
        user_count = SysUser.query.filter(SysUser.roles.any(SysRole.id == role.id)).count()
        if user_count:
            raise APIError("存在绑定用户的角色不允许删除")
        db.session.delete(role)
        delete_role_meta(role.id)
    db.session.commit()
    return ruoyi_ok(msg="删除成功")


@bp.get("/system/role/deptTree/<int:role_id>")
@auth_required(["admin"])
def get_role_dept_tree(role_id):
    role = SysRole.query.get_or_404(role_id)
    return ruoyi_ok({"depts": deepcopy(build_scope_dept_tree()), "checkedKeys": dept_checked_keys(role)})


@bp.get("/system/role/authUser/allocatedList")
@auth_required(["admin"])
def allocated_user_list():
    query = query_users_for_role(request.args.get("roleId"), allocated=True)
    items, total, _, _ = paginate_items([serialize_user(item) for item in query.all()])
    return ruoyi_ok({"rows": items, "total": total})


@bp.get("/system/role/authUser/unallocatedList")
@auth_required(["admin"])
def unallocated_user_list():
    query = query_users_for_role(request.args.get("roleId"), allocated=False)
    items, total, _, _ = paginate_items([serialize_user(item) for item in query.all()])
    return ruoyi_ok({"rows": items, "total": total})


@bp.put("/system/role/authUser/cancel")
@auth_required(["admin"])
def cancel_auth_user():
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("userId")
    role_id = payload.get("roleId")
    if not user_id or not role_id:
        raise APIError("用户和角色不能为空")
    role = ensure_role_assignable(SysRole.query.get_or_404(int(role_id)))
    user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
    if role.role_code == "admin" and user.id == g.current_user.id:
        raise APIError("当前登录管理员不能取消管理员角色")
    user.roles = [item for item in user.roles if int(item.id) != int(role.id)]
    db.session.commit()
    return ruoyi_ok(msg="取消授权成功")


@bp.put("/system/role/authUser/cancelAll")
@auth_required(["admin"])
def cancel_auth_user_all():
    role_id = request.args.get("roleId")
    user_ids = request.args.get("userIds") or ""
    if not role_id:
        raise APIError("角色编号不能为空")
    role = SysRole.query.get_or_404(int(role_id))
    payload = {"roleId": role_id, "userId": None}
    for user_id in [int(item) for item in user_ids.split(",") if item.strip()]:
        payload["userId"] = user_id
        user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
        if role.role_code == "admin" and user.id == g.current_user.id:
            raise APIError("当前登录管理员不能取消管理员角色")
        user.roles = [item for item in user.roles if int(item.id) != int(role.id)]
    db.session.commit()
    return ruoyi_ok(msg="取消授权成功")


@bp.put("/system/role/authUser/selectAll")
@auth_required(["admin"])
def select_auth_user_all():
    role_id = request.args.get("roleId")
    user_ids = request.args.get("userIds") or ""
    if not role_id:
        raise APIError("角色编号不能为空")
    role = SysRole.query.get_or_404(int(role_id))
    for user_id in [int(item) for item in user_ids.split(",") if item.strip()]:
        user = ensure_user_in_scope(SysUser.query.get_or_404(int(user_id)))
        if role.id not in {item.id for item in user.roles}:
            user.roles.append(role)
    db.session.commit()
    return ruoyi_ok(msg="授权成功")


@bp.post("/system/role/export")
@auth_required(["admin"])
def export_role_list():
    rows = []
    for item in query_roles().all():
        payload = serialize_role_row(item)
        rows.append([payload["roleId"], payload["roleName"], payload["roleKey"], payload["roleSort"], payload["status"], payload["remark"], payload["createTime"]])
    return export_rows("角色列表.xlsx", "角色列表", ["角色编号", "角色名称", "权限字符", "显示顺序", "状态", "备注", "创建时间"], rows, "system_role_export")


@bp.get("/system/menu/list")
@auth_required(["admin"])
def list_menu():
    menu_name = (request.args.get("menuName") or "").strip()
    status = (request.args.get("status") or "").strip()
    visible = (request.args.get("visible") or "").strip()
    rows = list_menu_items()
    if menu_name:
        rows = [item for item in rows if menu_name in item["menuName"]]
    if status:
        rows = [item for item in rows if item["status"] == status]
    if visible:
        rows = [item for item in rows if item["visible"] == visible]
    return ruoyi_ok({"data": rows})


@bp.get("/system/menu/<int:menu_id>")
@auth_required(["admin"])
def get_menu_detail(menu_id):
    item = get_menu(menu_id)
    if not item:
        raise APIError("菜单不存在")
    return ruoyi_ok({"data": item})


@bp.get("/system/menu/treeselect")
@auth_required(["admin"])
def menu_treeselect():
    return ruoyi_ok({"data": menu_tree_for_select()})


@bp.get("/system/menu/roleMenuTreeselect/<int:role_id>")
@auth_required(["admin"])
def role_menu_treeselect(role_id):
    role = SysRole.query.get_or_404(role_id)
    return ruoyi_ok({"menus": menu_tree_for_select(), "checkedKeys": role_tree_checked_keys(role)})


@bp.post("/system/menu")
@auth_required(["admin"])
def create_menu():
    payload = request.get_json(silent=True) or {}
    save_menu(payload)
    return ruoyi_ok(msg="新增成功")


@bp.put("/system/menu")
@auth_required(["admin"])
def update_menu():
    payload = request.get_json(silent=True) or {}
    save_menu(payload)
    return ruoyi_ok(msg="修改成功")


@bp.delete("/system/menu/<int:menu_id>")
@auth_required(["admin"])
def delete_menu_detail(menu_id):
    delete_menu(menu_id)
    return ruoyi_ok(msg="删除成功")


@bp.get("/system/config/list")
@auth_required(["admin"])
def list_config():
    config_name = (request.args.get("configName") or "").strip()
    config_key = (request.args.get("configKey") or "").strip()
    config_type = (request.args.get("configType") or "").strip()
    begin_time = parse_datetime_query(request.args.get("beginTime"))
    end_time = parse_datetime_query(request.args.get("endTime"))
    rows = list_config_items()
    if config_name:
        rows = [item for item in rows if config_name in item["configName"]]
    if config_key:
        rows = [item for item in rows if config_key in item["configKey"]]
    if config_type:
        rows = [item for item in rows if item["configType"] == config_type]
    rows = filter_by_date(rows, begin_time, end_time, "createTime")
    items, total, _, _ = paginate_items(rows)
    return ruoyi_ok({"rows": items, "total": total})


@bp.get("/system/config/<int:config_id>")
@auth_required(["admin"])
def get_config(config_id):
    item = get_config_item(config_id)
    if not item:
        raise APIError("参数不存在")
    return ruoyi_ok({"data": item})


@bp.post("/system/config")
@auth_required(["admin"])
def create_config():
    save_config_item(request.get_json(silent=True) or {})
    return ruoyi_ok(msg="新增成功")


@bp.put("/system/config")
@auth_required(["admin"])
def update_config():
    save_config_item(request.get_json(silent=True) or {})
    return ruoyi_ok(msg="修改成功")


@bp.delete("/system/config/<config_ids>")
@auth_required(["admin"])
def delete_config(config_ids):
    delete_config_items(config_ids)
    return ruoyi_ok(msg="删除成功")


@bp.delete("/system/config/refreshCache")
@auth_required(["admin"])
def refresh_config_cache():
    return ruoyi_ok(msg="刷新缓存成功")


@bp.post("/system/config/export")
@auth_required(["admin"])
def export_config():
    rows = [[item["configId"], item["configName"], item["configKey"], item["configValue"], item["configType"], item["remark"], item["createTime"]] for item in list_config_items()]
    return export_rows("参数配置.xlsx", "参数配置", ["编号", "参数名称", "参数键名", "参数键值", "系统内置", "备注", "创建时间"], rows, "system_config_export")


@bp.get("/system/config/runtimeProfile")
@auth_required(["admin"])
def config_runtime_profile():
    return ruoyi_ok({"data": storage_runtime_profile()})


@bp.post("/system/config/backup")
@auth_required(["admin"])
def create_config_backup():
    payload = request.get_json(silent=True) or {}
    include_uploads = payload.get("includeUploads")
    if isinstance(include_uploads, str):
        include_uploads = include_uploads.strip().lower() in {"1", "true", "yes", "y", "on"}
    result = create_system_backup(g.current_user.id, include_uploads=include_uploads if include_uploads is not None else None)
    return ruoyi_ok({"data": result}, msg="备份创建成功")


@bp.post("/system/config/backup/download")
@auth_required(["admin"])
def download_config_backup():
    payload = request.get_json(silent=True) or {}
    backup_file = request.form.get("backupFile") or payload.get("backupFile")
    target_path = backup_file_path(backup_file)
    return send_file(target_path, as_attachment=True, download_name=target_path.name, mimetype="application/zip")


@bp.post("/system/config/backup/restore")
@auth_required(["admin"])
def restore_config_backup():
    payload = request.get_json(silent=True) or {}
    backup_file = payload.get("backupFile")
    if not backup_file:
        raise APIError("备份文件不能为空")
    result = restore_system_backup(backup_file)
    return ruoyi_ok({"data": result}, msg="备份恢复成功")


@bp.get("/system/dict/type/list")
@auth_required(["admin"])
def list_dict_type():
    dict_name = (request.args.get("dictName") or "").strip()
    dict_type = (request.args.get("dictType") or "").strip()
    status = (request.args.get("status") or "").strip()
    begin_time = parse_datetime_query(request.args.get("beginTime"))
    end_time = parse_datetime_query(request.args.get("endTime"))
    rows = list_dict_types()
    if dict_name:
        rows = [item for item in rows if dict_name in item["dictName"]]
    if dict_type:
        rows = [item for item in rows if dict_type in item["dictType"]]
    if status:
        rows = [item for item in rows if item["status"] == status]
    rows = filter_by_date(rows, begin_time, end_time, "createTime")
    items, total, _, _ = paginate_items(rows)
    return ruoyi_ok({"rows": items, "total": total})


@bp.get("/system/dict/type/<int:dict_id>")
@auth_required(["admin"])
def get_dict_type_detail(dict_id):
    item = get_dict_type(dict_id)
    if not item:
        raise APIError("字典类型不存在")
    return ruoyi_ok({"data": item})


@bp.post("/system/dict/type")
@auth_required(["admin"])
def create_dict_type():
    save_dict_type(request.get_json(silent=True) or {})
    return ruoyi_ok(msg="新增成功")


@bp.put("/system/dict/type")
@auth_required(["admin"])
def update_dict_type():
    save_dict_type(request.get_json(silent=True) or {})
    return ruoyi_ok(msg="修改成功")


@bp.delete("/system/dict/type/<dict_ids>")
@auth_required(["admin"])
def delete_dict_type_detail(dict_ids):
    delete_dict_types(dict_ids)
    return ruoyi_ok(msg="删除成功")


@bp.delete("/system/dict/type/refreshCache")
@auth_required(["admin"])
def refresh_dict_cache():
    return ruoyi_ok(msg="刷新成功")


@bp.get("/system/dict/type/optionselect")
@auth_required(["admin"])
def dict_type_optionselect():
    rows = [item for item in list_dict_types() if item["status"] == "0"]
    return ruoyi_ok({"data": rows})


@bp.post("/system/dict/type/export")
@auth_required(["admin"])
def export_dict_type():
    rows = [[item["dictId"], item["dictName"], item["dictType"], item["status"], item["remark"], item["createTime"]] for item in list_dict_types()]
    return export_rows("字典类型.xlsx", "字典类型", ["编号", "字典名称", "字典类型", "状态", "备注", "创建时间"], rows, "system_dict_type_export")


@bp.get("/system/dict/data/list")
@auth_required(["admin"])
def list_dict_data():
    dict_type = (request.args.get("dictType") or "").strip()
    dict_label = (request.args.get("dictLabel") or "").strip()
    status = (request.args.get("status") or "").strip()
    rows = list_dict_data_items()
    if dict_type:
        rows = [item for item in rows if item["dictType"] == dict_type]
    if dict_label:
        rows = [item for item in rows if dict_label in item["dictLabel"]]
    if status:
        rows = [item for item in rows if item["status"] == status]
    rows.sort(key=lambda item: (item["dictSort"], item["dictCode"]))
    items, total, _, _ = paginate_items(rows)
    return ruoyi_ok({"rows": items, "total": total})


@bp.get("/system/dict/data/<int:dict_code>")
@auth_required(["admin"])
def get_dict_data_detail(dict_code):
    item = get_dict_data_item(dict_code)
    if not item:
        raise APIError("字典数据不存在")
    return ruoyi_ok({"data": item})


@bp.get("/system/dict/data/type/<dict_type>")
@auth_required()
def get_dict_data_by_type(dict_type):
    rows = [item for item in list_dict_data_items() if item["dictType"] == dict_type and item["status"] == "0"]
    rows.sort(key=lambda item: (item["dictSort"], item["dictCode"]))
    return ruoyi_ok({"data": rows})


@bp.post("/system/dict/data")
@auth_required(["admin"])
def create_dict_data():
    save_dict_data_item(request.get_json(silent=True) or {})
    return ruoyi_ok(msg="新增成功")


@bp.put("/system/dict/data")
@auth_required(["admin"])
def update_dict_data():
    save_dict_data_item(request.get_json(silent=True) or {})
    return ruoyi_ok(msg="修改成功")


@bp.delete("/system/dict/data/<dict_codes>")
@auth_required(["admin"])
def delete_dict_data_detail(dict_codes):
    delete_dict_data_items(dict_codes)
    return ruoyi_ok(msg="删除成功")


@bp.post("/system/dict/data/export")
@auth_required(["admin"])
def export_dict_data():
    rows = [[item["dictCode"], item["dictType"], item["dictLabel"], item["dictValue"], item["dictSort"], item["status"], item["remark"], item["createTime"]] for item in list_dict_data_items()]
    return export_rows("字典数据.xlsx", "字典数据", ["编码", "字典类型", "标签", "键值", "排序", "状态", "备注", "创建时间"], rows, "system_dict_data_export")


@bp.get("/monitor/operlog/list")
@auth_required(["admin"])
def list_operlog():
    oper_ip = (request.args.get("operIp") or "").strip()
    title = (request.args.get("title") or "").strip()
    oper_name = (request.args.get("operName") or "").strip()
    business_type = (request.args.get("businessType") or "").strip()
    status = (request.args.get("status") or "").strip()
    begin_time = parse_datetime_query(request.args.get("beginTime"))
    end_time = parse_datetime_query(request.args.get("endTime"))
    rows = list_oper_events()
    if oper_ip:
        rows = [item for item in rows if oper_ip in item["operIp"]]
    if title:
        rows = [item for item in rows if title in item["title"]]
    if oper_name:
        rows = [item for item in rows if oper_name in item["operName"]]
    if business_type:
        rows = [item for item in rows if item["businessType"] == business_type]
    if status:
        rows = [item for item in rows if str(item["status"]) == status]
    rows = filter_by_date(rows, begin_time, end_time, "operTime")
    rows = sort_rows(rows, "operTime")
    items, total, _, _ = paginate_items(rows)
    return ruoyi_ok({"rows": items, "total": total})


@bp.delete("/monitor/operlog/<oper_ids>")
@auth_required(["admin"])
def delete_operlog_detail(oper_ids):
    delete_oper_events(oper_ids)
    return ruoyi_ok(msg="删除成功")


@bp.delete("/monitor/operlog/clean")
@auth_required(["admin"])
def clean_operlog_detail():
    clean_oper_events()
    return ruoyi_ok(msg="清空成功")


@bp.post("/monitor/operlog/export")
@auth_required(["admin"])
def export_operlog():
    rows = [[item["operId"], item["title"], item["businessType"], item["operName"], item["operIp"], item["status"], item["costTime"], item["operTime"]] for item in list_oper_events()]
    return export_rows("操作日志.xlsx", "操作日志", ["编号", "模块", "类型", "操作人", "IP", "状态", "耗时(ms)", "时间"], rows, "monitor_operlog_export")


@bp.get("/monitor/logininfor/list")
@auth_required(["admin"])
def list_logininfor():
    ipaddr = (request.args.get("ipaddr") or "").strip()
    user_name = (request.args.get("userName") or "").strip()
    status = (request.args.get("status") or "").strip()
    begin_time = parse_datetime_query(request.args.get("beginTime"))
    end_time = parse_datetime_query(request.args.get("endTime"))
    rows = list_login_events()
    if ipaddr:
        rows = [item for item in rows if ipaddr in item["ipaddr"]]
    if user_name:
        rows = [item for item in rows if user_name in item["userName"]]
    if status:
        rows = [item for item in rows if item["status"] == status]
    rows = filter_by_date(rows, begin_time, end_time, "loginTime")
    rows = sort_rows(rows, "loginTime")
    items, total, _, _ = paginate_items(rows)
    return ruoyi_ok({"rows": items, "total": total})


@bp.delete("/monitor/logininfor/<info_ids>")
@auth_required(["admin"])
def delete_logininfor_detail(info_ids):
    delete_login_events(info_ids)
    return ruoyi_ok(msg="删除成功")


@bp.delete("/monitor/logininfor/clean")
@auth_required(["admin"])
def clean_logininfor_detail():
    clean_login_events()
    return ruoyi_ok(msg="清空成功")


@bp.get("/monitor/logininfor/unlock/<user_name>")
@auth_required(["admin"])
def unlock_login_user(user_name):
    return ruoyi_ok(msg=f"用户{user_name}解锁成功")


@bp.post("/monitor/logininfor/export")
@auth_required(["admin"])
def export_logininfor():
    rows = [[item["infoId"], item["userName"], item["ipaddr"], item["loginLocation"], item["os"], item["browser"], item["status"], item["msg"], item["loginTime"]] for item in list_login_events()]
    return export_rows("登录日志.xlsx", "登录日志", ["编号", "用户", "IP", "地点", "系统", "浏览器", "状态", "描述", "时间"], rows, "monitor_logininfor_export")
