"""Capa de dominio del microservicio persistence."""

from app.domain.models import Document
from app.domain.exceptions import (
    DomainError,
    DocumentNotFoundError,
    DocumentAlreadyExistsError,
    PersistenceInfrastructureError,
)
from app.domain.repositories import DocumentRepository

__all__ = [
    "Document",
    "DomainError",
    "DocumentNotFoundError",
    "DocumentAlreadyExistsError",
    "PersistenceInfrastructureError",
    "DocumentRepository",
]
