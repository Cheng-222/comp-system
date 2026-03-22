from datetime import datetime
from pathlib import Path

from flask import Blueprint, g, request, send_file
from sqlalchemy import and_, or_

from ..access import (
    apply_contest_scope,
    can_approve_registration,
    can_edit_registration,
    can_replace_registration,
    can_review_registration,
    can_submit_correction,
    can_submit_materials,
    can_supplement_registration,
    can_withdraw_registration,
    ensure_managed_contest,
    ensure_registration_access,
    ensure_student_owner,
    is_student_user,
    is_teacher_user,
    is_reviewer_user,
    managed_contest_ids,
    registration_requires_attachment_repair,
    reviewable_contest_ids,
    resolve_bound_student,
)
from ..common import paginate_query, parse_datetime, success
from ..data_scope import apply_college_scope, student_in_college_scope
from ..errors import APIError
from ..excel_utils import XLSX_MIMETYPE, create_export_file, create_workbook_bytes, parse_tabular_file, save_uploaded_attachment
from ..extensions import db
from ..models import AttachmentInfo, ContestInfo, ContestRegistration, ImportTask, RegistrationFlowLog, RegistrationMaterial, StudentInfo
from ..security import auth_required
from ..time_utils import now_beijing
from ..workflow_notifications import send_registration_workflow_messages


bp = Blueprint("registrations", __name__, url_prefix="/api/v1/registrations")


REGISTRATION_STATUSES = {"draft", "submitted", "reviewing", "correction_required", "approved", "rejected", "withdrawn", "replaced", "supplemented", "archived"}
REVIEW_STATUSES = {"pending", "reviewing", "correction_required", "approved", "rejected"}


def create_flow_log(registration, action_type, before_status, after_status, reason):
    log = RegistrationFlowLog(
        registration_id=registration.id,
        action_type=action_type,
        before_status=before_status,
        after_status=after_status,
        reason=reason,
        operator_id=g.current_user.id,
    )
    db.session.add(log)
    return log


def find_material_attachment(material):
    if getattr(material, "attachment_id", None):
        attachment = AttachmentInfo.query.get(material.attachment_id)
        if attachment:
            return attachment
    return AttachmentInfo.query.filter_by(biz_type=f"registration_material:{material.id}").order_by(AttachmentInfo.id.desc()).first()


def send_material_attachment(material, inline=False):
    attachment = find_material_attachment(material)
    if not attachment or not Path(attachment.file_path).exists():
        raise APIError("材料文件不存在", status=404)
    return send_file(
        attachment.file_path,
        as_attachment=not inline,
        download_name=attachment.file_name,
    )


def get_registration_or_fail(registration_id):
    registration = ContestRegistration.query.get(registration_id)
    if not registration:
        raise APIError("报名记录不存在", status=404)
    return registration


def serialize_registration(registration, with_details=False):
    payload = registration.to_dict(with_details=with_details)
    payload["permissions"] = {
        "canEdit": can_edit_registration(registration),
        "canSubmitMaterials": can_submit_materials(registration),
        "canApprove": can_approve_registration(registration),
        "canCorrection": can_submit_correction(registration),
        "canWithdraw": can_withdraw_registration(registration),
        "canReplace": can_replace_registration(registration),
        "canSupplement": can_supplement_registration(registration),
        "canReview": can_review_registration(registration),
        "canRepairAttachments": registration_requires_attachment_repair(registration),
        "ownedByCurrentUser": bool(is_student_user() and resolve_bound_student(required=True).id == registration.student_id)
        if is_student_user()
        else False,
    }
    return payload


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


