# Admin work audit (visibility / audit_status)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import get_db
from app.deps import get_current_admin
from app.models import User, Work
from app.schemas import AdminWorkListOut, AdminWorkOut, AdminWorkPatch, PageMeta
from app.schemas_admin import AdminWorkBulk
from app.services.admin.exports import EXPORT_LIMIT, csv_response, work_filters
from app.services.admin.work_review import apply_review, validate_review

router = APIRouter()


@router.get("/works", response_model=AdminWorkListOut)
async def list_works(
    audit_status: str | None = None,
    visibility: str | None = None,
    q: str | None = None,
    user_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminWorkListOut:
    # Paginated published works
    owner = aliased(User)
    stmt = select(Work, owner.email).outerjoin(owner, owner.id == Work.user_id)
    count_stmt = select(func.count()).select_from(Work)

    conditions = work_filters(audit_status, visibility, q, user_id)
    stmt = stmt.where(*conditions)
    count_stmt = count_stmt.where(*conditions)

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    rows = (
        await db.execute(
            stmt.order_by(Work.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()

    items: list[AdminWorkOut] = []
    for work, email in rows:
        data = AdminWorkOut.model_validate(work)
        data.user_email = email
        items.append(data)

    return AdminWorkListOut(items=items, meta=PageMeta(page=page, page_size=page_size, total=total))


@router.get("/works/export")
async def export_works(
    audit_status: str | None = None, visibility: str | None = None,
    q: str | None = None, user_id: int | None = None,
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """导出当前筛选结果，最多 10000 行。"""
    rows = (await db.execute(select(Work).where(*work_filters(audit_status, visibility, q, user_id))
                            .order_by(Work.id.desc()).limit(EXPORT_LIMIT + 1))).scalars().all()
    return csv_response("works.csv", ["ID", "作品", "用户ID", "审核状态", "可见性", "审核理由", "发布时间"],
                        ((w.id, w.title, w.user_id, w.audit_status, w.visibility, w.audit_reason, w.published_at) for w in rows))


@router.post("/works/bulk")
async def bulk_works(body: AdminWorkBulk, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """批量按稳定顺序锁行，缺失记录逐项报告，其余变更统一提交。"""
    validate_review(body)
    rows = (await db.execute(select(Work).where(Work.id.in_(body.ids)).order_by(Work.id).with_for_update())).scalars().all()
    by_id = {work.id: work for work in rows}
    results = []
    for work_id in body.ids:
        work = by_id.get(work_id)
        if work is None:
            results.append({"id": work_id, "success": False, "error": "作品不存在"})
            continue
        apply_review(db, work, body, _admin)
        results.append({"id": work_id, "success": True})
    await db.commit()
    return {"results": results, "succeeded": len(rows), "failed": len(body.ids) - len(rows)}


@router.get("/works/{work_id}", response_model=AdminWorkOut)
async def get_work(work_id: int, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> AdminWorkOut:
    """精确详情不依赖列表分页和标题模糊查询。"""
    work = await db.get(Work, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="作品不存在")
    owner = await db.get(User, work.user_id)
    data = AdminWorkOut.model_validate(work)
    data.user_email = owner.email if owner else None
    return data


@router.patch("/works/{work_id}", response_model=AdminWorkOut)
async def patch_work(
    work_id: int,
    body: AdminWorkPatch,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminWorkOut:
    # Update visibility / audit_status
    validate_review(body)
    work = (await db.execute(select(Work).where(Work.id == work_id).with_for_update())).scalar_one_or_none()
    if not work:
        raise HTTPException(status_code=404, detail="作品不存在")

    apply_review(db, work, body, _admin)

    await db.commit()
    await db.refresh(work)

    owner = await db.get(User, work.user_id)
    data = AdminWorkOut.model_validate(work)
    data.user_email = owner.email if owner else None
    return data
