import asyncio
import threading
import queue
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import progress, oss_queue


def test_progress_subscriber_is_bounded_and_keeps_latest(monkeypatch):
    progress._queues.clear()
    progress._latest.clear()
    q = progress.subscribe(77)
    for i in range(progress._QUEUE_SIZE + 10):
        progress._offer(q, {"step": i})
    assert q.qsize() == progress._QUEUE_SIZE
    assert q.get_nowait()["step"] == 10
    progress.unsubscribe(77, q)


@pytest.mark.asyncio
async def test_oss_enqueue_is_bounded_without_redis(monkeypatch):
    oss_queue._tasks[:] = [asyncio.current_task()]
    oss_queue._stopping = False
    monkeypatch.setattr(oss_queue.storage, "is_local_static_url", lambda _: True)
    monkeypatch.setattr(oss_queue.oss_svc, "oss_enabled", lambda: True)
    while True:
        try:
            oss_queue._INGRESS.get_nowait()
            oss_queue._INGRESS.task_done()
        except Exception:
            break
    for _ in range(oss_queue._MAX_PENDING):
        assert oss_queue.enqueue_oss_upload(f"/static/{_}.png")
    assert oss_queue.enqueue_oss_upload("/static/b.png") is False
    while True:
        try:
            oss_queue._INGRESS.get_nowait()
            oss_queue._INGRESS.task_done()
        except Exception:
            break
    oss_queue._tasks.clear()
    oss_queue._INGRESS_SEEN.clear()