def build_registration_query(params):
    keyword = (params.get("keyword") or "").strip()
    contest_id = params.get("contestId")
    student_id = params.get("studentId")
    final_status = params.get("finalStatus")
    review_status = params.get("reviewStatus")
    data_quality_status = (params.get("dataQualityStatus") or "").strip()
    source_type = (params.get("sourceType") or "").strip()
    student_college = (params.get("studentCollege") or "").strip()
    queue_only = parse_bool(params.get("queueOnly"), False)
    qualification_only = parse_bool(params.get("qualificationOnly"), False)

    query = ContestRegistration.query.join(StudentInfo).join(ContestInfo)
    if keyword:
        query = query.filter(
            or_(
                StudentInfo.name.like(f"%{keyword}%"),
                StudentInfo.student_no.like(f"%{keyword}%"),
                ContestInfo.contest_name.like(f"%{keyword}%"),
                ContestRegistration.project_name.like(f"%{keyword}%"),
                ContestRegistration.instructor_name.like(f"%{keyword}%"),
            )
        )
    if contest_id:
        query = query.filter(ContestRegistration.contest_id == int(contest_id))
    if student_id:
        query = query.filter(ContestRegistration.student_id == int(student_id))
    if final_status:
        query = query.filter(ContestRegistration.final_status == final_status)
    if review_status:
        query = query.filter(ContestRegistration.review_status == review_status)
    if data_quality_status == "dirty":
        query = query.filter(
            ContestRegistration.materials.any(
                and_(RegistrationMaterial.file_name.isnot(None), RegistrationMaterial.attachment_id.is_(None))
            )
        )
    elif data_quality_status == "clean":
        query = query.filter(
            ~ContestRegistration.materials.any(
                and_(RegistrationMaterial.file_name.isnot(None), RegistrationMaterial.attachment_id.is_(None))
            )
        )
    if source_type:
        query = query.filter(ContestRegistration.source_type == source_type)
    if student_college:
        query = query.filter(StudentInfo.college == student_college)
    if queue_only:
        query = query.filter(
            or_(
                ContestRegistration.review_status.in_(["pending", "reviewing", "correction_required"]),
                ContestRegistration.final_status.in_(["submitted", "reviewing", "correction_required", "supplemented"]),
            )
        )
    if qualification_only:
        query = query.filter(
            ContestRegistration.final_status.in_(["approved", "rejected", "withdrawn", "replaced", "supplemented"])
        )
    return query


def apply_registration_scope(query):
    if is_student_user():
        student = resolve_bound_student(required=True)
        return query.filter(ContestRegistration.student_id == student.id)
    if is_teacher_user():
        query = apply_contest_scope(query, ContestRegistration.contest_id, managed_contest_ids())
        return apply_college_scope(query, StudentInfo.college, g.current_user)
    if is_reviewer_user():
        query = apply_contest_scope(query, ContestRegistration.contest_id, reviewable_contest_ids())
        return apply_college_scope(query, StudentInfo.college, g.current_user)
    return query


def resolve_contest(record):
    contest_id = get_record_value(record, "contestId", "赛事ID")
    contest_name = str(get_record_value(record, "contestName", "赛事名称") or "").strip()
    contest = None
    if contest_id:
        contest = ContestInfo.query.get(int(contest_id))
    elif contest_name:
        contest = ContestInfo.query.filter_by(contest_name=contest_name).first()
    if not contest:
        raise APIError("报名导入中的赛事不存在")
    if is_teacher_user():
        ensure_managed_contest(contest.id, "当前账号无权导入该赛事报名")
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
        raise APIError("报名导入中的学生不存在")
    if not is_student_user() and not student_in_college_scope(student, g.current_user):
        raise APIError("当前数据权限不允许为该学院学生导入报名")
    return student


def normalize_registration_status(value, default="submitted"):
    status = str(value or default).strip() or default
    if status not in REGISTRATION_STATUSES:
        raise APIError("报名状态不合法")
    return status


def normalize_review_status(value, fallback_status):
    if value in (None, ""):
        if fallback_status in REVIEW_STATUSES:
            return fallback_status
        return "pending"
    status = str(value).strip()
    if status not in REVIEW_STATUSES:
        raise APIError("审核状态不合法")
    return status


def latest_review_comment(registration):
    comments = [item.review_comment for item in registration.materials if item.review_comment]
    return comments[-1] if comments else ""


def material_summary(registration):
    if not registration.materials:
        return "未提交材料"
    if registration_requires_attachment_repair(registration):
        return "存在仅登记文件名、未上传原件的历史材料"
    return "；".join(f"{item.material_type}:{item.file_name}" for item in registration.materials)


def pending_reason(registration):
    reasons = []
    if not registration.materials:
        reasons.append("未提交材料")
    if registration_requires_attachment_repair(registration):
        reasons.append("缺少真实原件")
    if registration.final_status == "correction_required":
        reasons.append("待补正")
    if any(item.review_status == "pending" for item in registration.materials):
        reasons.append("存在待审材料")
    if any(item.review_status == "rejected" for item in registration.materials):
        reasons.append("存在驳回材料")
    return "；".join(dict.fromkeys(reasons))


