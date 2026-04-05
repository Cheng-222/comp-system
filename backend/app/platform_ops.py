import json
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from flask import current_app
from sqlalchemy import MetaData, Table, select

from .config import REPO_ROOT
from .errors import APIError
from .extensions import db


STORAGE_DRIVER_KEY = "competition.storage.driver"
STORAGE_ROOT_KEY = "competition.storage.root"
STORAGE_LAYOUT_KEY = "competition.storage.layout"
BACKUP_DIR_KEY = "competition.backup.dir"
BACKUP_KEEP_COUNT_KEY = "competition.backup.keepCount"
BACKUP_INCLUDE_UPLOADS_KEY = "competition.backup.includeUploads"
BACKUP_RUNTIME_KEYS = {
    STORAGE_DRIVER_KEY,
    STORAGE_ROOT_KEY,
    STORAGE_LAYOUT_KEY,
    BACKUP_DIR_KEY,
    BACKUP_KEEP_COUNT_KEY,
    BACKUP_INCLUDE_UPLOADS_KEY,
}
SUPPORTED_STORAGE_DRIVERS = {"local"}
SUPPORTED_STORAGE_LAYOUTS = {"flat", "dated"}


def _get_runtime_config_value(config_key, fallback=""):
    from .system_compat_store import get_config_value

    value = str(get_config_value(config_key) or "").strip()
    return value if value else fallback


import tempfile
import os

def resolve_runtime_path(value, fallback):
    # 在Vercel环境中使用临时目录
    if os.getenv('VERCEL') == '1':
        if fallback in ['uploads', 'backups']:
            return Path(tempfile.gettempdir()) / fallback
    
    raw = str(value or fallback).strip() or fallback
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / raw
    return path.resolve()


def active_storage_driver():
    driver = _get_runtime_config_value(STORAGE_DRIVER_KEY, "local").lower()
    return driver if driver in SUPPORTED_STORAGE_DRIVERS else "local"


def active_storage_layout():
    layout = _get_runtime_config_value(STORAGE_LAYOUT_KEY, "flat").lower()
    return layout if layout in SUPPORTED_STORAGE_LAYOUTS else "flat"


def upload_root_path():
    configured = _get_runtime_config_value(STORAGE_ROOT_KEY, current_app.config["UPLOAD_DIR"])
    return resolve_runtime_path(configured, current_app.config["UPLOAD_DIR"])


def backup_root_path():
    configured = _get_runtime_config_value(BACKUP_DIR_KEY, "backups")
    return resolve_runtime_path(configured, "backups")


def backup_keep_count():
    raw_value = _get_runtime_config_value(BACKUP_KEEP_COUNT_KEY, "5")
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return 5


def include_uploads_by_default():
    return _get_runtime_config_value(BACKUP_INCLUDE_UPLOADS_KEY, "Y").upper() != "N"


def build_storage_subdir(subdir):
    base_dir = upload_root_path()
    layout = active_storage_layout()
    if layout == "dated":
        stamp = datetime.now().strftime("%Y/%m")
        return (base_dir / subdir / stamp).resolve()
    return (base_dir / subdir).resolve()


def export_dir_path():
    return build_storage_subdir("exports")


def ensure_runtime_directories():
    upload_root_path().mkdir(parents=True, exist_ok=True)
    backup_root_path().mkdir(parents=True, exist_ok=True)


def validate_runtime_config(payload):
    config_key = str(payload.get("configKey") or "").strip()
    config_value = str(payload.get("configValue") or "").strip()
    if config_key == STORAGE_DRIVER_KEY and config_value and config_value not in SUPPORTED_STORAGE_DRIVERS:
        raise APIError("当前仅支持 local 存储驱动")
    if config_key == STORAGE_LAYOUT_KEY and config_value and config_value not in SUPPORTED_STORAGE_LAYOUTS:
        raise APIError("存储布局仅支持 flat 或 dated")
    if config_key == BACKUP_KEEP_COUNT_KEY:
        try:
            if int(config_value) < 1:
                raise APIError("备份保留数量不能小于 1")
        except (TypeError, ValueError):
            raise APIError("备份保留数量必须为正整数")
    if config_key == BACKUP_INCLUDE_UPLOADS_KEY and config_value and config_value.upper() not in {"Y", "N"}:
        raise APIError("是否备份附件仅支持 Y 或 N")


