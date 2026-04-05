from sqlalchemy import inspect, text

from .extensions import db


ADDITIONAL_COLUMNS = {
    "sys_user": {
        "student_id": "BIGINT",
        "email": "VARCHAR(128)",
    },
    "student_info": {
        "grade": "VARCHAR(32)",
        "advisor_name": "VARCHAR(64)",
        "history_experience": "TEXT",
        "remark": "VARCHAR(500)",
    },
    "contest_info": {
        "subject_category": "VARCHAR(64)",
        "undertaker": "VARCHAR(255)",
        "target_students": "VARCHAR(255)",
        "contact_name": "VARCHAR(64)",
        "contact_mobile": "VARCHAR(32)",
        "location": "VARCHAR(255)",
        "description": "TEXT",
        "contest_year": "INTEGER",
        "rule_attachment_id": "BIGINT",
    },
    "contest_registration": {
        "project_name": "VARCHAR(255)",
        "instructor_name": "VARCHAR(64)",
        "instructor_mobile": "VARCHAR(32)",
        "emergency_contact": "VARCHAR(64)",
        "emergency_mobile": "VARCHAR(32)",
        "source_type": "VARCHAR(32)",
        "remark": "VARCHAR(500)",
    },
    "notice_message": {
        "contest_id": "BIGINT",
        "target_role": "VARCHAR(64)",
        "target_user_ids": "VARCHAR(500)",
        "target_status": "VARCHAR(32)",
        "priority": "VARCHAR(16)",
        "summary": "VARCHAR(255)",
        "planned_send_at": "TIMESTAMP",
        "sent_at": "TIMESTAMP",
        "source_key": "VARCHAR(255)",
        "todo_rule_id": "BIGINT",
        "last_error": "VARCHAR(255)",
    },
    "contest_result": {
        "score": "FLOAT",
        "ranking": "INTEGER",
        "certificate_no": "VARCHAR(64)",
        "archive_remark": "VARCHAR(500)",
    },
    "registration_material": {
        "attachment_id": "BIGINT",
    },
    "export_task": {
        "task_name": "VARCHAR(128)",
        "progress": "INTEGER",
        "current_step": "VARCHAR(255)",
        "error_message": "VARCHAR(500)",
        "request_payload_json": "TEXT",
        "started_at": "TIMESTAMP",
        "finished_at": "TIMESTAMP",
        "retry_count": "INTEGER",
    },
}


def ensure_schema_columns():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    for table_name, columns in ADDITIONAL_COLUMNS.items():
        if table_name not in table_names:
            continue
        existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
        missing = [(name, ddl) for name, ddl in columns.items() if name not in existing_columns]
        for column_name, ddl in missing:
            db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    db.session.commit()