def normalize_material_type(value, default_value):
    return str(value or default_value).strip() or default_value


def create_material_record(registration, material_type, file_name, attachment_id=None):
    material = RegistrationMaterial(
        registration_id=registration.id,
        material_type=material_type,
        file_name=file_name,
        attachment_id=attachment_id,
        submit_status="submitted",
        review_status="pending",
    )
    db.session.add(material)
    return material


def create_named_materials(registration, materials, default_material_type):
    created_count = 0
    for item in materials:
        material_type = normalize_material_type(item.get("materialType"), default_material_type)
        file_name = (item.get("fileName") or "").strip()
        if not file_name:
            raise APIError("材料文件名不能为空")
        create_material_record(registration, material_type, file_name)
        created_count += 1
    return created_count


def create_uploaded_materials(registration, files, default_material_type):
    created_count = 0
    material_type = normalize_material_type(request.form.get("materialType"), default_material_type)
    repair_targets = [item for item in registration.materials if item.file_name and not find_material_attachment(item)]
    for file_storage in files:
        if not file_storage or not getattr(file_storage, "filename", None):
            continue
        if repair_targets:
            material = repair_targets.pop(0)
            material.material_type = material.material_type or material_type
            material.submit_status = "submitted"
            material.review_status = "pending"
            material.review_comment = None
            material.reviewer_id = None
            material.reviewed_at = None
        else:
            material = create_material_record(registration, material_type, file_storage.filename or "未命名材料")
            db.session.flush()
        attachment = save_uploaded_attachment(file_storage, f"registration_material:{material.id}", g.current_user.id, subdir="registrations")
        material.file_name = attachment.file_name
        material.attachment_id = attachment.id
        created_count += 1
    return created_count


def request_uploaded_files():
    files = request.files.getlist("files")
    if files:
        return files
    single_file = request.files.get("file")
    return [single_file] if single_file else []


def fill_registration_fields(registration, payload):
    registration.direction = str(payload.get("direction") or registration.direction or "").strip() or None
    registration.team_name = str(payload.get("teamName") or registration.team_name or "").strip() or None
    registration.project_name = str(payload.get("projectName") or registration.project_name or "").strip() or None
    registration.instructor_name = str(payload.get("instructorName") or registration.instructor_name or "").strip() or None
    registration.instructor_mobile = str(payload.get("instructorMobile") or registration.instructor_mobile or "").strip() or None
    registration.emergency_contact = str(payload.get("emergencyContact") or registration.emergency_contact or "").strip() or None
    registration.emergency_mobile = str(payload.get("emergencyMobile") or registration.emergency_mobile or "").strip() or None
    registration.source_type = str(payload.get("sourceType") or registration.source_type or "online").strip() or "online"
    registration.remark = str(payload.get("remark") or registration.remark or "").strip() or None


def build_export_rows(scene, registrations):
    if scene == "review_results":
        return {
            "title": "审核结果",
            "headers": ["赛事", "学号", "学生", "学院", "项目名称", "方向", "队伍", "指导老师", "来源", "审核状态", "当前状态", "审核意见", "材料摘要", "提交时间（北京时间）"],
            "rows": [
                [
                    item.contest.contest_name if item.contest else None,
                    item.student.student_no if item.student else None,
                    item.student.name if item.student else None,
                    item.student.college if item.student else None,
                    item.project_name,
                    item.direction,
                    item.team_name,
                    item.instructor_name,
                    item.source_type,
                    item.review_status,
                    item.final_status,
                    latest_review_comment(item),
                    material_summary(item),
                    item.submit_time,
                ]
                for item in registrations
            ],
        }

    if scene == "pending_materials":
        pending_items = [item for item in registrations if pending_reason(item)]
        return {
            "title": "待补材料清单",
            "headers": ["赛事", "学号", "学生", "学院", "项目名称", "当前状态", "待办原因", "材料摘要", "提交时间（北京时间）"],
            "rows": [
                [
                    item.contest.contest_name if item.contest else None,
                    item.student.student_no if item.student else None,
                    item.student.name if item.student else None,
                    item.student.college if item.student else None,
                    item.project_name,
                    item.final_status,
                    pending_reason(item),
                    material_summary(item),
                    item.submit_time,
                ]
                for item in pending_items
            ],
        }

    return {
        "title": "报名名单",
        "headers": ["赛事", "学号", "学生", "学院", "项目名称", "方向", "队伍", "指导老师", "来源", "审核状态", "当前状态", "材料数量", "提交时间（北京时间）"],
        "rows": [
            [
                item.contest.contest_name if item.contest else None,
                item.student.student_no if item.student else None,
                item.student.name if item.student else None,
                item.student.college if item.student else None,
                item.project_name,
                item.direction,
                item.team_name,
                item.instructor_name,
                item.source_type,
                item.review_status,
                item.final_status,
                len(item.materials),
                item.submit_time,
            ]
            for item in registrations
        ],
    }


