import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_document_repository
from app.domain.exceptions import PersistenceInfrastructureError
from app.domain.models import Document
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.main import create_app


@pytest.fixture
def memory_repo() -> InMemoryDocumentRepository:
    return InMemoryDocumentRepository()


@pytest.fixture
def test_app(memory_repo: InMemoryDocumentRepository) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_document_repository] = lambda: memory_repo
    return app


@pytest.fixture
async def client(test_app: FastAPI):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_create_document_success(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    request_id = "document-create-201"
    payload = {
        "checksum_sha256": "A" * 64,  # Mayúsculas: debe normalizarse a minúsculas
        "filename": "informe.pdf",
        "extracted_text": "Texto extraído secreto",
        "page_count": 3,
        "file_size_bytes": 1024,
        "metadata": {"author": "Tester"},
    }
    resp = await client.post(
        "/api/v1/documents",
        json=payload,
        headers={"X-Request-ID": request_id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["checksum_sha256"] == "a" * 64
    assert data["filename"] == "informe.pdf"
    assert data["extracted_text"] == "Texto extraído secreto"
    assert resp.headers.get("Location") == f"/api/v1/documents/{data['id']}"

    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "persistence.events"
    ]
    create_logs = [entry for entry in logs if entry["event"] == "document_created"]
    assert len(create_logs) == 1
    create_log = create_logs[0]
    assert create_log["timestamp"]
    assert create_log["level"] == "INFO"
    assert create_log["service"] == "persistence"
    assert create_log["request_id"] == request_id
    assert create_log["document_id"] == data["id"]
    assert create_log["checksum"] == "a" * 64
    assert create_log["filename"] == "informe.pdf"
    assert create_log["text_length"] == len(payload["extracted_text"])
    assert set(create_log) == {
        "timestamp",
        "level",
        "service",
        "request_id",
        "event",
        "document_id",
        "checksum",
        "filename",
        "text_length",
    }
    assert payload["extracted_text"] not in caplog.text


async def test_create_document_duplicate_returns_409_uniform_without_extracted_text(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO)
    secret_text = "CONFIDENTIAL_PAYROLL_DATA_DO_NOT_LEAK"
    request_id = "duplicate-request-409"
    payload = {
        "checksum_sha256": "c" * 64,
        "filename": "payroll.pdf",
        "extracted_text": secret_text,
    }
    resp1 = await client.post("/api/v1/documents", json=payload)
    assert resp1.status_code == 201
    created_id = resp1.json()["id"]

    # Segundo intento con el mismo checksum
    payload_dup = {
        "checksum_sha256": "C" * 64,
        "filename": "payroll_duplicate.pdf",
        "extracted_text": secret_text,
    }
    resp2 = await client.post(
        "/api/v1/documents",
        json=payload_dup,
        headers={"X-Request-ID": request_id},
    )
    assert resp2.status_code == 409
    data = resp2.json()

    assert data["error"]["code"] == "DOCUMENT_ALREADY_EXISTS"
    assert data["error"]["details"]["existing_id"] == created_id
    assert data["error"]["details"]["checksum"] == "c" * 64
    # Garantía estricta: NO debe contener el texto extraído en ningún campo del error
    assert secret_text not in resp2.text

    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "persistence.events"
    ]
    conflict_logs = [entry for entry in logs if entry["event"] == "document_conflict"]
    assert len(conflict_logs) == 1
    conflict_log = conflict_logs[0]
    assert conflict_log["service"] == "persistence"
    assert conflict_log["request_id"] == request_id
    assert conflict_log["checksum"] == "c" * 64
    assert conflict_log["document_id"] == created_id
    assert secret_text not in caplog.text


async def test_create_document_validation_errors_422(client: AsyncClient):
    # 1. Falta filename
    resp1 = await client.post(
        "/api/v1/documents",
        json={"checksum_sha256": "a" * 64, "extracted_text": "text"},
    )
    assert resp1.status_code == 422
    assert resp1.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Checksum no tiene 64 hex
    resp2 = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": "short_invalid",
            "filename": "doc.pdf",
            "extracted_text": "text",
        },
    )
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Campo desconocido (extra="forbid")
    resp3 = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": "a" * 64,
            "filename": "doc.pdf",
            "extracted_text": "text",
            "unknown_extra": "forbidden",
        },
    )
    assert resp3.status_code == 422
    assert resp3.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_get_document_by_id_success_and_not_found(client: AsyncClient):
    payload = {
        "checksum_sha256": "d" * 64,
        "filename": "search.pdf",
        "extracted_text": "Content",
    }
    create_resp = await client.post("/api/v1/documents", json=payload)
    doc_id = create_resp.json()["id"]

    # 200 OK
    resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id

    # 404 con UUID inexistente
    resp404 = await client.get("/api/v1/documents/123e4567-e89b-12d3-a456-426614174099")
    assert resp404.status_code == 404
    assert resp404.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    # 422 con formato inválido de UUID
    resp422 = await client.get("/api/v1/documents/not-a-valid-uuid")
    assert resp422.status_code == 422
    assert resp422.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_get_document_by_checksum_success_and_validation(client: AsyncClient):
    checksum = "e" * 64
    payload = {
        "checksum_sha256": checksum,
        "filename": "search_checksum.pdf",
        "extracted_text": "Content",
    }
    await client.post("/api/v1/documents", json=payload)

    # 200 OK con mayúsculas en la URL (debe normalizarse)
    resp = await client.get(f"/api/v1/documents/by-checksum/{checksum.upper()}")
    assert resp.status_code == 200
    assert resp.json()["checksum_sha256"] == checksum

    # 404 con checksum no registrado
    resp404 = await client.get(f"/api/v1/documents/by-checksum/{'f' * 64}")
    assert resp404.status_code == 404
    assert resp404.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    # 422 con formato de checksum inválido
    resp422 = await client.get("/api/v1/documents/by-checksum/short-invalid")
    assert resp422.status_code == 422
    assert resp422.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_list_documents_paginated_excludes_extracted_text(client: AsyncClient):
    for i in range(3):
        await client.post(
            "/api/v1/documents",
            json={
                "checksum_sha256": f"{i}" * 64,
                "filename": f"file_{i}.pdf",
                "extracted_text": f"SENSITIVE_TEXT_{i}",
            },
        )

    resp = await client.get("/api/v1/documents?skip=0&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # Comprobación estricta: ningún item devuelto en el listado incluye extracted_text
    for item in data["items"]:
        assert "extracted_text" not in item
        assert "filename" in item


async def test_list_documents_invalid_query_params_422(client: AsyncClient):
    # limit = 0
    resp1 = await client.get("/api/v1/documents?limit=0")
    assert resp1.status_code == 422
    assert resp1.json()["error"]["code"] == "VALIDATION_ERROR"

    # limit = 101 (> 100)
    resp2 = await client.get("/api/v1/documents?limit=101")
    assert resp2.status_code == 422
    assert resp2.json()["error"]["code"] == "VALIDATION_ERROR"

    # skip = -1
    resp3 = await client.get("/api/v1/documents?skip=-1")
    assert resp3.status_code == 422
    assert resp3.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_delete_document_success_and_not_found(client: AsyncClient):
    payload = {
        "checksum_sha256": "1" * 64,
        "filename": "delete_target.pdf",
        "extracted_text": "Text",
    }
    create_resp = await client.post("/api/v1/documents", json=payload)
    doc_id = create_resp.json()["id"]

    # DELETE 204
    del_resp = await client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 204

    # GET subsecuente -> 404
    get_resp = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 404

    # DELETE repetido -> 404
    del_again = await client.delete(f"/api/v1/documents/{doc_id}")
    assert del_again.status_code == 404
    assert del_again.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


async def test_nonexistent_route_returns_404_uniform(client: AsyncClient):
    resp = await client.get("/api/v1/completely-unknown-endpoint")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["request_id"] is not None


async def test_500_error_does_not_leak_extracted_text(
    test_app: FastAPI, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    request_id = "infrastructure-request-500"
    secret_text = "SECRET_DO_NOT_LEAK"
    connection_url = "postgresql+asyncpg://user:private-password@database:5432/private"

    # Repositorio mock que falla con error de infraestructura
    class BrokenRepository(InMemoryDocumentRepository):
        async def save(self, document: Document) -> Document:
            raise PersistenceInfrastructureError(
                f"Database crash with extracted_text={secret_text} and {connection_url}"
            )

    test_app.dependency_overrides[get_document_repository] = lambda: BrokenRepository()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents",
            json={
                "checksum_sha256": "9" * 64,
                "filename": "fail.pdf",
                "extracted_text": secret_text,
            },
            headers={"X-Request-ID": request_id},
        )
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "PERSISTENCE_INFRASTRUCTURE_ERROR"
        assert secret_text not in resp.text

    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "persistence.events"
    ]
    failure_logs = [
        entry for entry in logs if entry["event"] == "persistence_infrastructure_failure"
    ]
    assert len(failure_logs) == 1
    assert failure_logs[0]["request_id"] == request_id
    assert secret_text not in caplog.text
    assert connection_url not in caplog.text
