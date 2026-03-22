from flask import Blueprint, g, request
from sqlalchemy import and_, or_

from ..access import (
    MESSAGE_EDITOR_ROLES,
    apply_contest_scope,
    current_role_codes,
    ensure_managed_contest,
    has_any_role,
    inbox_visible_contest_ids,
    is_admin_user,
    is_student_user,
    managed_contest_ids,
    registration_requires_attachment_repair,
    resolve_bound_student,
    student_status_index,
)
from ..common import paginate_query, parse_datetime, success
from ..errors import APIError
from ..extensions import db
from ..message_service import (
    build_target_user_condition,
    dispatch_message,
    normalize_target_roles,
    target_user_ids_blank_condition,
)
from ..models import (
    AttachmentInfo,
    ContestInfo,
    ContestRegistration,
    MessageReadRecord,
    MessageSendFailure,
    MessageTodoRule,
    NoticeMessage,
    parse_message_target_roles,
)
from ..security import auth_required
from ..time_utils import now_beijing


bp = Blueprint("messages", __name__, url_prefix="/api/v1/messages")

MESSAGE_STATUSES = {"pending", "sent", "failed", "canceled"}
PRIORITIES = {"low", "normal", "high", "urgent"}
TARGET_SCOPES = {"all", "contest", "role"}
TODO_RULE_SCENES = {
    "pending_materials": "未提交原件提醒",
    "correction_required": "补正未完成提醒",
}


def parse_bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def serialize_message(message, scene="manage"):
    payload = message.to_dict(g.current_user.id)
    contest = ContestInfo.query.get(message.contest_id) if message.contest_id else None
    payload["contestName"] = contest.contest_name if contest else None
    payload["todoRuleName"] = message.todo_rule.rule_name if message.todo_rule else None
    can_manage = scene == "manage" and has_any_role(*MESSAGE_EDITOR_ROLES)
    payload["permissions"] = {
        "canEdit": can_manage and message.send_status in {"pending", "failed"},
        "canSend": can_manage and message.send_status in {"pending", "failed"},
        "canCancel": can_manage and message.send_status in {"pending", "failed"},
        "canRead": scene == "inbox" and message.send_status == "sent" and not payload["readStatus"],
    }
    return payload


def serialize_todo_rule(rule):
    payload = rule.to_dict()
    contest = ContestInfo.query.get(rule.contest_id) if rule.contest_id else None
    payload["contestName"] = contest.contest_name if contest else None
    payload["sceneLabel"] = TODO_RULE_SCENES.get(rule.scene, rule.scene)
    payload["permissions"] = {
        "canEdit": has_any_role(*MESSAGE_EDITOR_ROLES),
        "canApply": has_any_role(*MESSAGE_EDITOR_ROLES) and bool(rule.enabled_status),
    }
    return payload


def serialize_failure_record(record):
    payload = record.to_dict()
    message = record.message
    contest = ContestInfo.query.get(message.contest_id) if message and message.contest_id else None
    payload["messageTitle"] = message.title if message else None
    payload["messageStatus"] = message.send_status if message else None
    payload["contestName"] = contest.contest_name if contest else None
    payload["todoRuleName"] = message.todo_rule.rule_name if message and message.todo_rule else None
    return payload


def build_target_role_condition(role_codes, include_public=False):
    normalized_roles = normalize_target_roles(role_codes)
    conditions = []
    if include_public:
        conditions.extend([NoticeMessage.target_role.is_(None), NoticeMessage.target_role == ""])
    for role in normalized_roles:
        conditions.extend(
            [
                NoticeMessage.target_role == role,
                NoticeMessage.target_role.like(f"{role},%"),
                NoticeMessage.target_role.like(f"%,{role},%"),
                NoticeMessage.target_role.like(f"%,{role}"),
            ]
        )
    if not conditions:
        return False
    return or_(*conditions)


