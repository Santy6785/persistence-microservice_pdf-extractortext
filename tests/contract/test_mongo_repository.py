import os

import pytest

from app.infrastructure.repositories.mongo import MongoDocumentRepository
from tests.contract.test_repository_contract import BaseDocumentRepositoryContractTest


def _docker_available() -> bool:
    """Verifica si el demonio de Docker responde (necesario para testcontainers)."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


if not _docker_available():
    pytest.skip(
        "Docker no está disponible; se salta el contrato contra Mongo hasta que "
        "haya un contenedor mongo:7 levantable.",
        allow_module_level=True,
    )


@pytest.mark.integration
class TestMongoDocumentRepository(BaseDocumentRepositoryContractTest):
    """Ejecución de la suite de contrato contra MongoDB real (contenedor efímero)."""

    _container = None
    _client = None

    @classmethod
    def setup_class(cls):
        import asyncio

        from pymongo import AsyncMongoClient
        from testcontainers.community.mongodb import MongoDbContainer

        cls._container = MongoDbContainer("mongo:7")
        cls._container.start()

        uri = cls._container.get_connection_url()
        db_name = cls._container.dbname

        os.environ["MONGODB_URI"] = uri
        os.environ["MONGODB_DB"] = db_name

        async def _init() -> None:
            cls._client = AsyncMongoClient(
                uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=20000,
            )
            # Forzar conexión para validar disponibilidad antes de los tests.
            await cls._client.admin.command("ping")

        asyncio.run(_init())

    @classmethod
    def teardown_class(cls):
        import asyncio

        if cls._client:
            asyncio.run(cls._client.close())
        if cls._container:
            cls._container.stop()

    @pytest.fixture(autouse=True)
    async def clean_collection(self):
        db_name = os.environ.get("MONGODB_DB", "persistence_db")
        db = self._client[db_name]
        await db["documents"].delete_many({})
        yield
        await db["documents"].delete_many({})

    async def get_repository(self) -> MongoDocumentRepository:
        return MongoDocumentRepository()
