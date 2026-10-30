"""Readiness failures must be bounded, recoverable and safe to expose."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import readiness


@pytest.fixture(autouse=True)
def reset_readiness(monkeypatch):
    monkeypatch.setattr(readiness, "_cached", None)
    monkeypatch.setattr(readiness, "_checked_at", 0.0)
    monkeypatch.setattr(readiness, "_lock", asyncio.Lock())
    monkeypatch.setattr(readiness, "_database_probe", AsyncMock())
    monkeypatch.setattr(readiness, "_redis_probe", AsyncMock())
    monkeypatch.setattr(readiness, "runtime_summary", lambda: {"enabled": True, "healthy": True})


@pytest.mark.asyncio
async def test_ready_requires_all_dependencies_and_coalesces_concurrent_polls():
    snapshots = await asyncio.gather(*(readiness.readiness_snapshot() for _ in range(10)))
    assert all(result["ok"] for result in snapshots)
    assert set(snapshots[0]["checks"]) == {"database", "redis", "task_runtime"}
    readiness._database_probe.assert_awaited_once()
    readiness._redis_probe.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ["_database_probe", "_redis_probe"])
async def test_dependency_failure_is_redacted_and_recovers(monkeypatch, caplog, component):
    probe = AsyncMock(side_effect=ConnectionError("redis://user:secret@internal:6379"))
    monkeypatch.setattr(readiness, component, probe)
    failed = await readiness.readiness_snapshot()
    assert failed["ok"] is False
    assert "secret" not in str(failed) + caplog.text
    assert "internal" not in str(failed) + caplog.text
    monkeypatch.setattr(readiness, "_checked_at", 0.0)
    probe.side_effect = None
    assert (await readiness.readiness_snapshot())["ok"] is True
    assert probe.await_count == 2


@pytest.mark.asyncio
async def test_timeout_cancels_probe_and_fails_closed(monkeypatch):
    released = asyncio.Event()

    async def blocked():
        try:
            await asyncio.Event().wait()
        finally:
            released.set()

    monkeypatch.setattr(readiness, "_database_probe", blocked)
    monkeypatch.setattr(readiness, "PROBE_TIMEOUT_SEC", 0.01)
    result = await asyncio.wait_for(readiness.readiness_snapshot(), timeout=0.5)
    assert result["ok"] is False
    assert result["checks"]["database"]["error"] == "TimeoutError"
    assert released.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "summary,expected,status",
    [
        ({"enabled": True, "healthy": False}, False, "unhealthy"),
        ({"enabled": False, "healthy": True}, True, "disabled"),
    ],
)
async def test_runtime_health_and_explicit_api_only_mode(monkeypatch, summary, expected, status):
    monkeypatch.setattr(readiness, "runtime_summary", lambda: summary)
    result = await readiness.readiness_snapshot()
    assert result["ok"] is expected
    assert result["checks"]["task_runtime"]["status"] == status


@pytest.mark.asyncio
async def test_redis_probe_closes_client_after_failed_ping(monkeypatch):
    # The fixture replaces the real probe; recover it from the module source
    # through its saved implementation below.
    client = SimpleNamespace(ping=AsyncMock(side_effect=ConnectionError("secret")), aclose=AsyncMock())
    monkeypatch.setattr(readiness.Redis, "from_url", lambda *args, **kwargs: client)
    with pytest.raises(ConnectionError):
        await _redis_probe_impl()
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("ok,status_code", [(True, 200), (False, 503)])
async def test_public_endpoint_is_minimal_and_liveness_stays_available(monkeypatch, ok, status_code):
    pytest.importorskip("PIL")
    from app import main

    monkeypatch.setattr(main, "readiness_snapshot", AsyncMock(return_value={
        "ok": ok, "status": "ready" if ok else "not_ready", "checks": {"database": {"error": "private"}},
    }))
    response = await main.ready()
    assert response.status_code == status_code
    assert b"private" not in response.body and b"database" not in response.body
    assert await main.health() == {"ok": True, "status": "ok"}


_redis_probe_impl = readiness._redis_probe
