from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import foreign

from .extensions import db
from .time_utils import now_beijing


ID_TYPE = db.BigInteger().with_variant(db.Integer(), "sqlite")


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=now_beijing, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_beijing, onupdate=now_beijing, nullable=False)


class SysUserRole(db.Model):
    __tablename__ = "sys_user_role"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    role_id = db.Column(ID_TYPE, db.ForeignKey("sys_role.id"), nullable=False)


class SysRole(db.Model, TimestampMixin):
    __tablename__ = "sys_role"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    role_code = db.Column(db.String(64), unique=True, nullable=False)
    role_name = db.Column(db.String(64), nullable=False)
    status = db.Column(db.Integer, default=1, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "roleCode": self.role_code,
            "roleName": self.role_name,
            "status": self.status,
        }


class SysUser(db.Model, TimestampMixin):
    __tablename__ = "sys_user"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    real_name = db.Column(db.String(64), nullable=False)
    mobile = db.Column(db.String(32))
    email = db.Column(db.String(128))
    student_id = db.Column(ID_TYPE)
    status = db.Column(db.Integer, default=1, nullable=False)

    roles = db.relationship("SysRole", secondary="sys_user_role", lazy="joined")
    contest_permissions = db.relationship("ContestPermission", back_populates="user", lazy="select", cascade="all, delete-orphan")

    @property
    def role_codes(self):
        return [role.role_code for role in self.roles]

    @property
    def primary_role(self):
        return self.role_codes[0] if self.role_codes else "guest"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "realName": self.real_name,
            "mobile": self.mobile,
            "email": self.email,
            "studentId": self.student_id,
            "status": self.status,
            "roleCodes": self.role_codes,
            "primaryRole": self.primary_role,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class StudentInfo(db.Model, TimestampMixin):
    __tablename__ = "student_info"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    student_no = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    gender = db.Column(db.String(16), default="未知")
    college = db.Column(db.String(128), nullable=False)
    major = db.Column(db.String(128), nullable=False)
    class_name = db.Column(db.String(128), nullable=False)
    grade = db.Column(db.String(32))
    advisor_name = db.Column(db.String(64))
    mobile = db.Column(db.String(32))
    email = db.Column(db.String(128))
    history_experience = db.Column(db.Text)
    remark = db.Column(db.String(500))
    status = db.Column(db.Integer, default=1, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "studentNo": self.student_no,
            "name": self.name,
            "gender": self.gender,
            "college": self.college,
            "major": self.major,
            "className": self.class_name,
            "grade": self.grade,
            "advisorName": self.advisor_name,
            "mobile": self.mobile,
            "email": self.email,
            "historyExperience": self.history_experience,
            "remark": self.remark,
            "status": self.status,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class ContestInfo(db.Model, TimestampMixin):
    __tablename__ = "contest_info"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    contest_name = db.Column(db.String(255), nullable=False)
    contest_level = db.Column(db.String(64), nullable=False)
    organizer = db.Column(db.String(255), nullable=False)
    subject_category = db.Column(db.String(64))
    undertaker = db.Column(db.String(255))
    target_students = db.Column(db.String(255))
    contact_name = db.Column(db.String(64))
    contact_mobile = db.Column(db.String(32))
    location = db.Column(db.String(255))
    description = db.Column(db.Text)
    contest_year = db.Column(db.Integer)
    sign_up_start = db.Column(db.DateTime)
    sign_up_end = db.Column(db.DateTime)
    contest_date = db.Column(db.DateTime)
    status = db.Column(db.String(32), default="draft", nullable=False)
    material_requirements = db.Column(db.Text)
    quota_limit = db.Column(db.Integer, default=0)
    rule_attachment_name = db.Column(db.String(255))
    rule_attachment_id = db.Column(ID_TYPE)
    permissions = db.relationship("ContestPermission", back_populates="contest", lazy="select", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "contestName": self.contest_name,
            "contestLevel": self.contest_level,
            "organizer": self.organizer,
            "subjectCategory": self.subject_category,
            "undertaker": self.undertaker,
            "targetStudents": self.target_students,
            "contactName": self.contact_name,
            "contactMobile": self.contact_mobile,
            "location": self.location,
            "description": self.description,
            "contestYear": self.contest_year,
            "signUpStart": self.sign_up_start.isoformat() if self.sign_up_start else None,
            "signUpEnd": self.sign_up_end.isoformat() if self.sign_up_end else None,
            "contestDate": self.contest_date.isoformat() if self.contest_date else None,
            "status": self.status,
            "materialRequirements": self.material_requirements,
            "quotaLimit": self.quota_limit,
            "ruleAttachmentName": self.rule_attachment_name,
            "ruleAttachmentId": self.rule_attachment_id,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class ContestPermission(db.Model, TimestampMixin):
    __tablename__ = "contest_permission"
    __table_args__ = (UniqueConstraint("contest_id", "user_id", "permission_scope", name="uq_contest_permission_scope"),)

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    contest_id = db.Column(ID_TYPE, db.ForeignKey("contest_info.id"), nullable=False)
    user_id = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    permission_scope = db.Column(db.String(32), nullable=False)

    contest = db.relationship("ContestInfo", back_populates="permissions")
    user = db.relationship("SysUser", back_populates="contest_permissions", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "contestId": self.contest_id,
            "userId": self.user_id,
            "permissionScope": self.permission_scope,
            "userName": self.user.username if self.user else None,
            "realName": self.user.real_name if self.user else None,
            "roleCodes": self.user.role_codes if self.user else [],
        }


DIRTY_REGISTRATION_STATUSES = {"reviewing", "correction_required", "approved", "rejected", "supplemented"}


def resolve_registration_material_attachment(material):
    attachment = getattr(material, "attachment", None)
    if not attachment and getattr(material, "attachment_id", None):
        attachment = AttachmentInfo.query.get(material.attachment_id)
    if not attachment and getattr(material, "id", None):
        attachment = AttachmentInfo.query.filter_by(biz_type=f"registration_material:{material.id}").order_by(AttachmentInfo.id.desc()).first()
    return attachment


def build_registration_data_quality(material_payloads, final_status):
    attachment_count = sum(1 for item in material_payloads if item.get("hasAttachment"))
    metadata_only_count = sum(1 for item in material_payloads if item.get("fileName") and not item.get("hasAttachment"))
    issues = []
    if metadata_only_count:
        issues.append({
            "code": "missing_original_files",
            "message": f"存在 {metadata_only_count} 份仅登记文件名、未上传原件的材料。",
        })
    if metadata_only_count and final_status in DIRTY_REGISTRATION_STATUSES:
        issues.append({
            "code": "workflow_progressed_without_original_files",
            "message": "报名流程已经推进，但材料原件并未真实上传。",
        })
    return {
        "status": "dirty" if issues else "clean",
        "attachmentCount": attachment_count,
        "metadataOnlyMaterialCount": metadata_only_count,
        "requiresAttachmentRepair": bool(metadata_only_count),
        "issues": issues,
    }


class ContestRegistration(db.Model, TimestampMixin):
    __tablename__ = "contest_registration"
    __table_args__ = (UniqueConstraint("contest_id", "student_id", name="uq_registration_contest_student"),)

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    contest_id = db.Column(ID_TYPE, db.ForeignKey("contest_info.id"), nullable=False)
    student_id = db.Column(ID_TYPE, db.ForeignKey("student_info.id"), nullable=False)
    direction = db.Column(db.String(128))
    team_name = db.Column(db.String(128))
    project_name = db.Column(db.String(255))
    instructor_name = db.Column(db.String(64))
    instructor_mobile = db.Column(db.String(32))
    emergency_contact = db.Column(db.String(64))
    emergency_mobile = db.Column(db.String(32))
    source_type = db.Column(db.String(32), default="online")
    remark = db.Column(db.String(500))
    registration_status = db.Column(db.String(32), default="submitted", nullable=False)
    review_status = db.Column(db.String(32), default="pending", nullable=False)
    final_status = db.Column(db.String(32), default="submitted", nullable=False)
    submit_time = db.Column(db.DateTime, default=now_beijing, nullable=False)

    contest = db.relationship("ContestInfo", lazy="joined")
    student = db.relationship("StudentInfo", lazy="joined")
    materials = db.relationship("RegistrationMaterial", back_populates="registration", lazy="select", cascade="all, delete-orphan")
    flow_logs = db.relationship("RegistrationFlowLog", back_populates="registration", lazy="select", cascade="all, delete-orphan")

    def to_dict(self, with_details=False):
        material_payloads = [item.to_dict() for item in self.materials]
        quality = build_registration_data_quality(material_payloads, self.final_status)
        payload = {
            "id": self.id,
            "contestId": self.contest_id,
            "contestName": self.contest.contest_name if self.contest else None,
            "studentId": self.student_id,
            "studentNo": self.student.student_no if self.student else None,
            "studentName": self.student.name if self.student else None,
            "studentCollege": self.student.college if self.student else None,
            "studentMajor": self.student.major if self.student else None,
            "studentClassName": self.student.class_name if self.student else None,
            "direction": self.direction,
            "teamName": self.team_name,
            "projectName": self.project_name,
            "instructorName": self.instructor_name,
            "instructorMobile": self.instructor_mobile,
            "emergencyContact": self.emergency_contact,
            "emergencyMobile": self.emergency_mobile,
            "sourceType": self.source_type,
            "remark": self.remark,
            "registrationStatus": self.registration_status,
            "reviewStatus": self.review_status,
            "finalStatus": self.final_status,
            "materialCount": len(self.materials),
            "attachmentCount": quality["attachmentCount"],
            "metadataOnlyMaterialCount": quality["metadataOnlyMaterialCount"],
            "dataQualityStatus": quality["status"],
            "dataQualityIssues": quality["issues"],
            "requiresAttachmentRepair": quality["requiresAttachmentRepair"],
            "latestReviewComment": next((item.review_comment for item in reversed(self.materials) if item.review_comment), ""),
            "submitTime": self.submit_time.isoformat() if self.submit_time else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
        if with_details:
            payload["materials"] = material_payloads
            payload["flowLogs"] = [item.to_dict() for item in self.flow_logs]
        return payload


class RegistrationMaterial(db.Model, TimestampMixin):
    __tablename__ = "registration_material"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    registration_id = db.Column(ID_TYPE, db.ForeignKey("contest_registration.id"), nullable=False)
    material_type = db.Column(db.String(64), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    attachment_id = db.Column(ID_TYPE)
    submit_status = db.Column(db.String(32), default="submitted", nullable=False)
    review_status = db.Column(db.String(32), default="pending", nullable=False)
    reviewer_id = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"))
    review_comment = db.Column(db.String(500))
    reviewed_at = db.Column(db.DateTime)

    registration = db.relationship("ContestRegistration", back_populates="materials")
    reviewer = db.relationship("SysUser", lazy="joined")
    attachment = db.relationship(
        "AttachmentInfo",
        primaryjoin="foreign(RegistrationMaterial.attachment_id)==AttachmentInfo.id",
        lazy="joined",
        viewonly=True,
        uselist=False,
    )

    def to_dict(self):
        attachment = resolve_registration_material_attachment(self)
        file_ext = attachment.file_ext if attachment else (self.file_name.rsplit(".", 1)[-1].lower() if "." in self.file_name else None)
        has_attachment = bool(attachment and attachment.file_path)
        return {
            "id": self.id,
            "materialType": self.material_type,
            "fileName": self.file_name,
            "attachmentId": attachment.id if attachment else self.attachment_id,
            "fileExt": file_ext,
            "fileSize": attachment.file_size if attachment else None,
            "uploadedAt": attachment.uploaded_at.isoformat() if attachment and attachment.uploaded_at else (self.created_at.isoformat() if self.created_at else None),
            "hasAttachment": has_attachment,
            "dataQualityStatus": "clean" if has_attachment else "dirty",
            "dataQualityMessage": "原件已上传" if has_attachment else "当前只有文件名，没有真实上传文件。",
            "submitStatus": self.submit_status,
            "reviewStatus": self.review_status,
            "reviewComment": self.review_comment,
            "reviewedAt": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewerName": self.reviewer.real_name if self.reviewer else None,
        }


class RegistrationFlowLog(db.Model):
    __tablename__ = "registration_flow_log"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    registration_id = db.Column(ID_TYPE, db.ForeignKey("contest_registration.id"), nullable=False)
    action_type = db.Column(db.String(64), nullable=False)
    before_status = db.Column(db.String(32))
    after_status = db.Column(db.String(32))
    reason = db.Column(db.String(500))
    operator_id = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    operated_at = db.Column(db.DateTime, default=now_beijing, nullable=False)

    registration = db.relationship("ContestRegistration", back_populates="flow_logs")
    operator = db.relationship("SysUser", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "actionType": self.action_type,
            "beforeStatus": self.before_status,
            "afterStatus": self.after_status,
            "reason": self.reason,
            "operatorName": self.operator.real_name if self.operator else None,
            "operatedAt": self.operated_at.isoformat() if self.operated_at else None,
        }


MESSAGE_TARGET_ROLE_CODES = ("admin", "teacher", "reviewer", "student")


def parse_message_target_roles(value):
    if value in (None, ""):
        return []
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    roles = []
    seen = set()
    for item in items:
        role = str(item or "").strip()
        if not role or role in seen:
            continue
        seen.add(role)
        roles.append(role)
    return roles


def parse_message_target_user_ids(value):
    if value in (None, ""):
        return []
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    user_ids = []
    seen = set()
    for item in items:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            continue
        if user_id in seen:
            continue
        seen.add(user_id)
        user_ids.append(user_id)
    return user_ids


class MessageTodoRule(db.Model, TimestampMixin):
    __tablename__ = "message_todo_rule"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    rule_name = db.Column(db.String(128), nullable=False)
    scene = db.Column(db.String(64), nullable=False, default="pending_materials")
    contest_id = db.Column(ID_TYPE)
    target_role = db.Column(db.String(64))
    priority = db.Column(db.String(16), default="normal", nullable=False)
    enabled_status = db.Column(db.Integer, default=1, nullable=False)
    title_template = db.Column(db.String(255))
    summary_template = db.Column(db.String(255))
    content_template = db.Column(db.Text)
    last_run_at = db.Column(db.DateTime)
    last_generated_count = db.Column(db.Integer, default=0, nullable=False)
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)

    creator = db.relationship("SysUser", lazy="joined")
    messages = db.relationship("NoticeMessage", back_populates="todo_rule", lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "ruleName": self.rule_name,
            "scene": self.scene,
            "contestId": self.contest_id,
            "targetRole": self.target_role,
            "targetRoles": parse_message_target_roles(self.target_role),
            "priority": self.priority,
            "enabledStatus": self.enabled_status,
            "titleTemplate": self.title_template,
            "summaryTemplate": self.summary_template,
            "contentTemplate": self.content_template,
            "lastRunAt": self.last_run_at.isoformat() if self.last_run_at else None,
            "lastGeneratedCount": self.last_generated_count,
            "createdBy": self.created_by,
            "createdByName": self.creator.real_name if self.creator else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class NoticeMessage(db.Model):
    __tablename__ = "notice_message"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=False)
    message_type = db.Column(db.String(32), default="notice", nullable=False)
    target_scope = db.Column(db.String(64), default="all", nullable=False)
    contest_id = db.Column(ID_TYPE)
    target_role = db.Column(db.String(64))
    target_user_ids = db.Column(db.String(500))
    target_status = db.Column(db.String(32))
    priority = db.Column(db.String(16), default="normal")
    summary = db.Column(db.String(255))
    planned_send_at = db.Column(db.DateTime)
    content = db.Column(db.Text, nullable=False)
    send_status = db.Column(db.String(32), default="pending", nullable=False)
    sent_at = db.Column(db.DateTime)
    source_key = db.Column(db.String(255))
    todo_rule_id = db.Column(ID_TYPE, db.ForeignKey("message_todo_rule.id"))
    last_error = db.Column(db.String(255))
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=now_beijing, nullable=False)

    creator = db.relationship("SysUser", lazy="joined")
    todo_rule = db.relationship("MessageTodoRule", back_populates="messages", lazy="joined")
    read_records = db.relationship("MessageReadRecord", back_populates="message", lazy="select", cascade="all, delete-orphan")
    failure_records = db.relationship("MessageSendFailure", back_populates="message", lazy="select", cascade="all, delete-orphan")

    def to_dict(self, current_user_id=None):
        read_record = None
        if current_user_id:
            read_record = next((item for item in self.read_records if item.user_id == current_user_id), None)
        latest_failure = max(self.failure_records, key=lambda item: item.id, default=None)
        return {
            "id": self.id,
            "title": self.title,
            "messageType": self.message_type,
            "targetScope": self.target_scope,
            "contestId": self.contest_id,
            "targetRole": self.target_role,
            "targetRoles": parse_message_target_roles(self.target_role),
            "targetUserIds": parse_message_target_user_ids(self.target_user_ids),
            "targetStatus": self.target_status,
            "priority": self.priority,
            "summary": self.summary,
            "plannedSendAt": self.planned_send_at.isoformat() if self.planned_send_at else None,
            "content": self.content,
            "sendStatus": self.send_status,
            "sentAt": self.sent_at.isoformat() if self.sent_at else None,
            "sourceKey": self.source_key,
            "todoRuleId": self.todo_rule_id,
            "lastError": self.last_error,
            "failureCount": len(self.failure_records),
            "latestFailureReason": latest_failure.reason if latest_failure else None,
            "createdBy": self.created_by,
            "createdByName": self.creator.real_name if self.creator else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "readStatus": read_record.read_status if read_record else 0,
            "readAt": read_record.read_at.isoformat() if read_record and read_record.read_at else None,
        }


class MessageReadRecord(db.Model):
    __tablename__ = "message_read_record"
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_message_user"),)

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    message_id = db.Column(ID_TYPE, db.ForeignKey("notice_message.id"), nullable=False)
    user_id = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    read_status = db.Column(db.Integer, default=0, nullable=False)
    read_at = db.Column(db.DateTime)

    message = db.relationship("NoticeMessage", back_populates="read_records")
    user = db.relationship("SysUser", lazy="joined")


class MessageSendFailure(db.Model):
    __tablename__ = "message_send_failure"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    message_id = db.Column(ID_TYPE, db.ForeignKey("notice_message.id"), nullable=False)
    role_code = db.Column(db.String(32))
    reason = db.Column(db.String(255), nullable=False)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_beijing, nullable=False)

    message = db.relationship("NoticeMessage", back_populates="failure_records")

    def to_dict(self):
        return {
            "id": self.id,
            "messageId": self.message_id,
            "roleCode": self.role_code,
            "reason": self.reason,
            "detail": self.detail,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class ContestResult(db.Model, TimestampMixin):
    __tablename__ = "contest_result"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    contest_id = db.Column(ID_TYPE, db.ForeignKey("contest_info.id"), nullable=False)
    student_id = db.Column(ID_TYPE, db.ForeignKey("student_info.id"), nullable=False)
    award_level = db.Column(db.String(64))
    result_status = db.Column(db.String(32), default="pending", nullable=False)
    score = db.Column(db.Float)
    ranking = db.Column(db.Integer)
    certificate_no = db.Column(db.String(64))
    certificate_attachment_name = db.Column(db.String(255))
    archive_remark = db.Column(db.String(500))
    confirmed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "contestId": self.contest_id,
            "studentId": self.student_id,
            "awardLevel": self.award_level,
            "resultStatus": self.result_status,
            "score": self.score,
            "ranking": self.ranking,
            "certificateNo": self.certificate_no,
            "certificateAttachmentName": self.certificate_attachment_name,
            "archiveRemark": self.archive_remark,
            "confirmedAt": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class AttachmentInfo(db.Model, TimestampMixin):
    __tablename__ = "attachment_info"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_ext = db.Column(db.String(32))
    file_size = db.Column(ID_TYPE, default=0, nullable=False)
    biz_type = db.Column(db.String(64), nullable=False)
    uploader_id = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=now_beijing, nullable=False)


class ImportTask(db.Model, TimestampMixin):
    __tablename__ = "import_task"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    task_type = db.Column(db.String(64), nullable=False)
    source_file_id = db.Column(ID_TYPE)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    fail_count = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)


