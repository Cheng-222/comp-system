import json
from copy import deepcopy

from .account_service import enabled_status_label
from .errors import APIError
from .extensions import db
from .models import SysRole, SystemConfig, SystemDictData, SystemDictType, SystemMenu, SystemRoleMeta
from .platform_ops import (
    BACKUP_DIR_KEY,
    BACKUP_INCLUDE_UPLOADS_KEY,
    BACKUP_KEEP_COUNT_KEY,
    STORAGE_DRIVER_KEY,
    STORAGE_LAYOUT_KEY,
    STORAGE_ROOT_KEY,
    ensure_runtime_directories,
    validate_runtime_config,
)


DEFAULT_MENU_ITEMS = [
    {"menuId": 1, "parentId": 0, "menuName": "竞赛管理", "icon": "skill", "orderNum": 1, "path": "competition", "component": "Layout", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "M", "perms": ""},
    {"menuId": 101, "parentId": 1, "menuName": "学生管理", "icon": "peoples", "orderNum": 1, "path": "students", "component": "competition/student/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:student:manage"},
    {"menuId": 102, "parentId": 1, "menuName": "赛事管理", "icon": "education", "orderNum": 2, "path": "contests", "component": "competition/contest/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:contest:manage"},
    {"menuId": 103, "parentId": 1, "menuName": "报名管理", "icon": "form", "orderNum": 3, "path": "registrations", "component": "competition/registration/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:registration:manage"},
    {"menuId": 104, "parentId": 1, "menuName": "资格管理", "icon": "job", "orderNum": 4, "path": "qualifications", "component": "competition/qualification/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:qualification:manage"},
    {"menuId": 105, "parentId": 1, "menuName": "材料审核", "icon": "clipboard", "orderNum": 5, "path": "reviews", "component": "competition/review/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:review:manage"},
    {"menuId": 106, "parentId": 1, "menuName": "通知中心", "icon": "message", "orderNum": 6, "path": "messages", "component": "competition/message/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:message:manage"},
    {"menuId": 107, "parentId": 1, "menuName": "赛后管理", "icon": "documentation", "orderNum": 7, "path": "results", "component": "competition/result/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:result:manage"},
    {"menuId": 108, "parentId": 1, "menuName": "统计报表", "icon": "chart", "orderNum": 8, "path": "statistics", "component": "competition/statistics/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:statistics:view"},
    {"menuId": 109, "parentId": 1, "menuName": "文件中心", "icon": "documentation", "orderNum": 9, "path": "files", "component": "competition/file/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "competition:file:view"},
    {"menuId": 2, "parentId": 0, "menuName": "系统设置", "icon": "system", "orderNum": 2, "path": "system", "component": "Layout", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "M", "perms": ""},
    {"menuId": 201, "parentId": 2, "menuName": "账号管理", "icon": "user", "orderNum": 1, "path": "user", "component": "system/user/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "system:user:list"},
    {"menuId": 2011, "parentId": 201, "menuName": "账号新增", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:user:add"},
    {"menuId": 2012, "parentId": 201, "menuName": "账号修改", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:user:edit"},
    {"menuId": 2013, "parentId": 201, "menuName": "账号删除", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:user:remove"},
    {"menuId": 2014, "parentId": 201, "menuName": "账号导出", "icon": "", "orderNum": 4, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:user:export"},
    {"menuId": 202, "parentId": 2, "menuName": "角色管理", "icon": "peoples", "orderNum": 2, "path": "role", "component": "system/role/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "system:role:list"},
    {"menuId": 2021, "parentId": 202, "menuName": "角色新增", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:role:add"},
    {"menuId": 2022, "parentId": 202, "menuName": "角色修改", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:role:edit"},
    {"menuId": 2023, "parentId": 202, "menuName": "角色删除", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:role:remove"},
    {"menuId": 2024, "parentId": 202, "menuName": "角色导出", "icon": "", "orderNum": 4, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:role:export"},
    {"menuId": 203, "parentId": 2, "menuName": "菜单管理", "icon": "tree-table", "orderNum": 3, "path": "menu", "component": "system/menu/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "system:menu:list"},
    {"menuId": 2031, "parentId": 203, "menuName": "菜单新增", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:menu:add"},
    {"menuId": 2032, "parentId": 203, "menuName": "菜单修改", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:menu:edit"},
    {"menuId": 2033, "parentId": 203, "menuName": "菜单删除", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:menu:remove"},
    {"menuId": 204, "parentId": 2, "menuName": "字典管理", "icon": "dict", "orderNum": 4, "path": "dict", "component": "system/dict/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "system:dict:list"},
    {"menuId": 2041, "parentId": 204, "menuName": "字典新增", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:dict:add"},
    {"menuId": 2042, "parentId": 204, "menuName": "字典修改", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:dict:edit"},
    {"menuId": 2043, "parentId": 204, "menuName": "字典删除", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:dict:remove"},
    {"menuId": 2044, "parentId": 204, "menuName": "字典导出", "icon": "", "orderNum": 4, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:dict:export"},
    {"menuId": 205, "parentId": 2, "menuName": "参数管理", "icon": "edit", "orderNum": 5, "path": "config", "component": "system/config/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "system:config:list"},
    {"menuId": 2051, "parentId": 205, "menuName": "参数新增", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:config:add"},
    {"menuId": 2052, "parentId": 205, "menuName": "参数修改", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:config:edit"},
    {"menuId": 2053, "parentId": 205, "menuName": "参数删除", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:config:remove"},
    {"menuId": 2054, "parentId": 205, "menuName": "参数导出", "icon": "", "orderNum": 4, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "system:config:export"},
    {"menuId": 3, "parentId": 0, "menuName": "系统监控", "icon": "monitor", "orderNum": 3, "path": "monitor", "component": "Layout", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "M", "perms": ""},
    {"menuId": 301, "parentId": 3, "menuName": "操作日志", "icon": "log", "orderNum": 1, "path": "operlog", "component": "monitor/operlog/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "monitor:operlog:list"},
    {"menuId": 3011, "parentId": 301, "menuName": "操作日志详情", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "monitor:operlog:query"},
    {"menuId": 3012, "parentId": 301, "menuName": "操作日志删除", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "monitor:operlog:remove"},
    {"menuId": 3013, "parentId": 301, "menuName": "操作日志导出", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "monitor:operlog:export"},
    {"menuId": 302, "parentId": 3, "menuName": "登录日志", "icon": "logininfor", "orderNum": 2, "path": "logininfor", "component": "monitor/logininfor/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "monitor:logininfor:list"},
    {"menuId": 3021, "parentId": 302, "menuName": "登录日志解锁", "icon": "", "orderNum": 1, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "monitor:logininfor:unlock"},
    {"menuId": 3022, "parentId": 302, "menuName": "登录日志删除", "icon": "", "orderNum": 2, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "monitor:logininfor:remove"},
    {"menuId": 3023, "parentId": 302, "menuName": "登录日志导出", "icon": "", "orderNum": 3, "path": "", "component": "", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "F", "perms": "monitor:logininfor:export"},
    {"menuId": 303, "parentId": 3, "menuName": "存储与备份", "icon": "server", "orderNum": 3, "path": "runtime", "component": "monitor/runtime/index", "query": "", "isFrame": "1", "isCache": "0", "visible": "0", "status": "0", "menuType": "C", "perms": "monitor:runtime:list"},
]


DEFAULT_ROLE_MENU_IDS = {
    "admin": [item["menuId"] for item in DEFAULT_MENU_ITEMS],
    "teacher": [1, 102, 103, 104, 106, 107, 108, 109],
    "reviewer": [1, 103, 105, 106, 109],
    "student": [1, 103, 106, 107],
}


DEFAULT_CONFIG_ITEMS = [
    {"configId": 1, "configName": "用户初始密码", "configKey": "sys.user.initPassword", "configValue": "Demo123!", "configType": "Y", "remark": "系统初始化与账号导入时使用。"},
    {"configId": 2, "configName": "附件根目录", "configKey": STORAGE_ROOT_KEY, "configValue": "uploads", "configType": "Y", "remark": "本地开发默认附件目录。"},
    {"configId": 3, "configName": "默认时区", "configKey": "competition.timezone", "configValue": "Asia/Shanghai", "configType": "N", "remark": "用于导出与时间展示。"},
    {"configId": 4, "configName": "附件存储驱动", "configKey": STORAGE_DRIVER_KEY, "configValue": "local", "configType": "Y", "remark": "当前支持 local，本地文件系统存储。"},
    {"configId": 5, "configName": "附件目录布局", "configKey": STORAGE_LAYOUT_KEY, "configValue": "flat", "configType": "N", "remark": "flat 为平铺目录，dated 为按年月分层目录。"},
    {"configId": 6, "configName": "备份目录", "configKey": BACKUP_DIR_KEY, "configValue": "backups", "configType": "Y", "remark": "系统备份包输出目录。"},
    {"configId": 7, "configName": "备份保留数量", "configKey": BACKUP_KEEP_COUNT_KEY, "configValue": "5", "configType": "N", "remark": "超过数量后自动清理更旧的备份包。"},
    {"configId": 8, "configName": "备份是否包含附件", "configKey": BACKUP_INCLUDE_UPLOADS_KEY, "configValue": "Y", "configType": "N", "remark": "Y 为包含附件目录，N 为仅备份数据库快照。"},
]


DEFAULT_DICT_TYPES = [
    {"dictId": 1, "dictName": "启停状态", "dictType": "sys_normal_disable", "status": "0", "remark": "通用启用/停用状态。"},
    {"dictId": 2, "dictName": "是否", "dictType": "sys_yes_no", "status": "0", "remark": "通用是否字典。"},
    {"dictId": 3, "dictName": "通用状态", "dictType": "sys_common_status", "status": "0", "remark": "日志成功/失败等状态。"},
    {"dictId": 4, "dictName": "操作类型", "dictType": "sys_oper_type", "status": "0", "remark": "操作日志类型。"},
    {"dictId": 5, "dictName": "显示状态", "dictType": "sys_show_hide", "status": "0", "remark": "菜单显示/隐藏状态。"},
]


DEFAULT_DICT_DATA = [
    {"dictCode": 1, "dictSort": 1, "dictLabel": "正常", "dictValue": "0", "dictType": "sys_normal_disable", "cssClass": "", "listClass": "success", "isDefault": "Y", "status": "0", "remark": "启用状态"},
    {"dictCode": 2, "dictSort": 2, "dictLabel": "停用", "dictValue": "1", "dictType": "sys_normal_disable", "cssClass": "", "listClass": "danger", "isDefault": "N", "status": "0", "remark": "停用状态"},
    {"dictCode": 3, "dictSort": 1, "dictLabel": "是", "dictValue": "Y", "dictType": "sys_yes_no", "cssClass": "", "listClass": "success", "isDefault": "Y", "status": "0", "remark": "是"},
    {"dictCode": 4, "dictSort": 2, "dictLabel": "否", "dictValue": "N", "dictType": "sys_yes_no", "cssClass": "", "listClass": "info", "isDefault": "N", "status": "0", "remark": "否"},
    {"dictCode": 5, "dictSort": 1, "dictLabel": "成功", "dictValue": "0", "dictType": "sys_common_status", "cssClass": "", "listClass": "success", "isDefault": "Y", "status": "0", "remark": "成功"},
    {"dictCode": 6, "dictSort": 2, "dictLabel": "失败", "dictValue": "1", "dictType": "sys_common_status", "cssClass": "", "listClass": "danger", "isDefault": "N", "status": "0", "remark": "失败"},
    {"dictCode": 7, "dictSort": 1, "dictLabel": "其它", "dictValue": "0", "dictType": "sys_oper_type", "cssClass": "", "listClass": "info", "isDefault": "Y", "status": "0", "remark": "其它操作"},
    {"dictCode": 8, "dictSort": 2, "dictLabel": "新增", "dictValue": "1", "dictType": "sys_oper_type", "cssClass": "", "listClass": "success", "isDefault": "N", "status": "0", "remark": "新增操作"},
    {"dictCode": 9, "dictSort": 3, "dictLabel": "修改", "dictValue": "2", "dictType": "sys_oper_type", "cssClass": "", "listClass": "warning", "isDefault": "N", "status": "0", "remark": "修改操作"},
    {"dictCode": 10, "dictSort": 4, "dictLabel": "删除", "dictValue": "3", "dictType": "sys_oper_type", "cssClass": "", "listClass": "danger", "isDefault": "N", "status": "0", "remark": "删除操作"},
    {"dictCode": 11, "dictSort": 5, "dictLabel": "授权", "dictValue": "4", "dictType": "sys_oper_type", "cssClass": "", "listClass": "primary", "isDefault": "N", "status": "0", "remark": "授权操作"},
    {"dictCode": 12, "dictSort": 6, "dictLabel": "导出", "dictValue": "5", "dictType": "sys_oper_type", "cssClass": "", "listClass": "warning", "isDefault": "N", "status": "0", "remark": "导出操作"},
    {"dictCode": 13, "dictSort": 7, "dictLabel": "导入", "dictValue": "6", "dictType": "sys_oper_type", "cssClass": "", "listClass": "primary", "isDefault": "N", "status": "0", "remark": "导入操作"},
    {"dictCode": 14, "dictSort": 1, "dictLabel": "显示", "dictValue": "0", "dictType": "sys_show_hide", "cssClass": "", "listClass": "success", "isDefault": "Y", "status": "0", "remark": "显示状态"},
    {"dictCode": 15, "dictSort": 2, "dictLabel": "隐藏", "dictValue": "1", "dictType": "sys_show_hide", "cssClass": "", "listClass": "info", "isDefault": "N", "status": "0", "remark": "隐藏状态"},
]


DEPT_TREE = [
    {
        "id": 1,
        "label": "竞赛管理平台",
        "children": [
            {"id": 11, "label": "系统管理员"},
            {"id": 12, "label": "教师与负责人"},
            {"id": 13, "label": "审核人员"},
            {"id": 14, "label": "学生账号"},
        ],
    }
]


BUILTIN_DICT_TYPES = {"sys_normal_disable", "sys_yes_no", "sys_common_status", "sys_oper_type", "sys_show_hide"}


def _load_json_int_list(raw_value):
    try:
        values = json.loads(raw_value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    result = []
    for item in values:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _dump_json_int_list(values):
    return json.dumps(_coerce_int_list(values), ensure_ascii=False)


def _coerce_int_list(values):
    result = []
    seen = set()
    for item in values or []:
        try:
            current = int(item)
        except (TypeError, ValueError):
            continue
        if current in seen:
            continue
        seen.add(current)
        result.append(current)
    return result


def _next_id(model):
    current = db.session.query(db.func.max(model.id)).scalar()
    return int(current or 0) + 1


def _serialize_menu(row):
    return {
        "menuId": row.id,
        "parentId": row.parent_id,
        "menuName": row.menu_name,
        "icon": row.icon,
        "orderNum": row.order_num,
        "path": row.path,
        "component": row.component,
        "query": row.query_value,
        "isFrame": row.is_frame,
        "isCache": row.is_cache,
        "visible": row.visible,
        "status": row.status,
        "menuType": row.menu_type,
        "perms": row.perms,
        "createTime": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_config(row):
    return {
        "configId": row.id,
        "configName": row.config_name,
        "configKey": row.config_key,
        "configValue": row.config_value,
        "configType": row.config_type,
        "remark": row.remark,
        "createTime": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_dict_type(row):
    return {
        "dictId": row.id,
        "dictName": row.dict_name,
        "dictType": row.dict_type,
        "status": row.status,
        "remark": row.remark,
        "createTime": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_dict_data(row):
    return {
        "dictCode": row.id,
        "dictSort": row.dict_sort,
        "dictLabel": row.dict_label,
        "dictValue": row.dict_value,
        "dictType": row.dict_type,
        "cssClass": row.css_class,
        "listClass": row.list_class,
        "isDefault": row.is_default,
        "status": row.status,
        "remark": row.remark,
        "createTime": row.created_at.isoformat() if row.created_at else None,
    }


def _default_role_meta(role):
    return {
        "roleSort": int(role.id or 0),
        "dataScope": "1",
        "menuIds": list(DEFAULT_ROLE_MENU_IDS.get(role.role_code, [])),
        "deptIds": [],
        "remark": "",
    }


def _serialize_role_meta(row, role):
    if row is None:
        return _default_role_meta(role)
    return {
        "roleSort": row.role_sort,
        "dataScope": row.data_scope,
        "menuIds": _load_json_int_list(row.menu_ids_json),
        "deptIds": _load_json_int_list(row.dept_ids_json),
        "remark": row.remark,
    }


def _build_tree(items, id_key="menuId", parent_key="parentId", root_value=0):
    node_map = {}
    for item in items:
        current = deepcopy(item)
        current["children"] = []
        node_map[current[id_key]] = current
    roots = []
    for item in node_map.values():
        parent_id = item.get(parent_key, root_value)
        if parent_id == root_value or parent_id not in node_map:
            roots.append(item)
        else:
            node_map[parent_id]["children"].append(item)
    for item in node_map.values():
        item["children"].sort(key=lambda row: (row.get("orderNum", 0), row.get(id_key, 0)))
    roots.sort(key=lambda row: (row.get("orderNum", 0), row.get(id_key, 0)))
    return roots


def _menu_children(children):
    rows = []
    for item in children:
        rows.append({"id": item["menuId"], "label": item["menuName"], "children": _menu_children(item.get("children", []))})
    return rows


def _serialize_menu_rows(rows):
    return [_serialize_menu(item) for item in rows]


def _menu_row_sort_key(row):
    return (row.parent_id, row.order_num, row.id)


def _collect_ancestor_ids(menu_ids, row_map):
    pending = [int(item) for item in menu_ids or [] if int(item) in row_map]
    resolved = set(pending)
    while pending:
        current_id = pending.pop()
        current = row_map.get(current_id)
        if current is None:
            continue
        parent_id = int(current.parent_id or 0)
        if parent_id and parent_id in row_map and parent_id not in resolved:
            resolved.add(parent_id)
            pending.append(parent_id)
    return resolved


def ensure_system_compat_seed():
    created = False
    existing_menu_map = {
        row.id: row
        for row in SystemMenu.query.filter(SystemMenu.id.in_([int(item["menuId"]) for item in DEFAULT_MENU_ITEMS])).all()
    }
    for payload in DEFAULT_MENU_ITEMS:
        current_row = existing_menu_map.get(int(payload["menuId"]))
        if current_row is None:
            current_row = SystemMenu(
                id=int(payload["menuId"]),
                parent_id=int(payload["parentId"]),
                menu_name=payload["menuName"],
                icon=payload["icon"],
                order_num=int(payload["orderNum"]),
                path=payload["path"],
                component=payload["component"],
                query_value=payload["query"],
                is_frame=payload["isFrame"],
                is_cache=payload["isCache"],
                visible=payload["visible"],
                status=payload["status"],
                menu_type=payload["menuType"],
                perms=payload["perms"],
            )
            db.session.add(current_row)
            existing_menu_map[current_row.id] = current_row
            created = True
            continue
        # Keep built-in menus aligned with shipped icon/component metadata.
        if (
            current_row.icon != payload["icon"]
            or current_row.component != payload["component"]
            or current_row.path != payload["path"]
            or current_row.perms != payload["perms"]
        ):
            current_row.icon = payload["icon"]
            current_row.component = payload["component"]
            current_row.path = payload["path"]
            current_row.perms = payload["perms"]
            created = True
    for payload in DEFAULT_CONFIG_ITEMS:
        if db.session.get(SystemConfig, int(payload["configId"])) is None:
            db.session.add(
                SystemConfig(
                    id=int(payload["configId"]),
                    config_name=payload["configName"],
                    config_key=payload["configKey"],
                    config_value=payload["configValue"],
                    config_type=payload["configType"],
                    remark=payload["remark"],
                )
            )
            created = True
    for payload in DEFAULT_DICT_TYPES:
        if db.session.get(SystemDictType, int(payload["dictId"])) is None:
            db.session.add(
                SystemDictType(
                    id=int(payload["dictId"]),
                    dict_name=payload["dictName"],
                    dict_type=payload["dictType"],
                    status=payload["status"],
                    remark=payload["remark"],
                )
            )
            created = True
    for payload in DEFAULT_DICT_DATA:
        if db.session.get(SystemDictData, int(payload["dictCode"])) is None:
            db.session.add(
                SystemDictData(
                    id=int(payload["dictCode"]),
                    dict_sort=int(payload["dictSort"]),
                    dict_label=payload["dictLabel"],
                    dict_value=payload["dictValue"],
                    dict_type=payload["dictType"],
                    css_class=payload["cssClass"],
                    list_class=payload["listClass"],
                    is_default=payload["isDefault"],
                    status=payload["status"],
                    remark=payload["remark"],
                )
            )
            created = True
    for role in SysRole.query.order_by(SysRole.id.asc()).all():
        if role.role_code not in DEFAULT_ROLE_MENU_IDS:
            continue
        current = SystemRoleMeta.query.filter_by(role_id=role.id).first()
        if current is None:
            defaults = _default_role_meta(role)
            db.session.add(
                SystemRoleMeta(
                    role_id=role.id,
                    role_sort=defaults["roleSort"],
                    data_scope=defaults["dataScope"],
                    menu_ids_json=_dump_json_int_list(defaults["menuIds"]),
                    dept_ids_json=_dump_json_int_list(defaults["deptIds"]),
                    remark=defaults["remark"],
                )
            )
            created = True
            continue
        if role.role_code in {"admin", "teacher", "reviewer"}:
            current_menu_ids = _load_json_int_list(current.menu_ids_json)
            required_menu_ids = [109]
            merged_menu_ids = sorted(set(current_menu_ids).union(required_menu_ids))
            if sorted(current_menu_ids) != merged_menu_ids:
                current.menu_ids_json = _dump_json_int_list(merged_menu_ids)
                created = True
    if created:
        db.session.commit()


def list_menu_items():
    ensure_system_compat_seed()
    rows = SystemMenu.query.order_by(SystemMenu.parent_id.asc(), SystemMenu.order_num.asc(), SystemMenu.id.asc()).all()
    return _serialize_menu_rows(rows)


def menu_tree_for_select():
    tree = _build_tree(list_menu_items())
    return [{"id": item["menuId"], "label": item["menuName"], "children": _menu_children(item.get("children", []))} for item in tree]


def menu_tree():
    return _build_tree(list_menu_items())


def get_menu(menu_id):
    ensure_system_compat_seed()
    row = db.session.get(SystemMenu, int(menu_id))
    return _serialize_menu(row) if row else None


def save_menu(payload):
    ensure_system_compat_seed()
    if payload.get("menuId") in (None, ""):
        row = SystemMenu(id=_next_id(SystemMenu))
        db.session.add(row)
    else:
        row = db.session.get(SystemMenu, int(payload["menuId"]))
        if row is None:
            raise APIError("菜单不存在")
    row.parent_id = int(payload.get("parentId") or 0)
    row.menu_name = str(payload.get("menuName") or "").strip()
    row.icon = str(payload.get("icon") or "").strip()
    row.order_num = int(payload.get("orderNum") or 0)
    row.path = str(payload.get("path") or "").strip()
    row.component = str(payload.get("component") or "").strip()
    row.query_value = str(payload.get("query") or "").strip()
    row.is_frame = str(payload.get("isFrame") or "1")
    row.is_cache = str(payload.get("isCache") or "0")
    row.visible = str(payload.get("visible") or "0")
    row.status = str(payload.get("status") or "0")
    row.menu_type = str(payload.get("menuType") or "M")
    row.perms = str(payload.get("perms") or "").strip()
    if not row.menu_name:
        raise APIError("菜单名称不能为空")
    if row.menu_type != "F" and not row.path:
        raise APIError("路由地址不能为空")
    db.session.flush()
    return _serialize_menu(row)


def delete_menu(menu_id):
    ensure_system_compat_seed()
    target_id = int(menu_id)
    child_exists = SystemMenu.query.filter_by(parent_id=target_id).first() is not None
    if child_exists:
        raise APIError("请先删除子菜单")
    row = db.session.get(SystemMenu, target_id)
    if row is None:
        raise APIError("菜单不存在")
    db.session.delete(row)


def ensure_role_meta(role):
    ensure_system_compat_seed()
    row = SystemRoleMeta.query.filter_by(role_id=role.id).first()
    return _serialize_role_meta(row, role)


def serialize_role_with_meta(role):
    meta = ensure_role_meta(role)
    return {
        "roleId": role.id,
        "roleName": role.role_name,
        "roleKey": role.role_code,
        "roleSort": meta["roleSort"],
        "dataScope": meta["dataScope"],
        "menuCheckStrictly": True,
        "deptCheckStrictly": True,
        "menuIds": list(meta["menuIds"]),
        "deptIds": list(meta["deptIds"]),
        "remark": meta["remark"],
        "status": enabled_status_label(role.status),
        "createTime": role.created_at.isoformat() if role.created_at else None,
    }


def save_role_meta(role_id, payload):
    ensure_system_compat_seed()
    role = db.session.get(SysRole, int(role_id))
    if role is None:
        raise APIError("角色不存在")
    row = SystemRoleMeta.query.filter_by(role_id=role.id).first()
    defaults = _default_role_meta(role)
    if row is None:
        row = SystemRoleMeta(
            role_id=role.id,
            role_sort=defaults["roleSort"],
            data_scope=defaults["dataScope"],
            menu_ids_json=_dump_json_int_list(defaults["menuIds"]),
            dept_ids_json=_dump_json_int_list(defaults["deptIds"]),
            remark=defaults["remark"],
        )
        db.session.add(row)
    if "roleSort" in payload:
        row.role_sort = int(payload.get("roleSort") or defaults["roleSort"])
    if "dataScope" in payload:
        row.data_scope = str(payload.get("dataScope") or defaults["dataScope"])
    if "menuIds" in payload:
        row.menu_ids_json = _dump_json_int_list(payload.get("menuIds") or [])
    if "deptIds" in payload:
        row.dept_ids_json = _dump_json_int_list(payload.get("deptIds") or [])
    if "remark" in payload:
        row.remark = str(payload.get("remark") or "").strip()
    db.session.flush()
    return _serialize_role_meta(row, role)


def delete_role_meta(role_id):
    row = SystemRoleMeta.query.filter_by(role_id=int(role_id)).first()
    if row is not None:
        db.session.delete(row)


def list_user_menu_items(user):
    ensure_system_compat_seed()
    if user is None:
        return []

    rows = SystemMenu.query.filter(SystemMenu.status == "0").order_by(SystemMenu.parent_id.asc(), SystemMenu.order_num.asc(), SystemMenu.id.asc()).all()
    if any(role.role_code == "admin" and int(role.status or 0) == 1 for role in user.roles):
        return _serialize_menu_rows(rows)

    row_map = {int(row.id): row for row in rows}
    menu_ids = set()
    for role in user.roles:
        if int(role.status or 0) != 1:
            continue
        menu_ids.update(ensure_role_meta(role).get("menuIds", []))
    visible_ids = _collect_ancestor_ids(menu_ids, row_map)
    selected_rows = [row_map[item] for item in visible_ids if item in row_map]
    selected_rows.sort(key=_menu_row_sort_key)
    return _serialize_menu_rows(selected_rows)


def user_menu_path_set(user):
    paths = set()
    for item in list_user_menu_items(user):
        if item.get("status") != "0":
            continue
        if item.get("menuType") not in {"M", "C"}:
            continue
        path = str(item.get("path") or "").strip()
        if path:
            paths.add(path)
    return paths


def user_menu_perm_set(user):
    perms = set()
    for item in list_user_menu_items(user):
        current = str(item.get("perms") or "").strip()
        if current:
            perms.add(current)
    return perms


def list_config_items():
    ensure_system_compat_seed()
    rows = SystemConfig.query.order_by(SystemConfig.id.asc()).all()
    return [_serialize_config(item) for item in rows]


def get_config_item(config_id):
    ensure_system_compat_seed()
    row = db.session.get(SystemConfig, int(config_id))
    return _serialize_config(row) if row else None


def get_config_value(config_key):
    ensure_system_compat_seed()
    row = SystemConfig.query.filter_by(config_key=str(config_key)).first()
    return row.config_value if row else ""


def save_config_item(payload):
    ensure_system_compat_seed()
    validate_runtime_config(payload)
    if payload.get("configId") in (None, ""):
        row = SystemConfig(id=_next_id(SystemConfig))
        db.session.add(row)
    else:
        row = db.session.get(SystemConfig, int(payload["configId"]))
        if row is None:
            raise APIError("参数不存在")
    row.config_name = str(payload.get("configName") or "").strip()
    row.config_key = str(payload.get("configKey") or "").strip()
    row.config_value = str(payload.get("configValue") or "").strip()
    row.config_type = str(payload.get("configType") or "N").strip() or "N"
    row.remark = str(payload.get("remark") or "").strip()
    if not row.config_name or not row.config_key:
        raise APIError("参数名称和参数键名不能为空")
    duplicate = SystemConfig.query.filter(SystemConfig.config_key == row.config_key, SystemConfig.id != row.id).first()
    if duplicate:
        raise APIError("参数键名已存在")
    db.session.flush()
    if row.config_key in {STORAGE_ROOT_KEY, BACKUP_DIR_KEY, STORAGE_LAYOUT_KEY}:
        ensure_runtime_directories()
    return _serialize_config(row)


def delete_config_items(config_ids):
    ensure_system_compat_seed()
    ids = {int(item) for item in str(config_ids).split(",") if str(item).strip()}
    builtin_items = SystemConfig.query.filter(SystemConfig.id.in_(ids), SystemConfig.config_type == "Y").all()
    if builtin_items:
        raise APIError("系统内置参数不允许删除")
    if ids:
        SystemConfig.query.filter(SystemConfig.id.in_(ids)).delete(synchronize_session=False)


def list_dict_types():
    ensure_system_compat_seed()
    rows = SystemDictType.query.order_by(SystemDictType.id.asc()).all()
    return [_serialize_dict_type(item) for item in rows]


def get_dict_type(dict_id):
    ensure_system_compat_seed()
    row = db.session.get(SystemDictType, int(dict_id))
    return _serialize_dict_type(row) if row else None


def save_dict_type(payload):
    ensure_system_compat_seed()
    if payload.get("dictId") in (None, ""):
        row = SystemDictType(id=_next_id(SystemDictType))
        db.session.add(row)
    else:
        row = db.session.get(SystemDictType, int(payload["dictId"]))
        if row is None:
            raise APIError("字典类型不存在")
    row.dict_name = str(payload.get("dictName") or "").strip()
    row.dict_type = str(payload.get("dictType") or "").strip()
    row.status = str(payload.get("status") or "0")
    row.remark = str(payload.get("remark") or "").strip()
    if not row.dict_name or not row.dict_type:
        raise APIError("字典名称和字典类型不能为空")
    duplicate = SystemDictType.query.filter(SystemDictType.dict_type == row.dict_type, SystemDictType.id != row.id).first()
    if duplicate:
        raise APIError("字典类型已存在")
    db.session.flush()
    return _serialize_dict_type(row)


def delete_dict_types(dict_ids):
    ensure_system_compat_seed()
    ids = {int(item) for item in str(dict_ids).split(",") if str(item).strip()}
    target_rows = SystemDictType.query.filter(SystemDictType.id.in_(ids)).all()
    target_types = {item.dict_type for item in target_rows}
    if target_types.intersection(BUILTIN_DICT_TYPES):
        raise APIError("系统内置字典类型不允许删除")
    if target_types:
        SystemDictData.query.filter(SystemDictData.dict_type.in_(target_types)).delete(synchronize_session=False)
        SystemDictType.query.filter(SystemDictType.id.in_(ids)).delete(synchronize_session=False)


def list_dict_data_items():
    ensure_system_compat_seed()
    rows = SystemDictData.query.order_by(SystemDictData.id.asc()).all()
    return [_serialize_dict_data(item) for item in rows]


def get_dict_data_item(dict_code):
    ensure_system_compat_seed()
    row = db.session.get(SystemDictData, int(dict_code))
    return _serialize_dict_data(row) if row else None


def save_dict_data_item(payload):
    ensure_system_compat_seed()
    if payload.get("dictCode") in (None, ""):
        row = SystemDictData(id=_next_id(SystemDictData))
        db.session.add(row)
    else:
        row = db.session.get(SystemDictData, int(payload["dictCode"]))
        if row is None:
            raise APIError("字典数据不存在")
    row.dict_type = str(payload.get("dictType") or "").strip()
    row.dict_label = str(payload.get("dictLabel") or "").strip()
    row.dict_value = str(payload.get("dictValue") or "").strip()
    row.dict_sort = int(payload.get("dictSort") or 0)
    row.css_class = str(payload.get("cssClass") or "").strip()
    row.list_class = str(payload.get("listClass") or "default").strip() or "default"
    row.status = str(payload.get("status") or "0")
    row.remark = str(payload.get("remark") or "").strip()
    row.is_default = str(payload.get("isDefault") or row.is_default or "N")
    if not row.dict_type or not row.dict_label or not row.dict_value:
        raise APIError("字典类型、标签和值不能为空")
    duplicate = SystemDictData.query.filter(
        SystemDictData.dict_type == row.dict_type,
        SystemDictData.dict_value == row.dict_value,
        SystemDictData.id != row.id,
    ).first()
    if duplicate:
        raise APIError("同一字典类型下键值已存在")
    db.session.flush()
    return _serialize_dict_data(row)


def delete_dict_data_items(dict_codes):
    ensure_system_compat_seed()
    ids = {int(item) for item in str(dict_codes).split(",") if str(item).strip()}
    protected_rows = SystemDictData.query.filter(SystemDictData.id.in_(ids), SystemDictData.dict_type.in_(BUILTIN_DICT_TYPES)).all()
    if protected_rows:
        raise APIError("系统内置字典数据不允许删除")
    if ids:
        SystemDictData.query.filter(SystemDictData.id.in_(ids)).delete(synchronize_session=False)
