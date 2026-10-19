"""Capa de dominio del microservicio persistence."""

from app.domain.exceptions import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    DomainError,
    PersistenceInfrastructureError,
)
from app.domain.models import Document
from app.domain.repositories import DocumentRepository

__all__ = [
    "Document",
    "DomainError",
    "DocumentNotFoundError",
    "DocumentAlreadyExistsError",
    "PersistenceInfrastructureError",
    "DocumentRepository",
]
