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
    mongodb_uri: str = "mongodb://mongodb:27017"
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
