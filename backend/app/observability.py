"""Small dependency-free process metrics used by the operator diagnostics.

The counters are intentionally bounded to the current process. They complement
structured request logs and task/database metrics without pretending to be a
replacement for a durable metrics backend.
"""

from __future__ import annotations

from threading import Lock

_lock = Lock()
_total = 0
_errors = 0
_slow = 0
_latency_ms = 0.0


def record_request(*, status_code: int, elapsed_ms: float, slow_threshold_ms: float = 3000.0) -> None:
    global _total, _errors, _slow, _latency_ms
    with _lock:
        _total += 1
        _errors += int(status_code >= 400)
        _slow += int(elapsed_ms >= slow_threshold_ms)
        _latency_ms += max(0.0, elapsed_ms)


def snapshot() -> dict[str, int | float | None]:
    with _lock:
        total = _total
        return {
            "requests_total": total,
            "errors_total": _errors,
            "slow_requests_total": _slow,
            "latency_ms_total": round(_latency_ms, 2),
            "latency_ms_avg": round(_latency_ms / total, 2) if total else None,
        }
