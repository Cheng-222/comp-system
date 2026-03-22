from datetime import datetime
from pathlib import Path

from .access import (
    CONTEST_MANAGE_SCOPES,
    CONTEST_REVIEW_SCOPES,
    can_view_result_record,
    current_contest_scopes,
    has_contest_scope,
    is_admin_user,
    is_reviewer_user,
    is_student_user,
    is_teacher_user,
    resolve_bound_student,
)
from .data_scope import student_in_college_scope
from .errors import APIError
from .models import (
    AttachmentInfo,
    ContestInfo,
    ContestRegistration,
    ContestResult,
    ExportTask,
    RegistrationMaterial,
    StudentInfo,
    SysUser,
)
from .platform_ops import backup_file_path, list_backup_files


FILE_CATEGORY_META = {
    "contest_rule": {"label": "赛事规则", "groupCode": "platform_attachment", "groupLabel": "平台附件"},
    "registration_material": {"label": "报名材料", "groupCode": "platform_attachment", "groupLabel": "平台附件"},
    "certificate": {"label": "证书文件", "groupCode": "platform_attachment", "groupLabel": "平台附件"},
    "export_file": {"label": "导出文件", "groupCode": "task_output", "groupLabel": "任务产物"},
    "import_template": {"label": "导入模板", "groupCode": "task_output", "groupLabel": "任务产物"},
    "import_source": {"label": "导入源文件", "groupCode": "task_output", "groupLabel": "任务产物"},
    "backup_package": {"label": "系统备份", "groupCode": "system_runtime", "groupLabel": "系统运维"},
    "other_file": {"label": "其他文件", "groupCode": "task_output", "groupLabel": "任务产物"},
}

FILE_GROUP_ORDER = ["platform_attachment", "task_output", "system_runtime"]
CATEGORY_ORDER = ["contest_rule", "registration_material", "certificate", "export_file", "import_template", "import_source", "backup_package", "other_file"]
NON_PREVIEWABLE_EXTENSIONS = {"zip", "rar", "7z", "tar", "gz", "bz2"}


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def attachment_context():
    attachments = AttachmentInfo.query.order_by(AttachmentInfo.uploaded_at.desc(), AttachmentInfo.id.desc()).all()
    return {
        "attachments": attachments,
        "contests": {item.id: item for item in ContestInfo.query.all()},
        "students": {item.id: item for item in StudentInfo.query.all()},
        "materials": {item.id: item for item in RegistrationMaterial.query.all()},
        "registrations": {item.id: item for item in ContestRegistration.query.all()},
        "results": {item.id: item for item in ContestResult.query.all()},
        "users": {item.id: item for item in SysUser.query.all()},
        "exportTasks": {item.file_id: item for item in ExportTask.query.filter(ExportTask.file_id.isnot(None)).all()},
    }


def attachment_meta(attachment, context):
    biz_type = str(attachment.biz_type or "").strip()
    uploader = context["users"].get(attachment.uploader_id)
    base = {
        "assetType": "attachment",
        "assetId": str(attachment.id),
        "fileId": attachment.id,
        "fileName": attachment.file_name,
        "fileExt": str(attachment.file_ext or "").lower(),
        "fileSize": int(attachment.file_size or 0),
        "bizType": biz_type,
        "uploaderId": attachment.uploader_id,
        "uploaderName": uploader.real_name if uploader else None,
        "createdAt": attachment.uploaded_at.isoformat() if attachment.uploaded_at else None,
        "contestId": None,
        "contestName": None,
        "studentId": None,
        "studentName": None,
        "college": None,
        "sourceName": attachment.file_name,
        "_path": str(attachment.file_path or ""),
        "_createdAt": attachment.uploaded_at,
    }

    if biz_type.startswith("contest_rule:"):
        contest_id = parse_int(biz_type.split(":", 1)[1])
        contest = context["contests"].get(contest_id)
        base.update(
            {
                "categoryCode": "contest_rule",
                "contestId": contest_id,
                "contestName": contest.contest_name if contest else None,
                "sourceName": contest.contest_name if contest else "赛事规则",
                "_contestId": contest_id,
            }
        )
        return base

    if biz_type.startswith("registration_material:"):
        material_id = parse_int(biz_type.split(":", 1)[1])
        material = context["materials"].get(material_id)
        registration = context["registrations"].get(material.registration_id) if material else None
        contest = context["contests"].get(registration.contest_id) if registration else None
        student = context["students"].get(registration.student_id) if registration else None
        base.update(
            {
                "categoryCode": "registration_material",
                "contestId": contest.id if contest else None,
                "contestName": contest.contest_name if contest else None,
                "studentId": student.id if student else None,
                "studentName": student.name if student else None,
                "college": student.college if student else None,
                "sourceName": f"{contest.contest_name if contest else '未知赛事'} / {student.name if student else '未知学生'} / {material.material_type if material else '材料'}",
                "_registration": registration,
            }
        )
        return base

    if biz_type.startswith("certificate:"):
        result_id = parse_int(biz_type.split(":", 1)[1])
        result = context["results"].get(result_id)
        contest = context["contests"].get(result.contest_id) if result else None
        student = context["students"].get(result.student_id) if result else None
        base.update(
            {
                "categoryCode": "certificate",
                "contestId": contest.id if contest else None,
                "contestName": contest.contest_name if contest else None,
                "studentId": student.id if student else None,
                "studentName": student.name if student else None,
                "college": student.college if student else None,
                "sourceName": f"{contest.contest_name if contest else '未知赛事'} / {student.name if student else '未知学生'} / 证书归档",
                "_result": result,
            }
        )
        return base

    export_task = context["exportTasks"].get(attachment.id)
    if export_task is not None:
        base.update(
            {
                "categoryCode": "export_file",
                "sourceName": export_task.task_name or attachment.file_name,
                "taskType": export_task.task_type,
                "taskStatus": export_task.status,
                "_exportTask": export_task,
            }
        )
        return base

    if "import_template" in biz_type:
        base.update({"categoryCode": "import_template", "sourceName": attachment.file_name})
        return base

    if biz_type.endswith("_import_source"):
        base.update({"categoryCode": "import_source", "sourceName": attachment.file_name})
        return base

    if biz_type.endswith("_export") or biz_type.startswith("registration_export:") or biz_type.startswith("file_export_batch"):
        base.update({"categoryCode": "export_file", "sourceName": attachment.file_name})
        return base

    base.update({"categoryCode": "other_file", "sourceName": attachment.file_name})
    return base


