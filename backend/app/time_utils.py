from datetime import datetime, timedelta, timezone


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def now_beijing():
    return datetime.now(BEIJING_TIMEZONE).replace(tzinfo=None)


def normalize_beijing_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(BEIJING_TIMEZONE).replace(tzinfo=None)


def serialize_datetime(value):
    normalized = normalize_beijing_datetime(value)
    return normalized.isoformat() if normalized else None


def format_datetime(value, pattern="%Y-%m-%d %H:%M:%S"):
    normalized = normalize_beijing_datetime(value)
    return normalized.strftime(pattern) if normalized else ""
