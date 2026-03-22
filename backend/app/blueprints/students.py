from datetime import datetime

from sqlalchemy import func, or_

from flask import Blueprint, g, request, send_file

from ..account_service import serialize_user, sync_student_account
from ..access import ensure_student_owner, has_any_role, is_student_user, resolve_bound_student
from ..common import paginate_query, success
from ..data_scope import apply_college_scope, student_in_college_scope
from ..errors import APIError
from ..excel_utils import XLSX_MIMETYPE, create_export_file, create_workbook_bytes, parse_tabular_file, save_uploaded_attachment
from ..extensions import db
from ..models import AttachmentInfo, ContestRegistration, ContestResult, ImportTask, StudentInfo, SysUser
from ..security import auth_required


bp = Blueprint("students", __name__, url_prefix="/api/v1/students")
STUDENT_IMPORT_TASK_TYPE = "contest_student_import"


def bool_flag(value):
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def collect_student_stats(student_ids):
    if not student_ids:
        return {}, {}
    registration_rows = (
        db.session.query(ContestRegistration.student_id, func.count(ContestRegistration.id))
        .filter(ContestRegistration.student_id.in_(student_ids))
        .group_by(ContestRegistration.student_id)
        .all()
    )
    award_rows = (
        db.session.query(ContestResult.student_id, func.count(ContestResult.id))
        .filter(ContestResult.student_id.in_(student_ids), ContestResult.award_level.isnot(None), ContestResult.award_level != "")
        .group_by(ContestResult.student_id)
        .all()
    )
    return dict(registration_rows), dict(award_rows)


def collect_student_accounts(student_ids):
    if not student_ids:
        return {}
    return {
        item.student_id: serialize_user(item)
        for item in SysUser.query.filter(SysUser.student_id.in_(student_ids)).order_by(SysUser.id.asc()).all()
        if item.student_id
    }


def serialize_student(student, participation_counts=None, award_counts=None, account_index=None):
    payload = student.to_dict()
    payload["participationCount"] = (participation_counts or {}).get(student.id, 0)
    payload["awardCount"] = (award_counts or {}).get(student.id, 0)
    payload["hasHistoryExperience"] = bool(payload["participationCount"] or payload.get("historyExperience"))
    account = (account_index or {}).get(student.id)
    payload["hasLoginAccount"] = bool(account)
    payload["accountUserId"] = account.get("userId") if account else None
    payload["loginAccount"] = account.get("userName") if account else None
    payload["accountStatus"] = account.get("status") if account else None
    payload["accountStatusLabel"] = "启用" if account and account.get("status") == "0" else ("停用" if account else "未创建")
    payload["accountSourceLabel"] = account.get("accountSourceLabel") if account else None
    is_manager = has_any_role("admin", "teacher")
    payload["permissions"] = {
        "canView": True,
        "ownedByCurrentUser": bool(is_student_user() and resolve_bound_student(required=True).id == student.id) if is_student_user() else False,
        "canEdit": is_manager,
        "canEnable": is_manager and int(student.status or 0) != 1,
        "canDisable": is_manager and int(student.status or 0) == 1,
    }
    return payload


def get_record_value(record, *keys):
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def parse_bool(value, default=True):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_student_status(value, default=1):
    if value in (None, ""):
        return int(default)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "enabled", "enable", "active", "启用"}:
        return 1
    if normalized in {"0", "false", "no", "n", "off", "disabled", "disable", "inactive", "停用"}:
        return 0
    raise APIError("学生状态不合法")


def normalize_optional_text(value):
    return str(value or "").strip() or None


def serialize_import_task(task):
    attachment = AttachmentInfo.query.get(task.source_file_id) if task.source_file_id else None
    creator = SysUser.query.get(task.created_by) if task.created_by else None
    return {
        "id": task.id,
        "taskType": task.task_type,
        "status": task.status,
        "successCount": task.success_count,
        "failCount": task.fail_count,
        "sourceFileId": task.source_file_id,
        "sourceFileName": attachment.file_name if attachment else None,
        "sourceFileSize": attachment.file_size if attachment else 0,
        "createdBy": task.created_by,
        "createdByName": creator.real_name if creator else None,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
        "updatedAt": task.updated_at.isoformat() if task.updated_at else None,
    }


