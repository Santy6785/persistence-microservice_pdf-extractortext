"""Capa de aplicación."""

from app.application.document_service import DocumentService
from app.application.dtos import CreateDocumentDTO, PaginatedDocumentsDTO

__all__ = [
    "CreateDocumentDTO",
    "PaginatedDocumentsDTO",
    "DocumentService",
]
