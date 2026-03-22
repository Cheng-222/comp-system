from sqlalchemy import or_

from .errors import APIError
from .extensions import db
from .models import (
    ContestPermission,
    ContestRegistration,
    MESSAGE_TARGET_ROLE_CODES,
    MessageSendFailure,
    NoticeMessage,
    SysRole,
    SysUser,
    parse_message_target_roles,
    parse_message_target_user_ids,
)
from .time_utils import now_beijing


MESSAGE_SCOPE_ROLE_HINTS = {
    "teacher": {"scopes": {"manage", "result"}, "label": "教师"},
    "reviewer": {"scopes": {"review"}, "label": "审核人"},
    "admin": {"scopes": set(), "label": "管理员"},
    "student": {"scopes": set(), "label": "学生"},
}


def normalize_target_roles(value):
    raw_roles = parse_message_target_roles(value)
    invalid_roles = [item for item in raw_roles if item not in MESSAGE_TARGET_ROLE_CODES]
    if invalid_roles:
        raise APIError("目标角色不合法")
    return [role for role in MESSAGE_TARGET_ROLE_CODES if role in raw_roles]


def normalize_target_user_ids(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = str(value).split(",")

    user_ids = []
    seen = set()
    for item in raw_items:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            user_id = int(raw)
        except (TypeError, ValueError) as error:
            raise APIError("目标接收人不合法") from error
        if user_id in seen:
            continue
        seen.add(user_id)
        user_ids.append(user_id)
    return user_ids


def serialize_target_user_ids(value):
    user_ids = normalize_target_user_ids(value)
    return ",".join(str(item) for item in user_ids) or None


def target_user_ids_blank_condition(column):
    return or_(column.is_(None), column == "")


def build_target_user_condition(column, user_id):
    if user_id in (None, ""):
        return False
    token = str(int(user_id))
    return or_(
        column == token,
        column.like(f"{token},%"),
        column.like(f"%,{token},%"),
        column.like(f"%,{token}"),
    )


def active_user_ids_for_roles(role_codes):
    if not role_codes:
        return set()
    rows = (
        SysUser.query.join(SysUser.roles)
        .filter(SysUser.status == 1, SysRole.role_code.in_(role_codes))
        .with_entities(SysUser.id)
        .distinct()
        .all()
    )
    return {int(item[0]) for item in rows}


def active_target_user_ids(user_ids):
    if not user_ids:
        return set()
    rows = (
        SysUser.query.filter(SysUser.status == 1, SysUser.id.in_(list(user_ids)))
        .with_entities(SysUser.id)
        .distinct()
        .all()
    )
    return {int(item[0]) for item in rows}


def count_student_recipients(message):
    directed_user_ids = parse_message_target_user_ids(message.target_user_ids)
    if directed_user_ids:
        return len(active_target_user_ids(directed_user_ids))
    if not message.contest_id and not message.target_status:
        return len(active_user_ids_for_roles(["student"]))
    query = ContestRegistration.query
    if message.contest_id:
        query = query.filter(ContestRegistration.contest_id == message.contest_id)
    if message.target_status:
        query = query.filter(
            or_(
                ContestRegistration.final_status == message.target_status,
                ContestRegistration.review_status == message.target_status,
                ContestRegistration.registration_status == message.target_status,
            )
        )
    return len({int(item[0]) for item in query.with_entities(ContestRegistration.student_id).distinct().all()})


def count_scoped_role_recipients(message, role_code):
    directed_user_ids = parse_message_target_user_ids(message.target_user_ids)
    if directed_user_ids:
        active_ids = active_target_user_ids(directed_user_ids)
        if not active_ids:
            return 0
        rows = (
            SysUser.query.join(SysUser.roles)
            .filter(SysUser.status == 1, SysUser.id.in_(list(active_ids)), SysRole.role_code == role_code)
            .with_entities(SysUser.id)
            .distinct()
            .all()
        )
        return len(rows)
    if role_code == "student":
        return count_student_recipients(message)
    if role_code == "admin":
        return len(active_user_ids_for_roles(["admin"]))
    if not message.contest_id:
        return len(active_user_ids_for_roles([role_code]))
    role_hint = MESSAGE_SCOPE_ROLE_HINTS.get(role_code) or {}
    scopes = role_hint.get("scopes") or set()
    if not scopes:
        return len(active_user_ids_for_roles([role_code]))
    user_ids = {
        int(item[0])
        for item in (
            ContestPermission.query.filter(
                ContestPermission.contest_id == message.contest_id,
                ContestPermission.permission_scope.in_(sorted(scopes)),
            )
            .with_entities(ContestPermission.user_id)
            .distinct()
            .all()
        )
    }
    if not user_ids:
        return 0
    rows = (
        SysUser.query.join(SysUser.roles)
        .filter(SysUser.status == 1, SysUser.id.in_(user_ids), SysRole.role_code == role_code)
        .with_entities(SysUser.id)
        .distinct()
        .all()
    )
    return len(rows)


def target_roles_for_message(message):
    roles = normalize_target_roles(message.target_role)
    return roles or list(MESSAGE_TARGET_ROLE_CODES)


def evaluate_message_delivery(message):
    failures = []
    directed_user_ids = normalize_target_user_ids(message.target_user_ids)
    if directed_user_ids:
        active_ids = active_target_user_ids(directed_user_ids)
        if not active_ids:
            failures.append({"roleCode": None, "reason": "未匹配到任何接收对象", "detail": "目标账号不存在或已停用。"})
            return 0, failures
        missing_count = len(directed_user_ids) - len(active_ids)
        if missing_count > 0:
            failures.append({"roleCode": None, "reason": "部分目标账号不可达", "detail": f"有 {missing_count} 个目标账号不存在或已停用。"})
        return len(active_ids), failures

    total_recipient_count = 0
    if message.target_scope == "contest" and not message.contest_id:
        failures.append({"roleCode": None, "reason": "指定赛事通知缺少关联赛事", "detail": "请先选择要触达的赛事。"})
        return 0, failures
    for role_code in target_roles_for_message(message):
        recipient_count = count_scoped_role_recipients(message, role_code)
        total_recipient_count += recipient_count
        if recipient_count == 0:
            role_label = (MESSAGE_SCOPE_ROLE_HINTS.get(role_code) or {}).get("label") or role_code
            failures.append(
                {
                    "roleCode": role_code,
                    "reason": f"{role_label}接收范围为空",
                    "detail": f"当前规则和条件下没有匹配到可见的{role_label}接收对象。",
                }
            )
    if total_recipient_count <= 0 and not failures:
        failures.append({"roleCode": None, "reason": "未匹配到任何接收对象", "detail": "请检查范围、赛事、角色和状态条件。"})
    return total_recipient_count, failures


def create_failure_records(message, failures):
    for item in failures:
        db.session.add(
            MessageSendFailure(
                message_id=message.id,
                role_code=item.get("roleCode"),
                reason=item.get("reason") or "发送失败",
                detail=item.get("detail"),
            )
        )


def dispatch_message(message):
    if message.id:
        MessageSendFailure.query.filter_by(message_id=message.id).delete(synchronize_session=False)
    recipient_count, failures = evaluate_message_delivery(message)
    create_failure_records(message, failures)
    message.sent_at = now_beijing() if recipient_count > 0 else None
    message.last_error = failures[0]["reason"] if failures else None
    message.send_status = "sent" if recipient_count > 0 else "failed"
    return recipient_count, failures


def create_and_dispatch_message(
    *,
    title,
    content,
    created_by,
    message_type="message",
    target_scope="contest",
    contest_id=None,
    target_roles=None,
    target_user_ids=None,
    target_status=None,
    priority="normal",
    summary=None,
    source_key=None,
):
    message = NoticeMessage.query.filter_by(source_key=source_key).order_by(NoticeMessage.id.desc()).first() if source_key else None
    if not message:
        message = NoticeMessage(created_by=created_by)
        db.session.add(message)

    message.title = title
    message.content = content
    message.message_type = message_type
    message.target_scope = target_scope
    message.contest_id = contest_id
    message.target_role = ",".join(normalize_target_roles(target_roles)) or None
    message.target_user_ids = serialize_target_user_ids(target_user_ids)
    message.target_status = (target_status or "").strip() or None
    message.priority = priority
    message.summary = (summary or "").strip() or None
    message.source_key = source_key
    message.planned_send_at = None
    message.sent_at = None
    message.last_error = None
    message.send_status = "pending"
    db.session.flush()
    dispatch_message(message)
    return message
