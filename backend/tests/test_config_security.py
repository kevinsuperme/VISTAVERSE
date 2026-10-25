"""Production configuration must reject checked-in placeholder secrets/hosts."""

from __future__ import annotations

import pytest

from app import config


_PRODUCTION_ENV = {
    "ENVIRONMENT": "production",
    "SECRET_KEY": "S" * 64,
    "DATABASE_URL": "postgresql+asyncpg://printfilm:strong-pass@127.0.0.1:5432/printfilm",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://printfilm:strong-pass@127.0.0.1:5432/printfilm",
    "REDIS_URL": "redis://:strong-pass@127.0.0.1:6379/0",
    "PUBLIC_BASE_URL": "https://studio.vistaverse.test",
    "CORS_ORIGINS": "https://studio.vistaverse.test",
    "OPENAI_API_KEY": "",
    "ARK_API_KEY": "",
}


def _load_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str):
    for key, value in {**_PRODUCTION_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)
    config.get_settings.cache_clear()
    return config.get_settings()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("SECRET_KEY", "replace-with-at-least-32-random-characters"),
        ("SECRET_KEY", "replace-me"),
        ("OPENAI_API_KEY", "replace-me"),
        ("ARK_API_KEY", "your-tokenfree-api-key"),
    ],
)
def test_production_rejects_placeholder_secrets(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    for key, env_value in _PRODUCTION_ENV.items():
        monkeypatch.setenv(key, env_value)
    monkeypatch.setenv(field, value)
    config.get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="示例|随机"):
        config.get_settings()


@pytest.mark.parametrize(
    "url",
    ["https://your-domain.example", "https://your-site.example.com"],
)
def test_production_rejects_placeholder_public_url(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    with pytest.raises(RuntimeError, match="示例域名"):
        _load_settings(monkeypatch, PUBLIC_BASE_URL=url)


def test_production_rejects_placeholder_cors_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        _load_settings(monkeypatch, CORS_ORIGINS="https://your-domain.example")


def test_production_accepts_real_secret_and_optional_blank_provider_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    assert settings.environment == "production"
    assert settings.secret_key == "S" * 64
    assert settings.openai_api_key == ""
    assert settings.ark_api_key == ""