def import_registration_record(record, overwrite):
    contest = resolve_contest(record)
    student = resolve_student(record)
    registration = ContestRegistration.query.filter_by(contest_id=contest.id, student_id=student.id).first()
    before_status = registration.final_status if registration else None
    if registration and not overwrite:
        raise APIError("该学生已存在报名记录，且未开启覆盖")
    if not registration:
        registration = ContestRegistration(contest_id=contest.id, student_id=student.id)
        db.session.add(registration)
        db.session.flush()

    final_status = normalize_registration_status(get_record_value(record, "finalStatus", "报名状态"), registration.final_status if before_status else "submitted")
    review_status = normalize_review_status(get_record_value(record, "reviewStatus", "审核状态"), final_status)

    fill_registration_fields(
        registration,
        {
            "direction": get_record_value(record, "direction", "报名方向"),
            "teamName": get_record_value(record, "teamName", "队伍名称"),
            "projectName": get_record_value(record, "projectName", "项目名称"),
            "instructorName": get_record_value(record, "instructorName", "指导老师"),
            "instructorMobile": get_record_value(record, "instructorMobile", "指导老师电话"),
            "emergencyContact": get_record_value(record, "emergencyContact", "紧急联系人"),
            "emergencyMobile": get_record_value(record, "emergencyMobile", "紧急联系电话"),
            "sourceType": get_record_value(record, "sourceType", "报名来源") or registration.source_type or "import",
            "remark": get_record_value(record, "remark", "备注"),
        },
    )
    registration.registration_status = final_status
    registration.review_status = review_status
    registration.final_status = final_status
    registration.submit_time = parse_datetime(get_record_value(record, "submitTime", "报名时间"), "报名时间") or registration.submit_time or now_beijing()

    action = "import_registration_update" if before_status else "import_registration_create"
    create_flow_log(registration, action, before_status, final_status, "批量导入报名数据")
    return registration


@bp.get("")
@auth_required(["admin", "teacher", "reviewer", "student"])
def list_registrations():
    query = apply_registration_scope(build_registration_query(request.args)).order_by(ContestRegistration.id.desc())
    items, total, page_num, page_size = paginate_query(query)
    return success({"list": [serialize_registration(item) for item in items], "total": total, "pageNum": page_num, "pageSize": page_size})


@bp.get("/<int:registration_id>")
@auth_required(["admin", "teacher", "reviewer", "student"])
def get_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    return success(serialize_registration(registration, with_details=True))


@bp.post("")
@auth_required(["admin", "teacher", "student"])
def create_registration():
    payload = request.get_json(silent=True) or {}
    contest_id = payload.get("contestId")
    student_id = payload.get("studentId")
    if is_student_user():
        bound_student = resolve_bound_student(required=True)
        if student_id in (None, ""):
            student_id = bound_student.id
        ensure_student_owner(student_id, "学生账号只能为本人创建报名")
    if not contest_id or not student_id:
        raise APIError("赛事和学生不能为空")

    contest = ContestInfo.query.get(contest_id)
    student = StudentInfo.query.get(student_id)
    if not contest:
        raise APIError("赛事不存在")
    if not student:
        raise APIError("学生不存在")
    if not is_student_user() and not student_in_college_scope(student, g.current_user):
        raise APIError("当前账号无权为该学院学生创建报名", code=403, status=200)
    if is_teacher_user():
        ensure_managed_contest(contest.id, "当前账号无权为该赛事维护报名")
    if contest.status not in {"signing_up", "reviewing"}:
        raise APIError("当前赛事不允许报名")
    if ContestRegistration.query.filter_by(contest_id=contest_id, student_id=student_id).first():
        raise APIError("该学生已报名当前赛事")

    registration = ContestRegistration(
        contest_id=contest_id,
        student_id=student_id,
        registration_status="submitted",
        review_status="pending",
        final_status="submitted",
        submit_time=now_beijing(),
    )
    fill_registration_fields(registration, payload)
    db.session.add(registration)
    db.session.flush()
    create_flow_log(registration, "submit_registration", None, "submitted", "提交报名")
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="报名提交成功")


