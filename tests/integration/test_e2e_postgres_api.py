import os
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from alembic.config import Config
from app.main import create_app
from app.config import Settings
from app.api.dependencies import _engine, _session_factory
import app.api.dependencies as deps


def is_docker_available() -> bool:
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
async def test_alembic_and_e2e_real_postgres():
    """
    Test de integración punta a punta:
    1. Ejecuta 'alembic upgrade head' contra PostgreSQL 16 real en Docker.
    2. Levanta la app FastAPI real conectada a dicha base.
    3. Valida el ciclo completo de vida: health, crear, obtener, listar, duplicado 409 y borrar.
    """
    with PostgresContainer("postgres:16-alpine") as postgres:
        raw_url = postgres.get_connection_url()
        if raw_url.startswith("postgresql+psycopg2://"):
            async_url = raw_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://", 1
            )
        elif raw_url.startswith("postgresql://"):
            async_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        else:
            async_url = raw_url

        # 1. Ejecutar migraciones de Alembic en thread aislado
        import asyncio
        os.environ["DATABASE_URL"] = async_url
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", async_url)
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

        # 2. Configurar motor para la app de prueba con NullPool
        test_engine = create_async_engine(async_url, poolclass=NullPool)
        test_session_factory = deps.create_session_factory(test_engine)

        deps._engine = test_engine
        deps._session_factory = test_session_factory

        app = create_app()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # A. Validar Healthchecks operativos
            live_resp = await client.get("/health/live")
            assert live_resp.status_code == 200
            assert live_resp.json() == {"status": "alive"}

            ready_resp = await client.get("/health/ready")
            assert ready_resp.status_code == 200
            assert ready_resp.json() == {"status": "ready", "database": "connected"}

            # B. Crear documento nuevo (POST /api/v1/documents)
            payload = {
                "checksum_sha256": "B" * 64,  # Mayúsculas: prueba normalización
                "filename": "e2e_report.pdf",
                "extracted_text": "Texto extraído en test E2E contra Postgres real",
                "page_count": 4,
                "file_size_bytes": 4096,
                "metadata": {"env": "test_e2e", "system": "persistence"},
            }
            create_resp = await client.post("/api/v1/documents", json=payload)
            assert create_resp.status_code == 201
            doc_data = create_resp.json()
            doc_id = doc_data["id"]
            expected_checksum = "b" * 64
            assert doc_data["checksum_sha256"] == expected_checksum
            assert doc_data["filename"] == "e2e_report.pdf"
            assert create_resp.headers.get("Location") == f"/api/v1/documents/{doc_id}"

            # C. Obtener por ID (GET /api/v1/documents/{id})
            get_id_resp = await client.get(f"/api/v1/documents/{doc_id}")
            assert get_id_resp.status_code == 200
            assert get_id_resp.json()["id"] == doc_id
            assert get_id_resp.json()["metadata"]["system"] == "persistence"

            # D. Obtener por Checksum (GET /api/v1/documents/by-checksum/{checksum})
            get_chk_resp = await client.get(f"/api/v1/documents/by-checksum/{expected_checksum}")
            assert get_chk_resp.status_code == 200
            assert get_chk_resp.json()["id"] == doc_id

            # E. Listar documentos (GET /api/v1/documents)
            list_resp = await client.get("/api/v1/documents?skip=0&limit=10")
            assert list_resp.status_code == 200
            list_data = list_resp.json()
            assert list_data["total"] >= 1
            # Validar que extracted_text NO se expone en el listado
            for item in list_data["items"]:
                assert "extracted_text" not in item
                assert "filename" in item

            # F. Detectar duplicado con 409 y formato uniforme
            dup_resp = await client.post("/api/v1/documents", json=payload)
            assert dup_resp.status_code == 409
            dup_data = dup_resp.json()
            assert dup_data["error"]["code"] == "DOCUMENT_ALREADY_EXISTS"
            assert dup_data["error"]["details"]["existing_id"] == doc_id
            assert dup_data["error"]["details"]["checksum"] == expected_checksum
            assert "Texto extraído en test E2E" not in dup_resp.text

            # G. Eliminar documento (DELETE /api/v1/documents/{id})
            del_resp = await client.delete(f"/api/v1/documents/{doc_id}")
            assert del_resp.status_code == 204

            # H. Confirmar que ya no existe (404 uniforme)
            not_found_resp = await client.get(f"/api/v1/documents/{doc_id}")
            assert not_found_resp.status_code == 404
            assert not_found_resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

        await test_engine.dispose()
        deps._engine = None
        deps._session_factory = None