class ExportTask(db.Model, TimestampMixin):
    __tablename__ = "export_task"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    task_type = db.Column(db.String(64), nullable=False)
    task_name = db.Column(db.String(128), default="", nullable=False)
    file_id = db.Column(ID_TYPE)
    status = db.Column(db.String(32), default="pending", nullable=False)
    progress = db.Column(db.Integer, default=0, nullable=False)
    current_step = db.Column(db.String(255), default="", nullable=False)
    error_message = db.Column(db.String(500), default="", nullable=False)
    request_payload_json = db.Column(db.Text, default="{}", nullable=False)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)


class FileDeliveryChannel(db.Model, TimestampMixin):
    __tablename__ = "file_delivery_channel"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    channel_name = db.Column(db.String(128), unique=True, nullable=False)
    channel_type = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(16), default="enabled", nullable=False)
    config_json = db.Column(db.Text, default="{}", nullable=False)
    remark = db.Column(db.String(500), default="", nullable=False)
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    last_validated_at = db.Column(db.DateTime)
    last_validation_status = db.Column(db.String(16), default="pending", nullable=False)
    last_error = db.Column(db.String(500), default="", nullable=False)


class FileExportPolicy(db.Model, TimestampMixin):
    __tablename__ = "file_export_policy"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    policy_name = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(16), default="enabled", nullable=False)
    schedule_type = db.Column(db.String(16), default="manual", nullable=False)
    schedule_time = db.Column(db.String(16), default="", nullable=False)
    increment_mode = db.Column(db.String(16), default="full", nullable=False)
    scope_json = db.Column(db.Text, default="{}", nullable=False)
    folder_template = db.Column(db.String(255), default="", nullable=False)
    file_name_template = db.Column(db.String(255), default="", nullable=False)
    include_manifest = db.Column(db.String(8), default="Y", nullable=False)
    delivery_channel_ids_json = db.Column(db.Text, default="[]", nullable=False)
    remark = db.Column(db.String(500), default="", nullable=False)
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    last_run_at = db.Column(db.DateTime)
    next_run_at = db.Column(db.DateTime)
    last_status = db.Column(db.String(32), default="", nullable=False)
    last_error = db.Column(db.String(500), default="", nullable=False)


