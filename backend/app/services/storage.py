"""Download / persist generated assets under backend/static/generated.

When OSS is enabled:
- Default (async): return /static URL immediately and enqueue upload+DB backfill.
- sync=True: upload inline (template seed, celery unavailable, etc.).
- skip_oss_intermediates(): 科普流水线只上传 final.mp4，分镜图/配音/镜头视频留本地。
FFmpeg always reads local files.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import mimetypes
import socket
import shutil
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from app.config import get_settings

# 科普成片文件名：仅此文件在 skip_oss_intermediates 下仍入 OSS
_KEPU_FINAL_NAMES = frozenset({"final.mp4"})
# True 时 publish_local 跳过中间文件的异步 OSS 入队
_skip_oss_intermediates: ContextVar[bool] = ContextVar("skip_oss_intermediates", default=False)

logger = logging.getLogger(__name__)

STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
GENERATED_ROOT = STATIC_ROOT / "generated"


def disk_status() -> dict[str, int | float]:
    """Return bounded filesystem capacity metrics for operator diagnostics."""
    usage = shutil.disk_usage(STATIC_ROOT)
    used_percent = (usage.used / usage.total * 100.0) if usage.total else 0.0
    return {
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": int(usage.free),
        "used_percent": round(used_percent, 2),
    }


def project_dir(project_id: int) -> Path:
    path = GENERATED_ROOT / f"p{project_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_dir(user_id: int) -> Path:
    path = GENERATED_ROOT / "users" / f"u{user_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def to_public_url(rel_or_abs: str) -> str:
    """Convert /static/... path to absolute URL for frontend."""
    if rel_or_abs.startswith("http://") or rel_or_abs.startswith("https://"):
        return protect_media_url(rel_or_abs)
    settings = get_settings()
    if not rel_or_abs.startswith("/"):
        rel_or_abs = "/" + rel_or_abs
    return protect_media_url(f"{settings.public_base_url.rstrip('/')}{rel_or_abs}")


def local_path_from_url(url: str) -> Path | None:
    """Resolve DB/media URL to a local filesystem path when possible."""
    if not url:
        return None

    parsed = urlsplit(str(url).strip())
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if parsed.scheme or parsed.netloc:
        # An arbitrary absolute URL containing ``/generated/`` must never be
        # treated as a local path. Only our configured app/OSS hosts qualify.
        from app.services.media_access import is_trusted_media_host

        if not is_trusted_media_host(parsed.netloc):
            return None

    def _safe_local(relative: str) -> Path | None:
        """Resolve only paths that remain below STATIC_ROOT."""
        decoded = unquote(relative)
        if "\x00" in decoded or "\\" in decoded:
            return None
        if any(part in {".", ".."} for part in decoded.split("/")):
            logger.warning("拒绝含 dot segment 的媒体路径: %s", url[:160])
            return None
        candidate = (STATIC_ROOT / decoded.lstrip("/\\")).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            logger.warning("拒绝越界媒体路径: %s", url[:160])
            return None
        return candidate

    path = parsed.path
    if path.startswith("/static/"):
        return _safe_local(path.removeprefix("/static/"))
    settings = get_settings()
    if path.startswith("/api/media/"):
        return _safe_local(path.removeprefix("/api/media/"))
    prefix_path = urlsplit(settings.public_base_url.rstrip("/")).path.rstrip("/")
    if prefix_path and path.startswith(f"{prefix_path}/static/"):
        return _safe_local(path.split("/static/", 1)[1])

    # OSS public URL → kepu/generated/... → static/generated/...
    if parsed.scheme in {"http", "https"}:
        from app.services import oss as oss_svc

        if oss_svc.oss_enabled():
            folder = oss_svc.folder_prefix()
            marker = f"/{folder}/"
            idx = path.find(marker)
            if idx >= 0:
                rest = path[idx + len(marker) :]
                return _safe_local(rest)
        # Generic: .../generated/pN/...
        marker2 = "/generated/"
        idx2 = path.find(marker2)
        if idx2 >= 0:
            rest = path[idx2 + 1 :]  # generated/pN/...
            return _safe_local(rest)
    return None


def _is_private_ip(value: str) -> bool:
    """Return whether an address is local, private, link-local or reserved."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _validate_remote_url(url: str) -> None:
    """Reject non-HTTP URLs and destinations that can reach local networks."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("媒体下载仅支持 HTTPS URL")
    hostname = parsed.hostname.rstrip(".")
    if hostname.lower() in {"localhost", "metadata.google.internal"}:
        raise ValueError("媒体下载目标地址不允许访问本机或云元数据服务")
    try:
        resolved = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("媒体下载目标地址无法解析") from exc
    for item in resolved:
        address = item[4][0]
        if _is_private_ip(address):
            raise ValueError("媒体下载目标地址不允许访问内网")


def validate_remote_reference_url(url: str) -> None:
    """Validate a user-supplied reference URL before an upstream fetch."""
    _validate_remote_url(url)


def _download_timeout(timeout: float | httpx.Timeout) -> httpx.Timeout:
    """把秒数收成 httpx.Timeout：连接短、读体长，避免整包 120s 把大视频掐断。"""
    if isinstance(timeout, httpx.Timeout):
        return timeout
    seconds = max(30.0, float(timeout))
    return httpx.Timeout(connect=min(30.0, seconds), read=seconds, write=60.0, pool=30.0)


class RetryableMediaDownloadError(RuntimeError):
    """上游成片已成功，下载被中断。调用方应沿原任务重试下载，不要重新生成。"""

    def __init__(
        self,
        message: str,
        *,
        provider_task_id: str = "",
        counts_attempt: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider_task_id = (provider_task_id or "").strip()
        # 正文下载失败才计入次数；查询抖动或「尚未就绪」不消耗下载额度
        self.counts_attempt = bool(counts_attempt)


def _walk_download_errors(exc: BaseException):
    """沿着 cause/context 看一小段，避免只看最外层包装。"""
    current: BaseException | None = exc
    seen: list[int] = []
    while current is not None and id(current) not in seen and len(seen) < 6:
        seen.append(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_retryable_download_error(exc: BaseException) -> bool:
    """连接被对端掐断、读超时或不完整体，适合沿原任务重试下载。"""
    retryable_types = (
        httpx.RemoteProtocolError,
        httpx.ReadTimeout,
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadError,
        httpx.WriteError,
        httpx.NetworkError,
        httpx.PoolTimeout,
    )
    markers = (
        "peer closed",
        "incomplete download",
        "complete message body",
        "connection reset",
        "connection aborted",
        "broken pipe",
        "10054",
    )
    for current in _walk_download_errors(exc):
        if isinstance(current, RetryableMediaDownloadError):
            return True
        if isinstance(current, retryable_types):
            return True
        text = str(current or "").lower()
        if any(marker in text for marker in markers):
            return True
    return False


_is_retryable_download_error = is_retryable_download_error


# 下载远程文件到 dest；TokenFree 成片 URL 可传 Bearer headers
async def download_to(
    url: str,
    dest: Path,
    *,
    timeout: float | httpx.Timeout = 300.0,
    headers: dict[str, str] | None = None,
    retries: int = 3,
) -> Path:
    import asyncio

    _validate_remote_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    attempts = max(1, int(retries))
    max_bytes = max(1, int(get_settings().media_download_max_bytes))
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            current_url = url
            async with httpx.AsyncClient(timeout=_download_timeout(timeout), follow_redirects=False) as client:
                for _redirect in range(4):
                    _validate_remote_url(current_url)
                    async with client.stream("GET", current_url, headers=headers) as resp:
                        if resp.is_redirect:
                            location = resp.headers.get("location")
                            if not location:
                                raise RuntimeError("媒体下载重定向缺少目标")
                            current_url = urljoin(current_url, location)
                            continue
                        resp.raise_for_status()
                        expected = resp.headers.get("Content-Length")
                        if expected and expected.isdigit() and int(expected) > max_bytes:
                            raise ValueError("媒体文件超过下载大小限制")
                        written = 0
                        with tmp.open("wb") as handle:
                            async for chunk in resp.aiter_bytes(64 * 1024):
                                if chunk:
                                    written += len(chunk)
                                    if written > max_bytes:
                                        raise ValueError("媒体文件超过下载大小限制")
                                    handle.write(chunk)
                    break
                else:
                    raise RuntimeError("媒体下载重定向次数过多")
            if written <= 0:
                raise RuntimeError(f"empty download: {url}")
            if expected and expected.isdigit() and written != int(expected):
                raise RuntimeError(
                    f"incomplete download: {url} got {written} bytes, expected {expected}"
                )
            tmp.replace(dest)
            return dest
        except BaseException as exc:
            last_exc = exc
            try:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
            except OSError:
                logger.warning("failed to remove partial download %s", tmp)
            if attempt + 1 < attempts and _is_retryable_download_error(exc):
                logger.warning(
                    "download retry %s/%s url=%s err=%s",
                    attempt + 1,
                    attempts,
                    (url or "")[:120],
                    exc,
                )
                await asyncio.sleep(1.5 + attempt * 2.0)
                continue
            raise
    assert last_exc is not None
    raise last_exc


def file_to_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def ensure_local_media(url: str, dest: Path) -> Path:
    """If url is remote, download; if already local, copy/resolve."""
    local = local_path_from_url(url)
    if local and local.exists():
        if local.resolve() != dest.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(local.read_bytes())
        return dest
    if url.startswith("http://") or url.startswith("https://"):
        return await download_to(url, dest)
    raise FileNotFoundError(f"cannot resolve media: {url}")


def rel_static_url(path: Path) -> str:
    rel = path.resolve().relative_to(STATIC_ROOT.resolve())
    return protect_media_url(f"/static/{rel.as_posix()}")


def protect_media_url(url: str) -> str:
    """Sign local generated URLs when production media ACL is enabled.

    Paths outside ``static/generated`` (templates, mock assets and SPA files)
    remain public. Existing OSS URLs are left untouched.
    """
    if not url:
        return url
    from app.services import media_access
    # Private OSS objects require signing even when local signature mode is off.
    if media_access.oss_object_key(url) is not None:
        return media_access.signed_media_url(url)
    if not bool(getattr(get_settings(), "media_require_signature", False)):
        return url

    parsed = urlsplit(url)
    if parsed.path.startswith("/api/media/"):
        params = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
        try:
            if media_access.verify_media_signature(
                parsed.path.removeprefix("/api/media/"),
                int(params.get("expires", "0")),
                params.get("signature", ""),
            ):
                return url
        except (TypeError, ValueError):
            pass
    if parsed.scheme or parsed.netloc:
        if not media_access.is_trusted_media_host(parsed.netloc):
            return url
        configured_base = urlsplit(str(getattr(get_settings(), "public_base_url", "") or ""))
        if parsed.netloc.lower() != configured_base.netloc.lower():
            return media_access.signed_media_url(url) or url
    key = media_access.media_path_from_url(url)
    if not key or not key.startswith("generated/"):
        return url
    local = local_path_from_url(url)
    if not local or not local.is_file():
        return url
    return media_access.signed_media_url(url) or url


def protect_media_payload(value: Any) -> Any:
    """Recursively refresh local generated URLs in an API JSON payload.

    A generated URL may have been persisted by an older service call. Applying
    the capability at the response boundary prevents an expired database URL
    from being handed to the browser while keeping storage rows canonical or
    backward compatible.
    """
    if isinstance(value, str):
        return protect_media_url(value)
    if isinstance(value, list):
        return [protect_media_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: protect_media_payload(item) for key, item in value.items()}
    return value


def signed_media_url(url: str, *, expires: int | None = None) -> str | None:
    """Public storage helper for issuing a short-lived local media URL."""
    from app.services import media_access

    return media_access.signed_media_url(url, expires=expires)


def is_local_static_url(url: str | None) -> bool:
    """True when url points at media under backend/static (relative or site /static/).

    HTTPS OSS/CDN 地址即使本地仍保留 FFmpeg 副本，也不算本地 URL。
    """
    if not url:
        return False
    if url.startswith("/static/"):
        return True
    if url.startswith("/api/media/"):
        return True
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    if url.startswith(f"{base}/static/") or url.startswith(f"{base}/api/media/"):
        return True
    # 主站 / 旧站 / 历史拼写错误域名、本地调试地址
    for host in (
        "www.printfilm.com",
        "printfilm.com",
        "kepu.printfilm.com",
        "kepu.printtfilm.com",
        "127.0.0.1:8000",
        "localhost:8000",
    ):
        for scheme in ("https://", "http://"):
            if url.startswith(f"{scheme}{host}/static/") or url.startswith(f"{scheme}{host}/api/media/"):
                return True
    # 远程 http(s)（含 OSS public_base）一律非本地；勿因磁盘副本误判
    if url.startswith("http://") or url.startswith("https://"):
        return False
    return False


@contextmanager
def skip_oss_intermediates() -> Iterator[None]:
    """科普流水线：中间分镜不入 OSS 队列，成片 final.mp4 仍上传。"""
    token = _skip_oss_intermediates.set(True)
    try:
        yield
    finally:
        _skip_oss_intermediates.reset(token)


F = TypeVar("F", bound=Callable[..., Any])


def without_intermediate_oss(fn: F) -> F:
    """装饰科普入口：调用期间跳过中间文件异步 OSS 上传。"""

    @wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any):
        with skip_oss_intermediates():
            return await fn(*args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def is_kepu_final_media(path: Path) -> bool:
    """是否为科普最终成片文件（当前仅 final.mp4）。"""
    return Path(path).name.lower() in _KEPU_FINAL_NAMES


def upload_local_sync(path: Path, *, retries: int = 2, canonical: bool = False) -> str:
    """Upload file to OSS synchronously; raises if OSS disabled or all retries fail."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    from app.services import oss as oss_svc

    if not oss_svc.oss_enabled():
        return rel_static_url(path)
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            uploaded = oss_svc.upload_file(path)
            return uploaded if canonical else protect_media_url(uploaded)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning(
                "OSS upload attempt %s/%s failed for %s: %s",
                attempt + 1,
                retries,
                path,
                exc,
            )
    raise RuntimeError(f"OSS upload failed for {path}: {last_err}")