@bp.put("/<int:registration_id>")
@auth_required(["admin", "teacher", "student"])
def update_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_edit_registration(registration):
        raise APIError("当前报名状态不允许编辑", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    fill_registration_fields(registration, payload)
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="报名信息更新成功")


@bp.post("/import-template")
@auth_required(["admin", "teacher"])
def download_registration_import_template():
    content = create_workbook_bytes(
        [
            {
                "title": "报名导入模板",
                "headers": ["赛事名称", "学号", "项目名称", "报名方向", "队伍名称", "指导老师", "指导老师电话", "报名来源", "备注", "报名状态", "审核状态", "报名时间"],
                "rows": [["省级程序设计竞赛", "20260001", "智能车项目", "算法设计", "今夜必胜队", "王老师", "13800001111", "import", "批量导入样例", "submitted", "pending", now_beijing().strftime("%Y-%m-%d %H:%M:%S")]],
            }
        ]
    )
    _, _, target_path = create_export_file("报名导入模板.xlsx", content, "registration_import_template", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name="报名导入模板.xlsx", mimetype=XLSX_MIMETYPE)


@bp.post("/import")
@auth_required(["admin", "teacher"])
def import_registrations():
    json_payload = request.get_json(silent=True) or {}
    file = request.files.get("file")
    overwrite = parse_bool(request.form.get("overwrite") or json_payload.get("overwrite"), True)
    records = json_payload.get("records") or []

    task = ImportTask(task_type="contest_registration_import", status="processing", created_by=g.current_user.id)
    db.session.add(task)
    db.session.flush()

    start_row = 1
    if file:
        records = parse_tabular_file(file)
        if hasattr(file.stream, "seek"):
            file.stream.seek(0)
        attachment = save_uploaded_attachment(file, "contest_registration_import_source", g.current_user.id)
        task.source_file_id = attachment.id
        start_row = 2

    if not records:
        raise APIError("请至少提供一条报名记录")

    success_count = 0
    fail_count = 0
    errors = []
    for index, record in enumerate(records, start=start_row):
        try:
            import_registration_record(record, overwrite)
            success_count += 1
        except Exception as error:
            fail_count += 1
            errors.append({"row": index, "message": str(error)})

    task.success_count = success_count
    task.fail_count = fail_count
    task.status = "completed" if fail_count == 0 else "partial_success"
    db.session.commit()
    return success({"taskId": task.id, "successCount": success_count, "failCount": fail_count, "errors": errors}, message="报名导入完成")


@bp.post("/export")
@auth_required(["admin", "teacher", "reviewer"])
def export_registrations():
    scene = (request.form.get("scene") or request.args.get("scene") or "registration_list").strip()
    registrations = apply_registration_scope(build_registration_query(request.values)).order_by(ContestRegistration.id.desc()).all()
    sheet = build_export_rows(scene, registrations)
    filename_map = {
        "registration_list": "报名名单导出.xlsx",
        "review_results": "审核结果导出.xlsx",
        "pending_materials": "待补材料清单.xlsx",
    }
    content = create_workbook_bytes([sheet])
    _, _, target_path = create_export_file(filename_map.get(scene, "报名导出.xlsx"), content, f"registration_export:{scene}", g.current_user.id)
    db.session.commit()
    return send_file(target_path, as_attachment=True, download_name=filename_map.get(scene, "报名导出.xlsx"), mimetype=XLSX_MIMETYPE)


