"""管理端通知列表与幂等已读接口。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.models import User
from app.models_admin import AdminNotificationRead
from app.schemas_admin import AdminNotificationReadPatch
from app.services.admin.notifications import notification_source

router = APIRouter()


@router.get("/notifications")
async def list_notifications(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), unread_only: bool = False,
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
) -> dict:
    """先按角色过滤来源，再计算本人未读和分页，不泄露其他管理员状态。"""
    source = notification_source(_admin)
    joined = source.outerjoin(AdminNotificationRead, and_(
        AdminNotificationRead.notification_id == source.c.id, AdminNotificationRead.user_id == _admin.id,
    ))
    unread = AdminNotificationRead.notification_id.is_(None)
    unread_count = int((await db.scalar(select(func.count()).select_from(joined).where(unread))) or 0)
    conditions = [unread] if unread_only else []
    total = int((await db.scalar(select(func.count()).select_from(joined).where(*conditions))) or 0)
    rows = (await db.execute(select(source, AdminNotificationRead.read_at).select_from(joined)
                            .where(*conditions).order_by(source.c.created_at.desc(), source.c.id)
                            .offset((page - 1) * page_size).limit(page_size))).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        item["read"] = item.pop("read_at") is not None
        items.append(item)
    return {"items": items, "meta": {"page": page, "page_size": page_size, "total": total}, "unread_count": unread_count}


@router.patch("/notifications/read")
async def mark_notifications_read(
    body: AdminNotificationReadPatch, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
) -> dict:
    """只标记当前角色可见的真实通知，重复请求不会重复插入。"""
    source = notification_source(_admin)
    valid_ids = list((await db.scalars(select(source.c.id).where(source.c.id.in_(set(body.ids))))).all())
    if valid_ids:
        await db.execute(insert(AdminNotificationRead).values([
            {"user_id": _admin.id, "notification_id": notification_id} for notification_id in valid_ids
        ]).on_conflict_do_nothing(index_elements=["user_id", "notification_id"]))
        await db.commit()
    return {"marked": len(valid_ids)}
