import json
import os
import sys
import time
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib import parse as url_parse

from openpyxl import Workbook


CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

os.environ['DATABASE_URL'] = f"sqlite:///{(CURRENT_DIR / 'smoke_test.db').resolve()}"
os.environ['APP_AUTO_SEED'] = 'true'
os.environ['APP_ENV'] = 'test'
os.environ['APP_FILE_EXPORT_SCHEDULER_AUTO_START'] = 'N'
os.environ['BAIDU_PAN_APP_KEY'] = 'smoke-app-key'
os.environ['BAIDU_PAN_SECRET_KEY'] = 'smoke-secret-key'
os.environ['BAIDU_PAN_SIGN_KEY'] = 'smoke-sign-key'
os.environ['BAIDU_PAN_CALLBACK_URL'] = 'http://localhost:5002/api/integrations/baidu-pan/callback'

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


def auth_header(token):
    return {'Authorization': f'Bearer {token}'}


def build_workbook(headers, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    content = BytesIO()
    workbook.save(content)
    content.seek(0)
    return content


def find_tree_node_id(nodes, label):
    pending = list(nodes or [])
    while pending:
        current = pending.pop(0)
        if current.get('label') == label:
            return current.get('id')
        pending.extend(current.get('children') or [])
    return None


def tree_contains_id(node, target_id):
    if not node:
        return False
    if node.get('id') == target_id:
        return True
    return any(tree_contains_id(child, target_id) for child in node.get('children') or [])


def wait_for_export_task(client, token, task_id, expected_status='completed', timeout=10.0):
    deadline = time.time() + timeout
    last_payload = None
    while time.time() < deadline:
        detail_resp = client.get(f'/api/v1/statistics/export-records/{task_id}', headers=auth_header(token))
        assert detail_resp.status_code == 200, detail_resp.get_json()
        last_payload = detail_resp.get_json()['data']
        if last_payload['status'] == expected_status:
            return last_payload
        if last_payload['status'] == 'failed' and expected_status != 'failed':
            raise AssertionError(last_payload)
        time.sleep(0.2)
    raise AssertionError(last_payload or {'taskId': task_id, 'status': 'timeout'})


def wait_for_file_export_batch(client, token, batch_id, expected_status='completed', timeout=12.0):
    deadline = time.time() + timeout
    expected_statuses = {expected_status} if isinstance(expected_status, str) else set(expected_status)
    last_payload = None
    while time.time() < deadline:
        detail_resp = client.get(f'/api/v1/files/export-batches/{batch_id}', headers=auth_header(token))
        assert detail_resp.status_code == 200, detail_resp.get_json()
        last_payload = detail_resp.get_json()['data']
        if last_payload['status'] in expected_statuses:
            return last_payload
        if last_payload['status'] == 'failed' and 'failed' not in expected_statuses:
            raise AssertionError(last_payload)
        time.sleep(0.2)
    raise AssertionError(last_payload or {'batchId': batch_id, 'status': 'timeout'})


def main():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        from app.seed import seed_initial_data
        from app.models import ContestInfo

        seed_initial_data('Admin123!')
        seeded_contest_id = ContestInfo.query.filter_by(contest_name='校级算法竞赛').first().id

    client = app.test_client()

    admin_login = client.post('/login', json={'username': 'admin', 'password': 'Admin123!'})
    admin_token = admin_login.get_json()['token']

    teacher_login = client.post('/login', json={'username': 'teacher', 'password': 'Demo123!'})
    teacher_token = teacher_login.get_json()['token']

    reviewer_login = client.post('/login', json={'username': 'reviewer', 'password': 'Demo123!'})
    reviewer_token = reviewer_login.get_json()['token']

    student_login = client.post('/login', json={'username': '20260001', 'password': 'Demo123!'})
    student_token = student_login.get_json()['token']
    failed_login = client.post('/login', json={'username': 'admin', 'password': 'WrongPassword!'})
    assert failed_login.status_code == 200, failed_login.get_json()
    assert failed_login.get_json()['code'] == 500, failed_login.get_json()
    teacher_user_id = client.get('/getInfo', headers=auth_header(teacher_token)).get_json()['user']['userId']
    reviewer_user_id = client.get('/getInfo', headers=auth_header(reviewer_token)).get_json()['user']['userId']

    init_password_resp = client.get('/system/config/configKey/sys.user.initPassword', headers=auth_header(admin_token))
    assert init_password_resp.status_code == 200, init_password_resp.get_json()
    assert init_password_resp.get_json()['msg'] == 'Demo123!', init_password_resp.get_json()

    user_option_resp = client.get('/system/user/', headers=auth_header(admin_token))
    assert user_option_resp.status_code == 200, user_option_resp.get_json()
    role_options = user_option_resp.get_json()['roles']
    teacher_role_id = next(item['roleId'] for item in role_options if item['roleKey'] == 'teacher')
    reviewer_role_id = next(item['roleId'] for item in role_options if item['roleKey'] == 'reviewer')

    student_template_resp = client.post('/api/v1/students/import-template', headers=auth_header(admin_token))
    assert student_template_resp.status_code == 200

    student_import_file = build_workbook(
        ['学号', '姓名', '性别', '学院', '专业', '班级', '年级', '导师', '手机', '邮箱', '历史经历', '备注', '状态'],
        [
            ['20260003', '王五', '男', '计算机学院', '数据科学', '数据科学 2201', '2022级', '刘老师', '13800000003', 'wangwu@example.com', '2025 数据分析挑战赛二等奖', '学生导入成功样例', 1],
            ['20269998', '', '女', '计算机学院', '人工智能', '人工智能 2202', '2022级', '刘老师', '13800009998', 'invalid@example.com', '', '姓名缺失，应导入失败', 1],
        ],
    )
    student_import_resp = client.post(
        '/api/v1/students/import',
        headers=auth_header(admin_token),
        data={'overwrite': 'true', 'file': (student_import_file, 'student_import.xlsx')},
        content_type='multipart/form-data',
    )
    assert student_import_resp.status_code == 200, student_import_resp.get_json()
    assert student_import_resp.get_json()['data']['successCount'] == 1, student_import_resp.get_json()
    assert student_import_resp.get_json()['data']['failCount'] == 1, student_import_resp.get_json()

    student_import_records_resp = client.get('/api/v1/students/import-records', headers=auth_header(admin_token))
    assert student_import_records_resp.status_code == 200, student_import_records_resp.get_json()
    first_student_import_task = student_import_records_resp.get_json()['data']['list'][0]
    assert first_student_import_task['sourceFileName'] == 'student_import.xlsx', student_import_records_resp.get_json()
    assert first_student_import_task['successCount'] == 1, student_import_records_resp.get_json()
    assert first_student_import_task['failCount'] == 1, student_import_records_resp.get_json()

    imported_students_resp = client.get('/api/v1/students?pageSize=200', headers=auth_header(admin_token))
    assert imported_students_resp.status_code == 200, imported_students_resp.get_json()
    imported_student_row = next(item for item in imported_students_resp.get_json()['data']['list'] if item['studentNo'] == '20260003')
    imported_student_id = imported_student_row['id']
    assert imported_student_row['loginAccount'] == '20260003', imported_students_resp.get_json()

    imported_student_login = client.post('/login', json={'username': '20260003', 'password': 'Demo123!'})
    assert imported_student_login.status_code == 200, imported_student_login.get_json()
    imported_student_token = imported_student_login.get_json()['token']
    imported_student_info = client.get('/getInfo', headers=auth_header(imported_student_token))
    assert imported_student_info.status_code == 200, imported_student_info.get_json()
    assert imported_student_info.get_json()['user']['studentId'] == imported_student_id, imported_student_info.get_json()

    student_resp = client.post(
        '/api/v1/students',
        headers=auth_header(admin_token),
        json={
            'studentNo': '20260002',
            'name': '李四',
            'gender': '女',
            'college': '计算机学院',
            'major': '人工智能',
            'className': '人工智能 2201',
            'grade': '2022级',
            'advisorName': '陈老师',
            'mobile': '13800000002',
            'email': 'lisi@example.com',
            'historyExperience': '2025 机器人设计大赛校级一等奖',
            'remark': '冒烟测试学生',
        },
    )
    assert student_resp.status_code == 200, student_resp.get_json()
    assert student_resp.get_json()['data']['advisorName'] == '陈老师'
    student_id = student_resp.get_json()['data']['id']
    assert student_resp.get_json()['data']['loginAccount'] == '20260002', student_resp.get_json()

    created_student_login = client.post('/login', json={'username': '20260002', 'password': 'Demo123!'})
    assert created_student_login.status_code == 200, created_student_login.get_json()
    created_student_token = created_student_login.get_json()['token']

    managed_teacher_resp = client.post(
        '/system/user',
        headers=auth_header(admin_token),
        json={
            'userName': 'mentor01',
            'nickName': '指导老师甲',
            'password': 'Teach123!',
            'phonenumber': '13800000055',
            'email': 'mentor01@example.com',
            'roleIds': [teacher_role_id],
            'status': '0',
        },
    )
    assert managed_teacher_resp.status_code == 200, managed_teacher_resp.get_json()

    managed_teacher_list = client.get('/system/user/list?roleCode=teacher', headers=auth_header(admin_token))
    assert managed_teacher_list.status_code == 200, managed_teacher_list.get_json()
    managed_teacher_row = next(item for item in managed_teacher_list.get_json()['rows'] if item['userName'] == 'mentor01')
    managed_teacher_user_id = managed_teacher_row['userId']

    managed_teacher_login = client.post('/login', json={'username': 'mentor01', 'password': 'Teach123!'})
    assert managed_teacher_login.status_code == 200, managed_teacher_login.get_json()

    auth_role_resp = client.put(
        '/system/user/authRole',
        headers=auth_header(admin_token),
        query_string={'userId': managed_teacher_user_id, 'roleIds': f'{teacher_role_id},{reviewer_role_id}'},
    )
    assert auth_role_resp.status_code == 200, auth_role_resp.get_json()

    managed_teacher_updated = client.get(f'/system/user/{managed_teacher_user_id}', headers=auth_header(admin_token))
    assert managed_teacher_updated.status_code == 200, managed_teacher_updated.get_json()
    assert sorted(managed_teacher_updated.get_json()['data']['roleCodes']) == ['reviewer', 'teacher'], managed_teacher_updated.get_json()

    role_list_resp = client.get('/system/role/list?pageSize=50', headers=auth_header(admin_token))
    assert role_list_resp.status_code == 200, role_list_resp.get_json()
    assert any(item['roleKey'] == 'teacher' for item in role_list_resp.get_json()['rows']), role_list_resp.get_json()

    role_create_resp = client.post(
        '/system/role',
        headers=auth_header(admin_token),
        json={'roleName': '观察员', 'roleKey': 'observer', 'roleSort': 9, 'status': '0', 'menuIds': [204], 'remark': '系统管理冒烟测试角色'},
    )
    assert role_create_resp.status_code == 200, role_create_resp.get_json()

    role_list_after_create = client.get('/system/role/list?pageSize=50', headers=auth_header(admin_token))
    assert role_list_after_create.status_code == 200, role_list_after_create.get_json()
    observer_role_row = next(item for item in role_list_after_create.get_json()['rows'] if item['roleKey'] == 'observer')
    observer_role_id = observer_role_row['roleId']

    role_detail_resp = client.get(f'/system/role/{observer_role_id}', headers=auth_header(admin_token))
    assert role_detail_resp.status_code == 200, role_detail_resp.get_json()
    assert role_detail_resp.get_json()['data']['roleName'] == '观察员', role_detail_resp.get_json()

    role_menu_tree_resp = client.get(f'/system/menu/roleMenuTreeselect/{observer_role_id}', headers=auth_header(admin_token))
    assert role_menu_tree_resp.status_code == 200, role_menu_tree_resp.get_json()
    assert 204 in role_menu_tree_resp.get_json()['checkedKeys'], role_menu_tree_resp.get_json()

    dept_tree_resp = client.get(f'/system/role/deptTree/{observer_role_id}', headers=auth_header(admin_token))
    assert dept_tree_resp.status_code == 200, dept_tree_resp.get_json()
    assert dept_tree_resp.get_json()['depts'], dept_tree_resp.get_json()

    role_update_resp = client.put(
        '/system/role',
        headers=auth_header(admin_token),
        json={'roleId': observer_role_id, 'roleName': '观察员角色', 'roleKey': 'observer', 'roleSort': 10, 'status': '0', 'menuIds': [204, 205], 'remark': '已更新'},
    )
    assert role_update_resp.status_code == 200, role_update_resp.get_json()

    role_scope_resp = client.put(
        '/system/role/dataScope',
        headers=auth_header(admin_token),
        json={'roleId': observer_role_id, 'dataScope': '2', 'deptIds': [12]},
    )
    assert role_scope_resp.status_code == 200, role_scope_resp.get_json()

    unallocated_role_users = client.get(
        '/system/role/authUser/unallocatedList',
        headers=auth_header(admin_token),
        query_string={'roleId': observer_role_id, 'pageSize': 50},
    )
    assert unallocated_role_users.status_code == 200, unallocated_role_users.get_json()
    assert any(item['userId'] == managed_teacher_user_id for item in unallocated_role_users.get_json()['rows']), unallocated_role_users.get_json()

    auth_user_select_resp = client.put(
        '/system/role/authUser/selectAll',
        headers=auth_header(admin_token),
        query_string={'roleId': observer_role_id, 'userIds': str(managed_teacher_user_id)},
    )
    assert auth_user_select_resp.status_code == 200, auth_user_select_resp.get_json()

    allocated_role_users = client.get(
        '/system/role/authUser/allocatedList',
        headers=auth_header(admin_token),
        query_string={'roleId': observer_role_id, 'pageSize': 50},
    )
    assert allocated_role_users.status_code == 200, allocated_role_users.get_json()
    assert any(item['userId'] == managed_teacher_user_id for item in allocated_role_users.get_json()['rows']), allocated_role_users.get_json()

    auth_user_cancel_resp = client.put(
        '/system/role/authUser/cancelAll',
        headers=auth_header(admin_token),
        query_string={'roleId': observer_role_id, 'userIds': str(managed_teacher_user_id)},
    )
    assert auth_user_cancel_resp.status_code == 200, auth_user_cancel_resp.get_json()

    role_export_resp = client.post('/system/role/export', headers=auth_header(admin_token))
    assert role_export_resp.status_code == 200

    menu_list_resp = client.get('/system/menu/list', headers=auth_header(admin_token))
    assert menu_list_resp.status_code == 200, menu_list_resp.get_json()
    assert any(item['menuName'] == '账号管理' for item in menu_list_resp.get_json()['data']), menu_list_resp.get_json()
    user_menu_id = next(item['menuId'] for item in menu_list_resp.get_json()['data'] if item['menuName'] == '账号管理')
    role_menu_id = next(item['menuId'] for item in menu_list_resp.get_json()['data'] if item['menuName'] == '角色管理')

    menu_create_resp = client.post(
        '/system/menu',
        headers=auth_header(admin_token),
        json={
            'parentId': 2,
            'menuName': '系统测试菜单',
            'icon': 'edit',
            'orderNum': 99,
            'path': 'system-test-menu',
            'component': 'system/config/index',
            'query': '',
            'isFrame': '1',
            'isCache': '0',
            'visible': '0',
            'status': '0',
            'menuType': 'C',
            'perms': 'system:test:list',
        },
    )
    assert menu_create_resp.status_code == 200, menu_create_resp.get_json()

    scope_role_resp = client.post(
        '/system/role',
        headers=auth_header(admin_token),
        json={'roleName': '教师账号管理员', 'roleKey': 'teacher_scope_manager', 'roleSort': 18, 'status': '0', 'menuIds': [user_menu_id, role_menu_id], 'remark': '仅可查看教师账号'},
    )
    assert scope_role_resp.status_code == 200, scope_role_resp.get_json()

    scope_role_list = client.get('/system/role/list?pageSize=100', headers=auth_header(admin_token))
    assert scope_role_list.status_code == 200, scope_role_list.get_json()
    scope_role_id = next(item['roleId'] for item in scope_role_list.get_json()['rows'] if item['roleKey'] == 'teacher_scope_manager')

    scope_role_scope_resp = client.put(
        '/system/role/dataScope',
        headers=auth_header(admin_token),
        json={'roleId': scope_role_id, 'dataScope': '2', 'deptIds': [12]},
    )
    assert scope_role_scope_resp.status_code == 200, scope_role_scope_resp.get_json()

    scope_manager_resp = client.post(
        '/system/user',
        headers=auth_header(admin_token),
        json={
            'userName': 'teacher_scope_mgr',
            'nickName': '教师数据管理员',
            'password': 'Scope123!',
            'phonenumber': '13800000056',
            'email': 'scope-manager@example.com',
            'roleIds': [scope_role_id],
            'status': '0',
        },
    )
    assert scope_manager_resp.status_code == 200, scope_manager_resp.get_json()

    scope_login = client.post('/login', json={'username': 'teacher_scope_mgr', 'password': 'Scope123!'})
    assert scope_login.status_code == 200, scope_login.get_json()
    scope_token = scope_login.get_json()['token']

    scoped_user_list = client.get('/system/user/list?pageSize=100', headers=auth_header(scope_token))
    assert scoped_user_list.status_code == 200, scoped_user_list.get_json()
    scoped_user_names = {item['userName'] for item in scoped_user_list.get_json()['rows']}
    assert 'teacher' in scoped_user_names, scoped_user_list.get_json()
    assert 'mentor01' in scoped_user_names, scoped_user_list.get_json()
    assert 'admin' not in scoped_user_names, scoped_user_list.get_json()
    assert 'reviewer' not in scoped_user_names, scoped_user_list.get_json()
    assert '20260001' not in scoped_user_names, scoped_user_list.get_json()

    scoped_teacher_detail = client.get(f'/system/user/{teacher_user_id}', headers=auth_header(scope_token))
    assert scoped_teacher_detail.status_code == 200, scoped_teacher_detail.get_json()
    scoped_reviewer_detail = client.get(f'/system/user/{reviewer_user_id}', headers=auth_header(scope_token))
    assert scoped_reviewer_detail.status_code in {400, 403}, scoped_reviewer_detail.get_json()
    assert scoped_reviewer_detail.get_json()['code'] == 403, scoped_reviewer_detail.get_json()

    scoped_role_users = client.get(
        '/system/role/authUser/unallocatedList',
        headers=auth_header(scope_token),
        query_string={'roleId': observer_role_id, 'pageSize': 50},
    )
    assert scoped_role_users.status_code == 200, scoped_role_users.get_json()
    scoped_role_user_names = {item['userName'] for item in scoped_role_users.get_json()['rows']}
    assert 'teacher' in scoped_role_user_names or 'mentor01' in scoped_role_user_names, scoped_role_users.get_json()
    assert 'reviewer' not in scoped_role_user_names, scoped_role_users.get_json()

    menu_list_after_create = client.get('/system/menu/list', headers=auth_header(admin_token))
    assert menu_list_after_create.status_code == 200, menu_list_after_create.get_json()
    system_test_menu = next(item for item in menu_list_after_create.get_json()['data'] if item['menuName'] == '系统测试菜单')
    system_test_menu_id = system_test_menu['menuId']

    menu_detail_resp = client.get(f'/system/menu/{system_test_menu_id}', headers=auth_header(admin_token))
    assert menu_detail_resp.status_code == 200, menu_detail_resp.get_json()

    menu_update_resp = client.put(
        '/system/menu',
        headers=auth_header(admin_token),
        json={**menu_detail_resp.get_json()['data'], 'menuName': '系统测试菜单更新'},
    )
    assert menu_update_resp.status_code == 200, menu_update_resp.get_json()

    menu_delete_resp = client.delete(f'/system/menu/{system_test_menu_id}', headers=auth_header(admin_token))
    assert menu_delete_resp.status_code == 200, menu_delete_resp.get_json()

    config_create_resp = client.post(
        '/system/config',
        headers=auth_header(admin_token),
        json={'configName': '系统测试参数', 'configKey': 'system.test.key', 'configValue': 'v1', 'configType': 'N', 'remark': '参数冒烟测试'},
    )
    assert config_create_resp.status_code == 200, config_create_resp.get_json()

    config_list_resp = client.get('/system/config/list?pageSize=50', headers=auth_header(admin_token))
    assert config_list_resp.status_code == 200, config_list_resp.get_json()
    system_test_config = next(item for item in config_list_resp.get_json()['rows'] if item['configKey'] == 'system.test.key')
    system_test_config_id = system_test_config['configId']

    config_detail_resp = client.get(f'/system/config/{system_test_config_id}', headers=auth_header(admin_token))
    assert config_detail_resp.status_code == 200, config_detail_resp.get_json()

    config_update_resp = client.put(
        '/system/config',
        headers=auth_header(admin_token),
        json={**config_detail_resp.get_json()['data'], 'configValue': 'v2'},
    )
    assert config_update_resp.status_code == 200, config_update_resp.get_json()

    config_key_resp = client.get('/system/config/configKey/system.test.key', headers=auth_header(admin_token))
    assert config_key_resp.status_code == 200, config_key_resp.get_json()
    assert config_key_resp.get_json()['msg'] == 'v2', config_key_resp.get_json()

    config_refresh_resp = client.delete('/system/config/refreshCache', headers=auth_header(admin_token))
    assert config_refresh_resp.status_code == 200, config_refresh_resp.get_json()

    config_export_resp = client.post('/system/config/export', headers=auth_header(admin_token))
    assert config_export_resp.status_code == 200

    config_delete_resp = client.delete(f'/system/config/{system_test_config_id}', headers=auth_header(admin_token))
    assert config_delete_resp.status_code == 200, config_delete_resp.get_json()

    dict_type_create_resp = client.post(
        '/system/dict/type',
        headers=auth_header(admin_token),
        json={'dictName': '系统测试字典', 'dictType': 'system_test_dict', 'status': '0', 'remark': '字典类型冒烟测试'},
    )
    assert dict_type_create_resp.status_code == 200, dict_type_create_resp.get_json()

    dict_type_list_resp = client.get('/system/dict/type/list?pageSize=50', headers=auth_header(admin_token))
    assert dict_type_list_resp.status_code == 200, dict_type_list_resp.get_json()
    system_test_dict = next(item for item in dict_type_list_resp.get_json()['rows'] if item['dictType'] == 'system_test_dict')
    system_test_dict_id = system_test_dict['dictId']

    dict_type_detail_resp = client.get(f'/system/dict/type/{system_test_dict_id}', headers=auth_header(admin_token))
    assert dict_type_detail_resp.status_code == 200, dict_type_detail_resp.get_json()

    dict_type_update_resp = client.put(
        '/system/dict/type',
        headers=auth_header(admin_token),
        json={**dict_type_detail_resp.get_json()['data'], 'dictName': '系统测试字典更新'},
    )
    assert dict_type_update_resp.status_code == 200, dict_type_update_resp.get_json()

    dict_option_resp = client.get('/system/dict/type/optionselect', headers=auth_header(admin_token))
    assert dict_option_resp.status_code == 200, dict_option_resp.get_json()
    assert any(item['dictType'] == 'system_test_dict' for item in dict_option_resp.get_json()['data']), dict_option_resp.get_json()

    dict_data_create_resp = client.post(
        '/system/dict/data',
        headers=auth_header(admin_token),
        json={
            'dictType': 'system_test_dict',
            'dictLabel': '测试标签',
            'dictValue': 'enabled',
            'dictSort': 1,
            'cssClass': '',
            'listClass': 'success',
            'status': '0',
            'remark': '字典数据冒烟测试',
        },
    )
    assert dict_data_create_resp.status_code == 200, dict_data_create_resp.get_json()

    dict_data_list_resp = client.get('/system/dict/data/list?pageSize=50&dictType=system_test_dict', headers=auth_header(admin_token))
    assert dict_data_list_resp.status_code == 200, dict_data_list_resp.get_json()
    system_test_dict_data = next(item for item in dict_data_list_resp.get_json()['rows'] if item['dictValue'] == 'enabled')
    system_test_dict_code = system_test_dict_data['dictCode']

    dict_data_detail_resp = client.get(f'/system/dict/data/{system_test_dict_code}', headers=auth_header(admin_token))
    assert dict_data_detail_resp.status_code == 200, dict_data_detail_resp.get_json()

    dict_data_by_type_resp = client.get('/system/dict/data/type/system_test_dict', headers=auth_header(admin_token))
    assert dict_data_by_type_resp.status_code == 200, dict_data_by_type_resp.get_json()
    assert any(item['dictCode'] == system_test_dict_code for item in dict_data_by_type_resp.get_json()['data']), dict_data_by_type_resp.get_json()

    dict_data_update_resp = client.put(
        '/system/dict/data',
        headers=auth_header(admin_token),
        json={**dict_data_detail_resp.get_json()['data'], 'dictLabel': '测试标签更新'},
    )
    assert dict_data_update_resp.status_code == 200, dict_data_update_resp.get_json()

    dict_type_export_resp = client.post('/system/dict/type/export', headers=auth_header(admin_token))
    assert dict_type_export_resp.status_code == 200
    dict_data_export_resp = client.post('/system/dict/data/export', headers=auth_header(admin_token))
    assert dict_data_export_resp.status_code == 200

    dict_refresh_resp = client.delete('/system/dict/type/refreshCache', headers=auth_header(admin_token))
    assert dict_refresh_resp.status_code == 200, dict_refresh_resp.get_json()

    dict_data_delete_resp = client.delete(f'/system/dict/data/{system_test_dict_code}', headers=auth_header(admin_token))
    assert dict_data_delete_resp.status_code == 200, dict_data_delete_resp.get_json()

    dict_type_delete_resp = client.delete(f'/system/dict/type/{system_test_dict_id}', headers=auth_header(admin_token))
    assert dict_type_delete_resp.status_code == 200, dict_type_delete_resp.get_json()

    role_delete_resp = client.delete(f'/system/role/{observer_role_id}', headers=auth_header(admin_token))
    assert role_delete_resp.status_code == 200, role_delete_resp.get_json()

    teacher_create_student_resp = client.post(
        '/api/v1/students',
        headers=auth_header(teacher_token),
        json={'studentNo': '20269999', 'name': '越权学生', 'college': '计算机学院', 'major': '软件工程', 'className': '软件工程 2201'},
    )
    assert teacher_create_student_resp.status_code == 200, teacher_create_student_resp.get_json()
    assert teacher_create_student_resp.get_json()['code'] == 403, teacher_create_student_resp.get_json()

    teacher_contest_resp = client.post(
        '/api/v1/contests',
        headers=auth_header(teacher_token),
        json={
            'contestName': '教师自建算法竞赛',
            'contestLevel': '校级',
            'organizer': '计算机学院',
            'subjectCategory': '程序设计',
            'status': 'draft',
            'quotaLimit': 30,
        },
    )
    assert teacher_contest_resp.status_code == 200, teacher_contest_resp.get_json()
    teacher_owned_contest_id = teacher_contest_resp.get_json()['data']['id']
    assert teacher_contest_resp.get_json()['data']['managerUserIds'] == [teacher_user_id], teacher_contest_resp.get_json()

    contest_resp = client.post(
        '/api/v1/contests',
        headers=auth_header(admin_token),
        json={
            'contestName': '省级程序设计竞赛',
            'contestLevel': '省级',
            'organizer': '省教育厅',
            'subjectCategory': '程序设计',
            'undertaker': '计算机学院',
            'targetStudents': '本科生',
            'contactName': '李老师',
            'contactMobile': '13800002222',
            'contestYear': 2026,
            'status': 'draft',
            'quotaLimit': 50,
            'managerUserIds': [teacher_user_id],
            'reviewerUserIds': [reviewer_user_id],
        },
    )
    assert contest_resp.status_code == 200, contest_resp.get_json()
    contest_id = contest_resp.get_json()['data']['id']
    assert contest_resp.get_json()['data']['managerUserIds'] == [teacher_user_id], contest_resp.get_json()
    assert contest_resp.get_json()['data']['reviewerUserIds'] == [reviewer_user_id], contest_resp.get_json()

    rule_attachment_resp = client.post(
        f'/api/v1/contests/{contest_id}/rule-attachment',
        headers=auth_header(admin_token),
        data={'file': (BytesIO(b'contest-rule-attachment'), 'contest_rules.pdf')},
        content_type='multipart/form-data',
    )
    assert rule_attachment_resp.status_code == 200, rule_attachment_resp.get_json()
    assert rule_attachment_resp.get_json()['data']['ruleAttachmentId'], rule_attachment_resp.get_json()
    assert rule_attachment_resp.get_json()['data']['ruleAttachmentName'] == 'contest_rules.pdf', rule_attachment_resp.get_json()

    contest_detail_resp = client.get(f'/api/v1/contests/{contest_id}', headers=auth_header(admin_token))
    assert contest_detail_resp.status_code == 200, contest_detail_resp.get_json()
    assert contest_detail_resp.get_json()['data']['ruleAttachmentName'] == 'contest_rules.pdf', contest_detail_resp.get_json()

    rule_attachment_download = client.post(f'/api/v1/contests/{contest_id}/rule-attachment/download', headers=auth_header(teacher_token))
    assert rule_attachment_download.status_code == 200
    assert 'attachment' in rule_attachment_download.headers.get('Content-Disposition', '').lower()
    rule_attachment_preview = client.post(f'/api/v1/contests/{contest_id}/rule-attachment/preview', headers=auth_header(teacher_token))
    assert rule_attachment_preview.status_code == 200
    assert rule_attachment_preview.content_type.startswith('application/pdf')

    rule_attachment_remove_resp = client.post(f'/api/v1/contests/{contest_id}/rule-attachment/remove', headers=auth_header(admin_token))
    assert rule_attachment_remove_resp.status_code == 200, rule_attachment_remove_resp.get_json()
    assert rule_attachment_remove_resp.get_json()['data']['ruleAttachmentId'] is None, rule_attachment_remove_resp.get_json()

    hidden_contest_resp = client.post(
        '/api/v1/contests',
        headers=auth_header(admin_token),
        json={
            'contestName': '国家级数学建模竞赛',
            'contestLevel': '国家级',
            'organizer': '教育部',
            'subjectCategory': '数学建模',
            'status': 'draft',
            'quotaLimit': 80,
        },
    )
    assert hidden_contest_resp.status_code == 200, hidden_contest_resp.get_json()
    hidden_contest_id = hidden_contest_resp.get_json()['data']['id']

    publish_resp = client.post(f'/api/v1/contests/{contest_id}/publish', headers=auth_header(admin_token))
    assert publish_resp.status_code == 200, publish_resp.get_json()
    hidden_publish_resp = client.post(f'/api/v1/contests/{hidden_contest_id}/publish', headers=auth_header(admin_token))
    assert hidden_publish_resp.status_code == 200, hidden_publish_resp.get_json()

    teacher_contests = client.get('/api/v1/contests', headers=auth_header(teacher_token))
    assert teacher_contests.status_code == 200, teacher_contests.get_json()
    teacher_contest_names = [item['contestName'] for item in teacher_contests.get_json()['data']['list']]
    assert '教师自建算法竞赛' in teacher_contest_names, teacher_contests.get_json()
    assert '省级程序设计竞赛' in teacher_contest_names, teacher_contests.get_json()
    assert '国家级数学建模竞赛' not in teacher_contest_names, teacher_contests.get_json()

    reviewer_contests = client.get('/api/v1/contests', headers=auth_header(reviewer_token))
    assert reviewer_contests.status_code == 200, reviewer_contests.get_json()
    reviewer_contest_names = [item['contestName'] for item in reviewer_contests.get_json()['data']['list']]
    assert '省级程序设计竞赛' in reviewer_contest_names, reviewer_contests.get_json()
    assert '国家级数学建模竞赛' not in reviewer_contest_names, reviewer_contests.get_json()

    teacher_hidden_contest = client.get(f'/api/v1/contests/{hidden_contest_id}', headers=auth_header(teacher_token))
    assert teacher_hidden_contest.status_code == 200, teacher_hidden_contest.get_json()
    assert teacher_hidden_contest.get_json()['code'] == 403, teacher_hidden_contest.get_json()

    registration_template_resp = client.post('/api/v1/registrations/import-template', headers=auth_header(teacher_token))
    assert registration_template_resp.status_code == 200

    registration_file = build_workbook(
        ['赛事名称', '学号', '项目名称', '报名方向', '队伍名称', '指导老师', '指导老师电话', '报名来源', '备注', '报名状态', '审核状态', '报名时间'],
        [['省级程序设计竞赛', '20260002', '智能车项目', '算法设计', '今夜必胜队', '陈老师', '13800002222', 'import', '批量导入冒烟', 'submitted', 'pending', '2026-03-11 09:00:00']],
    )
    registration_import_resp = client.post(
        '/api/v1/registrations/import',
        headers=auth_header(teacher_token),
        data={'overwrite': 'true', 'file': (registration_file, 'registration_import.xlsx')},
        content_type='multipart/form-data',
    )
    assert registration_import_resp.status_code == 200, registration_import_resp.get_json()
    assert registration_import_resp.get_json()['data']['successCount'] == 1

    hidden_registration_file = build_workbook(
        ['赛事名称', '学号', '项目名称', '报名方向', '队伍名称', '指导老师', '指导老师电话', '报名来源', '备注', '报名状态', '审核状态', '报名时间'],
        [['国家级数学建模竞赛', '20260002', '建模项目', '建模设计', '数学之星', '陈老师', '13800002222', 'import', '应被拦截', 'submitted', 'pending', '2026-03-11 09:00:00']],
    )
    hidden_registration_import_resp = client.post(
        '/api/v1/registrations/import',
        headers=auth_header(teacher_token),
        data={'overwrite': 'true', 'file': (hidden_registration_file, 'registration_hidden.xlsx')},
        content_type='multipart/form-data',
    )
    assert hidden_registration_import_resp.status_code == 200, hidden_registration_import_resp.get_json()
    assert hidden_registration_import_resp.get_json()['data']['failCount'] == 1, hidden_registration_import_resp.get_json()

    registration_list_resp = client.get('/api/v1/registrations', headers=auth_header(admin_token))
    assert registration_list_resp.status_code == 200, registration_list_resp.get_json()
    registration_row = next(item for item in registration_list_resp.get_json()['data']['list'] if item['contestName'] == '省级程序设计竞赛')
    assert registration_row['projectName'] == '智能车项目'
    registration_id = registration_row['id']

    teacher_registration_list = client.get('/api/v1/registrations', headers=auth_header(teacher_token))
    assert teacher_registration_list.status_code == 200, teacher_registration_list.get_json()
    assert all(item['contestName'] != '国家级数学建模竞赛' for item in teacher_registration_list.get_json()['data']['list']), teacher_registration_list.get_json()

    registration_update_resp = client.put(
        f'/api/v1/registrations/{registration_id}',
        headers=auth_header(teacher_token),
        json={'projectName': '智能车项目-复赛', 'instructorName': '周老师', 'sourceType': 'online', 'remark': '更新细粒度字段'},
    )
    assert registration_update_resp.status_code == 200, registration_update_resp.get_json()
    assert registration_update_resp.get_json()['data']['instructorName'] == '周老师'

    student_registration_detail = client.get(f'/api/v1/registrations/{registration_id}', headers=auth_header(student_token))
    assert student_registration_detail.status_code == 200, student_registration_detail.get_json()
    assert student_registration_detail.get_json()['code'] == 403, student_registration_detail.get_json()

    dirty_review_registration_resp = client.post(
        '/api/v1/registrations',
        headers=auth_header(teacher_token),
        json={'contestId': seeded_contest_id, 'studentId': imported_student_id, 'projectName': '历史脏数据-待审核', 'direction': '补件治理', 'sourceType': 'import'},
    )
    assert dirty_review_registration_resp.status_code == 200, dirty_review_registration_resp.get_json()
    dirty_review_registration_id = dirty_review_registration_resp.get_json()['data']['id']

    dirty_repair_registration_resp = client.post(
        '/api/v1/registrations',
        headers=auth_header(teacher_token),
        json={'contestId': seeded_contest_id, 'studentId': student_id, 'projectName': '历史脏数据-补传', 'direction': '补件治理', 'sourceType': 'import'},
    )
    assert dirty_repair_registration_resp.status_code == 200, dirty_repair_registration_resp.get_json()
    dirty_repair_registration_id = dirty_repair_registration_resp.get_json()['data']['id']

    with app.app_context():
        from app.models import ContestRegistration, RegistrationMaterial

        dirty_review_registration = db.session.get(ContestRegistration, dirty_review_registration_id)
        dirty_review_registration.registration_status = 'reviewing'
        dirty_review_registration.review_status = 'reviewing'
        dirty_review_registration.final_status = 'reviewing'
        db.session.add(
            RegistrationMaterial(
                registration_id=dirty_review_registration_id,
                material_type='方案书',
                file_name='legacy_review_only.pdf',
                submit_status='submitted',
                review_status='pending',
            )
        )

        dirty_repair_registration = db.session.get(ContestRegistration, dirty_repair_registration_id)
        dirty_repair_registration.registration_status = 'approved'
        dirty_repair_registration.review_status = 'approved'
        dirty_repair_registration.final_status = 'approved'
        db.session.add(
            RegistrationMaterial(
                registration_id=dirty_repair_registration_id,
                material_type='成绩单',
                file_name='legacy_approved_only.pdf',
                submit_status='submitted',
                review_status='approved',
            )
        )
        db.session.commit()

    dirty_review_detail_resp = client.get(f'/api/v1/registrations/{dirty_review_registration_id}', headers=auth_header(teacher_token))
    assert dirty_review_detail_resp.status_code == 200, dirty_review_detail_resp.get_json()
    assert dirty_review_detail_resp.get_json()['data']['dataQualityStatus'] == 'dirty', dirty_review_detail_resp.get_json()

    dirty_review_approve_resp = client.post(
        f'/api/v1/registrations/{dirty_review_registration_id}/review',
        headers=auth_header(reviewer_token),
        json={'action': 'approve', 'comment': '不应允许直接通过'},
    )
    assert dirty_review_approve_resp.status_code == 400, dirty_review_approve_resp.get_json()
    assert '不能直接审核通过' in dirty_review_approve_resp.get_json()['msg'], dirty_review_approve_resp.get_json()

    dirty_repair_detail_resp = client.get(f'/api/v1/registrations/{dirty_repair_registration_id}', headers=auth_header(teacher_token))
    assert dirty_repair_detail_resp.status_code == 200, dirty_repair_detail_resp.get_json()
    assert dirty_repair_detail_resp.get_json()['data']['permissions']['canSubmitMaterials'] is True, dirty_repair_detail_resp.get_json()
    assert dirty_repair_detail_resp.get_json()['data']['dataQualityStatus'] == 'dirty', dirty_repair_detail_resp.get_json()

    dirty_repair_upload_resp = client.post(
        f'/api/v1/registrations/{dirty_repair_registration_id}/materials',
        headers=auth_header(teacher_token),
        data={
            'materialType': '成绩单',
            'remark': '补传历史原件',
            'files': (BytesIO(b'legacy-repair-material'), 'legacy_repaired.pdf'),
        },
        content_type='multipart/form-data',
    )
    assert dirty_repair_upload_resp.status_code == 200, dirty_repair_upload_resp.get_json()
    assert dirty_repair_upload_resp.get_json()['data']['finalStatus'] == 'reviewing', dirty_repair_upload_resp.get_json()
    assert dirty_repair_upload_resp.get_json()['data']['dataQualityStatus'] == 'clean', dirty_repair_upload_resp.get_json()

    dirty_repair_approve_resp = client.post(
        f'/api/v1/registrations/{dirty_repair_registration_id}/review',
        headers=auth_header(reviewer_token),
        json={'action': 'approve', 'comment': '历史脏数据已补传原件'},
    )
    assert dirty_repair_approve_resp.status_code == 200, dirty_repair_approve_resp.get_json()

    pending_registration_resp = client.post(
        '/api/v1/registrations',
        headers=auth_header(teacher_token),
        json={'contestId': contest_id, 'studentId': imported_student_id, 'projectName': '待催交项目', 'direction': '工程设计', 'sourceType': 'online'},
    )
    assert pending_registration_resp.status_code == 200, pending_registration_resp.get_json()

    material_file = BytesIO(b'registration-material')
    material_resp = client.post(
        f'/api/v1/registrations/{registration_id}/materials',
        headers=auth_header(teacher_token),
        data={
            'materialType': '成绩单',
            'remark': '上传真实报名材料',
            'files': (material_file, 'transcript.pdf'),
        },
        content_type='multipart/form-data',
    )
    assert material_resp.status_code == 200, material_resp.get_json()
    uploaded_material = material_resp.get_json()['data']['materials'][-1]
    assert uploaded_material['attachmentId'], material_resp.get_json()
    review_todo_title = '待审核：省级程序设计竞赛 / 李四'
    reviewer_auto_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(reviewer_token))
    assert reviewer_auto_messages.status_code == 200, reviewer_auto_messages.get_json()
    assert any(item['title'] == review_todo_title for item in reviewer_auto_messages.get_json()['data']['list']), reviewer_auto_messages.get_json()
    unrelated_student_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(student_token))
    assert unrelated_student_messages.status_code == 200, unrelated_student_messages.get_json()
    assert all(item['title'] != review_todo_title for item in unrelated_student_messages.get_json()['data']['list']), unrelated_student_messages.get_json()

    material_download_resp = client.post(
        f"/api/v1/registrations/materials/{uploaded_material['id']}/download",
        headers=auth_header(teacher_token),
    )
    assert material_download_resp.status_code == 200
    assert 'attachment' in material_download_resp.headers.get('Content-Disposition', '').lower()
    material_preview_resp = client.post(
        f"/api/v1/registrations/materials/{uploaded_material['id']}/preview",
        headers=auth_header(teacher_token),
    )
    assert material_preview_resp.status_code == 200
    assert material_preview_resp.content_type.startswith('application/pdf')

    review_resp = client.post(
        f'/api/v1/registrations/{registration_id}/review',
        headers=auth_header(reviewer_token),
        json={'action': 'approve', 'comment': '材料齐全，审核通过'},
    )
    assert review_resp.status_code == 200, review_resp.get_json()
    approval_message_title = '审核通过：省级程序设计竞赛 / 李四'
    created_student_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(created_student_token))
    assert created_student_messages.status_code == 200, created_student_messages.get_json()
    assert any(item['title'] == approval_message_title for item in created_student_messages.get_json()['data']['list']), created_student_messages.get_json()
    unrelated_student_messages_after_approve = client.get('/api/v1/messages?scene=inbox', headers=auth_header(student_token))
    assert unrelated_student_messages_after_approve.status_code == 200, unrelated_student_messages_after_approve.get_json()
    assert all(item['title'] != approval_message_title for item in unrelated_student_messages_after_approve.get_json()['data']['list']), unrelated_student_messages_after_approve.get_json()

    student_withdraw_registration_resp = client.post(
        '/api/v1/registrations',
        headers=auth_header(created_student_token),
        json={'contestId': hidden_contest_id, 'studentId': student_id, 'projectName': '学生自助退赛样例', 'direction': '自助资格处理', 'sourceType': 'online'},
    )
    assert student_withdraw_registration_resp.status_code == 200, student_withdraw_registration_resp.get_json()
    student_withdraw_registration_id = student_withdraw_registration_resp.get_json()['data']['id']
    student_withdraw_resp = client.post(
        f'/api/v1/registrations/{student_withdraw_registration_id}/withdraw',
        headers=auth_header(created_student_token),
        json={'reason': '学生自行退赛'},
    )
    assert student_withdraw_resp.status_code == 200, student_withdraw_resp.get_json()
    assert student_withdraw_resp.get_json()['data']['finalStatus'] == 'withdrawn', student_withdraw_resp.get_json()

    for scene in ['registration_list', 'review_results', 'pending_materials']:
        export_resp = client.post('/api/v1/registrations/export', headers=auth_header(admin_token), data={'scene': scene})
        assert export_resp.status_code == 200
        assert export_resp.content_type.startswith('application/vnd.openxmlformats-officedocument')

    result_template_resp = client.post('/api/v1/results/import-template', headers=auth_header(admin_token))
    assert result_template_resp.status_code == 200

    result_file = build_workbook(
        ['赛事名称', '学号', '获奖等级', '结果状态', '成绩分数', '名次', '证书编号', '归档备注', '确认时间'],
        [['省级程序设计竞赛', '20260002', '一等奖', 'awarded', 95.5, 1, 'CERT-TEST-001', '决赛成绩', '2026-03-11 10:00:00']],
    )
    result_import_resp = client.post(
        '/api/v1/results/import',
        headers=auth_header(admin_token),
        data={'overwrite': 'true', 'file': (result_file, 'result_import.xlsx')},
        content_type='multipart/form-data',
    )
    assert result_import_resp.status_code == 200, result_import_resp.get_json()
    assert result_import_resp.get_json()['data']['successCount'] == 1

    results_resp = client.get('/api/v1/results', headers=auth_header(admin_token))
    assert results_resp.status_code == 200, results_resp.get_json()
    result_row = next(item for item in results_resp.get_json()['data']['list'] if item['contestName'] == '省级程序设计竞赛' and item['studentId'] == student_id)
    assert result_row['certificateNo'] == 'CERT-TEST-001'
    result_id = result_row['id']

    teacher_results = client.get('/api/v1/results', headers=auth_header(teacher_token))
    assert teacher_results.status_code == 200, teacher_results.get_json()
    assert any(item['id'] == result_id for item in teacher_results.get_json()['data']['list']), teacher_results.get_json()

    student_result_list = client.get('/api/v1/results', headers=auth_header(student_token))
    assert student_result_list.status_code == 200, student_result_list.get_json()
    assert student_result_list.get_json()['data']['total'] == 0, student_result_list.get_json()

    result_update_resp = client.put(
        f'/api/v1/results/{result_id}',
        headers=auth_header(teacher_token),
        json={'score': 96.5, 'ranking': 1, 'certificateNo': 'CERT-TEST-002', 'archiveRemark': '更新赛后字段'},
    )
    assert result_update_resp.status_code == 200, result_update_resp.get_json()
    assert result_update_resp.get_json()['data']['certificateNo'] == 'CERT-TEST-002', result_update_resp.get_json()

    certificate_file = BytesIO(b'certificate-bytes')
    certificate_resp = client.post(
        '/api/v1/certificates/upload',
        headers=auth_header(teacher_token),
        data={'resultId': str(result_id), 'file': (certificate_file, 'certificate.pdf')},
        content_type='multipart/form-data',
    )
    assert certificate_resp.status_code == 200, certificate_resp.get_json()

    certificate_download_resp = client.post('/api/v1/certificates/download', headers=auth_header(teacher_token), data={'resultId': result_id})
    assert certificate_download_resp.status_code == 200
    certificate_preview_resp = client.post('/api/v1/certificates/preview', headers=auth_header(admin_token), data={'resultId': result_id})
    assert certificate_preview_resp.status_code == 200
    assert certificate_preview_resp.content_type.startswith('application/pdf')

    student_certificate_download = client.post('/api/v1/certificates/download', headers=auth_header(student_token), data={'resultId': result_id})
    assert student_certificate_download.status_code == 200, student_certificate_download.get_json()
    assert student_certificate_download.get_json()['code'] == 403, student_certificate_download.get_json()

    statistics_resp = client.get('/api/v1/statistics/awards', headers=auth_header(admin_token))
    assert statistics_resp.status_code == 200, statistics_resp.get_json()
    assert statistics_resp.get_json()['data']['summary']['awardedCount'] >= 1
    teacher_statistics_resp = client.get('/api/v1/statistics/awards', headers=auth_header(teacher_token))
    assert teacher_statistics_resp.status_code == 200, teacher_statistics_resp.get_json()
    assert teacher_statistics_resp.get_json()['data']['summary']['awardedCount'] >= 1

    statistics_export_resp = client.post('/api/v1/statistics/awards/export', headers=auth_header(admin_token))
    assert statistics_export_resp.status_code == 200
    teacher_statistics_export_resp = client.post('/api/v1/statistics/awards/export', headers=auth_header(teacher_token))
    assert teacher_statistics_export_resp.status_code == 200

    archive_export_resp = client.post('/api/v1/results/archive-export', headers=auth_header(admin_token))
    assert archive_export_resp.status_code == 200
    teacher_archive_export_resp = client.post('/api/v1/results/archive-export', headers=auth_header(teacher_token))
    assert teacher_archive_export_resp.status_code == 200

    statistics_export_records_resp = client.get('/api/v1/statistics/export-records?pageSize=20', headers=auth_header(admin_token))
    assert statistics_export_records_resp.status_code == 200, statistics_export_records_resp.get_json()
    statistics_export_rows = statistics_export_records_resp.get_json()['data']['list']
    assert {'archive_export', 'award_statistics_export'}.issubset({item['taskType'] for item in statistics_export_rows}), statistics_export_records_resp.get_json()

    teacher_export_records_resp = client.get('/api/v1/statistics/export-records?pageSize=20', headers=auth_header(teacher_token))
    assert teacher_export_records_resp.status_code == 200, teacher_export_records_resp.get_json()
    teacher_export_rows = teacher_export_records_resp.get_json()['data']['list']
    assert teacher_export_rows, teacher_export_records_resp.get_json()
    assert {'archive_export', 'award_statistics_export'}.issubset({item['taskType'] for item in teacher_export_rows}), teacher_export_records_resp.get_json()
    assert all(item['createdBy'] == teacher_user_id for item in teacher_export_rows), teacher_export_records_resp.get_json()
    teacher_award_export_row = next(item for item in teacher_export_rows if item['taskType'] == 'award_statistics_export')

    teacher_export_download_resp = client.post(
        f"/api/v1/statistics/export-records/{teacher_award_export_row['id']}/download",
        headers=auth_header(teacher_token),
    )
    assert teacher_export_download_resp.status_code == 200
    assert teacher_export_download_resp.content_type.startswith('application/vnd.openxmlformats-officedocument'), teacher_export_download_resp.headers

    teacher_message_create = client.post(
        '/api/v1/messages',
        headers=auth_header(teacher_token),
        json={'title': '教师报名结果通知', 'summary': '教师已完成赛后处理', 'content': '请查看当前赛事的赛后结果与证书归档状态。', 'messageType': 'message', 'contestId': contest_id, 'targetScope': 'role', 'targetRoles': ['student'], 'priority': 'high'},
    )
    assert teacher_message_create.status_code == 200, teacher_message_create.get_json()
    teacher_message_id = teacher_message_create.get_json()['data']['id']
    teacher_message_send_resp = client.post(f'/api/v1/messages/{teacher_message_id}/send', headers=auth_header(teacher_token))
    assert teacher_message_send_resp.status_code == 200, teacher_message_send_resp.get_json()
    teacher_created_student_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(created_student_token))
    assert teacher_created_student_messages.status_code == 200, teacher_created_student_messages.get_json()
    assert any(item['title'] == '教师报名结果通知' for item in teacher_created_student_messages.get_json()['data']['list']), teacher_created_student_messages.get_json()

    message_resp = client.post(
        '/api/v1/messages',
        headers=auth_header(admin_token),
        json={'title': '报名结果通知', 'summary': '审核结果提醒', 'content': '请同步处理当前赛事报名结果。', 'messageType': 'message', 'contestId': contest_id, 'targetScope': 'role', 'targetRoles': ['teacher', 'reviewer'], 'priority': 'high'},
    )
    assert message_resp.status_code == 200, message_resp.get_json()
    assert message_resp.get_json()['data']['targetRoles'] == ['teacher', 'reviewer']
    message_id = message_resp.get_json()['data']['id']
    send_resp = client.post(f'/api/v1/messages/{message_id}/send', headers=auth_header(admin_token))
    assert send_resp.status_code == 200, send_resp.get_json()

    hidden_message_resp = client.post(
        '/api/v1/messages',
        headers=auth_header(admin_token),
        json={'title': '未授权赛事教师通知', 'summary': '仅未授权赛事', 'content': '内部通知', 'messageType': 'notice', 'contestId': hidden_contest_id, 'targetScope': 'role', 'targetRoles': ['teacher', 'reviewer'], 'priority': 'normal'},
    )
    hidden_message_id = hidden_message_resp.get_json()['data']['id']
    hidden_send_resp = client.post(f'/api/v1/messages/{hidden_message_id}/send', headers=auth_header(admin_token))
    assert hidden_send_resp.status_code == 200, hidden_send_resp.get_json()
    assert hidden_send_resp.get_json()['data']['sendStatus'] == 'failed', hidden_send_resp.get_json()

    failure_records_resp = client.get('/api/v1/messages/failures', headers=auth_header(admin_token))
    assert failure_records_resp.status_code == 200, failure_records_resp.get_json()
    hidden_failures = [item for item in failure_records_resp.get_json()['data']['list'] if item['messageId'] == hidden_message_id]
    assert len(hidden_failures) >= 2, failure_records_resp.get_json()
    teacher_failure_records = client.get('/api/v1/messages/failures', headers=auth_header(teacher_token))
    assert teacher_failure_records.status_code == 200, teacher_failure_records.get_json()
    assert all(item['messageId'] != hidden_message_id for item in teacher_failure_records.get_json()['data']['list']), teacher_failure_records.get_json()

    todo_rule_resp = client.post(
        '/api/v1/messages/todo-rules',
        headers=auth_header(teacher_token),
        json={
            'ruleName': '报名原件催交',
            'scene': 'pending_materials',
            'contestId': contest_id,
            'targetRoles': ['teacher'],
            'priority': 'high',
            'enabledStatus': True,
        },
    )
    assert todo_rule_resp.status_code == 200, todo_rule_resp.get_json()
    todo_rule_id = todo_rule_resp.get_json()['data']['id']

    todo_rule_list_resp = client.get('/api/v1/messages/todo-rules', headers=auth_header(teacher_token))
    assert todo_rule_list_resp.status_code == 200, todo_rule_list_resp.get_json()
    assert any(item['id'] == todo_rule_id for item in todo_rule_list_resp.get_json()['data']['list']), todo_rule_list_resp.get_json()

    apply_rule_resp = client.post(f'/api/v1/messages/todo-rules/{todo_rule_id}/apply', headers=auth_header(teacher_token))
    assert apply_rule_resp.status_code == 200, apply_rule_resp.get_json()
    assert apply_rule_resp.get_json()['data']['generatedCount'] >= 1, apply_rule_resp.get_json()

    teacher_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(teacher_token))
    assert teacher_messages.status_code == 200, teacher_messages.get_json()
    teacher_message_titles = [item['title'] for item in teacher_messages.get_json()['data']['list']]
    assert '报名结果通知' in teacher_message_titles, teacher_messages.get_json()
    assert '未授权赛事教师通知' not in teacher_message_titles, teacher_messages.get_json()
    assert any(item['messageType'] == 'todo' for item in teacher_messages.get_json()['data']['list']), teacher_messages.get_json()

    reviewer_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(reviewer_token))
    assert reviewer_messages.status_code == 200, reviewer_messages.get_json()
    reviewer_message_titles = [item['title'] for item in reviewer_messages.get_json()['data']['list']]
    assert '报名结果通知' in reviewer_message_titles, reviewer_messages.get_json()

    student_messages = client.get('/api/v1/messages?scene=inbox', headers=auth_header(student_token))
    assert student_messages.status_code == 200, student_messages.get_json()
    assert all(item['id'] != message_id for item in student_messages.get_json()['data']['list']), student_messages.get_json()

    read_resp = client.post(f'/api/v1/messages/{message_id}/read', headers=auth_header(teacher_token))
    assert read_resp.status_code == 200, read_resp.get_json()

    math_student_resp = client.post(
        '/api/v1/students',
        headers=auth_header(admin_token),
        json={
            'studentNo': '20260004',
            'name': '赵六',
            'gender': '男',
            'college': '数学学院',
            'major': '数学与应用数学',
            'className': '数学 2201',
            'grade': '2022级',
            'advisorName': '王老师',
            'mobile': '13800000004',
            'email': 'zhaoliu@example.com',
            'historyExperience': '无',
            'remark': '学院范围测试学生',
        },
    )
    assert math_student_resp.status_code == 200, math_student_resp.get_json()
    math_student_id = math_student_resp.get_json()['data']['id']

    math_registration_resp = client.post(
        '/api/v1/registrations',
        headers=auth_header(admin_token),
        json={
            'contestId': contest_id,
            'studentId': math_student_id,
            'projectName': '数学建模冲刺项目',
            'direction': '数学建模',
            'sourceType': 'online',
            'remark': '学院范围越权校验',
        },
    )
    assert math_registration_resp.status_code == 200, math_registration_resp.get_json()
    math_registration_id = math_registration_resp.get_json()['data']['id']

    math_result_resp = client.post(
        '/api/v1/results',
        headers=auth_header(admin_token),
        json={
            'contestId': contest_id,
            'studentId': math_student_id,
            'awardLevel': '二等奖',
            'resultStatus': 'awarded',
            'score': 88.0,
            'ranking': 2,
            'certificateNo': 'CERT-MATH-001',
            'archiveRemark': '学院范围越权校验',
        },
    )
    assert math_result_resp.status_code == 200, math_result_resp.get_json()
    math_result_id = math_result_resp.get_json()['data']['id']

    college_scope_tree_resp = client.get(f'/system/role/deptTree/{teacher_role_id}', headers=auth_header(admin_token))
    assert college_scope_tree_resp.status_code == 200, college_scope_tree_resp.get_json()
    computer_college_node_id = find_tree_node_id(college_scope_tree_resp.get_json()['depts'], '计算机学院')
    math_college_node_id = find_tree_node_id(college_scope_tree_resp.get_json()['depts'], '数学学院')
    assert computer_college_node_id, college_scope_tree_resp.get_json()
    assert math_college_node_id, college_scope_tree_resp.get_json()

    teacher_college_scope_resp = client.put(
        '/system/role/dataScope',
        headers=auth_header(admin_token),
        json={'roleId': teacher_role_id, 'dataScope': '2', 'deptIds': [computer_college_node_id]},
    )
    assert teacher_college_scope_resp.status_code == 200, teacher_college_scope_resp.get_json()

    reviewer_college_scope_resp = client.put(
        '/system/role/dataScope',
        headers=auth_header(admin_token),
        json={'roleId': reviewer_role_id, 'dataScope': '2', 'deptIds': [computer_college_node_id]},
    )
    assert reviewer_college_scope_resp.status_code == 200, reviewer_college_scope_resp.get_json()

    teacher_scoped_students = client.get('/api/v1/students?pageSize=200', headers=auth_header(teacher_token))
    assert teacher_scoped_students.status_code == 200, teacher_scoped_students.get_json()
    teacher_scoped_student_nos = {item['studentNo'] for item in teacher_scoped_students.get_json()['data']['list']}
    assert '20260002' in teacher_scoped_student_nos, teacher_scoped_students.get_json()
    assert '20260004' not in teacher_scoped_student_nos, teacher_scoped_students.get_json()

    teacher_hidden_student_detail = client.get(f'/api/v1/students/{math_student_id}', headers=auth_header(teacher_token))
    assert teacher_hidden_student_detail.status_code == 200, teacher_hidden_student_detail.get_json()
    assert teacher_hidden_student_detail.get_json()['code'] == 403, teacher_hidden_student_detail.get_json()

    teacher_scoped_registrations = client.get('/api/v1/registrations?pageSize=200', headers=auth_header(teacher_token))
    assert teacher_scoped_registrations.status_code == 200, teacher_scoped_registrations.get_json()
    teacher_registration_ids = {item['id'] for item in teacher_scoped_registrations.get_json()['data']['list']}
    assert registration_id in teacher_registration_ids, teacher_scoped_registrations.get_json()
    assert math_registration_id not in teacher_registration_ids, teacher_scoped_registrations.get_json()

    teacher_hidden_registration_detail = client.get(f'/api/v1/registrations/{math_registration_id}', headers=auth_header(teacher_token))
    assert teacher_hidden_registration_detail.status_code == 200, teacher_hidden_registration_detail.get_json()
    assert teacher_hidden_registration_detail.get_json()['code'] == 403, teacher_hidden_registration_detail.get_json()

    teacher_scoped_results = client.get('/api/v1/results?pageSize=200', headers=auth_header(teacher_token))
    assert teacher_scoped_results.status_code == 200, teacher_scoped_results.get_json()
    teacher_result_ids = {item['id'] for item in teacher_scoped_results.get_json()['data']['list']}
    assert result_id in teacher_result_ids, teacher_scoped_results.get_json()
    assert math_result_id not in teacher_result_ids, teacher_scoped_results.get_json()

    teacher_hidden_result_detail = client.get(f'/api/v1/results/{math_result_id}', headers=auth_header(teacher_token))
    assert teacher_hidden_result_detail.status_code == 200, teacher_hidden_result_detail.get_json()
    assert teacher_hidden_result_detail.get_json()['code'] == 403, teacher_hidden_result_detail.get_json()

    teacher_scoped_statistics = client.get(f'/api/v1/statistics/awards?contestId={contest_id}', headers=auth_header(teacher_token))
    assert teacher_scoped_statistics.status_code == 200, teacher_scoped_statistics.get_json()
    teacher_college_stats = teacher_scoped_statistics.get_json()['data']['collegeStats']
    assert {item['college'] for item in teacher_college_stats} == {'计算机学院'}, teacher_scoped_statistics.get_json()
    assert teacher_scoped_statistics.get_json()['data']['summary']['resultCount'] == 1, teacher_scoped_statistics.get_json()

    teacher_async_award_task_resp = client.post(
        '/api/v1/statistics/export-records',
        headers=auth_header(teacher_token),
        json={'taskType': 'award_statistics_export', 'contestId': contest_id},
    )
    assert teacher_async_award_task_resp.status_code == 200, teacher_async_award_task_resp.get_json()
    teacher_async_award_task = teacher_async_award_task_resp.get_json()['data']
    assert teacher_async_award_task['taskType'] == 'award_statistics_export', teacher_async_award_task_resp.get_json()
    assert teacher_async_award_task['status'] in {'pending', 'processing', 'completed'}, teacher_async_award_task_resp.get_json()

    completed_teacher_award_task = wait_for_export_task(client, teacher_token, teacher_async_award_task['id'])
    assert completed_teacher_award_task['status'] == 'completed', completed_teacher_award_task
    assert completed_teacher_award_task['progress'] == 100, completed_teacher_award_task
    assert completed_teacher_award_task['contestId'] == contest_id, completed_teacher_award_task
    assert completed_teacher_award_task['fileName'].endswith('.xlsx'), completed_teacher_award_task

    teacher_async_award_download_resp = client.post(
        f"/api/v1/statistics/export-records/{teacher_async_award_task['id']}/download",
        headers=auth_header(teacher_token),
    )
    assert teacher_async_award_download_resp.status_code == 200
    assert teacher_async_award_download_resp.content_type.startswith('application/vnd.openxmlformats-officedocument'), teacher_async_award_download_resp.headers

    teacher_async_archive_task_resp = client.post(
        '/api/v1/statistics/export-records',
        headers=auth_header(teacher_token),
        json={'taskType': 'archive_export', 'contestId': contest_id},
    )
    assert teacher_async_archive_task_resp.status_code == 200, teacher_async_archive_task_resp.get_json()
    teacher_async_archive_task = teacher_async_archive_task_resp.get_json()['data']
    assert teacher_async_archive_task['taskType'] == 'archive_export', teacher_async_archive_task_resp.get_json()

    completed_teacher_archive_task = wait_for_export_task(client, teacher_token, teacher_async_archive_task['id'])
    assert completed_teacher_archive_task['status'] == 'completed', completed_teacher_archive_task
    assert completed_teacher_archive_task['progress'] == 100, completed_teacher_archive_task
    assert completed_teacher_archive_task['fileName'].endswith('.xlsx'), completed_teacher_archive_task

    teacher_async_archive_download_resp = client.post(
        f"/api/v1/statistics/export-records/{teacher_async_archive_task['id']}/download",
        headers=auth_header(teacher_token),
    )
    assert teacher_async_archive_download_resp.status_code == 200
    assert teacher_async_archive_download_resp.content_type.startswith('application/vnd.openxmlformats-officedocument'), teacher_async_archive_download_resp.headers

    with app.app_context():
        from app.models import ExportTask

        failed_retry_task = ExportTask(
            task_type='award_statistics_export',
            task_name='失败重试测试任务',
            status='failed',
            progress=0,
            current_step='导出失败',
            error_message='模拟失败',
            request_payload_json=json.dumps({'contestId': contest_id}, ensure_ascii=False),
            retry_count=0,
            created_by=teacher_user_id,
        )
        db.session.add(failed_retry_task)
        db.session.commit()
        failed_retry_task_id = failed_retry_task.id

    failed_retry_detail_resp = client.get(
        f'/api/v1/statistics/export-records/{failed_retry_task_id}',
        headers=auth_header(teacher_token),
    )
    assert failed_retry_detail_resp.status_code == 200, failed_retry_detail_resp.get_json()
    assert failed_retry_detail_resp.get_json()['data']['status'] == 'failed', failed_retry_detail_resp.get_json()
    assert failed_retry_detail_resp.get_json()['data']['canRetry'] is True, failed_retry_detail_resp.get_json()

    retry_export_task_resp = client.post(
        f'/api/v1/statistics/export-records/{failed_retry_task_id}/retry',
        headers=auth_header(teacher_token),
    )
    assert retry_export_task_resp.status_code == 200, retry_export_task_resp.get_json()
    assert retry_export_task_resp.get_json()['data']['retryCount'] == 1, retry_export_task_resp.get_json()
    assert retry_export_task_resp.get_json()['data']['status'] in {'pending', 'processing', 'completed'}, retry_export_task_resp.get_json()

    retried_export_task = wait_for_export_task(client, teacher_token, failed_retry_task_id)
    assert retried_export_task['status'] == 'completed', retried_export_task
    assert retried_export_task['retryCount'] == 1, retried_export_task
    assert retried_export_task['errorMessage'] == '', retried_export_task
    assert retried_export_task['fileName'].endswith('.xlsx'), retried_export_task

    teacher_async_export_records_resp = client.get('/api/v1/statistics/export-records?pageSize=20', headers=auth_header(teacher_token))
    assert teacher_async_export_records_resp.status_code == 200, teacher_async_export_records_resp.get_json()
    teacher_async_export_ids = {item['id'] for item in teacher_async_export_records_resp.get_json()['data']['list']}
    assert {
        teacher_async_award_task['id'],
        teacher_async_archive_task['id'],
        failed_retry_task_id,
    }.issubset(teacher_async_export_ids), teacher_async_export_records_resp.get_json()

    admin_file_categories_resp = client.get('/api/v1/files/categories', headers=auth_header(admin_token))
    assert admin_file_categories_resp.status_code == 200, admin_file_categories_resp.get_json()
    admin_file_category_tree = admin_file_categories_resp.get_json()['data']['tree']
    assert admin_file_categories_resp.get_json()['data']['summary']['totalFiles'] >= 3, admin_file_categories_resp.get_json()
    assert tree_contains_id(admin_file_category_tree, 'group:platform_attachment'), admin_file_categories_resp.get_json()
    assert tree_contains_id(admin_file_category_tree, 'group:task_output'), admin_file_categories_resp.get_json()

    teacher_files_resp = client.get('/api/v1/files?pageSize=200', headers=auth_header(teacher_token))
    assert teacher_files_resp.status_code == 200, teacher_files_resp.get_json()
    teacher_file_rows = teacher_files_resp.get_json()['data']['list']
    teacher_certificate_file = next(item for item in teacher_file_rows if item['categoryCode'] == 'certificate' and item['fileName'] == 'certificate.pdf')
    assert teacher_files_resp.get_json()['data']['summary']['totalFiles'] >= 2, teacher_files_resp.get_json()

    teacher_file_download_resp = client.post(
        '/api/v1/files/download',
        headers=auth_header(teacher_token),
        data={'assetType': teacher_certificate_file['assetType'], 'assetId': teacher_certificate_file['assetId']},
    )
    assert teacher_file_download_resp.status_code == 200
    assert 'attachment' in teacher_file_download_resp.headers.get('Content-Disposition', '').lower()
    teacher_file_preview_resp = client.post(
        '/api/v1/files/preview',
        headers=auth_header(teacher_token),
        data={'assetType': teacher_certificate_file['assetType'], 'assetId': teacher_certificate_file['assetId']},
    )
    assert teacher_file_preview_resp.status_code == 200
    assert teacher_file_preview_resp.content_type.startswith('application/pdf')

    reviewer_files_resp = client.get('/api/v1/files?pageSize=200', headers=auth_header(reviewer_token))
    assert reviewer_files_resp.status_code == 200, reviewer_files_resp.get_json()
    reviewer_file_rows = reviewer_files_resp.get_json()['data']['list']
    assert reviewer_file_rows, reviewer_files_resp.get_json()
    assert all(item['categoryCode'] != 'backup_package' for item in reviewer_file_rows), reviewer_files_resp.get_json()
    reviewer_material_file = next(item for item in reviewer_file_rows if item['categoryCode'] == 'registration_material')

    reviewer_file_preview_resp = client.post(
        '/api/v1/files/preview',
        headers=auth_header(reviewer_token),
        data={'assetType': reviewer_material_file['assetType'], 'assetId': reviewer_material_file['assetId']},
    )
    assert reviewer_file_preview_resp.status_code == 200
    assert reviewer_file_preview_resp.content_type.startswith('application/pdf')

    student_file_list_resp = client.get('/api/v1/files?pageSize=20', headers=auth_header(student_token))
    assert student_file_list_resp.status_code == 200, student_file_list_resp.get_json()
    assert student_file_list_resp.get_json()['code'] == 403, student_file_list_resp.get_json()

    reviewer_scoped_registrations = client.get('/api/v1/registrations?pageSize=200', headers=auth_header(reviewer_token))
    assert reviewer_scoped_registrations.status_code == 200, reviewer_scoped_registrations.get_json()
    reviewer_registration_ids = {item['id'] for item in reviewer_scoped_registrations.get_json()['data']['list']}
    assert registration_id in reviewer_registration_ids, reviewer_scoped_registrations.get_json()
    assert math_registration_id not in reviewer_registration_ids, reviewer_scoped_registrations.get_json()

    reviewer_hidden_registration_detail = client.get(f'/api/v1/registrations/{math_registration_id}', headers=auth_header(reviewer_token))
    assert reviewer_hidden_registration_detail.status_code == 200, reviewer_hidden_registration_detail.get_json()
    assert reviewer_hidden_registration_detail.get_json()['code'] == 403, reviewer_hidden_registration_detail.get_json()

    file_export_metadata_resp = client.get('/api/v1/files/export-metadata', headers=auth_header(teacher_token))
    assert file_export_metadata_resp.status_code == 200, file_export_metadata_resp.get_json()
    assert any(item['value'] == 'registration_material' for item in file_export_metadata_resp.get_json()['data']['categoryOptions']), file_export_metadata_resp.get_json()
    assert any(item['id'] == contest_id for item in file_export_metadata_resp.get_json()['data']['contestOptions']), file_export_metadata_resp.get_json()

    local_channel_resp = client.post(
        '/api/v1/files/delivery-channels',
        headers=auth_header(admin_token),
        json={
            'channelName': '本地归档目录',
            'channelType': 'local_folder',
            'status': 'enabled',
            'config': {'rootPath': 'smoke_local_delivery', 'folderTemplate': '{policyName}/{date}'},
            'remark': '冒烟测试本地目录渠道',
        },
    )
    assert local_channel_resp.status_code == 200, local_channel_resp.get_json()
    local_channel_id = local_channel_resp.get_json()['data']['id']

    baidu_mock_channel_resp = client.post(
        '/api/v1/files/delivery-channels',
        headers=auth_header(admin_token),
        json={
            'channelName': '百度网盘-Mock',
            'channelType': 'baidu_pan',
            'status': 'enabled',
            'config': {
                'rootPath': '/competition/archive',
                'folderTemplate': '{policyName}/{date}',
                'mockMode': True,
                'mockRoot': 'smoke_baidu_pan',
                'conflictMode': 'overwrite',
            },
            'remark': '冒烟测试百度网盘 mock 渠道',
        },
    )
    assert baidu_mock_channel_resp.status_code == 200, baidu_mock_channel_resp.get_json()
    baidu_mock_channel_id = baidu_mock_channel_resp.get_json()['data']['id']

    baidu_oauth_channel_resp = client.post(
        '/api/v1/files/delivery-channels',
        headers=auth_header(admin_token),
        json={
            'channelName': '百度网盘-OAuth',
            'channelType': 'baidu_pan',
            'status': 'enabled',
            'config': {
                'rootPath': '/competition/oauth',
                'folderTemplate': '{policyName}/{date}',
                'mockMode': False,
                'conflictMode': 'overwrite',
            },
            'remark': '冒烟测试百度网盘 OAuth 渠道',
        },
    )
    assert baidu_oauth_channel_resp.status_code == 200, baidu_oauth_channel_resp.get_json()
    baidu_oauth_channel_id = baidu_oauth_channel_resp.get_json()['data']['id']

    authorize_channel_resp = client.post(
        f'/api/v1/files/delivery-channels/{baidu_oauth_channel_id}/oauth-authorize',
        headers=auth_header(admin_token),
    )
    assert authorize_channel_resp.status_code == 200, authorize_channel_resp.get_json()
    authorize_payload = authorize_channel_resp.get_json()['data']
    authorize_query = url_parse.parse_qs(url_parse.urlparse(authorize_payload['authorizeUrl']).query)
    assert authorize_query['response_type'] == ['code'], authorize_payload
    assert authorize_query['scope'] == ['basic,netdisk'], authorize_payload
    assert authorize_query['redirect_uri'] == ['http://localhost:5002/api/integrations/baidu-pan/callback'], authorize_payload
    callback_state = authorize_query['state'][0]

    with patch(
        'app.file_export_service._exchange_baidu_authorization_code',
        return_value={
            'access_token': 'oauth-access-token-smoke',
            'refresh_token': 'oauth-refresh-token-smoke',
            'expires_in': 3600,
            'scope': 'basic,netdisk',
        },
    ):
        callback_resp = client.get('/api/integrations/baidu-pan/callback', query_string={'code': 'smoke-oauth-code', 'state': callback_state})
    assert callback_resp.status_code == 200, callback_resp.get_data(as_text=True)
    assert '百度网盘授权成功' in callback_resp.get_data(as_text=True), callback_resp.get_data(as_text=True)

    baidu_oauth_detail_resp = client.get(f'/api/v1/files/delivery-channels/{baidu_oauth_channel_id}', headers=auth_header(admin_token))
    assert baidu_oauth_detail_resp.status_code == 200, baidu_oauth_detail_resp.get_json()
    baidu_oauth_config = baidu_oauth_detail_resp.get_json()['data']['config']
    assert baidu_oauth_config['authMode'] == 'oauth', baidu_oauth_detail_resp.get_json()
    assert baidu_oauth_config['accessTokenMasked'], baidu_oauth_detail_resp.get_json()
    assert baidu_oauth_config['refreshTokenMasked'], baidu_oauth_detail_resp.get_json()
    assert baidu_oauth_config['callbackUrl'] == 'http://localhost:5002/api/integrations/baidu-pan/callback', baidu_oauth_detail_resp.get_json()

    validate_local_channel = client.post(f'/api/v1/files/delivery-channels/{local_channel_id}/validate', headers=auth_header(admin_token))
    assert validate_local_channel.status_code == 200, validate_local_channel.get_json()
    assert validate_local_channel.get_json()['data']['mode'] == 'local', validate_local_channel.get_json()

    validate_baidu_mock_channel = client.post(f'/api/v1/files/delivery-channels/{baidu_mock_channel_id}/validate', headers=auth_header(admin_token))
    assert validate_baidu_mock_channel.status_code == 200, validate_baidu_mock_channel.get_json()
    assert validate_baidu_mock_channel.get_json()['data']['mode'] == 'mock', validate_baidu_mock_channel.get_json()

    with patch('app.file_export_service._ensure_baidu_folder', return_value={'path': '/competition/oauth'}):
        validate_baidu_oauth_channel = client.post(f'/api/v1/files/delivery-channels/{baidu_oauth_channel_id}/validate', headers=auth_header(admin_token))
    assert validate_baidu_oauth_channel.status_code == 200, validate_baidu_oauth_channel.get_json()
    assert validate_baidu_oauth_channel.get_json()['data']['mode'] == 'oauth', validate_baidu_oauth_channel.get_json()

    teacher_file_export_metadata = client.get('/api/v1/files/export-metadata', headers=auth_header(teacher_token))
    assert teacher_file_export_metadata.status_code == 200, teacher_file_export_metadata.get_json()
    teacher_channel_option_ids = {item['id'] for item in teacher_file_export_metadata.get_json()['data']['channelOptions']}
    assert {local_channel_id, baidu_mock_channel_id}.issubset(teacher_channel_option_ids), teacher_file_export_metadata.get_json()

    policy_create_resp = client.post(
        '/api/v1/files/export-policies',
        headers=auth_header(teacher_token),
        json={
            'policyName': '每日报名证书归档',
            'status': 'enabled',
            'scheduleType': 'daily',
            'scheduleTime': '01:30',
            'incrementMode': 'full',
            'scope': {
                'categoryCodes': ['registration_material', 'certificate'],
                'contestIds': [contest_id],
                'collegeNames': ['计算机学院'],
                'keyword': '',
            },
            'folderTemplate': '{categoryName}/{contestName}/{college}/{date}',
            'fileNameTemplate': '{policyName}_{date}_{batchNo}.zip',
            'includeManifest': True,
            'deliveryChannelIds': [local_channel_id, baidu_mock_channel_id],
            'remark': '冒烟测试导出规则',
        },
    )
    assert policy_create_resp.status_code == 200, policy_create_resp.get_json()
    file_export_policy_id = policy_create_resp.get_json()['data']['id']
    assert policy_create_resp.get_json()['data']['nextRunAt'], policy_create_resp.get_json()

    teacher_policy_list_resp = client.get('/api/v1/files/export-policies?pageSize=20', headers=auth_header(teacher_token))
    assert teacher_policy_list_resp.status_code == 200, teacher_policy_list_resp.get_json()
    assert any(item['id'] == file_export_policy_id for item in teacher_policy_list_resp.get_json()['data']['list']), teacher_policy_list_resp.get_json()

    run_policy_resp = client.post(f'/api/v1/files/export-policies/{file_export_policy_id}/run', headers=auth_header(teacher_token))
    assert run_policy_resp.status_code == 200, run_policy_resp.get_json()
    successful_batch = wait_for_file_export_batch(client, teacher_token, run_policy_resp.get_json()['data']['id'])
    assert successful_batch['status'] == 'completed', successful_batch
    assert successful_batch['sourceCount'] >= 2, successful_batch
    assert successful_batch['deliverySummary']['completed'] == 2, successful_batch

    successful_batch_detail_resp = client.get(f"/api/v1/files/export-batches/{successful_batch['id']}", headers=auth_header(teacher_token))
    assert successful_batch_detail_resp.status_code == 200, successful_batch_detail_resp.get_json()
    successful_batch_detail = successful_batch_detail_resp.get_json()['data']
    assert len(successful_batch_detail['manifest']['entries']) == successful_batch['sourceCount'], successful_batch_detail_resp.get_json()
    local_delivery = next(item for item in successful_batch_detail['deliveries'] if item['channelType'] == 'local_folder')
    mock_delivery = next(item for item in successful_batch_detail['deliveries'] if item['channelType'] == 'baidu_pan')
    assert Path(local_delivery['targetPath']).exists(), successful_batch_detail_resp.get_json()
    assert Path(mock_delivery['responseSnapshot']['mockFilePath']).exists(), successful_batch_detail_resp.get_json()

    successful_batch_download = client.post(f"/api/v1/files/export-batches/{successful_batch['id']}/download", headers=auth_header(teacher_token))
    assert successful_batch_download.status_code == 200
    assert 'zip' in successful_batch_download.content_type.lower(), successful_batch_download.content_type

    delivery_blocker = CURRENT_DIR / 'delivery_blocker.txt'
    delivery_blocker.write_text('block channel root', encoding='utf-8')

    failing_channel_resp = client.post(
        '/api/v1/files/delivery-channels',
        headers=auth_header(admin_token),
        json={
            'channelName': '故障目录渠道',
            'channelType': 'local_folder',
            'status': 'enabled',
            'config': {'rootPath': str(delivery_blocker), 'folderTemplate': '{policyName}/{date}'},
            'remark': '指向文件路径，故意让批次投递失败',
        },
    )
    assert failing_channel_resp.status_code == 200, failing_channel_resp.get_json()
    failing_channel_id = failing_channel_resp.get_json()['data']['id']

    failing_policy_resp = client.post(
        '/api/v1/files/export-policies',
        headers=auth_header(teacher_token),
        json={
            'policyName': '失败重试导出规则',
            'status': 'enabled',
            'scheduleType': 'manual',
            'scheduleTime': '',
            'incrementMode': 'full',
            'scope': {
                'categoryCodes': ['registration_material'],
                'contestIds': [contest_id],
                'collegeNames': ['计算机学院'],
                'keyword': '',
            },
            'folderTemplate': '{contestName}/{date}',
            'fileNameTemplate': '{policyName}_{batchNo}.zip',
            'includeManifest': True,
            'deliveryChannelIds': [failing_channel_id],
            'remark': '用于验证失败补偿与重试',
        },
    )
    assert failing_policy_resp.status_code == 200, failing_policy_resp.get_json()
    failing_policy_id = failing_policy_resp.get_json()['data']['id']

    failing_batch_resp = client.post(f'/api/v1/files/export-policies/{failing_policy_id}/run', headers=auth_header(teacher_token))
    assert failing_batch_resp.status_code == 200, failing_batch_resp.get_json()
    failing_batch = wait_for_file_export_batch(client, teacher_token, failing_batch_resp.get_json()['data']['id'], expected_status={'partial_success', 'failed'})
    assert failing_batch['canRetry'] is True, failing_batch

    failing_batch_detail_resp = client.get(f"/api/v1/files/export-batches/{failing_batch['id']}", headers=auth_header(teacher_token))
    assert failing_batch_detail_resp.status_code == 200, failing_batch_detail_resp.get_json()
    assert any(item['status'] == 'failed' for item in failing_batch_detail_resp.get_json()['data']['deliveries']), failing_batch_detail_resp.get_json()

    repair_channel_resp = client.put(
        f'/api/v1/files/delivery-channels/{failing_channel_id}',
        headers=auth_header(admin_token),
        json={
            'channelName': '故障目录渠道',
            'channelType': 'local_folder',
            'status': 'enabled',
            'config': {'rootPath': 'smoke_repaired_delivery', 'folderTemplate': '{policyName}/{date}'},
            'remark': '修复后的目录渠道',
        },
    )
    assert repair_channel_resp.status_code == 200, repair_channel_resp.get_json()

    retry_batch_resp = client.post(f"/api/v1/files/export-batches/{failing_batch['id']}/retry", headers=auth_header(teacher_token))
    assert retry_batch_resp.status_code == 200, retry_batch_resp.get_json()
    repaired_batch = wait_for_file_export_batch(client, teacher_token, failing_batch['id'])
    assert repaired_batch['status'] == 'completed', repaired_batch

    with app.app_context():
        from app.models import FileExportPolicy
        from app.time_utils import now_beijing

        due_policy = db.session.get(FileExportPolicy, file_export_policy_id)
        due_policy.next_run_at = now_beijing() - timedelta(minutes=1)
        db.session.commit()

    due_scan_resp = client.post('/api/v1/files/export-policies/run-due', headers=auth_header(teacher_token))
    assert due_scan_resp.status_code == 200, due_scan_resp.get_json()
    assert due_scan_resp.get_json()['data']['count'] == 1, due_scan_resp.get_json()
    scheduled_batch = wait_for_file_export_batch(client, teacher_token, due_scan_resp.get_json()['data']['batchIds'][0])
    assert scheduled_batch['triggerType'] == 'schedule', scheduled_batch

    operlog_resp = client.get('/monitor/operlog/list?pageSize=200', headers=auth_header(admin_token))
    assert operlog_resp.status_code == 200, operlog_resp.get_json()
    assert operlog_resp.get_json()['total'] > 0, operlog_resp.get_json()
    assert any(item['title'] == '角色管理' for item in operlog_resp.get_json()['rows']), operlog_resp.get_json()

    operlog_export_resp = client.post('/monitor/operlog/export', headers=auth_header(admin_token))
    assert operlog_export_resp.status_code == 200

    logininfor_resp = client.get('/monitor/logininfor/list?pageSize=200', headers=auth_header(admin_token))
    assert logininfor_resp.status_code == 200, logininfor_resp.get_json()
    assert logininfor_resp.get_json()['total'] > 0, logininfor_resp.get_json()
    assert any(item['userName'] == 'admin' and item['status'] == '1' for item in logininfor_resp.get_json()['rows']), logininfor_resp.get_json()

    unlock_resp = client.get('/monitor/logininfor/unlock/admin', headers=auth_header(admin_token))
    assert unlock_resp.status_code == 200, unlock_resp.get_json()

    logininfor_export_resp = client.post('/monitor/logininfor/export', headers=auth_header(admin_token))
    assert logininfor_export_resp.status_code == 200

    persist_menu_resp = client.post(
        '/system/menu',
        headers=auth_header(admin_token),
        json={
            'parentId': 2,
            'menuName': '持久化菜单',
            'icon': 'edit',
            'orderNum': 88,
            'path': 'persist-menu',
            'component': 'system/config/index',
            'query': '',
            'isFrame': '1',
            'isCache': '0',
            'visible': '0',
            'status': '0',
            'menuType': 'C',
            'perms': 'system:persist:list',
        },
    )
    assert persist_menu_resp.status_code == 200, persist_menu_resp.get_json()

    persist_menu_list = client.get('/system/menu/list', headers=auth_header(admin_token))
    assert persist_menu_list.status_code == 200, persist_menu_list.get_json()
    persist_menu_id = next(item['menuId'] for item in persist_menu_list.get_json()['data'] if item['menuName'] == '持久化菜单')

    persist_role_resp = client.post(
        '/system/role',
        headers=auth_header(admin_token),
        json={'roleName': '持久化角色', 'roleKey': 'persistent_role', 'roleSort': 30, 'status': '0', 'menuIds': [204, persist_menu_id], 'remark': '重启后应保留'},
    )
    assert persist_role_resp.status_code == 200, persist_role_resp.get_json()

    persist_role_list = client.get('/system/role/list?pageSize=100', headers=auth_header(admin_token))
    assert persist_role_list.status_code == 200, persist_role_list.get_json()
    persist_role_id = next(item['roleId'] for item in persist_role_list.get_json()['rows'] if item['roleKey'] == 'persistent_role')

    persist_role_scope_resp = client.put(
        '/system/role/dataScope',
        headers=auth_header(admin_token),
        json={'roleId': persist_role_id, 'dataScope': '2', 'deptIds': [12, 13]},
    )
    assert persist_role_scope_resp.status_code == 200, persist_role_scope_resp.get_json()

    persist_config_resp = client.post(
        '/system/config',
        headers=auth_header(admin_token),
        json={'configName': '持久化参数', 'configKey': 'system.persist.key', 'configValue': 'persisted-value', 'configType': 'N', 'remark': '重启后应保留'},
    )
    assert persist_config_resp.status_code == 200, persist_config_resp.get_json()

    persist_dict_type_resp = client.post(
        '/system/dict/type',
        headers=auth_header(admin_token),
        json={'dictName': '持久化字典', 'dictType': 'system_persist_dict', 'status': '0', 'remark': '重启后应保留'},
    )
    assert persist_dict_type_resp.status_code == 200, persist_dict_type_resp.get_json()

    persist_dict_data_resp = client.post(
        '/system/dict/data',
        headers=auth_header(admin_token),
        json={
            'dictType': 'system_persist_dict',
            'dictLabel': '持久化标签',
            'dictValue': 'persisted',
            'dictSort': 1,
            'cssClass': '',
            'listClass': 'success',
            'status': '0',
            'remark': '重启后应保留',
        },
    )
    assert persist_dict_data_resp.status_code == 200, persist_dict_data_resp.get_json()

    with app.app_context():
        from app.models import ExportTask, FileExportBatch
        from app.time_utils import now_beijing

        resumable_export_task = ExportTask(
            task_type='award_statistics_export',
            task_name='重启恢复测试任务',
            status='processing',
            progress=45,
            current_step='汇总导出数据',
            error_message='',
            request_payload_json=json.dumps({'contestId': contest_id}, ensure_ascii=False),
            retry_count=0,
            created_by=teacher_user_id,
            started_at=now_beijing(),
        )
        db.session.add(resumable_export_task)
        db.session.commit()
        resumable_export_task_id = resumable_export_task.id

        resumable_file_export_batch = FileExportBatch(
            policy_id=file_export_policy_id,
            batch_no='FB-RESUME-0001',
            trigger_type='schedule',
            status='processing',
            progress=45,
            current_step='正在整理目录',
            error_message='',
            request_snapshot_json=json.dumps({'policyId': file_export_policy_id}, ensure_ascii=False),
            result_snapshot_json='{}',
            manifest_json='{}',
            created_by=teacher_user_id,
            scheduled_for=now_beijing(),
        )
        db.session.add(resumable_file_export_batch)
        db.session.commit()
        resumable_file_export_batch_id = resumable_file_export_batch.id

    reloaded_app = create_app()
    reloaded_client = reloaded_app.test_client()
    reloaded_login = reloaded_client.post('/login', json={'username': 'admin', 'password': 'Admin123!'})
    assert reloaded_login.status_code == 200, reloaded_login.get_json()
    reloaded_admin_token = reloaded_login.get_json()['token']
    reloaded_teacher_login = reloaded_client.post('/login', json={'username': 'teacher', 'password': 'Demo123!'})
    assert reloaded_teacher_login.status_code == 200, reloaded_teacher_login.get_json()
    reloaded_teacher_token = reloaded_teacher_login.get_json()['token']

    reloaded_menu_detail = reloaded_client.get(f'/system/menu/{persist_menu_id}', headers=auth_header(reloaded_admin_token))
    assert reloaded_menu_detail.status_code == 200, reloaded_menu_detail.get_json()
    assert reloaded_menu_detail.get_json()['data']['menuName'] == '持久化菜单', reloaded_menu_detail.get_json()

    reloaded_role_detail = reloaded_client.get(f'/system/role/{persist_role_id}', headers=auth_header(reloaded_admin_token))
    assert reloaded_role_detail.status_code == 200, reloaded_role_detail.get_json()
    assert sorted(reloaded_role_detail.get_json()['data']['menuIds']) == sorted([204, persist_menu_id]), reloaded_role_detail.get_json()
    assert sorted(reloaded_role_detail.get_json()['data']['deptIds']) == [12, 13], reloaded_role_detail.get_json()

    reloaded_config_key = reloaded_client.get('/system/config/configKey/system.persist.key', headers=auth_header(reloaded_admin_token))
    assert reloaded_config_key.status_code == 200, reloaded_config_key.get_json()
    assert reloaded_config_key.get_json()['msg'] == 'persisted-value', reloaded_config_key.get_json()

    reloaded_dict_data = reloaded_client.get('/system/dict/data/type/system_persist_dict', headers=auth_header(reloaded_admin_token))
    assert reloaded_dict_data.status_code == 200, reloaded_dict_data.get_json()
    assert any(item['dictValue'] == 'persisted' for item in reloaded_dict_data.get_json()['data']), reloaded_dict_data.get_json()

    reloaded_logininfor = reloaded_client.get('/monitor/logininfor/list?pageSize=200', headers=auth_header(reloaded_admin_token))
    assert reloaded_logininfor.status_code == 200, reloaded_logininfor.get_json()
    assert any(item['userName'] == 'admin' and item['status'] == '1' for item in reloaded_logininfor.get_json()['rows']), reloaded_logininfor.get_json()

    reloaded_operlog = reloaded_client.get('/monitor/operlog/list?pageSize=200', headers=auth_header(reloaded_admin_token))
    assert reloaded_operlog.status_code == 200, reloaded_operlog.get_json()
    assert any(item['title'] == '角色管理' for item in reloaded_operlog.get_json()['rows']), reloaded_operlog.get_json()

    resumed_export_task = wait_for_export_task(reloaded_client, reloaded_teacher_token, resumable_export_task_id)
    assert resumed_export_task['status'] == 'completed', resumed_export_task
    assert resumed_export_task['progress'] == 100, resumed_export_task
    assert resumed_export_task['fileName'].endswith('.xlsx'), resumed_export_task

    resumed_file_batch = wait_for_file_export_batch(reloaded_client, reloaded_teacher_token, resumable_file_export_batch_id)
    assert resumed_file_batch['status'] == 'completed', resumed_file_batch
    assert resumed_file_batch['fileName'].endswith('.zip'), resumed_file_batch

    runtime_profile_resp = client.get('/system/config/runtimeProfile', headers=auth_header(admin_token))
    assert runtime_profile_resp.status_code == 200, runtime_profile_resp.get_json()
    assert runtime_profile_resp.get_json()['data']['storage']['driver'] == 'local', runtime_profile_resp.get_json()

    backup_marker_create = client.post(
        '/system/config',
        headers=auth_header(admin_token),
        json={'configName': '备份恢复标记', 'configKey': 'system.backup.marker', 'configValue': 'before-restore', 'configType': 'N', 'remark': '用于验证备份恢复'},
    )
    assert backup_marker_create.status_code == 200, backup_marker_create.get_json()

    backup_create_resp = client.post('/system/config/backup', headers=auth_header(admin_token), json={'includeUploads': True})
    assert backup_create_resp.status_code == 200, backup_create_resp.get_json()
    backup_file_name = backup_create_resp.get_json()['data']['fileName']

    backup_download_resp = client.post('/system/config/backup/download', headers=auth_header(admin_token), data={'backupFile': backup_file_name})
    assert backup_download_resp.status_code == 200
    assert backup_download_resp.headers['Content-Type'] == 'application/zip'

    admin_backup_files_resp = client.get('/api/v1/files?pageSize=200&categoryCode=backup_package', headers=auth_header(admin_token))
    assert admin_backup_files_resp.status_code == 200, admin_backup_files_resp.get_json()
    admin_backup_rows = admin_backup_files_resp.get_json()['data']['list']
    assert any(item['assetType'] == 'backup' and item['fileName'] == backup_file_name for item in admin_backup_rows), admin_backup_files_resp.get_json()

    teacher_backup_files_resp = client.get('/api/v1/files?pageSize=200&categoryCode=backup_package', headers=auth_header(teacher_token))
    assert teacher_backup_files_resp.status_code == 200, teacher_backup_files_resp.get_json()
    assert teacher_backup_files_resp.get_json()['data']['total'] == 0, teacher_backup_files_resp.get_json()

    marker_list_resp = client.get('/system/config/list?pageSize=200&configKey=system.backup.marker', headers=auth_header(admin_token))
    assert marker_list_resp.status_code == 200, marker_list_resp.get_json()
    marker_config_id = next(item['configId'] for item in marker_list_resp.get_json()['rows'] if item['configKey'] == 'system.backup.marker')

    marker_update_resp = client.put(
        '/system/config',
        headers=auth_header(admin_token),
        json={'configId': marker_config_id, 'configName': '备份恢复标记', 'configKey': 'system.backup.marker', 'configValue': 'after-backup', 'configType': 'N', 'remark': '用于验证备份恢复'},
    )
    assert marker_update_resp.status_code == 200, marker_update_resp.get_json()

    with app.app_context():
        from app.platform_ops import upload_root_path

        upload_probe = upload_root_path() / 'post-backup-probe.txt'
        upload_probe.write_text('created after backup', encoding='utf-8')

    restore_backup_resp = client.post(
        '/system/config/backup/restore',
        headers=auth_header(admin_token),
        json={'backupFile': backup_file_name},
    )
    assert restore_backup_resp.status_code == 200, restore_backup_resp.get_json()

    restored_marker_resp = client.get('/system/config/configKey/system.backup.marker', headers=auth_header(admin_token))
    assert restored_marker_resp.status_code == 200, restored_marker_resp.get_json()
    assert restored_marker_resp.get_json()['msg'] == 'before-restore', restored_marker_resp.get_json()

    assert not upload_probe.exists(), str(upload_probe)

    dashboard_resp = client.get('/api/v1/system/dashboard', headers=auth_header(admin_token))
    assert dashboard_resp.status_code == 200, dashboard_resp.get_json()
    data = dashboard_resp.get_json()['data']

    student_dashboard = client.get('/api/v1/system/dashboard', headers=auth_header(student_token))
    assert student_dashboard.status_code == 200, student_dashboard.get_json()
    assert student_dashboard.get_json()['data']['studentCount'] == 1, student_dashboard.get_json()

    print('Smoke test passed')
    print({
        'students': data['studentCount'],
        'contests': data['contestCount'],
        'registrations': data['registrationCount'],
        'pendingReviews': data['pendingReviewCount'],
        'awardedResults': statistics_resp.get_json()['data']['summary']['awardedCount'],
    })


if __name__ == '__main__':
    main()
