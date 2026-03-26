import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, g, request, send_file
from sqlalchemy import or_

from ..access import (
    CONTEST_RESULT_SCOPES,
    RESULT_EDITOR_ROLES,
    apply_contest_scope,
    can_view_result_record,
    ensure_result_access,
    ensure_result_visible_contest,
    has_contest_scope,
    has_any_role,
    is_admin_user,
    is_student_user,
    result_visible_contest_ids,
    resolve_bound_student,
)
from ..common import paginate_query, parse_datetime, success
from ..data_scope import apply_college_scope, selected_college_names, student_in_college_scope
from ..errors import APIError
from ..excel_utils import XLSX_MIMETYPE, create_export_file, create_workbook_bytes, parse_tabular_file, save_uploaded_attachment
from ..extensions import db
from ..models import (
    AttachmentInfo,
    ContestInfo,
    ContestRegistration,
    ContestResult,
    ExportTask,
    ImportTask,
    RegistrationFlowLog,
    RegistrationMaterial,
    StudentInfo,
    SysUser,
)
from ..security import auth_required
from ..time_utils import now_beijing


bp = Blueprint("results", __name__, url_prefix="/api/v1")


RESULT_STATUSES = {"pending", "awarded", "participated", "archived"}
STATISTICS_EXPORT_TASK_TYPES = {"award_statistics_export", "archive_export"}
ACTIVE_EXPORT_TASK_STATUSES = {"pending", "processing"}
EXPORT_TASK_META = {
    "award_statistics_export": {"label": "获奖统计报表", "filename": "获奖统计报表.xlsx"},
    "archive_export": {"label": "赛后归档资料", "filename": "赛后归档资料.xlsx"},
}
EXPORT_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="competition-export")


def export_task_meta(task_type):
    task_key = str(task_type or "").strip()
    meta = EXPORT_TASK_META.get(task_key)
    if not meta:
        raise APIError("不支持的导出任务类型")
    return meta


def export_task_filename(task_type):
    return export_task_meta(task_type)["filename"]


