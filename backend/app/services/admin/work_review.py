"""作品审核校验及审计，单条和批量共用相同规则。"""

from datetime import UTC, datetime

from fastapi import HTTPException

from app.services.admin.audit import record_audit


def validate_review(body) -> None:
    """拒绝无效状态和无理由驳回，避免批量操作中途才发现输入问题。"""
    if body.visibility is not None and body.visibility.strip() not in ("public", "private", "unlisted"):
        raise HTTPException(status_code=400, detail="visibility 无效")
    if body.audit_status is not None and body.audit_status.strip() not in ("pending", "passed", "rejected"):
        raise HTTPException(status_code=400, detail="audit_status 无效")
    if (body.audit_status or "").strip() == "rejected" and not (body.audit_reason or "").strip():
        raise HTTPException(status_code=400, detail="驳回作品必须填写审核理由")
    if body.visibility is None and body.audit_status is None:
        raise HTTPException(status_code=400, detail="请选择审核或可见性操作")


def apply_review(db, work, body, admin) -> None:
    """调用方持有作品行锁后修改，审计与状态变更在同一事务提交。"""
    changes = {}
    for field in ("visibility", "audit_status"):
        value = getattr(body, field)
        if value is not None:
            value = value.strip()
            changes[field] = {"before": getattr(work, field), "after": value}
            setattr(work, field, value)
    if body.audit_status is not None:
        work.audit_reason = (body.audit_reason or "").strip()
        work.audited_by = admin.id
        work.audited_at = datetime.now(UTC)
        changes["audit_reason"] = work.audit_reason
    record_audit(db, admin, "work.review", "work", work.id, changes)
