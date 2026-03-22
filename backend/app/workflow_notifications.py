from sqlalchemy import or_

from .message_service import create_and_dispatch_message
from .models import ContestPermission, SysRole, SysUser


STATUS_LABELS = {
    "submitted": "已提交",
    "reviewing": "审核中",
    "correction_required": "待补正",
    "approved": "已通过",
    "rejected": "已驳回",
    "withdrawn": "已退赛",
    "replaced": "已换人",
    "supplemented": "补录中",
}


def status_label(value):
    return STATUS_LABELS.get(value, value or "待确认")


def student_account_user_ids(student):
    if not student:
        return []
    rows = (
        SysUser.query.join(SysUser.roles)
        .filter(
            SysUser.status == 1,
            SysRole.role_code == "student",
            or_(SysUser.student_id == student.id, SysUser.username == student.student_no),
        )
        .with_entities(SysUser.id)
        .distinct()
        .all()
    )
    return [int(item[0]) for item in rows]


def contest_user_ids(contest_id, scopes, role_code):
    user_ids = {
        int(item[0])
        for item in (
            ContestPermission.query.join(ContestPermission.user).join(SysUser.roles)
            .filter(
                ContestPermission.contest_id == contest_id,
                ContestPermission.permission_scope.in_(sorted(set(scopes))),
                SysUser.status == 1,
                SysRole.role_code == role_code,
            )
            .with_entities(ContestPermission.user_id)
            .distinct()
            .all()
        )
    }
    return sorted(user_ids)


def unique_user_ids(*groups):
    merged = []
    seen = set()
    for group in groups:
        for user_id in group or []:
            if user_id in seen:
                continue
            seen.add(user_id)
            merged.append(int(user_id))
    return merged


def actor_name(actor_user_id):
    if not actor_user_id:
        return "系统"
    actor = SysUser.query.get(actor_user_id)
    return actor.real_name if actor else "系统"


def build_context(registration, reason, actor_user_id):
    return {
        "contest_name": registration.contest.contest_name if registration.contest else "当前赛事",
        "student_name": registration.student.name if registration.student else "当前学生",
        "project_name": registration.project_name or "未命名项目",
        "status_label": status_label(registration.final_status),
        "reason": reason or "无补充说明",
        "actor_name": actor_name(actor_user_id),
    }


def send_message(payload):
    if not payload.get("target_user_ids"):
        return None
    return create_and_dispatch_message(**payload)


