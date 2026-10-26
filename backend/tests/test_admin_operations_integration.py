"""后台关键操作真实 PostgreSQL 回归；每例事务回滚，不接触业务库。"""

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.admin.finance import export_finance
from app.api.admin.notifications import list_notifications, mark_notifications_read
from app.api.admin.orders import get_order
from app.api.admin.templates import bulk_templates, export_templates, list_templates, templates_meta
from app.api.admin.users import get_user, patch_user
from app.api.admin.works import bulk_works, export_works, get_work, patch_work
from app.config import get_settings
from app.models import Order, Project, Template, User, WalletLedger, Work
from app.models_admin import AdminAuditLog, AdminBalanceRequest, AdminNotificationRead
from app.schemas import AdminUserPatch, AdminWorkPatch
from app.schemas_admin import AdminNotificationReadPatch, AdminTemplateBulk, AdminWorkBulk
from tests.conftest import _resolve_test_database_url, make_task, make_user


async def admin_user(db, role="admin"):
    """创建可通过公开响应邮箱验证的角色用户。"""
    user = await make_user(db)
    user.email = f"{uuid.uuid4().hex}@example.com"
    user.role = role
    await db.flush()
    return user


async def sample_work(db, user, *, title="待审核作品", audit_status="pending"):
    """建立作品所需的模板、项目外键，不伪造业务关联。"""
    template = Template(id=uuid.uuid4().hex, name="测试模板", style_prefix="test")
    db.add(template)
    await db.flush()
    project = Project(user_id=user.id, template_id=template.id, title=title, source_text="sample")
    db.add(project)
    await db.flush()
    work = Work(project_id=project.id, user_id=user.id, title=title, video_url="/test.mp4", audit_status=audit_status)
    db.add(work)
    await db.flush()
    return work


@pytest.mark.asyncio
async def test_precise_details_and_finance_field_permissions(db_session):
    """详情按主键；财务角色只可调账且记录真实前后值。"""
    admin = await admin_user(db_session, "admin_finance")
    user = await admin_user(db_session, "user")
    other = await admin_user(db_session, "user")
    other.nickname = f"包含ID {user.id}"
    order = Order(out_trade_no=uuid.uuid4().hex, user_id=user.id, sku_id="test", amount_fen=10, credit_fen=10, pay_type="test")
    db_session.add(order)
    await db_session.flush()
    assert (await get_user(user.id, admin, db_session)).id == user.id
    assert (await get_order(order.id, admin, db_session)).user_id == user.id
    before = user.balance_fen
    await patch_user(user.id, AdminUserPatch(balance_delta_fen=50, balance_note="测试调账"), admin, db_session)
    log = await db_session.scalar(select(AdminAuditLog).where(AdminAuditLog.target_id == str(user.id)))
    assert log.changes["balance_fen"] == {"before": before, "after": before + 50}
    with pytest.raises(HTTPException) as caught:
        await patch_user(user.id, AdminUserPatch(balance_delta_fen=50, role="admin"), admin, db_session)
    assert caught.value.status_code == 403
    assert user.balance_fen == before + 50 and user.role == "user"
    with pytest.raises(HTTPException) as too_large:
        await patch_user(user.id, AdminUserPatch(balance_delta_fen=2_147_483_647, balance_note="测试上限"), admin, db_session)
    assert too_large.value.status_code == 400 and user.balance_fen == before + 50


@pytest.mark.asyncio
async def test_review_reason_batch_partial_failure_and_audit(db_session):
    """驳回不丢理由；缺失记录逐项失败，已存在作品写审计。"""
    admin = await admin_user(db_session, "admin_reviewer")
    work = await sample_work(db_session, admin)
    missing_id = work.id + 1_000_000
    result = await bulk_works(AdminWorkBulk(ids=[work.id, missing_id], audit_status="rejected", audit_reason="不符合发布要求"), admin, db_session)
    assert (result["succeeded"], result["failed"]) == (1, 1)
    assert result["results"][1]["success"] is False
    detail = await get_work(work.id, admin, db_session)
    assert detail.audit_reason == "不符合发布要求" and detail.audited_by == admin.id
    assert detail.audited_at is not None and detail.audit_status == "rejected"
    log = await db_session.scalar(select(AdminAuditLog).where(AdminAuditLog.target_type == "work", AdminAuditLog.target_id == str(work.id)))
    assert log.changes["audit_status"] == {"before": "pending", "after": "rejected"}
    await patch_work(work.id, AdminWorkPatch(visibility="private"), admin, db_session)
    assert work.audit_reason == "不符合发布要求"


