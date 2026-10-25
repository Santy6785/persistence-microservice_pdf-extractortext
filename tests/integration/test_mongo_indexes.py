import os

import pytest

from app.config import get_settings
from app.infrastructure.database import connection
from app.infrastructure.database.connection import ensure_indexes


@pytest.fixture(scope="class")
def mongo_container():
    """Levanta un contenedor mongo:7 efímero. Se saltea si no hay Docker/Mongo."""
    from testcontainers.community.mongodb import MongoDbContainer

    try:
        container = MongoDbContainer("mongo:7")
        container.start()
    except Exception as exc:  # noqa: BLE001 - no hay Docker o no hay Mongo
        pytest.skip(f"No se pudo levantar Mongo (¿Docker activo?): {exc}")
    yield container
    try:
        container.stop()
    except Exception:  # noqa: BLE001 - mejor esfuerzo al apagar
        pass


@pytest.fixture(autouse=True)
def mongo_env(mongo_container, monkeypatch: pytest.MonkeyPatch):
    """Setea MONGODB_URI / MONGODB_DB solo durante la prueba y revierte después."""
    monkeypatch.setenv("MONGODB_URI", mongo_container.get_connection_url())
    monkeypatch.setenv("MONGODB_DB", mongo_container.dbname)
    get_settings.cache_clear()
    monkeypatch.setattr(connection, "_client", None)


@pytest.fixture
async def clean_collection(mongo_env):
    """Limpia la colección antes y después de cada test que lo pida.

    Depende de mongo_env para asegurar que MONGODB_DB ya esté seteado.
    """
    client = connection.get_client()
    db = client[os.environ["MONGODB_DB"]]
    await db["documents"].delete_many({})
    await ensure_indexes()
    yield
    await db["documents"].delete_many({})


@pytest.mark.integration
class TestMongoIndexes:
    """Verificación de índices y ciclo de vida contra MongoDB real."""

    async def test_ensure_indexes_creates_unique_checksum_index(
        self, clean_collection
    ):
        """ensure_indexes crea el índice único uq_checksum_sha256."""
        await ensure_indexes()
        client = connection.get_client()
        collection = client[os.environ["MONGODB_DB"]]["documents"]
        cursor = await collection.list_indexes()
        indexes = await cursor.to_list()
        names = {ix["name"] for ix in indexes}
        assert "uq_checksum_sha256" in names, f"Índices: {names}"
        uq = [ix for ix in indexes if ix["name"] == "uq_checksum_sha256"][0]
        assert uq.get("unique") is True, f"Índice no único: {uq}"

    async def test_ensure_indexes_creates_order_index(self, clean_collection):
        """ensure_indexes crea el índice compuesto ix_created_at_id."""
        await ensure_indexes()
        client = connection.get_client()
        collection = client[os.environ["MONGODB_DB"]]["documents"]
        cursor = await collection.list_indexes()
        indexes = await cursor.to_list()
        names = {ix["name"] for ix in indexes}
        assert "ix_created_at_id" in names, f"Índices: {names}"
        order = [ix for ix in indexes if ix["name"] == "ix_created_at_id"][0]
        keys = order.get("key", [])
        assert list(keys.items()) == [("created_at", -1), ("_id", 1)], f"Claves inesperadas: {keys}"

    async def test_lifespan_propagates_index_failure(self, monkeypatch):
        """Si ensure_indexes falla, el lifespan propaga el error y el arranque falla."""
        import app.main as main_mod
        from app.main import lifespan

        async def _failing_ensure_indexes():
            raise RuntimeError("no se pueden crear índices")

        monkeypatch.setattr(main_mod, "ensure_indexes", _failing_ensure_indexes)

        from fastapi import FastAPI

        with pytest.raises(RuntimeError, match="no se pueden crear índices"):
            async with lifespan(FastAPI()):
                pass