def publish_local(path: Path, *, sync: bool = False, retries: int = 2) -> str:
    """Publish media for the frontend.

    Default: return /static URL immediately; when OSS async is on, enqueue
    upload and DB backfill. Use sync=True for startup seeds or when immediate OSS
    URL is required.

    科普 skip_oss_intermediates 下：非 final.mp4 的异步上传会被跳过；sync=True
    仍上传（Seedance 参考图需要公网 https）。
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    local_url = rel_static_url(path)
    from app.services import oss as oss_svc

    if not oss_svc.oss_enabled():
        return local_url

    # 科普中间文件：异步不入队；显式 sync 仍走公网（方舟拉参考图）
    skip_mid = _skip_oss_intermediates.get() and not is_kepu_final_media(path)
    if skip_mid and not sync:
        return local_url

    settings = get_settings()
    want_async = (
        not sync
        and bool(settings.oss_upload_async)
    )
    if want_async:
        try:
            from app.services.oss_queue import enqueue_oss_upload

            enqueue_oss_upload(local_url)
            return local_url
        except Exception:  # noqa: BLE001
            logger.warning("OSS queue unavailable; retaining local media for reconciliation")
            return local_url

    try:
        return upload_local_sync(path, retries=retries)
    except Exception as exc:  # noqa: BLE001
        logger.error("OSS sync upload failed for %s, keeping local URL: %s", path, exc)
        return local_url


def republish_url(url: str | None, *, sync: bool = True) -> str | None:
    """If url is a local /static path and file exists, upload to OSS and return new URL."""
    if not url:
        return url
    from app.services import media_access
    if media_access.oss_object_key(url) is not None:
        return media_access.signed_media_url(url)
    if not is_local_static_url(url):
        return url
    from app.services import oss as oss_svc

    if not oss_svc.oss_enabled():
        return url
    local = local_path_from_url(url)
    if not local or not local.is_file():
        logger.warning("cannot republish missing local media: %s", url)
        return url
    return publish_local(local, sync=sync)