@pytest.mark.asyncio
async def test_template_premium_meta_batch_and_export_share_filters(db_session):
    """Premium 不再仅过滤当前页；分类计数来自全库，导出和列表一致。"""
    admin = await admin_user(db_session)
    prefix = uuid.uuid4().hex[:8]
    rows = [Template(id=f"{prefix}-{i}", name=f"{prefix}-{i}", style_prefix="x", is_premium=(i == 1), category=[prefix]) for i in range(3)]
    db_session.add_all(rows)
    await db_session.flush()
    listed = await list_templates(page=1, page_size=1, q=prefix, is_premium=True, _admin=admin, db=db_session)
    assert listed.meta.total == 1 and listed.items[0].id == rows[1].id
    meta = await templates_meta(admin, db_session)
    assert meta["category_counts"][prefix] == 3
    exported = await export_templates(q=prefix, is_premium=True, _admin=admin, db=db_session)
    csv = exported.body.decode("utf-8-sig")
    assert rows[1].id in csv and rows[0].id not in csv
    result = await bulk_templates(AdminTemplateBulk(ids=[rows[1].id, f"{prefix}-missing"], is_active=False), admin, db_session)
    assert result["succeeded"] == result["failed"] == 1
    assert rows[1].is_active is False


@pytest.mark.asyncio
async def test_notification_permissions_pagination_and_read_isolation(db_session, monkeypatch):
    """审核员看不到失败任务；已读幂等且不会影响其他管理员。"""
    monkeypatch.setattr("app.services.admin.notifications.runtime_summary", lambda: {"enabled": True, "healthy": True})
    admin = await admin_user(db_session)
    reviewer = await admin_user(db_session, "admin_reviewer")
    finance = await admin_user(db_session, "admin_finance")
    work = await sample_work(db_session, admin)
    await make_task(db_session, admin, status="failed")
    page = await list_notifications(page=1, page_size=1, _admin=admin, db=db_session)
    assert len(page["items"]) == 1 and page["meta"]["total"] >= 2
    reviews = await list_notifications(page=1, page_size=100, _admin=reviewer, db=db_session)
    assert all(row["kind"] == "work_pending" for row in reviews["items"])
    target = next(row for row in reviews["items"] if row["href"] == f"/works?work={work.id}")
    body = AdminNotificationReadPatch(ids=[target["id"]])
    await mark_notifications_read(body, reviewer, db_session)
    await mark_notifications_read(body, reviewer, db_session)
    assert await db_session.scalar(select(func.count()).select_from(AdminNotificationRead).where(AdminNotificationRead.user_id == reviewer.id)) == 1
    unread = await list_notifications(page=1, page_size=100, unread_only=True, _admin=reviewer, db=db_session)
    assert target["id"] not in {row["id"] for row in unread["items"]}
    other = await list_notifications(page=1, page_size=100, _admin=admin, db=db_session)
    assert next(row for row in other["items"] if row["id"] == target["id"])["read"] is False
    assert (await mark_notifications_read(body, finance, db_session))["marked"] == 0
    assert (await list_notifications(page=1, page_size=20, _admin=finance, db=db_session))["items"] == []


@pytest.mark.asyncio
async def test_exports_formula_and_finance_window(db_session):
    """导出匹配筛选、阻断作品标题公式，财务复用页面日期窗口。"""
    admin = await admin_user(db_session)
    tag = uuid.uuid4().hex[:8]
    await sample_work(db_session, admin, title=f"=SUM(1)+{tag}")
    await sample_work(db_session, admin, title=f"{tag}-excluded", audit_status="passed")
    response = await export_works(q=tag, audit_status="pending", _admin=admin, db=db_session)
    text = response.body.decode("utf-8-sig")
    assert "'=SUM(1)" in text and "excluded" not in text
    finance = await export_finance(days=7, _admin=admin, db=db_session)
    assert len(finance.body.decode("utf-8-sig").splitlines()) == 8


