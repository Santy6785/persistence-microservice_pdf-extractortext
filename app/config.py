"""
Configuración centralizada de la aplicación usando Pydantic Settings.
Carga variables de entorno de forma tipada y segura.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del microservicio persistence."""

    app_env: str = "development"
    app_port: int = 8000
    app_host: str = "0.0.0.0"
    log_level: str = "INFO"

    max_payload_size_bytes: int = 26214400  # 25 MB por defecto

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/persistence_db"
    test_database_url: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia singleton cacheada de Settings."""
    return Settings()
