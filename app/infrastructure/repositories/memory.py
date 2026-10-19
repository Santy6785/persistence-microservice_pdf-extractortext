"""
Implementación en memoria del patrón DocumentRepository.
Utilizada para tests unitarios rápidos y tests de contrato.
"""

from copy import deepcopy
from typing import Optional
from app.domain.models import Document
from app.domain.exceptions import DocumentAlreadyExistsError
from app.domain.repositories import DocumentRepository


class InMemoryDocumentRepository(DocumentRepository):
    """Repositorio en memoria thread-safe/async para pruebas."""

    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}
        self._checksum_to_id: dict[str, str] = {}

    async def save(self, document: Document) -> Document:
        existing_id_for_checksum = self._checksum_to_id.get(document.checksum_sha256)
        if existing_id_for_checksum and existing_id_for_checksum != document.id:
            raise DocumentAlreadyExistsError(
                checksum=document.checksum_sha256,
                existing_id=existing_id_for_checksum,
            )

        # Si el documento ya existía con otro checksum, limpiamos el índice viejo
        if document.id in self._documents:
            old_doc = self._documents[document.id]
            if old_doc.checksum_sha256 != document.checksum_sha256:
                self._checksum_to_id.pop(old_doc.checksum_sha256, None)

        saved_doc = deepcopy(document)
        self._documents[document.id] = saved_doc
        self._checksum_to_id[document.checksum_sha256] = document.id
        return deepcopy(saved_doc)

    async def find_by_id(self, document_id: str) -> Optional[Document]:
        doc = self._documents.get(document_id)
        return deepcopy(doc) if doc else None

    async def find_by_checksum(self, checksum: str) -> Optional[Document]:
        doc_id = self._checksum_to_id.get(checksum)
        if not doc_id:
            return None
        return await self.find_by_id(doc_id)

    async def list_paginated(
        self, skip: int = 0, limit: int = 20
    ) -> tuple[list[Document], int]:
        total = len(self._documents)
        # Orden determinista: created_at DESC, id ASC
        sorted_docs = sorted(
            self._documents.values(),
            key=lambda d: (-d.created_at.timestamp(), d.id),
        )
        paged = sorted_docs[skip : skip + limit]
        return [deepcopy(doc) for doc in paged], total

    async def delete(self, document_id: str) -> bool:
        doc = self._documents.pop(document_id, None)
        if doc:
            self._checksum_to_id.pop(doc.checksum_sha256, None)
            return True
        return False
