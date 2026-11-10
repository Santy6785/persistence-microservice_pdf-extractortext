"""Fixtures globales de la suite de tests.

Incluye el fixture de logging existente (aislamiento entre tests) y los
fixtures de integración que levantan MongoDB mediante testcontainers,
apuntan la app al contenedor efímero y sobrescriben la inyección de
dependencias de FastAPI para usar ese contenedor.
"""

import logging
import os
import time

import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

import app.api.dependencies as dependencies_module
from app.config import get_settings
from app.domain.exceptions import PersistenceInfrastructureError
from app.infrastructure.database import connection
from app.main import create_app
from app.observability import EVENT_LOGGER


# ---------------------------------------------------------------------------
# Fixture existente: aislamiento de logging entre tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_test_logging_state():
    """Aísla el estado de logging entre tests.

    Limpia el cache de get_settings() para que configure_logging() re-lea
    las variables de entorno, y resetea EVENT_LOGGER a un estado conocido
    (nivel DEBUG, sin handlers extra) para evitar que un test file previo
    (p. ej. test_log_level_ciclo4.py con LOG_LEVEL=error) deje el nivel
    en ERROR y filtre los logs INFO de los tests de otros archivos.
    """
    original_level = EVENT_LOGGER.level
    original_propagate = EVENT_LOGGER.propagate
    original_handlers = list(EVENT_LOGGER.handlers)

    get_settings.cache_clear()

    EVENT_LOGGER.setLevel(logging.DEBUG)
    EVENT_LOGGER.propagate = True
    for h in list(EVENT_LOGGER.handlers):
        EVENT_LOGGER.removeHandler(h)

    yield

    EVENT_LOGGER.setLevel(original_level)
    EVENT_LOGGER.propagate = original_propagate
    for h in list(EVENT_LOGGER.handlers):
        EVENT_LOGGER.removeHandler(h)
    for h in original_handlers:
        EVENT_LOGGER.addHandler(h)


# ---------------------------------------------------------------------------
# Helpers de testcontainers / MongoDB
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    """Verifica si el demonio de Docker responde (necesario para testcontainers)."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _wait_for_mongo(uri: str, timeout_s: float = 30.0) -> None:
    """Espera hasta que mongod responda al ping (máximo timeout_s segundos).

    testcontainers levanta el contenedor pero mongod puede tardar unos
    segundos en aceptar conexiones. Sin esta espera, el primer test de
    la suite falla con ServerSelectionTimeoutError.
    """
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        try:
            client = MongoClient(
                uri,
                serverSelectionTimeoutMS=1000,
                connectTimeoutMS=1000,
            )
            try:
                client.admin.command("ping")
                return
            finally:
                client.close()
        except PyMongoError as exc:  # noqa: BLE001 - reintentar hasta timeout
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"MongoDB no estuvo listo en {timeout_s}s: {last_error}")


# ---------------------------------------------------------------------------
# Fixtures de integración (MongoDB real vía testcontainers)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mongo_container():
    """Levanta un contenedor mongo:7 efímero para toda la sesión de tests de integración.

    Se saltea si no hay Docker disponible.
    """
    from testcontainers.community.mongodb import MongoDbContainer

    if not _docker_available():
        pytest.skip("Docker no disponible; se salta los tests de integración de MongoDB")
    try:
        container = MongoDbContainer("mongo:7")
        container.start()
        _wait_for_mongo(container.get_connection_url())
    except Exception as exc:  # noqa: BLE001 - no hay Mongo alcanzable
        pytest.skip(f"No se pudo levantar Mongo (¿Docker activo?): {exc}")
    yield container
    try:
        container.stop()
    except Exception:  # noqa: BLE001 - mejor esfuerzo al apagar
        pass


@pytest.fixture
def mongo_env(mongo_container, monkeypatch: pytest.MonkeyPatch):
    """Apunta la app al contenedor Mongo y limpia el cache de settings y los clientes singleton.

    Setea MONGODB_URI y MONGODB_DB con los valores del contenedor efímero,
    limpia el cache de get_settings() y resetea los clientes singleton de
    connection.py y dependencies.py para que se reconecten al contenedor.
    """
    monkeypatch.setenv("MONGODB_URI", mongo_container.get_connection_url())
    monkeypatch.setenv("MONGODB_DB", mongo_container.dbname)
    get_settings.cache_clear()
    connection._client = None
    dependencies_module._client = None


@pytest.fixture
async def clean_collection(mongo_env):
    """Limpia la colección antes y después de cada test de integración.

    Depende de mongo_env para asegurar que MONGODB_DB ya esté seteado y el
    cliente apunte al contenedor efímero.
    """
    client = connection.get_client()
    db = client[os.environ["MONGODB_DB"]]
    await db["documents"].delete_many({})
    await connection.ensure_indexes()
    yield
    await db["documents"].delete_many({})


@pytest.fixture
async def client(clean_collection):
    """Cliente HTTP de la app real conectada a Mongo real (testcontainers).

    Sobreescribe la inyección de dependencias del repositorio
    (get_document_repository) para usar MongoDocumentRepository conectado al
    contenedor efímero. Cada test recibe una app nueva con un cliente HTTP
    aislado.
    """
    from app.api.dependencies import get_document_repository
    from app.infrastructure.repositories.mongo import MongoDocumentRepository

    app = create_app()

    async def _override_repository():
        return MongoDocumentRepository()

    app.dependency_overrides[get_document_repository] = _override_repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def failing_client(mongo_env):
    """Cliente HTTP con el repositorio sobrescrito para simular fallo de DB (503).

    El repositorio simulado lanza PersistenceInfrastructureError en todas sus
    operaciones, por lo que cualquier endpoint que acceda a datos retorna
    503 Service Unavailable.
    """
    from app.api.dependencies import get_document_repository

    app = create_app()

    async def _override_repository():
        return _FailingRepository()

    app.dependency_overrides[get_document_repository] = _override_repository

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class _FailingRepository:
    """Repositorio simulado que siempre lanza PersistenceInfrastructureError.

    Se usa únicamente en failing_client para reproducir un fallo de conexión
    a la base de datos y validar que la API retorna 503.
    """

    async def save(self, document):  # noqa: ARG002
        raise PersistenceInfrastructureError("conexión a MongoDB fallida")

    async def find_by_id(self, document_id):  # noqa: ARG002
        raise PersistenceInfrastructureError("conexión a MongoDB fallida")

    async def find_by_checksum(self, checksum):  # noqa: ARG002
        raise PersistenceInfrastructureError("conexión a MongoDB fallida")

    async def list_paginated(self, skip=0, limit=20):  # noqa: ARG002
        raise PersistenceInfrastructureError("conexión a MongoDB fallida")

    async def delete(self, document_id):  # noqa: ARG002
        raise PersistenceInfrastructureError("conexión a MongoDB fallida")

    async def update(self, document_id, filename=None, metadata=None):  # noqa: ARG002
        raise PersistenceInfrastructureError("conexión a MongoDB fallida")



