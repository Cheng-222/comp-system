import json
from pathlib import Path

from flask import Blueprint, Response, current_app, g, request, send_file

from ..common import paginate_items, paginate_query, success
from ..errors import APIError
from ..file_center_service import category_tree, filter_assets, resolve_asset_file, summary, visible_assets
from ..file_export_service import (
    CHANNEL_STATUS_ENABLED,
    POLICY_STATUS_ENABLED,
    build_baidu_authorize_url,
    complete_baidu_oauth_callback,
    batch_query_for_user,
    channel_query_for_user,
    create_policy_batch,
    ensure_batch_access,
    ensure_channel_access,
    ensure_policy_access,
    export_metadata,
    normalize_channel_payload,
    normalize_policy_payload,
    policy_query_for_user,
    recover_pending_file_export_batches,
    retry_batch,
    scan_due_policies,
    serialize_batch,
    serialize_channel,
    serialize_policy,
    start_file_export_scheduler,
    validate_channel_config,
)
from ..models import AttachmentInfo, FileDeliveryChannel, FileExportBatch, FileExportPolicy
from ..security import auth_required
from ..time_utils import now_beijing


bp = Blueprint("files", __name__, url_prefix="/api/v1/files")
callback_bp = Blueprint("file_oauth_callback", __name__, url_prefix="/api")


def _payload():
    return request.get_json(silent=True) or {}


def _payload_value(name):
    payload = _payload()
    return request.form.get(name) or payload.get(name)


def _asset_type_and_id():
    asset_type = str(_payload_value("assetType") or "").strip()
    asset_id = str(_payload_value("assetId") or "").strip()
    if not asset_type or not asset_id:
        raise APIError("文件标识不能为空")
    return asset_type, asset_id


def _serialize_paginated_rows(query):
    items, total, page_num, page_size = paginate_query(query)
    return {"items": items, "total": total, "pageNum": page_num, "pageSize": page_size}


