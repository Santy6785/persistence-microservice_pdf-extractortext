import pytest

from app.config import Settings, get_settings


def test_default_settings():
    settings = Settings()
    assert settings.app_env in ["development", "production", "test"]
    assert settings.app_port == 8000
    assert settings.app_host == "0.0.0.0"
    assert "postgresql+asyncpg" in settings.database_url
    assert settings.max_payload_size_bytes == 26214400


def test_settings_override_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/prod_db")
    monkeypatch.setenv("MAX_PAYLOAD_SIZE_BYTES", "10485760")

    settings = Settings()
    assert settings.app_env == "production"
    assert settings.app_port == 9000
    assert settings.database_url == "postgresql+asyncpg://user:pass@db:5432/prod_db"
    assert settings.max_payload_size_bytes == 10485760


def test_get_settings_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