def normalize_export_contest_id(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise APIError("赛事编号格式错误") from error


def export_task_payload(task):
    try:
        payload = json.loads(task.request_payload_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def export_task_label(task_type):
    return export_task_meta(task_type)["label"]


def export_task_name(task_type, contest_id=None):
    contest_name = None
    if contest_id:
        contest = db.session.get(ContestInfo, int(contest_id))
        contest_name = contest.contest_name if contest else None
    base_name = export_task_label(task_type)
    return f"{contest_name} / {base_name}" if contest_name else base_name



def parse_float(value, field_name):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise APIError(f"{field_name} 格式错误") from error



def parse_int(value, field_name):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise APIError(f"{field_name} 格式错误") from error


def get_record_value(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_bool(value, default=True):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def find_contest(record):
    contest_id = get_record_value(record, "contestId", "赛事ID")
    contest_name = (get_record_value(record, "contestName", "赛事名称") or "").strip()
    contest = None
    if contest_id:
        contest = ContestInfo.query.get(int(contest_id))
    elif contest_name:
        contest = ContestInfo.query.filter_by(contest_name=contest_name).first()
    if not contest:
        raise APIError("结果导入中的赛事不存在")
    return contest


def resolve_student(record):
    student_id = get_record_value(record, "studentId", "学生ID")
    student_no = str(get_record_value(record, "studentNo", "学号") or "").strip()
    student = None
    if student_id:
        student = StudentInfo.query.get(int(student_id))
    elif student_no:
        student = StudentInfo.query.filter_by(student_no=student_no).first()
    if not student:
        raise APIError("结果导入中的学生不存在")
    return student


def find_certificate_attachment(result):
    attachment = AttachmentInfo.query.filter_by(biz_type=f"certificate:{result.id}").order_by(AttachmentInfo.id.desc()).first()
    if attachment:
        return attachment
    if result.certificate_attachment_name:
        return AttachmentInfo.query.filter(
            AttachmentInfo.file_name == result.certificate_attachment_name,
            AttachmentInfo.biz_type.in_(["certificate", f"certificate:{result.id}"]),
        ).order_by(AttachmentInfo.id.desc()).first()
    return None


def serialize_result(item):
    contest = ContestInfo.query.get(item.contest_id)
    student = StudentInfo.query.get(item.student_id)
    attachment = find_certificate_attachment(item)
    payload = item.to_dict()
    payload.update({
        "contestName": contest.contest_name if contest else None,
        "contestLevel": contest.contest_level if contest else None,
        "studentNo": student.student_no if student else None,
        "studentName": student.name if student else None,
        "college": student.college if student else None,
        "major": student.major if student else None,
        "certificateAttachmentId": attachment.id if attachment else None,
        "certificateAttachmentExt": attachment.file_ext if attachment else None,
        "certificateAttachmentSize": attachment.file_size if attachment else None,
        "certificateUploadedAt": attachment.uploaded_at.isoformat() if attachment and attachment.uploaded_at else None,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
    })
    owned_by_current_user = False
    if is_student_user():
        owned_by_current_user = resolve_bound_student(required=True).id == item.student_id
    has_certificate = bool(attachment and attachment.file_path)
    payload["permissions"] = {
        "canView": True,
        "ownedByCurrentUser": owned_by_current_user,
        "canEdit": has_any_role(*RESULT_EDITOR_ROLES),
        "canUploadCertificate": has_any_role(*RESULT_EDITOR_ROLES) and can_view_result_record(item) and item.result_status in {"awarded", "archived"},
        "canDownloadCertificate": has_certificate and (
            is_admin_user() or
            (has_any_role("teacher") and can_view_result_record(item)) or
            owned_by_current_user
        ),
        "canPreviewCertificate": has_certificate and (
            is_admin_user() or
            (has_any_role("teacher") and can_view_result_record(item)) or
            owned_by_current_user
        ),
    }
    return payload


def serialize_export_task(task):
    attachment = db.session.get(AttachmentInfo, task.file_id) if task.file_id else None
    creator = db.session.get(SysUser, task.created_by) if task.created_by else None
    payload = export_task_payload(task)
    contest_id = normalize_export_contest_id(payload.get("contestId"))
    return {
        "id": task.id,
        "taskType": task.task_type,
        "taskName": task.task_name or export_task_name(task.task_type, contest_id),
        "status": task.status,
        "progress": int(task.progress or 0),
        "currentStep": task.current_step or "",
        "errorMessage": task.error_message or "",
        "fileId": task.file_id,
        "fileName": attachment.file_name if attachment else None,
        "fileSize": attachment.file_size if attachment else 0,
        "contestId": contest_id,
        "createdBy": task.created_by,
        "createdByName": creator.real_name if creator else None,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
        "startedAt": task.started_at.isoformat() if task.started_at else None,
        "finishedAt": task.finished_at.isoformat() if task.finished_at else None,
        "updatedAt": task.updated_at.isoformat() if task.updated_at else None,
        "retryCount": int(task.retry_count or 0),
        "canRetry": task.status == "failed",
    }


def ensure_export_task_access(task):
    if task.task_type not in STATISTICS_EXPORT_TASK_TYPES:
        raise APIError("导出记录不存在", status=404)
    if not is_admin_user(g.current_user) and int(task.created_by or 0) != int(g.current_user.id):
        raise APIError("当前账号无权下载该导出文件", code=403, status=200)
    return task


def ensure_export_task_downloadable(task):
    ensure_export_task_access(task)
    if task.status != "completed":
        raise APIError("导出任务尚未完成", code=400, status=200)
    return task


def ensure_export_task_retryable(task):
    ensure_export_task_access(task)
    if task.status != "failed":
        raise APIError("仅失败任务允许重试", code=400, status=200)
    return task


def validate_export_task_scope(task_type, contest_id, user):
    if contest_id and not is_admin_user(user) and not has_contest_scope(contest_id, CONTEST_RESULT_SCOPES, user=user):
        if task_type == "archive_export":
            raise APIError("当前账号无权导出该赛事归档", code=403, status=200)
        raise APIError("当前账号无权导出该赛事统计", code=403, status=200)


def award_statistics_sheets(payload):
    return [
        {
            "title": "统计概览",
            "headers": ["参与人数", "成绩记录", "获奖人数", "未获奖人数", "证书归档数"],
            "rows": [[payload["summary"]["participantCount"], payload["summary"]["resultCount"], payload["summary"]["awardedCount"], payload["summary"]["unawardedCount"], payload["summary"]["certificateCount"]]],
        },
        {
            "title": "获奖等级分布",
            "headers": ["获奖等级", "数量"],
            "rows": [[item["awardLevel"], item["count"]] for item in payload["awardLevels"]],
        },
        {
            "title": "赛事维度统计",
            "headers": ["赛事", "成绩数", "获奖数", "证书数"],
            "rows": [[item["contestName"], item["resultCount"], item["awardedCount"], item["certificateCount"]] for item in payload["contestStats"]],
        },
        {
            "title": "学院维度统计",
            "headers": ["学院", "参与数", "获奖数"],
            "rows": [[item["college"], item["participantCount"], item["awardedCount"]] for item in payload["collegeStats"]],
        },
        {
            "title": "未获奖名单",
            "headers": ["赛事", "学号", "学生", "学院"],
            "rows": [[item["contestName"], item["studentNo"], item["studentName"], item["college"]] for item in payload["unawardedList"]],
        },
    ]


def delete_task_attachment(attachment_id):
    if not attachment_id:
        return
    attachment = db.session.get(AttachmentInfo, int(attachment_id))
    if not attachment:
        return
    attachment_path = Path(attachment.file_path or "")
    if attachment_path.exists():
        attachment_path.unlink(missing_ok=True)
    db.session.delete(attachment)
    db.session.flush()


def build_export_task_content(task_type, contest_id, user):
    validate_export_task_scope(task_type, contest_id, user)
    allowed_contest_ids = None if is_admin_user(user) else result_visible_contest_ids(user=user)
    if task_type == "archive_export":
        return create_workbook_bytes(build_archive_sheets(contest_id, allowed_contest_ids, user=user))
    payload = build_statistics_payload(contest_id, allowed_contest_ids, user=user)
    return create_workbook_bytes(award_statistics_sheets(payload))


def execute_export_task(app, task_id):
    with app.app_context():
        try:
            task = db.session.get(ExportTask, int(task_id))
            if task is None:
                return
            user = db.session.get(SysUser, task.created_by) if task.created_by else None
            if user is None or int(user.status or 0) != 1:
                raise APIError("导出任务创建人不存在或已停用")

            payload = export_task_payload(task)
            contest_id = normalize_export_contest_id(payload.get("contestId"))
            task.task_name = export_task_name(task.task_type, contest_id)
            task.status = "processing"
            task.progress = 10
            task.current_step = "校验导出范围"
            task.error_message = ""
            task.started_at = now_beijing()
            task.finished_at = None
            db.session.commit()

            task.progress = 45
            task.current_step = "汇总导出数据"
            db.session.commit()
            content = build_export_task_content(task.task_type, contest_id, user)

            task.progress = 80
            task.current_step = "写入导出文件"
            db.session.commit()

            if task.file_id:
                delete_task_attachment(task.file_id)
                task.file_id = None
                db.session.commit()

            attachment, _, _ = create_export_file(export_task_filename(task.task_type), content, task.task_type, task.created_by, create_task=False)
            task.file_id = attachment.id
            task.status = "completed"
            task.progress = 100
            task.current_step = "导出完成"
            task.error_message = ""
            task.finished_at = now_beijing()
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            task = db.session.get(ExportTask, int(task_id))
            if task is not None:
                task.status = "failed"
                task.progress = 0
                task.current_step = "导出失败"
                task.error_message = str(error)[:500]
                task.finished_at = now_beijing()
                db.session.commit()
        finally:
            db.session.remove()


def enqueue_export_task(task_id, app=None):
    app_obj = app or current_app._get_current_object()
    EXPORT_TASK_EXECUTOR.submit(execute_export_task, app_obj, int(task_id))


def recover_pending_export_tasks(app=None):
    app_obj = app or current_app._get_current_object()
    recoverable_tasks = ExportTask.query.filter(
        ExportTask.task_type.in_(sorted(STATISTICS_EXPORT_TASK_TYPES)),
        ExportTask.status.in_(sorted(ACTIVE_EXPORT_TASK_STATUSES)),
    ).order_by(ExportTask.id.asc()).all()
    task_ids = []
    for task in recoverable_tasks:
        if task.file_id:
            delete_task_attachment(task.file_id)
            task.file_id = None
        task.status = "pending"
        task.progress = 0
        task.current_step = "等待恢复执行"
        task.error_message = ""
        task.started_at = None
        task.finished_at = None
        task_ids.append(int(task.id))
    if task_ids:
        db.session.commit()
        for task_id in task_ids:
            enqueue_export_task(task_id, app_obj)
    return task_ids


def create_async_export_task(task_type, creator_id, contest_id=None):
    task = ExportTask(
        task_type=task_type,
        task_name=export_task_name(task_type, contest_id),
        status="pending",
        progress=0,
        current_step="等待执行",
        error_message="",
        request_payload_json=json.dumps({"contestId": contest_id}, ensure_ascii=False),
        retry_count=0,
        created_by=creator_id,
    )
    db.session.add(task)
    db.session.commit()
    enqueue_export_task(task.id)
    db.session.refresh(task)
    return task


def collect_results_query(params):
    keyword = (params.get("keyword") or "").strip()
    contest_id = params.get("contestId")
    result_status = params.get("resultStatus")
    award_level = params.get("awardLevel")
    has_certificate = params.get("hasCertificate")

    query = ContestResult.query
    if contest_id:
        query = query.filter(ContestResult.contest_id == int(contest_id))
    if result_status:
        query = query.filter(ContestResult.result_status == result_status)
    if award_level:
        query = query.filter(ContestResult.award_level == award_level)
    if has_certificate not in (None, ""):
        has_certificate = str(has_certificate).strip().lower() in {"1", "true", "yes", "y", "on"}
        query = query.filter(ContestResult.certificate_attachment_name.isnot(None) if has_certificate else ContestResult.certificate_attachment_name.is_(None))

    if keyword:
        student_ids = [
            item.id
            for item in StudentInfo.query.filter(
                or_(
                    StudentInfo.name.like(f"%{keyword}%"),
                    StudentInfo.student_no.like(f"%{keyword}%"),
                    StudentInfo.college.like(f"%{keyword}%"),
                )
            ).all()
        ]
        contest_ids = [item.id for item in ContestInfo.query.filter(ContestInfo.contest_name.like(f"%{keyword}%")).all()]
        query = query.filter(or_(ContestResult.student_id.in_(student_ids or [-1]), ContestResult.contest_id.in_(contest_ids or [-1])))
    return query


def fill_result_fields(result, payload):
    award_level = str(payload.get("awardLevel") or result.award_level or "").strip() or None
    result_status = str(payload.get("resultStatus") or result.result_status or "pending").strip() or "pending"
    if result_status not in RESULT_STATUSES:
        raise APIError("成绩状态不合法")
    result.award_level = award_level
    result.result_status = result_status
    result.score = parse_float(payload.get("score"), "成绩分数") if payload.get("score") not in (None, "") else result.score
    result.ranking = parse_int(payload.get("ranking"), "名次") if payload.get("ranking") not in (None, "") else result.ranking
    result.certificate_no = str(payload.get("certificateNo") or result.certificate_no or "").strip() or None
    result.archive_remark = str(payload.get("archiveRemark") or result.archive_remark or "").strip() or None
    if payload.get("confirmedAt") in (None, ""):
        result.confirmed_at = result.confirmed_at or now_beijing()
    else:
        result.confirmed_at = parse_datetime(payload.get("confirmedAt"), "成绩确认时间")


def build_statistics_payload(contest_id=None, allowed_contest_ids=None, user=None):
    actor = user or getattr(g, "current_user", None)
    results_query = ContestResult.query.join(StudentInfo, ContestResult.student_id == StudentInfo.id)
    approved_registration_query = ContestRegistration.query.join(StudentInfo, ContestRegistration.student_id == StudentInfo.id).filter(ContestRegistration.final_status.in_(["approved", "supplemented", "reviewing"]))
    if allowed_contest_ids is not None:
        results_query = apply_contest_scope(results_query, ContestResult.contest_id, allowed_contest_ids)
        approved_registration_query = apply_contest_scope(approved_registration_query, ContestRegistration.contest_id, allowed_contest_ids)
    college_names = None if is_admin_user(actor) else selected_college_names(actor)
    if college_names is not None:
        results_query = apply_college_scope(results_query, StudentInfo.college, actor)
        approved_registration_query = apply_college_scope(approved_registration_query, StudentInfo.college, actor)
    if contest_id:
        results_query = results_query.filter(ContestResult.contest_id == int(contest_id))
        approved_registration_query = approved_registration_query.filter(ContestRegistration.contest_id == int(contest_id))
    results = results_query.order_by(ContestResult.id.desc()).all()

    contest_map = {item.id: item for item in ContestInfo.query.all()}
    student_map = {item.id: item for item in StudentInfo.query.all()}
    approved_registration_count = approved_registration_query.count()

    award_levels = {}
    contest_stats = {}
    college_stats = {}
    unawarded_list = []
    awarded_count = 0
    certificate_count = 0

    for item in results:
        student = student_map.get(item.student_id)
        contest = contest_map.get(item.contest_id)
        # 判断是否获奖：优先检查 result_status，其次检查 award_level
        is_awarded = item.result_status == "awarded" or bool(item.award_level)
        level_key = item.award_level or ("已获奖" if is_awarded else "未获奖")
        award_levels[level_key] = award_levels.get(level_key, 0) + 1
        if is_awarded:
            awarded_count += 1
        else:
            unawarded_list.append(
                {
                    "contestName": contest.contest_name if contest else "未知赛事",
                    "studentNo": student.student_no if student else None,
                    "studentName": student.name if student else "未知学生",
                    "college": student.college if student else "未知学院",
                }
            )
        if item.certificate_attachment_name:
            certificate_count += 1

        contest_entry = contest_stats.setdefault(
            item.contest_id,
            {
                "contestId": item.contest_id,
                "contestName": contest.contest_name if contest else "未知赛事",
                "resultCount": 0,
                "awardedCount": 0,
                "certificateCount": 0,
            },
        )
        contest_entry["resultCount"] += 1
        if is_awarded:
            contest_entry["awardedCount"] += 1
        if item.certificate_attachment_name:
            contest_entry["certificateCount"] += 1

        college_name = student.college if student else "未知学院"
        college_entry = college_stats.setdefault(
            college_name,
            {
                "college": college_name,
                "participantCount": 0,
                "awardedCount": 0,
            },
        )
        college_entry["participantCount"] += 1
        if is_awarded:
            college_entry["awardedCount"] += 1

    return {
        "summary": {
            "participantCount": max(len(results), approved_registration_count),
            "resultCount": len(results),
            "awardedCount": awarded_count,
            "unawardedCount": max(len(results) - awarded_count, 0),
            "certificateCount": certificate_count,
        },
        "awardLevels": [{"awardLevel": key, "count": value} for key, value in award_levels.items()],
        "contestStats": list(contest_stats.values()),
        "collegeStats": list(college_stats.values()),
        "unawardedList": unawarded_list,
    }


def serialize_result_detail(item):
    payload = serialize_result(item)
    attachment = find_certificate_attachment(item)
    payload["certificateFilePath"] = attachment.file_path if attachment else None
    if is_admin_user():
        registration = ContestRegistration.query.filter_by(contest_id=item.contest_id, student_id=item.student_id).first()
        payload["registration"] = registration.to_dict(with_details=True) if registration else None
    else:
        payload["registration"] = None
    return payload


def upsert_result(record, overwrite):
    contest = find_contest(record)
    if not is_admin_user():
        ensure_result_visible_contest(contest.id, "当前账号无权导入该赛事成绩")
    student = resolve_student(record)
    if not is_admin_user() and not student_in_college_scope(student, g.current_user):
        raise APIError("当前数据权限不允许导入该学院学生成绩")
    result_status = str(get_record_value(record, "resultStatus", "结果状态") or "awarded").strip()
    if result_status not in RESULT_STATUSES:
        raise APIError("成绩状态不合法")

    result = ContestResult.query.filter_by(contest_id=contest.id, student_id=student.id).first()
    if result and not overwrite:
        raise APIError("该学生成绩已存在，且未开启覆盖")
    if not result:
        result = ContestResult(contest_id=contest.id, student_id=student.id)
        db.session.add(result)

    fill_result_fields(
        result,
        {
            "awardLevel": get_record_value(record, "awardLevel", "获奖等级"),
            "resultStatus": result_status,
            "score": get_record_value(record, "score", "成绩分数"),
            "ranking": get_record_value(record, "ranking", "名次"),
            "certificateNo": get_record_value(record, "certificateNo", "证书编号"),
            "archiveRemark": get_record_value(record, "archiveRemark", "归档备注"),
            "confirmedAt": get_record_value(record, "confirmedAt", "确认时间"),
        },
    )
    return result


def build_archive_sheets(contest_id=None, allowed_contest_ids=None, user=None):
    actor = user or getattr(g, "current_user", None)
    registrations_query = ContestRegistration.query.join(StudentInfo, ContestRegistration.student_id == StudentInfo.id)
    results_query = ContestResult.query.join(StudentInfo, ContestResult.student_id == StudentInfo.id)
    if allowed_contest_ids is not None:
        registrations_query = apply_contest_scope(registrations_query, ContestRegistration.contest_id, allowed_contest_ids)
        results_query = apply_contest_scope(results_query, ContestResult.contest_id, allowed_contest_ids)
    if not is_admin_user(actor):
        registrations_query = apply_college_scope(registrations_query, StudentInfo.college, actor)
        results_query = apply_college_scope(results_query, StudentInfo.college, actor)
    if contest_id:
        registrations_query = registrations_query.filter(ContestRegistration.contest_id == int(contest_id))
        results_query = results_query.filter(ContestResult.contest_id == int(contest_id))

    registrations = registrations_query.order_by(ContestRegistration.id.desc()).all()
    results = results_query.order_by(ContestResult.id.desc()).all()

    result_rows = []
    certificate_rows = []
    for item in results:
        payload = serialize_result(item)
        result_rows.append(
            [
                payload["contestName"],
                payload["studentNo"],
                payload["studentName"],
                payload["college"],
                payload["awardLevel"] or "未获奖",
                payload["resultStatus"],
                payload["certificateAttachmentName"] or "未归档",
                payload["confirmedAt"],
            ]
        )
        if payload["certificateAttachmentName"]:
            attachment = find_certificate_attachment(item)
            certificate_rows.append(
                [
                    payload["contestName"],
                    payload["studentNo"],
                    payload["studentName"],
                    payload["certificateAttachmentName"],
                    attachment.file_path if attachment else "",
                    payload["confirmedAt"],
                ]
            )

    material_rows = []
    flow_rows = []
    for registration in registrations:
        for material in registration.materials:
            material_rows.append(
                [
                    registration.contest.contest_name if registration.contest else None,
                    registration.student.student_no if registration.student else None,
                    registration.student.name if registration.student else None,
                    material.material_type,
                    material.file_name,
                    material.review_status,
                    material.review_comment or "",
                    material.reviewed_at,
                ]
            )
        for flow in registration.flow_logs:
            flow_rows.append(
                [
                    registration.contest.contest_name if registration.contest else None,
                    registration.student.student_no if registration.student else None,
                    registration.student.name if registration.student else None,
                    flow.action_type,
                    flow.before_status,
                    flow.after_status,
                    flow.reason,
                    flow.operator.real_name if flow.operator else None,
                    flow.operated_at,
                ]
            )

    return [
        {
            "title": "成绩归档",
            "headers": ["赛事", "学号", "学生", "学院", "获奖等级", "结果状态", "证书文件", "确认时间（北京时间）"],
            "rows": result_rows,
        },
        {
            "title": "证书目录",
            "headers": ["赛事", "学号", "学生", "证书文件", "存储路径", "确认时间（北京时间）"],
            "rows": certificate_rows,
        },
        {
            "title": "材料提交记录",
            "headers": ["赛事", "学号", "学生", "材料类型", "文件名", "审核状态", "审核意见", "审核时间（北京时间）"],
            "rows": material_rows,
        },
        {
            "title": "状态流转记录",
            "headers": ["赛事", "学号", "学生", "动作", "变更前", "变更后", "原因", "操作人", "操作时间（北京时间）"],
            "rows": flow_rows,
        },
    ]


@bp.get("/results")
@auth_required(["admin", "teacher", "student"])
def list_results():
    query = collect_results_query(request.args).order_by(ContestResult.id.desc())
    if is_student_user():
        student = resolve_bound_student(required=True)
        query = query.filter(ContestResult.student_id == student.id)
    elif not is_admin_user():
        query = apply_contest_scope(query, ContestResult.contest_id, result_visible_contest_ids())
        query = query.join(StudentInfo, ContestResult.student_id == StudentInfo.id)
        query = apply_college_scope(query, StudentInfo.college, g.current_user)
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_result(item) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.get("/results/<int:result_id>")
@auth_required(["admin", "teacher", "student"])
def get_result(result_id):
    result = ensure_result_access(ContestResult.query.get_or_404(result_id))
    return success(serialize_result_detail(result))


@bp.post("/results")
@auth_required(["admin", "teacher"])
def create_result():
    payload = request.get_json(silent=True) or {}
    contest_id = payload.get("contestId")
    student_id = payload.get("studentId")
    if not contest_id or not student_id:
        raise APIError("赛事和学生不能为空")
    contest = ContestInfo.query.get(int(contest_id))
    student = StudentInfo.query.get(int(student_id))
    if not contest or not student:
        raise APIError("赛事或学生不存在")
    if not is_admin_user():
        ensure_result_visible_contest(contest.id, "当前账号无权维护该赛事成绩")
        if not student_in_college_scope(student, g.current_user):
            raise APIError("当前账号无权维护该学院学生成绩", code=403, status=200)
    duplicated = ContestResult.query.filter_by(contest_id=contest.id, student_id=student.id).first()
    if duplicated:
        raise APIError("该学生成绩已存在，请使用编辑")
    result = ContestResult(contest_id=contest.id, student_id=student.id)
    fill_result_fields(result, payload)
    db.session.add(result)
    db.session.commit()
    return success(serialize_result(result), message="成绩创建成功")


@bp.put("/results/<int:result_id>")
@auth_required(["admin", "teacher"])
def update_result(result_id):
    result = ensure_result_access(ContestResult.query.get_or_404(result_id), "当前账号无权维护该成绩记录")
    payload = request.get_json(silent=True) or {}
    fill_result_fields(result, payload)
    db.session.commit()
    return success(serialize_result(result), message="成绩更新成功")


@bp.post("/results/import-template")
@auth_required(["admin", "teacher"])
def download_result_import_template():
    content = create_workbook_bytes(
        [
            {
                "title": "成绩导入模板",
                "headers": ["赛事名称", "学号", "获奖等级", "结果状态", "成绩分数", "名次", "证书编号", "归档备注", "确认时间"],
                "rows": [["省级程序设计竞赛", "20260001", "一等奖", "awarded", 95.5, 1, "CERT-2026-001", "决赛获奖", now_beijing().strftime("%Y-%m-%d %H:%M:%S")]],
            }
        ]
    )
    _, _, target_path = create_export_file("成绩导入模板.xlsx", content, "result_import_template", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="成绩导入模板.xlsx", mimetype=XLSX_MIMETYPE)


@bp.post("/results/import")
@auth_required(["admin", "teacher"])
def import_results():
    json_payload = request.get_json(silent=True) or {}
    file = request.files.get("file")
    overwrite = parse_bool(request.form.get("overwrite") or json_payload.get("overwrite"), True)
    records = json_payload.get("records") or []

    task = ImportTask(task_type="contest_result_import", status="processing", created_by=g.current_user.id)
    db.session.add(task)
    db.session.flush()

    start_row = 1
    if file:
        records = parse_tabular_file(file)
        if hasattr(file.stream, "seek"):
            file.stream.seek(0)
        attachment = save_uploaded_attachment(file, "contest_result_import_source", g.current_user.id)
        task.source_file_id = attachment.id
        start_row = 2

    if not records:
        raise APIError("请至少提供一条成绩记录")

    success_count = 0
    fail_count = 0
    errors = []
    for index, record in enumerate(records, start=start_row):
        try:
            upsert_result(record, overwrite)
            success_count += 1
        except Exception as error:
            fail_count += 1
            errors.append({"row": index, "message": str(error)})

    task.success_count = success_count
    task.fail_count = fail_count
    task.status = "completed" if fail_count == 0 else "partial_success"
    db.session.commit()
    return success({"taskId": task.id, "successCount": success_count, "failCount": fail_count, "errors": errors}, message="成绩导入完成")


@bp.post("/certificates/upload")
@auth_required(["admin", "teacher"])
def upload_certificate():
    payload = request.get_json(silent=True) or {}
    result_id = request.form.get("resultId") or payload.get("resultId")
    if not result_id:
        raise APIError("成绩记录不能为空")
    result = ContestResult.query.get(int(result_id))
    if not result:
        raise APIError("成绩记录不存在")
    if not is_admin_user():
        ensure_result_access(result, "当前账号无权上传该成绩证书")

    file = request.files.get("file")
    if file:
        attachment = save_uploaded_attachment(file, f"certificate:{result.id}", g.current_user.id, subdir="certificates")
    else:
        raise APIError("请上传真实证书文件")

    result.certificate_attachment_name = attachment.file_name
    result.confirmed_at = result.confirmed_at or now_beijing()
    db.session.commit()
    return success({"result": serialize_result(result), "attachmentId": attachment.id, "filePath": attachment.file_path}, message="证书上传成功")


@bp.post("/certificates/download")
@auth_required(["admin", "teacher", "student"])
def download_certificate():
    result_id = request.form.get("resultId") or (request.get_json(silent=True) or {}).get("resultId")
    if not result_id:
        raise APIError("成绩记录不能为空")
    result = ContestResult.query.get(int(result_id))
    if not result:
        raise APIError("成绩记录不存在")
    ensure_result_access(result, "当前账号无权下载该成绩证书")
    attachment = find_certificate_attachment(result)
    if not attachment or not Path(attachment.file_path).exists():
        raise APIError("证书文件不存在")
    return send_file(attachment.file_path, as_attachment=True, download_name=attachment.file_name)


@bp.post("/certificates/preview")
@auth_required(["admin", "teacher", "student"])
def preview_certificate():
    result_id = request.form.get("resultId") or (request.get_json(silent=True) or {}).get("resultId")
    if not result_id:
        raise APIError("结果记录不能为空")
    result = ensure_result_access(ContestResult.query.get_or_404(int(result_id)))
    attachment = find_certificate_attachment(result)
    if not attachment or not Path(attachment.file_path).exists():
        raise APIError("证书文件不存在")
    return send_file(attachment.file_path, as_attachment=False, download_name=attachment.file_name)


@bp.get("/statistics/awards")
@auth_required(["admin", "teacher"])
def award_statistics():
    contest_id = normalize_export_contest_id(request.args.get("contestId"))
    if contest_id and not is_admin_user(g.current_user):
        ensure_result_visible_contest(contest_id, "当前账号无权查看该赛事统计")
    allowed_contest_ids = None if is_admin_user(g.current_user) else result_visible_contest_ids(user=g.current_user)
    return success(build_statistics_payload(contest_id, allowed_contest_ids, user=g.current_user))


@bp.post("/statistics/export-records")
@auth_required(["admin", "teacher"])
def create_statistics_export_task():
    payload = request.get_json(silent=True) or {}
    task_type = str(payload.get("taskType") or "award_statistics_export").strip() or "award_statistics_export"
    export_task_meta(task_type)
    contest_id = normalize_export_contest_id(payload.get("contestId"))
    validate_export_task_scope(task_type, contest_id, g.current_user)
    task = create_async_export_task(task_type, g.current_user.id, contest_id)
    return success(serialize_export_task(task), message="导出任务已创建")


@bp.get("/statistics/export-records")
@auth_required(["admin", "teacher"])
def list_statistics_export_records():
    query = ExportTask.query.filter(ExportTask.task_type.in_(sorted(STATISTICS_EXPORT_TASK_TYPES))).order_by(ExportTask.id.desc())
    if not is_admin_user():
        query = query.filter(ExportTask.created_by == g.current_user.id)
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_export_task(item) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.get("/statistics/export-records/<int:task_id>")
@auth_required(["admin", "teacher"])
def get_statistics_export_record(task_id):
    task = ensure_export_task_access(ExportTask.query.get_or_404(task_id))
    return success(serialize_export_task(task))


@bp.post("/statistics/export-records/<int:task_id>/download")
@auth_required(["admin", "teacher"])
def download_statistics_export_record(task_id):
    task = ensure_export_task_downloadable(ExportTask.query.get_or_404(task_id))
    attachment = db.session.get(AttachmentInfo, task.file_id) if task.file_id else None
    if not attachment or not Path(attachment.file_path).exists():
        raise APIError("导出文件不存在", status=404)
    mimetype = XLSX_MIMETYPE if str(attachment.file_ext or "").lower() == "xlsx" else None
    return send_file(attachment.file_path, as_attachment=True, download_name=attachment.file_name, mimetype=mimetype)


@bp.post("/statistics/export-records/<int:task_id>/retry")
@auth_required(["admin", "teacher"])
def retry_statistics_export_record(task_id):
    task = ensure_export_task_retryable(ExportTask.query.get_or_404(task_id))
    if task.file_id:
        delete_task_attachment(task.file_id)
        task.file_id = None
    task.status = "pending"
    task.progress = 0
    task.current_step = "等待重试"
    task.error_message = ""
    task.started_at = None
    task.finished_at = None
    task.retry_count = int(task.retry_count or 0) + 1
    db.session.commit()
    enqueue_export_task(task.id)
    return success(serialize_export_task(task), message="导出任务已重新提交")


@bp.post("/statistics/awards/export")
@auth_required(["admin", "teacher"])
def export_award_statistics():
    contest_id = normalize_export_contest_id(request.form.get("contestId") or request.args.get("contestId"))
    if contest_id and not is_admin_user(g.current_user):
        ensure_result_visible_contest(contest_id, "当前账号无权导出该赛事统计")
    allowed_contest_ids = None if is_admin_user(g.current_user) else result_visible_contest_ids(user=g.current_user)
    payload = build_statistics_payload(contest_id, allowed_contest_ids, user=g.current_user)
    content = create_workbook_bytes(award_statistics_sheets(payload))
    _, _, target_path = create_export_file("获奖统计报表.xlsx", content, "award_statistics_export", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="获奖统计报表.xlsx", mimetype=XLSX_MIMETYPE)


@bp.post("/results/archive-export")
@auth_required(["admin", "teacher"])
def export_archive_report():
    contest_id = normalize_export_contest_id(request.form.get("contestId") or request.args.get("contestId"))
    if contest_id and not is_admin_user(g.current_user):
        ensure_result_visible_contest(contest_id, "当前账号无权导出该赛事归档")
    allowed_contest_ids = None if is_admin_user(g.current_user) else result_visible_contest_ids(user=g.current_user)
    content = create_workbook_bytes(build_archive_sheets(contest_id, allowed_contest_ids, user=g.current_user))
    _, _, target_path = create_export_file("赛后归档资料.xlsx", content, "archive_export", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="赛后归档资料.xlsx", mimetype=XLSX_MIMETYPE)
