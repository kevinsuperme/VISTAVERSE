"""与业务变更同事务写入后台审计。"""

from app.models_admin import AdminAuditLog


def record_audit(db, actor, action: str, target_type: str, target_id, changes: dict) -> None:
    """调用方显式选取安全字段，审计不单独提交。"""
    db.add(AdminAuditLog(actor_id=actor.id, action=action, target_type=target_type,
                         target_id=str(target_id), changes=changes))
