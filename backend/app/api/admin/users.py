# Admin user list and wallet/plan patch
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.models import User, WalletLedger
from app.schemas import AdminUserListOut, AdminUserOut, AdminUserPatch, PageMeta
from app.services.admin.audit import record_audit
from app.services.admin.balance_requests import check_balance_request, record_balance_request
from app.services.admin.permissions import ROLE_PERMISSIONS, require_permission

router = APIRouter()


@router.get("/users", response_model=AdminUserListOut)
async def list_users(
    q: str | None = None,
    plan: str | None = None,
    role: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListOut:
    # Paginated user search by email / nickname / id
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if q and q.strip():
        raw = q.strip()
        like = f"%{raw}%"
        id_match = None
        if raw.isdigit():
            id_match = int(raw)
        filt = or_(User.email.ilike(like), User.nickname.ilike(like))
        if id_match is not None:
            filt = or_(filt, User.id == id_match)
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)
    if plan and plan.strip():
        stmt = stmt.where(User.plan == plan.strip())
        count_stmt = count_stmt.where(User.plan == plan.strip())
    if role and role.strip():
        stmt = stmt.where(User.role == role.strip())
        count_stmt = count_stmt.where(User.role == role.strip())

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    result = await db.execute(
        stmt.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(result.scalars().all())
    return AdminUserListOut(
        items=[AdminUserOut.model_validate(u) for u in items],
        meta=PageMeta(page=page, page_size=page_size, total=total),
    )


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(user_id: int, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> AdminUserOut:
    """按主键读取用户，详情深链不受同名邮箱和列表页码影响。"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return AdminUserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def patch_user(
    user_id: int,
    body: AdminUserPatch,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserOut:
    # Update plan / role; balance changes write WalletLedger
    if body.plan is not None:
        require_permission(admin, "users:write")
    if body.role is not None:
        require_permission(admin, "users:role")
    if body.balance_delta_fen is not None or body.balance_fen is not None:
        require_permission(admin, "balance:write")
    balance_change = body.balance_delta_fen is not None or body.balance_fen is not None
    if body.balance_request_id is not None or body.expected_balance_fen is not None:
        if not balance_change or body.plan is not None or body.role is not None:
            raise HTTPException(status_code=400, detail="调账请求编号和余额快照只能用于独立调账")
        if body.balance_request_id is not None and body.expected_balance_fen is None:
            raise HTTPException(status_code=400, detail="请同时提供确认时的用户余额")
    # 余额更新必须锁住用户行；否则两个管理员并发调账会基于同一旧余额
    # 写入，导致实际余额与 WalletLedger 的 balance_after 不一致。
    user = (
        await db.execute(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if balance_change and await check_balance_request(db, admin, user, body):
        # 释放行锁；余额可能已被其他合法请求更新，返回当前用户状态。
        await db.commit()
        return AdminUserOut.model_validate(user)

    before = {key: getattr(user, key) for key in ("plan", "role", "balance_fen")}

    if body.plan is not None:
        user.plan = body.plan.strip() or "free"

    if body.role is not None:
        role = body.role.strip()
        if role not in {"user", *ROLE_PERMISSIONS}:
            raise HTTPException(status_code=400, detail="role 无效")
        if user.id == admin.id and role != "admin":
            raise HTTPException(status_code=400, detail="不能降低自己的管理员权限")
        user.role = role

    if body.balance_delta_fen is not None and body.balance_fen is not None:
        raise HTTPException(status_code=400, detail="请只传 balance_delta_fen 或 balance_fen 之一")

    current = int(user.balance_fen or 0)
    delta: int | None = None
    if body.balance_delta_fen is not None:
        delta = int(body.balance_delta_fen)
    elif body.balance_fen is not None:
        target = int(body.balance_fen)
        if target < 0:
            raise HTTPException(status_code=400, detail="余额不能为负")
        delta = target - current

    if delta is not None and delta != 0:
        if not (body.balance_note or "").strip():
            raise HTTPException(status_code=400, detail="请填写调账原因")
        target = current + delta
        if target < 0:
            raise HTTPException(status_code=400, detail="余额不能减为负数")
        if target > 2_147_483_647:
            raise HTTPException(status_code=400, detail="调整后余额超过系统支持上限")
        user.balance_fen = target
        db.add(
            WalletLedger(
                user_id=user.id,
                delta_fen=delta,
                balance_after=target,
                kind="adjust" if delta < 0 else "grant",
                ref_type="admin",
                ref_id=str(admin.id),
                note=(body.balance_note or "").strip() or "admin_adjust",
            )
        )

    changes = {key: {"before": value, "after": getattr(user, key)}
               for key, value in before.items() if value != getattr(user, key)}
    if changes:
        # 备注可能含用户粘贴的敏感内容；WalletLedger 保留业务备注，审计只记结构化余额前后值。
        record_audit(db, admin, "user.update", "user", user.id, changes)
    if balance_change:
        record_balance_request(db, admin, user, body)
    await db.commit()
    await db.refresh(user)
    return AdminUserOut.model_validate(user)