class FileExportBatch(db.Model, TimestampMixin):
    __tablename__ = "file_export_batch"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    policy_id = db.Column(ID_TYPE, db.ForeignKey("file_export_policy.id"), nullable=False)
    batch_no = db.Column(db.String(64), unique=True, nullable=False)
    trigger_type = db.Column(db.String(16), default="manual", nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)
    progress = db.Column(db.Integer, default=0, nullable=False)
    current_step = db.Column(db.String(255), default="", nullable=False)
    error_message = db.Column(db.String(500), default="", nullable=False)
    source_count = db.Column(db.Integer, default=0, nullable=False)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    fail_count = db.Column(db.Integer, default=0, nullable=False)
    attachment_id = db.Column(ID_TYPE)
    package_file_name = db.Column(db.String(255), default="", nullable=False)
    manifest_json = db.Column(db.Text, default="{}", nullable=False)
    request_snapshot_json = db.Column(db.Text, default="{}", nullable=False)
    result_snapshot_json = db.Column(db.Text, default="{}", nullable=False)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    created_by = db.Column(ID_TYPE, db.ForeignKey("sys_user.id"), nullable=False)
    scheduled_for = db.Column(db.DateTime)

    policy = db.relationship("FileExportPolicy", lazy="joined")


class FileDeliveryRecord(db.Model, TimestampMixin):
    __tablename__ = "file_delivery_record"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    batch_id = db.Column(ID_TYPE, db.ForeignKey("file_export_batch.id"), nullable=False)
    channel_id = db.Column(ID_TYPE, db.ForeignKey("file_delivery_channel.id"), nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)
    progress = db.Column(db.Integer, default=0, nullable=False)
    current_step = db.Column(db.String(255), default="", nullable=False)
    target_path = db.Column(db.String(500), default="", nullable=False)
    delivered_file_name = db.Column(db.String(255), default="", nullable=False)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    fail_count = db.Column(db.Integer, default=0, nullable=False)
    response_snapshot_json = db.Column(db.Text, default="{}", nullable=False)
    error_message = db.Column(db.String(500), default="", nullable=False)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    retry_count = db.Column(db.Integer, default=0, nullable=False)

    batch = db.relationship("FileExportBatch", lazy="joined")
    channel = db.relationship("FileDeliveryChannel", lazy="joined")