def _oauth_callback_page(title, message, success_state=True):
    tone = "#16a34a" if success_state else "#dc2626"
    summary = "授权完成后可回到文件中心刷新或校验渠道。" if success_state else "处理失败后请回到文件中心重新发起授权。"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fb; color: #1f2937; margin: 0; }}
    .wrap {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; }}
    .card {{ width: min(520px, 100%); background: #fff; border-radius: 20px; box-shadow: 0 20px 60px rgba(15, 23, 42, 0.12); padding: 28px; }}
    .badge {{ display: inline-flex; align-items: center; gap: 8px; color: {tone}; font-weight: 700; margin-bottom: 12px; }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ margin: 0 0 12px; line-height: 1.7; color: #475569; }}
    button {{ border: none; border-radius: 999px; padding: 10px 18px; background: {tone}; color: #fff; cursor: pointer; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="badge">文件中心 · 百度网盘</div>
      <h1>{title}</h1>
      <p>{message}</p>
      <p>{summary}</p>
      <button onclick="window.close()">关闭窗口</button>
    </div>
  </div>
  <script>
    setTimeout(function () {{
      if (window.opener) {{
        window.close()
      }}
    }}, 1600)
  </script>
</body>
</html>"""


@bp.get("/categories")
@auth_required(["admin", "teacher", "reviewer"])
def file_categories():
    items = visible_assets(g.current_user)
    return success({"tree": category_tree(items), "summary": summary(items)})


@bp.get("")
@auth_required(["admin", "teacher", "reviewer"])
def list_files():
    items = filter_assets(visible_assets(g.current_user), request.args)
    page_items, total, page_num, page_size = paginate_items(items)
    for item in page_items:
        item.pop("_sort", None)
        item.pop("_path", None)
        item.pop("_createdAt", None)
    return success({"list": page_items, "total": total, "pageNum": page_num, "pageSize": page_size, "summary": summary(items)})


@bp.post("/download")
@auth_required(["admin", "teacher", "reviewer"])
def download_file():
    asset_type, asset_id = _asset_type_and_id()
    target = resolve_asset_file(g.current_user, asset_type, asset_id)
    return send_file(target["path"], as_attachment=True, download_name=target["fileName"])


@bp.post("/preview")
@auth_required(["admin", "teacher", "reviewer"])
def preview_file():
    asset_type, asset_id = _asset_type_and_id()
    target = resolve_asset_file(g.current_user, asset_type, asset_id)
    return send_file(target["path"], as_attachment=False, download_name=target["fileName"])


@bp.get("/export-metadata")
@auth_required(["admin", "teacher"])
def get_export_metadata():
    return success(export_metadata(g.current_user))


@bp.get("/export-policies")
@auth_required(["admin", "teacher"])
def list_export_policies():
    keyword = str(request.args.get("keyword") or "").strip()
    status = str(request.args.get("status") or "").strip()
    schedule_type = str(request.args.get("scheduleType") or "").strip()
    query = policy_query_for_user(g.current_user)
    if keyword:
        query = query.filter(FileExportPolicy.policy_name.like(f"%{keyword}%"))
    if status:
        query = query.filter(FileExportPolicy.status == status)
    if schedule_type:
        query = query.filter(FileExportPolicy.schedule_type == schedule_type)
    page = _serialize_paginated_rows(query)
    return success({"list": [serialize_policy(item) for item in page["items"]], "total": page["total"], "pageNum": page["pageNum"], "pageSize": page["pageSize"]})


@bp.get("/export-policies/<int:policy_id>")
@auth_required(["admin", "teacher"])
def get_export_policy(policy_id):
    policy = ensure_policy_access(FileExportPolicy.query.get_or_404(policy_id), g.current_user)
    return success(serialize_policy(policy))


@bp.post("/export-policies")
@auth_required(["admin", "teacher"])
def create_export_policy():
    values = normalize_policy_payload(_payload(), g.current_user)
    policy = FileExportPolicy(created_by=g.current_user.id, **values)
    if policy.status != POLICY_STATUS_ENABLED:
        policy.next_run_at = None
    current_app.logger.info("创建文件导出规则：%s", policy.policy_name)
    from ..extensions import db

    db.session.add(policy)
    db.session.commit()
    return success(serialize_policy(policy), message="导出规则创建成功")


@bp.put("/export-policies/<int:policy_id>")
@auth_required(["admin", "teacher"])
def update_export_policy(policy_id):
    from ..extensions import db

    policy = ensure_policy_access(FileExportPolicy.query.get_or_404(policy_id), g.current_user, write=True)
    values = normalize_policy_payload(_payload(), g.current_user, existing=policy)
    for field, value in values.items():
        setattr(policy, field, value)
    if policy.status != POLICY_STATUS_ENABLED:
        policy.next_run_at = None
    db.session.commit()
    return success(serialize_policy(policy), message="导出规则更新成功")


@bp.delete("/export-policies/<int:policy_id>")
@auth_required(["admin", "teacher"])
def delete_export_policy(policy_id):
    from ..extensions import db

    policy = ensure_policy_access(FileExportPolicy.query.get_or_404(policy_id), g.current_user, write=True)
    batch_count = FileExportBatch.query.filter_by(policy_id=policy.id).count()
    if batch_count:
        raise APIError("当前规则已有执行批次，不能直接删除")
    db.session.delete(policy)
    db.session.commit()
    return success(message="导出规则删除成功")


@bp.post("/export-policies/<int:policy_id>/run")
@auth_required(["admin", "teacher"])
def run_export_policy(policy_id):
    policy = ensure_policy_access(FileExportPolicy.query.get_or_404(policy_id), g.current_user, write=True)
    batch = create_policy_batch(policy, g.current_user, trigger_type="manual")
    return success(serialize_batch(batch), message="导出批次已创建")


@bp.post("/export-policies/run-due")
@auth_required(["admin", "teacher"])
def run_due_export_policies():
    creator_id = None if is_admin_request() else g.current_user.id
    batch_ids = scan_due_policies(current_app._get_current_object(), creator_id=creator_id)
    return success({"batchIds": batch_ids, "count": len(batch_ids)}, message="已完成到期规则扫描")


def is_admin_request():
    return any(role_code == "admin" for role_code in getattr(g.current_user, "role_codes", []) or [])


@bp.get("/export-batches")
@auth_required(["admin", "teacher"])
def list_export_batches():
    keyword = str(request.args.get("keyword") or "").strip()
    status = str(request.args.get("status") or "").strip()
    policy_id = request.args.get("policyId")
    query = batch_query_for_user(g.current_user)
    if keyword:
        query = query.join(FileExportPolicy, FileExportBatch.policy_id == FileExportPolicy.id).filter(
            (FileExportBatch.batch_no.like(f"%{keyword}%")) |
            (FileExportPolicy.policy_name.like(f"%{keyword}%")) |
            (FileExportBatch.package_file_name.like(f"%{keyword}%"))
        )
    if status:
        query = query.filter(FileExportBatch.status == status)
    if policy_id:
        query = query.filter(FileExportBatch.policy_id == int(policy_id))
    page = _serialize_paginated_rows(query)
    return success({"list": [serialize_batch(item) for item in page["items"]], "total": page["total"], "pageNum": page["pageNum"], "pageSize": page["pageSize"]})


@bp.get("/export-batches/<int:batch_id>")
@auth_required(["admin", "teacher"])
def get_export_batch(batch_id):
    batch = ensure_batch_access(FileExportBatch.query.get_or_404(batch_id), g.current_user)
    return success(serialize_batch(batch, include_details=True))


@bp.post("/export-batches/<int:batch_id>/download")
@auth_required(["admin", "teacher"])
def download_export_batch(batch_id):
    batch = ensure_batch_access(FileExportBatch.query.get_or_404(batch_id), g.current_user)
    if batch.status not in {"completed", "partial_success"}:
        raise APIError("导出批次尚未完成", code=400, status=200)
    attachment = AttachmentInfo.query.get(int(batch.attachment_id or 0))
    if not attachment or not Path(str(attachment.file_path or "")).exists():
        raise APIError("导出归档包不存在", status=404)
    return send_file(attachment.file_path, as_attachment=True, download_name=attachment.file_name)


@bp.post("/export-batches/<int:batch_id>/retry")
@auth_required(["admin", "teacher"])
def retry_export_batch(batch_id):
    batch = ensure_batch_access(FileExportBatch.query.get_or_404(batch_id), g.current_user)
    batch = retry_batch(batch, g.current_user)
    return success(serialize_batch(batch), message="导出批次已重新提交")


@bp.get("/delivery-channels")
@auth_required(["admin"])
def list_delivery_channels():
    keyword = str(request.args.get("keyword") or "").strip()
    status = str(request.args.get("status") or "").strip()
    channel_type = str(request.args.get("channelType") or "").strip()
    query = channel_query_for_user(g.current_user)
    if keyword:
        query = query.filter(FileDeliveryChannel.channel_name.like(f"%{keyword}%"))
    if status:
        query = query.filter(FileDeliveryChannel.status == status)
    if channel_type:
        query = query.filter(FileDeliveryChannel.channel_type == channel_type)
    page = _serialize_paginated_rows(query)
    return success({"list": [serialize_channel(item) for item in page["items"]], "total": page["total"], "pageNum": page["pageNum"], "pageSize": page["pageSize"]})


@bp.get("/delivery-channels/<int:channel_id>")
@auth_required(["admin"])
def get_delivery_channel(channel_id):
    channel = ensure_channel_access(FileDeliveryChannel.query.get_or_404(channel_id), g.current_user)
    return success(serialize_channel(channel, include_config=True))


@bp.post("/delivery-channels")
@auth_required(["admin"])
def create_delivery_channel():
    from ..extensions import db

    values = normalize_channel_payload(_payload())
    channel = FileDeliveryChannel(created_by=g.current_user.id, **values)
    db.session.add(channel)
    db.session.commit()
    return success(serialize_channel(channel, include_config=True), message="投递渠道创建成功")


@bp.put("/delivery-channels/<int:channel_id>")
@auth_required(["admin"])
def update_delivery_channel(channel_id):
    from ..extensions import db

    channel = ensure_channel_access(FileDeliveryChannel.query.get_or_404(channel_id), g.current_user)
    values = normalize_channel_payload(_payload(), existing=channel)
    for field, value in values.items():
        setattr(channel, field, value)
    db.session.commit()
    return success(serialize_channel(channel, include_config=True), message="投递渠道更新成功")


@bp.delete("/delivery-channels/<int:channel_id>")
@auth_required(["admin"])
def delete_delivery_channel(channel_id):
    from ..extensions import db

    channel = ensure_channel_access(FileDeliveryChannel.query.get_or_404(channel_id), g.current_user)
    policy_count = sum(
        1
        for item in FileExportPolicy.query.all()
        if int(channel.id) in {
            int(value)
            for value in (json.loads(item.delivery_channel_ids_json or "[]") if item.delivery_channel_ids_json else [])
            if str(value).strip().isdigit()
        }
    )
    if policy_count:
        raise APIError("该渠道已被导出规则引用，不能删除")
    db.session.delete(channel)
    db.session.commit()
    return success(message="投递渠道删除成功")


@bp.post("/delivery-channels/<int:channel_id>/oauth-authorize")
@auth_required(["admin"])
def authorize_delivery_channel(channel_id):
    channel = ensure_channel_access(FileDeliveryChannel.query.get_or_404(channel_id), g.current_user)
    return success(build_baidu_authorize_url(channel, g.current_user), message="授权链接已生成")


@bp.post("/delivery-channels/<int:channel_id>/validate")
@auth_required(["admin"])
def validate_delivery_channel(channel_id):
    from ..extensions import db

    channel = ensure_channel_access(FileDeliveryChannel.query.get_or_404(channel_id), g.current_user)
    try:
        result = validate_channel_config(channel)
        channel.last_validated_at = now_beijing()
        channel.last_validation_status = "success"
        channel.last_error = ""
        db.session.commit()
        return success(result, message="渠道校验成功")
    except Exception as error:
        db.session.rollback()
        channel = ensure_channel_access(FileDeliveryChannel.query.get_or_404(channel_id), g.current_user)
        channel.last_validated_at = now_beijing()
        channel.last_validation_status = "failed"
        channel.last_error = str(error)[:500]
        db.session.commit()
        raise


@callback_bp.get("/callback")
@callback_bp.get("/integrations/baidu-pan/callback")
def baidu_pan_callback():
    callback_error = str(request.args.get("error") or request.args.get("error_reason") or "").strip()
    callback_message = str(request.args.get("error_description") or request.args.get("error_msg") or "").strip()
    if callback_error:
        html = _oauth_callback_page("百度网盘授权未完成", callback_message or callback_error, success_state=False)
        return Response(html, mimetype="text/html", status=400)
    try:
        channel = complete_baidu_oauth_callback(request.args.get("code"), request.args.get("state"))
        html = _oauth_callback_page("百度网盘授权成功", f"渠道“{channel.channel_name}”已完成授权。")
        return Response(html, mimetype="text/html")
    except APIError as error:
        html = _oauth_callback_page("百度网盘授权失败", error.message, success_state=False)
        return Response(html, mimetype="text/html", status=400)


def warm_file_export_runtime(app=None):
    app_obj = app or current_app._get_current_object()
    recovered_batch_ids = recover_pending_file_export_batches(app_obj)
    scheduler_thread = start_file_export_scheduler(app_obj)
    return {
        "recoveredBatchIds": recovered_batch_ids,
        "schedulerStarted": bool(scheduler_thread),
    }