def apply_student_visibility(query, student):
    status_map = student_status_index(student.id)
    all_statuses = sorted({status for statuses in status_map.values() for status in statuses if status})

    query = query.filter(NoticeMessage.send_status == "sent")
    contest_ids = list(status_map.keys())
    if contest_ids:
        contest_condition = or_(NoticeMessage.contest_id.is_(None), NoticeMessage.contest_id.in_(contest_ids))
    else:
        contest_condition = NoticeMessage.contest_id.is_(None)

    status_conditions = [NoticeMessage.target_status.is_(None), NoticeMessage.target_status == ""]
    if all_statuses:
        status_conditions.append(and_(NoticeMessage.contest_id.is_(None), NoticeMessage.target_status.in_(all_statuses)))
        for contest_id, statuses in status_map.items():
            valid_statuses = [item for item in statuses if item]
            if not valid_statuses:
                continue
            status_conditions.append(and_(NoticeMessage.contest_id == contest_id, NoticeMessage.target_status.in_(valid_statuses)))
    legacy_condition = and_(
        target_user_ids_blank_condition(NoticeMessage.target_user_ids),
        build_target_role_condition(["student"], include_public=True),
        contest_condition,
        or_(*status_conditions),
    )
    direct_condition = build_target_user_condition(NoticeMessage.target_user_ids, g.current_user.id)
    return query.filter(or_(direct_condition, legacy_condition))


def apply_role_inbox_visibility(query):
    role_codes = sorted(current_role_codes())
    if not role_codes:
        return query.filter(False)
    query = query.filter(NoticeMessage.send_status == "sent")
    contest_ids = inbox_visible_contest_ids()
    if contest_ids is not None:
        contest_condition = or_(NoticeMessage.contest_id.is_(None), NoticeMessage.contest_id.in_(list(contest_ids) or [-1]))
    else:
        contest_condition = True
    legacy_condition = and_(
        target_user_ids_blank_condition(NoticeMessage.target_user_ids),
        build_target_role_condition(role_codes, include_public=True),
        contest_condition,
    )
    direct_condition = build_target_user_condition(NoticeMessage.target_user_ids, g.current_user.id)
    return query.filter(or_(direct_condition, legacy_condition))


def apply_manage_visibility(query, contest_column):
    if is_admin_user():
        return query
    return apply_contest_scope(query.filter(contest_column.isnot(None)), contest_column, managed_contest_ids())


def ensure_message_manage_access(message, error_message="当前账号无权维护该通知"):
    if is_admin_user():
        return message
    if not message.contest_id:
        raise APIError(error_message, code=403, status=200)
    ensure_managed_contest(message.contest_id, error_message)
    return message


def ensure_todo_rule_manage_access(rule, error_message="当前账号无权维护该待办规则"):
    if is_admin_user():
        return rule
    if not rule.contest_id:
        raise APIError(error_message, code=403, status=200)
    ensure_managed_contest(rule.contest_id, error_message)
    return rule


def fill_message_fields(message, payload):
    title = (payload.get("title") or message.title or "").strip()
    content = (payload.get("content") or message.content or "").strip()
    if not title or not content:
        raise APIError("消息标题和内容不能为空")
    priority = (payload.get("priority") or message.priority or "normal").strip()
    if priority not in PRIORITIES:
        raise APIError("优先级不合法")
    target_scope = (payload.get("targetScope") or message.target_scope or "all").strip() or "all"
    if target_scope not in TARGET_SCOPES:
        raise APIError("触达范围不合法")
    if "targetRoles" in payload:
        raw_target_roles = payload.get("targetRoles")
    elif "targetRole" in payload:
        raw_target_roles = payload.get("targetRole")
    else:
        raw_target_roles = message.target_role
    target_roles = normalize_target_roles(raw_target_roles)
    contest_id = payload.get("contestId")
    if contest_id in (None, ""):
        contest = ContestInfo.query.get(message.contest_id) if message.contest_id else None
    else:
        contest = ContestInfo.query.get(int(contest_id))
        if not contest:
            raise APIError("关联赛事不存在")
    if target_scope == "contest" and not contest:
        raise APIError("指定赛事通知必须关联赛事")
    if target_scope == "role" and not target_roles:
        raise APIError("指定角色通知至少选择一个目标角色")
    if not is_admin_user():
        if not contest:
            raise APIError("教师通知必须关联已分配赛事")
        ensure_managed_contest(contest.id, "当前账号无权维护该赛事通知")

    message.title = title
    message.content = content
    message.message_type = (payload.get("messageType") or message.message_type or "notice").strip() or "notice"
    message.target_scope = target_scope
    message.target_role = ",".join(target_roles) or None
    message.target_user_ids = None
    message.target_status = (payload.get("targetStatus") or message.target_status or "").strip() or None
    message.priority = priority
    message.summary = (payload.get("summary") or message.summary or "").strip() or None
    planned_send_at = parse_datetime(payload.get("plannedSendAt"), "计划发送时间") if payload.get("plannedSendAt") not in (None, "") else None
    if payload.get("plannedSendAt") in (None, ""):
        planned_send_at = message.planned_send_at
    message.planned_send_at = planned_send_at
    message.contest_id = contest.id if contest else None


