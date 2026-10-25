"""Submódulo de conexión a MongoDB."""

from app.infrastructure.database.connection import (
    close_client,
    get_client,
    get_database_name,
    ping,
)

__all__ = [
    "get_client",
    "close_client",
    "get_database_name",
    "ping",
]