@pytest.mark.asyncio
async def test_balance_replay_conflicts_and_optimistic_confirmation(db_session):
    """同编号相同内容不重复扣费，内容冲突和旧余额快照均整单拒绝。"""
    admin = await admin_user(db_session, "admin_finance")
    user = await admin_user(db_session, "user")
    before = user.balance_fen
    request_id = uuid.uuid4()
    body = AdminUserPatch(balance_delta_fen=-100, balance_note="调账回归", balance_request_id=request_id, expected_balance_fen=before)
    first = await patch_user(user.id, body, admin, db_session)
    replay = await patch_user(user.id, body, admin, db_session)
    assert first.balance_fen == replay.balance_fen == before - 100
    assert await db_session.scalar(select(func.count()).select_from(WalletLedger).where(WalletLedger.user_id == user.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(AdminBalanceRequest).where(AdminBalanceRequest.user_id == user.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.actor_id == admin.id)) == 1
    for changed in (
        body.model_copy(update={"balance_delta_fen": -200}),
        body.model_copy(update={"balance_note": "不同原因"}),
        body.model_copy(update={"balance_request_id": uuid.uuid4()}),
    ):
        with pytest.raises(HTTPException) as caught:
            await patch_user(user.id, changed, admin, db_session)
        assert caught.value.status_code == 409
    assert user.balance_fen == before - 100
    with pytest.raises(HTTPException) as no_note:
        await patch_user(user.id, AdminUserPatch(balance_delta_fen=1), admin, db_session)
    assert no_note.value.status_code == 400


@pytest.mark.asyncio
async def test_balance_concurrent_replay_and_stale_confirmation(db_session):
    """独立真实连接验证行锁：同请求只记一次，新请求旧快照只允许一个成功。"""
    # db_session 初始化隔离库表；本用例的独立连接必须看见已提交数据，结束精确清理自身 UUID 用户。
    test_url, test_name = _resolve_test_database_url(get_settings().database_url)
    assert "test" in test_name
    engine = create_async_engine(test_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    actor_id = user_id = None
    try:
        async with sessions() as setup:
            actor = await admin_user(setup, "admin_finance")
            target = await admin_user(setup, "user")
            actor_id, user_id = actor.id, target.id
            before = target.balance_fen
            await setup.commit()

        async def adjust(body):
            """每个请求独立事务，按真实 Web 请求生命周期提交或回滚。"""
            async with sessions() as db:
                actor = await db.get(User, actor_id)
                try:
                    result = await patch_user(user_id, body, actor, db)
                    return result.balance_fen
                except HTTPException as exc:
                    return exc.status_code

        first = AdminUserPatch(balance_delta_fen=10, balance_note="并发重放", balance_request_id=uuid.uuid4(), expected_balance_fen=before)
        assert await asyncio.gather(adjust(first), adjust(first)) == [before + 10, before + 10]
        next_a = AdminUserPatch(balance_delta_fen=10, balance_note="再次调账", balance_request_id=uuid.uuid4(), expected_balance_fen=before + 10)
        next_b = next_a.model_copy(update={"balance_request_id": uuid.uuid4()})
        outcomes = await asyncio.gather(adjust(next_a), adjust(next_b))
        assert sorted(outcomes) == [409, before + 20]
        async with sessions() as verify:
            assert (await verify.get(User, user_id)).balance_fen == before + 20
            assert await verify.scalar(select(func.count()).select_from(WalletLedger).where(WalletLedger.user_id == user_id)) == 2
            assert await verify.scalar(select(func.count()).select_from(AdminBalanceRequest).where(AdminBalanceRequest.user_id == user_id)) == 2
    finally:
        if actor_id is not None and user_id is not None:
            async with sessions() as cleanup:
                await cleanup.execute(delete(AdminAuditLog).where(AdminAuditLog.actor_id == actor_id))
                await cleanup.execute(delete(AdminBalanceRequest).where(AdminBalanceRequest.actor_id == actor_id))
                await cleanup.execute(delete(WalletLedger).where(WalletLedger.user_id == user_id))
                await cleanup.execute(delete(User).where(User.id.in_([actor_id, user_id])))
                await cleanup.commit()
        await engine.dispose()