def fill_todo_rule_fields(rule, payload):
    rule_name = (payload.get("ruleName") or rule.rule_name or "").strip()
    if not rule_name:
        raise APIError("规则名称不能为空")
    scene = (payload.get("scene") or rule.scene or "pending_materials").strip()
    if scene not in TODO_RULE_SCENES:
        raise APIError("待办规则场景不合法")
    priority = (payload.get("priority") or rule.priority or "normal").strip()
    if priority not in PRIORITIES:
        raise APIError("优先级不合法")
    if "targetRoles" in payload:
        raw_target_roles = payload.get("targetRoles")
    elif "targetRole" in payload:
        raw_target_roles = payload.get("targetRole")
    else:
        raw_target_roles = rule.target_role or "student,teacher"
    target_roles = normalize_target_roles(raw_target_roles)
    if not target_roles:
        target_roles = ["student", "teacher"]
    contest_id = payload.get("contestId")
    contest = None
    if contest_id not in (None, ""):
        contest = ContestInfo.query.get(int(contest_id))
        if not contest:
            raise APIError("关联赛事不存在")
    if not is_admin_user():
        if not contest:
            raise APIError("教师待办规则必须关联已分配赛事")
        ensure_managed_contest(contest.id, "当前账号无权维护该赛事待办规则")

    rule.rule_name = rule_name
    rule.scene = scene
    rule.contest_id = contest.id if contest else None
    rule.target_role = ",".join(target_roles)
    rule.priority = priority
    rule.enabled_status = 1 if parse_bool(payload.get("enabledStatus"), bool(rule.enabled_status if rule.id else True)) else 0
    rule.title_template = (payload.get("titleTemplate") or rule.title_template or "").strip() or None
    rule.summary_template = (payload.get("summaryTemplate") or rule.summary_template or "").strip() or None
    rule.content_template = (payload.get("contentTemplate") or rule.content_template or "").strip() or None
def message_visible_to_current_user(message):
    if is_admin_user():
        return True
    if is_student_user():
        student = resolve_bound_student(required=True)
        visible_ids = [item.id for item in apply_student_visibility(NoticeMessage.query, student).all()]
        return message.id in visible_ids
    visible_ids = [item.id for item in apply_role_inbox_visibility(NoticeMessage.query).all()]
    return message.id in visible_ids


def get_message_or_404(message_id):
    message = NoticeMessage.query.get_or_404(message_id)
    if not message_visible_to_current_user(message):
        raise APIError("当前账号无权访问该通知", code=403, status=200)
    return message


def find_material_attachment(material):
    if getattr(material, "attachment_id", None):
        attachment = AttachmentInfo.query.get(material.attachment_id)
        if attachment:
            return attachment
    if material.id:
        return AttachmentInfo.query.filter_by(biz_type=f"registration_material:{material.id}").order_by(AttachmentInfo.id.desc()).first()
    return None


def registration_needs_rule(rule, registration):
    has_real_materials = any(find_material_attachment(item) for item in registration.materials)
    if rule.scene == "pending_materials":
        return registration.final_status in {"submitted", "supplemented"} and (
            not has_real_materials or registration_requires_attachment_repair(registration)
        )
    if rule.scene == "correction_required":
        return registration.final_status == "correction_required"
    return False


def render_rule_template(template, fallback, context):
    content = template or fallback
    for key, value in context.items():
        content = content.replace(f"{{{key}}}", str(value or ""))
    return content.strip()


def build_rule_message_defaults(rule, registration):
    contest_name = registration.contest.contest_name if registration.contest else "当前赛事"
    student_name = registration.student.name if registration.student else "当前学生"
    latest_comment = next((item.review_comment for item in reversed(registration.materials) if item.review_comment), "") or "暂无审核意见"
    scene_name = TODO_RULE_SCENES.get(rule.scene, rule.scene)
    context = {
        "contestName": contest_name,
        "studentName": student_name,
        "projectName": registration.project_name or "未命名项目",
        "status": registration.final_status,
        "latestComment": latest_comment,
        "sceneName": scene_name,
    }
    title_fallback = f"{scene_name}：{contest_name} / {student_name}"
    summary_fallback = (
        f"{student_name} 在 {contest_name} 的报名记录仍处于“{scene_name}”阶段，请尽快处理。"
    )
    content_fallback = (
        f"赛事：{contest_name}\n"
        f"学生：{student_name}\n"
        f"项目：{registration.project_name or '未命名项目'}\n"
        f"当前状态：{registration.final_status}\n"
        f"最近意见：{latest_comment}\n"
        f"处理建议：请尽快完成材料提交或补正。"
    )
    return {
        "title": render_rule_template(rule.title_template, title_fallback, context),
        "summary": render_rule_template(rule.summary_template, summary_fallback, context),
        "content": render_rule_template(rule.content_template, content_fallback, context),
    }


