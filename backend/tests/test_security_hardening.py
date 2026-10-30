# -*- coding: utf-8 -*-
"""A3 安全加固回归：支付回调幂等、IDOR、令牌解析、签名常量时间比较。"""
from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import billing as billing_api
from app.api import auth as auth_api
from app.api import projects as projects_api
from app.api import tools as tools_api
from app.api.drama import generation as drama_generation_api
from app.api.v1 import generation as v1_generation
from app.deps import _user_from_bearer
from app.models import Order, User, WalletLedger
from app.services import epay
from app.services import storage
from app.services import ffmpeg_compose
from app.services import media_access
from app.services.tasks import service as task_service
from app.services.billing import settlement
from app.services.tasks import executor
from app.schemas_api import V1SeedanceTaskRequest

from tests.conftest import make_task, make_user


class _FakeNotifyRequest:
    """模拟易支付回调的 POST 表单请求。"""

    def __init__(self, params: dict[str, str]) -> None:
        self.method = "POST"
        self._params = params
        self.query_params: dict[str, str] = {}

    async def form(self) -> dict[str, str]:
        return self._params


async def _make_pending_order(db: AsyncSession, user: User) -> Order:
    """构造一笔 1 元待支付订单。"""
    order = Order(
        out_trade_no=f"TEST{uuid.uuid4().hex[:16]}",
        user_id=user.id,
        sku_id="test_100",
        amount_fen=100,
        credit_fen=100,
        pay_type="alipay",
        status="pending",
    )
    db.add(order)
    await db.flush()
    return order


async def test_epay_notify_duplicate_callback_credits_once(
    db_session: AsyncSession,
) -> None:
    """易支付重复回调只入账一次（行锁 + paid 幂等返回）。"""
    user = await make_user(db_session, balance_fen=0)
    order = await _make_pending_order(db_session, user)
    params = {
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": order.out_trade_no,
        "trade_no": "upstream-t-1",
        "money": "1.00",
        "sign": "x",
    }

    with patch.object(epay, "verify", return_value=True):
        resp1 = await billing_api.epay_notify(_FakeNotifyRequest(params), db=db_session)
        resp2 = await billing_api.epay_notify(_FakeNotifyRequest(params), db=db_session)

    assert resp1.body == b"success"
    assert resp2.body == b"success"
    topup_count = (
        await db_session.execute(
            select(func.count())
            .select_from(WalletLedger)
            .where(
                WalletLedger.user_id == user.id,
                WalletLedger.kind == "topup",
                WalletLedger.ref_id == order.out_trade_no,
            )
        )
    ).scalar_one()
    assert topup_count == 1
    await db_session.refresh(user)
    assert user.balance_fen == 100


def test_epay_notify_source_locks_order_row() -> None:
    """源码守卫：回调必须用 SELECT ... FOR UPDATE 锁订单行，防并发双入账。"""
    assert "with_for_update" in inspect.getsource(billing_api.epay_notify)


def test_close_order_source_locks_order_row() -> None:
    """Manual cancellation must serialize with the payment callback."""
    assert "with_for_update" in inspect.getsource(billing_api.close_order)


def test_epay_notify_source_fails_closed_on_invalid_amount() -> None:
    """Malformed/missing provider amounts must not fall back to order amount."""
    source = inspect.getsource(billing_api.epay_notify)
    assert "amount is missing or invalid" in source
    assert "except (TypeError, ValueError, OverflowError)" in source


def test_v1_reference_urls_are_validated_before_upstream_fetch() -> None:
    """Public generation endpoints must not forward arbitrary internal URLs."""
    source = inspect.getsource(v1_generation.generate_image)
    source += inspect.getsource(v1_generation.generate_video)
    assert "validate_remote_reference_url" in source
    assert "status_code=422" in source
    assert "validate_remote_reference_url" in inspect.getsource(storage)


def test_avatar_upload_reads_in_bounded_chunks() -> None:
    """Avatar uploads must reject oversize files while streaming reads."""
    source = inspect.getsource(auth_api.upload_avatar)
    assert "while True" in source
    assert "1024 * 1024" in source
    assert "头像不能超过 5MB" in source


def test_project_cover_upload_reads_in_bounded_chunks() -> None:
    from app.services.avatar_upload import receive_image_upload
    source = inspect.getsource(projects_api.upload_project_cover)
    assert "receive_image_upload" in source
    assert "8 * 1024 * 1024" in source
    shared_source = inspect.getsource(receive_image_upload)
    assert "while True" in shared_source
    assert "64 * 1024" in shared_source
    assert "total > max_bytes" in shared_source


def test_seedance_content_is_bounded_and_media_urls_are_checked() -> None:
    """Multimodal forwarding must cap payloads and validate every media URL."""
    with pytest.raises(ValueError):
        V1SeedanceTaskRequest(content=[{"type": "text", "text": "x" * 8001}])
    source = inspect.getsource(v1_generation.forward_seedance)
    assert "validate_remote_reference_url" in source
    assert "max_length=20" in inspect.getsource(V1SeedanceTaskRequest)
    normalized = V1SeedanceTaskRequest(
        content=[{"type": "image_url", "image_url": "https://example.com/a.png"}]
    )
    assert normalized.content[0]["image_url"] == {"url": "https://example.com/a.png"}


def test_ffmpeg_execution_has_a_hard_timeout() -> None:
    """Media composition must terminate a child that exceeds its budget."""
    source = inspect.getsource(ffmpeg_compose._run)
    assert "TimeoutExpired" in source
    assert "timeout=" in source


