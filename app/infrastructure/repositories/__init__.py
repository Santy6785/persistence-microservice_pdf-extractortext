"""Implementaciones de repositorios."""

from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.infrastructure.repositories.mongo import MongoDocumentRepository

__all__ = [
    "InMemoryDocumentRepository",
    "MongoDocumentRepository",
]
