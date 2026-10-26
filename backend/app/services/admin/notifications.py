"""从真实任务、待审核作品和运行时健康状态构造可分页通知。"""

from datetime import UTC, datetime

from sqlalchemy import String, cast, false, func, literal, select, union_all

from app.models import Work
from app.models_tasks import TaskRun
from app.services.admin.permissions import permissions_for
from app.services.tasks.runtime import runtime_summary

# 每次进程中的异常周期使用独立 ID；恢复后再次异常会重新提示。
_runtime_incident: datetime | None = None


def notification_source(user):
    """权限筛选在 SQL 分页前执行，不拉全表后在内存裁剪。"""
    global _runtime_incident
    permissions = permissions_for(user.role)
    sources = []
    if "tasks:read" in permissions:
        task_time = func.coalesce(TaskRun.updated_at, TaskRun.created_at, func.now())
        task_key = literal("task:") + cast(TaskRun.id, String) + literal(":") + cast(func.extract("epoch", task_time), String)
        sources.append(select(
            task_key.label("id"), literal("task_failed").label("kind"), literal("error").label("severity"),
            (literal("任务失败 #") + cast(TaskRun.id, String)).label("title"),
            (literal("任务类型：") + TaskRun.task_type).label("message"),
            (literal("/queues?task=") + cast(TaskRun.id, String)).label("href"),
            task_time.label("created_at"),
        ).where(TaskRun.status == "failed"))
        runtime = runtime_summary()
        if runtime.get("enabled") and not runtime.get("healthy"):
            _runtime_incident = _runtime_incident or datetime.now(UTC)
            sources.append(select(
                literal("runtime:" + _runtime_incident.isoformat()).label("id"),
                literal("runtime_alert").label("kind"), literal("error").label("severity"),
                literal("任务运行时异常").label("title"),
                literal("调度器或轮询心跳异常，请打开任务中心检查运行状态。").label("message"),
                literal("/queues").label("href"), literal(_runtime_incident).label("created_at"),
            ))
        else:
            _runtime_incident = None
    if "works:read" in permissions:
        work_time = func.coalesce(Work.audited_at, Work.published_at)
        work_key = literal("work:") + cast(Work.id, String) + literal(":") + cast(func.extract("epoch", work_time), String)
        sources.append(select(
            work_key.label("id"), literal("work_pending").label("kind"), literal("warning").label("severity"),
            (literal("待审核：") + Work.title).label("title"),
            literal("请查看作品并记录审核结论。").label("message"),
            (literal("/works?work=") + cast(Work.id, String)).label("href"), work_time.label("created_at"),
        ).where(Work.audit_status == "pending"))
    if not sources:
        sources.append(select(
            literal("").label("id"), literal("").label("kind"), literal("").label("severity"),
            literal("").label("title"), literal("").label("message"), literal("").label("href"),
            literal(datetime.now(UTC)).label("created_at"),
        ).where(false()))
    return union_all(*sources).subquery()
