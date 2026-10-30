"""Regressions for private uploads, decoded avatars and rendered log redaction."""
from io import BytesIO
import logging

import pytest
from PIL import Image

from app.logging_setup import RedactingFormatter
from app.services import oss
from app.services.avatar_upload import normalize_avatar


def test_avatar_rejects_spoofed_and_truncated_images(tmp_path):
    for raw in (b"<svg onload='evil()'/>", b"\x89PNG\r\n\x1a\nspoof"):
        with pytest.raises(ValueError, match="有效图片"):
            normalize_avatar(BytesIO(raw), tmp_path)
    assert not list(tmp_path.iterdir())


def test_avatar_normalizes_strips_payload_and_bounds_dimensions(tmp_path):
    stream = BytesIO()
    Image.new("RGB", (2048, 32)).save(stream, "PNG")
    stream.write(b"secret-trailing-payload")
    stream.seek(0)
    destination = normalize_avatar(stream, tmp_path)
    assert b"secret-trailing-payload" not in destination.read_bytes()
    with Image.open(destination) as image:
        assert image.format == "PNG"
        assert image.size == (1024, 16)
    assert not list(tmp_path.glob("*.part"))


def test_avatar_rejects_excessive_dimensions(tmp_path):
    stream = BytesIO()
    Image.new("RGB", (8193, 1)).save(stream, "PNG")
    stream.seek(0)
    with pytest.raises(ValueError, match="尺寸过大"):
        normalize_avatar(stream, tmp_path)


def test_oss_upload_is_private_and_signing_failure_is_closed(monkeypatch):
    class Bucket:
        headers = None

        def put_object(self, key, data, *, headers):
            self.headers = headers

        def sign_url(self, *args, **kwargs):
            raise RuntimeError("upstream failure")

    bucket = Bucket()
    monkeypatch.setattr(oss, "_bucket", lambda: bucket)
    monkeypatch.setattr(oss, "oss_enabled", lambda: True)
    canonical = oss.upload_bytes(b"media", "generated/test.png")
    assert "?" not in canonical
    with pytest.raises(RuntimeError, match="signing unavailable"):
        oss.signed_public_url("generated/test.png")
    assert bucket.headers["x-oss-object-acl"] == "private"


def test_log_redaction_includes_traceback_and_query_only_urls():
    formatter = RedactingFormatter(logging.Formatter("%(message)s"))
    try:
        raise RuntimeError("https://user:password@example.com/a?Signature=top-secret")
    except RuntimeError:
        import sys
        record = logging.LogRecord("app", logging.WARNING, __file__, 1,
                                   "recipient=%s path=%s", ("a@example.com", "/api/media/a?signature=abc"),
                                   sys.exc_info())
    rendered = formatter.format(record)
    assert "top-secret" not in rendered
    assert "password" not in rendered
    assert "a@example.com" not in rendered
    assert "signature=abc" not in rendered
    assert "RuntimeError" in rendered


def test_oss_signer_maps_internal_host_to_public_cname(monkeypatch):
    from types import SimpleNamespace
    class Bucket:
        def sign_url(self, method, key, ttl, **kwargs):
            assert key == "kepu/generated/p1/a.png"
            return "https://bucket.oss-internal.aliyuncs.com/kepu/generated/p1/a.png?Expires=999&Signature=safe"
    monkeypatch.setattr(oss, "_bucket", lambda: Bucket())
    monkeypatch.setattr(oss, "oss_enabled", lambda: True)
    monkeypatch.setattr(oss, "get_settings", lambda: SimpleNamespace(oss_public_base="https://cdn.example.com/media"))
    signed = oss.signed_public_url("kepu/generated/p1/a.png")
    assert signed == "https://cdn.example.com/media/kepu/generated/p1/a.png?Expires=999&Signature=safe"


def test_oss_expired_reference_refreshed_and_signing_failure_not_returned(monkeypatch):
    from app.services import media_access, storage
    monkeypatch.setattr(oss, "oss_enabled", lambda: True)
    monkeypatch.setattr(oss, "public_base", lambda: "https://cdn.example.com/media")
    keys = []
    def sign(key, **kwargs):
        keys.append(key)
        return "https://cdn.example.com/media/kepu/generated/p1/a.png?Signature=fresh"
    monkeypatch.setattr(oss, "signed_public_url", sign)
    expired = "https://cdn.example.com/media/kepu/generated/p1/a.png?Expires=1&Signature=old"
    assert "fresh" in storage.republish_url(expired)
    assert "fresh" in storage.protect_media_url(expired)
    assert keys == ["kepu/generated/p1/a.png"] * 2
    def fail(*args, **kwargs):
        raise RuntimeError("signing unavailable")
    monkeypatch.setattr(oss, "signed_public_url", fail)
    with pytest.raises(RuntimeError):
        storage.protect_media_url(expired)
    with pytest.raises(RuntimeError):
        media_access.signed_media_url(expired)


def test_log_redacts_database_and_redis_credentials():
    from app.logging_setup import redact_log_text
    rendered = redact_log_text("postgresql+asyncpg://user:db-password@db/a redis://:cache-password@cache/0")
    assert "db-password" not in rendered
    assert "cache-password" not in rendered


def test_oss_v1_public_host_mapping_preserves_signature(monkeypatch):
    """Real pinned SDK V1 signatures bind bucket/key, not internal vs CNAME host."""
    import oss2
    from urllib.parse import urlsplit, parse_qs
    from app.services import media_access
    auth = oss2.Auth("test-key", "test-secret")
    bucket = oss2.Bucket(auth, "https://oss-cn-hangzhou-internal.aliyuncs.com", "test-bucket")
    monkeypatch.setattr(oss, "_bucket", lambda: bucket)
    monkeypatch.setattr(oss, "oss_enabled", lambda: True)
    monkeypatch.setattr(oss, "public_base", lambda: "https://cdn.example.com/prefix")
    key = "kepu/generated/p1/sp ace+name.png"
    signed = oss.signed_public_url(key)
    parsed = urlsplit(signed)
    assert parsed.netloc == "cdn.example.com"
    assert parsed.path == "/prefix/kepu/generated/p1/sp%20ace%2Bname.png"
    query = parse_qs(parsed.query)
    assert query["OSSAccessKeyId"] == ["test-key"]
    monkeypatch.setattr("time.time", lambda: int(query["Expires"][0]) - 900)
    public_bucket = oss2.Bucket(auth, "https://oss-cn-hangzhou.aliyuncs.com", "test-bucket")
    direct = public_bucket.sign_url("GET", key, 900, slash_safe=True)
    assert parse_qs(urlsplit(direct).query)["Signature"] == query["Signature"]


@pytest.mark.asyncio
async def test_shared_image_upload_rejects_spoof_and_oversize(tmp_path):
    from fastapi import HTTPException, UploadFile
    from app.services.avatar_upload import receive_image_upload
    for content, max_bytes in [(b"<html>not image</html>", 100), (b"x" * 101, 100)]:
        file = UploadFile(filename="cover.png", file=BytesIO(content))
        with pytest.raises(HTTPException) as error:
            await receive_image_upload(file, tmp_path, max_bytes=max_bytes, prefix="cover")
        assert error.value.status_code == 400
        assert file.file.closed
    assert not list(tmp_path.iterdir())
