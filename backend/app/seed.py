from .extensions import db
from .models import ContestInfo, ContestPermission, StudentInfo, SysRole, SysUser
from .security import password_hash


DEFAULT_ROLES = [
    ("admin", "系统管理员"),
    ("teacher", "竞赛管理员"),
    ("reviewer", "审核人员"),
    ("student", "学生用户"),
]

DEFAULT_USERS = [
    ("admin", "系统管理员", "admin"),
    ("teacher", "竞赛教师", "teacher"),
    ("reviewer", "资格审核员", "reviewer"),
]


def seed_initial_data(default_password):
    created = False
    role_map = {}

    for role_code, role_name in DEFAULT_ROLES:
        role = SysRole.query.filter_by(role_code=role_code).first()
        if not role:
            role = SysRole(role_code=role_code, role_name=role_name, status=1)
            db.session.add(role)
            created = True
        role_map[role_code] = role

    db.session.flush()

    for username, real_name, role_code in DEFAULT_USERS:
        user = SysUser.query.filter_by(username=username).first()
        if not user:
            user = SysUser(
                username=username,
                real_name=real_name,
                password_hash=password_hash(default_password if username == "admin" else "Demo123!"),
                mobile="13800000000",
                email=f"{username}@example.com",
                status=1,
            )
            user.roles.append(role_map[role_code])
            db.session.add(user)
            created = True
        elif not user.email:
            user.email = f"{username}@example.com"
            created = True

    default_student = StudentInfo.query.filter_by(student_no="20260001").first()
    if not default_student:
        default_student = StudentInfo(
            student_no="20260001",
            name="张三",
            gender="男",
            college="计算机学院",
            major="软件工程",
            class_name="软件工程 2201",
            grade="2022级",
            advisor_name="王老师",
            mobile="13800000001",
            email="student@example.com",
            history_experience="2024 校级算法竞赛二等奖",
            remark="默认演示学生",
            status=1,
        )
        db.session.add(default_student)
        created = True

    if not ContestInfo.query.filter_by(contest_name="校级算法竞赛").first():
        db.session.add(
            ContestInfo(
                contest_name="校级算法竞赛",
                contest_level="校级",
                organizer="教务处",
                subject_category="程序设计",
                undertaker="计算机学院",
                target_students="本科生",
                contact_name="竞赛秘书",
                contact_mobile="13800009999",
                location="创新实验中心",
                description="面向全校的软件与算法方向竞赛。",
                contest_year=2026,
                status="signing_up",
                material_requirements="学生证、成绩单、作品说明",
                quota_limit=200,
            )
        )
        created = True

    db.session.flush()

    student_user = None
    if default_student:
        student_user = SysUser.query.filter_by(student_id=default_student.id).first()
        if not student_user:
            student_user = SysUser.query.filter_by(username=default_student.student_no).first()
        if not student_user:
            student_user = SysUser.query.filter_by(username="student").first()
        if not student_user:
            student_user = SysUser(
                username=default_student.student_no,
                real_name=default_student.name,
                password_hash=password_hash("Demo123!"),
                mobile=default_student.mobile,
                email=default_student.email,
                status=int(default_student.status or 1),
            )
            student_user.roles.append(role_map["student"])
            db.session.add(student_user)
            created = True
        if student_user.student_id != default_student.id:
            student_user.student_id = default_student.id
            created = True

    default_teacher = SysUser.query.filter_by(username="teacher").first()
    default_reviewer = SysUser.query.filter_by(username="reviewer").first()
    default_contest = ContestInfo.query.filter_by(contest_name="校级算法竞赛").first()
    if default_contest and default_teacher:
        for scope in ("manage", "result"):
            permission = ContestPermission.query.filter_by(
                contest_id=default_contest.id,
                user_id=default_teacher.id,
                permission_scope=scope,
            ).first()
            if not permission:
                db.session.add(ContestPermission(contest_id=default_contest.id, user_id=default_teacher.id, permission_scope=scope))
                created = True
    if default_contest and default_reviewer:
        permission = ContestPermission.query.filter_by(
            contest_id=default_contest.id,
            user_id=default_reviewer.id,
            permission_scope="review",
        ).first()
        if not permission:
            db.session.add(ContestPermission(contest_id=default_contest.id, user_id=default_reviewer.id, permission_scope="review"))
            created = True

    if created:
        db.session.commit()
