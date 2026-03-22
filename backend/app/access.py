from flask import g

from .data_scope import student_in_college_scope
from .errors import APIError
from .models import ContestPermission, ContestRegistration, StudentInfo, build_registration_data_quality
from .runtime_menu_store import user_menu_path_set


ADMIN_ROLES = {"admin"}
TEACHER_ROLES = {"teacher"}
REVIEWER_ROLES = {"reviewer"}
MANAGER_ROLES = ADMIN_ROLES | TEACHER_ROLES
REVIEW_ROLES = ADMIN_ROLES | REVIEWER_ROLES
RESULT_EDITOR_ROLES = ADMIN_ROLES | TEACHER_ROLES
MESSAGE_EDITOR_ROLES = ADMIN_ROLES | TEACHER_ROLES
CONTEST_MANAGE_SCOPES = {"manage"}
CONTEST_REVIEW_SCOPES = {"review"}
CONTEST_RESULT_SCOPES = {"manage", "result"}
REGISTRATION_TERMINAL_STATUSES = {"withdrawn", "replaced", "archived"}
REGISTRATION_REVIEWABLE_STATUSES = {"submitted", "reviewing", "correction_required", "supplemented"}
TEACHER_MENU_PATHS = {"contests", "registrations", "qualifications", "results", "statistics"}


def current_user():
    return getattr(g, "current_user", None)


def current_role_codes(user=None):
    target = user or current_user()
    return set(getattr(target, "role_codes", []) or [])


def current_menu_paths(user=None):
    target = user or current_user()
    if not target:
        return set()
    return user_menu_path_set(target)


def has_any_role(*roles, user=None):
    return bool(current_role_codes(user).intersection(set(roles)))


def is_admin_user(user=None):
    return has_any_role(*ADMIN_ROLES, user=user)


def is_teacher_user(user=None):
    if has_any_role(*TEACHER_ROLES, user=user):
        return True
    if is_admin_user(user) or is_reviewer_user(user) or is_student_user(user):
        return False
    return bool(current_menu_paths(user).intersection(TEACHER_MENU_PATHS))


def is_reviewer_user(user=None):
    if is_admin_user(user):
        return False
    return has_any_role(*REVIEWER_ROLES, user=user) or "reviews" in current_menu_paths(user)


def is_student_user(user=None):
    role_codes = current_role_codes(user)
    if not role_codes:
        return False
    return "student" in role_codes and not role_codes.intersection(MANAGER_ROLES | REVIEWER_ROLES)


def assigned_contest_ids(user=None, scopes=None):
    target = user or current_user()
    if not target:
        return set()
    if is_admin_user(target):
        return None
    query = ContestPermission.query.filter_by(user_id=target.id)
    if scopes:
        query = query.filter(ContestPermission.permission_scope.in_(sorted(set(scopes))))
    return {int(item.contest_id) for item in query.all()}


def managed_contest_ids(user=None):
    return assigned_contest_ids(user=user, scopes=CONTEST_MANAGE_SCOPES)


def reviewable_contest_ids(user=None):
    return assigned_contest_ids(user=user, scopes=CONTEST_REVIEW_SCOPES)


def result_visible_contest_ids(user=None):
    return assigned_contest_ids(user=user, scopes=CONTEST_RESULT_SCOPES)


def inbox_visible_contest_ids(user=None):
    target = user or current_user()
    if not target:
        return set()
    if is_admin_user(target):
        return None
    scopes = set()
    if is_teacher_user(target):
        scopes.update(CONTEST_RESULT_SCOPES)
    if is_reviewer_user(target):
        scopes.update(CONTEST_REVIEW_SCOPES)
    if not scopes:
        return set()
    return assigned_contest_ids(user=target, scopes=scopes)


def current_contest_scopes(contest_id, user=None):
    target = user or current_user()
    if not target:
        return set()
    if is_admin_user(target):
        return {"manage", "review", "result"}
    return {
        item.permission_scope
        for item in ContestPermission.query.filter_by(user_id=target.id, contest_id=int(contest_id)).all()
    }


def has_contest_scope(contest_id, scopes, user=None):
    allowed_ids = assigned_contest_ids(user=user, scopes=scopes)
    if allowed_ids is None:
        return True
    return int(contest_id) in allowed_ids


def apply_contest_scope(query, contest_column, contest_ids):
    if contest_ids is None:
        return query
    return query.filter(contest_column.in_(list(contest_ids) or [-1]))


def ensure_contest_scope(contest_id, scopes, message):
    if not has_contest_scope(contest_id, scopes):
        raise APIError(message, code=403, status=200)
    return int(contest_id)


def ensure_managed_contest(contest_id, message="当前账号无权管理该赛事"):
    return ensure_contest_scope(contest_id, CONTEST_MANAGE_SCOPES, message)


def ensure_reviewable_contest(contest_id, message="当前账号无权审核该赛事"):
    return ensure_contest_scope(contest_id, CONTEST_REVIEW_SCOPES, message)


def ensure_result_visible_contest(contest_id, message="当前账号无权查看该赛事成绩"):
    return ensure_contest_scope(contest_id, CONTEST_RESULT_SCOPES, message)