@pytest.mark.asyncio
async def test_upload_db_failure_keeps_durable_job(monkeypatch):
    monkeypatch.setattr(oss_queue, "upload_local_url_sync", lambda _: "https://oss/media")
    commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    ack = AsyncMock()
    monkeypatch.setattr(oss_queue, "backfill_media_url", commit)
    monkeypatch.setattr(oss_queue, "clear_enqueue_marker", ack)
    with pytest.raises(RuntimeError, match="commit failed"):
        await oss_queue._upload_local_url_background("/static/media")
    ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_retains_upload_thread_accounting_and_keeps_pending(monkeypatch):
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    def upload(_):
        entered.set()
        release.wait(2)
        exited.set()
        return "https://oss/media"
    ack = AsyncMock()
    monkeypatch.setattr(oss_queue, "upload_local_url_sync", upload)
    monkeypatch.setattr(oss_queue, "clear_enqueue_marker", ack)
    task = asyncio.create_task(oss_queue._upload_local_url_background("/static/media"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.2)
        assert oss_queue._upload_futures
        release.set()
        assert await asyncio.to_thread(exited.wait, 1)
        await asyncio.sleep(0)
        assert exited.is_set()
        ack.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_persister_cancel_accounts_for_inflight_and_restart(monkeypatch):
    oss_queue._INGRESS.put_nowait("/static/recover.png")
    oss_queue._INGRESS_SEEN.add("/static/recover.png")
    entered = asyncio.Event()
    async def unavailable(_):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(oss_queue, "_persist_pending", unavailable)
    task = asyncio.create_task(oss_queue._persist_ingress())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert oss_queue._INGRESS.unfinished_tasks == 0
    assert not oss_queue._INGRESS_SEEN
    persisted = AsyncMock(return_value=True)
    monkeypatch.setattr(oss_queue, "_persist_pending", persisted)
    oss_queue._INGRESS.put_nowait("/static/recovered.png")
    task = asyncio.create_task(oss_queue._persist_ingress())
    await asyncio.wait_for(asyncio.to_thread(oss_queue._INGRESS.join), 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    persisted.assert_awaited_once_with("/static/recovered.png")


@pytest.mark.asyncio
async def test_progress_bridge_recovers_after_initial_failure(monkeypatch):
    received = asyncio.Event()
    class Pubsub:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def subscribe(self, _):
            pass
        async def get_message(self, **kwargs):
            received.set()
            await asyncio.Event().wait()
    class Client:
        calls = 0
        def pubsub(self):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("temporary")
            return Pubsub()
        async def get(self, _):
            return '{"event":"done"}'
    client = Client()
    monkeypatch.setattr(progress, "_get_redis", lambda: client)
    q = asyncio.Queue(maxsize=2)
    task = asyncio.create_task(progress.redis_bridge(1, q))
    try:
        await asyncio.wait_for(received.wait(), 2)
        assert (await q.get())["event"] == "done"
        assert client.calls == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_api_only_does_not_start_oss_workers(monkeypatch):
    monkeypatch.setattr(oss_queue.oss_svc, "oss_enabled", lambda: True)
    monkeypatch.setattr(oss_queue, "get_settings", lambda: SimpleNamespace(oss_upload_async=True, task_runtime_enabled=False))
    await oss_queue.start_oss_workers()
    assert not oss_queue._tasks


def test_async_publish_does_not_fallback_to_sync(tmp_path, monkeypatch):
    path = tmp_path / "asset.png"
    path.write_bytes(b"asset")
    from app.services import storage
    monkeypatch.setattr(storage, "STATIC_ROOT", tmp_path)
    monkeypatch.setattr(oss_queue.oss_svc, "oss_enabled", lambda: True)
    monkeypatch.setattr(storage, "get_settings", lambda: SimpleNamespace(oss_upload_async=True, public_base_url=""))
    def fail(*args, **kwargs):
        raise AssertionError("synchronous upload called")
    monkeypatch.setattr(storage, "upload_local_sync", fail)
    monkeypatch.setattr(oss_queue, "enqueue_oss_upload", fail)
    assert storage.publish_local(path) == "/static/asset.png"


@pytest.mark.asyncio
async def test_progress_close_releases_pool(monkeypatch):
    client = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(progress, "_redis", client)
    await progress.close_progress()
    client.aclose.assert_awaited_once()
    assert progress._redis is None


@pytest.mark.asyncio
async def test_recovery_scan_uses_sql_limit_and_rotating_keyset(monkeypatch):
    import app.database
    from app.models import User
    queries = []
    pages = [[(1, "/static/avatar-a.png")], [(2, "/static/avatar-b.png")], []]
    class Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def execute(self, stmt):
            if "shots" in str(stmt):
                return SimpleNamespace(all=lambda: [])
            queries.append(stmt)
            return SimpleNamespace(all=lambda: pages.pop(0))
    monkeypatch.setattr(app.database, "AsyncSessionLocal", Session)
    monkeypatch.setattr(oss_queue, "collect_pending_column_targets", lambda: [(User, ["avatar_url"])])
    monkeypatch.setattr(oss_queue, "_json_targets", lambda: [])
    oss_queue._scan_cursors.clear()
    assert await oss_queue.collect_pending_local_media_urls() == ["/static/avatar-a.png"]
    assert await oss_queue.collect_pending_local_media_urls() == ["/static/avatar-b.png"]
    assert await oss_queue.collect_pending_local_media_urls() == []
    assert all(stmt._limit_clause.value == 100 for stmt in queries)
    assert "users.id >" in str(queries[1])
    assert oss_queue._scan_cursors["users:False"] is None


@pytest.mark.asyncio
async def test_threaded_duplicate_enqueue_has_one_entry(monkeypatch):
    oss_queue._tasks[:] = [asyncio.current_task()]
    oss_queue._stopping = False
    monkeypatch.setattr(oss_queue.storage, "is_local_static_url", lambda _: True)
    monkeypatch.setattr(oss_queue.oss_svc, "oss_enabled", lambda: True)
    calls = await asyncio.gather(*(asyncio.to_thread(oss_queue.enqueue_oss_upload, "/static/shared.png") for _ in range(20)))
    assert sum(calls) == 1
    assert oss_queue._INGRESS.qsize() == 1
    oss_queue._INGRESS.get_nowait()
    oss_queue._INGRESS.task_done()
    oss_queue._INGRESS_SEEN.clear()
    oss_queue._tasks.clear()


@pytest.mark.asyncio
async def test_persister_retries_temporary_redis_outage(monkeypatch):
    calls = 0
    recovered = asyncio.Event()
    async def persist(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("redis restarting")
        recovered.set()
        return True
    original_sleep = asyncio.sleep
    async def short_sleep(delay):
        await original_sleep(min(delay, 0.001))
    monkeypatch.setattr(oss_queue.asyncio, "sleep", short_sleep)
    monkeypatch.setattr(oss_queue, "_persist_pending", persist)
    oss_queue._INGRESS.put_nowait("/static/retry.png")
    task = asyncio.create_task(oss_queue._persist_ingress())
    try:
        await asyncio.wait_for(recovered.wait(), 1)
        assert calls == 2
        assert oss_queue._INGRESS.unfinished_tasks == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_oss_upload_worker_pool_has_bounded_concurrency(monkeypatch):
    release = asyncio.Event()
    two_started = asyncio.Event()
    active = set()
    peak = 0
    async def upload(url):
        nonlocal peak
        active.add(url)
        peak = max(peak, len(active))
        if len(active) == 2:
            two_started.set()
        try:
            await release.wait()
        finally:
            active.remove(url)
    client = SimpleNamespace(zrangebyscore=AsyncMock(return_value=["/static/a", "/static/b", "/static/c"]))
    monkeypatch.setattr(oss_queue, "_redis", lambda: client)
    monkeypatch.setattr(oss_queue, "_upload_local_url_background", upload)
    tasks = [asyncio.create_task(oss_queue._upload_worker()) for _ in range(2)]
    try:
        await asyncio.wait_for(two_started.wait(), 1)
        assert peak == 2
        assert len(oss_queue._active) == 2
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert not oss_queue._active


@pytest.mark.asyncio
async def test_shutdown_bounded_and_restart_blocked_while_sdk_thread_runs(monkeypatch):
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    def upload(_):
        entered.set()
        release.wait(2)
        exited.set()
        return "https://oss/media"
    monkeypatch.setattr(oss_queue, "upload_local_url_sync", upload)
    monkeypatch.setattr(oss_queue, "_SHUTDOWN_TIMEOUT", 0.05)
    monkeypatch.setattr(oss_queue, "get_settings", lambda: SimpleNamespace(oss_upload_async=True, task_runtime_enabled=True))
    monkeypatch.setattr(oss_queue.oss_svc, "oss_enabled", lambda: True)
    task = asyncio.create_task(oss_queue._upload_local_url_background("/static/hanging.png"))
    oss_queue._tasks[:] = [task]
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await asyncio.wait_for(oss_queue.stop_oss_workers(), 0.2)
        assert not exited.is_set()
        assert not oss_queue._tasks
        with pytest.raises(RuntimeError, match="previous uploads"):
            await oss_queue.start_oss_workers()
    finally:
        release.set()
        assert await asyncio.to_thread(exited.wait, 1)
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_recovery_scan_accepts_old_and_new_manual_shot_names(monkeypatch):
    import app.database
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def execute(self, stmt):
            return SimpleNamespace(all=lambda: [
                (1, "/static/shot_1_upload.png"),
                (2, "/static/shot_2_upload-deadbeef.png"),
                (3, "/static/shot_003.png"),
            ])
    monkeypatch.setattr(app.database, "AsyncSessionLocal", Session)
    monkeypatch.setattr(oss_queue, "collect_pending_column_targets", lambda: [])
    monkeypatch.setattr(oss_queue, "_json_targets", lambda: [])
    oss_queue._scan_cursors.clear()
    assert await oss_queue.collect_pending_local_media_urls() == [
        "/static/shot_1_upload.png", "/static/shot_2_upload-deadbeef.png",
    ]


@pytest.mark.asyncio
async def test_json_backfill_locks_rows_and_refreshes_identity_map(monkeypatch):
    import app.database
    from app.models import ToolRun
    statements = []
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def execute(self, stmt):
            statements.append(stmt)
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
        async def commit(self): pass
    monkeypatch.setattr(app.database, "AsyncSessionLocal", Session)
    monkeypatch.setattr(oss_queue, "collect_pending_column_targets", lambda: [])
    monkeypatch.setattr(oss_queue, "_json_targets", lambda: [(ToolRun, ["urls"])])
    # Direct-column updates include Shot; return rowcount for those.
    original = Session.execute
    async def execute(self, stmt):
        if stmt.is_update:
            return SimpleNamespace(rowcount=0)
        return await original(self, stmt)
    monkeypatch.setattr(Session, "execute", execute)
    assert await oss_queue.backfill_media_url("/static/a", "https://oss/a") == 0
    assert "FOR UPDATE" in str(statements[0])
    assert statements[0].get_execution_options()["populate_existing"] is True
