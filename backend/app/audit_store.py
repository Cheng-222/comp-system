from .extensions import db
from .models import AuditLoginInfo, AuditOperLog


def infer_title(path):
    path = path or ""
    mapping = (
        ("/system/config/runtimeProfile", "存储与备份"),
        ("/system/config/backup", "存储与备份"),
        ("/system/user", "账号管理"),
        ("/system/role", "角色管理"),
        ("/system/menu", "菜单管理"),
        ("/system/dict", "字典管理"),
        ("/system/config", "参数管理"),
        ("/monitor/operlog", "操作日志"),
        ("/monitor/logininfor", "登录日志"),
        ("/api/v1/students", "学生管理"),
        ("/api/v1/contests", "赛事管理"),
        ("/api/v1/registrations", "报名管理"),
        ("/api/v1/messages", "通知中心"),
        ("/api/v1/results", "赛后管理"),
        ("/api/v1/statistics", "统计报表"),
        ("/login", "登录管理"),
        ("/getInfo", "认证鉴权"),
        ("/getRouters", "认证鉴权"),
    )
    for prefix, title in mapping:
        if path.startswith(prefix):
            return title
    return "竞赛管理系统"


def infer_business_type(method, path):
    path = path or ""
    if "/export" in path:
        return "5"
    if "/import" in path or "/upload" in path:
        return "6"
    if "/auth" in path or "/roleMenuTreeselect" in path:
        return "4"
    return {
        "POST": "1",
        "PUT": "2",
        "DELETE": "3",
    }.get((method or "GET").upper(), "0")


def _serialize_login_event(row):
    return {
        "infoId": row.id,
        "userName": row.user_name,
        "ipaddr": row.ipaddr,
        "loginLocation": row.login_location,
        "browser": row.browser,
        "os": row.os,
        "status": row.status,
        "msg": row.msg,
        "loginTime": row.login_time.isoformat() if row.login_time else None,
    }


def _serialize_oper_event(row):
    return {
        "operId": row.id,
        "title": row.title,
        "businessType": row.business_type,
        "operName": row.oper_name,
        "operIp": row.oper_ip,
        "operLocation": row.oper_location,
        "operUrl": row.oper_url,
        "requestMethod": row.request_method,
        "method": row.method,
        "operParam": row.oper_param,
        "jsonResult": row.json_result,
        "status": row.status,
        "errorMsg": row.error_msg,
        "costTime": row.cost_time,
        "operTime": row.oper_time.isoformat() if row.oper_time else None,
    }


def record_login_event(user_name, status, msg, ipaddr="127.0.0.1", user_agent=""):
    try:
        db.session.add(
            AuditLoginInfo(
                user_name=user_name or "unknown",
                ipaddr=ipaddr or "127.0.0.1",
                login_location="本地开发环境",
                browser=user_agent or "Browser",
                os=user_agent or "OS",
                status=str(status),
                msg=msg or "",
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def list_login_events():
    rows = AuditLoginInfo.query.order_by(AuditLoginInfo.login_time.desc(), AuditLoginInfo.id.desc()).all()
    return [_serialize_login_event(item) for item in rows]


def delete_login_events(info_ids):
    ids = {int(item) for item in str(info_ids).split(",") if str(item).strip()}
    if ids:
        AuditLoginInfo.query.filter(AuditLoginInfo.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def clean_login_events():
    AuditLoginInfo.query.delete(synchronize_session=False)
    db.session.commit()


def record_oper_event(
    *,
    title,
    business_type,
    oper_name,
    oper_url,
    request_method,
    method,
    oper_param,
    json_result,
    status,
    error_msg="",
    oper_ip="127.0.0.1",
    cost_time=0,
):
    try:
        db.session.add(
            AuditOperLog(
                title=title or "竞赛管理系统",
                business_type=str(business_type or "0"),
                oper_name=oper_name or "anonymous",
                oper_ip=oper_ip or "127.0.0.1",
                oper_location="本地开发环境",
                oper_url=oper_url or "",
                request_method=request_method or "",
                method=method or "",
                oper_param=oper_param or "",
                json_result=json_result or "",
                status=int(status or 0),
                error_msg=error_msg or "",
                cost_time=int(cost_time or 0),
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def list_oper_events():
    rows = AuditOperLog.query.order_by(AuditOperLog.oper_time.desc(), AuditOperLog.id.desc()).all()
    return [_serialize_oper_event(item) for item in rows]


def delete_oper_events(oper_ids):
    ids = {int(item) for item in str(oper_ids).split(",") if str(item).strip()}
    if ids:
        AuditOperLog.query.filter(AuditOperLog.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def clean_oper_events():
    AuditOperLog.query.delete(synchronize_session=False)
    db.session.commit()
