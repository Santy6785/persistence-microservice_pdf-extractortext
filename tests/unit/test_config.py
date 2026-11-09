import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_default_settings(monkeypatch: pytest.MonkeyPatch):
    # get_settings() usa lru_cache: invalida para leer el entorno actual
    # (sin variables de Mongo de pruebas previas).
    get_settings.cache_clear()
    for var in ["MONGODB_DB"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongodb:27017")

    settings = Settings(_env_file=None)
    assert settings.app_env in ["development", "production", "test"]
    assert settings.app_port == 8000
    assert settings.app_host == "0.0.0.0"
    assert settings.mongodb_uri == "mongodb://mongodb:27017"
    assert settings.mongodb_db == "persistence_db"
    assert settings.max_payload_size_bytes == 14 * 1024 * 1024  # 14 MB por defecto
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

    settings = Settings(_env_file=None)
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


def test_default_operation_timeout_es_mayor_que_server_selection(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.delenv("MONGODB_DB", raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongodb:27017")

    settings = Settings(_env_file=None)
    assert settings.mongodb_operation_timeout_ms == 10000
    assert (
        settings.mongodb_operation_timeout_ms
        > settings.mongodb_server_selection_timeout_ms
    )


def test_operation_timeout_debe_ser_mayor_que_server_selection_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    """MONGODB_OPERATION_TIMEOUT_MS menor o igual que server selection es inválido."""
    monkeypatch.setenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "8000")
    monkeypatch.setenv("MONGODB_OPERATION_TIMEOUT_MS", "5000")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_operation_timeout_por_defecto_igual_a_server_selection_es_invalido(
    monkeypatch: pytest.MonkeyPatch,
):
    """El valor límite (igual) también se rechaza: debe ser estrictamente mayor."""
    monkeypatch.setenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "10000")
    monkeypatch.setenv("MONGODB_OPERATION_TIMEOUT_MS", "10000")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_sin_mongodb_uri_lanza_error_claro(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sin MONGODB_URI, Settings lanza ValidationError que nombra a la variable faltante."""
    get_settings.cache_clear()
    monkeypatch.delenv("MONGODB_URI", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "MONGODB_URI" in str(exc_info.value)


def test_settings_con_mongodb_uri_carga_correctamente(
    monkeypatch: pytest.MonkeyPatch,
):
    """Con MONGODB_URI definida, Settings carga sin fallas."""
    get_settings.cache_clear()
    monkeypatch.setenv(
        "MONGODB_URI", "mongodb://usuario:clave@mongodb:27017/persistence_db?authSource=admin"
    )

    settings = Settings(_env_file=None)
    assert (
        settings.mongodb_uri
        == "mongodb://usuario:clave@mongodb:27017/persistence_db?authSource=admin"
    )
    assert settings.mongodb_db == "persistence_db"


def test_log_level_valor_valido_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
):
    """LOG_LEVEL acepta debug/info/warn/error sin distinguir mayúsculas."""
    get_settings.cache_clear()
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongodb:27017")
    for valor_entrada, valor_esperado in [
        ("debug", "DEBUG"),
        ("DEBUG", "DEBUG"),
        ("Debug", "DEBUG"),
        ("info", "INFO"),
        ("INFO", "INFO"),
        ("Info", "INFO"),
        ("warn", "WARNING"),
        ("WARN", "WARNING"),
        ("Warn", "WARNING"),
        ("error", "ERROR"),
        ("ERROR", "ERROR"),
        ("Error", "ERROR"),
    ]:
        monkeypatch.setenv("LOG_LEVEL", valor_entrada)
        settings = Settings(_env_file=None)
        assert settings.log_level == valor_esperado, (
            f"LOG_LEVEL={valor_entrada!r} -> {settings.log_level!r}, esperado {valor_esperado!r}"
        )
        get_settings.cache_clear()


def test_log_level_warn_se_mapea_a_warning(
    monkeypatch: pytest.MonkeyPatch,
):
    """warn (minúsculas) se normaliza a WARNING."""
    get_settings.cache_clear()
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongodb:27017")
    monkeypatch.setenv("LOG_LEVEL", "warn")
    settings = Settings(_env_file=None)
    assert settings.log_level == "WARNING"


def test_log_level_valor_invalido_falla_con_mensaje_claro(
    monkeypatch: pytest.MonkeyPatch,
):
    """Un valor de LOG_LEVEL no permitido lanza ValidationError."""
    get_settings.cache_clear()
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongodb:27017")
    monkeypatch.setenv("LOG_LEVEL", "trace")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "LOG_LEVEL" in str(exc_info.value)
    assert "trace" in str(exc_info.value)
