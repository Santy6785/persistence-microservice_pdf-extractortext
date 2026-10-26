import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app


def _docker_available() -> bool:
    """Verifica si el demonio de Docker responde (necesario para testcontainers)."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def mongo_container():
    """Levanta un contenedor mongo:7 efímero para el e2e.

    Saltea todo el módulo si no hay Docker ni Mongo alcanzable.
    """
    from testcontainers.community.mongodb import MongoDbContainer

    if not _docker_available():
        pytest.skip("Docker no disponible; se salta el e2e de Mongo hasta haber mongo:7")
    try:
        container = MongoDbContainer("mongo:7")
        container.start()
    except Exception as exc:  # noqa: BLE001 - no hay Mongo alcanzable
        pytest.skip(f"No se pudo levantar Mongo (¿Docker activo?): {exc}")
    yield container
    try:
        container.stop()
    except Exception:  # noqa: BLE001 - mejor esfuerzo al apagar
        pass


@pytest.fixture(autouse=True)
def mongo_env(mongo_container, monkeypatch: pytest.MonkeyPatch):
    """Apunta la app al contenedor Mongo y limpia el cache de settings."""
    monkeypatch.setenv("MONGODB_URI", mongo_container.get_connection_url())
    monkeypatch.setenv("MONGODB_DB", mongo_container.dbname)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def clean_collection(mongo_env):
    """Limpia la colección antes y después de cada test.

    Depende de mongo_env para asegurar que MONGODB_DB ya esté seteado.
    """
    from app.infrastructure.database import connection

    client = connection.get_client()
    db = client[os.environ["MONGODB_DB"]]
    await db["documents"].delete_many({})
    yield
    await db["documents"].delete_many({})


@pytest.fixture(scope="module")
async def client():
    """Cliente HTTP de la app real conectada a Mongo real."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.integration
async def test_e2e_mongo_crud(client: AsyncClient):
    """Ciclo de vida completo contra Mongo real: health, crear, obtener,
    listar, duplicado 409 y borrar."""
    # A. Healthchecks operativos
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
        "extracted_text": "Texto extraído en test E2E contra Mongo real",
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
    assert doc_data["extracted_text"] == payload["extracted_text"]
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
    # Validar que extracted_text NO se expone en el listado (proyección)
    for item in list_data["items"]:
        assert "extracted_text" not in item
        assert "filename" in item

    # F. Detectar duplicado con 409 y formato uniforme (sin extracted_text)
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
