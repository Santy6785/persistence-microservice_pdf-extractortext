"""
Inyección de dependencias para los endpoints de FastAPI.
"""

from typing import Annotated
from fastapi import Depends
from app.config import get_settings
from app.domain.repositories import DocumentRepository
from app.infrastructure.database.connection import create_engine, create_session_factory
from app.infrastructure.repositories.postgres import PostgresDocumentRepository
from app.application.document_service import DocumentService

# Engine y session factory singleton para runtime
_engine = None
_session_factory = None


def get_session_factory():
    global _engine, _session_factory
    if _session_factory is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url)
        _session_factory = create_session_factory(_engine)
    return _session_factory


def get_document_repository() -> DocumentRepository:
    """Provee la instancia del repositorio de persistencia (sobrescribible en tests)."""
    session_factory = get_session_factory()
    return PostgresDocumentRepository(session_factory=session_factory)


def get_document_service(
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> DocumentService:
    """Provee la instancia de DocumentService con su repositorio inyectado."""
    return DocumentService(repository=repository)
