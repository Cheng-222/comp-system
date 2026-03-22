from pathlib import Path

from flask import Blueprint, g, request, send_file
from sqlalchemy import case, func, or_

from ..access import (
    apply_contest_scope,
    current_contest_scopes,
    ensure_managed_contest,
    ensure_reviewable_contest,
    is_admin_user,
    is_reviewer_user,
    is_student_user,
    is_teacher_user,
    managed_contest_ids,
    reviewable_contest_ids,
)
from ..common import paginate_query, parse_datetime, success
from ..errors import APIError
from ..excel_utils import save_uploaded_attachment
from ..extensions import db
from ..models import AttachmentInfo, ContestInfo, ContestPermission, ContestRegistration, SysRole, SysUser
from ..security import auth_required


bp = Blueprint("contests", __name__, url_prefix="/api/v1/contests")

CONTEST_STATUSES = {"draft", "pending_publish", "signing_up", "reviewing", "closed", "archived"}


def serialize_user(user):
    return {
        "userId": user.id,
        "userName": user.username,
        "realName": user.real_name,
        "roleCodes": user.role_codes,
    }


def normalize_user_ids(value):
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple, set)):
        raise APIError("赛事授权配置格式不正确")
    normalized = []
    for item in value:
        if item in (None, ""):
            continue
        user_id = int(item)
        if user_id not in normalized:
            normalized.append(user_id)
    return normalized


def collect_permission_index(contest_ids):
    if not contest_ids:
        return {}
    rows = (
        ContestPermission.query.filter(ContestPermission.contest_id.in_(contest_ids))
        .order_by(ContestPermission.contest_id.asc(), ContestPermission.id.asc())
        .all()
    )
    index = {}
    for contest_id in contest_ids:
        index[contest_id] = {
            "managerUsers": [],
            "reviewerUsers": [],
            "managerUserIds": [],
            "reviewerUserIds": [],
            "currentUserScopes": [],
        }
    current_user_id = getattr(getattr(g, "current_user", None), "id", None)
    for item in rows:
        payload = index.setdefault(
            item.contest_id,
            {
                "managerUsers": [],
                "reviewerUsers": [],
                "managerUserIds": [],
                "reviewerUserIds": [],
                "currentUserScopes": [],
            },
        )
        if current_user_id and item.user_id == current_user_id and item.permission_scope not in payload["currentUserScopes"]:
            payload["currentUserScopes"].append(item.permission_scope)
        if item.permission_scope == "manage" and item.user_id not in payload["managerUserIds"]:
            payload["managerUsers"].append(serialize_user(item.user))
            payload["managerUserIds"].append(item.user_id)
        if item.permission_scope == "review" and item.user_id not in payload["reviewerUserIds"]:
            payload["reviewerUsers"].append(serialize_user(item.user))
            payload["reviewerUserIds"].append(item.user_id)
    return index


def ensure_contest_view_access(contest_id, message="当前账号无权访问该赛事"):
    if is_teacher_user():
        ensure_managed_contest(contest_id, message)
    elif is_reviewer_user():
        ensure_reviewable_contest(contest_id, message)
    return ContestInfo.query.get_or_404(contest_id)


def ensure_contest_manage_access(contest_id, message="当前账号无权维护该赛事"):
    if not is_admin_user():
        ensure_managed_contest(contest_id, message)
    return ContestInfo.query.get_or_404(contest_id)


def find_rule_attachment(contest):
    if contest.rule_attachment_id:
        attachment = AttachmentInfo.query.get(contest.rule_attachment_id)
        if attachment:
            return attachment
    if contest.rule_attachment_name:
        attachment = AttachmentInfo.query.filter(
            AttachmentInfo.file_name == contest.rule_attachment_name,
            AttachmentInfo.biz_type.in_(["contest_rule", f"contest_rule:{contest.id}"]),
        ).order_by(AttachmentInfo.id.desc()).first()
        if attachment:
            return attachment
    return None