class SystemRoleMeta(db.Model, TimestampMixin):
    __tablename__ = "system_role_meta"
    __table_args__ = (UniqueConstraint("role_id", name="uq_system_role_meta_role"),)

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    role_id = db.Column(ID_TYPE, db.ForeignKey("sys_role.id"), nullable=False)
    role_sort = db.Column(db.Integer, default=0, nullable=False)
    data_scope = db.Column(db.String(16), default="1", nullable=False)
    menu_ids_json = db.Column(db.Text, default="[]", nullable=False)
    dept_ids_json = db.Column(db.Text, default="[]", nullable=False)
    remark = db.Column(db.String(500), default="", nullable=False)


class SystemMenu(db.Model, TimestampMixin):
    __tablename__ = "system_menu"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=False)
    parent_id = db.Column(ID_TYPE, default=0, nullable=False)
    menu_name = db.Column(db.String(128), nullable=False)
    icon = db.Column(db.String(64), default="", nullable=False)
    order_num = db.Column(db.Integer, default=0, nullable=False)
    path = db.Column(db.String(255), default="", nullable=False)
    component = db.Column(db.String(255), default="", nullable=False)
    query_value = db.Column(db.String(255), default="", nullable=False)
    is_frame = db.Column(db.String(8), default="1", nullable=False)
    is_cache = db.Column(db.String(8), default="0", nullable=False)
    visible = db.Column(db.String(8), default="0", nullable=False)
    status = db.Column(db.String(8), default="0", nullable=False)
    menu_type = db.Column(db.String(8), default="M", nullable=False)
    perms = db.Column(db.String(255), default="", nullable=False)


