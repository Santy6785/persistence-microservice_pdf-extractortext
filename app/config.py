"""
Configuración centralizada de la aplicación usando Pydantic Settings.
Carga variables de entorno de forma tipada y segura.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del microservicio persistence."""

    app_env: str = "development"
    app_port: int = 8000
    app_host: str = "0.0.0.0"
    log_level: str = "INFO"

    max_payload_size_bytes: int = 14680064  # 14 MB (margen bajo el límite BSON de 16 MB)

    # MongoDB (única base de persistencia)
    # MONGODB_URI es obligatoria: no tiene valor por defecto (no se commitean credenciales).
    mongodb_uri: str
    mongodb_db: str = "persistence_db"
    mongodb_collection: str = "documents"
    mongodb_server_selection_timeout_ms: int = 5000
    mongodb_connect_timeout_ms: int = 5000
    mongodb_socket_timeout_ms: int = 20000

    # Timeout máximo de cada operación de datos contra MongoDB (ms). Debe ser
    # estrictamente mayor que MONGODB_SERVER_SELECTION_TIMEOUT_MS: la selección
    # de servidor es solo una parte de la operación, y el timeout de operación
    # es el que rige las peticiones de datos reales.
    mongodb_operation_timeout_ms: int = 10000

    # Tope configurable (bytes) del cuerpo que guarda el middleware de trazado
    # (/trace). Si el cuerpo lo supera, se guarda solo el tamaño.
    trace_max_body_bytes: int = 1024 * 1024  # 1 MB por defecto

    @model_validator(mode="before")
    @classmethod
    def _validate_mongodb_uri_presente(cls, data: dict) -> dict:
        """MONGODB_URI es obligatoria: si falta, fallar rápido con mensaje claro."""
        if not data.get("mongodb_uri"):
            raise ValueError(
                "Falta la variable de entorno MONGODB_URI. "
                "Definila en .env con la cadena de conexión a MongoDB "
                "(p. ej. mongodb://usuario:clave@host:27017/base_de_datos). "
                "No commitees credenciales."
            )
        return data

    @model_validator(mode="after")
    def _validate_operation_timeout_gt_server_selection(self) -> "Settings":
        """MONGODB_OPERATION_TIMEOUT_MS debe superar a serverSelectionTimeoutMS."""
        if (
            self.mongodb_operation_timeout_ms
            <= self.mongodb_server_selection_timeout_ms
        ):
            raise ValueError(
                "MONGODB_OPERATION_TIMEOUT_MS debe ser mayor que "
                "MONGODB_SERVER_SELECTION_TIMEOUT_MS"
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia singleton cacheada de Settings."""
    return Settings()
