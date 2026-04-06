from functools import wraps

from flask import current_app, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .access import is_admin_user, is_reviewer_user, is_student_user, is_teacher_user
from .common import failure
from .models import SysUser


def build_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="competition-auth")


def create_token(user_id):
    serializer = build_serializer()
    return serializer.dumps({"user_id": user_id})


def resolve_user_from_token(token):
    serializer = build_serializer()
    try:
        payload = serializer.loads(token, max_age=current_app.config["TOKEN_EXPIRES_SECONDS"])
    except (SignatureExpired, BadSignature):
        return None
    return SysUser.query.get(payload.get("user_id"))


def password_hash(password):
    return generate_password_hash(password)


def verify_password(password, password_digest):
    if not password_digest:
        return False
    try:
        return check_password_hash(password_digest, password)
    except ValueError:
        # 处理无效的哈希格式
        return False


PATH_MENU_PREFIXES = (
    ("/system/user", "user"),
    ("/system/role", "role"),
    ("/system/menu", "menu"),
    ("/system/dict", "dict"),
    ("/system/config", "config"),
    ("/monitor/operlog", "operlog"),
    ("/monitor/logininfor", "logininfor"),
    ("/api/v1/students", "students"),
    ("/api/v1/contests", "contests"),
    ("/api/v1/registrations", "registrations"),
    ("/api/v1/messages", "messages"),
    ("/api/v1/results", "results"),
    ("/api/v1/certificates", "results"),
    ("/api/v1/statistics", "statistics"),
    ("/api/v1/files", "files"),
)


def _matches_expected_role(user, role):
    if role == "admin":
        return is_admin_user(user)
    if role == "teacher":
        return is_teacher_user(user)
    if role == "reviewer":
        return is_reviewer_user(user)
    if role == "student":
        return is_student_user(user)
    return role in set(getattr(user, "role_codes", []) or [])


def _menu_path_for_request(path):
    for prefix, menu_path in PATH_MENU_PREFIXES:
        if str(path or "").startswith(prefix):
            return menu_path
    return None


def _has_runtime_menu_access(user, path):
    menu_path = _menu_path_for_request(path)
    if not menu_path:
        return False
    from .runtime_menu_store import user_menu_path_set

    return menu_path in user_menu_path_set(user)


def auth_required(roles=None):
    expected_roles = set(roles or [])

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            if not token:
                return failure("未登录或登录已过期", code=401, status=200)

            user = resolve_user_from_token(token)
            if not user or user.status != 1:
                return failure("未登录或登录已过期", code=401, status=200)

            g.current_user = user
            if expected_roles and not any(_matches_expected_role(user, role) for role in expected_roles):
                if not _has_runtime_menu_access(user, request.path):
                    return failure("当前账号无权访问该资源", code=403, status=200)
            return func(*args, **kwargs)

        return wrapper

    return decorator
