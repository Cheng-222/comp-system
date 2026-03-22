from datetime import timedelta

from sqlalchemy import text

from .extensions import db
from .models import (
    AttachmentInfo,
    ContestInfo,
    ContestPermission,
    ContestRegistration,
    ContestResult,
    ExportTask,
    ImportTask,
    MessageReadRecord,
    MessageSendFailure,
    MessageTodoRule,
    NoticeMessage,
    RegistrationFlowLog,
    RegistrationMaterial,
    StudentInfo,
    SysRole,
    SysUser,
)


MIGRATION_KEY = "beijing_time_migration_v1"
RUNTIME_META_TABLE = "app_runtime_meta"


def ensure_runtime_meta_table():
    db.session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {RUNTIME_META_TABLE} (
                meta_key VARCHAR(128) PRIMARY KEY,
                meta_value VARCHAR(255)
            )
            """
        )
    )
    db.session.commit()


def get_runtime_meta(key):
    row = db.session.execute(
        text(f"SELECT meta_value FROM {RUNTIME_META_TABLE} WHERE meta_key = :meta_key"),
        {"meta_key": key},
    ).first()
    return row[0] if row else None


def set_runtime_meta(key, value):
    if get_runtime_meta(key) is None:
        db.session.execute(
            text(f"INSERT INTO {RUNTIME_META_TABLE} (meta_key, meta_value) VALUES (:meta_key, :meta_value)"),
            {"meta_key": key, "meta_value": value},
        )
    else:
        db.session.execute(
            text(f"UPDATE {RUNTIME_META_TABLE} SET meta_value = :meta_value WHERE meta_key = :meta_key"),
            {"meta_key": key, "meta_value": value},
        )


def shift_8_hours(value):
    return value + timedelta(hours=8) if value else None


def shift_fields(item, *field_names):
    for field_name in field_names:
        value = getattr(item, field_name, None)
        if value:
            setattr(item, field_name, shift_8_hours(value))


def migrate_legacy_utc_to_beijing():
    ensure_runtime_meta_table()
    if get_runtime_meta(MIGRATION_KEY):
        return

    for model in (SysRole, SysUser, StudentInfo, ContestInfo, ContestPermission, AttachmentInfo, ImportTask, ExportTask):
        for item in model.query.all():
            shift_fields(item, "created_at", "updated_at")
            if isinstance(item, ExportTask):
                shift_fields(item, "started_at", "finished_at")

    for item in ContestRegistration.query.all():
        original_created_at = item.created_at
        original_submit_time = item.submit_time
        shift_fields(item, "created_at", "updated_at")
        if original_submit_time and (
            item.source_type != "import"
            or (original_created_at and abs((original_submit_time - original_created_at).total_seconds()) <= 300)
        ):
            item.submit_time = shift_8_hours(original_submit_time)

    for item in RegistrationMaterial.query.all():
        shift_fields(item, "created_at", "updated_at", "reviewed_at")

    for item in RegistrationFlowLog.query.all():
        shift_fields(item, "operated_at")

    for item in MessageTodoRule.query.all():
        shift_fields(item, "created_at", "updated_at", "last_run_at")

    for item in NoticeMessage.query.all():
        shift_fields(item, "created_at", "sent_at")

    for item in MessageReadRecord.query.all():
        shift_fields(item, "read_at")

    for item in MessageSendFailure.query.all():
        shift_fields(item, "created_at")

    for item in ContestResult.query.all():
        original_created_at = item.created_at
        original_confirmed_at = item.confirmed_at
        shift_fields(item, "created_at", "updated_at")
        if original_confirmed_at and original_created_at and abs((original_confirmed_at - original_created_at).total_seconds()) <= 300:
            item.confirmed_at = shift_8_hours(original_confirmed_at)

    set_runtime_meta(MIGRATION_KEY, "done")
    db.session.commit()