def backup_meta(item):
    created_at = item.get("createdAt")
    created_dt = None
    if created_at:
        try:
            created_dt = datetime.fromisoformat(str(created_at))
        except ValueError:
            created_dt = None
    return {
        "assetType": "backup",
        "assetId": item["fileName"],
        "fileId": None,
        "fileName": item["fileName"],
        "fileExt": Path(item["fileName"]).suffix.lower().lstrip("."),
        "fileSize": int(item.get("fileSize") or 0),
        "bizType": "system_backup",
        "uploaderId": None,
        "uploaderName": "系统管理员",
        "createdAt": created_at,
        "contestId": None,
        "contestName": None,
        "studentId": None,
        "studentName": None,
        "college": None,
        "categoryCode": "backup_package",
        "sourceName": "系统备份包",
        "_path": str(item.get("path") or ""),
        "_createdAt": created_dt,
    }


def can_access_meta(meta, user):
    category_code = meta.get("categoryCode")
    if category_code == "backup_package":
        return is_admin_user(user)

    if category_code == "contest_rule":
        contest_id = meta.get("_contestId")
        return is_admin_user(user) or bool(contest_id and current_contest_scopes(contest_id, user=user))

    if category_code == "registration_material":
        registration = meta.get("_registration")
        if registration is None:
            return is_admin_user(user)
        if is_admin_user(user):
            return True
        student = registration.student or StudentInfo.query.get(registration.student_id)
        if is_teacher_user(user):
            return has_contest_scope(registration.contest_id, CONTEST_MANAGE_SCOPES, user=user) and student_in_college_scope(student, user)
        if is_reviewer_user(user):
            return has_contest_scope(registration.contest_id, CONTEST_REVIEW_SCOPES, user=user) and student_in_college_scope(student, user)
        if is_student_user(user):
            bound_student = resolve_bound_student(user=user)
            return bool(bound_student and int(bound_student.id) == int(registration.student_id))
        return False

    if category_code == "certificate":
        result = meta.get("_result")
        return bool(result and can_view_result_record(result, user=user))

    export_task = meta.get("_exportTask")
    if export_task is not None:
        return is_admin_user(user) or int(export_task.created_by or 0) == int(user.id)

    if is_admin_user(user):
        return True

    return int(meta.get("uploaderId") or 0) == int(user.id)


def public_meta(meta):
    category_meta = FILE_CATEGORY_META[meta["categoryCode"]]
    file_ext = str(meta.get("fileExt") or "").lower()
    return {
        "assetType": meta["assetType"],
        "assetId": meta["assetId"],
        "fileId": meta["fileId"],
        "fileName": meta["fileName"],
        "fileExt": file_ext,
        "fileSize": meta["fileSize"],
        "bizType": meta["bizType"],
        "categoryCode": meta["categoryCode"],
        "categoryName": category_meta["label"],
        "groupCode": category_meta["groupCode"],
        "groupName": category_meta["groupLabel"],
        "uploaderId": meta["uploaderId"],
        "uploaderName": meta["uploaderName"],
        "createdAt": meta["createdAt"],
        "contestId": meta["contestId"],
        "contestName": meta["contestName"],
        "studentId": meta["studentId"],
        "studentName": meta["studentName"],
        "college": meta["college"],
        "sourceName": meta["sourceName"],
        "previewable": meta["assetType"] != "backup" and file_ext not in NON_PREVIEWABLE_EXTENSIONS,
    }