def _serialize_backup_value(value):
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    return value


def _deserialize_backup_value(value):
    if not isinstance(value, dict):
        return value
    value_type = value.get("__type__")
    if value_type == "datetime":
        return datetime.fromisoformat(str(value.get("value") or ""))
    if value_type == "date":
        return date.fromisoformat(str(value.get("value") or ""))
    return value


def _reflect_tables():
    metadata = MetaData()
    metadata.reflect(bind=db.engine)
    return [table for table in metadata.sorted_tables if not table.name.startswith("sqlite_")]


def _table_snapshot(table):
    rows = []
    for row in db.session.execute(select(table)).mappings():
        payload = {}
        for column in table.columns:
            payload[column.name] = _serialize_backup_value(row.get(column.name))
        rows.append(payload)
    return rows


def _snapshot_config_value(snapshot, config_key):
    for item in snapshot.get("system_config", []):
        if item.get("config_key") == config_key:
            return item.get("config_value") or ""
    return ""


def _extract_upload_root_from_snapshot(snapshot):
    configured = str(_snapshot_config_value(snapshot, STORAGE_ROOT_KEY) or "").strip()
    if configured:
        return resolve_runtime_path(configured, current_app.config["UPLOAD_DIR"])
    return upload_root_path()


def _extract_backup_root_from_snapshot(snapshot):
    configured = str(_snapshot_config_value(snapshot, BACKUP_DIR_KEY) or "").strip()
    if configured:
        return resolve_runtime_path(configured, "backups")
    return backup_root_path()


def _apply_attachment_path_rebase(snapshot, original_root, target_root):
    if not original_root or not target_root:
        return
    source_prefix = str(Path(original_root).resolve())
    target_prefix = str(Path(target_root).resolve())
    if source_prefix == target_prefix:
        return
    for row in snapshot.get("attachment_info", []):
        current_path = str(row.get("file_path") or "").strip()
        if current_path.startswith(source_prefix):
            row["file_path"] = current_path.replace(source_prefix, target_prefix, 1)


def list_backup_files():
    root = backup_root_path()
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in sorted(root.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True):
        stat = item.stat()
        rows.append(
            {
                "fileName": item.name,
                "fileSize": stat.st_size,
                "createdAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "path": str(item),
            }
        )
    return rows


def prune_backup_files():
    rows = list_backup_files()
    for item in rows[backup_keep_count():]:
        Path(item["path"]).unlink(missing_ok=True)


def storage_runtime_profile():
    ensure_runtime_directories()
    upload_root = upload_root_path()
    backup_root = backup_root_path()
    backup_files = list_backup_files()
    writable_probe = upload_root / f".storage_probe_{uuid4().hex}"
    writable = False
    try:
        writable_probe.write_text("ok", encoding="utf-8")
        writable = True
    finally:
        writable_probe.unlink(missing_ok=True)
    return {
        "storage": {
            "driver": active_storage_driver(),
            "layout": active_storage_layout(),
            "rootPath": str(upload_root),
            "writable": writable,
            "supportedDrivers": sorted(SUPPORTED_STORAGE_DRIVERS),
            "supportedLayouts": sorted(SUPPORTED_STORAGE_LAYOUTS),
        },
        "backup": {
            "rootPath": str(backup_root),
            "keepCount": backup_keep_count(),
            "includeUploadsByDefault": include_uploads_by_default(),
            "totalFiles": len(backup_files),
            "latestFile": backup_files[0] if backup_files else None,
            "files": backup_files,
        },
    }


