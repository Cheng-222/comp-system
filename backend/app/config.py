import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def build_database_uri():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    app_env = os.getenv("APP_ENV", "dev").lower()
    mysql_keys = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD")
    has_mysql_env = any(os.getenv(key) for key in mysql_keys)
    if not has_mysql_env and app_env in {"dev", "development", "local"}:
        sqlite_path = REPO_ROOT / "backend" / "data" / "app.db"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_path.resolve()}"

    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "competition_db")
    username = os.getenv("MYSQL_USER", "competition_user")
    password = os.getenv("MYSQL_PASSWORD", "change_me")
    return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def resolve_path(value, fallback):
    raw = value or fallback
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / raw
    return str(path.resolve())


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret")
    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    JSON_AS_ASCII = False
    TOKEN_EXPIRES_SECONDS = int(os.getenv("TOKEN_EXPIRES_SECONDS", "86400"))
    CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "*").split(",") if item.strip()]
    UPLOAD_DIR = resolve_path(os.getenv("UPLOAD_DIR"), "uploads")
    LOG_DIR = resolve_path(os.getenv("LOG_DIR"), "logs")
    DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin123!")
    DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "Demo123!")
    BAIDU_PAN_APP_KEY = os.getenv("BAIDU_PAN_APP_KEY", "")
    BAIDU_PAN_SECRET_KEY = os.getenv("BAIDU_PAN_SECRET_KEY", "")
    BAIDU_PAN_SIGN_KEY = os.getenv("BAIDU_PAN_SIGN_KEY", "")
    BAIDU_PAN_CALLBACK_URL = os.getenv("BAIDU_PAN_CALLBACK_URL", "http://localhost:5002/api/integrations/baidu-pan/callback")
    APP_AUTO_SEED = os.getenv("APP_AUTO_SEED", "true").lower() == "true"
