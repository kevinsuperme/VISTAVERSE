# Admin template CRUD
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.models import Project, Template, User
from app.schemas import (
    AdminTemplateCreate,
    AdminTemplateListOut,
    AdminTemplateOut,
    AdminTemplatePatch,
    PageMeta,
)
from app.schemas_admin import AdminTemplateBulk
from app.services.admin.audit import record_audit
from app.services.admin.exports import EXPORT_LIMIT, csv_response, template_filters

router = APIRouter()


@router.get("/templates/meta")
async def templates_meta(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 汇总全库分类标签（用于管理端筛选）
    result = await db.execute(select(Template.category))
    counts: dict[str, int] = {}
    for (cat_list,) in result.all():
        if not isinstance(cat_list, list):
            continue
        for item in set(item.strip() for item in cat_list if isinstance(item, str)):
            if isinstance(item, str) and item.strip():
                counts[item] = counts.get(item, 0) + 1
    total = int((await db.scalar(select(func.count()).select_from(Template))) or 0)
    return {"categories": sorted(counts), "category_counts": counts, "total": total}


@router.get("/templates", response_model=AdminTemplateListOut)
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    q: str | None = None,
    is_active: bool | None = None,
    category: str | None = None,
    is_premium: bool | None = None,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminTemplateListOut:
    # All templates including inactive
    stmt = select(Template)
    count_stmt = select(func.count()).select_from(Template)
    conditions = template_filters(q, is_active, category, is_premium)
    stmt = stmt.where(*conditions)
    count_stmt = count_stmt.where(*conditions)

    total = int((await db.execute(count_stmt)).scalar_one() or 0)
    result = await db.execute(
        stmt.order_by(Template.sort_order, Template.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [AdminTemplateOut.model_validate(t) for t in result.scalars().all()]
    return AdminTemplateListOut(
        items=items, meta=PageMeta(page=page, page_size=page_size, total=total)
    )


@router.get("/templates/export")
async def export_templates(
    q: str | None = None, is_active: bool | None = None, category: str | None = None,
    is_premium: bool | None = None, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """导出筛选后的模板概览，不包含模型配置内容。"""
    rows = (await db.execute(select(Template).where(*template_filters(q, is_active, category, is_premium))
                            .order_by(Template.sort_order, Template.id).limit(EXPORT_LIMIT + 1))).scalars().all()
    return csv_response("templates.csv", ["ID", "名称", "分类", "已上架", "Premium", "排序"],
                        ((t.id, t.name, ",".join(t.category or []), t.is_active, t.is_premium, t.sort_order) for t in rows))


@router.post("/templates/bulk")
async def bulk_templates(body: AdminTemplateBulk, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """批量上下架并返回每项结果，全部成功项与审计同事务提交。"""
    rows = (await db.execute(select(Template).where(Template.id.in_(body.ids)).order_by(Template.id).with_for_update())).scalars().all()
    by_id = {template.id: template for template in rows}
    results = []
    for template_id in body.ids:
        template = by_id.get(template_id)
        if template is None:
            results.append({"id": template_id, "success": False, "error": "模板不存在"})
            continue
        record_audit(db, _admin, "template.update", "template", template_id,
                     {"is_active": {"before": template.is_active, "after": body.is_active}})
        template.is_active = body.is_active
        results.append({"id": template_id, "success": True})
    await db.commit()
    return {"results": results, "succeeded": len(rows), "failed": len(body.ids) - len(rows)}


@router.get("/templates/{template_id}", response_model=AdminTemplateOut)
async def get_template(
    template_id: str,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminTemplateOut:
    tpl = await db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return AdminTemplateOut.model_validate(tpl)


@router.post("/templates", response_model=AdminTemplateOut)
async def create_template(
    body: AdminTemplateCreate,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminTemplateOut:
    # Create a new template row
    existing = await db.get(Template, body.id)
    if existing:
        raise HTTPException(status_code=400, detail="模板 ID 已存在")
    tpl = Template(**body.model_dump())
    db.add(tpl)
    record_audit(db, _admin, "template.create", "template", body.id, {"fields": sorted(body.model_dump())})
    await db.commit()
    await db.refresh(tpl)
    return AdminTemplateOut.model_validate(tpl)


@router.patch("/templates/{template_id}", response_model=AdminTemplateOut)
async def patch_template(
    template_id: str,
    body: AdminTemplatePatch,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminTemplateOut:
    # Partial update including is_active / is_premium
    tpl = (await db.execute(select(Template).where(Template.id == template_id).with_for_update())).scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    data = body.model_dump(exclude_unset=True)
    if any(value is None for value in data.values()):
        raise HTTPException(status_code=400, detail="模板字段不能为 null")
    # 配置 JSON 可能包含供应商参数；只记录字段名称和公开状态。
    changes = {key: {"before": getattr(tpl, key), "after": data[key]}
               for key in ("is_active", "is_premium", "sort_order", "name") if key in data}
    changes["fields"] = sorted(data)
    for key, value in data.items():
        setattr(tpl, key, value)
    record_audit(db, _admin, "template.update", "template", template_id, changes)
    await db.commit()
    await db.refresh(tpl)
    return AdminTemplateOut.model_validate(tpl)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Refuse delete when projects still reference the template
    tpl = await db.get(Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    used = int(
        (
            await db.execute(
                select(func.count()).select_from(Project).where(Project.template_id == template_id)
            )
        ).scalar_one()
        or 0
    )
    if used > 0:
        raise HTTPException(status_code=400, detail=f"模板仍被 {used} 个项目引用，无法删除")
    await db.delete(tpl)
    record_audit(db, _admin, "template.delete", "template", template_id, {"name": tpl.name})
    await db.commit()
    return {"ok": True}
