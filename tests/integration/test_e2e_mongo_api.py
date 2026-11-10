"""
Pruebas de integración contra MongoDB real usando testcontainers.

Todos los tests están decorados con @pytest.mark.integration y requieren
Docker disponible. Se ejecutan con:

    uv run pytest -m integration
"""

import uuid

import pytest
from httpx import AsyncClient


_CHECKSUM_A = "a" * 64
_CHECKSUM_B = "b" * 64
_CHECKSUM_C = "c" * 64
_CHECKSUM_E = "e" * 64


# ---------------------------------------------------------------------------
# Caso 1: Insertar y leer por ID, por checksum, listado paginado
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_insert_and_read_by_id_and_checksum_and_paginated(client: AsyncClient):
    """Insertar un documento y leerlo por ID, por checksum y verificar el listado paginado."""
    payload = {
        "checksum_sha256": _CHECKSUM_A,
        "filename": "invoice.pdf",
        "extracted_text": "Factura número 12345",
        "page_count": 2,
        "file_size_bytes": 2048,
        "metadata": {"source": "test", "type": "invoice"},
    }

    # Crear documento
    create_resp = await client.post("/api/v1/documents", json=payload)
    assert create_resp.status_code == 201
    doc = create_resp.json()
    doc_id = doc["id"]
    assert doc["checksum_sha256"] == _CHECKSUM_A
    assert doc["filename"] == "invoice.pdf"
    assert doc["extracted_text"] == "Factura número 12345"
    assert doc["page_count"] == 2
    assert doc["file_size_bytes"] == 2048
    assert doc["metadata"] == {"source": "test", "type": "invoice"}
    assert "created_at" in doc
    assert "updated_at" in doc
    # Cabecera Location apunta al recurso creado
    assert create_resp.headers.get("Location") == f"/api/v1/documents/{doc_id}"

    # Leer por ID
    get_id_resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_id_resp.status_code == 200
    assert get_id_resp.json()["id"] == doc_id
    assert get_id_resp.json()["checksum_sha256"] == _CHECKSUM_A
    assert uuid.UUID(doc_id)  # valida que es un UUID válido

    # Leer por checksum
    get_chk_resp = await client.get(f"/api/v1/documents/by-checksum/{_CHECKSUM_A}")
    assert get_chk_resp.status_code == 200
    assert get_chk_resp.json()["id"] == doc_id
    assert get_chk_resp.json()["filename"] == "invoice.pdf"

    # Listado paginado
    list_resp = await client.get("/api/v1/documents?skip=0&limit=10")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert list_data["skip"] == 0
    assert list_data["limit"] == 10
    assert any(item["id"] == doc_id for item in list_data["items"])
    # extracted_text NO se expone en el listado (proyección)
    for item in list_data["items"]:
        assert "extracted_text" not in item
        assert "filename" in item
        assert "checksum_sha256" in item


# ---------------------------------------------------------------------------
# Caso 2: Duplicado por checksum → 409 Conflict
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_duplicate_checksum_returns_409(client: AsyncClient):
    """Insertar un documento duplicado por checksum y validar que retorna 409 Conflict."""
    payload = {
        "checksum_sha256": _CHECKSUM_B,
        "filename": "report.pdf",
        "extracted_text": "Contenido del reporte",
        "page_count": 3,
        "metadata": {"env": "test"},
    }

    # Primera inserción
    create_resp = await client.post("/api/v1/documents", json=payload)
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    # Inserción duplicada (mismo checksum)
    dup_resp = await client.post("/api/v1/documents", json=payload)
    assert dup_resp.status_code == 409
    dup_data = dup_resp.json()
    assert dup_data["error"]["code"] == "DOCUMENT_ALREADY_EXISTS"
    assert dup_data["error"]["details"]["existing_id"] == doc_id
    assert dup_data["error"]["details"]["checksum"] == _CHECKSUM_B
    # extracted_text no se filtra en el error 409
    assert "Contenido del reporte" not in dup_resp.text


