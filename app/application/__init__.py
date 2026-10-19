"""Capa de aplicación."""

from app.application.dtos import CreateDocumentDTO, PaginatedDocumentsDTO
from app.application.document_service import DocumentService

__all__ = [
    "CreateDocumentDTO",
    "PaginatedDocumentsDTO",
    "DocumentService",
]
