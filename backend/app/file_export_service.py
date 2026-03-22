import json
import os
import re
import shutil
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from flask import current_app
from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer

from .access import assigned_contest_ids, is_admin_user
from .data_scope import selected_college_names
from .errors import APIError
from .excel_utils import create_binary_attachment
from .extensions import db
from .file_center_service import FILE_CATEGORY_META, visible_assets
from .models import (
    AttachmentInfo,
    ContestInfo,
    FileDeliveryChannel,
    FileDeliveryRecord,
    FileExportBatch,
    FileExportPolicy,
    SysUser,
    StudentInfo,
)
from .platform_ops import resolve_runtime_path
from .time_utils import now_beijing


POLICY_STATUS_ENABLED = "enabled"
POLICY_STATUS_DISABLED = "disabled"
CHANNEL_STATUS_ENABLED = "enabled"
CHANNEL_STATUS_DISABLED = "disabled"
DELIVERY_CHANNEL_TYPES = {"local_folder", "baidu_pan"}
POLICY_SCHEDULE_TYPES = {"manual", "daily"}
POLICY_INCREMENT_MODES = {"full", "delta"}
BATCH_ACTIVE_STATUSES = {"pending", "processing"}
BATCH_RETRYABLE_STATUSES = {"failed", "partial_success"}
BATCH_TERMINAL_STATUSES = {"completed", "failed", "partial_success"}
DELIVERY_TERMINAL_STATUSES = {"completed", "failed"}
DEFAULT_FOLDER_TEMPLATE = "{categoryName}/{contestName}/{college}/{date}"
DEFAULT_FILE_TEMPLATE = "{policyName}_{date}_{batchNo}.zip"
DEFAULT_CHANNEL_FOLDER_TEMPLATE = "{policyName}/{date}"
BAIDU_PAN_MKDIR_ENDPOINT = "https://d.pcs.baidu.com/rest/2.0/pcs/file"
BAIDU_PAN_UPLOAD_ENDPOINT = "https://c.pcs.baidu.com/rest/2.0/pcs/file"
BAIDU_OAUTH_AUTHORIZE_ENDPOINT = "https://openapi.baidu.com/oauth/2.0/authorize"
BAIDU_OAUTH_TOKEN_ENDPOINT = "https://openapi.baidu.com/oauth/2.0/token"
BAIDU_OAUTH_SCOPE = "basic,netdisk"
BAIDU_TOKEN_REFRESH_WINDOW_SECONDS = 300
BAIDU_REQUEST_RETRY_LIMIT = 3
FILE_EXPORT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="competition-file-export")
SCHEDULER_THREADS = {}
INVALID_PATH_CHARS_PATTERN = re.compile(r'[<>:"/\\\\|?*]+')
TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _json_loads(raw_value, fallback):
    try:
        payload = json.loads(raw_value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return payload if isinstance(payload, type(fallback)) else fallback


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def _parse_int_list(values):
    result = []
    seen = set()
    for item in values or []:
        try:
            current = int(item)
        except (TypeError, ValueError):
            continue
        if current in seen:
            continue
        seen.add(current)
        result.append(current)
    return result


def _parse_string_list(values):
    result = []
    seen = set()
    for item in values or []:
        current = str(item or "").strip()
        if not current or current in seen:
            continue
        seen.add(current)
        result.append(current)
    return result


def _channel_config(channel):
    return _json_loads(getattr(channel, "config_json", "{}"), {})


def _policy_scope(policy):
    payload = _json_loads(getattr(policy, "scope_json", "{}"), {})
    return {
        "categoryCodes": _parse_string_list(payload.get("categoryCodes") or []),
        "contestIds": _parse_int_list(payload.get("contestIds") or []),
        "collegeNames": _parse_string_list(payload.get("collegeNames") or []),
        "keyword": str(payload.get("keyword") or "").strip(),
    }


def _policy_channel_ids(policy):
    return _parse_int_list(_json_loads(getattr(policy, "delivery_channel_ids_json", "[]"), []))


def _mask_secret(value):
    raw = str(value or "").strip()
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}***{raw[-4:]}"


def _app_config_value(name, default=""):
    try:
        return current_app.config.get(name, default)
    except RuntimeError:
        return os.getenv(name, default)


def _baidu_oauth_settings():
    app_key = str(_app_config_value("BAIDU_PAN_APP_KEY", "") or "").strip()
    secret_key = str(_app_config_value("BAIDU_PAN_SECRET_KEY", "") or "").strip()
    callback_url = str(_app_config_value("BAIDU_PAN_CALLBACK_URL", "http://localhost:5002/api/integrations/baidu-pan/callback") or "").strip()
    sign_key = str(_app_config_value("BAIDU_PAN_SIGN_KEY", "") or "").strip() or str(_app_config_value("SECRET_KEY", "") or "").strip()
    if not app_key or not secret_key:
        raise APIError("百度网盘应用配置不完整，请先设置 BAIDU_PAN_APP_KEY 和 BAIDU_PAN_SECRET_KEY")
    if not callback_url:
        raise APIError("百度网盘回调地址未配置")
    if not sign_key:
        raise APIError("百度网盘签名密钥未配置")
    return {
        "app_key": app_key,
        "secret_key": secret_key,
        "sign_key": sign_key,
        "callback_url": callback_url,
        "scope": BAIDU_OAUTH_SCOPE,
    }


def _baidu_oauth_serializer():
    settings = _baidu_oauth_settings()
    return URLSafeTimedSerializer(settings["sign_key"], salt="competition-baidu-pan-oauth")


