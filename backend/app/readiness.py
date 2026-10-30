"""Bounded, read-only dependency probes, shared by readiness and admin diagnostics."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.services.tasks.runtime import runtime_summary

logger = logging.getLogger("app.readiness")
PROBE_TIMEOUT_SEC = 2.0
CACHE_TTL_SEC = 2.0
_lock = asyncio.Lock()
_cached: dict | None = None
_checked_at = 0.0


async def _database_probe() -> None:
    # A connection checkout and SELECT test the real pool and server, without writes.
    async with engine.connect() as conn:
        if await conn.scalar(text("SELECT 1")) != 1:
            raise RuntimeError("unexpected probe result")


async def _redis_probe() -> None:
    # Use an independent async client: a sync publisher must never block the API
    # event loop, nor may its cached failure state prevent reconnect probes.
    client = Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=PROBE_TIMEOUT_SEC,
        socket_timeout=PROBE_TIMEOUT_SEC,
        retry_on_timeout=False,
        max_connections=1,
    )
    try:
        if not await client.ping():
            raise RuntimeError("unexpected probe result")
    finally:
        await client.aclose()


async def _runtime_probe() -> dict:
    summary = runtime_summary()
    # An explicitly disabled runtime is valid for an API-only process. The
    # deployment must separately monitor the process that owns task execution.
    if summary.get("enabled") is False:
        return {"ok": True, "status": "disabled"}
    if not summary.get("healthy"):
        return {"ok": False, "status": "unhealthy"}
    return {"ok": True, "status": "ok"}


async def _check(name: str, probe: Callable[[], Awaitable]) -> tuple[str, dict]:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(probe(), timeout=PROBE_TIMEOUT_SEC)
        details = result if isinstance(result, dict) else {"ok": True, "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        # Driver messages may contain DSNs, passwords, internal hosts or SQL.
        # Only fixed component names and exception class names enter diagnostics.
        error = type(exc).__name__
        logger.warning("readiness dependency=%s error=%s", name, error)
        details = {"ok": False, "status": "error", "error": error}
    return name, {**details, "elapsed_ms": round((time.monotonic() - started) * 1000)}


async def readiness_snapshot() -> dict:
    """Single-flight probes, cached briefly so public polling cannot fill pools."""
    global _cached, _checked_at
    if _cached is not None and time.monotonic() - _checked_at < CACHE_TTL_SEC:
        return _cached
    async with _lock:
        if _cached is not None and time.monotonic() - _checked_at < CACHE_TTL_SEC:
            return _cached
        results = await asyncio.gather(
            _check("database", _database_probe),
            _check("redis", _redis_probe),
            _check("task_runtime", _runtime_probe),
        )
        checks = dict(results)
        ok = all(item["ok"] for item in checks.values())
        _cached = {"ok": ok, "status": "ready" if ok else "not_ready", "checks": checks}
        _checked_at = time.monotonic()
        return _cached
