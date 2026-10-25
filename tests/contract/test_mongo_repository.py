import os

import pytest

from app.config import get_settings
from app.infrastructure.database import connection
from app.infrastructure.database.connection import ensure_indexes
from app.infrastructure.repositories.mongo import MongoDocumentRepository
from tests.contract.test_repository_contract import BaseDocumentRepositoryContractTest


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
    """Setea MONGODB_URI / MONGODB_DB solo durante la prueba y revierte después.

    Además invalida el cache de get_settings() y resetea el cliente singleton
    de MongoDB para que se cree en el event loop del test actual (pytest-asyncio
    usa un loop distinto por test, y AsyncMongoClient se vincula a un solo loop).
    """
    monkeypatch.setenv("MONGODB_URI", mongo_container.get_connection_url())
    monkeypatch.setenv("MONGODB_DB", mongo_container.dbname)
    get_settings.cache_clear()
    monkeypatch.setattr(connection, "_client", None)


@pytest.fixture(autouse=True)
async def clean_collection(mongo_env):
    """Limpia la colección antes y después de cada test.

    Depende de mongo_env para asegurar que MONGODB_DB ya esté seteado.
    """
    client = connection.get_client()
    db = client[os.environ["MONGODB_DB"]]
    await db["documents"].delete_many({})
    await ensure_indexes()
    yield
    await db["documents"].delete_many({})


@pytest.mark.integration
class TestMongoDocumentRepository(BaseDocumentRepositoryContractTest):
    """Ejecución de la suite de contrato contra MongoDB real (contenedor efímero)."""

    async def get_repository(self) -> MongoDocumentRepository:
        return MongoDocumentRepository()
