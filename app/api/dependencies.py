"""
Inyección de dependencias para los endpoints de FastAPI.
Provee el repositorio de persistencia (MongoDB) y el servicio de aplicación.
"""

from typing import Annotated

from fastapi import Depends

from app.api.health import check_db_health
from app.application.document_service import DocumentService
from app.domain.exceptions import PersistenceInfrastructureError
from app.domain.repositories import DocumentRepository
from app.infrastructure.database.connection import get_database_name
from app.infrastructure.repositories.mongo import MongoDocumentRepository

# Cliente singleton de MongoDB (creado en el lifespan, reutilizado aquí).
_client = None


def get_client():
    """Retorna el cliente singleton de MongoDB (sobrescribible en tests)."""
    global _client
    if _client is None:
        from app.infrastructure.database.connection import get_client as _gc

        _client = _gc()
    return _client


def get_collection():
    """Provee la colección de MongoDB sobre la que operan los repositorios."""
    client = get_client()
    return client[get_database_name()]["documents"]


def get_document_repository() -> DocumentRepository:
    """Provee la instancia del repositorio de persistencia (sobrescribible en tests)."""
    return MongoDocumentRepository()


async def get_document_service(
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> DocumentService:
    """Provee DocumentService verificando antes que MongoDB esté healthy."""
    if isinstance(repository, MongoDocumentRepository):
        is_healthy = await check_db_health()
        if not is_healthy:
            raise PersistenceInfrastructureError(
                "MongoDB is unavailable or health check timed out."
            )
    return DocumentService(repository=repository)
