"""Implementaciones de repositorios."""

from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.infrastructure.repositories.postgres import PostgresDocumentRepository

__all__ = [
    "InMemoryDocumentRepository",
    "PostgresDocumentRepository",
]