@bp.post("/<int:registration_id>/materials")
@auth_required(["admin", "teacher", "student"])
def submit_materials(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_submit_materials(registration):
        raise APIError("当前报名状态不允许提交材料", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    materials = payload.get("materials") or []
    if not materials and payload.get("fileName"):
        materials = [payload]
    uploaded_files = request_uploaded_files()
    repair_required_count = sum(1 for item in registration.materials if item.file_name and not find_material_attachment(item))
    if materials:
        raise APIError("请上传真实材料文件，不能只登记文件名")
    if repair_required_count and len(uploaded_files) < repair_required_count:
        raise APIError(f"当前记录还缺少 {repair_required_count} 份原件，请一次补齐后再送审")
    created_count = 0
    if uploaded_files:
        created_count += create_uploaded_materials(registration, uploaded_files, "报名材料")
    if not created_count:
        raise APIError("至少提交一份材料")

    before_status = registration.final_status
    registration.registration_status = "reviewing"
    registration.review_status = "reviewing"
    registration.final_status = "reviewing"
    remark = request.form.get("remark") or payload.get("remark") or "提交审核材料"
    flow_log = create_flow_log(registration, "submit_materials", before_status, "reviewing", remark)
    db.session.flush()
    send_registration_workflow_messages(
        event="submit_materials",
        registration=registration,
        actor_user_id=g.current_user.id,
        reason=remark,
        flow_log_id=flow_log.id,
    )
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="材料提交成功")


@bp.post("/<int:registration_id>/review")
@auth_required(["admin", "reviewer"])
def review_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_review_registration(registration):
        raise APIError("当前报名状态不允许审核", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    comment = payload.get("comment") or ""
    if action not in {"approve", "reject", "correction_required"}:
        raise APIError("审核动作不合法")
    if action in {"approve", "reject"} and not registration.materials:
        raise APIError("请先提交报名材料后再完成审核")
    if action == "approve" and not can_approve_registration(registration):
        raise APIError("当前记录缺少真实上传的材料原件，不能直接审核通过")

    before_status = registration.final_status
    if action == "approve":
        registration.registration_status = "approved"
        registration.review_status = "approved"
        registration.final_status = "approved"
    elif action == "reject":
        registration.registration_status = "rejected"
        registration.review_status = "rejected"
        registration.final_status = "rejected"
    else:
        registration.registration_status = "correction_required"
        registration.review_status = "correction_required"
        registration.final_status = "correction_required"

    for material in registration.materials:
        material.review_status = registration.review_status
        material.review_comment = comment
        material.reviewer_id = g.current_user.id
        material.reviewed_at = now_beijing()

    flow_log = create_flow_log(registration, f"review_{action}", before_status, registration.final_status, comment or "审核完成")
    db.session.flush()
    send_registration_workflow_messages(
        event=f"review_{action}",
        registration=registration,
        actor_user_id=g.current_user.id,
        reason=comment or "审核完成",
        flow_log_id=flow_log.id,
    )
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="审核处理成功")


@bp.post("/<int:registration_id>/correction")
@auth_required(["admin", "teacher", "student"])
def correction_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_submit_correction(registration):
        raise APIError("当前报名状态不允许提交补正", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    materials = payload.get("materials") or []
    uploaded_files = request_uploaded_files()
    repair_required_count = sum(1 for item in registration.materials if item.file_name and not find_material_attachment(item))
    if materials:
        raise APIError("补正材料必须上传真实文件，不能只登记文件名")
    if repair_required_count and len(uploaded_files) < repair_required_count:
        raise APIError(f"当前记录还缺少 {repair_required_count} 份原件，请一次补齐后再送审")
    created_count = 0
    if uploaded_files:
        created_count += create_uploaded_materials(registration, uploaded_files, "补正材料")
    if not created_count:
        raise APIError("补正时至少提交一份材料")
    comment = request.form.get("comment") or payload.get("comment") or "提交补正材料"
    before_status = registration.final_status
    registration.registration_status = "reviewing"
    registration.review_status = "reviewing"
    registration.final_status = "reviewing"

    flow_log = create_flow_log(registration, "submit_correction", before_status, "reviewing", comment)
    db.session.flush()
    send_registration_workflow_messages(
        event="submit_correction",
        registration=registration,
        actor_user_id=g.current_user.id,
        reason=comment,
        flow_log_id=flow_log.id,
    )
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="补正提交成功")


@bp.post("/materials/<int:material_id>/download")
@auth_required(["admin", "teacher", "reviewer", "student"])
def download_registration_material(material_id):
    material = RegistrationMaterial.query.get(material_id)
    if not material:
        raise APIError("材料不存在", status=404)
    ensure_registration_access(get_registration_or_fail(material.registration_id))
    return send_material_attachment(material, inline=False)


@bp.post("/materials/<int:material_id>/preview")
@auth_required(["admin", "teacher", "reviewer", "student"])
def preview_registration_material(material_id):
    material = RegistrationMaterial.query.get(material_id)
    if not material:
        raise APIError("材料不存在", status=404)
    ensure_registration_access(get_registration_or_fail(material.registration_id))
    return send_material_attachment(material, inline=True)


@bp.post("/<int:registration_id>/withdraw")
@auth_required(["admin", "teacher", "student"])
def withdraw_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_withdraw_registration(registration):
        raise APIError("当前报名状态不允许退赛", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason") or "主动退赛"
    before_status = registration.final_status
    registration.registration_status = "withdrawn"
    registration.final_status = "withdrawn"
    flow_log = create_flow_log(registration, "withdraw", before_status, "withdrawn", reason)
    db.session.flush()
    send_registration_workflow_messages(
        event="withdraw",
        registration=registration,
        actor_user_id=g.current_user.id,
        reason=reason,
        flow_log_id=flow_log.id,
    )
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="退赛处理成功")


@bp.post("/<int:registration_id>/replace")
@auth_required(["admin", "teacher"])
def replace_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_replace_registration(registration):
        raise APIError("当前报名状态不允许换人", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    replacement_student_id = payload.get("replacementStudentId")
    reason = payload.get("reason") or "换人处理"
    before_status = registration.final_status
    registration.registration_status = "replaced"
    registration.final_status = "replaced"
    replace_log = create_flow_log(registration, "replace", before_status, "replaced", reason)

    new_registration = None
    replacement_entry_log = None
    if replacement_student_id:
        student = StudentInfo.query.get(replacement_student_id)
        if not student:
            raise APIError("替换学生不存在")
        if not student_in_college_scope(student, g.current_user):
            raise APIError("当前账号无权为该学院学生执行换人", code=403, status=200)
        if ContestRegistration.query.filter_by(contest_id=registration.contest_id, student_id=replacement_student_id).first():
            raise APIError("替换学生已报名当前赛事")
        new_registration = ContestRegistration(
            contest_id=registration.contest_id,
            student_id=replacement_student_id,
            direction=registration.direction,
            team_name=registration.team_name,
            registration_status="supplemented",
            review_status="reviewing",
            final_status="supplemented",
        )
        db.session.add(new_registration)
        db.session.flush()
        replacement_entry_log = create_flow_log(new_registration, "replacement_entry", None, "supplemented", f"承接原报名 {registration.id}")

    db.session.flush()
    send_registration_workflow_messages(
        event="replace",
        registration=registration,
        actor_user_id=g.current_user.id,
        reason=reason,
        flow_log_id=replace_log.id,
        replacement_registration=new_registration,
        replacement_flow_log_id=replacement_entry_log.id if replacement_entry_log else None,
    )
    db.session.commit()
    return success({"current": serialize_registration(registration, with_details=True), "replacement": serialize_registration(new_registration, with_details=True) if new_registration else None}, message="换人处理成功")


@bp.post("/<int:registration_id>/supplement")
@auth_required(["admin", "teacher"])
def supplement_registration(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    if not can_supplement_registration(registration):
        raise APIError("当前报名状态不允许补录", code=403, status=200)
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason") or "补录处理"
    before_status = registration.final_status
    registration.registration_status = "supplemented"
    registration.review_status = "reviewing"
    registration.final_status = "supplemented"
    flow_log = create_flow_log(registration, "supplement", before_status, "supplemented", reason)
    db.session.flush()
    send_registration_workflow_messages(
        event="supplement",
        registration=registration,
        actor_user_id=g.current_user.id,
        reason=reason,
        flow_log_id=flow_log.id,
    )
    db.session.commit()
    return success(serialize_registration(registration, with_details=True), message="补录处理成功")


@bp.get("/<int:registration_id>/flow-logs")
@auth_required(["admin", "teacher", "reviewer", "student"])
def registration_flow_logs(registration_id):
    registration = ensure_registration_access(get_registration_or_fail(registration_id))
    return success([item.to_dict() for item in registration.flow_logs])
