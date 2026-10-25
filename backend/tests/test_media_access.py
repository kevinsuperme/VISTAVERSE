"""本地生成媒体 URL 解析与签名访问回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

from app.services import media_access
from app.services import storage


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        secret_key="test-media-secret-key-which-is-long-enough",
        media_signed_url_ttl_sec=900,
        public_base_url="http://127.0.0.1:8000",
        oss_public_base="",
        oss_enabled=False,
    )


def test_media_path_rejects_arbitrary_absolute_host(monkeypatch) -> None:
    monkeypatch.setattr(media_access, "get_settings", _settings)

    assert media_access.media_path_from_url("https://evil.example/generated/p1/out.mp4") is None
    assert media_access.media_path_from_url("http://127.0.0.1:8000/static/generated/p1/out.mp4") == (
        "generated/p1/out.mp4"
    )

    monkeypatch.setattr(storage, "get_settings", _settings)
    assert storage.local_path_from_url("https://evil.example/generated/p1/out.mp4") is None
    assert storage.local_path_from_url("/static/generated/p1/../secret.txt") is None


def test_media_path_rejects_encoded_traversal() -> None:
    assert media_access.media_path_from_url("/static/generated/p1/%2e%2e/secret.txt") is None
    assert media_access.media_path_from_url("/static/generated/p1/%252e%252e/secret.txt") is None


def test_signed_media_url_verifies_and_detects_tampering(monkeypatch) -> None:
    monkeypatch.setattr(media_access, "get_settings", _settings)

    signed = media_access.signed_media_url("/static/generated/p1/out.mp4")
    assert signed is not None
    parsed = media_access.urlsplit(signed)
    query = dict(item.split("=", 1) for item in parsed.query.split("&"))
    assert media_access.verify_media_signature(
        parsed.path.removeprefix("/api/media/"), int(query["expires"]), query["signature"]
    )
    assert not media_access.verify_media_signature(
        "generated/p1/other.mp4", int(query["expires"]), query["signature"]
    )


def test_signed_media_url_uses_oss_capability_for_oss_host(monkeypatch) -> None:
    settings = _settings()
    settings.oss_public_base = "https://bucket.example.test"
    settings.oss_enabled = True
    monkeypatch.setattr(media_access, "get_settings", lambda: settings)
    monkeypatch.setattr("app.services.oss.oss_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.oss.signed_public_url",
        lambda key, *, expires: f"https://bucket.example.test/{key}?signed={expires}",
    )

    out = media_access.signed_media_url(
        "https://bucket.example.test/kepu/generated/p1/out.mp4"
    )
    assert out is not None
    assert out.startswith("https://bucket.example.test/kepu/generated/p1/out.mp4?signed=")

