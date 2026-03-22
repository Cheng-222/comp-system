import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
BACKEND_DIR = REPO_ROOT / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('DATABASE_URL', f"sqlite:///{(BACKEND_DIR / 'data' / 'app.db').resolve()}")
os.environ.setdefault('APP_AUTO_SEED', 'true')
os.environ.setdefault('APP_ENV', 'prod')

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    AttachmentInfo,
    ContestInfo,
    ContestPermission,
    ContestRegistration,
    ContestResult,
    MessageReadRecord,
    NoticeMessage,
    RegistrationFlowLog,
    RegistrationMaterial,
    StudentInfo,
    SysUser,
)


NOW = datetime.utcnow()
UPLOAD_DIR = REPO_ROOT / 'uploads'


def get_user(*usernames):
    for username in usernames:
        user = SysUser.query.filter_by(username=username).first()
        if user:
            return user
    raise RuntimeError(f'用户不存在: {", ".join(usernames)}')


def upsert_student(student_no, **payload):
    student = StudentInfo.query.filter_by(student_no=student_no).first()
    if not student:
        student = StudentInfo(student_no=student_no)
        db.session.add(student)
    for key, value in payload.items():
        setattr(student, key, value)
    return student


def upsert_contest(contest_name, **payload):
    contest = ContestInfo.query.filter_by(contest_name=contest_name).first()
    if not contest:
        contest = ContestInfo(contest_name=contest_name)
        db.session.add(contest)
    for key, value in payload.items():
        setattr(contest, key, value)
    return contest


def upsert_registration(contest, student, **payload):
    registration = ContestRegistration.query.filter_by(contest_id=contest.id, student_id=student.id).first()
    if not registration:
        registration = ContestRegistration(contest_id=contest.id, student_id=student.id)
        db.session.add(registration)
    for key, value in payload.items():
        setattr(registration, key, value)
    return registration


def ensure_contest_permission(contest, user, scope):
    permission = ContestPermission.query.filter_by(
        contest_id=contest.id,
        user_id=user.id,
        permission_scope=scope,
    ).first()
    if not permission:
        permission = ContestPermission(contest_id=contest.id, user_id=user.id, permission_scope=scope)
        db.session.add(permission)
    return permission


def ensure_material(registration, material_type, file_name, review_status='pending', comment=None, reviewer=None, reviewed_at=None):
    material = RegistrationMaterial.query.filter_by(
        registration_id=registration.id,
        material_type=material_type,
        file_name=file_name,
    ).first()
    if not material:
        material = RegistrationMaterial(registration_id=registration.id, material_type=material_type, file_name=file_name)
        db.session.add(material)
    material.submit_status = 'submitted'
    material.review_status = review_status
    material.review_comment = comment
    material.reviewer_id = reviewer.id if reviewer else None
    material.reviewed_at = reviewed_at
    return material


def ensure_flow(registration, action_type, before_status, after_status, reason, operator, operated_at):
    flow = RegistrationFlowLog.query.filter_by(
        registration_id=registration.id,
        action_type=action_type,
        before_status=before_status,
        after_status=after_status,
        reason=reason,
    ).first()
    if not flow:
        flow = RegistrationFlowLog(
            registration_id=registration.id,
            action_type=action_type,
            before_status=before_status,
            after_status=after_status,
            reason=reason,
            operator_id=operator.id,
            operated_at=operated_at,
        )
        db.session.add(flow)
    else:
        flow.operator_id = operator.id
        flow.operated_at = operated_at
    return flow


def upsert_message(title, **payload):
    message = NoticeMessage.query.filter_by(title=title).first()
    if not message:
        message = NoticeMessage(title=title, created_by=payload['created_by'])
        db.session.add(message)
    for key, value in payload.items():
        setattr(message, key, value)
    message.title = title
    return message


def ensure_read_record(message, user, read_status=1, read_at=None):
    record = MessageReadRecord.query.filter_by(message_id=message.id, user_id=user.id).first()
    if not record:
        record = MessageReadRecord(message_id=message.id, user_id=user.id)
        db.session.add(record)
    record.read_status = read_status
    record.read_at = read_at
    return record


def upsert_result(contest, student, **payload):
    result = ContestResult.query.filter_by(contest_id=contest.id, student_id=student.id).first()
    if not result:
        result = ContestResult(contest_id=contest.id, student_id=student.id)
        db.session.add(result)
    for key, value in payload.items():
        setattr(result, key, value)
    return result