def _parse_datetime_value(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _write_channel_config(channel, config):
    channel.config_json = _json_dumps(config)
    db.session.add(channel)


def _channel_response_config(config):
    payload = dict(config or {})
    access_token = str(payload.get("accessToken") or "").strip()
    refresh_token = str(payload.get("refreshToken") or "").strip()
    auth_mode = str(payload.get("authMode") or "").strip()
    if not auth_mode:
        auth_mode = "oauth" if refresh_token else "manual" if access_token else ""
    oauth_status = str(payload.get("oauthStatus") or "").strip()
    if not oauth_status:
        oauth_status = "authorized" if access_token else "pending"
    return {
        "rootPath": str(payload.get("rootPath") or "").strip(),
        "folderTemplate": str(payload.get("folderTemplate") or DEFAULT_CHANNEL_FOLDER_TEMPLATE).strip() or DEFAULT_CHANNEL_FOLDER_TEMPLATE,
        "mockMode": bool(payload.get("mockMode")),
        "mockRoot": str(payload.get("mockRoot") or "").strip(),
        "conflictMode": str(payload.get("conflictMode") or "overwrite").strip() or "overwrite",
        "accessToken": "",
        "accessTokenMasked": _mask_secret(access_token) if access_token else "",
        "accessTokenConfigured": bool(access_token),
        "refreshTokenMasked": _mask_secret(refresh_token) if refresh_token else "",
        "authorizedAt": str(payload.get("authorizedAt") or "").strip(),
        "tokenExpiresAt": str(payload.get("tokenExpiresAt") or "").strip(),
        "scope": str(payload.get("scope") or "").strip(),
        "authMode": auth_mode,
        "oauthStatus": oauth_status,
        "callbackUrl": str(_app_config_value("BAIDU_PAN_CALLBACK_URL", "http://localhost:5002/api/integrations/baidu-pan/callback") or payload.get("callbackUrl") or "").strip(),
    }


def _token_expired(expires_at, refresh_window=BAIDU_TOKEN_REFRESH_WINDOW_SECONDS):
    if expires_at is None:
        return False
    return expires_at <= now_beijing() + timedelta(seconds=refresh_window)


def _sanitize_segment(value, fallback="未命名"):
    text = str(value or "").strip()
    text = INVALID_PATH_CHARS_PATTERN.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def _template_context(base_context, fallback="未命名"):
    return {key: _sanitize_segment(value, fallback) for key, value in (base_context or {}).items()}


def _render_template(template, context, fallback="未命名"):
    source = str(template or "").strip()
    if not source:
        return ""

    safe_context = _template_context(context, fallback)

    def replace(match):
        key = match.group(1)
        return safe_context.get(key, fallback)

    return TEMPLATE_PATTERN.sub(replace, source)


def _render_folder_path(template, context):
    rendered = _render_template(template or DEFAULT_FOLDER_TEMPLATE, context)
    segments = []
    for item in rendered.replace("\\", "/").split("/"):
        current = _sanitize_segment(item, fallback="未分组")
        if current:
            segments.append(current)
    return "/".join(segments)


def _render_file_name(template, context):
    rendered = _render_template(template or DEFAULT_FILE_TEMPLATE, context)
    file_name = _sanitize_segment(rendered, fallback="导出批次")
    if not file_name.lower().endswith(".zip"):
        file_name = f"{file_name}.zip"
    return file_name


def _parse_schedule_time(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError as error:
        raise APIError("执行时间格式错误，请使用 HH:mm") from error


def compute_next_run_at(schedule_type, schedule_time, now_value=None):
    if schedule_type != "daily":
        return None
    schedule_clock = _parse_schedule_time(schedule_time)
    if schedule_clock is None:
        raise APIError("每日执行规则必须配置执行时间")
    current = now_value or now_beijing()
    candidate = current.replace(hour=schedule_clock.hour, minute=schedule_clock.minute, second=0, microsecond=0)
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate


def file_export_scheduler_enabled():
    return str(os.getenv("APP_FILE_EXPORT_SCHEDULER_AUTO_START", "Y")).strip().upper() != "N"


def file_export_scan_interval_seconds():
    raw_value = str(os.getenv("APP_FILE_EXPORT_SCAN_INTERVAL_SECONDS", "30")).strip()
    try:
        return max(10, int(raw_value))
    except (TypeError, ValueError):
        return 30


def serialize_channel(channel, include_config=False):
    config = _channel_config(channel)
    safe_config = _channel_response_config(config)
    payload = {
        "id": channel.id,
        "channelName": channel.channel_name,
        "channelType": channel.channel_type,
        "status": channel.status,
        "remark": channel.remark,
        "createdBy": channel.created_by,
        "createdAt": channel.created_at.isoformat() if channel.created_at else None,
        "updatedAt": channel.updated_at.isoformat() if channel.updated_at else None,
        "lastValidatedAt": channel.last_validated_at.isoformat() if channel.last_validated_at else None,
        "lastValidationStatus": channel.last_validation_status,
        "lastError": channel.last_error or "",
        "configPreview": safe_config,
    }
    if include_config:
        payload["config"] = safe_config
    return payload


def serialize_policy(policy):
    scope = _policy_scope(policy)
    channel_ids = _policy_channel_ids(policy)
    channels = []
    if channel_ids:
        channel_map = {item.id: item for item in FileDeliveryChannel.query.filter(FileDeliveryChannel.id.in_(channel_ids)).all()}
        channels = [channel_map[item_id] for item_id in channel_ids if item_id in channel_map]
    creator = db.session.get(SysUser, policy.created_by) if policy.created_by else None
    return {
        "id": policy.id,
        "policyName": policy.policy_name,
        "status": policy.status,
        "scheduleType": policy.schedule_type,
        "scheduleTime": policy.schedule_time or "",
        "incrementMode": policy.increment_mode,
        "scope": scope,
        "folderTemplate": policy.folder_template,
        "fileNameTemplate": policy.file_name_template,
        "includeManifest": str(policy.include_manifest or "Y").upper() != "N",
        "deliveryChannelIds": channel_ids,
        "deliveryChannelNames": [item.channel_name for item in channels],
        "remark": policy.remark,
        "createdBy": policy.created_by,
        "createdByName": creator.real_name if creator else None,
        "createdAt": policy.created_at.isoformat() if policy.created_at else None,
        "updatedAt": policy.updated_at.isoformat() if policy.updated_at else None,
        "lastRunAt": policy.last_run_at.isoformat() if policy.last_run_at else None,
        "nextRunAt": policy.next_run_at.isoformat() if policy.next_run_at else None,
        "lastStatus": policy.last_status or "",
        "lastError": policy.last_error or "",
    }


def serialize_delivery_record(record):
    channel = record.channel or db.session.get(FileDeliveryChannel, record.channel_id)
    return {
        "id": record.id,
        "channelId": record.channel_id,
        "channelName": channel.channel_name if channel else None,
        "channelType": channel.channel_type if channel else None,
        "status": record.status,
        "progress": int(record.progress or 0),
        "currentStep": record.current_step or "",
        "targetPath": record.target_path or "",
        "deliveredFileName": record.delivered_file_name or "",
        "successCount": int(record.success_count or 0),
        "failCount": int(record.fail_count or 0),
        "errorMessage": record.error_message or "",
        "responseSnapshot": _json_loads(record.response_snapshot_json or "{}", {}),
        "startedAt": record.started_at.isoformat() if record.started_at else None,
        "finishedAt": record.finished_at.isoformat() if record.finished_at else None,
        "updatedAt": record.updated_at.isoformat() if record.updated_at else None,
        "retryCount": int(record.retry_count or 0),
    }


def serialize_batch(batch, include_details=False):
    creator = db.session.get(SysUser, batch.created_by) if batch.created_by else None
    attachment = db.session.get(AttachmentInfo, batch.attachment_id) if batch.attachment_id else None
    policy = batch.policy or db.session.get(FileExportPolicy, batch.policy_id)
    manifest = _json_loads(batch.manifest_json or "{}", {})
    deliveries = FileDeliveryRecord.query.filter_by(batch_id=batch.id).order_by(FileDeliveryRecord.id.asc()).all()
    payload = {
        "id": batch.id,
        "policyId": batch.policy_id,
        "policyName": policy.policy_name if policy else None,
        "batchNo": batch.batch_no,
        "triggerType": batch.trigger_type,
        "status": batch.status,
        "progress": int(batch.progress or 0),
        "currentStep": batch.current_step or "",
        "errorMessage": batch.error_message or "",
        "sourceCount": int(batch.source_count or 0),
        "successCount": int(batch.success_count or 0),
        "failCount": int(batch.fail_count or 0),
        "attachmentId": batch.attachment_id,
        "fileName": attachment.file_name if attachment else batch.package_file_name,
        "fileSize": int(attachment.file_size or 0) if attachment else 0,
        "createdBy": batch.created_by,
        "createdByName": creator.real_name if creator else None,
        "createdAt": batch.created_at.isoformat() if batch.created_at else None,
        "updatedAt": batch.updated_at.isoformat() if batch.updated_at else None,
        "startedAt": batch.started_at.isoformat() if batch.started_at else None,
        "finishedAt": batch.finished_at.isoformat() if batch.finished_at else None,
        "scheduledFor": batch.scheduled_for.isoformat() if batch.scheduled_for else None,
        "retryCount": int(batch.retry_count or 0),
        "deliverySummary": {
            "total": len(deliveries),
            "completed": sum(1 for item in deliveries if item.status == "completed"),
            "failed": sum(1 for item in deliveries if item.status == "failed"),
            "processing": sum(1 for item in deliveries if item.status in {"pending", "processing"}),
        },
        "canRetry": batch.status in BATCH_RETRYABLE_STATUSES,
    }
    if include_details:
        payload["policy"] = serialize_policy(policy) if policy else None
        payload["manifest"] = manifest
        payload["deliveries"] = [serialize_delivery_record(item) for item in deliveries]
        payload["requestSnapshot"] = _json_loads(batch.request_snapshot_json or "{}", {})
        payload["resultSnapshot"] = _json_loads(batch.result_snapshot_json or "{}", {})
    return payload


def export_metadata(user):
    contest_ids = assigned_contest_ids(user=user)
    contest_query = ContestInfo.query.order_by(ContestInfo.contest_year.desc(), ContestInfo.id.desc())
    if contest_ids is not None:
        contest_query = contest_query.filter(ContestInfo.id.in_(list(contest_ids) or [-1]))
    college_query = StudentInfo.query.with_entities(StudentInfo.college).filter(StudentInfo.college.isnot(None), StudentInfo.college != "")
    scoped_colleges = selected_college_names(user)
    if scoped_colleges is not None:
        college_query = college_query.filter(StudentInfo.college.in_(tuple(sorted(scoped_colleges)) or ("__none__",)))
    categories = []
    for code, meta in FILE_CATEGORY_META.items():
        if code == "backup_package" and not is_admin_user(user):
            continue
        categories.append({"value": code, "label": meta["label"], "groupCode": meta["groupCode"], "groupName": meta["groupLabel"]})
    channels_query = FileDeliveryChannel.query.filter(FileDeliveryChannel.status == CHANNEL_STATUS_ENABLED).order_by(FileDeliveryChannel.id.desc())
    if not is_admin_user(user):
        channels_query = channels_query.filter(FileDeliveryChannel.channel_type.in_(("local_folder", "baidu_pan")))
    return {
        "categoryOptions": categories,
        "contestOptions": [{"id": item.id, "contestName": item.contest_name, "contestYear": item.contest_year} for item in contest_query.all()],
        "collegeOptions": [item[0] for item in college_query.distinct().order_by(StudentInfo.college.asc()).all()],
        "channelOptions": [serialize_channel(item) for item in channels_query.all()],
        "templateVariables": [
            {"key": "{policyName}", "label": "规则名称"},
            {"key": "{batchNo}", "label": "批次号"},
            {"key": "{date}", "label": "当前日期"},
            {"key": "{datetime}", "label": "当前时间"},
            {"key": "{categoryName}", "label": "文件分类"},
            {"key": "{contestName}", "label": "赛事名称"},
            {"key": "{college}", "label": "学院"},
            {"key": "{studentName}", "label": "学生"},
            {"key": "{sourceName}", "label": "来源名称"},
        ],
    }


def normalize_channel_payload(payload, existing=None):
    channel_name = str(payload.get("channelName") or "").strip()
    if not channel_name:
        raise APIError("渠道名称不能为空")
    channel_type = str(payload.get("channelType") or "local_folder").strip()
    if channel_type not in DELIVERY_CHANNEL_TYPES:
        raise APIError("投递渠道类型不支持")
    status = str(payload.get("status") or CHANNEL_STATUS_ENABLED).strip()
    if status not in {CHANNEL_STATUS_ENABLED, CHANNEL_STATUS_DISABLED}:
        raise APIError("渠道状态不合法")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    existing_config = _channel_config(existing) if existing is not None else {}
    root_path = str(config.get("rootPath") or "").strip()
    folder_template = str(config.get("folderTemplate") or DEFAULT_CHANNEL_FOLDER_TEMPLATE).strip() or DEFAULT_CHANNEL_FOLDER_TEMPLATE
    normalized_config = {
        "rootPath": root_path,
        "folderTemplate": folder_template,
    }
    if channel_type == "local_folder":
        if not root_path:
            raise APIError("本地目录渠道必须配置目标根目录")
    else:
        mock_mode = bool(config.get("mockMode"))
        if not root_path:
            raise APIError("百度网盘渠道必须配置目标网盘根目录")
        normalized_config.update(
            {
                "mockMode": mock_mode,
                "mockRoot": str(config.get("mockRoot") or existing_config.get("mockRoot") or "").strip(),
                "conflictMode": str(config.get("conflictMode") or existing_config.get("conflictMode") or "overwrite").strip() or "overwrite",
                "callbackUrl": str(_app_config_value("BAIDU_PAN_CALLBACK_URL", "http://localhost:5002/api/integrations/baidu-pan/callback") or existing_config.get("callbackUrl") or "").strip(),
            }
        )
        access_token = str(config.get("accessToken") or "").strip()
        if access_token:
            normalized_config.update(
                {
                    "accessToken": access_token,
                    "refreshToken": "",
                    "authorizedAt": now_beijing().isoformat(),
                    "tokenExpiresAt": "",
                    "scope": str(existing_config.get("scope") or "").strip(),
                    "authMode": "manual",
                    "oauthStatus": "manual",
                }
            )
        else:
            normalized_config.update(
                {
                    "accessToken": str(existing_config.get("accessToken") or "").strip(),
                    "refreshToken": str(existing_config.get("refreshToken") or "").strip(),
                    "authorizedAt": str(existing_config.get("authorizedAt") or "").strip(),
                    "tokenExpiresAt": str(existing_config.get("tokenExpiresAt") or "").strip(),
                    "scope": str(existing_config.get("scope") or "").strip(),
                    "authMode": str(existing_config.get("authMode") or "").strip(),
                    "oauthStatus": str(existing_config.get("oauthStatus") or ("authorized" if existing_config.get("accessToken") else "pending")).strip(),
                }
            )
    return {
        "channel_name": channel_name,
        "channel_type": channel_type,
        "status": status,
        "config_json": _json_dumps(normalized_config),
        "remark": str(payload.get("remark") or "").strip(),
    }


def normalize_policy_payload(payload, actor, existing=None):
    policy_name = str(payload.get("policyName") or "").strip()
    if not policy_name:
        raise APIError("规则名称不能为空")
    schedule_type = str(payload.get("scheduleType") or "manual").strip()
    if schedule_type not in POLICY_SCHEDULE_TYPES:
        raise APIError("调度类型不合法")
    schedule_time = str(payload.get("scheduleTime") or "").strip()
    if schedule_type == "daily":
        _parse_schedule_time(schedule_time)
    increment_mode = str(payload.get("incrementMode") or "full").strip()
    if increment_mode not in POLICY_INCREMENT_MODES:
        raise APIError("增量模式不合法")
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    category_codes = _parse_string_list(scope.get("categoryCodes") or [])
    contest_ids = _parse_int_list(scope.get("contestIds") or [])
    college_names = _parse_string_list(scope.get("collegeNames") or [])
    keyword = str(scope.get("keyword") or "").strip()
    unknown_categories = [item for item in category_codes if item not in FILE_CATEGORY_META]
    if unknown_categories:
        raise APIError("规则中存在无效的文件分类")
    allowed_contest_ids = assigned_contest_ids(user=actor)
    if allowed_contest_ids is not None and any(item not in allowed_contest_ids for item in contest_ids):
        raise APIError("规则中包含当前账号无权导出的赛事")
    allowed_colleges = selected_college_names(actor)
    if allowed_colleges is not None and any(item not in allowed_colleges for item in college_names):
        raise APIError("规则中包含当前账号无权导出的学院")
    delivery_channel_ids = _parse_int_list(payload.get("deliveryChannelIds") or [])
    if delivery_channel_ids:
        channel_rows = FileDeliveryChannel.query.filter(FileDeliveryChannel.id.in_(delivery_channel_ids)).all()
        if len(channel_rows) != len(delivery_channel_ids):
            raise APIError("存在不存在的投递渠道")
        if any(item.status != CHANNEL_STATUS_ENABLED for item in channel_rows):
            raise APIError("投递渠道必须是启用状态")
    include_manifest = "Y" if bool(payload.get("includeManifest", True)) else "N"
    status = str(payload.get("status") or POLICY_STATUS_ENABLED).strip()
    if status not in {POLICY_STATUS_ENABLED, POLICY_STATUS_DISABLED}:
        raise APIError("规则状态不合法")
    next_run_at = None
    if status == POLICY_STATUS_ENABLED and schedule_type == "daily":
        next_run_at = compute_next_run_at(schedule_type, schedule_time)
    elif existing is not None and existing.schedule_type == "daily" and existing.status == POLICY_STATUS_ENABLED and status == POLICY_STATUS_ENABLED:
        next_run_at = compute_next_run_at(schedule_type, schedule_time)
    return {
        "policy_name": policy_name,
        "status": status,
        "schedule_type": schedule_type,
        "schedule_time": schedule_time,
        "increment_mode": increment_mode,
        "scope_json": _json_dumps(
            {
                "categoryCodes": category_codes,
                "contestIds": contest_ids,
                "collegeNames": college_names,
                "keyword": keyword,
            }
        ),
        "folder_template": str(payload.get("folderTemplate") or DEFAULT_FOLDER_TEMPLATE).strip() or DEFAULT_FOLDER_TEMPLATE,
        "file_name_template": str(payload.get("fileNameTemplate") or DEFAULT_FILE_TEMPLATE).strip() or DEFAULT_FILE_TEMPLATE,
        "include_manifest": include_manifest,
        "delivery_channel_ids_json": _json_dumps(delivery_channel_ids),
        "remark": str(payload.get("remark") or "").strip(),
        "next_run_at": next_run_at,
    }


def validate_channel_config(channel):
    config = _channel_config(channel)
    if channel.channel_type == "local_folder":
        target_root = resolve_runtime_path(config.get("rootPath"), "exports/local-delivery")
        target_root.mkdir(parents=True, exist_ok=True)
        probe_file = target_root / f".channel_probe_{uuid4().hex}"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        return {"channelType": channel.channel_type, "targetRoot": str(target_root), "mode": "local", "message": "本地目录可写"}
    if channel.channel_type == "baidu_pan":
        if bool(config.get("mockMode")):
            mock_root = resolve_runtime_path(config.get("mockRoot") or "mock_baidu_pan", "mock_baidu_pan")
            mock_root.mkdir(parents=True, exist_ok=True)
            probe_file = mock_root / f".channel_probe_{uuid4().hex}"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            return {"channelType": channel.channel_type, "targetRoot": config.get("rootPath") or "/", "mode": "mock", "mockRoot": str(mock_root), "message": "百度网盘 mock 目录可写"}
        access_token = resolve_baidu_access_token(channel)
        _ensure_baidu_folder(access_token, config.get("rootPath") or "/")
        safe_config = _channel_response_config(_channel_config(channel))
        return {
            "channelType": channel.channel_type,
            "targetRoot": safe_config.get("rootPath") or "/",
            "mode": "oauth" if safe_config.get("authMode") == "oauth" else "remote",
            "message": "百度网盘授权有效，可执行远程上传",
            "authorizedAt": safe_config.get("authorizedAt") or "",
            "tokenExpiresAt": safe_config.get("tokenExpiresAt") or "",
            "oauthStatus": safe_config.get("oauthStatus") or "",
        }
    raise APIError("未知的投递渠道类型")


def ensure_policy_access(policy, user, write=False):
    if policy is None:
        raise APIError("导出规则不存在", status=404)
    if is_admin_user(user):
        return policy
    if int(policy.created_by or 0) != int(user.id):
        raise APIError("当前账号无权访问该导出规则", code=403, status=200)
    return policy


def ensure_channel_access(channel, user):
    if channel is None:
        raise APIError("投递渠道不存在", status=404)
    if not is_admin_user(user):
        raise APIError("当前账号无权管理投递渠道", code=403, status=200)
    return channel


def ensure_batch_access(batch, user):
    if batch is None:
        raise APIError("导出批次不存在", status=404)
    if is_admin_user(user):
        return batch
    if int(batch.created_by or 0) != int(user.id):
        raise APIError("当前账号无权查看该导出批次", code=403, status=200)
    return batch


def policy_query_for_user(user):
    query = FileExportPolicy.query.order_by(FileExportPolicy.id.desc())
    if not is_admin_user(user):
        query = query.filter(FileExportPolicy.created_by == user.id)
    return query


def channel_query_for_user(user):
    if not is_admin_user(user):
        raise APIError("当前账号无权查看投递渠道", code=403, status=200)
    return FileDeliveryChannel.query.order_by(FileDeliveryChannel.id.desc())


def batch_query_for_user(user):
    query = FileExportBatch.query.order_by(FileExportBatch.id.desc())
    if not is_admin_user(user):
        query = query.filter(FileExportBatch.created_by == user.id)
    return query


def _unique_arc_name(arc_name, used_names):
    candidate = arc_name
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate
    path = PurePosixPath(candidate)
    suffix = path.suffix
    stem = path.stem
    parent = str(path.parent) if str(path.parent) != "." else ""
    index = 2
    while True:
        next_name = f"{stem}_{index}{suffix}"
        candidate = f"{parent}/{next_name}" if parent else next_name
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def _batch_context(policy, batch, extra=None):
    base = {
        "policyName": policy.policy_name,
        "batchNo": batch.batch_no,
        "date": now_beijing().strftime("%Y-%m-%d"),
        "datetime": now_beijing().strftime("%Y-%m-%d_%H%M"),
        "contestName": "全部赛事",
        "college": "全部学院",
        "categoryName": "全部文件",
        "studentName": "全部学生",
        "sourceName": "文件归档",
    }
    if extra:
        base.update(extra)
    return base


def _filter_policy_assets(policy, user):
    scope = _policy_scope(policy)
    rows = visible_assets(user, include_internal=True)
    if scope["categoryCodes"]:
        rows = [item for item in rows if item["categoryCode"] in set(scope["categoryCodes"])]
    if scope["contestIds"]:
        target_ids = set(scope["contestIds"])
        rows = [item for item in rows if int(item.get("contestId") or 0) in target_ids]
    if scope["collegeNames"]:
        target_colleges = set(scope["collegeNames"])
        rows = [item for item in rows if str(item.get("college") or "").strip() in target_colleges]
    if scope["keyword"]:
        keyword = scope["keyword"].lower()
        rows = [
            item
            for item in rows
            if keyword in " ".join(
                str(item.get(field) or "").lower()
                for field in ("fileName", "sourceName", "contestName", "studentName", "college", "categoryName", "groupName")
            )
        ]
    if policy.increment_mode == "delta" and policy.last_run_at:
        rows = [item for item in rows if item.get("_createdAt") and item["_createdAt"] > policy.last_run_at]
    return rows


def _build_manifest_entries(policy, batch, assets):
    used_names = set()
    entries = []
    for item in assets:
        context = _batch_context(
            policy,
            batch,
            {
                "categoryName": item.get("categoryName") or "未分类",
                "categoryCode": item.get("categoryCode") or "other_file",
                "contestName": item.get("contestName") or "未关联赛事",
                "college": item.get("college") or "未归属学院",
                "studentName": item.get("studentName") or "未关联学生",
                "sourceName": item.get("sourceName") or item.get("fileName") or "文件",
            },
        )
        folder_path = _render_folder_path(policy.folder_template or DEFAULT_FOLDER_TEMPLATE, context)
        display_name = _sanitize_segment(item.get("fileName") or "文件", fallback="文件")
        package_path = f"{folder_path}/{display_name}" if folder_path else display_name
        package_path = _unique_arc_name(package_path, used_names)
        entries.append(
            {
                "assetType": item.get("assetType"),
                "assetId": item.get("assetId"),
                "categoryCode": item.get("categoryCode"),
                "categoryName": item.get("categoryName"),
                "contestId": item.get("contestId"),
                "contestName": item.get("contestName"),
                "studentId": item.get("studentId"),
                "studentName": item.get("studentName"),
                "college": item.get("college"),
                "sourceName": item.get("sourceName"),
                "fileName": item.get("fileName"),
                "fileSize": int(item.get("fileSize") or 0),
                "createdAt": item.get("createdAt"),
                "packagePath": package_path,
                "storagePath": item.get("_path"),
            }
        )
    return entries


def _build_package(policy, batch, entries):
    package_context = _batch_context(policy, batch)
    package_name = _render_file_name(policy.file_name_template or DEFAULT_FILE_TEMPLATE, package_context)
    manifest_payload = {
        "batchNo": batch.batch_no,
        "policyId": policy.id,
        "policyName": policy.policy_name,
        "triggerType": batch.trigger_type,
        "generatedAt": now_beijing().isoformat(),
        "sourceCount": len(entries),
        "entries": entries,
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for item in entries:
            storage_path = Path(str(item.get("storagePath") or ""))
            if not storage_path.exists():
                continue
            archive.write(storage_path, arcname=item["packagePath"])
        if str(policy.include_manifest or "Y").upper() != "N":
            archive.writestr("manifest.json", json.dumps(manifest_payload, ensure_ascii=False, indent=2))
    return package_name, buffer.getvalue(), manifest_payload


def _normalize_posix_path(*parts):
    path = PurePosixPath("/")
    for item in parts:
        current = str(item or "").strip().replace("\\", "/")
        if not current:
            continue
        path = path.joinpath(current.lstrip("/"))
    normalized = str(path)
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _build_channel_target_folder(channel, policy, batch):
    config = _channel_config(channel)
    context = _batch_context(policy, batch)
    folder_part = _render_folder_path(config.get("folderTemplate") or DEFAULT_CHANNEL_FOLDER_TEMPLATE, context)
    return _normalize_posix_path(config.get("rootPath") or "/", folder_part)


def _perform_local_delivery(record, channel, attachment, policy, batch):
    config = _channel_config(channel)
    target_root = resolve_runtime_path(config.get("rootPath"), "exports/local-delivery")
    target_folder = _build_channel_target_folder(channel, policy, batch).lstrip("/")
    final_dir = target_root / target_folder
    final_dir.mkdir(parents=True, exist_ok=True)
    target_path = final_dir / attachment.file_name
    shutil.copy2(attachment.file_path, target_path)
    return {"targetPath": str(target_path), "response": {"mode": "local", "copied": True}}


def _baidu_token_request(params):
    request_obj = url_request.Request(
        BAIDU_OAUTH_TOKEN_ENDPOINT,
        data=url_parse.urlencode(params).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with url_request.urlopen(request_obj, timeout=60) as response:
            payload = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads((payload or b"{}").decode(charset))
    except url_error.HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        raise APIError(f"百度网盘授权接口异常：{body or error.reason}") from error
    except url_error.URLError as error:
        raise APIError(f"百度网盘授权连接失败：{error.reason}") from error


def _exchange_baidu_authorization_code(code):
    settings = _baidu_oauth_settings()
    payload = _baidu_token_request(
        {
            "grant_type": "authorization_code",
            "code": str(code or "").strip(),
            "client_id": settings["app_key"],
            "client_secret": settings["secret_key"],
            "redirect_uri": settings["callback_url"],
        }
    )
    if not payload.get("access_token"):
        raise APIError(f"百度网盘授权换取令牌失败：{payload.get('error_description') or payload.get('error') or '未返回 access_token'}")
    return payload


def _refresh_baidu_access_token(refresh_token):
    settings = _baidu_oauth_settings()
    payload = _baidu_token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": str(refresh_token or "").strip(),
            "client_id": settings["app_key"],
            "client_secret": settings["secret_key"],
        }
    )
    if not payload.get("access_token"):
        raise APIError(f"百度网盘刷新令牌失败：{payload.get('error_description') or payload.get('error') or '未返回 access_token'}")
    return payload


def _apply_baidu_token_payload(channel, token_payload, auth_mode="oauth"):
    config = _channel_config(channel)
    now_value = now_beijing()
    expires_in = int(token_payload.get("expires_in") or 0)
    expires_at = now_value + timedelta(seconds=expires_in) if expires_in > 0 else None
    config.update(
        {
            "accessToken": str(token_payload.get("access_token") or config.get("accessToken") or "").strip(),
            "refreshToken": str(token_payload.get("refresh_token") or config.get("refreshToken") or "").strip(),
            "authorizedAt": now_value.isoformat(),
            "tokenExpiresAt": expires_at.isoformat() if expires_at else "",
            "scope": str(token_payload.get("scope") or config.get("scope") or "").strip(),
            "authMode": auth_mode,
            "oauthStatus": "authorized",
            "callbackUrl": str(_app_config_value("BAIDU_PAN_CALLBACK_URL", "http://localhost:5002/api/integrations/baidu-pan/callback") or config.get("callbackUrl") or "").strip(),
        }
    )
    _write_channel_config(channel, config)
    channel.last_validated_at = now_value
    channel.last_validation_status = "authorized"
    channel.last_error = ""
    db.session.flush()
    return config


def build_baidu_authorize_url(channel, user):
    if channel.channel_type != "baidu_pan":
        raise APIError("只有百度网盘渠道支持发起授权")
    config = _channel_config(channel)
    if bool(config.get("mockMode")):
        raise APIError("Mock 模式渠道不需要发起百度网盘授权")
    settings = _baidu_oauth_settings()
    state = _baidu_oauth_serializer().dumps(
        {
            "channelId": int(channel.id),
            "userId": int(user.id),
            "issuedAt": now_beijing().isoformat(),
        }
    )
    authorize_url = f"{BAIDU_OAUTH_AUTHORIZE_ENDPOINT}?{url_parse.urlencode({'response_type': 'code', 'client_id': settings['app_key'], 'redirect_uri': settings['callback_url'], 'scope': settings['scope'], 'state': state, 'display': 'popup', 'force_login': '1'})}"
    return {
        "authorizeUrl": authorize_url,
        "callbackUrl": settings["callback_url"],
        "scope": settings["scope"],
        "channelId": int(channel.id),
        "channelName": channel.channel_name,
    }


def complete_baidu_oauth_callback(code, state):
    raw_code = str(code or "").strip()
    raw_state = str(state or "").strip()
    if not raw_code or not raw_state:
        raise APIError("授权回调参数不完整，请回到文件中心重新发起授权")
    try:
        state_payload = _baidu_oauth_serializer().loads(raw_state, max_age=1800)
    except SignatureExpired as error:
        raise APIError("授权状态已失效，请回到文件中心重新发起授权") from error
    except BadData as error:
        raise APIError("授权状态校验失败，请回到文件中心重新发起授权") from error

    channel = db.session.get(FileDeliveryChannel, int(state_payload.get("channelId") or 0))
    if channel is None:
        raise APIError("回调对应的投递渠道不存在")
    if channel.channel_type != "baidu_pan":
        raise APIError("回调对应的渠道不是百度网盘")
    token_payload = _exchange_baidu_authorization_code(raw_code)
    _apply_baidu_token_payload(channel, token_payload, auth_mode="oauth")
    db.session.commit()
    return channel


def resolve_baidu_access_token(channel, force_refresh=False):
    config = _channel_config(channel)
    if bool(config.get("mockMode")):
        return ""
    access_token = str(config.get("accessToken") or "").strip()
    refresh_token = str(config.get("refreshToken") or "").strip()
    expires_at = _parse_datetime_value(config.get("tokenExpiresAt"))
    if access_token and not force_refresh and not (refresh_token and _token_expired(expires_at)):
        return access_token
    if refresh_token:
        token_payload = _refresh_baidu_access_token(refresh_token)
        refreshed_config = _apply_baidu_token_payload(channel, token_payload, auth_mode="oauth")
        return str(refreshed_config.get("accessToken") or "").strip()
    if access_token:
        return access_token
    raise APIError("百度网盘渠道尚未授权，请先在文件中心完成授权")


def _baidu_request(endpoint, params, method="POST", data=None, headers=None):
    url = f"{endpoint}?{url_parse.urlencode(params)}"
    request_headers = {"User-Agent": "competition-platform/1.0", "Connection": "close"}
    if headers:
        request_headers.update(headers)
    last_error = None
    for attempt in range(1, BAIDU_REQUEST_RETRY_LIMIT + 1):
        request_obj = url_request.Request(url, data=data, method=method, headers=request_headers)
        try:
            with url_request.urlopen(request_obj, timeout=60) as response:
                payload = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                if not payload:
                    return {}
                return json.loads(payload.decode(charset))
        except url_error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            raise APIError(f"百度网盘接口异常：{body or error.reason}") from error
        except (url_error.URLError, ssl.SSLError, OSError) as error:
            last_error = error
            reason = getattr(error, 'reason', error)
            message = str(reason or error)
            retryable = 'UNEXPECTED_EOF_WHILE_READING' in message or 'EOF occurred in violation of protocol' in message or 'tlsv1 alert internal error' in message.lower()
            if retryable and attempt < BAIDU_REQUEST_RETRY_LIMIT:
                time.sleep(0.4 * attempt)
                continue
            raise APIError(f"百度网盘连接失败：{message}") from error
    raise APIError(f"百度网盘连接失败：{last_error}")


def _ensure_baidu_folder(access_token, folder_path):
    normalized = _normalize_posix_path(folder_path)
    if normalized in {"", "/"}:
        return {"path": "/"}
    try:
        return _baidu_request(
            BAIDU_PAN_MKDIR_ENDPOINT,
            {"method": "mkdir", "access_token": access_token, "path": normalized},
            method="POST",
            data=b"",
        )
    except APIError as error:
        message = str(getattr(error, 'message', '') or error)
        if '31061' in message or 'file already exists' in message.lower():
            return {"path": normalized, "existed": True}
        raise


def _upload_to_baidu_pan(access_token, remote_file_path, attachment, conflict_mode="overwrite"):
    boundary = f"----CodexBoundary{uuid4().hex}"
    file_name = _sanitize_segment(attachment.file_name, fallback="export.zip")
    file_bytes = Path(attachment.file_path).read_bytes()
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = prefix + file_bytes + suffix
    return _baidu_request(
        BAIDU_PAN_UPLOAD_ENDPOINT,
        {
            "method": "upload",
            "access_token": access_token,
            "path": _normalize_posix_path(remote_file_path),
            "ondup": "overwrite" if str(conflict_mode or "").lower() != "newcopy" else "newcopy",
        },
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def _perform_baidu_pan_delivery(record, channel, attachment, policy, batch):
    config = _channel_config(channel)
    target_folder = _build_channel_target_folder(channel, policy, batch)
    remote_file_path = _normalize_posix_path(target_folder, attachment.file_name)
    if bool(config.get("mockMode")):
        mock_root = resolve_runtime_path(config.get("mockRoot") or "mock_baidu_pan", "mock_baidu_pan")
        target_path = mock_root / remote_file_path.lstrip("/")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(attachment.file_path, target_path)
        return {
            "targetPath": remote_file_path,
            "response": {
                "mode": "mock",
                "mockRoot": str(mock_root),
                "mockFilePath": str(target_path),
            },
        }

    access_token = resolve_baidu_access_token(channel)
    _ensure_baidu_folder(access_token, target_folder)
    response = _upload_to_baidu_pan(access_token, remote_file_path, attachment, conflict_mode=config.get("conflictMode"))
    return {"targetPath": remote_file_path, "response": response}


def _execute_delivery_record(record, attachment, policy, batch):
    channel = record.channel or db.session.get(FileDeliveryChannel, record.channel_id)
    if channel is None:
        raise APIError("投递渠道不存在")
    record.status = "processing"
    record.progress = 10
    record.current_step = "准备投递"
    record.error_message = ""
    record.started_at = now_beijing()
    record.finished_at = None
    db.session.commit()

    handler = _perform_local_delivery if channel.channel_type == "local_folder" else _perform_baidu_pan_delivery
    result = handler(record, channel, attachment, policy, batch)

    record.status = "completed"
    record.progress = 100
    record.current_step = "投递完成"
    record.target_path = str(result.get("targetPath") or "")
    record.delivered_file_name = attachment.file_name
    record.success_count = 1
    record.fail_count = 0
    record.response_snapshot_json = _json_dumps(result.get("response") or {})
    record.error_message = ""
    record.finished_at = now_beijing()
    db.session.commit()


def _reset_delivery_record(record, retry_increment=False):
    record.status = "pending"
    record.progress = 0
    record.current_step = "等待投递"
    record.target_path = ""
    record.delivered_file_name = ""
    record.success_count = 0
    record.fail_count = 0
    record.response_snapshot_json = "{}"
    record.error_message = ""
    record.started_at = None
    record.finished_at = None
    if retry_increment:
        record.retry_count = int(record.retry_count or 0) + 1


def _ensure_batch_delivery_records(batch, policy):
    existing_records = {item.channel_id: item for item in FileDeliveryRecord.query.filter_by(batch_id=batch.id).all()}
    channel_ids = _policy_channel_ids(policy)
    record_ids = []
    for channel_id in channel_ids:
        record = existing_records.get(channel_id)
        if record is None:
            record = FileDeliveryRecord(batch_id=batch.id, channel_id=channel_id, current_step="等待投递")
            db.session.add(record)
            db.session.flush()
        record_ids.append(record.id)
    for channel_id, record in existing_records.items():
        if channel_id not in channel_ids:
            db.session.delete(record)
    db.session.commit()
    return record_ids


def delete_attachment_file(attachment_id):
    if not attachment_id:
        return
    attachment = db.session.get(AttachmentInfo, int(attachment_id))
    if not attachment:
        return
    attachment_path = Path(str(attachment.file_path or ""))
    if attachment_path.exists():
        attachment_path.unlink(missing_ok=True)
    db.session.delete(attachment)
    db.session.flush()


def execute_file_export_batch(app, batch_id):
    with app.app_context():
        try:
            batch = db.session.get(FileExportBatch, int(batch_id))
            if batch is None:
                return
            policy = db.session.get(FileExportPolicy, batch.policy_id)
            user = db.session.get(SysUser, batch.created_by)
            if policy is None or user is None or int(user.status or 0) != 1:
                raise APIError("批次关联的规则或创建人不存在")

            batch.status = "processing"
            batch.progress = 10
            batch.current_step = "收集导出文件"
            batch.error_message = ""
            batch.started_at = now_beijing()
            batch.finished_at = None
            db.session.commit()

            assets = _filter_policy_assets(policy, user)
            batch.source_count = len(assets)
            batch.progress = 35
            batch.current_step = "生成目录模板"
            db.session.commit()

            manifest_entries = _build_manifest_entries(policy, batch, assets)
            package_name, package_bytes, manifest_payload = _build_package(policy, batch, manifest_entries)

            batch.progress = 65
            batch.current_step = "写入归档包"
            db.session.commit()

            if batch.attachment_id:
                delete_attachment_file(batch.attachment_id)
                batch.attachment_id = None
                db.session.commit()

            attachment, _ = create_binary_attachment(package_name, package_bytes, "file_export_batch_export", batch.created_by, subdir="exports")
            batch.attachment_id = attachment.id
            batch.package_file_name = attachment.file_name
            batch.manifest_json = _json_dumps(manifest_payload)
            batch.success_count = len(manifest_entries)
            batch.fail_count = 0
            batch.progress = 80
            batch.current_step = "执行投递渠道"
            batch.result_snapshot_json = _json_dumps({"packageFileName": attachment.file_name, "manifestCount": len(manifest_entries)})
            db.session.commit()

            record_ids = _ensure_batch_delivery_records(batch, policy)
            for record_id in record_ids:
                record = db.session.get(FileDeliveryRecord, record_id)
                try:
                    _execute_delivery_record(record, attachment, policy, batch)
                except Exception as error:
                    db.session.rollback()
                    record = db.session.get(FileDeliveryRecord, record_id)
                    if record is not None:
                        record.status = "failed"
                        record.progress = 0
                        record.current_step = "投递失败"
                        record.error_message = str(error)[:500]
                        record.fail_count = 1
                        record.finished_at = now_beijing()
                        db.session.commit()

            deliveries = FileDeliveryRecord.query.filter_by(batch_id=batch.id).all()
            has_failed_delivery = any(item.status == "failed" for item in deliveries)
            batch.status = "partial_success" if has_failed_delivery else "completed"
            batch.progress = 100
            batch.current_step = "导出完成" if not has_failed_delivery else "导出完成，部分投递失败"
            batch.error_message = "" if not has_failed_delivery else "存在投递失败记录，请查看批次详情后重试。"
            batch.fail_count = sum(int(item.fail_count or 0) for item in deliveries)
            batch.finished_at = now_beijing()
            policy.last_run_at = batch.finished_at
            policy.last_status = batch.status
            policy.last_error = batch.error_message or ""
            if policy.status == POLICY_STATUS_ENABLED and policy.schedule_type == "daily":
                policy.next_run_at = compute_next_run_at(policy.schedule_type, policy.schedule_time, now_value=batch.finished_at)
            db.session.commit()
        except Exception as error:
            db.session.rollback()
            batch = db.session.get(FileExportBatch, int(batch_id))
            if batch is not None:
                batch.status = "failed"
                batch.progress = 0
                batch.current_step = "执行失败"
                batch.error_message = str(error)[:500]
                batch.finished_at = now_beijing()
                db.session.commit()
                policy = db.session.get(FileExportPolicy, batch.policy_id)
                if policy is not None:
                    policy.last_run_at = batch.finished_at
                    policy.last_status = batch.status
                    policy.last_error = batch.error_message or ""
                    if policy.status == POLICY_STATUS_ENABLED and policy.schedule_type == "daily":
                        policy.next_run_at = compute_next_run_at(policy.schedule_type, policy.schedule_time, now_value=batch.finished_at)
                    db.session.commit()
        finally:
            db.session.remove()


def enqueue_file_export_batch(batch_id, app=None):
    app_obj = app or current_app._get_current_object()
    FILE_EXPORT_EXECUTOR.submit(execute_file_export_batch, app_obj, int(batch_id))


def create_policy_batch(policy, actor, trigger_type="manual", scheduled_for=None, retry_increment=False, app=None):
    active_batch = FileExportBatch.query.filter(
        FileExportBatch.policy_id == policy.id,
        FileExportBatch.status.in_(sorted(BATCH_ACTIVE_STATUSES)),
    ).order_by(FileExportBatch.id.desc()).first()
    if active_batch:
        raise APIError("当前规则已有执行中的批次，请稍后再试")

    batch = FileExportBatch(
        policy_id=policy.id,
        batch_no="pending",
        trigger_type=trigger_type,
        status="pending",
        progress=0,
        current_step="等待执行",
        error_message="",
        request_snapshot_json=_json_dumps({"policy": serialize_policy(policy), "operatorId": int(actor.id), "operatorName": actor.real_name}),
        result_snapshot_json="{}",
        manifest_json="{}",
        created_by=policy.created_by,
        scheduled_for=scheduled_for,
        retry_count=1 if retry_increment else 0,
    )
    db.session.add(batch)
    db.session.flush()
    batch.batch_no = f"FB{now_beijing().strftime('%Y%m%d%H%M%S')}{int(batch.id):04d}"
    if trigger_type == "schedule" and policy.status == POLICY_STATUS_ENABLED and policy.schedule_type == "daily":
        policy.next_run_at = compute_next_run_at(policy.schedule_type, policy.schedule_time, now_value=scheduled_for or now_beijing())
    db.session.commit()
    enqueue_file_export_batch(batch.id, app=app)
    db.session.refresh(batch)
    return batch


def retry_batch(batch, actor, app=None):
    ensure_batch_access(batch, actor)
    if batch.status not in BATCH_RETRYABLE_STATUSES:
        raise APIError("仅失败或部分成功的批次支持重试", code=400, status=200)
    if batch.attachment_id:
        delete_attachment_file(batch.attachment_id)
        batch.attachment_id = None
    batch.status = "pending"
    batch.progress = 0
    batch.current_step = "等待重试"
    batch.error_message = ""
    batch.source_count = 0
    batch.success_count = 0
    batch.fail_count = 0
    batch.package_file_name = ""
    batch.manifest_json = "{}"
    batch.result_snapshot_json = "{}"
    batch.started_at = None
    batch.finished_at = None
    batch.retry_count = int(batch.retry_count or 0) + 1
    deliveries = FileDeliveryRecord.query.filter_by(batch_id=batch.id).all()
    for record in deliveries:
        _reset_delivery_record(record, retry_increment=True)
    db.session.commit()
    enqueue_file_export_batch(batch.id, app=app)
    db.session.refresh(batch)
    return batch


def recover_pending_file_export_batches(app=None):
    app_obj = app or current_app._get_current_object()
    recoverable = FileExportBatch.query.filter(FileExportBatch.status.in_(sorted(BATCH_ACTIVE_STATUSES))).order_by(FileExportBatch.id.asc()).all()
    batch_ids = []
    for batch in recoverable:
        if batch.attachment_id:
            delete_attachment_file(batch.attachment_id)
            batch.attachment_id = None
        batch.status = "pending"
        batch.progress = 0
        batch.current_step = "等待恢复执行"
        batch.error_message = ""
        batch.source_count = 0
        batch.success_count = 0
        batch.fail_count = 0
        batch.package_file_name = ""
        batch.manifest_json = "{}"
        batch.result_snapshot_json = "{}"
        batch.started_at = None
        batch.finished_at = None
        batch_ids.append(int(batch.id))
        deliveries = FileDeliveryRecord.query.filter_by(batch_id=batch.id).all()
        for record in deliveries:
            _reset_delivery_record(record)
    if batch_ids:
        db.session.commit()
        for batch_id in batch_ids:
            enqueue_file_export_batch(batch_id, app_obj)
    return batch_ids


def scan_due_policies(app=None, creator_id=None):
    app_obj = app or current_app._get_current_object()
    with app_obj.app_context():
        query = FileExportPolicy.query.filter(
            FileExportPolicy.status == POLICY_STATUS_ENABLED,
            FileExportPolicy.schedule_type == "daily",
            FileExportPolicy.next_run_at.isnot(None),
            FileExportPolicy.next_run_at <= now_beijing(),
        ).order_by(FileExportPolicy.next_run_at.asc(), FileExportPolicy.id.asc())
        if creator_id:
            query = query.filter(FileExportPolicy.created_by == int(creator_id))
        policy_rows = query.all()
        batch_ids = []
        for policy in policy_rows:
            active_batch = FileExportBatch.query.filter(
                FileExportBatch.policy_id == policy.id,
                FileExportBatch.status.in_(sorted(BATCH_ACTIVE_STATUSES)),
            ).first()
            if active_batch is not None:
                continue
            actor = db.session.get(SysUser, policy.created_by)
            if actor is None or int(actor.status or 0) != 1:
                continue
            batch = create_policy_batch(policy, actor, trigger_type="schedule", scheduled_for=policy.next_run_at, app=app_obj)
            batch_ids.append(batch.id)
        return batch_ids


def _scheduler_loop(app):
    interval_seconds = file_export_scan_interval_seconds()
    while True:
        try:
            scan_due_policies(app)
        except Exception:
            app.logger.exception("文件导出调度扫描失败")
        time.sleep(interval_seconds)


def start_file_export_scheduler(app=None):
    app_obj = app or current_app._get_current_object()
    if not file_export_scheduler_enabled():
        return None
    thread_key = id(app_obj)
    if thread_key in SCHEDULER_THREADS:
        return SCHEDULER_THREADS[thread_key]
    worker = threading.Thread(target=_scheduler_loop, args=(app_obj,), name="competition-file-export-scheduler", daemon=True)
    worker.start()
    SCHEDULER_THREADS[thread_key] = worker
    return worker
