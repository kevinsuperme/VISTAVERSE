"""Async OSS upload queue: enqueue after local save, then backfill DB URLs."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import queue
import time
import threading
import copy
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import String, cast, or_, select, update

from app.config import get_settings
from app.services import oss as oss_svc
from app.services import storage

logger = logging.getLogger(__name__)

# The API has a bounded worker pool. Pending URLs remain in Redis until the
# upload AND database commit succeed. Redis AOF is required by Compose.
_PENDING_KEY = "ai_movie:oss:pending:v2"
_FAILED_KEY = "ai_movie:oss:failed:v2"
_ATTEMPTS_KEY = "ai_movie:oss:attempts:v2"
_MAX_PENDING = 1000
_CONCURRENCY = 2
_INGRESS: queue.Queue[str] = queue.Queue(maxsize=_MAX_PENDING)
_INGRESS_SEEN: set[str] = set()
_INGRESS_LOCK = threading.Lock()
_scan_cursors: dict[str, Any] = {}
_tasks: list[asyncio.Task] = []
_active: set[str] = set()
_client: Redis | None = None
_stopping = False
_SHUTDOWN_TIMEOUT = 5.0
_upload_executor = ThreadPoolExecutor(max_workers=_CONCURRENCY, thread_name_prefix="oss-upload")
_upload_futures: set[Future] = set()
_ASSET_PARAM_URL_KEYS = ("voiceAudio", "cover", "url", "image", "video")


def _redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            get_settings().redis_url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2, max_connections=8,
            health_check_interval=15,
        )
    return _client


def _digest(local_url: str) -> str:
    return hashlib.sha1(local_url.encode("utf-8")).hexdigest()[:24]


def enqueue_oss_upload(local_url: str) -> bool:
    """Nonblocking admission; DB reconciliation recovers rejected/lost ingress.

    The synchronous interface is also called from upload threads. Never do
    network I/O here. True means accepted into bounded ingress, not persisted;
    the persister makes it durable before any worker can upload it.
    """
    url = (local_url or "").strip()
    if not url or not storage.is_local_static_url(url) or not oss_svc.oss_enabled():
        return False
    with _INGRESS_LOCK:
        if not _tasks or _stopping:
            return False
        if url in _INGRESS_SEEN:
            return False
        try:
            _INGRESS.put_nowait(url)
            _INGRESS_SEEN.add(url)
            return True
        except queue.Full:
            logger.error("OSS ingress full; database reconciliation will recover local references")
            return False


async def _persist_pending(url: str) -> bool:
    # Atomic limit + NX: duplicate enqueue must not reset a failed job's backoff.
    result = await _redis().eval(
        "local failed = redis.call('ZSCORE', KEYS[2], ARGV[1]); "
        "if failed and tonumber(failed) > tonumber(ARGV[2]) then return 1 end "
        "redis.call('ZREM', KEYS[2], ARGV[1]); "
        "if redis.call('ZSCORE', KEYS[1], ARGV[1]) then return 1 end "
        "if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then return 0 end "
        "redis.call('ZADD', KEYS[1], ARGV[2], ARGV[1]); return 1",
        2, _PENDING_KEY, _FAILED_KEY, url, time.time(), _MAX_PENDING,
    )
    return bool(result)


async def _persist_ingress() -> None:
    while True:
        try:
            url = _INGRESS.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.2)
            continue
        try:
            while True:
                try:
                    if await _persist_pending(url):
                        break
                    logger.warning("OSS durable queue full; waiting for capacity")
                except Exception as exc:
                    logger.warning("OSS queue persistence retry (%s)", type(exc).__name__)
                await asyncio.sleep(5)
        finally:
            # Cancellation discards the volatile item; committed DB references
            # are recovered by the rotating scan. Keep Queue accounting valid.
            with _INGRESS_LOCK:
                _INGRESS_SEEN.discard(url)
                _INGRESS.task_done()


async def _upload_local_url_background(local_url: str) -> None:
    """Only ACK after the DB transaction commits; cancellation keeps pending."""
    # A dedicated executor retains its two slots until the actual blocking SDK
    # calls finish. Cancelling an asyncio waiter cannot kill a Python thread.
    future = _upload_executor.submit(upload_local_url_sync, local_url)
    with _INGRESS_LOCK:
        _upload_futures.add(future)
    def finished(done: Future) -> None:
        with _INGRESS_LOCK:
            _upload_futures.discard(done)
    future.add_done_callback(finished)
    upload = asyncio.wrap_future(future)
    # Retrieve detached wrapper errors after cancellation to avoid unobserved
    # exception warnings. Durable pending is intentionally not ACKed.
    upload.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    oss_url = await asyncio.shield(upload)
    if not oss_url:
        raise RuntimeError("local media missing or upload unavailable")
    await backfill_media_url(local_url, oss_url)
    await clear_enqueue_marker(local_url)


async def clear_enqueue_marker(local_url: str) -> None:
    async with _redis().pipeline(transaction=True) as pipe:
        pipe.zrem(_PENDING_KEY, local_url)
        pipe.hdel(_ATTEMPTS_KEY, local_url)
        await pipe.execute()


async def _upload_worker() -> None:
    while True:
        url = None
        try:
            candidates = await _redis().zrangebyscore(
                _PENDING_KEY, "-inf", time.time(), start=0, num=_CONCURRENCY + 1,
            )
            # No await between checking and reserving: one event loop owns this.
            url = next((item for item in candidates if item not in _active), None)
            if url is None:
                await asyncio.sleep(1)
                continue
            _active.add(url)
            await _upload_local_url_background(url)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("OSS upload/persistence retry (%s)", type(exc).__name__)
            if url is not None:
                try:
                    attempts = await _redis().hincrby(_ATTEMPTS_KEY, url, 1)
                    if attempts >= 10:
                        # Quarantine repeatedly failing URLs for an hour to free
                        # capacity. Bounded failed index; DB is the retry source.
                        async with _redis().pipeline(transaction=True) as pipe:
                            pipe.zadd(_FAILED_KEY, {url: time.time() + 3600})
                            pipe.zremrangebyrank(_FAILED_KEY, 0, -(_MAX_PENDING + 1))
                            pipe.zrem(_PENDING_KEY, url)
                            pipe.hdel(_ATTEMPTS_KEY, url)
                            await pipe.execute()
                    else:
                        await _redis().zadd(_PENDING_KEY, {url: time.time() + min(2 ** attempts, 300)})
                    if attempts % 5 == 0:
                        logger.error("OSS upload failed %s times; pending retained id=%s", attempts, _digest(url))
                except Exception as retry_exc:
                    logger.warning("OSS retry state unavailable (%s)", type(retry_exc).__name__)
            await asyncio.sleep(2)
        finally:
            if url is not None:
                _active.discard(url)


async def _reconcile_pending() -> None:
    while True:
        try:
            # Committed local references recover ingress lost in a crash or an
            # outage. Existing durable jobs retain their retry schedule.
            urls = await collect_pending_local_media_urls(limit=_MAX_PENDING)
            for url in urls:
                if not await _persist_pending(url):
                    logger.warning("OSS reconciliation paused: durable queue full")
                    break
        except Exception as exc:
            logger.warning("OSS database reconciliation retry (%s)", type(exc).__name__)
        await asyncio.sleep(300)


async def start_oss_workers() -> None:
    global _stopping
    if (_tasks or not oss_svc.oss_enabled() or not get_settings().oss_upload_async
            or not get_settings().task_runtime_enabled):
        return
    with _INGRESS_LOCK:
        if _upload_futures:
            raise RuntimeError("OSS previous uploads still running; process restart required")
    _stopping = False
    _tasks.extend([
        asyncio.create_task(_persist_ingress(), name="oss-persister"),
        asyncio.create_task(_reconcile_pending(), name="oss-reconcile"),
        *(asyncio.create_task(_upload_worker(), name=f"oss-upload-{i}") for i in range(_CONCURRENCY)),
    ])


async def stop_oss_workers() -> None:
    global _client, _stopping
    _stopping = True
    # Let the persister commit admitted URLs before stopping workers. On Redis
    # outage the DB scan remains the recovery source; files are never deleted.
    deadline = time.monotonic() + _SHUTDOWN_TIMEOUT
    while _INGRESS.unfinished_tasks and time.monotonic() < deadline - 1:
        await asyncio.sleep(0.1)
    if _INGRESS.unfinished_tasks:
        logger.warning("OSS ingress not drained; database reconciliation required")
    for task in _tasks:
        task.cancel()
    if _tasks:
        done, pending = await asyncio.wait(_tasks, timeout=max(0, deadline - time.monotonic()))
        for task in done:
            if not task.cancelled():
                task.exception()
        if pending:
            logger.error("OSS worker shutdown deadline reached; process termination required")
            # Do not silently allow a second pool while cancelled work survives.
            _tasks[:] = list(pending)
        else:
            _tasks.clear()
    with _INGRESS_LOCK:
        if _upload_futures:
            logger.warning("OSS SDK threads still running; Redis pending retained; restart blocked until completion")
    with _INGRESS_LOCK:
        while True:
            try:
                _INGRESS.get_nowait()
                _INGRESS.task_done()
            except queue.Empty:
                break
        _INGRESS_SEEN.clear()
    if _client is not None:
        client, _client = _client, None
        close = asyncio.create_task(client.aclose())
        close.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        remaining = max(0, deadline - time.monotonic())
        _, pending = await asyncio.wait({close}, timeout=remaining)
        if pending:
            close.cancel()


# 从资产 params 递归收集本地 /static URL
def _collect_local_urls_from_params(params: Any, out: set[str]) -> None:
    if isinstance(params, dict):
        for key, value in params.items():
            if key in _ASSET_PARAM_URL_KEYS and isinstance(value, str):
                raw = value.strip()
                if storage.is_local_static_url(raw):
                    out.add(raw)
            elif isinstance(value, (dict, list)):
                _collect_local_urls_from_params(value, out)
    elif isinstance(params, list):
        for item in params:
            if isinstance(item, str) and storage.is_local_static_url(item.strip()):
                out.add(item.strip())
            elif isinstance(item, (dict, list)):
                _collect_local_urls_from_params(item, out)


# 将 params 内 old→new 的本地 URL 替换；有改动返回 True
def _rewrite_local_urls_in_params(params: Any, old: str, new: str) -> bool:
    changed = False
    if isinstance(params, dict):
        for key, value in list(params.items()):
            if isinstance(value, str) and value.strip() == old:
                params[key] = new
                changed = True
            elif isinstance(value, (dict, list)):
                if _rewrite_local_urls_in_params(value, old, new):
                    changed = True
    elif isinstance(params, list):
        for index, item in enumerate(params):
            if isinstance(item, str) and item.strip() == old:
                params[index] = new
                changed = True
            elif isinstance(item, (dict, list)):
                if _rewrite_local_urls_in_params(item, old, new):
                    changed = True
    return changed


async def backfill_media_url(old_url: str, new_url: str) -> int:
    """Replace exact local URL references with OSS URL across media tables."""
    old = (old_url or "").strip()
    new = (new_url or "").strip()
    if not old or not new or old == new:
        return 0

    from app.database import AsyncSessionLocal
    from app.models import Shot

    targets = collect_pending_column_targets() + [(Shot, ["image_url", "image_ark_url", "last_frame_url", "video_url", "audio_url"])]
    changed = 0
    async with AsyncSessionLocal() as db:
        for model, fields in targets:
            for field in fields:
                col = getattr(model, field)
                result = await db.execute(
                    update(model).where(col == old).values(**{field: new})
                )
                changed += int(result.rowcount or 0)

        for model, fields in _json_targets():
            for field in fields:
                cursor = None
                while True:
                    col = getattr(model, field)
                    stmt = (select(model).where(cast(col, String).contains(old, autoescape=True))
                            .with_for_update().execution_options(populate_existing=True))
                    if cursor is not None:
                        stmt = stmt.where(model.id > cursor)
                    rows = (await db.execute(stmt.order_by(model.id).limit(100))).scalars().all()
                    if not rows:
                        break
                    for row in rows:
                        rewritten = copy.deepcopy(getattr(row, field))
                        if _rewrite_local_urls_in_params(rewritten, old, new):
                            setattr(row, field, rewritten)
                            changed += 1
                    cursor = rows[-1].id
        await db.commit()
    if changed:
        logger.info("oss backfill rows=%s id=%s", changed, _digest(old))
    return changed


def collect_pending_column_targets() -> list[tuple[type, list[str]]]:
    """Recover committed public media; kepu shot intermediates remain local."""
    from app.models import Project, Template, Work, User, ToolRun
    from app.models_drama import DramaAsset, DramaEpisodeFragment
    return [
        (User, ["avatar_url"]),
        (Project, ["cover_url", "ref_image_url", "final_video_url"]),
        (Template, ["preview_cover"]),
        (Work, ["cover_url", "video_url"]),
        (ToolRun, ["preview_url"]),
        (DramaAsset, ["cover", "url"]),
        (DramaEpisodeFragment, ["cover", "video"]),
    ]


def _json_targets() -> list[tuple[type, list[str]]]:
    from app.models import ToolRun
    from app.models_drama import DramaAsset, DramaEpisodeFragment, DramaEpisode, DramaProject
    return [
        (ToolRun, ["urls", "params"]), (DramaAsset, ["params"]),
        (DramaEpisodeFragment, ["params"]), (DramaEpisode, ["params"]),
        (DramaProject, ["params", "content"]),
    ]


async def collect_pending_local_media_urls(*, limit: int = 2000) -> list[str]:
    """Read at most one 100-row keyset page per model/field per invocation.

    Cursors advance even for missing/failed URLs, and wrap at table end. Thus
    old failed rows cannot pin the reconciliation scan to the first batch.
    """
    from app.database import AsyncSessionLocal
    from app.models import Shot
    found: set[str] = set()
    groups = [(model, fields, False) for model, fields in collect_pending_column_targets()]
    # User-uploaded shot images are admitted outside skip_oss_intermediates.
    # Generated kepu shot media intentionally remain local.
    groups.append((Shot, ["image_url"], False))
    groups += [(model, fields, True) for model, fields in _json_targets()]
    async with AsyncSessionLocal() as db:
        for model, fields, is_json in groups:
            key = f"{model.__tablename__}:{is_json}"
            stmt = select(model.id, *(getattr(model, field) for field in fields))
            cursor = _scan_cursors.get(key)
            if cursor is not None:
                stmt = stmt.where(model.id > cursor)
            rows = (await db.execute(stmt.order_by(model.id).limit(100))).all()
            _scan_cursors[key] = rows[-1][0] if rows else None
            for row in rows:
                for value in row[1:]:
                    if is_json:
                        _collect_local_urls_from_params(value, found)
                    elif isinstance(value, str) and storage.is_local_static_url(value.strip()):
                        if model is not Shot or "_upload." in value or "_upload-" in value:
                            found.add(value.strip())
    return sorted(found)[:max(1, limit)]


def upload_local_url_sync(local_url: str) -> str | None:
    """同步上传单个本地 URL；成功返回 OSS https，失败返回 None。"""
    url = (local_url or "").strip()
    if not url or not storage.is_local_static_url(url):
        return None
    if not oss_svc.oss_enabled():
        return None
    path = storage.local_path_from_url(url)
    if not path or not path.is_file():
        logger.warning("oss backfill skip missing file %s", url)
        return None
    oss_url = storage.upload_local_sync(path, canonical=True)
    # 成功须为公网 http(s)；勿用 is_local_static_url（本地副本仍在会误判 OSS URL）
    if not oss_url or not (oss_url.startswith("http://") or oss_url.startswith("https://")):
        raise RuntimeError(f"upload returned local URL for {url}")
    return oss_url


async def backfill_pending_local_media(*, limit: int = 500, dry_run: bool = False) -> dict[str, Any]:
    """把库里仍是 /static 的媒体补传到 OSS 并回写 URL。"""
    pending = await collect_pending_local_media_urls(limit=limit)
    # uploaded / failed / skipped / changed_rows 统计
    uploaded = 0
    failed = 0
    skipped = 0
    changed_rows = 0
    errors: list[str] = []

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "pending": len(pending),
            "urls": pending[:50],
        }

    if not oss_svc.oss_enabled():
        return {"ok": False, "error": "OSS disabled", "pending": len(pending)}

    for local_url in pending:
        try:
            oss_url = await asyncio.to_thread(upload_local_url_sync, local_url)
            if not oss_url:
                skipped += 1
                continue
            changed_rows += await backfill_media_url(local_url, oss_url)
            await clear_enqueue_marker(local_url)
            uploaded += 1
            logger.info("oss pending backfill ok id=%s", _digest(local_url))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"{local_url}: {exc}"[:240])
            logger.exception("oss pending backfill failed %s", local_url)

    return {
        "ok": failed == 0,
        "pending": len(pending),
        "uploaded": uploaded,
        "skipped": skipped,
        "failed": failed,
        "changed_rows": changed_rows,
        "errors": errors[:20],
    }