# ---------------------------------------------------------------------------
# Caso 3: PATCH sobre campos editables y rechazo de inmutables
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_patch_editable_fields_and_reject_immutable(client: AsyncClient):
    """PATCH sobre campos editables (filename, metadata) y rechazo de inmutables."""
    payload = {
        "checksum_sha256": _CHECKSUM_C,
        "filename": "original.pdf",
        "extracted_text": "Texto original",
        "page_count": 1,
        "metadata": {"version": 1},
    }
    create_resp = await client.post("/api/v1/documents", json=payload)
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    # PATCH con campos editables (filename y metadata)
    patch_resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"filename": "renamed.pdf", "metadata": {"version": 2, "tag": "updated"}},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["id"] == doc_id
    assert updated["filename"] == "renamed.pdf"
    assert updated["metadata"] == {"version": 2, "tag": "updated"}
    # Los inmutables no cambian
    assert updated["checksum_sha256"] == _CHECKSUM_C
    assert updated["extracted_text"] == "Texto original"
    assert updated["page_count"] == 1

    # PATCH solo con filename
    patch_filename_resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"filename": "solo_nombre.pdf"},
    )
    assert patch_filename_resp.status_code == 200
    assert patch_filename_resp.json()["filename"] == "solo_nombre.pdf"

    # PATCH solo con metadata
    patch_meta_resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"metadata": {"only_meta": True}},
    )
    assert patch_meta_resp.status_code == 200
    assert patch_meta_resp.json()["metadata"] == {"only_meta": True}

    # PATCH con campo inmutable (checksum_sha256) → 422 por extra_forbid
    immutable_resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={"checksum_sha256": "d" * 64},
    )
    assert immutable_resp.status_code == 422

    # PATCH con cuerpo vacío → 422 (validación de modelo)
    empty_resp = await client.patch(
        f"/api/v1/documents/{doc_id}",
        json={},
    )
    assert empty_resp.status_code == 422


# ---------------------------------------------------------------------------
# Caso 4: Eliminar (204) y luego buscar de nuevo (404)
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_delete_document_then_404(client: AsyncClient):
    """Eliminar un documento (204 No Content) y luego buscarlo de nuevo (404 Not Found)."""
    payload = {
        "checksum_sha256": _CHECKSUM_E,
        "filename": "temp.pdf",
        "extracted_text": "Documento temporal",
        "page_count": 1,
    }
    create_resp = await client.post("/api/v1/documents", json=payload)
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    # Eliminar documento
    del_resp = await client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 204
    assert del_resp.content == b""  # 204 no tiene cuerpo

    # Buscar de nuevo → 404
    get_resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 404
    assert get_resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
    assert get_resp.json()["error"]["details"]["document_id"] == doc_id

    # Buscar por checksum también → 404
    get_chk_resp = await client.get(f"/api/v1/documents/by-checksum/{_CHECKSUM_E}")
    assert get_chk_resp.status_code == 404
    assert get_chk_resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Caso 5: Fallo de conexión a la base de datos → 503 Service Unavailable
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_database_failure_returns_503(failing_client: AsyncClient):
    """Simular un fallo de conexión a la base de datos y validar 503 Service Unavailable.

    El fixture failing_client sobrescribe el repositorio para que todas las
    operaciones lancen PersistenceInfrastructureError, que el handler global
    mapea a 503 con código SERVICE_UNAVAILABLE sin exponer detalles internos.
    """
    # Listar documentos falla porque el repositorio simulado siempre falla
    resp = await failing_client.get("/api/v1/documents")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["message"] == "A database or infrastructure failure occurred."
    assert body["error"]["details"] == {}
    assert body["error"]["request_id"]
    assert body["error"]["timestamp"]

    # Crear documento también falla con 503
    create_resp = await failing_client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": "f" * 64,
            "filename": "fail.pdf",
            "extracted_text": "no se guardará",
        },
    )
    assert create_resp.status_code == 503
    assert create_resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
