from flask import Blueprint, g

from ..access import (
    apply_contest_scope,
    current_role_codes,
    inbox_visible_contest_ids,
    is_admin_user,
    is_reviewer_user,
    is_student_user,
    is_teacher_user,
    managed_contest_ids,
    resolve_bound_student,
    result_visible_contest_ids,
    reviewable_contest_ids,
    student_status_index,
)
from ..common import success
from ..extensions import db
from ..models import ContestInfo, ContestRegistration, ContestResult, NoticeMessage, StudentInfo, SysRole, parse_message_target_roles, parse_message_target_user_ids
from ..security import auth_required


bp = Blueprint("system", __name__, url_prefix="/api/v1/system")


STATUS_LABELS = {
    "draft": "草稿",
    "signing_up": "报名中",
    "reviewing": "审核中",
    "closed": "已关闭",
    "archived": "已归档",
    "submitted": "已提交",
    "pending": "待处理",
    "correction_required": "待补正",
    "approved": "已通过",
    "rejected": "已驳回",
    "withdrawn": "已退赛",
    "replaced": "已替换",
    "supplemented": "补录中",
    "awarded": "已获奖",
    "participated": "已参赛",
}


MESSAGE_TYPE_LABELS = {
    "notice": "公告",
    "todo": "待办",
    "message": "通知",
}


def serialize_dashboard_message(item):
    return {
        "id": item.id,
        "title": item.title,
        "messageType": item.message_type,
        "messageTypeLabel": MESSAGE_TYPE_LABELS.get(item.message_type, item.message_type),
        "sendStatus": item.send_status,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
        "createdByName": item.creator.real_name if item.creator else None,
    }


def role_visible_messages(message_query):
    role_codes = sorted(current_role_codes())
    contest_ids = inbox_visible_contest_ids()
    items = []
    for item in message_query.order_by(NoticeMessage.id.desc()).all():
        if item.send_status != "sent":
            continue
        direct_user_ids = parse_message_target_user_ids(item.target_user_ids)
        if direct_user_ids:
            if g.current_user.id in direct_user_ids:
                items.append(item)
            continue
        target_roles = parse_message_target_roles(item.target_role)
        if target_roles and not set(target_roles).intersection(role_codes):
            continue
        if contest_ids is not None and item.contest_id and item.contest_id not in contest_ids:
            continue
        items.append(item)
    return items