def ensure_certificate(result, file_name, uploader):
    certificates_dir = UPLOAD_DIR / 'certificates'
    certificates_dir.mkdir(parents=True, exist_ok=True)
    target_path = certificates_dir / f'demo_result_{result.id}_{file_name}'
    if not target_path.exists():
        target_path.write_text(f'Demo certificate for result {result.id}\n', encoding='utf-8')

    attachment = AttachmentInfo.query.filter_by(biz_type=f'certificate:{result.id}', file_name=file_name).first()
    if not attachment:
        attachment = AttachmentInfo(
            file_name=file_name,
            file_path=str(target_path),
            file_ext=target_path.suffix.lower().lstrip('.'),
            file_size=target_path.stat().st_size,
            biz_type=f'certificate:{result.id}',
            uploader_id=uploader.id,
            uploaded_at=NOW,
        )
        db.session.add(attachment)
    else:
        attachment.file_path = str(target_path)
        attachment.file_ext = target_path.suffix.lower().lstrip('.')
        attachment.file_size = target_path.stat().st_size
        attachment.uploader_id = uploader.id
        attachment.uploaded_at = NOW
    result.certificate_attachment_name = file_name
    return attachment


def main():
    app = create_app()
    with app.app_context():
        admin = get_user('admin')
        teacher = get_user('teacher')
        reviewer = get_user('reviewer')
        student_user = get_user('student', '20260001')

        students = {
            '20260001': upsert_student('20260001', name='张三', gender='男', college='计算机学院', major='软件工程', class_name='软件工程 2201', grade='2022级', advisor_name='王老师', mobile='13800000001', email='student@example.com', history_experience='2024 校级算法竞赛二等奖', remark='默认演示学生', status=1),
            '20260002': upsert_student('20260002', name='李四', gender='女', college='计算机学院', major='人工智能', class_name='人工智能 2201', grade='2022级', advisor_name='陈老师', mobile='13800000002', email='lisi@example.com', history_experience='2025 智能车竞赛校级一等奖', remark='演示数据：待补正案例', status=1),
            '20260003': upsert_student('20260003', name='王敏', gender='女', college='数学学院', major='信息与计算科学', class_name='信计 2301', grade='2023级', advisor_name='刘老师', mobile='13800000003', email='wangmin@example.com', history_experience='2025 数学建模竞赛参赛', remark='演示数据：审核中案例', status=1),
            '20260004': upsert_student('20260004', name='赵强', gender='男', college='电子学院', major='电子信息工程', class_name='电子 2203', grade='2022级', advisor_name='周老师', mobile='13800000004', email='zhaoqiang@example.com', history_experience='2025 机器人竞赛省级三等奖', remark='演示数据：已通过并有成绩', status=1),
            '20260005': upsert_student('20260005', name='孙悦', gender='女', college='机电学院', major='自动化', class_name='自动化 2102', grade='2021级', advisor_name='何老师', mobile='13800000005', email='sunyue@example.com', history_experience='2024 机器人大赛校级一等奖', remark='演示数据：退赛案例', status=1),
            '20260006': upsert_student('20260006', name='陈晨', gender='男', college='商学院', major='大数据管理与应用', class_name='大数据 2302', grade='2023级', advisor_name='赵老师', mobile='13800000006', email='chenchen@example.com', history_experience='2025 数据分析挑战赛决赛入围', remark='演示数据：补录和赛后归档案例', status=1),
            '20260007': upsert_student('20260007', name='郑凯', gender='男', college='计算机学院', major='网络工程', class_name='网络工程 2202', grade='2022级', advisor_name='吴老师', mobile='13800000007', email='zhengkai@example.com', history_experience='2025 网络攻防赛校级一等奖', remark='演示数据：换人前原报名人', status=1),
            '20260008': upsert_student('20260008', name='黄婷', gender='女', college='外国语学院', major='商务英语', class_name='商务英语 2401', grade='2024级', advisor_name='林老师', mobile='13800000008', email='huangting@example.com', history_experience='2025 创新创业训练营展示奖', remark='演示数据：换人后补录报名人', status=1),
        }
        db.session.flush()
        student_user.student_id = students['20260001'].id

        contests = {
            '校级算法竞赛': upsert_contest('校级算法竞赛', contest_level='校级', organizer='教务处', subject_category='程序设计', undertaker='计算机学院', target_students='本科生', contact_name='竞赛秘书', contact_mobile='13800009999', location='创新实验中心', description='面向全校的软件与算法方向竞赛。', contest_year=2026, sign_up_start=NOW - timedelta(days=18), sign_up_end=NOW + timedelta(days=5), contest_date=NOW + timedelta(days=15), status='signing_up', material_requirements='学生证、成绩单、作品说明', quota_limit=200, rule_attachment_name='algorithm_rules.pdf'),
            '省级程序设计竞赛': upsert_contest('省级程序设计竞赛', contest_level='省级', organizer='省教育厅', subject_category='程序设计', undertaker='计算机学院', target_students='本科生', contact_name='李老师', contact_mobile='13800002222', location='省大学城', description='省级程序设计赛事，报名后进入集中审核。', contest_year=2026, sign_up_start=NOW - timedelta(days=25), sign_up_end=NOW + timedelta(days=2), contest_date=NOW + timedelta(days=20), status='reviewing', material_requirements='报名表、成绩单、指导老师推荐意见', quota_limit=60, rule_attachment_name='provincial_programming_rules.pdf'),
            '大学生机器人大赛': upsert_contest('大学生机器人大赛', contest_level='国家级', organizer='教育部高教司', subject_category='机器人', undertaker='机电学院', target_students='本科生/研究生', contact_name='顾老师', contact_mobile='13800003333', location='工程训练中心', description='机器人设计与对抗类竞赛。', contest_year=2026, sign_up_start=NOW - timedelta(days=40), sign_up_end=NOW - timedelta(days=10), contest_date=NOW + timedelta(days=8), status='closed', material_requirements='方案书、视频、队伍信息表', quota_limit=30, rule_attachment_name='robot_contest_rules.pdf'),
            '数据分析挑战赛': upsert_contest('数据分析挑战赛', contest_level='校级', organizer='商学院', subject_category='数据分析', undertaker='商学院数据实验室', target_students='本科生', contact_name='许老师', contact_mobile='13800004444', location='经管楼报告厅', description='赛后已进入归档与统计阶段。', contest_year=2026, sign_up_start=NOW - timedelta(days=60), sign_up_end=NOW - timedelta(days=25), contest_date=NOW - timedelta(days=7), status='archived', material_requirements='分析报告、答辩材料', quota_limit=80, rule_attachment_name='data_challenge_rules.pdf'),
            '创新创业训练营答辩赛': upsert_contest('创新创业训练营答辩赛', contest_level='校级', organizer='创新创业学院', subject_category='创新创业', undertaker='创新创业学院', target_students='本科生', contact_name='冯老师', contact_mobile='13800005555', location='创业中心路演厅', description='待发布的训练营答辩赛。', contest_year=2026, sign_up_start=NOW + timedelta(days=10), sign_up_end=NOW + timedelta(days=20), contest_date=NOW + timedelta(days=28), status='draft', material_requirements='项目计划书、路演PPT', quota_limit=40, rule_attachment_name='innovation_camp_rules.pdf'),
        }
        db.session.flush()

        teacher_managed_contests = [
            contests['校级算法竞赛'],
            contests['数据分析挑战赛'],
            contests['创新创业训练营答辩赛'],
        ]
        reviewer_contests = [
            contests['校级算法竞赛'],
            contests['省级程序设计竞赛'],
        ]
        for contest in teacher_managed_contests:
            ensure_contest_permission(contest, teacher, 'manage')
            ensure_contest_permission(contest, teacher, 'result')
        for contest in reviewer_contests:
            ensure_contest_permission(contest, reviewer, 'review')

        registrations = {}
        registrations['approved_alg'] = upsert_registration(contests['校级算法竞赛'], students['20260001'], direction='算法设计', team_name='Alpha Team', project_name='算法优化平台', instructor_name='王老师', instructor_mobile='13800001111', emergency_contact='张女士', emergency_mobile='13900001111', source_type='online', remark='材料齐全', registration_status='approved', review_status='approved', final_status='approved', submit_time=NOW - timedelta(days=12))
        registrations['correction_alg'] = upsert_registration(contests['校级算法竞赛'], students['20260002'], direction='智能车', team_name='Smart Wheels', project_name='智能车路径规划', instructor_name='陈老师', instructor_mobile='13800002223', emergency_contact='李先生', emergency_mobile='13900002222', source_type='online', remark='身份证明缺少盖章页', registration_status='correction_required', review_status='correction_required', final_status='correction_required', submit_time=NOW - timedelta(days=9))
        registrations['reviewing_prov'] = upsert_registration(contests['省级程序设计竞赛'], students['20260003'], direction='系统设计', team_name='Matrix', project_name='赛题评测系统', instructor_name='刘老师', instructor_mobile='13800003334', emergency_contact='王女士', emergency_mobile='13900003333', source_type='import', remark='等待复核', registration_status='reviewing', review_status='reviewing', final_status='reviewing', submit_time=NOW - timedelta(days=6))
        registrations['approved_prov'] = upsert_registration(contests['省级程序设计竞赛'], students['20260004'], direction='嵌入式开发', team_name='Robotics Lab', project_name='机器人控制系统', instructor_name='周老师', instructor_mobile='13800004445', emergency_contact='赵女士', emergency_mobile='13900004444', source_type='online', remark='已通过审核', registration_status='approved', review_status='approved', final_status='approved', submit_time=NOW - timedelta(days=14))
        registrations['withdraw_robot'] = upsert_registration(contests['大学生机器人大赛'], students['20260005'], direction='机器人控制', team_name='AutoDrive', project_name='机器人自主导航', instructor_name='何老师', instructor_mobile='13800005556', emergency_contact='孙先生', emergency_mobile='13900005555', source_type='online', remark='因课程冲突退赛', registration_status='withdrawn', review_status='pending', final_status='withdrawn', submit_time=NOW - timedelta(days=20))
        registrations['supplement_data'] = upsert_registration(contests['数据分析挑战赛'], students['20260006'], direction='商业分析', team_name='Insight', project_name='校园消费数据分析', instructor_name='赵老师', instructor_mobile='13800006667', emergency_contact='陈女士', emergency_mobile='13900006666', source_type='import', remark='补录入围名单', registration_status='supplemented', review_status='reviewing', final_status='supplemented', submit_time=NOW - timedelta(days=17))
        registrations['replaced_old'] = upsert_registration(contests['校级算法竞赛'], students['20260007'], direction='网络安全', team_name='Blue Shield', project_name='漏洞检测平台', instructor_name='吴老师', instructor_mobile='13800007778', emergency_contact='郑女士', emergency_mobile='13900007777', source_type='online', remark='队员调整', registration_status='replaced', review_status='pending', final_status='replaced', submit_time=NOW - timedelta(days=7))
        registrations['replacement_new'] = upsert_registration(contests['校级算法竞赛'], students['20260008'], direction='网络安全', team_name='Blue Shield', project_name='漏洞检测平台', instructor_name='吴老师', instructor_mobile='13800007778', emergency_contact='黄女士', emergency_mobile='13900008888', source_type='online', remark='承接换人后的报名', registration_status='supplemented', review_status='reviewing', final_status='supplemented', submit_time=NOW - timedelta(days=5))
        registrations['rejected_robot'] = upsert_registration(contests['大学生机器人大赛'], students['20260006'], direction='机器人控制', team_name='DataBots', project_name='机械臂协同控制', instructor_name='赵老师', instructor_mobile='13800006667', emergency_contact='陈女士', emergency_mobile='13900006666', source_type='online', remark='方案与赛事方向不匹配', registration_status='rejected', review_status='rejected', final_status='rejected', submit_time=NOW - timedelta(days=19))
        db.session.flush()

        ensure_material(registrations['approved_alg'], '成绩单', 'zhangsan_transcript.pdf', 'approved', '材料齐全，审核通过', reviewer, NOW - timedelta(days=10))
        ensure_material(registrations['approved_alg'], '项目说明', 'zhangsan_project.pdf', 'approved', '材料齐全，审核通过', reviewer, NOW - timedelta(days=10))
        ensure_material(registrations['correction_alg'], '身份证明', 'lisi_identity_scan.pdf', 'rejected', '缺少学院盖章页，请补充', reviewer, NOW - timedelta(days=7))
        ensure_material(registrations['reviewing_prov'], '报名表', 'wangmin_registration_form.pdf', 'pending', None, None, None)
        ensure_material(registrations['approved_prov'], '方案书', 'zhaoqiang_plan.pdf', 'approved', '方案完整，可以进入后续名单确认', reviewer, NOW - timedelta(days=12))
        ensure_material(registrations['supplement_data'], '分析报告', 'chenchen_report.pdf', 'pending', None, None, None)
        ensure_material(registrations['replacement_new'], '队伍信息表', 'huangting_team_form.pdf', 'pending', None, None, None)
        ensure_material(registrations['rejected_robot'], '方案书', 'chenchen_robot_plan.pdf', 'rejected', '项目内容与赛事规则不匹配', reviewer, NOW - timedelta(days=16))

        ensure_flow(registrations['approved_alg'], 'submit_registration', None, 'submitted', '提交报名', teacher, NOW - timedelta(days=12))
        ensure_flow(registrations['approved_alg'], 'submit_materials', 'submitted', 'reviewing', '提交审核材料', teacher, NOW - timedelta(days=11))
        ensure_flow(registrations['approved_alg'], 'review_approve', 'reviewing', 'approved', '材料齐全，审核通过', reviewer, NOW - timedelta(days=10))

        ensure_flow(registrations['correction_alg'], 'submit_registration', None, 'submitted', '提交报名', teacher, NOW - timedelta(days=9))
        ensure_flow(registrations['correction_alg'], 'submit_materials', 'submitted', 'reviewing', '提交审核材料', teacher, NOW - timedelta(days=8))
        ensure_flow(registrations['correction_alg'], 'review_correction_required', 'reviewing', 'correction_required', '缺少学院盖章页，请补充', reviewer, NOW - timedelta(days=7))

        ensure_flow(registrations['reviewing_prov'], 'submit_registration', None, 'submitted', '批量导入报名数据', teacher, NOW - timedelta(days=6))
        ensure_flow(registrations['reviewing_prov'], 'submit_materials', 'submitted', 'reviewing', '补交报名表', teacher, NOW - timedelta(days=5))

        ensure_flow(registrations['approved_prov'], 'submit_registration', None, 'submitted', '提交报名', teacher, NOW - timedelta(days=14))
        ensure_flow(registrations['approved_prov'], 'submit_materials', 'submitted', 'reviewing', '提交审核材料', teacher, NOW - timedelta(days=13))
        ensure_flow(registrations['approved_prov'], 'review_approve', 'reviewing', 'approved', '方案完整，可以进入后续名单确认', reviewer, NOW - timedelta(days=12))

        ensure_flow(registrations['withdraw_robot'], 'submit_registration', None, 'submitted', '提交报名', teacher, NOW - timedelta(days=20))
        ensure_flow(registrations['withdraw_robot'], 'withdraw', 'submitted', 'withdrawn', '课程冲突，主动退赛', teacher, NOW - timedelta(days=18))

        ensure_flow(registrations['supplement_data'], 'import_registration_create', None, 'supplemented', '批量导入报名数据', teacher, NOW - timedelta(days=17))
        ensure_flow(registrations['supplement_data'], 'supplement', 'submitted', 'supplemented', '补录入围名单', teacher, NOW - timedelta(days=16))

        ensure_flow(registrations['replaced_old'], 'submit_registration', None, 'submitted', '提交报名', teacher, NOW - timedelta(days=7))
        ensure_flow(registrations['replaced_old'], 'replace', 'submitted', 'replaced', '换人为 黄婷', teacher, NOW - timedelta(days=4))
        ensure_flow(registrations['replacement_new'], 'replacement_entry', None, 'supplemented', '承接原报名换人后的资格', teacher, NOW - timedelta(days=4))

        ensure_flow(registrations['rejected_robot'], 'submit_registration', None, 'submitted', '提交报名', teacher, NOW - timedelta(days=19))
        ensure_flow(registrations['rejected_robot'], 'submit_materials', 'submitted', 'reviewing', '提交审核材料', teacher, NOW - timedelta(days=18))
        ensure_flow(registrations['rejected_robot'], 'review_reject', 'reviewing', 'rejected', '项目内容与赛事规则不匹配', reviewer, NOW - timedelta(days=16))

        messages = [
            upsert_message('校级算法竞赛审核结果通知', message_type='message', target_scope='contest', contest_id=contests['校级算法竞赛'].id, target_role='student', target_status='approved', priority='high', summary='已通过审核的同学请关注后续赛程安排。', planned_send_at=NOW - timedelta(days=9), content='你已通过校级算法竞赛资格审核，请在比赛前确认赛程与签到要求。', send_status='sent', created_by=teacher.id, created_at=NOW - timedelta(days=9)),
            upsert_message('校级算法竞赛补正提醒', message_type='todo', target_scope='contest', contest_id=contests['校级算法竞赛'].id, target_role='student', target_status='correction_required', priority='urgent', summary='请尽快补充缺失材料。', planned_send_at=NOW - timedelta(days=6), content='你的报名材料存在缺失项，请在截止时间前补充盖章页与身份证明。', send_status='pending', created_by=reviewer.id, created_at=NOW - timedelta(days=6)),
            upsert_message('省级程序设计竞赛审核排班', message_type='notice', target_scope='role', contest_id=contests['省级程序设计竞赛'].id, target_role='reviewer', target_status=None, priority='normal', summary='审核老师请按排班表处理报名。', planned_send_at=NOW - timedelta(days=5), content='省级程序设计竞赛已进入集中审核阶段，请审核老师按排班表完成复核。', send_status='sent', created_by=admin.id, created_at=NOW - timedelta(days=5)),
            upsert_message('机器人大赛报名关闭通知', message_type='notice', target_scope='contest', contest_id=contests['大学生机器人大赛'].id, target_role='teacher', target_status=None, priority='low', summary='报名阶段已结束。', planned_send_at=NOW - timedelta(days=10), content='大学生机器人大赛报名已截止，后续将进入名单确认与赛前准备。', send_status='canceled', created_by=teacher.id, created_at=NOW - timedelta(days=10)),
            upsert_message('数据分析挑战赛归档提醒', message_type='todo', target_scope='contest', contest_id=contests['数据分析挑战赛'].id, target_role='teacher', target_status='approved', priority='high', summary='请补全成绩和证书归档信息。', planned_send_at=NOW - timedelta(days=2), content='数据分析挑战赛已结束，请补录成绩、证书编号和归档备注。', send_status='sent', created_by=teacher.id, created_at=NOW - timedelta(days=2)),
        ]
        db.session.flush()

        ensure_read_record(messages[0], admin, 1, NOW - timedelta(days=8, hours=20))
        ensure_read_record(messages[0], student_user, 1, NOW - timedelta(days=8, hours=12))
        ensure_read_record(messages[2], reviewer, 1, NOW - timedelta(days=4, hours=18))

        result1 = upsert_result(contests['校级算法竞赛'], students['20260001'], award_level='二等奖', result_status='awarded', score=91.5, ranking=12, certificate_no='ALG-2026-021', archive_remark='校赛现场赛获奖', confirmed_at=NOW - timedelta(days=1))
        result2 = upsert_result(contests['省级程序设计竞赛'], students['20260004'], award_level='一等奖', result_status='awarded', score=96.0, ranking=2, certificate_no='PRO-2026-002', archive_remark='省赛决赛获奖', confirmed_at=NOW - timedelta(hours=18))
        result3 = upsert_result(contests['数据分析挑战赛'], students['20260006'], award_level='三等奖', result_status='archived', score=88.0, ranking=9, certificate_no='DATA-2026-015', archive_remark='已完成赛后归档', confirmed_at=NOW - timedelta(days=3))
        result4 = upsert_result(contests['校级算法竞赛'], students['20260008'], award_level=None, result_status='participated', score=79.0, ranking=31, certificate_no=None, archive_remark='已参赛，未获奖', confirmed_at=NOW - timedelta(days=1, hours=2))
        db.session.flush()

        ensure_certificate(result1, 'alg_second_prize.pdf', teacher)
        ensure_certificate(result2, 'prov_first_prize.pdf', teacher)
        ensure_certificate(result3, 'data_third_prize.pdf', teacher)

        db.session.commit()

        print({
            'students': StudentInfo.query.count(),
            'contests': ContestInfo.query.count(),
            'registrations': ContestRegistration.query.count(),
            'materials': RegistrationMaterial.query.count(),
            'flowLogs': RegistrationFlowLog.query.count(),
            'messages': NoticeMessage.query.count(),
            'results': ContestResult.query.count(),
        })


if __name__ == '__main__':
    main()
