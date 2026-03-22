from flask import Blueprint, g, jsonify, request

from ..access import (
    is_admin_user,
    is_reviewer_user,
    is_student_user,
    is_teacher_user,
    resolve_bound_student,
)
from ..audit_store import record_login_event
from ..models import SysUser
from ..runtime_menu_store import list_user_menu_items, user_menu_path_set, user_menu_perm_set
from ..security import auth_required, create_token, verify_password


bp = Blueprint('ruoyi_compat', __name__)


PERMISSION_COMPAT_EXPANSIONS = {
    'system:user:list': {'system:user:add', 'system:user:edit', 'system:user:remove', 'system:user:export'},
    'system:role:list': {'system:role:add', 'system:role:edit', 'system:role:remove', 'system:role:export'},
    'system:menu:list': {'system:menu:add', 'system:menu:edit', 'system:menu:remove'},
    'system:dict:list': {'system:dict:add', 'system:dict:edit', 'system:dict:remove', 'system:dict:export'},
    'system:config:list': {'system:config:add', 'system:config:edit', 'system:config:remove', 'system:config:export'},
    'monitor:operlog:list': {'monitor:operlog:query', 'monitor:operlog:remove', 'monitor:operlog:export'},
    'monitor:logininfor:list': {'monitor:logininfor:unlock', 'monitor:logininfor:remove', 'monitor:logininfor:export'},
}


ROUTE_NAME_MAP = {
    'competition': 'Competition',
    'students': 'CompetitionStudents',
    'contests': 'CompetitionContests',
    'registrations': 'CompetitionRegistrations',
    'qualifications': 'CompetitionQualifications',
    'reviews': 'CompetitionReviews',
    'messages': 'CompetitionMessages',
    'results': 'CompetitionResults',
    'statistics': 'CompetitionStatistics',
    'files': 'CompetitionFiles',
    'system': 'System',
    'user': 'SystemUser',
    'role': 'SystemRole',
    'menu': 'SystemMenu',
    'dict': 'SystemDict',
    'config': 'SystemConfig',
    'monitor': 'Monitor',
    'operlog': 'MonitorOperlog',
    'logininfor': 'MonitorLogininfor',
    'runtime': 'MonitorRuntime',
}


def ruoyi_ok(payload=None, msg='操作成功'):
    data = {'code': 200, 'msg': msg}
    if payload:
        data.update(payload)
    return jsonify(data)


def build_menu_tree(menu_items):
    node_map = {}
    roots = []
    for item in menu_items:
        if item.get('status') != '0' or item.get('menuType') not in {'M', 'C'}:
            continue
        current = dict(item)
        current['children'] = []
        node_map[current['menuId']] = current
    for item in node_map.values():
        parent_id = int(item.get('parentId') or 0)
        parent = node_map.get(parent_id)
        if parent is None:
            roots.append(item)
        else:
            parent['children'].append(item)
    for item in node_map.values():
        item['children'].sort(key=lambda row: (row.get('orderNum', 0), row.get('menuId', 0)))
    roots.sort(key=lambda row: (row.get('orderNum', 0), row.get('menuId', 0)))
    return roots


def route_name(item, parents):
    path = str(item.get('path') or '').strip()
    if path in ROUTE_NAME_MAP:
        return ROUTE_NAME_MAP[path]
    segments = list(parents) + [path]
    return ''.join(''.join(part.capitalize() for part in segment.replace('-', '_').split('_') if part) for segment in segments if segment)


def first_leaf_path(route):
    children = route.get('children') or []
    if not children:
        return route.get('path')
    child_path = first_leaf_path(children[0])
    if not child_path:
        return route.get('path')
    if str(child_path).startswith('/'):
        return child_path
    current_path = str(route.get('path') or '').rstrip('/')
    return f"{current_path}/{child_path}".replace('//', '/')


def serialize_route(item, parents=(), root_level=False):
    children = [serialize_route(child, parents + (str(item.get('path') or '').strip(),), False) for child in item.get('children', [])]
    children = [child for child in children if child]
    if item.get('menuType') == 'M' and not children:
        return None

    route = {
        'name': route_name(item, parents),
        'path': f"/{str(item.get('path') or '').strip('/')}" if root_level else str(item.get('path') or '').strip('/'),
        'hidden': str(item.get('visible') or '0') == '1',
        'component': item.get('component'),
        'meta': {'title': item.get('menuName'), 'icon': item.get('icon')},
    }
    if children:
        route['children'] = children
        route['alwaysShow'] = True
        route['redirect'] = first_leaf_path(route)
    return route