def serialize_contest(contest, stats=None, permission_index=None):
    payload = contest.to_dict()
    stats = stats or {}
    permission_index = permission_index or {}
    assignment = permission_index.get(contest.id, {})
    attachment = find_rule_attachment(contest)
    if attachment:
        payload["ruleAttachmentName"] = attachment.file_name
        payload["ruleAttachmentId"] = attachment.id
        payload["ruleAttachmentExt"] = attachment.file_ext
        payload["ruleAttachmentSize"] = attachment.file_size
        payload["ruleAttachmentUploadedAt"] = attachment.uploaded_at.isoformat() if attachment.uploaded_at else None
    payload["registrationCount"] = stats.get(contest.id, {}).get("registrationCount", 0)
    payload["approvedCount"] = stats.get(contest.id, {}).get("approvedCount", 0)
    current_scopes = set(assignment.get("currentUserScopes") or current_contest_scopes(contest.id))
    can_manage = is_admin_user() or "manage" in current_scopes
    payload["managerUsers"] = assignment.get("managerUsers", [])
    payload["reviewerUsers"] = assignment.get("reviewerUsers", [])
    payload["managerUserIds"] = assignment.get("managerUserIds", [])
    payload["reviewerUserIds"] = assignment.get("reviewerUserIds", [])
    payload["currentUserScopes"] = sorted(current_scopes)
    payload["permissions"] = {
        "canView": True,
        "canEdit": can_manage and contest.status != "archived",
        "canPublish": can_manage and contest.status in {"draft", "pending_publish", "closed"},
        "canClose": can_manage and contest.status in {"signing_up", "reviewing"},
        "canArchive": can_manage and contest.status in {"closed", "reviewing"},
        "canUploadRuleAttachment": can_manage and contest.status != "archived",
        "canDownloadRuleAttachment": bool(attachment and attachment.file_path),
        "canPreviewRuleAttachment": bool(attachment and attachment.file_path),
    }
    return payload


def ensure_transition_allowed(contest, target_status):
    transitions = {
        "draft": {"pending_publish", "signing_up", "closed"},
        "pending_publish": {"draft", "signing_up", "closed"},
        "signing_up": {"reviewing", "closed"},
        "reviewing": {"closed", "archived"},
        "closed": {"signing_up", "archived"},
        "archived": set(),
    }
    if target_status == contest.status:
        return
    allowed = transitions.get(contest.status, set())
    if target_status not in allowed:
        raise APIError(f"赛事当前状态不支持变更为 {target_status}")


def collect_contest_stats(contest_ids):
    if not contest_ids:
        return {}
    rows = (
        db.session.query(
            ContestRegistration.contest_id,
            func.count(ContestRegistration.id).label("registration_count"),
            func.sum(case((ContestRegistration.final_status == "approved", 1), else_=0)).label("approved_count"),
        )
        .filter(ContestRegistration.contest_id.in_(contest_ids))
        .group_by(ContestRegistration.contest_id)
        .all()
    )
    return {
        contest_id: {
            "registrationCount": int(registration_count or 0),
            "approvedCount": int(approved_count or 0),
        }
        for contest_id, registration_count, approved_count in rows
    }


def query_assignable_users(role_code):
    return (
        SysUser.query.join(SysUser.roles)
        .filter(SysRole.role_code == role_code, SysUser.status == 1)
        .order_by(SysUser.id.asc())
        .all()
    )


def sync_contest_permissions(contest, payload):
    manager_user_ids = normalize_user_ids(payload.get("managerUserIds")) if "managerUserIds" in payload else None
    reviewer_user_ids = normalize_user_ids(payload.get("reviewerUserIds")) if "reviewerUserIds" in payload else None
    if manager_user_ids is None and reviewer_user_ids is None:
        return
    if not is_admin_user():
        raise APIError("仅管理员可配置赛事授权", code=403, status=200)

    if manager_user_ids is not None:
        teacher_ids = {item.id for item in query_assignable_users("teacher")}
        invalid = [item for item in manager_user_ids if item not in teacher_ids]
        if invalid:
            raise APIError("负责教师配置不合法")
        ContestPermission.query.filter(
            ContestPermission.contest_id == contest.id,
            ContestPermission.permission_scope.in_(["manage", "result"]),
        ).delete(synchronize_session=False)
        for user_id in manager_user_ids:
            db.session.add(ContestPermission(contest_id=contest.id, user_id=user_id, permission_scope="manage"))
            db.session.add(ContestPermission(contest_id=contest.id, user_id=user_id, permission_scope="result"))

    if reviewer_user_ids is not None:
        reviewer_ids = {item.id for item in query_assignable_users("reviewer")}
        invalid = [item for item in reviewer_user_ids if item not in reviewer_ids]
        if invalid:
            raise APIError("审核人配置不合法")
        ContestPermission.query.filter(
            ContestPermission.contest_id == contest.id,
            ContestPermission.permission_scope == "review",
        ).delete(synchronize_session=False)
        for user_id in reviewer_user_ids:
            db.session.add(ContestPermission(contest_id=contest.id, user_id=user_id, permission_scope="review"))


