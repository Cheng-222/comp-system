from .models import SystemMenu


def _load_role_menu_ids(role):
    from .system_compat_store import ensure_role_meta, ensure_system_compat_seed

    ensure_system_compat_seed()
    return ensure_role_meta(role).get("menuIds", [])


def _collect_ancestor_ids(menu_ids, row_map):
    pending = []
    for item in menu_ids or []:
        try:
            current_id = int(item)
        except (TypeError, ValueError):
            continue
        if current_id in row_map:
            pending.append(current_id)
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
    }


def _menu_row_sort_key(row):
    return (row.parent_id, row.order_num, row.id)


def list_user_menu_items(user):
    from .system_compat_store import ensure_system_compat_seed

    ensure_system_compat_seed()
    if user is None:
        return []

    rows = SystemMenu.query.filter(SystemMenu.status == "0").order_by(SystemMenu.parent_id.asc(), SystemMenu.order_num.asc(), SystemMenu.id.asc()).all()
    if any(role.role_code == "admin" and int(role.status or 0) == 1 for role in user.roles):
        return [_serialize_menu(item) for item in rows]

    row_map = {int(row.id): row for row in rows}
    menu_ids = set()
    for role in user.roles:
        if int(role.status or 0) != 1:
            continue
        menu_ids.update(_load_role_menu_ids(role))
    visible_ids = _collect_ancestor_ids(menu_ids, row_map)
    selected_rows = [row_map[item] for item in visible_ids if item in row_map]
    selected_rows.sort(key=_menu_row_sort_key)
    return [_serialize_menu(item) for item in selected_rows]


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
