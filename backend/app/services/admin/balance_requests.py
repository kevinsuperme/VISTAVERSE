"""调账幂等和确认快照校验；调用方必须先锁住目标用户行。"""

import hashlib
import json

from fastapi import HTTPException

from app.models_admin import AdminBalanceRequest


def payload_fingerprint(body) -> str:
    """摘要覆盖金额、备注和余额快照，不在收据中重复保存敏感文本。"""
    payload = {
        "balance_delta_fen": body.balance_delta_fen,
        "balance_fen": body.balance_fen,
        "balance_note": (body.balance_note or "").strip(),
        "expected_balance_fen": body.expected_balance_fen,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


async def check_balance_request(db, actor, user, body) -> bool:
    """重放先于余额快照校验，相同成功请求重试不会被旧快照误拒绝。"""
    if body.balance_request_id is not None:
        receipt = await db.get(AdminBalanceRequest, (actor.id, user.id, str(body.balance_request_id)))
        if receipt is not None:
            if receipt.payload_hash != payload_fingerprint(body):
                raise HTTPException(status_code=409, detail="调账请求编号已用于其他内容，请重新确认")
            return True
    if body.expected_balance_fen is not None and int(user.balance_fen or 0) != body.expected_balance_fen:
        raise HTTPException(status_code=409, detail="用户余额已变化，请刷新详情并重新确认调账")
    return False


def record_balance_request(db, actor, user, body) -> None:
    """成功提交才保留收据，失败回滚后可安全重试同一请求。"""
    if body.balance_request_id is not None:
        db.add(AdminBalanceRequest(
            actor_id=actor.id, user_id=user.id, request_id=str(body.balance_request_id),
            payload_hash=payload_fingerprint(body), balance_after=int(user.balance_fen or 0),
        ))
