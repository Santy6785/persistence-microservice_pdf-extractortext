"""
Servicio de aplicación para la gestión de documentos.
Orquesta casos de uso de negocio y coordina con el repositorio.
"""

from datetime import datetime, timezone
import uuid
from app.application.dtos import CreateDocumentDTO, PaginatedDocumentsDTO
from app.domain.models import Document
from app.domain.exceptions import DocumentNotFoundError
from app.domain.repositories import DocumentRepository


class DocumentService:
    """Servicio de aplicación que orquesta las operaciones de documentos."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def create_document(self, dto: CreateDocumentDTO) -> Document:
        """Crea y persiste un nuevo documento con id generado (UUID v4) y timestamps."""
        now = datetime.now(timezone.utc)
        document_id = str(uuid.uuid4())

        doc = Document(
            id=document_id,
            checksum_sha256=dto.checksum_sha256,
            filename=dto.filename,
            extracted_text=dto.extracted_text,
            created_at=now,
            updated_at=now,
            page_count=dto.page_count,
            file_size_bytes=dto.file_size_bytes,
            metadata=dto.metadata,
        )

        return await self._repository.save(doc)

    async def get_document_by_id(self, document_id: str) -> Document:
        """Obtiene un documento por su ID o lanza DocumentNotFoundError."""
        doc = await self._repository.find_by_id(document_id)
        if doc is None:
            raise DocumentNotFoundError(document_id=document_id)
        return doc

    async def get_document_by_checksum(self, checksum: str) -> Document:
        """Obtiene un documento por su checksum o lanza DocumentNotFoundError."""
        doc = await self._repository.find_by_checksum(checksum)
        if doc is None:
            raise DocumentNotFoundError(document_id=checksum)
        return doc

    async def list_documents(
        self, skip: int = 0, limit: int = 20
    ) -> PaginatedDocumentsDTO:
        """Retorna lista paginada de documentos con total."""
        items, total = await self._repository.list_paginated(skip=skip, limit=limit)
        return PaginatedDocumentsDTO(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
        )

    async def delete_document(self, document_id: str) -> None:
        """Elimina un documento por su ID o lanza DocumentNotFoundError."""
        deleted = await self._repository.delete(document_id)
        if not deleted:
            raise DocumentNotFoundError(document_id=document_id)
