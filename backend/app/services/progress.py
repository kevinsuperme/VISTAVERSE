"""Bounded progress pub/sub; Redis failures never block the event loop."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
_QUEUE_SIZE = 64
_LATEST_LIMIT = 1024
_LATEST_TTL = 3600
_queues: dict[int, list[asyncio.Queue]] = {}
_latest: OrderedDict[int, tuple[float, dict[str, Any]]] = OrderedDict()
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        from redis.asyncio import Redis
        _redis = Redis.from_url(
            get_settings().redis_url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
            max_connections=128, health_check_interval=15,
        )
    return _redis


def channel(project_id: int) -> str:
    return f"framecut:progress:{project_id}"


def _offer(q: asyncio.Queue, payload: dict[str, Any]) -> None:
    # Progress is a snapshot: keep the newest state when a consumer is slow.
    if q.full():
        q.get_nowait()
    q.put_nowait(payload)


def _prune_latest() -> None:
    cutoff = time.monotonic() - _LATEST_TTL
    while _latest and (len(_latest) > _LATEST_LIMIT or next(iter(_latest.values()))[0] < cutoff):
        _latest.popitem(last=False)


async def publish_progress(project_id: int, payload: dict[str, Any]) -> None:
    _latest[project_id] = (time.monotonic(), payload)
    _latest.move_to_end(project_id)
    _prune_latest()
    for q in tuple(_queues.get(project_id, ())):
        _offer(q, payload)
    try:
        r = _get_redis()
        raw = json.dumps(payload, ensure_ascii=False)
        async with r.pipeline(transaction=True) as pipe:
            pipe.setex(f"framecut:latest:{project_id}", _LATEST_TTL, raw)
            pipe.publish(channel(project_id), raw)
            await pipe.execute()
    except Exception as exc:  # Redis client reconnects on the next operation.
        logger.warning("Progress Redis publish unavailable (%s)", type(exc).__name__)


def subscribe(project_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_SIZE)
    _queues.setdefault(project_id, []).append(q)
    _prune_latest()
    if project_id in _latest:
        _offer(q, _latest[project_id][1])
    return q


def unsubscribe(project_id: int, q: asyncio.Queue) -> None:
    subscribers = _queues.get(project_id)
    if subscribers and q in subscribers:
        subscribers.remove(q)
        if not subscribers:
            _queues.pop(project_id, None)


async def redis_bridge(project_id: int, q: asyncio.Queue) -> None:
    """Subscribe before loading the snapshot; reconnect after transient failures."""
    delay = 1
    while True:
        try:
            r = _get_redis()
            async with r.pubsub() as pubsub:
                await pubsub.subscribe(channel(project_id))
                raw = await r.get(f"framecut:latest:{project_id}")
                if raw:
                    _offer(q, json.loads(raw))
                delay = 1
                while True:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg and msg.get("type") == "message":
                        data = msg.get("data")
                        if isinstance(data, str):
                            _offer(q, json.loads(data))
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Progress Redis bridge reconnecting (%s)", type(exc).__name__)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def close_progress() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