def generate_rule_messages(rule):
    query = ContestRegistration.query
    if rule.contest_id:
        query = query.filter(ContestRegistration.contest_id == rule.contest_id)
    query = query.order_by(ContestRegistration.id.desc())
    registrations = [item for item in query.all() if registration_needs_rule(rule, item)]
    generated_count = 0
    for registration in registrations:
        source_key = f"todo_rule:{rule.id}:registration:{registration.id}:status:{registration.final_status}"
        message = NoticeMessage.query.filter_by(source_key=source_key).order_by(NoticeMessage.id.desc()).first()
        is_new = False
        if not message:
            message = NoticeMessage(created_by=g.current_user.id)
            db.session.add(message)
            is_new = True
        payload = build_rule_message_defaults(rule, registration)
        message.title = payload["title"]
        message.summary = payload["summary"]
        message.content = payload["content"]
        message.message_type = "todo"
        message.target_scope = "contest"
        message.contest_id = registration.contest_id
        message.target_role = rule.target_role or "student,teacher"
        message.target_status = registration.final_status
        message.priority = rule.priority
        message.planned_send_at = None
        message.source_key = source_key
        message.todo_rule_id = rule.id
        message.send_status = "pending"
        message.sent_at = None
        message.last_error = None
        db.session.flush()
        dispatch_message(message)
        generated_count += 1 if is_new or message.send_status in {"sent", "failed"} else 0
    rule.last_run_at = now_beijing()
    rule.last_generated_count = generated_count
    return generated_count


