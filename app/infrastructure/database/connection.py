"""
Gestión de la conexión asíncrona a MongoDB con el cliente oficial de PyMongo (AsyncMongoClient).

El cliente es un singleton creado al arrancar y cerrado al apagar.
Los timeouts son configurables por variables de entorno (vía pydantic-settings).
"""

from typing import Optional

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from app.config import get_settings

_client: Optional[AsyncMongoClient] = None
_database_name: str = "persistence_db"


def get_client() -> AsyncMongoClient:
    """Retorna el cliente singleton de MongoDB, creándolo si es necesario."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncMongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
            connectTimeoutMS=settings.mongodb_connect_timeout_ms,
            socketTimeoutMS=settings.mongodb_socket_timeout_ms,
        )
    return _client


def get_database_name() -> str:
    """Retorna el nombre de la base de datos configurada."""
    settings = get_settings()
    return settings.mongodb_db


async def close_client() -> None:
    """Cierra el cliente singleton de MongoDB y libera sus recursos."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ping() -> bool:
    """Ejecuta un ping contra MongoDB para verificar conectividad activa.

    Retorna True si el servidor responde, False en caso contrario.
    Nunca lanza excepción al caller: cualquier fallo se reporta como False.
    """
    try:
        client = get_client()
        await client.admin.command("ping")
        return True
    except PyMongoError:
        return False


async def ensure_indexes() -> None:
    """Crea los índices requeridos en la colección de documentos.

    - Índice único en `checksum_sha256` (garantiza unicidad estricta del checksum).
    - Índice compuesto en `(created_at DESC, _id ASC)` (soporta el orden
      determinista de list_paginated).

    Si alguna creación falla, la excepción se propaga: el arranque de la
    aplicación debe fallar si los índices no pueden crearse.
    """
    client = get_client()
    collection = client[get_database_name()]["documents"]
    await collection.create_index(
        "checksum_sha256",
        unique=True,
        name="uq_checksum_sha256",
    )
    await collection.create_index(
        [("created_at", DESCENDING), ("_id", ASCENDING)],
        name="ix_created_at_id",
    )
