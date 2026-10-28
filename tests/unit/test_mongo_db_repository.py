import asyncio
import datetime as _dt
import time

import pytest
from pymongo.errors import ConnectionFailure, DocumentTooLarge

from app.config import Settings
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


class _SlowCollection:
    """Colección falsa cuya cada operación se duerme más allá del timeout de operación."""

    async def insert_one(self, document):
        await asyncio.sleep(5)

    async def find_one(self, filter):
        await asyncio.sleep(5)

    async def count_documents(self, filter):
        await asyncio.sleep(5)

    async def delete_one(self, filter):
        await asyncio.sleep(5)


class _SlowDb:
    def __getitem__(self, name):
        return _SlowCollection()


class _SlowClient:
    def __getitem__(self, name):
        return _SlowDb()


def _make_slow_client() -> _SlowClient:
    return _SlowClient()


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


@pytest.mark.asyncio
async def test_operation_exceeding_timeout_raises_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Una operación de datos que excede MONGODB_OPERATION_TIMEOUT_MS lanza
    PersistenceInfrastructureError y la operación no queda colgada esperando a MongoDB."""
    # 100 ms de operación vs 50 ms de selección de servidor: válido (> serverSelection).
    settings = Settings(
        mongodb_operation_timeout_ms=100,
        mongodb_server_selection_timeout_ms=50,
    )
    monkeypatch.setattr(
        "app.infrastructure.repositories.mongo.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.infrastructure.repositories.mongo.get_client",
        lambda: _make_slow_client(),
    )
    repo = MongoDocumentRepository()

    start = time.monotonic()
    with pytest.raises(PersistenceInfrastructureError) as exc_info:
        await repo.save(_sample_document())
    elapsed = time.monotonic() - start

    # La operación falla rápido por timeout; no se queda colgada los 5 s del fake.
    assert elapsed < 2
    assert "timeout" in str(exc_info.value).lower()
