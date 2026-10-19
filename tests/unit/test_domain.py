from datetime import datetime, timezone
import pytest
from app.domain.models import Document
from app.domain.exceptions import (
    DomainError,
    DocumentNotFoundError,
    DocumentAlreadyExistsError,
    PersistenceInfrastructureError,
)


def test_document_creation_valid():
    now = datetime.now(timezone.utc)
    doc = Document(
        id="123e4567-e89b-12d3-a456-426614174000",
        checksum_sha256="a" * 64,
        filename="test.pdf",
        extracted_text="Some extracted text",
        created_at=now,
        updated_at=now,
        page_count=3,
        file_size_bytes=1024,
        metadata={"author": "Test Author"},
    )
    assert doc.id == "123e4567-e89b-12d3-a456-426614174000"
    assert doc.checksum_sha256 == "a" * 64
    assert doc.page_count == 3
    assert doc.metadata["author"] == "Test Author"


def test_document_invalid_checksum_raises_value_error():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="Checksum must be a 64-character hexadecimal string"):
        Document(
            id="123e4567-e89b-12d3-a456-426614174000",
            checksum_sha256="invalid_checksum",
            filename="test.pdf",
            extracted_text="Text",
            created_at=now,
            updated_at=now,
        )


def test_document_negative_page_count_raises_value_error():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="page_count must be non-negative"):
        Document(
            id="123e4567-e89b-12d3-a456-426614174000",
            checksum_sha256="a" * 64,
            filename="test.pdf",
            extracted_text="Text",
            created_at=now,
            updated_at=now,
            page_count=-1,
        )


def test_domain_exceptions_attributes():
    not_found = DocumentNotFoundError(document_id="doc-123")
    assert isinstance(not_found, DomainError)
    assert not_found.document_id == "doc-123"
    assert "doc-123" in str(not_found)

    exists = DocumentAlreadyExistsError(checksum="abc", existing_id="doc-existing")
    assert isinstance(exists, DomainError)
    assert exists.checksum == "abc"
    assert exists.existing_id == "doc-existing"

    infra_err = PersistenceInfrastructureError("DB connection lost")
    assert isinstance(infra_err, DomainError)
    assert "DB connection lost" in str(infra_err)
