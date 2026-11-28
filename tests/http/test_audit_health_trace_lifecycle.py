import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.infrastructure.database.connection as connection
from app.api.dependencies import get_document_repository
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.main import create_app, lifespan


@pytest.fixture
def audit_app() -> FastAPI:
    return create_app()


@pytest.fixture
async def audit_client(audit_app: FastAPI):
    transport = ASGITransport(app=audit_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_ready_returns_503_on_ping_timeout(
    audit_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """/health/ready devuelve 503 si ping() supera MONGODB_PING_TIMEOUT_MS."""

    class ShortTimeoutSettings:
        mongodb_ping_timeout_ms = 20

    async def slow_ping() -> bool:
        await asyncio.sleep(0.2)
        return True

    monkeypatch.setattr("app.api.health.get_settings", lambda: ShortTimeoutSettings())
    monkeypatch.setattr("app.api.health.ping", slow_ping)

    resp = await audit_client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unhealthy", "database": "disconnected"}


async def test_documents_endpoint_rejects_with_503_when_mongo_unhealthy(
    audit_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Antes de aceptar operaciones de documentos, valida Mongo healthy y devuelve 503 estándar."""

    async def unhealthy_db() -> bool:
        return False

    monkeypatch.setattr("app.api.dependencies.check_db_health", unhealthy_db)

    resp = await audit_client.get("/api/v1/documents")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "request_id" in body["error"]
    assert "timestamp" in body["error"]


async def test_trace_redacts_secrets_headers_and_payloads(
    audit_app: FastAPI, audit_client: AsyncClient
):
    """/trace redacta cabeceras sensibles, claves de secretos y extracted_text."""
    repo = InMemoryDocumentRepository()
    audit_app.dependency_overrides[get_document_repository] = lambda: repo

    payload = {
        "checksum_sha256": "a" * 64,
        "filename": "secret.pdf",
        "extracted_text": "Contenido confidencial del PDF",
        "page_count": 1,
        "file_size_bytes": 128,
        "metadata": {
            "api_key": "super-secret-key",
            "token": "jwt-token-value",
        },
    }
    headers = {
        "Authorization": "Bearer top-secret-token",
        "Cookie": "session=secret-cookie",
        "X-API-Key": "internal-key-123",
    }

    create_resp = await audit_client.post("/api/v1/documents", json=payload, headers=headers)
    assert create_resp.status_code == 201

    trace_resp = await audit_client.get("/trace")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()

    req_headers = trace_data["request"]["headers"]
    assert req_headers["authorization"] == "<redacted>"
    assert req_headers["cookie"] == "<redacted>"
    assert req_headers["x-api-key"] == "<redacted>"

    req_body = trace_data["request"]["body"]
    assert req_body["extracted_text"] == f"<redacted: {len('Contenido confidencial del PDF')} chars>"
    assert req_body["metadata"]["api_key"] == "<redacted>"
    assert req_body["metadata"]["token"] == "<redacted>"

    serialized = json.dumps(trace_data)
    assert "Contenido confidencial" not in serialized
    assert "super-secret-key" not in serialized
    assert "jwt-token-value" not in serialized
    assert "top-secret-token" not in serialized


async def test_graceful_shutdown_closes_mongo_and_logs_event(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """El cierre ordenado (lifespan/SIGTERM) cierra MongoDB y registra mongodb_client_closed."""
    caplog.set_level(logging.INFO)

    class FakeClient:
        closed = False

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def noop_indexes() -> None:
        return None

    async def close_fake() -> None:
        await fake_client.close()
        connection._client = None

    monkeypatch.setattr("app.main.get_client", lambda: fake_client)
    monkeypatch.setattr("app.main.ensure_indexes", noop_indexes)
    monkeypatch.setattr("app.main.close_client", close_fake)

    async with lifespan(FastAPI()):
        assert fake_client.closed is False

    assert fake_client.closed is True
    records = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "persistence.events"
    ]
    assert any(r["message"] == "mongodb_client_closed" for r in records)