def upsert_student_record(record, overwrite):
    student_id = get_record_value(record, "studentId", "学生ID")
    student_no = str(get_record_value(record, "studentNo", "学号") or "").strip()
    student = None
    is_new_student = False
    if student_id not in (None, ""):
        student = StudentInfo.query.get(int(student_id))
        if not student:
            raise APIError("导入中的学生 ID 不存在")
    elif student_no:
        student = StudentInfo.query.filter_by(student_no=student_no).first()

    if student and not overwrite:
        raise APIError("该学生已存在，且未开启覆盖")
    if not student:
        student = StudentInfo()
        is_new_student = True

    next_student_no = str(get_record_value(record, "studentNo", "学号") or student.student_no or "").strip()
    next_name = str(get_record_value(record, "name", "姓名") or student.name or "").strip()
    next_college = str(get_record_value(record, "college", "学院") or student.college or "").strip()
    next_major = str(get_record_value(record, "major", "专业") or student.major or "").strip()
    next_class_name = str(get_record_value(record, "className", "班级") or student.class_name or "").strip()

    if not all([next_student_no, next_name, next_college, next_major, next_class_name]):
        raise APIError("学生学号、姓名、学院、专业、班级不能为空")

    duplicated = StudentInfo.query.filter(StudentInfo.student_no == next_student_no)
    if student.id:
        duplicated = duplicated.filter(StudentInfo.id != student.id)
    if duplicated.first():
        raise APIError("学生学号已存在")

    if is_new_student:
        db.session.add(student)

    student.student_no = next_student_no
    student.name = next_name
    student.gender = str(get_record_value(record, "gender", "性别") or student.gender or "未知").strip() or "未知"
    student.college = next_college
    student.major = next_major
    student.class_name = next_class_name
    student.grade = normalize_optional_text(get_record_value(record, "grade", "年级")) if get_record_value(record, "grade", "年级") not in (None, "") else student.grade
    student.advisor_name = normalize_optional_text(get_record_value(record, "advisorName", "导师", "指导老师")) if get_record_value(record, "advisorName", "导师", "指导老师") not in (None, "") else student.advisor_name
    student.mobile = normalize_optional_text(get_record_value(record, "mobile", "手机", "联系方式")) if get_record_value(record, "mobile", "手机", "联系方式") not in (None, "") else student.mobile
    student.email = normalize_optional_text(get_record_value(record, "email", "邮箱")) if get_record_value(record, "email", "邮箱") not in (None, "") else student.email
    student.history_experience = normalize_optional_text(get_record_value(record, "historyExperience", "历史经历", "参赛经历")) if get_record_value(record, "historyExperience", "历史经历", "参赛经历") not in (None, "") else student.history_experience
    student.remark = normalize_optional_text(get_record_value(record, "remark", "备注")) if get_record_value(record, "remark", "备注") not in (None, "") else student.remark
    student.status = normalize_student_status(get_record_value(record, "status", "状态"), student.status if student.status is not None else 1)
    return student