def fill_contest_fields(contest, payload):
    contest.contest_name = (payload.get("contestName") or contest.contest_name or "").strip()
    contest.contest_level = (payload.get("contestLevel") or contest.contest_level or "").strip()
    contest.organizer = (payload.get("organizer") or contest.organizer or "").strip()
    contest.subject_category = (payload.get("subjectCategory") or contest.subject_category or "").strip() or None
    contest.undertaker = (payload.get("undertaker") or contest.undertaker or "").strip() or None
    contest.target_students = (payload.get("targetStudents") or contest.target_students or "").strip() or None
    contest.contact_name = (payload.get("contactName") or contest.contact_name or "").strip() or None
    contest.contact_mobile = (payload.get("contactMobile") or contest.contact_mobile or "").strip() or None
    contest.location = (payload.get("location") or contest.location or "").strip() or None
    contest.description = (payload.get("description") or contest.description or "").strip() or None
    contest.contest_year = int(payload.get("contestYear")) if payload.get("contestYear") not in (None, "") else None
    sign_up_start = parse_datetime(payload.get("signUpStart"), "报名开始时间")
    sign_up_end = parse_datetime(payload.get("signUpEnd"), "报名结束时间")
    contest_date = parse_datetime(payload.get("contestDate"), "比赛时间")
    contest.sign_up_start = sign_up_start if payload.get("signUpStart") not in (None, "") else contest.sign_up_start
    contest.sign_up_end = sign_up_end if payload.get("signUpEnd") not in (None, "") else contest.sign_up_end
    contest.contest_date = contest_date if payload.get("contestDate") not in (None, "") else contest.contest_date
    status = payload.get("status")
    if status:
        if status not in CONTEST_STATUSES:
            raise APIError("赛事状态不合法")
        contest.status = status
    contest.material_requirements = (payload.get("materialRequirements") or contest.material_requirements or "").strip() or None
    contest.quota_limit = int(payload.get("quotaLimit") or contest.quota_limit or 0)
    contest.rule_attachment_name = (payload.get("ruleAttachmentName") or contest.rule_attachment_name or "").strip() or None
    if not all([contest.contest_name, contest.contest_level, contest.organizer]):
        raise APIError("赛事名称、级别、主办单位不能为空")


