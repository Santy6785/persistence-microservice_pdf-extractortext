import pytest
from app.application.dtos import CreateDocumentDTO
from app.application.document_service import DocumentService
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.domain.exceptions import DocumentNotFoundError, DocumentAlreadyExistsError


@pytest.fixture
def service() -> DocumentService:
    repo = InMemoryDocumentRepository()
    return DocumentService(repository=repo)


async def test_create_document_success(service: DocumentService):
    dto = CreateDocumentDTO(
        checksum_sha256="f" * 64,
        filename="reporte.pdf",
        extracted_text="Contenido relevante",
        page_count=5,
        file_size_bytes=2048,
        metadata={"category": "finance"},
    )
    doc = await service.create_document(dto)

    assert doc.id is not None
    assert doc.checksum_sha256 == "f" * 64
    assert doc.filename == "reporte.pdf"
    assert doc.extracted_text == "Contenido relevante"
    assert doc.page_count == 5
    assert doc.file_size_bytes == 2048
    assert doc.metadata == {"category": "finance"}
    assert doc.created_at is not None
    assert doc.updated_at is not None


async def test_create_document_duplicate_raises(service: DocumentService):
    dto = CreateDocumentDTO(
        checksum_sha256="e" * 64,
        filename="doc1.pdf",
        extracted_text="Texto 1",
    )
    created = await service.create_document(dto)

    dto_dup = CreateDocumentDTO(
        checksum_sha256="e" * 64,
        filename="doc2.pdf",
        extracted_text="Texto 2",
    )
    with pytest.raises(DocumentAlreadyExistsError) as exc_info:
        await service.create_document(dto_dup)

    assert exc_info.value.existing_id == created.id
    assert exc_info.value.checksum == "e" * 64


async def test_get_document_by_id_success_and_not_found(service: DocumentService):
    dto = CreateDocumentDTO(
        checksum_sha256="d" * 64,
        filename="sample.pdf",
        extracted_text="Texto",
    )
    created = await service.create_document(dto)

    retrieved = await service.get_document_by_id(created.id)
    assert retrieved.id == created.id

    with pytest.raises(DocumentNotFoundError) as exc_info:
        await service.get_document_by_id("non-existent-uuid")
    assert exc_info.value.document_id == "non-existent-uuid"


async def test_get_document_by_checksum_success_and_not_found(service: DocumentService):
    checksum = "c" * 64
    dto = CreateDocumentDTO(
        checksum_sha256=checksum,
        filename="sample.pdf",
        extracted_text="Texto",
    )
    created = await service.create_document(dto)

    retrieved = await service.get_document_by_checksum(checksum)
    assert retrieved.id == created.id

    with pytest.raises(DocumentNotFoundError):
        await service.get_document_by_checksum("0" * 64)


async def test_list_documents(service: DocumentService):
    for i in range(5):
        await service.create_document(
            CreateDocumentDTO(
                checksum_sha256=f"{i}" * 64,
                filename=f"doc_{i}.pdf",
                extracted_text=f"Text {i}",
            )
        )

    res = await service.list_documents(skip=1, limit=2)
    assert res.total == 5
    assert len(res.items) == 2
    assert res.skip == 1
    assert res.limit == 2


async def test_delete_document_success_and_not_found(service: DocumentService):
    dto = CreateDocumentDTO(
        checksum_sha256="b" * 64,
        filename="delete_me.pdf",
        extracted_text="Texto",
    )
    created = await service.create_document(dto)

    await service.delete_document(created.id)

    with pytest.raises(DocumentNotFoundError):
        await service.get_document_by_id(created.id)

    with pytest.raises(DocumentNotFoundError):
        await service.delete_document(created.id)
