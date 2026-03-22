from datetime import datetime

from flask import jsonify, request

from .errors import APIError
from .time_utils import normalize_beijing_datetime


def success(data=None, message="success", code=200, status=200):
    return jsonify({"code": code, "msg": message, "message": message, "data": data, "traceId": None}), status


def failure(message, code=400, status=None, data=None):
    return jsonify({"code": code, "msg": message, "message": message, "data": data or {}, "traceId": None}), status or code


def parse_datetime(value, field_name):
    if not value:
        return None
    if isinstance(value, datetime):
        return normalize_beijing_datetime(value)
    normalized = str(value).strip()
    try:
        return normalize_beijing_datetime(datetime.fromisoformat(normalized.replace("Z", "+00:00")))
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    raise APIError(f"{field_name} 时间格式错误，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")


def get_pagination_args():
    page_num = max(int(request.args.get("pageNum", 1)), 1)
    page_size = max(min(int(request.args.get("pageSize", 10)), 100), 1)
    return page_num, page_size


def paginate_query(query):
    page_num, page_size = get_pagination_args()
    pagination = query.paginate(page=page_num, per_page=page_size, error_out=False)
    return pagination.items, pagination.total, page_num, page_size


def paginate_items(items):
    page_num, page_size = get_pagination_args()
    total = len(items)
    start = (page_num - 1) * page_size
    end = start + page_size
    return items[start:end], total, page_num, page_size
