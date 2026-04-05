import json
import time
from pathlib import Path

from flask import Flask, g, request

from .account_service import reconcile_student_accounts
from .audit_store import infer_business_type, infer_title, record_oper_event
from .blueprints import BLUEPRINTS
from .common import failure, success
from .config import Config
from .errors import APIError
from .extensions import cors, db
from .platform_ops import ensure_runtime_directories
from .runtime_migrations import migrate_legacy_utc_to_beijing
from .schema import ensure_schema_columns
from .seed import seed_initial_data
from .system_compat_store import ensure_system_compat_seed


def _mask_sensitive(value):
    sensitive_exact_keys = {"code", "state", "signkey", "sign_key"}
    sensitive_keywords = ("password", "token", "secret")
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            current_key = str(key).lower()
            if current_key in sensitive_exact_keys or any(keyword in current_key for keyword in sensitive_keywords):
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive(item)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


def _truncate_text(value, limit=1200):
    if not value:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _serialize_request_payload():
    payload = {}
    query = request.args.to_dict(flat=False)
    if query:
        payload["query"] = query
    if request.is_json:
        data = request.get_json(silent=True)
        if data not in (None, {}):
            payload["json"] = data
    form = request.form.to_dict(flat=False)
    if form:
        payload["form"] = form
    files = {
        key: [item.filename for item in request.files.getlist(key)]
        for key in request.files.keys()
    }
    if files:
        payload["files"] = files
    return _truncate_text(json.dumps(_mask_sensitive(payload), ensure_ascii=False, default=str)) if payload else ""


def _serialize_response_payload(response):
    if response.direct_passthrough or not response.is_json:
        return _truncate_text(response.content_type or "")
    payload = response.get_json(silent=True)
    if payload in (None, {}):
        return ""
    return _truncate_text(json.dumps(_mask_sensitive(payload), ensure_ascii=False, default=str))


def _resolve_oper_name():
    current_user = getattr(g, "current_user", None)
    if current_user is not None:
        return current_user.username
    payload = request.get_json(silent=True) or {}
    for key in ("username", "userName"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return "anonymous"


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["LOG_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"] or "*"}, r"/captchaImage": {"origins": app.config["CORS_ORIGINS"] or "*"}, r"/login": {"origins": app.config["CORS_ORIGINS"] or "*"}, r"/logout": {"origins": app.config["CORS_ORIGINS"] or "*"}, r"/getInfo": {"origins": app.config["CORS_ORIGINS"] or "*"}, r"/getRouters": {"origins": app.config["CORS_ORIGINS"] or "*"}}, supports_credentials=False)

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    @app.get("/api/v1/ping")
    def ping():
        return success({"status": "ok"})

    @app.before_request
    def capture_request_started_at():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def capture_oper_log(response):
        path = request.path or ""
        if request.method == "OPTIONS" or path in {"/api/v1/ping", "/favicon.ico"}:
            return response
        response_payload = response.get_json(silent=True) if response.is_json and not response.direct_passthrough else {}
        app_code = response_payload.get("code") if isinstance(response_payload, dict) else None
        status = 0 if response.status_code < 500 and app_code in (None, 200) else 1
        cost_time = int((time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000)
        error_msg = ""
        if status:
            error_msg = (response_payload.get("msg") if isinstance(response_payload, dict) else "") or response.status
        try:
            record_oper_event(
                title=infer_title(path),
                business_type=infer_business_type(request.method, path),
                oper_name=_resolve_oper_name(),
                oper_url=path,
                request_method=request.method,
                method=request.endpoint or path,
                oper_param=_serialize_request_payload(),
                json_result=_serialize_response_payload(response),
                status=status,
                error_msg=_truncate_text(error_msg, 300),
                oper_ip=request.remote_addr or "127.0.0.1",
                cost_time=cost_time,
            )
        except Exception:
            app.logger.exception("记录操作日志失败")
        return response

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return failure(error.message, code=error.code, status=error.status, data=error.data)

    @app.errorhandler(404)
    def handle_not_found(_error):
        return failure("接口不存在", code=404)

    @app.errorhandler(Exception)
    def handle_unknown_error(error):
        app.logger.exception(error)
        return failure("服务器内部异常", code=500)

    with app.app_context():
        db.create_all()
        ensure_schema_columns()
        migrate_legacy_utc_to_beijing()
        if app.config["APP_AUTO_SEED"]:
            seed_initial_data(app.config["DEFAULT_ADMIN_PASSWORD"])
        ensure_system_compat_seed()
        ensure_runtime_directories()
        reconcile_student_accounts()
        db.session.commit()
        from .blueprints.results import recover_pending_export_tasks
        from .blueprints.files import warm_file_export_runtime

        recovered_export_task_ids = recover_pending_export_tasks(app)
        if recovered_export_task_ids:
            app.logger.info("已恢复 %s 个未完成导出任务", len(recovered_export_task_ids))
        file_export_runtime = warm_file_export_runtime(app)
        if file_export_runtime["recoveredBatchIds"]:
            app.logger.info("已恢复 %s 个未完成文件导出批次", len(file_export_runtime["recoveredBatchIds"]))

    return app