def visible_assets(user, include_internal=False):
    context = attachment_context()
    rows = []
    for attachment in context["attachments"]:
        file_path = Path(str(attachment.file_path or ""))
        if not file_path.exists():
            continue
        meta = attachment_meta(attachment, context)
        if can_access_meta(meta, user):
            payload = public_meta(meta)
            payload["_sort"] = payload["createdAt"] or ""
            if include_internal:
                payload["_path"] = meta.get("_path") or str(file_path)
                payload["_createdAt"] = meta.get("_createdAt")
            rows.append(payload)

    if is_admin_user(user):
        for item in list_backup_files():
            meta = backup_meta(item)
            payload = public_meta(meta)
            payload["_sort"] = payload["createdAt"] or ""
            if include_internal:
                payload["_path"] = meta.get("_path")
                payload["_createdAt"] = meta.get("_createdAt")
            rows.append(payload)

    rows.sort(key=lambda item: (item.get("_sort") or "", item["fileName"]), reverse=True)
    return rows


def category_tree(items):
    total = len(items)
    grouped_counts = {}
    category_counts = {}
    for item in items:
        grouped_counts[item["groupCode"]] = grouped_counts.get(item["groupCode"], 0) + 1
        category_counts[item["categoryCode"]] = category_counts.get(item["categoryCode"], 0) + 1

    children = []
    for group_code in FILE_GROUP_ORDER:
        if grouped_counts.get(group_code, 0) == 0:
            continue
        category_children = []
        for category_code in CATEGORY_ORDER:
            category_meta = FILE_CATEGORY_META[category_code]
            if category_meta["groupCode"] != group_code or category_counts.get(category_code, 0) == 0:
                continue
            category_children.append(
                {
                    "id": category_code,
                    "label": f'{category_meta["label"]}（{category_counts[category_code]}）',
                    "count": category_counts[category_code],
                }
            )
        group_name = next(meta["groupLabel"] for meta in FILE_CATEGORY_META.values() if meta["groupCode"] == group_code)
        children.append(
            {
                "id": f"group:{group_code}",
                "label": f"{group_name}（{grouped_counts[group_code]}）",
                "count": grouped_counts[group_code],
                "children": category_children,
            }
        )
    return {
        "id": "all",
        "label": f"全部文件（{total}）",
        "count": total,
        "children": children,
    }


def summary(items):
    total_size = sum(int(item.get("fileSize") or 0) for item in items)
    return {
        "totalFiles": len(items),
        "totalSize": total_size,
        "categoryCount": len({item["categoryCode"] for item in items}),
        "exportCount": sum(1 for item in items if item["categoryCode"] == "export_file"),
    }


def filter_assets(items, params):
    keyword = str((params or {}).get("keyword") or "").strip().lower()
    contest_id = parse_int((params or {}).get("contestId"))
    category_code = str((params or {}).get("categoryCode") or "").strip()

    rows = list(items)
    if category_code and category_code != "all":
        if category_code.startswith("group:"):
            group_code = category_code.split(":", 1)[1]
            rows = [item for item in rows if item["groupCode"] == group_code]
        else:
            rows = [item for item in rows if item["categoryCode"] == category_code]
    if contest_id:
        rows = [item for item in rows if int(item.get("contestId") or 0) == contest_id]
    if keyword:
        rows = [
            item
            for item in rows
            if keyword in " ".join(
                str(item.get(field) or "").lower()
                for field in ("fileName", "sourceName", "contestName", "studentName", "college", "categoryName", "groupName", "bizType")
            )
        ]
    return rows


def resolve_asset_file(user, asset_type, asset_id):
    if asset_type == "backup":
        if not is_admin_user(user):
            raise APIError("当前账号无权查看该备份文件", code=403, status=200)
        target_path = backup_file_path(asset_id)
        if not target_path.exists():
            raise APIError("文件不存在", status=404)
        return {"path": str(target_path), "fileName": target_path.name}

    attachment = AttachmentInfo.query.get(parse_int(asset_id) or 0)
    if not attachment:
        raise APIError("文件不存在", status=404)
    meta = attachment_meta(attachment, attachment_context())
    if not can_access_meta(meta, user):
        raise APIError("当前账号无权查看该文件", code=403, status=200)
    target_path = Path(str(attachment.file_path or ""))
    if not target_path.exists():
        raise APIError("文件不存在", status=404)
    return {"path": str(target_path), "fileName": attachment.file_name}
