from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.exceptions import DocumentAlreadyExistsError
from app.domain.models import Document
from app.domain.repositories import DocumentRepository


class BaseDocumentRepositoryContractTest(ABC):
    """Batería común de tests para verificar el cumplimiento del contrato DocumentRepository."""

    @abstractmethod
    async def get_repository(self) -> DocumentRepository:
        """Fixture abstracta que debe proveer la instancia del repositorio a probar."""
        pass

    def _create_sample_document(
        self,
        doc_id: str,
        checksum: str,
        created_at: datetime | None = None,
        filename: str = "doc.pdf",
    ) -> Document:
        now = created_at or datetime.now(timezone.utc)
        return Document(
            id=doc_id,
            checksum_sha256=checksum,
            filename=filename,
            extracted_text="Contenido de prueba",
            created_at=now,
            updated_at=now,
            page_count=1,
            file_size_bytes=100,
            metadata={"source": "test"},
        )

    async def test_save_and_find_by_id(self):
        repo = await self.get_repository()
        doc = self._create_sample_document(
            doc_id="11111111-1111-1111-1111-111111111111",
            checksum="a" * 64,
        )

        saved = await repo.save(doc)
        assert saved.id == doc.id

        found = await repo.find_by_id(doc.id)
        assert found is not None
        assert found.id == doc.id
        assert found.checksum_sha256 == doc.checksum_sha256
        assert found.filename == doc.filename
        assert found.extracted_text == doc.extracted_text
        assert found.metadata == {"source": "test"}

    async def test_find_by_id_not_found_returns_none(self):
        repo = await self.get_repository()
        found = await repo.find_by_id("non-existent-id")
        assert found is None

    async def test_find_by_checksum_success_and_not_found(self):
        repo = await self.get_repository()
        checksum = "b" * 64
        doc = self._create_sample_document(
            doc_id="22222222-2222-2222-2222-222222222222",
            checksum=checksum,
        )
        await repo.save(doc)

        found = await repo.find_by_checksum(checksum)
        assert found is not None
        assert found.id == doc.id

        not_found = await repo.find_by_checksum("c" * 64)
        assert not_found is None

    async def test_save_duplicate_checksum_raises_already_exists(self):
        repo = await self.get_repository()
        checksum = "d" * 64
        doc1 = self._create_sample_document(
            doc_id="33333333-3333-3333-3333-333333333333",
            checksum=checksum,
            filename="first.pdf",
        )
        await repo.save(doc1)

        doc2 = self._create_sample_document(
            doc_id="44444444-4444-4444-4444-444444444444",
            checksum=checksum,
            filename="second.pdf",
        )

        with pytest.raises(DocumentAlreadyExistsError) as exc_info:
            await repo.save(doc2)

        assert exc_info.value.checksum == checksum
        assert exc_info.value.existing_id == doc1.id

    async def test_save_duplicate_checksum_concurrent_asyncio_gather(self):
        import asyncio

        repo = await self.get_repository()
        checksum = "f" * 64

        doc1 = self._create_sample_document(
            doc_id="66666666-6666-6666-6666-666666666666",
            checksum=checksum,
            filename="concurrent_1.pdf",
        )
        doc2 = self._create_sample_document(
            doc_id="77777777-7777-7777-7777-777777777777",
            checksum=checksum,
            filename="concurrent_2.pdf",
        )

        results = await asyncio.gather(
            repo.save(doc1),
            repo.save(doc2),
            return_exceptions=True,
        )

        successes = [r for r in results if isinstance(r, Document)]
        errors = [r for r in results if isinstance(r, DocumentAlreadyExistsError)]

        # Exactamente una inserción debe triunfar y la otra debe fallar por duplicado
        assert len(successes) == 1
        assert len(errors) == 1
        assert errors[0].checksum == checksum
        assert errors[0].existing_id == successes[0].id

    async def test_list_paginated_ordering_created_at_desc_id_asc(self):
        repo = await self.get_repository()
        base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Doc 1: t0, id "b"
        doc1 = self._create_sample_document(
            doc_id="b2222222-2222-2222-2222-222222222222",
            checksum="1" * 64,
            created_at=base_time,
        )
        # Doc 2: t0, id "a" (mismo timestamp, desempata id ASC: doc2 debe ir antes de doc1)
        doc2 = self._create_sample_document(
            doc_id="a1111111-1111-1111-1111-111111111111",
            checksum="2" * 64,
            created_at=base_time,
        )
        # Doc 3: t1 (más reciente que t0: debe ir primero)
        doc3 = self._create_sample_document(
            doc_id="c3333333-3333-3333-3333-333333333333",
            checksum="3" * 64,
            created_at=base_time + timedelta(hours=1),
        )

        await repo.save(doc1)
        await repo.save(doc2)
        await repo.save(doc3)

        # Total 3 docs
        items, total = await repo.list_paginated(skip=0, limit=10)
        assert total == 3
        assert len(items) == 3
        # Esperado: doc3 (más nuevo), luego doc2 (t0, id 'a'), luego doc1 (t0, id 'b')
        assert items[0].id == doc3.id
        assert items[1].id == doc2.id
        assert items[2].id == doc1.id

        # Paginación con skip y limit
        page, total = await repo.list_paginated(skip=1, limit=1)
        assert total == 3
        assert len(page) == 1
        assert page[0].id == doc2.id

    async def test_delete(self):
        repo = await self.get_repository()
        doc = self._create_sample_document(
            doc_id="55555555-5555-5555-5555-555555555555",
            checksum="e" * 64,
        )
        await repo.save(doc)

        deleted = await repo.delete(doc.id)
        assert deleted is True

        found = await repo.find_by_id(doc.id)
        assert found is None

        # Borrar nuevamente debe retornar False
        deleted_again = await repo.delete(doc.id)
        assert deleted_again is False