def resolve_bound_student(user=None, required=False):
    target = user or current_user()
    if not target or not is_student_user(target):
        return None

    student = None
    if getattr(target, "student_id", None):
        student = StudentInfo.query.get(target.student_id)
    if not student and target.username:
        student = StudentInfo.query.filter_by(student_no=target.username).first()
    if not student and target.mobile:
        student = StudentInfo.query.filter_by(mobile=target.mobile).first()

    if required and not student:
        raise APIError("当前学生账号未绑定学生档案", code=403, status=200)
    return student


def ensure_student_owner(student_id, message="仅可访问本人数据"):
    student = resolve_bound_student(required=True)
    if int(student_id) != int(student.id):
        raise APIError(message, code=403, status=200)
    return student


def registration_belongs_to_current_student(registration):
    student = resolve_bound_student(required=True)
    return int(registration.student_id) == int(student.id)


def ensure_registration_access(registration, message="仅可访问本人的报名记录"):
    if is_admin_user():
        return registration
    if is_teacher_user():
        ensure_managed_contest(registration.contest_id, "当前账号无权访问该赛事报名记录")
        student = registration.student or StudentInfo.query.get(registration.student_id)
        if not student_in_college_scope(student, current_user()):
            raise APIError("当前账号无权访问该学院报名记录", code=403, status=200)
        return registration
    if is_reviewer_user():
        ensure_reviewable_contest(registration.contest_id, "当前账号无权访问该赛事审核记录")
        student = registration.student or StudentInfo.query.get(registration.student_id)
        if not student_in_college_scope(student, current_user()):
            raise APIError("当前账号无权访问该学院报名记录", code=403, status=200)
        return registration
    if not registration_belongs_to_current_student(registration):
        raise APIError(message, code=403, status=200)
    return registration


def student_status_index(student_id):
    status_map = {}
    for item in ContestRegistration.query.filter_by(student_id=student_id).all():
        statuses = status_map.setdefault(item.contest_id, set())
        if item.final_status:
            statuses.add(item.final_status)
        if item.review_status:
            statuses.add(item.review_status)
    return status_map


def can_edit_registration(registration, user=None):
    if is_admin_user(user):
        return registration.final_status not in REGISTRATION_TERMINAL_STATUSES
    if is_teacher_user(user):
        return has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user) and registration.final_status not in REGISTRATION_TERMINAL_STATUSES
    if has_any_role(*MANAGER_ROLES, user=user):
        return registration.final_status not in REGISTRATION_TERMINAL_STATUSES
    if is_student_user(user) and registration_belongs_to_current_student(registration):
        return registration.final_status in {"submitted", "correction_required"}
    return False


def can_submit_materials(registration, user=None):
    owner_or_manager = is_admin_user(user) or (
        is_teacher_user(user) and has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user)
    ) or (
        is_student_user(user) and registration_belongs_to_current_student(registration)
    )
    return owner_or_manager and (
        registration.final_status in {"submitted", "correction_required", "supplemented"} or
        (registration_requires_attachment_repair(registration) and registration.final_status not in REGISTRATION_TERMINAL_STATUSES)
    )


def can_submit_correction(registration, user=None):
    owner_or_manager = is_admin_user(user) or (
        is_teacher_user(user) and has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user)
    ) or (
        is_student_user(user) and registration_belongs_to_current_student(registration)
    )
    return owner_or_manager and registration.final_status == "correction_required"


def can_withdraw_registration(registration, user=None):
    owner_or_manager = is_admin_user(user) or (
        is_teacher_user(user) and has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user)
    ) or (
        is_student_user(user) and registration_belongs_to_current_student(registration)
    )
    return owner_or_manager and registration.final_status in {
        "submitted",
        "reviewing",
        "correction_required",
        "approved",
        "supplemented",
    }


def can_replace_registration(registration, user=None):
    return (is_admin_user(user) or (is_teacher_user(user) and has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user))) and registration.final_status in {
        "submitted",
        "reviewing",
        "correction_required",
        "approved",
        "supplemented",
    }


def can_supplement_registration(registration, user=None):
    return (is_admin_user(user) or (is_teacher_user(user) and has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user))) and registration.final_status in {"rejected", "withdrawn", "replaced"}


def can_review_registration(registration, user=None):
    return (is_admin_user(user) or (is_reviewer_user(user) and has_contest_scope(registration.contest_id, CONTEST_REVIEW_SCOPES, user=user))) and registration.final_status in REGISTRATION_REVIEWABLE_STATUSES


def registration_data_quality(registration):
    material_payloads = [item.to_dict() for item in registration.materials]
    return build_registration_data_quality(material_payloads, registration.final_status)


def registration_requires_attachment_repair(registration):
    return registration_data_quality(registration)["requiresAttachmentRepair"]


def can_approve_registration(registration, user=None):
    quality = registration_data_quality(registration)
    return can_review_registration(registration, user=user) and quality["attachmentCount"] > 0 and not quality["requiresAttachmentRepair"]


def can_view_result_record(result, user=None):
    if is_admin_user(user):
        return True
    if is_teacher_user(user):
        student = StudentInfo.query.get(result.student_id)
        return has_contest_scope(result.contest_id, CONTEST_RESULT_SCOPES, user=user) and student_in_college_scope(student, user or current_user())
    if is_student_user(user):
        student = resolve_bound_student(user=user, required=True)
        return int(result.student_id) == int(student.id)
    return False


def ensure_result_access(result, message="当前账号无权查看该成绩记录"):
    if not can_view_result_record(result):
        raise APIError(message, code=403, status=200)
    return result
