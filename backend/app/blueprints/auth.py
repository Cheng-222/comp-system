from flask import Blueprint, g, request

from ..audit_store import record_login_event
from ..common import success
from ..errors import APIError
from ..models import SysUser
from ..security import auth_required, create_token, verify_password


bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        record_login_event(username or "unknown", 1, "用户名和密码不能为空", request.remote_addr, request.user_agent.string)
        raise APIError("用户名和密码不能为空")

    user = SysUser.query.filter_by(username=username).first()
    if not user or user.status != 1 or not verify_password(password, user.password_hash):
        record_login_event(username or "unknown", 1, "用户名或密码错误", request.remote_addr, request.user_agent.string)
        raise APIError("用户名或密码错误", status=401)

    record_login_event(user.username, 0, "登录成功", request.remote_addr, request.user_agent.string)
    return success({"token": create_token(user.id), "user": user.to_dict()})


@bp.get("/me")
@auth_required()
def me():
    return success(g.current_user.to_dict())


@bp.get("/menus")
@auth_required()
def menus():
    role_codes = set(g.current_user.role_codes)
    items = [
        {"path": "/dashboard", "title": "工作台", "roles": ["admin", "teacher", "reviewer", "student"]},
        {"path": "/students", "title": "学生管理", "roles": ["admin", "teacher"]},
        {"path": "/contests", "title": "赛事管理", "roles": ["admin", "teacher"]},
        {"path": "/registrations", "title": "报名管理", "roles": ["admin", "teacher", "reviewer", "student"]},
        {"path": "/reviews", "title": "材料审核", "roles": ["admin", "teacher", "reviewer"]},
        {"path": "/messages", "title": "通知中心", "roles": ["admin", "teacher", "reviewer", "student"]},
    ]
    return success([item for item in items if role_codes.intersection(set(item["roles"]))])