@bp.get("")
@auth_required(["admin", "teacher", "reviewer", "student"])
def list_students():
    keyword = (request.args.get("keyword") or "").strip()
    status = request.args.get("status")
    college = (request.args.get("college") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    has_experience = bool_flag(request.args.get("hasExperience"))

    query = StudentInfo.query
    if is_student_user():
        student = resolve_bound_student(required=True)
        query = query.filter(StudentInfo.id == student.id)
    else:
        query = apply_college_scope(query, StudentInfo.college, g.current_user)
    if keyword:
        query = query.filter(
            or_(
                StudentInfo.student_no.like(f"%{keyword}%"),
                StudentInfo.name.like(f"%{keyword}%"),
                StudentInfo.college.like(f"%{keyword}%"),
                StudentInfo.major.like(f"%{keyword}%"),
                StudentInfo.advisor_name.like(f"%{keyword}%"),
            )
        )
    if status not in (None, ""):
        query = query.filter(StudentInfo.status == int(status))
    if college:
        query = query.filter(StudentInfo.college == college)
    if grade:
        query = query.filter(StudentInfo.grade == grade)
    if has_experience is True:
        query = query.filter(
            or_(
                StudentInfo.history_experience.isnot(None),
                StudentInfo.id.in_(db.session.query(ContestRegistration.student_id)),
                StudentInfo.id.in_(db.session.query(ContestResult.student_id)),
            )
        )
    elif has_experience is False:
        query = query.filter(
            StudentInfo.history_experience.is_(None),
            ~StudentInfo.id.in_(db.session.query(ContestRegistration.student_id)),
            ~StudentInfo.id.in_(db.session.query(ContestResult.student_id)),
        )

    query = query.order_by(StudentInfo.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    student_ids = [item.id for item in items]
    participation_counts, award_counts = collect_student_stats(student_ids)
    account_index = collect_student_accounts(student_ids)
    return success(
        {
            "list": [serialize_student(item, participation_counts, award_counts, account_index) for item in items],
            "total": total,
            "pageNum": page_num,
            "pageSize": page_size,
        }
    )


@bp.get("/<int:student_id>")
@auth_required(["admin", "teacher", "reviewer", "student"])
def get_student(student_id):
    if is_student_user():
        ensure_student_owner(student_id, "仅可查看本人学生档案")
    student = StudentInfo.query.get_or_404(student_id)
    if not is_student_user() and not student_in_college_scope(student, g.current_user):
        raise APIError("当前账号无权查看该学院学生档案", code=403, status=200)
    participation_counts, award_counts = collect_student_stats([student.id])
    recent_registrations = (
        ContestRegistration.query.filter_by(student_id=student.id)
        .order_by(ContestRegistration.id.desc())
        .limit(5)
        .all()
    )
    recent_results = ContestResult.query.filter_by(student_id=student.id).order_by(ContestResult.id.desc()).limit(5).all()
    payload = serialize_student(student, participation_counts, award_counts, collect_student_accounts([student.id]))
    payload["recentRegistrations"] = [item.to_dict() for item in recent_registrations]
    payload["recentResults"] = [item.to_dict() for item in recent_results]
    return success(payload)


@bp.post("")
@auth_required(["admin"])
def create_student():
    payload = request.get_json(silent=True) or {}
    student_no = (payload.get("studentNo") or "").strip()
    name = (payload.get("name") or "").strip()
    college = (payload.get("college") or "").strip()
    major = (payload.get("major") or "").strip()
    class_name = (payload.get("className") or "").strip()
    if not all([student_no, name, college, major, class_name]):
        raise APIError("学生学号、姓名、学院、专业、班级不能为空")
    if StudentInfo.query.filter_by(student_no=student_no).first():
        raise APIError("学生学号已存在")

    student = StudentInfo(
        student_no=student_no,
        name=name,
        gender=payload.get("gender") or "未知",
        college=college,
        major=major,
        class_name=class_name,
        grade=(payload.get("grade") or "").strip() or None,
        advisor_name=(payload.get("advisorName") or "").strip() or None,
        mobile=(payload.get("mobile") or "").strip() or None,
        email=(payload.get("email") or "").strip() or None,
        history_experience=(payload.get("historyExperience") or "").strip() or None,
        remark=(payload.get("remark") or "").strip() or None,
        status=int(payload.get("status", 1)),
    )
    db.session.add(student)
    db.session.flush()
    sync_student_account(student)
    db.session.commit()
    return success(serialize_student(student, account_index=collect_student_accounts([student.id])), message="学生创建成功")


@bp.put("/<int:student_id>")
@auth_required(["admin"])
def update_student(student_id):
    student = StudentInfo.query.get_or_404(student_id)
    payload = request.get_json(silent=True) or {}
    student_no = (payload.get("studentNo") or student.student_no).strip()
    duplicated = StudentInfo.query.filter(StudentInfo.student_no == student_no, StudentInfo.id != student_id).first()
    if duplicated:
        raise APIError("学生学号已存在")

    student.student_no = student_no
    student.name = (payload.get("name") or student.name).strip()
    student.gender = payload.get("gender") or student.gender
    student.college = (payload.get("college") or student.college).strip()
    student.major = (payload.get("major") or student.major).strip()
    student.class_name = (payload.get("className") or student.class_name).strip()
    student.grade = (payload.get("grade") or student.grade or "").strip() or None
    student.advisor_name = (payload.get("advisorName") or student.advisor_name or "").strip() or None
    student.mobile = (payload.get("mobile") or "").strip() or None
    student.email = (payload.get("email") or "").strip() or None
    student.history_experience = (payload.get("historyExperience") or "").strip() or None
    student.remark = (payload.get("remark") or "").strip() or None
    student.status = int(payload.get("status", student.status))
    sync_student_account(student)
    db.session.commit()
    return success(serialize_student(student, account_index=collect_student_accounts([student.id])), message="学生更新成功")


@bp.post("/<int:student_id>/status")
@auth_required(["admin"])
def update_student_status(student_id):
    student = StudentInfo.query.get_or_404(student_id)
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in (0, 1, "0", "1"):
        raise APIError("学生状态不合法")
    student.status = int(status)
    sync_student_account(student)
    db.session.commit()
    return success(serialize_student(student, account_index=collect_student_accounts([student.id])), message="学生状态更新成功")


@bp.post("/import-template")
@auth_required(["admin"])
def download_student_import_template():
    content = create_workbook_bytes(
        [
            {
                "title": "学生导入模板",
                "headers": ["学号", "姓名", "性别", "学院", "专业", "班级", "年级", "导师", "手机", "邮箱", "历史经历", "备注", "状态"],
                "rows": [["20260001", "王小明", "男", "计算机学院", "软件工程", "软件工程 2201", "2022级", "陈老师", "13800001111", "wangxiaoming@example.com", "2025 程序设计竞赛校级一等奖", "批量导入样例", 1]],
            }
        ]
    )
    _, _, target_path = create_export_file("学生导入模板.xlsx", content, "student_import_template", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="学生导入模板.xlsx", mimetype=XLSX_MIMETYPE)


@bp.post("/import")
@auth_required(["admin"])
def import_students():
    json_payload = request.get_json(silent=True) or {}
    file = request.files.get("file")
    overwrite = parse_bool(request.form.get("overwrite") or json_payload.get("overwrite"), True)
    records = json_payload.get("records") or []

    task = ImportTask(task_type=STUDENT_IMPORT_TASK_TYPE, status="processing", created_by=g.current_user.id)
    db.session.add(task)
    db.session.flush()

    start_row = 1
    if file:
        records = parse_tabular_file(file)
        if hasattr(file.stream, "seek"):
            file.stream.seek(0)
        attachment = save_uploaded_attachment(file, "contest_student_import_source", g.current_user.id)
        task.source_file_id = attachment.id
        start_row = 2

    if not records:
        raise APIError("请至少提供一条学生记录")

    success_count = 0
    fail_count = 0
    errors = []
    for index, record in enumerate(records, start=start_row):
        try:
            with db.session.begin_nested():
                student = upsert_student_record(record, overwrite)
                db.session.flush()
                sync_student_account(student)
            success_count += 1
        except Exception as error:
            fail_count += 1
            errors.append({"row": index, "message": str(error)})

    task.success_count = success_count
    task.fail_count = fail_count
    task.status = "completed" if fail_count == 0 else "partial_success"
    db.session.commit()
    return success({"taskId": task.id, "successCount": success_count, "failCount": fail_count, "errors": errors}, message="学生导入完成")


@bp.get("/import-records")
@auth_required(["admin"])
def list_student_import_records():
    query = ImportTask.query.filter_by(task_type=STUDENT_IMPORT_TASK_TYPE).order_by(ImportTask.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_import_task(item) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})