def build_routes(user):
    menu_tree = build_menu_tree(list_user_menu_items(user))
    routes = [serialize_route(item, root_level=True) for item in menu_tree]
    return [item for item in routes if item]


def build_permissions(user, bound_student):
    if is_admin_user(user):
        return ['*:*:*']

    permissions = set(user_menu_perm_set(user))
    menu_paths = user_menu_path_set(user)
    permissions.add('competition:view')
    if 'messages' in menu_paths:
        permissions.add('competition:message:inbox')
    if 'results' in menu_paths:
        permissions.add('competition:result:view')
    if 'files' in menu_paths:
        permissions.add('competition:file:view')
    if bound_student and 'registrations' in menu_paths:
        permissions.add('competition:registration:self')
    if bound_student and 'results' in menu_paths:
        permissions.add('competition:result:self')
    for permission in list(permissions):
        permissions.update(PERMISSION_COMPAT_EXPANSIONS.get(permission, set()))
    return sorted(permissions)


def build_capabilities(user, bound_student):
    menu_paths = user_menu_path_set(user)
    student_view = bool(bound_student)
    reviewer_view = is_reviewer_user(user)
    return {
        'manageStudents': 'students' in menu_paths,
        'manageContests': 'contests' in menu_paths,
        'createContests': 'contests' in menu_paths,
        'assignContestPermissions': is_admin_user(user),
        'manageRegistrations': 'registrations' in menu_paths and not student_view and not reviewer_view,
        'manageQualifications': 'qualifications' in menu_paths,
        'reviewMaterials': 'reviews' in menu_paths,
        'manageMessages': 'messages' in menu_paths and not student_view and not reviewer_view,
        'viewInbox': True,
        'manageResults': 'results' in menu_paths and not student_view and not reviewer_view,
        'viewResults': 'results' in menu_paths or student_view,
        'exportArchives': 'results' in menu_paths and not student_view and not reviewer_view,
        'viewStatistics': 'statistics' in menu_paths,
        'viewFiles': 'files' in menu_paths,
        'manageFileExports': 'files' in menu_paths and not student_view and not reviewer_view,
        'viewFileExportBatches': 'files' in menu_paths and not student_view and not reviewer_view,
        'manageDeliveryChannels': 'files' in menu_paths and is_admin_user(user),
    }


@bp.post('/login')
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    password = payload.get('password') or ''
    user = SysUser.query.filter_by(username=username).first()
    if not user or user.status != 1 or not verify_password(password, user.password_hash):
        record_login_event(username or 'unknown', 1, '用户名或密码错误', request.remote_addr, request.user_agent.string)
        return jsonify({'code': 500, 'msg': '用户名或密码错误'})
    record_login_event(user.username, 0, '登录成功', request.remote_addr, request.user_agent.string)
    return ruoyi_ok({'token': create_token(user.id)})


@bp.post('/logout')
@auth_required()
def logout():
    return ruoyi_ok(msg='退出成功')


@bp.get('/getInfo')
@auth_required()
def get_info():
    user = g.current_user
    bound_student = resolve_bound_student() if is_student_user(user) else None
    return ruoyi_ok(
        {
            'user': {
                'userId': user.id,
                'userName': user.username,
                'nickName': user.real_name,
                'avatar': '',
                'studentId': user.student_id,
                'studentNo': bound_student.student_no if bound_student else None,
                'studentName': bound_student.name if bound_student else None,
            },
            'roles': user.role_codes or ['ROLE_DEFAULT'],
            'permissions': build_permissions(user, bound_student),
            'capabilities': build_capabilities(user, bound_student),
            'isDefaultModifyPwd': False,
            'isPasswordExpired': False,
        }
    )


@bp.get('/getRouters')
@auth_required()
def get_routers():
    return ruoyi_ok({'data': build_routes(g.current_user)})


@bp.get('/captchaImage')
def captcha_image():
    return ruoyi_ok({'captchaEnabled': False, 'uuid': '', 'img': ''})