class SystemConfig(db.Model, TimestampMixin):
    __tablename__ = "system_config"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=False)
    config_name = db.Column(db.String(128), nullable=False)
    config_key = db.Column(db.String(128), unique=True, nullable=False)
    config_value = db.Column(db.Text, default="", nullable=False)
    config_type = db.Column(db.String(8), default="N", nullable=False)
    remark = db.Column(db.String(500), default="", nullable=False)


class SystemDictType(db.Model, TimestampMixin):
    __tablename__ = "system_dict_type"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=False)
    dict_name = db.Column(db.String(128), nullable=False)
    dict_type = db.Column(db.String(128), unique=True, nullable=False)
    status = db.Column(db.String(8), default="0", nullable=False)
    remark = db.Column(db.String(500), default="", nullable=False)


class SystemDictData(db.Model, TimestampMixin):
    __tablename__ = "system_dict_data"
    __table_args__ = (UniqueConstraint("dict_type", "dict_value", name="uq_system_dict_data_type_value"),)

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=False)
    dict_sort = db.Column(db.Integer, default=0, nullable=False)
    dict_label = db.Column(db.String(128), nullable=False)
    dict_value = db.Column(db.String(128), nullable=False)
    dict_type = db.Column(db.String(128), nullable=False)
    css_class = db.Column(db.String(128), default="", nullable=False)
    list_class = db.Column(db.String(32), default="default", nullable=False)
    is_default = db.Column(db.String(8), default="N", nullable=False)
    status = db.Column(db.String(8), default="0", nullable=False)
    remark = db.Column(db.String(500), default="", nullable=False)


