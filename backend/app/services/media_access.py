"""签名的本地媒体访问。

数据库只保存规范化的 ``/static/generated/...`` 或 OSS URL；浏览器得到的
本地媒体链接由这里签发短期 HMAC capability。签名内容包含完整对象路径和
过期时间，避免把任意文件路径或外部 URL 当成本地文件读取。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from app.config import get_settings

MEDIA_PREFIX = "generated/"


def is_trusted_media_host(netloc: str) -> bool:
    """Whether an absolute URL belongs to this app or its configured OSS CDN."""
    candidate = (netloc or "").strip().lower().rstrip(".")
    if not candidate:
        return False
    settings = get_settings()
    configured = []
    for raw in (
        getattr(settings, "public_base_url", ""),
        getattr(settings, "oss_public_base", ""),
    ):
        parsed = urlsplit(str(raw or ""))
        if parsed.netloc:
            configured.append(parsed.netloc.lower().rstrip("."))
    # Legacy production hostnames are explicit trust anchors, not a generic
    # "any host containing generated" rule.
    configured.extend(
        {
            "www.printfilm.com",
            "printfilm.com",
            "kepu.printfilm.com",
            "kepu.printtfilm.com",
            "127.0.0.1:8000",
            "localhost:8000",
        }
    )
    if candidate in configured:
        return True
    try:
        from app.services import oss

        if oss.oss_enabled():
            oss_netloc = urlsplit(oss.public_base()).netloc.lower().rstrip(".")
            return candidate == oss_netloc
    except Exception:  # noqa: BLE001
        return False
    return False


def _secret_key() -> bytes:
    key = str(getattr(get_settings(), "secret_key", "") or "").strip()
    if not key:
        raise RuntimeError("媒体签名密钥未配置")
    return key.encode("utf-8")


def _ttl() -> int:
    value = int(getattr(get_settings(), "media_signed_url_ttl_sec", 900) or 900)
    return max(60, min(value, 86_400))


def _decode_path(value: str) -> str:
    # URL path 只解码一次；拒绝反斜杠、NUL 和 dot segments，避免不同层级
    # 对同一个对象名产生不同解释。
    raw = str(value or "")
    decoded = unquote(raw).replace("\\", "/")
    # A second encoded traversal must not become meaningful after another
    # proxy/framework decode. Reject residual percent escapes that decode to a
    # dot segment or slash rather than accepting an ambiguous object key.
    second = unquote(decoded)
    if second != decoded and any(part in {".", ".."} for part in second.replace("\\", "/").split("/")):
        raise ValueError("媒体路径无效")
    if "\x00" in decoded:
        raise ValueError("媒体路径无效")
    parts = [part for part in decoded.split("/") if part not in {""}]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("媒体路径无效")
    normalized = "/".join(parts)
    if not normalized.startswith(MEDIA_PREFIX) or normalized == MEDIA_PREFIX:
        raise ValueError("媒体路径无效")
    return normalized


def media_path_from_url(value: str) -> str | None:
    """Extract a validated ``generated/...`` key from a local media URL."""
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if (parsed.scheme or parsed.netloc) and not is_trusted_media_host(parsed.netloc):
        return None
    path = parsed.path
    if path.startswith("/static/"):
        path = path[len("/static/") :]
    elif path.startswith("static/"):
        path = path[len("static/") :]
    elif path.startswith("/api/media/"):
        path = path[len("/api/media/") :]
    elif path.startswith("api/media/"):
        path = path[len("api/media/") :]
    elif parsed.scheme or parsed.netloc:
        marker = "/generated/"
        if marker not in path:
            return None
        path = path.split(marker, 1)[1]
        path = f"generated/{path}"
    try:
        return _decode_path(path)
    except ValueError:
        return None


def local_media_path(value: str) -> Path | None:
    """Resolve a generated key below ``static/generated`` only."""
    key = media_path_from_url(value)
    if not key:
        return None
    from app.services.storage import GENERATED_ROOT

    candidate = (GENERATED_ROOT / key.removeprefix(MEDIA_PREFIX)).resolve()
    try:
        candidate.relative_to(GENERATED_ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _payload(key: str, expires: int) -> bytes:
    return f"{key}\n{int(expires)}".encode()


def _signature(key: str, expires: int) -> str:
    digest = hmac.new(_secret_key(), _payload(key, expires), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def sign_media_path(path: str, *, expires: int | None = None) -> tuple[str, int, str]:
    """Return ``(key, expires, signature)`` for a validated media path."""
    key = _decode_path(path)
    exp = int(expires if expires is not None else time.time() + _ttl())
    if exp <= int(time.time()):
        raise ValueError("媒体签名过期时间无效")
    return key, exp, _signature(key, exp)


def verify_media_signature(path: str, expires: int, signature: str) -> bool:
    try:
        key = _decode_path(path)
        exp = int(expires)
        if exp <= int(time.time()) or exp > int(time.time()) + 86_400:
            return False
        expected = _signature(key, exp)
        return hmac.compare_digest(expected, str(signature or ""))
    except (TypeError, ValueError, RuntimeError):
        return False


def signed_media_url(value: str, *, expires: int | None = None) -> str | None:
    """Convert a generated local URL to a short-lived API URL.

    Non-local/OSS URLs are returned unchanged so existing public OSS delivery
    keeps working; callers that need private OSS should use its OSS signer.
    """
    key = media_path_from_url(value)
    if not key:
        return None
    _, exp, signature = sign_media_path(key, expires=expires)
    parsed = urlsplit(str(value or "").strip())
    if parsed.netloc:
        try:
            from app.services import oss

            configured_oss_base = str(getattr(get_settings(), "oss_public_base", "") or "").strip()
            oss_base = configured_oss_base or oss.public_base()
            oss_netloc = urlsplit(oss_base).netloc.lower().rstrip(".")
            if parsed.netloc.lower().rstrip(".") == oss_netloc and oss.oss_enabled():
                base_path = urlsplit(oss_base).path.rstrip("/")
                object_key = parsed.path.removeprefix(f"{base_path}/").lstrip("/")
                return oss.signed_public_url(object_key, expires=exp - int(time.time()))
        except Exception:  # noqa: BLE001
            return None
    base = str(getattr(get_settings(), "public_base_url", "") or "").rstrip("/")
    route = f"/api/media/{quote(key, safe='/')}"
    query = f"?expires={exp}&signature={quote(signature)}"
    return f"{base}{route}{query}" if base else f"{route}{query}"


def canonical_media_url(value: str) -> str | None:
    """Return a stable local DB URL for a generated object."""
    key = media_path_from_url(value)
    return f"/static/{key}" if key else None


async def user_owns_media(db, user_id: int, value: str) -> bool:
    """Check ownership before issuing a browser capability.

    User/tool directories encode the owner. Project directories are checked in
    both the legacy project table and the drama project table because their IDs
    share the same ``generated/p{id}`` layout.
    """
    key = media_path_from_url(value)
    if not key:
        return False
    parts = key.split("/")
    if len(parts) >= 4 and parts[0] == "generated" and parts[1] in {"users", "tools"}:
        try:
            return int(parts[2].removeprefix("u")) == int(user_id)
        except (TypeError, ValueError):
            return False
    if (
        len(parts) >= 5
        and parts[:3] == ["generated", "p0", "tools"]
        and parts[3].startswith("u")
    ):
        try:
            return int(parts[3][1:]) == int(user_id)
        except (TypeError, ValueError):
            return False
    if len(parts) < 3:
        return False
    # key is generated/p{id}/...; tolerate callers passing the prefix stripped
    # by using the normalized path above.
    if parts[0] != "generated" or not parts[1].startswith("p"):
        return False
    try:
        project_id = int(parts[1][1:])
    except ValueError:
        return False
    from sqlalchemy import select

    from app.models import Project

    predicates = [Project.id == project_id]
    try:
        from app.models_drama import DramaProject

        stmt = select(Project.id).where(Project.id == project_id, Project.user_id == user_id).limit(1)
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            return True
        drama_stmt = select(DramaProject.id).where(
            DramaProject.id == project_id,
            DramaProject.user_id == user_id,
        ).limit(1)
        return (await db.execute(drama_stmt)).scalar_one_or_none() is not None
    except Exception:  # noqa: BLE001
        # Missing optional drama tables must not turn ownership checks into an
        # allow decision; legacy project ownership is still checked above.
        stmt = select(Project.id).where(*predicates, Project.user_id == user_id).limit(1)
        return (await db.execute(stmt)).scalar_one_or_none() is not None

