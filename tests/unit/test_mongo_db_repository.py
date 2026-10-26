import datetime as _dt

import pytest
from pymongo.errors import ConnectionFailure, DocumentTooLarge

from app.domain.exceptions import DocumentTooLargeError, PersistenceInfrastructureError
from app.domain.models import Document
from app.infrastructure.repositories.mongo import MongoDocumentRepository


class _FakeCollection:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def insert_one(self, document):
        raise self._exc


class _FakeDb:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __getitem__(self, name):
        return _FakeCollection(self._exc)


class _FakeClient:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __getitem__(self, name):
        return _FakeDb(self._exc)


def _make_fake_client(exc: Exception) -> _FakeClient:
    return _FakeClient(exc)


def _sample_document() -> Document:
    now = _dt.datetime.now(_dt.timezone.utc)
    return Document(
        id="11111111-1111-1111-1111-111111111111",
        checksum_sha256="a" * 64,
        filename="doc.pdf",
        extracted_text="Texto",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_document_too_large_raises_domain_error(monkeypatch: pytest.MonkeyPatch):
    """DocumentTooLarge de PyMongo se traduce a DocumentTooLargeError."""
    monkeypatch.setattr(
        "app.infrastructure.repositories.mongo.get_client",
        lambda: _make_fake_client(DocumentTooLarge("BSON document too large")),
    )
    repo = MongoDocumentRepository()
    with pytest.raises(DocumentTooLargeError) as exc_info:
        await repo.save(_sample_document())
    assert "16 MB" in str(exc_info.value) or "BSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_other_pymongo_error_raises_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Cualquier otro PyMongoError (no DocumentTooLarge) da PersistenceInfrastructureError."""
    monkeypatch.setattr(
        "app.infrastructure.repositories.mongo.get_client",
        lambda: _make_fake_client(ConnectionFailure("no server available")),
    )
    repo = MongoDocumentRepository()
    with pytest.raises(PersistenceInfrastructureError):
        await repo.save(_sample_document())