class AuditLoginInfo(db.Model):
    __tablename__ = "audit_login_info"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    user_name = db.Column(db.String(128), nullable=False)
    ipaddr = db.Column(db.String(64), default="127.0.0.1", nullable=False)
    login_location = db.Column(db.String(255), default="", nullable=False)
    browser = db.Column(db.String(255), default="", nullable=False)
    os = db.Column(db.String(255), default="", nullable=False)
    status = db.Column(db.String(8), default="0", nullable=False)
    msg = db.Column(db.String(255), default="", nullable=False)
    login_time = db.Column(db.DateTime, default=now_beijing, nullable=False)


class AuditOperLog(db.Model):
    __tablename__ = "audit_oper_log"

    id = db.Column(ID_TYPE, primary_key=True, autoincrement=True)
    title = db.Column(db.String(128), nullable=False)
    business_type = db.Column(db.String(8), default="0", nullable=False)
    oper_name = db.Column(db.String(128), default="anonymous", nullable=False)
    oper_ip = db.Column(db.String(64), default="127.0.0.1", nullable=False)
    oper_location = db.Column(db.String(255), default="", nullable=False)
    oper_url = db.Column(db.String(255), default="", nullable=False)
    request_method = db.Column(db.String(16), default="GET", nullable=False)
    method = db.Column(db.String(255), default="", nullable=False)
    oper_param = db.Column(db.Text, default="", nullable=False)
    json_result = db.Column(db.Text, default="", nullable=False)
    status = db.Column(db.Integer, default=0, nullable=False)
    error_msg = db.Column(db.Text, default="", nullable=False)
    cost_time = db.Column(db.Integer, default=0, nullable=False)
    oper_time = db.Column(db.DateTime, default=now_beijing, nullable=False)
