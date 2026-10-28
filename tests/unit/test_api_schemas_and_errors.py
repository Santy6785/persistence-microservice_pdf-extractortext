import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api.error_handlers import (
    build_error_payload,
    persistence_infrastructure_handler,
    unhandled_exception_handler,
)
from app.api.schemas import (
    DocumentCreateRequest,
    DocumentSummaryResponse,
    ErrorEnvelope,
)
from app.domain.exceptions import PersistenceInfrastructureError
from app.domain.models import Document


class _FakeRequest(Request):
    """Request mínimo para probar handlers sin ASGI."""

    def __init__(self, request_id: str = "req-unit") -> None:
        super().__init__({"type": "http", "state": {}})
        self.state.request_id = request_id


def test_document_create_request_valid_and_checksum_normalized():
    raw_checksum = "A" * 64
    req = DocumentCreateRequest(
        checksum_sha256=raw_checksum,
        filename="test.pdf",
        extracted_text="Contenido",
        page_count=2,
        file_size_bytes=100,
        metadata={"key": "val"},
    )
    # Checksum debe normalizarse a minúsculas
    assert req.checksum_sha256 == "a" * 64
    assert req.filename == "test.pdf"
    assert req.page_count == 2


def test_document_create_request_extra_fields_forbidden():
    with pytest.raises(ValidationError) as exc_info:
        DocumentCreateRequest(
            checksum_sha256="a" * 64,
            filename="test.pdf",
            extracted_text="Contenido",
            extra_field="malicious_or_unknown",
        )
    errors = exc_info.value.errors()
    assert any(err["type"] == "extra_forbidden" for err in errors)


def test_document_create_request_invalid_checksum():
    with pytest.raises(ValidationError):
        DocumentCreateRequest(
            checksum_sha256="not-hex-and-not-64-chars",
            filename="test.pdf",
            extracted_text="Contenido",
        )


def test_document_summary_response_excludes_extracted_text():
    now = datetime.now(timezone.utc)
    doc = Document(
        id="123e4567-e89b-12d3-a456-426614174000",
        checksum_sha256="b" * 64,
        filename="doc.pdf",
        extracted_text="MUCHO_TEXTO_CONFIDENCIAL",
        created_at=now,
        updated_at=now,
        page_count=10,
        file_size_bytes=5000,
    )
    summary = DocumentSummaryResponse.from_entity(doc)
    summary_dict = summary.model_dump()
    assert "extracted_text" not in summary_dict
    assert summary.id == doc.id
    assert summary.filename == "doc.pdf"


def test_build_error_payload_structure():
    payload = build_error_payload(
        code="VALIDATION_ERROR",
        message="Invalid input",
        details={"field": "missing"},
        request_id="req-123",
    )
    envelope = ErrorEnvelope.model_validate(payload)
    assert envelope.error.code == "VALIDATION_ERROR"
    assert envelope.error.message == "Invalid input"
    assert envelope.error.details == {"field": "missing"}
    assert envelope.error.request_id == "req-123"
    assert envelope.error.timestamp is not None


async def test_persistence_infrastructure_handler_returns_503_service_unavailable():
    """PersistenceInfrastructureError → 503 SERVICE_UNAVAILABLE, sin filtrar extracted_text."""
    secret_text = "SECRETO_NO_DEBE_FILTRARSE"
    exc = PersistenceInfrastructureError(
        f"se cayó la base de datos con extracted_text={secret_text}"
    )
    response = await persistence_infrastructure_handler(_FakeRequest("req-503"), exc)

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert body["error"]["message"] == "A database or infrastructure failure occurred."
    assert body["error"]["details"] == {}
    assert body["error"]["request_id"] == "req-503"
    assert body["error"]["timestamp"]
    assert secret_text not in response.body.decode()


async def test_unhandled_exception_handler_returns_500_internal_server_error():
    """Una excepción no prevista → 500 INTERNAL_SERVER_ERROR, sin filtrar datos sensibles."""
    secret_text = "SECRETO_NO_DEBE_FILTRARSE"
    exc = RuntimeError(f"algo totalmente inesperado con {secret_text}")
    response = await unhandled_exception_handler(_FakeRequest("req-500"), exc)

    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert body["error"]["message"] == "An unexpected internal server error occurred."
    assert body["error"]["details"] == {}
    assert body["error"]["request_id"] == "req-500"
    assert body["error"]["timestamp"]
    assert secret_text not in response.body.decode()