def test_v1_upstream_errors_are_not_returned_to_clients() -> None:
    source = inspect.getsource(v1_generation)
    assert 'detail="上游生图服务暂时不可用"' in source
    assert 'detail="上游生视频服务暂时不可用"' in source
    assert "str(exc)[:400]" not in source


def test_media_ownership_fails_closed_for_colliding_project_ids() -> None:
    source = inspect.getsource(media_access.user_owns_media)
    assert "len(owners) == 1" in source
    assert "unambiguous" in source


def test_client_ip_ignores_forwarded_headers_without_trusted_proxy() -> None:
    request = SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.10"),
        headers={"x-forwarded-for": "10.0.0.9", "x-real-ip": "10.0.0.9"},
    )
    settings = SimpleNamespace(trusted_proxy_ips="")
    with patch.object(billing_api, "get_settings", return_value=settings):
        assert billing_api._client_ip(request) == "198.51.100.10"

    settings.trusted_proxy_ips = "198.51.100.0/24"
    with patch.object(billing_api, "get_settings", return_value=settings):
        assert billing_api._client_ip(request) == "10.0.0.9"


def test_registration_normalizes_email_and_handles_unique_race() -> None:
    source = inspect.getsource(auth_api.register)
    assert "email_norm = str(body.email).strip().lower()" in source
    assert "except IntegrityError" in source
    assert 'detail="邮箱已注册"' in source
    update_source = inspect.getsource(auth_api.update_me)
    assert "except IntegrityError" in update_source
    assert 'detail="该邮箱已被使用"' in update_source


def test_drama_voice_generation_uses_billed_task_scope() -> None:
    source = inspect.getsource(drama_generation_api.generate_voice)
    assert 'task_type="voice_synthesis"' in source
    assert "run_billed_ephemeral" in source
    assert "commit=False" in source
    assert 'detail="音色合成服务暂时不可用"' in source


def test_task_creation_serializes_dedupe_retries() -> None:
    source = inspect.getsource(task_service.create_task)
    assert "pg_advisory_xact_lock" in source
    assert "body.client_request_id" in source
    assert "TaskRun.domain == body.domain" in source
    assert "TaskRun.dedupe_key == dedupe_key" in source
    assert "return existing" in source


def test_cancelled_tasks_are_rechecked_under_billing_lock() -> None:
    settlement_source = inspect.getsource(settlement.freeze_for_task)
    executor_source = inspect.getsource(executor.execute_task_run)
    cancelled_source = inspect.getsource(executor._mark_cancelled)
    assert "TaskCancelledBeforeStart" in settlement_source
    assert "task.cancel_requested" in settlement_source
    assert "except TaskCancelledBeforeStart" in executor_source
    assert "await _mark_cancelled(db, task, step=step)" in executor_source
    assert "task.lease_token = None" in cancelled_source
    assert 'event_type="task.cancelled"' in cancelled_source
    assert "await settle_task(db, task.id)" in cancelled_source


def test_epay_verify_constant_time_signature() -> None:
    """正确签名通过、篡改签名拒绝；比较走 hmac.compare_digest。"""
    key = "unit-key"
    params = {"a": "1", "b": "2"}
    sign = epay._sign_pairs(params, key)
    fake_settings = SimpleNamespace(epay_key=key)
    forged = sign[:-1] + ("0" if sign[-1] != "0" else "1")
    with patch.object(epay, "get_settings", return_value=fake_settings):
        assert epay.verify({**params, "sign": sign}) is True
        assert epay.verify({**params, "sign": forged}) is False
        assert epay.verify({**params, "sign": ""}) is False
    assert "compare_digest" in inspect.getsource(epay.verify)


async def test_v1_get_task_rejects_other_user(db_session: AsyncSession) -> None:
    """B 用户不得凭上游 task_id 查询 A 用户的视频任务（IDOR）。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await make_task(
        db_session,
        user_a,
        domain="api",
        task_type="v1_seedance",
        status="awaiting_poll",
        billing_status="frozen",
        provider_task_id="prov-idor-1",
    )

    poll = AsyncMock(return_value={"status": "running"})
    with patch.object(v1_generation, "poll_video_task", poll):
        with pytest.raises(HTTPException) as exc:
            await v1_generation.get_task("prov-idor-1", db=db_session, user=user_b)
    assert exc.value.status_code == 404
    poll.assert_not_called()


async def test_v1_get_task_allows_owner(db_session: AsyncSession) -> None:
    """归属人查询自己的任务正常透传上游状态。"""
    user = await make_user(db_session)
    await make_task(
        db_session,
        user,
        domain="api",
        task_type="v1_seedance",
        status="awaiting_poll",
        billing_status="frozen",
        provider_task_id="prov-owner-1",
    )

    poll = AsyncMock(return_value={"status": "running"})
    with patch.object(v1_generation, "poll_video_task", poll):
        out = await v1_generation.get_task("prov-owner-1", db=db_session, user=user)
    assert out.status == "running"
    poll.assert_awaited_once()


async def test_tools_get_task_404_without_local_row(db_session: AsyncSession) -> None:
    """/api/tools/tasks 本地无归属记录时不得代理查询上游。"""
    user = await make_user(db_session)
    poll = AsyncMock()
    with patch.object(tools_api, "poll_video_task", poll):
        with pytest.raises(HTTPException) as exc:
            await tools_api.get_tool_task("stranger-task", db=db_session, user=user)
    assert exc.value.status_code == 404
    poll.assert_not_called()


async def test_bearer_rejects_non_numeric_jwt_sub(db_session: AsyncSession) -> None:
    """JWT sub 非数字时返回匿名 None，不抛 ValueError。"""
    with patch("app.deps.decode_token", return_value="not-an-int"):
        assert await _user_from_bearer(db_session, "fake.jwt.token") is None