@bp.get("/dashboard")
@auth_required()
def dashboard():
    registration_query = ContestRegistration.query
    result_query = ContestResult.query
    contest_query = ContestInfo.query
    message_query = NoticeMessage.query
    student_query = StudentInfo.query

    if is_student_user():
        student = resolve_bound_student(required=True)
        registration_query = registration_query.filter(ContestRegistration.student_id == student.id)
        result_query = result_query.filter(ContestResult.student_id == student.id)
        student_query = student_query.filter(StudentInfo.id == student.id)
        registered_contest_ids = [item.contest_id for item in registration_query.all()]
        contest_query = contest_query.filter(ContestInfo.id.in_(registered_contest_ids or [-1]))
        status_map = student_status_index(student.id)
        allowed_messages = []
        for item in message_query.order_by(NoticeMessage.id.desc()).all():
            if item.send_status != "sent":
                continue
            direct_user_ids = parse_message_target_user_ids(item.target_user_ids)
            if direct_user_ids:
                if g.current_user.id in direct_user_ids:
                    allowed_messages.append(item)
                continue
            target_roles = parse_message_target_roles(item.target_role)
            if target_roles and "student" not in target_roles:
                continue
            if item.contest_id and item.contest_id not in status_map:
                continue
            if item.target_status:
                if item.contest_id and item.target_status not in status_map.get(item.contest_id, set()):
                    continue
                if not item.contest_id and not any(item.target_status in statuses for statuses in status_map.values()):
                    continue
            allowed_messages.append(item)
        recent_messages = [serialize_dashboard_message(item) for item in allowed_messages[:6]]
        sent_message_count = len(allowed_messages)
    elif is_admin_user():
        visible_messages = role_visible_messages(message_query)
        recent_messages = [serialize_dashboard_message(item) for item in visible_messages[:6]]
        sent_message_count = message_query.filter_by(send_status="sent").count()
    else:
        if is_teacher_user():
            contest_query = apply_contest_scope(contest_query, ContestInfo.id, managed_contest_ids())
            registration_query = apply_contest_scope(registration_query, ContestRegistration.contest_id, managed_contest_ids())
            result_query = apply_contest_scope(result_query, ContestResult.contest_id, result_visible_contest_ids())
        elif is_reviewer_user():
            contest_query = apply_contest_scope(contest_query, ContestInfo.id, reviewable_contest_ids())
            registration_query = apply_contest_scope(registration_query, ContestRegistration.contest_id, reviewable_contest_ids())
            result_query = apply_contest_scope(result_query, ContestResult.contest_id, set())
        visible_messages = role_visible_messages(message_query)
        recent_messages = [serialize_dashboard_message(item) for item in visible_messages[:6]]
        sent_message_count = len(visible_messages)

    pending_reviews_query = registration_query.filter(
        ContestRegistration.review_status.in_(["pending", "reviewing", "correction_required"])
    )
    status_breakdown = [
        {"status": status, "label": STATUS_LABELS.get(status, status), "count": count}
        for status, count in db.session.query(
            ContestRegistration.final_status,
            db.func.count(ContestRegistration.id),
        )
        .filter(ContestRegistration.id.in_([item.id for item in registration_query.all()] or [-1]))
        .group_by(ContestRegistration.final_status)
    ]

    recent_contests = [
        {
            "id": item.id,
            "contestName": item.contest_name,
            "contestLevel": item.contest_level,
            "organizer": item.organizer,
            "status": item.status,
            "statusLabel": STATUS_LABELS.get(item.status, item.status),
            "quotaLimit": item.quota_limit,
            "contestDate": item.contest_date.isoformat() if item.contest_date else None,
            "signUpEnd": item.sign_up_end.isoformat() if item.sign_up_end else None,
        }
        for item in contest_query.order_by(ContestInfo.id.desc()).limit(6).all()
    ]

    recent_registrations = [
        {
            "id": item.id,
            "contestName": item.contest.contest_name if item.contest else None,
            "studentName": item.student.name if item.student else None,
            "studentNo": item.student.student_no if item.student else None,
            "college": item.student.college if item.student else None,
            "finalStatus": item.final_status,
            "reviewStatus": item.review_status,
            "submitTime": item.submit_time.isoformat() if item.submit_time else None,
        }
        for item in registration_query.order_by(ContestRegistration.submit_time.desc(), ContestRegistration.id.desc()).limit(8).all()
    ]

    todo_registrations = [
        {
            "id": item.id,
            "contestName": item.contest.contest_name if item.contest else None,
            "studentName": item.student.name if item.student else None,
            "studentNo": item.student.student_no if item.student else None,
            "reviewStatus": item.review_status,
            "finalStatus": item.final_status,
            "submitTime": item.submit_time.isoformat() if item.submit_time else None,
        }
        for item in pending_reviews_query.order_by(ContestRegistration.submit_time.desc(), ContestRegistration.id.desc()).limit(8).all()
    ]

    data = {
        "currentUser": g.current_user.to_dict(),
        "studentCount": student_query.count(),
        "contestCount": contest_query.count(),
        "registrationCount": registration_query.count(),
        "pendingReviewCount": pending_reviews_query.count(),
        "sentMessageCount": sent_message_count,
        "resultCount": result_query.count(),
        "awardedCount": result_query.filter(ContestResult.award_level.isnot(None)).count(),
        "statusBreakdown": status_breakdown,
        "recentContests": recent_contests,
        "recentRegistrations": recent_registrations,
        "todoRegistrations": todo_registrations,
        "recentMessages": recent_messages,
    }
    return success(data)


@bp.get("/dicts")
@auth_required()
def dicts():
    return success(
        {
            "roles": [item.to_dict() for item in SysRole.query.order_by(SysRole.id.asc())],
            "contestStatus": [
                {"label": "草稿", "value": "draft"},
                {"label": "报名中", "value": "signing_up"},
                {"label": "审核中", "value": "reviewing"},
                {"label": "已关闭", "value": "closed"},
                {"label": "已归档", "value": "archived"},
            ],
            "registrationStatus": [
                {"label": "已提交", "value": "submitted"},
                {"label": "审核中", "value": "reviewing"},
                {"label": "待补正", "value": "correction_required"},
                {"label": "已通过", "value": "approved"},
                {"label": "已驳回", "value": "rejected"},
                {"label": "已退赛", "value": "withdrawn"},
                {"label": "已替换", "value": "replaced"},
                {"label": "补录中", "value": "supplemented"},
            ],
            "messageType": [
                {"label": "公告", "value": "notice"},
                {"label": "提醒", "value": "todo"},
                {"label": "通知", "value": "message"},
            ],
        }
    )
