import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.infrastructure.database.models import Base
from app.infrastructure.database.connection import create_session_factory
from app.infrastructure.repositories.postgres import PostgresDocumentRepository
from app.domain.exceptions import PersistenceInfrastructureError
from tests.contract.test_repository_contract import BaseDocumentRepositoryContractTest


def is_docker_available() -> bool:
    """Verifica si el demonio de Docker está disponible y responde."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


if not is_docker_available():
    pytest.skip(
        "Docker no está disponible en este entorno; se saltan los tests de integración.",
        allow_module_level=True,
    )

try:
    from testcontainers.community.postgres import PostgresContainer
except ImportError:
    from testcontainers.postgres import PostgresContainer  # fallback


@pytest.mark.integration
class TestPostgresDocumentRepository(BaseDocumentRepositoryContractTest):
    """Ejecución de la suite completa de contrato contra un PostgreSQL 16 real usando Testcontainers."""

    _container = None
    _async_url = None

    @classmethod
    def setup_class(cls):
        cls._container = PostgresContainer("postgres:16-alpine")
        cls._container.start()

        raw_url = cls._container.get_connection_url()
        if raw_url.startswith("postgresql+psycopg2://"):
            cls._async_url = raw_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://", 1
            )
        elif raw_url.startswith("postgresql://"):
            cls._async_url = raw_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        else:
            cls._async_url = raw_url

    @classmethod
    def teardown_class(cls):
        if cls._container:
            cls._container.stop()

    @pytest.fixture(autouse=True)
    async def setup_repo_for_test(self):
        # Usamos NullPool para aislar conexiones al event loop del test en Windows
        engine = create_async_engine(self._async_url, poolclass=NullPool)
        session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("TRUNCATE TABLE documents;"))

        self._repo = PostgresDocumentRepository(session_factory=session_factory)
        yield
        await engine.dispose()

    async def get_repository(self) -> PostgresDocumentRepository:
        return self._repo

    async def test_infrastructure_error_is_raised_never_swallowed(self):
        """Verifica que un fallo de infraestructura eleva PersistenceInfrastructureError y nunca devuelve None o False."""
        broken_engine = create_async_engine(
            "postgresql+asyncpg://invalid:invalid@127.0.0.1:59999/broken",
            poolclass=NullPool,
        )
        broken_session_factory = create_session_factory(broken_engine)
        broken_repo = PostgresDocumentRepository(session_factory=broken_session_factory)

        try:
            with pytest.raises(PersistenceInfrastructureError):
                await broken_repo.find_by_id("any-id")

            with pytest.raises(PersistenceInfrastructureError):
                await broken_repo.delete("any-id")

            with pytest.raises(PersistenceInfrastructureError):
                await broken_repo.find_by_checksum("a" * 64)

            with pytest.raises(PersistenceInfrastructureError):
                await broken_repo.list_paginated()
        finally:
            await broken_engine.dispose()
