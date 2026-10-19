from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.api.error_handlers import build_error_payload
from app.api.schemas import (
    DocumentCreateRequest,
    DocumentSummaryResponse,
    ErrorEnvelope,
)
from app.domain.models import Document


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