def create_system_backup(created_by, include_uploads=None):
    ensure_runtime_directories()
    upload_root = upload_root_path()
    backup_root = backup_root_path()
    include_uploads = include_uploads_by_default() if include_uploads is None else bool(include_uploads)

    metadata_tables = _reflect_tables()
    snapshot = {table.name: _table_snapshot(table) for table in metadata_tables}
    created_at = datetime.now()
    file_name = f"competition-backup-{created_at.strftime('%Y%m%d-%H%M%S')}.zip"
    target_path = backup_root / file_name
    manifest = {
        "version": 1,
        "createdAt": created_at.isoformat(),
        "createdBy": int(created_by or 0),
        "storageDriver": active_storage_driver(),
        "storageLayout": active_storage_layout(),
        "storageRoot": str(upload_root),
        "backupRoot": str(backup_root),
        "includeUploads": include_uploads,
        "tables": {name: len(rows) for name, rows in snapshot.items()},
    }

    with ZipFile(target_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
        if include_uploads and upload_root.exists():
            for file_path in upload_root.rglob("*"):
                if file_path.is_dir():
                    continue
                if backup_root in file_path.parents:
                    continue
                relative_path = file_path.relative_to(upload_root)
                archive.write(file_path, arcname=str(Path("uploads") / relative_path))

    prune_backup_files()
    file_stat = target_path.stat()
    return {
        "fileName": target_path.name,
        "fileSize": file_stat.st_size,
        "createdAt": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
        "includeUploads": include_uploads,
        "path": str(target_path),
    }


def backup_file_path(file_name):
    file_path = (backup_root_path() / Path(str(file_name or "")).name).resolve()
    backup_root = backup_root_path().resolve()
    if backup_root not in file_path.parents and file_path != backup_root:
        raise APIError("备份文件不存在")
    if not file_path.exists() or not file_path.is_file():
        raise APIError("备份文件不存在")
    return file_path


def restore_system_backup(file_name):
    ensure_runtime_directories()
    file_path = backup_file_path(file_name)
    with ZipFile(file_path, "r") as archive:
        if "snapshot.json" not in archive.namelist():
            raise APIError("备份文件缺少 snapshot.json")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8")) if "manifest.json" in archive.namelist() else {}
        snapshot = json.loads(archive.read("snapshot.json").decode("utf-8"))

        original_upload_root = Path(str(manifest.get("storageRoot") or upload_root_path())).resolve()
        target_upload_root = _extract_upload_root_from_snapshot(snapshot)
        target_backup_root = _extract_backup_root_from_snapshot(snapshot)
        _apply_attachment_path_rebase(snapshot, original_upload_root, target_upload_root)

        metadata_tables = _reflect_tables()
        table_map = {table.name: table for table in metadata_tables}
        for table in reversed(metadata_tables):
            db.session.execute(table.delete())
        for table in metadata_tables:
            rows = snapshot.get(table.name, [])
            if not rows:
                continue
            payloads = []
            for row in rows:
                payload = {}
                for column in table.columns:
                    payload[column.name] = _deserialize_backup_value(row.get(column.name))
                payloads.append(payload)
            db.session.execute(table.insert(), payloads)
        db.session.commit()

        if target_upload_root.exists():
            shutil.rmtree(target_upload_root)
        target_upload_root.mkdir(parents=True, exist_ok=True)
        target_backup_root.mkdir(parents=True, exist_ok=True)

        if bool(manifest.get("includeUploads")):
            for member_name in archive.namelist():
                if not member_name.startswith("uploads/") or member_name.endswith("/"):
                    continue
                relative_path = Path(member_name).relative_to("uploads")
                target_path = target_upload_root / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member_name, "r") as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

    return {
        "fileName": file_path.name,
        "restoredAt": datetime.now().isoformat(),
        "tableCount": len(table_map),
        "uploadRoot": str(target_upload_root),
    }
