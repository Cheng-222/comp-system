from copy import deepcopy
from zlib import crc32

from sqlalchemy import and_, false, or_

from .models import StudentInfo, SysRole, SysUser


ROLE_DEPT_IDS = {
    "admin": 11,
    "teacher": 12,
    "reviewer": 13,
    "student": 14,
}
COLLEGE_SCOPE_PARENT_ID = 100
COLLEGE_SCOPE_ID_OFFSET = 100000

STATIC_DEPT_TREE = [
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

DEPT_DESCENDANTS = {
    1: {11, 12, 13, 14},
    11: set(),
    12: set(),
    13: set(),
    14: set(),
    COLLEGE_SCOPE_PARENT_ID: set(),
}


def _active_roles(user):
    if user is None:
        return []
    return [role for role in getattr(user, "roles", []) if int(role.status or 0) == 1]


def college_node_id(college_name):
    normalized = str(college_name or "").strip()
    if not normalized:
        return None
    return COLLEGE_SCOPE_ID_OFFSET + (crc32(normalized.encode("utf-8")) & 0x7FFFFFFF)


def college_scope_items():
    colleges = [
        item[0]
        for item in StudentInfo.query.with_entities(StudentInfo.college).filter(StudentInfo.college.isnot(None), StudentInfo.college != "").distinct().order_by(StudentInfo.college.asc()).all()
    ]
    return [{"id": college_node_id(item), "label": item} for item in colleges if college_node_id(item) is not None]


def college_scope_tree():
    return {
        "id": COLLEGE_SCOPE_PARENT_ID,
        "label": "学院范围",
        "children": college_scope_items(),
    }


def build_scope_dept_tree():
    tree = deepcopy(STATIC_DEPT_TREE)
    if tree:
        college_branch = college_scope_tree()
        if college_branch["children"]:
            tree[0]["children"].append(college_branch)
    return tree


def expand_dept_ids(values):
    dynamic_college_ids = {item["id"] for item in college_scope_items()}
    result = set()
    for item in values or []:
        try:
            current = int(item)
        except (TypeError, ValueError):
            continue
        result.add(current)
        result.update(DEPT_DESCENDANTS.get(current, set()))
        if current == 1:
            result.add(COLLEGE_SCOPE_PARENT_ID)
            result.update(dynamic_college_ids)
        if current == COLLEGE_SCOPE_PARENT_ID:
            result.update(dynamic_college_ids)
    return result


def college_names_for_dept_ids(dept_ids):
    college_map = {item["id"]: item["label"] for item in college_scope_items()}
    return {college_map[item] for item in expand_dept_ids(dept_ids) if item in college_map}


def user_dept_ids(user):
    dept_ids = set()
    for role in _active_roles(user):
        dept_id = ROLE_DEPT_IDS.get(role.role_code)
        if dept_id:
            dept_ids.add(dept_id)
    return dept_ids


def resolve_user_scope(user):
    if user is None:
        return {"allAccess": False, "deptIds": set(), "allowSelf": False, "roleCodes": set(), "collegeNames": set()}

    active_roles = _active_roles(user)
    if any(role.role_code == "admin" for role in active_roles):
        return {"allAccess": True, "deptIds": set(), "allowSelf": True, "roleCodes": set(), "collegeNames": set()}

    from .system_compat_store import ensure_role_meta

    own_dept_ids = user_dept_ids(user)
    allowed_dept_ids = set()
    allow_self = False
    allowed_role_codes = set()
    allowed_college_names = set()
    for role in active_roles:
        meta = ensure_role_meta(role)
        data_scope = str(meta.get("dataScope") or "1").strip() or "1"
        if data_scope == "1":
            return {"allAccess": True, "deptIds": set(), "allowSelf": True, "roleCodes": set(), "collegeNames": set()}
        if data_scope == "2":
            selected_dept_ids = expand_dept_ids(meta.get("deptIds") or [])
            allowed_dept_ids.update(selected_dept_ids)
            allowed_role_codes.update(role_codes_for_dept_ids(selected_dept_ids))
            allowed_college_names.update(college_names_for_dept_ids(selected_dept_ids))
            continue
        if data_scope == "3":
            allowed_dept_ids.update(own_dept_ids)
            allowed_role_codes.update(role_codes_for_dept_ids(own_dept_ids))
            continue
        if data_scope == "4":
            inherited_dept_ids = expand_dept_ids(own_dept_ids)
            allowed_dept_ids.update(inherited_dept_ids)
            allowed_role_codes.update(role_codes_for_dept_ids(inherited_dept_ids))
            continue
        if data_scope == "5":
            allow_self = True
    return {
        "allAccess": False,
        "deptIds": allowed_dept_ids,
        "allowSelf": allow_self,
        "roleCodes": allowed_role_codes,
        "collegeNames": allowed_college_names,
    }


def role_codes_for_dept_ids(dept_ids):
    dept_id_set = expand_dept_ids(dept_ids)
    role_codes = set()
    for role_code, dept_id in ROLE_DEPT_IDS.items():
        if dept_id in dept_id_set:
            role_codes.add(role_code)
    return role_codes


def apply_user_data_scope(query, current_user):
    scope = resolve_user_scope(current_user)
    if scope["allAccess"]:
        return query

    conditions = []
    role_codes = set(scope.get("roleCodes") or set()) or role_codes_for_dept_ids(scope["deptIds"])
    if role_codes:
        conditions.append(SysUser.roles.any(and_(SysRole.role_code.in_(tuple(sorted(role_codes))), SysRole.status == 1)))
    college_names = set(scope.get("collegeNames") or set())
    if college_names:
        query = query.outerjoin(StudentInfo, SysUser.student_id == StudentInfo.id)
        conditions.append(StudentInfo.college.in_(tuple(sorted(college_names))))
    if scope["allowSelf"] and current_user is not None:
        conditions.append(SysUser.id == int(current_user.id))
    if not conditions:
        return query.filter(false())
    return query.filter(or_(*conditions))


def can_access_user(current_user, target_user):
    if target_user is None:
        return False
    scoped_query = apply_user_data_scope(SysUser.query.filter(SysUser.id == int(target_user.id)), current_user)
    return scoped_query.first() is not None


def role_assignable_by_user(role, current_user):
    if role is None:
        return False
    scope = resolve_user_scope(current_user)
    if scope["allAccess"]:
        return True

    dept_id = ROLE_DEPT_IDS.get(role.role_code)
    if dept_id:
        return dept_id in expand_dept_ids(scope["deptIds"])

    from .system_compat_store import ensure_role_meta

    role_meta = ensure_role_meta(role)
    role_dept_ids = expand_dept_ids(role_meta.get("deptIds") or [])
    if role_dept_ids:
        return bool(role_dept_ids.intersection(expand_dept_ids(scope["deptIds"])))
    return False


def filter_assignable_roles(roles, current_user):
    if current_user is None:
        return list(roles)
    return [role for role in roles if role_assignable_by_user(role, current_user)]


def selected_college_names(user):
    scope = resolve_user_scope(user)
    if scope["allAccess"]:
        return None
    college_names = set(scope.get("collegeNames") or set())
    return college_names or None


def apply_college_scope(query, college_column, current_user):
    colleges = selected_college_names(current_user)
    if colleges is None:
        return query
    return query.filter(college_column.in_(tuple(sorted(colleges))))


def student_in_college_scope(student, current_user):
    colleges = selected_college_names(current_user)
    if colleges is None or student is None:
        return True
    college_name = str(getattr(student, "college", "") or "").strip()
    return bool(college_name) and college_name in colleges
