import pytest

from app.config import Settings, get_settings


def test_default_settings(monkeypatch: pytest.MonkeyPatch):
    # get_settings() usa lru_cache: invalida para leer el entorno actual
    # (sin variables de Mongo de pruebas previas).
    get_settings.cache_clear()
    for var in ["MONGODB_URI", "MONGODB_DB"]:
        monkeypatch.delenv(var, raising=False)

    settings = Settings()
    assert settings.app_env in ["development", "production", "test"]
    assert settings.app_port == 8000
    assert settings.app_host == "0.0.0.0"
    assert settings.mongodb_uri == "mongodb://mongodb:27017"
    assert settings.mongodb_db == "persistence_db"
    assert settings.max_payload_size_bytes == 26214400
    assert settings.mongodb_server_selection_timeout_ms == 5000
    assert settings.mongodb_connect_timeout_ms == 5000
    assert settings.mongodb_socket_timeout_ms == 20000


def test_settings_override_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("MONGODB_URI", "mongodb://user:pass@db:27017/prod_db")
    monkeypatch.setenv("MONGODB_DB", "prod_db")
    monkeypatch.setenv("MAX_PAYLOAD_SIZE_BYTES", "10485760")
    monkeypatch.setenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "3000")

    settings = Settings()
    assert settings.app_env == "production"
    assert settings.app_port == 9000
    assert settings.mongodb_uri == "mongodb://user:pass@db:27017/prod_db"
    assert settings.mongodb_db == "prod_db"
    assert settings.max_payload_size_bytes == 10485760
    assert settings.mongodb_server_selection_timeout_ms == 3000


def test_get_settings_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
