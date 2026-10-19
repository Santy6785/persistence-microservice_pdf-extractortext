"""
Interfaz del patrón Repository para la entidad Document.
Define el contrato abstracto que cualquier implementación técnica debe satisfacer.
"""

from abc import ABC, abstractmethod
from typing import Optional
from app.domain.models import Document


class DocumentRepository(ABC):
    """Interfaz abstracta para el repositorio de persistencia de documentos."""

    @abstractmethod
    async def save(self, document: Document) -> Document:
        """
        Persiste un nuevo documento o actualiza uno existente.

        Raises:
            DocumentAlreadyExistsError: Si ya existe un documento con el mismo checksum.
            PersistenceInfrastructureError: Si ocurre un fallo técnico no recuperable.
        """
        pass

    @abstractmethod
    async def find_by_id(self, document_id: str) -> Optional[Document]:
        """
        Recupera un documento por su identificador único.

        Returns:
            Document si existe, None en caso contrario.

        Raises:
            PersistenceInfrastructureError: Si ocurre un fallo técnico en la infraestructura.
        """
        pass

    @abstractmethod
    async def find_by_checksum(self, checksum: str) -> Optional[Document]:
        """
        Recupera un documento por su hash SHA-256.

        Returns:
            Document si existe, None en caso contrario.

        Raises:
            PersistenceInfrastructureError: Si ocurre un fallo técnico en la infraestructura.
        """
        pass

    @abstractmethod
    async def list_paginated(
        self, skip: int = 0, limit: int = 20
    ) -> tuple[list[Document], int]:
        """
        Retorna una tupla de (documentos, total_count) con paginación determinista
        ordenada por created_at DESC, id ASC.

        Raises:
            PersistenceInfrastructureError: Si ocurre un fallo técnico en la infraestructura.
        """
        pass

    @abstractmethod
    async def delete(self, document_id: str) -> bool:
        """
        Elimina un documento por su ID.

        Returns:
            True si fue eliminado, False si no existía.

        Raises:
            PersistenceInfrastructureError: Si ocurre un fallo técnico en la infraestructura.
        """
        pass