def send_registration_workflow_messages(
    *,
    event,
    registration,
    actor_user_id,
    reason="",
    flow_log_id=None,
    replacement_registration=None,
    replacement_flow_log_id=None,
):
    manager_user_ids = contest_user_ids(registration.contest_id, {"manage", "result"}, "teacher")
    reviewer_user_ids = contest_user_ids(registration.contest_id, {"review"}, "reviewer")
    student_user_ids = student_account_user_ids(registration.student)
    context = build_context(registration, reason, actor_user_id)
    messages = []

    if event == "submit_materials":
        messages.append(
            send_message(
                {
                    "title": f"待审核：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 已提交报名材料，等待审核处理。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"提交人：{context['actor_name']}\n"
                        f"说明：{context['reason']}\n"
                        "下一步：请进入材料审核页面处理通过、驳回或退回补正。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "todo",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["teacher", "reviewer"],
                    "target_user_ids": unique_user_ids(manager_user_ids, reviewer_user_ids),
                    "target_status": registration.final_status,
                    "priority": "high",
                    "source_key": f"workflow:submit_materials:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
    elif event == "submit_correction":
        messages.append(
            send_message(
                {
                    "title": f"补正已提交：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 已重新提交补正材料，等待复核。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"提交人：{context['actor_name']}\n"
                        f"补充说明：{context['reason']}\n"
                        "下一步：请进入材料审核页面继续复核。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "todo",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["teacher", "reviewer"],
                    "target_user_ids": unique_user_ids(manager_user_ids, reviewer_user_ids),
                    "target_status": registration.final_status,
                    "priority": "high",
                    "source_key": f"workflow:submit_correction:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
    elif event == "review_approve":
        messages.append(
            send_message(
                {
                    "title": f"审核通过：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 的报名已审核通过。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"处理人：{context['actor_name']}\n"
                        f"审核意见：{context['reason']}\n"
                        "下一步：报名主审核流程已完成，如需退赛、换人或补录，请由老师进入资格管理处理。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "message",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["student", "teacher"],
                    "target_user_ids": unique_user_ids(student_user_ids, manager_user_ids),
                    "target_status": registration.final_status,
                    "priority": "normal",
                    "source_key": f"workflow:review_approve:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
    elif event == "review_reject":
        messages.append(
            send_message(
                {
                    "title": f"审核驳回：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 的报名已被驳回。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"处理人：{context['actor_name']}\n"
                        f"审核意见：{context['reason']}\n"
                        "下一步：如需继续参赛，请联系负责老师确认是否通过资格管理补录。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "message",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["student", "teacher"],
                    "target_user_ids": unique_user_ids(student_user_ids, manager_user_ids),
                    "target_status": registration.final_status,
                    "priority": "high",
                    "source_key": f"workflow:review_reject:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
    elif event == "review_correction_required":
        messages.append(
            send_message(
                {
                    "title": f"补正提醒：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 的报名被退回补正，请尽快补材料。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"处理人：{context['actor_name']}\n"
                        f"审核意见：{context['reason']}\n"
                        "下一步：请回到报名管理，用“提交补正”补齐材料后重新送审。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "todo",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["student", "teacher"],
                    "target_user_ids": unique_user_ids(student_user_ids, manager_user_ids),
                    "target_status": registration.final_status,
                    "priority": "high",
                    "source_key": f"workflow:review_correction_required:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
    elif event == "withdraw":
        messages.append(
            send_message(
                {
                    "title": f"退赛确认：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 的报名已退出当前赛事流程。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"处理人：{context['actor_name']}\n"
                        f"原因：{context['reason']}\n"
                        "下一步：这条报名记录已结束，无需继续提交材料或审核。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "message",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["student", "teacher"],
                    "target_user_ids": unique_user_ids(student_user_ids, manager_user_ids),
                    "target_status": registration.final_status,
                    "priority": "normal",
                    "source_key": f"workflow:withdraw:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
    elif event == "replace":
        messages.append(
            send_message(
                {
                    "title": f"资格变更：{context['contest_name']} / {context['student_name']} 已换人",
                    "summary": f"{context['student_name']} 的原报名名额已转出。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"处理人：{context['actor_name']}\n"
                        f"原因：{context['reason']}\n"
                        "下一步：后续流程会在新的补录记录中继续推进。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "message",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["student", "teacher"],
                    "target_user_ids": unique_user_ids(student_user_ids, manager_user_ids),
                    "target_status": registration.final_status,
                    "priority": "normal",
                    "source_key": f"workflow:replace_current:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )
        if replacement_registration:
            replacement_context = build_context(replacement_registration, reason, actor_user_id)
            replacement_student_ids = student_account_user_ids(replacement_registration.student)
            replacement_manager_ids = contest_user_ids(replacement_registration.contest_id, {"manage", "result"}, "teacher")
            messages.append(
                send_message(
                    {
                        "title": f"补录通知：{replacement_context['contest_name']} / {replacement_context['student_name']}",
                        "summary": f"{replacement_context['student_name']} 已承接新的补录报名记录。",
                        "content": (
                            f"赛事：{replacement_context['contest_name']}\n"
                            f"学生：{replacement_context['student_name']}\n"
                            f"项目：{replacement_context['project_name']}\n"
                            f"当前状态：{replacement_context['status_label']}\n"
                            f"处理人：{replacement_context['actor_name']}\n"
                            f"原因：{replacement_context['reason']}\n"
                            "下一步：请尽快在报名管理补齐材料，再送入审核。"
                        ),
                        "created_by": actor_user_id,
                        "message_type": "todo",
                        "target_scope": "contest",
                        "contest_id": replacement_registration.contest_id,
                        "target_roles": ["student", "teacher"],
                        "target_user_ids": unique_user_ids(replacement_student_ids, replacement_manager_ids),
                        "target_status": replacement_registration.final_status,
                        "priority": "high",
                        "source_key": f"workflow:replace_replacement:registration:{replacement_registration.id}:flow:{replacement_flow_log_id}",
                    }
                )
            )
    elif event == "supplement":
        messages.append(
            send_message(
                {
                    "title": f"补录已发起：{context['contest_name']} / {context['student_name']}",
                    "summary": f"{context['student_name']} 的报名已进入补录流程。",
                    "content": (
                        f"赛事：{context['contest_name']}\n"
                        f"学生：{context['student_name']}\n"
                        f"项目：{context['project_name']}\n"
                        f"当前状态：{context['status_label']}\n"
                        f"处理人：{context['actor_name']}\n"
                        f"原因：{context['reason']}\n"
                        "下一步：请尽快补齐材料，再把记录重新送进审核。"
                    ),
                    "created_by": actor_user_id,
                    "message_type": "todo",
                    "target_scope": "contest",
                    "contest_id": registration.contest_id,
                    "target_roles": ["student", "teacher"],
                    "target_user_ids": unique_user_ids(student_user_ids, manager_user_ids),
                    "target_status": registration.final_status,
                    "priority": "high",
                    "source_key": f"workflow:supplement:registration:{registration.id}:flow:{flow_log_id}",
                }
            )
        )

    return [item for item in messages if item]