@bp.get("/todo-rules")
@auth_required(["admin", "teacher"])
def list_todo_rules():
    keyword = (request.args.get("keyword") or "").strip()
    scene = (request.args.get("scene") or "").strip()
    enabled_status = request.args.get("enabledStatus")
    query = MessageTodoRule.query
    if keyword:
        query = query.filter(MessageTodoRule.rule_name.like(f"%{keyword}%"))
    if scene:
        query = query.filter(MessageTodoRule.scene == scene)
    if enabled_status not in (None, ""):
        query = query.filter(MessageTodoRule.enabled_status == (1 if parse_bool(enabled_status) else 0))
    query = apply_manage_visibility(query, MessageTodoRule.contest_id)
    query = query.order_by(MessageTodoRule.enabled_status.desc(), MessageTodoRule.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_todo_rule(item) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.post("/todo-rules")
@auth_required(["admin", "teacher"])
def create_todo_rule():
    payload = request.get_json(silent=True) or {}
    rule = MessageTodoRule(created_by=g.current_user.id)
    fill_todo_rule_fields(rule, payload)
    db.session.add(rule)
    db.session.commit()
    return success(serialize_todo_rule(rule), message="待办规则创建成功")


@bp.put("/todo-rules/<int:rule_id>")
@auth_required(["admin", "teacher"])
def update_todo_rule(rule_id):
    rule = ensure_todo_rule_manage_access(MessageTodoRule.query.get_or_404(rule_id))
    payload = request.get_json(silent=True) or {}
    fill_todo_rule_fields(rule, payload)
    db.session.commit()
    return success(serialize_todo_rule(rule), message="待办规则更新成功")


@bp.post("/todo-rules/<int:rule_id>/apply")
@auth_required(["admin", "teacher"])
def apply_todo_rule(rule_id):
    rule = ensure_todo_rule_manage_access(MessageTodoRule.query.get_or_404(rule_id))
    if not rule.enabled_status:
        raise APIError("请先启用待办规则")
    generated_count = generate_rule_messages(rule)
    db.session.commit()
    return success({"rule": serialize_todo_rule(rule), "generatedCount": generated_count}, message="待办规则已执行")


@bp.get("/failures")
@auth_required(["admin", "teacher"])
def list_failures():
    keyword = (request.args.get("keyword") or "").strip()
    message_id = request.args.get("messageId")
    role_code = (request.args.get("roleCode") or "").strip()
    query = MessageSendFailure.query.join(NoticeMessage)
    if keyword:
        query = query.filter(
            or_(
                NoticeMessage.title.like(f"%{keyword}%"),
                MessageSendFailure.reason.like(f"%{keyword}%"),
                MessageSendFailure.detail.like(f"%{keyword}%"),
            )
        )
    if message_id:
        query = query.filter(MessageSendFailure.message_id == int(message_id))
    if role_code:
        query = query.filter(MessageSendFailure.role_code == role_code)
    query = apply_manage_visibility(query, NoticeMessage.contest_id)
    query = query.order_by(MessageSendFailure.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_failure_record(item) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.get("")
@auth_required(["admin", "teacher", "reviewer", "student"])
def list_messages():
    keyword = (request.args.get("keyword") or "").strip()
    send_status = request.args.get("sendStatus")
    message_type = (request.args.get("messageType") or "").strip()
    contest_id = request.args.get("contestId")
    target_role = (request.args.get("targetRole") or "").strip()
    target_status = (request.args.get("targetStatus") or "").strip()
    priority = (request.args.get("priority") or "").strip()
    scene = (request.args.get("scene") or "inbox").strip()

    if scene == "manage" and not has_any_role(*MESSAGE_EDITOR_ROLES):
        scene = "inbox"

    query = NoticeMessage.query
    if keyword:
        query = query.filter(
            or_(
                NoticeMessage.title.like(f"%{keyword}%"),
                NoticeMessage.summary.like(f"%{keyword}%"),
                NoticeMessage.content.like(f"%{keyword}%"),
            )
        )
    if send_status:
        query = query.filter_by(send_status=send_status)
    if message_type:
        query = query.filter_by(message_type=message_type)
    if contest_id:
        query = query.filter_by(contest_id=int(contest_id))
    if target_role and scene == "manage":
        query = query.filter(build_target_role_condition(target_role))
    if target_status and scene == "manage":
        query = query.filter_by(target_status=target_status)
    if priority:
        query = query.filter_by(priority=priority)

    if is_student_user():
        student = resolve_bound_student(required=True)
        query = apply_student_visibility(query, student)
    elif scene == "manage":
        query = apply_manage_visibility(query, NoticeMessage.contest_id)
    elif scene == "inbox":
        query = apply_role_inbox_visibility(query)

    query = query.order_by(NoticeMessage.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_message(item, scene) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.post("")
@auth_required(["admin", "teacher"])
def create_message():
    payload = request.get_json(silent=True) or {}
    message = NoticeMessage(created_by=g.current_user.id, send_status="pending")
    fill_message_fields(message, payload)
    db.session.add(message)
    db.session.commit()
    return success(serialize_message(message, "manage"), message="通知创建成功")


@bp.put("/<int:message_id>")
@auth_required(["admin", "teacher"])
def update_message(message_id):
    message = ensure_message_manage_access(NoticeMessage.query.get_or_404(message_id))
    payload = request.get_json(silent=True) or {}
    fill_message_fields(message, payload)
    message.last_error = None
    if message.send_status == "failed":
        message.send_status = "pending"
    db.session.commit()
    return success(serialize_message(message, "manage"), message="通知更新成功")


@bp.post("/<int:message_id>/send")
@auth_required(["admin", "teacher"])
def send_message(message_id):
    message = ensure_message_manage_access(NoticeMessage.query.get_or_404(message_id))
    if message.send_status == "canceled":
        raise APIError("已取消的通知不能发送")
    dispatch_message(message)
    db.session.commit()
    response_message = "通知发送成功" if message.send_status == "sent" else "通知发送失败"
    return success(serialize_message(message, "manage"), message=response_message)


@bp.post("/<int:message_id>/cancel")
@auth_required(["admin", "teacher"])
def cancel_message(message_id):
    message = ensure_message_manage_access(NoticeMessage.query.get_or_404(message_id))
    if message.send_status == "sent":
        raise APIError("已发送通知不能取消")
    message.send_status = "canceled"
    message.sent_at = None
    db.session.commit()
    return success(serialize_message(message, "manage"), message="通知已取消")


@bp.post("/<int:message_id>/read")
@auth_required(["admin", "teacher", "reviewer", "student"])
def read_message(message_id):
    message = get_message_or_404(message_id)
    if message.send_status != "sent":
        raise APIError("未发送的通知不能标记已读", code=403, status=200)
    record = MessageReadRecord.query.filter_by(message_id=message.id, user_id=g.current_user.id).first()
    if not record:
        record = MessageReadRecord(message_id=message.id, user_id=g.current_user.id)
        db.session.add(record)
    record.read_status = 1
    record.read_at = now_beijing()
    db.session.commit()
    return success(serialize_message(message, "inbox"), message="消息已读")
