"""Small process-local guard for unauthenticated authentication endpoints.

It is a last line of defence for a single API process. Production deployments
should still enforce a shared rate limit at the reverse proxy or API gateway.
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

_WINDOW_SECONDS = 60.0
_LIMITS = {
    "/api/auth/login": 10,
    "/api/auth/register": 10,
    "/api/auth/forgot-password": 5,
    "/api/auth/reset-password": 10,
}
_lock = Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def check_auth_rate_limit(path: str, client_key: str) -> int | None:
    """Return retry seconds when limited, otherwise record and return ``None``."""
    limit = _LIMITS.get(path)
    if limit is None:
        return None
    now = monotonic()
    key = (path, client_key or "unknown")
    with _lock:
        bucket = _hits[key]
        while bucket and now - bucket[0] >= _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= limit:
            return max(1, int(_WINDOW_SECONDS - (now - bucket[0])))
        bucket.append(now)
        # Keep the dictionary bounded in long-lived development processes.
        if len(_hits) > 2048:
            stale = [item for item, values in _hits.items() if not values or now - values[-1] >= _WINDOW_SECONDS]
            for item in stale[:512]:
                _hits.pop(item, None)
    return None