@bp.get("")
@auth_required(["admin", "teacher", "reviewer", "student"])
def list_contests():
    keyword = (request.args.get("keyword") or "").strip()
    status = request.args.get("status")
    contest_level = (request.args.get("contestLevel") or "").strip()
    subject_category = (request.args.get("subjectCategory") or "").strip()
    contest_year = request.args.get("contestYear")

    query = ContestInfo.query
    if is_teacher_user():
        query = apply_contest_scope(query, ContestInfo.id, managed_contest_ids())
    elif is_reviewer_user():
        query = apply_contest_scope(query, ContestInfo.id, reviewable_contest_ids())
    if keyword:
        query = query.filter(
            or_(
                ContestInfo.contest_name.like(f"%{keyword}%"),
                ContestInfo.organizer.like(f"%{keyword}%"),
                ContestInfo.contest_level.like(f"%{keyword}%"),
                ContestInfo.subject_category.like(f"%{keyword}%"),
                ContestInfo.undertaker.like(f"%{keyword}%"),
            )
        )
    if status:
        query = query.filter(ContestInfo.status == status)
    if contest_level:
        query = query.filter(ContestInfo.contest_level == contest_level)
    if subject_category:
        query = query.filter(ContestInfo.subject_category == subject_category)
    if contest_year not in (None, ""):
        query = query.filter(ContestInfo.contest_year == int(contest_year))

    query = query.order_by(ContestInfo.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    stats = collect_contest_stats([item.id for item in items])
    permission_index = collect_permission_index([item.id for item in items])
    return success({"list": [serialize_contest(item, stats, permission_index) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.get("/<int:contest_id>")
@auth_required(["admin", "teacher", "reviewer", "student"])
def get_contest(contest_id):
    contest = ensure_contest_view_access(contest_id, "当前账号无权访问该赛事")
    stats = collect_contest_stats([contest.id])
    permission_index = collect_permission_index([contest.id])
    payload = serialize_contest(contest, stats, permission_index)
    if is_student_user():
        payload["recentRegistrations"] = []
    else:
        recent_registrations = ContestRegistration.query.filter_by(contest_id=contest.id).order_by(ContestRegistration.id.desc()).limit(8).all()
        payload["recentRegistrations"] = [item.to_dict() for item in recent_registrations]
    return success(payload)


@bp.post("")
@auth_required(["admin", "teacher"])
def create_contest():
    payload = request.get_json(silent=True) or {}
    contest = ContestInfo()
    fill_contest_fields(contest, payload)
    if contest.status not in CONTEST_STATUSES:
        contest.status = "draft"
    db.session.add(contest)
    db.session.flush()
    if is_admin_user():
        sync_contest_permissions(contest, payload)
    else:
        db.session.add(ContestPermission(contest_id=contest.id, user_id=g.current_user.id, permission_scope="manage"))
        db.session.add(ContestPermission(contest_id=contest.id, user_id=g.current_user.id, permission_scope="result"))
    db.session.commit()
    permission_index = collect_permission_index([contest.id])
    return success(serialize_contest(contest, permission_index=permission_index), message="赛事创建成功")


@bp.put("/<int:contest_id>")
@auth_required(["admin", "teacher"])
def update_contest(contest_id):
    contest = ensure_contest_manage_access(contest_id)
    payload = request.get_json(silent=True) or {}
    fill_contest_fields(contest, payload)
    sync_contest_permissions(contest, payload)
    db.session.commit()
    permission_index = collect_permission_index([contest.id])
    return success(serialize_contest(contest, permission_index=permission_index), message="赛事更新成功")


@bp.post("/<int:contest_id>/publish")
@auth_required(["admin", "teacher"])
def publish_contest(contest_id):
    contest = ensure_contest_manage_access(contest_id)
    ensure_transition_allowed(contest, "signing_up")
    contest.status = "signing_up"
    db.session.commit()
    permission_index = collect_permission_index([contest.id])
    return success(serialize_contest(contest, permission_index=permission_index), message="赛事已发布")


@bp.post("/<int:contest_id>/status")
@auth_required(["admin", "teacher"])
def change_contest_status(contest_id):
    contest = ensure_contest_manage_access(contest_id)
    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or "").strip()
    if status not in CONTEST_STATUSES:
        raise APIError("赛事状态不合法")
    ensure_transition_allowed(contest, status)
    contest.status = status
    db.session.commit()
    permission_index = collect_permission_index([contest.id])
    return success(serialize_contest(contest, permission_index=permission_index), message="赛事状态更新成功")


@bp.post("/<int:contest_id>/rule-attachment")
@auth_required(["admin", "teacher"])
def upload_rule_attachment(contest_id):
    contest = ensure_contest_manage_access(contest_id)
    file = request.files.get("file")
    if not file or not getattr(file, "filename", None):
        raise APIError("请上传真实规则附件")
    attachment = save_uploaded_attachment(file, f"contest_rule:{contest.id}", g.current_user.id, subdir="contests")
    contest.rule_attachment_name = attachment.file_name
    contest.rule_attachment_id = attachment.id
    db.session.commit()
    permission_index = collect_permission_index([contest.id])
    return success(serialize_contest(contest, permission_index=permission_index), message="规则附件上传成功")


@bp.post("/<int:contest_id>/rule-attachment/remove")
@auth_required(["admin", "teacher"])
def remove_rule_attachment(contest_id):
    contest = ensure_contest_manage_access(contest_id)
    contest.rule_attachment_name = None
    contest.rule_attachment_id = None
    db.session.commit()
    permission_index = collect_permission_index([contest.id])
    return success(serialize_contest(contest, permission_index=permission_index), message="规则附件已移除")


@bp.post("/<int:contest_id>/rule-attachment/download")
@auth_required(["admin", "teacher", "reviewer", "student"])
def download_rule_attachment(contest_id):
    contest = ensure_contest_view_access(contest_id, "当前账号无权下载该赛事规则附件")
    attachment = find_rule_attachment(contest)
    if not attachment or not attachment.file_path or not Path(attachment.file_path).exists():
        raise APIError("规则附件不存在")
    return send_file(attachment.file_path, as_attachment=True, download_name=attachment.file_name)


@bp.post("/<int:contest_id>/rule-attachment/preview")
@auth_required(["admin", "teacher", "reviewer", "student"])
def preview_rule_attachment(contest_id):
    contest = ensure_contest_view_access(contest_id, "当前账号无权查看该赛事规则附件")
    attachment = find_rule_attachment(contest)
    if not attachment or not attachment.file_path or not Path(attachment.file_path).exists():
        raise APIError("规则附件不存在")
    return send_file(attachment.file_path, as_attachment=False, download_name=attachment.file_name)


@bp.get("/permission-users")
@auth_required(["admin"])
def list_permission_users():
    return success(
        {
            "teachers": [serialize_user(item) for item in query_assignable_users("teacher")],
            "reviewers": [serialize_user(item) for item in query_assignable_users("reviewer")],
        }
    )
