"""
Implementación concreta de DocumentRepository para MongoDB con PyMongo async (AsyncMongoClient).

Mapeo explícito entre la entidad de dominio Document y el documento de BSON de MongoDB.
El campo `_id` de MongoDB es el UUID propio del documento (entity.id), por lo que la
unicidad del documento está garantizada por _id y la unicidad del checksum_sha256 se
garantiza mediante un índice único creado en el lifespan de la aplicación.
"""

from typing import Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.domain.exceptions import (
    DocumentAlreadyExistsError,
    PersistenceInfrastructureError,
)
from app.domain.models import Document
from app.domain.repositories import DocumentRepository
from app.infrastructure.database.connection import get_client, get_database_name


class MongoDocumentRepository(DocumentRepository):
    """Repositorio asíncrono de documentos para MongoDB."""

    def __init__(self) -> None:
        self._collection_name = "documents"

    @property
    def _collection(self):
        client = get_client()
        return client[get_database_name()][self._collection_name]

    # ------------------------------------------------------------------
    # Mapeo explícito entidad <-> documento Mongo
    # ------------------------------------------------------------------

    @staticmethod
    def _to_document(entity: Document) -> dict:
        """Convierte una entidad de dominio en un documento de BSON para MongoDB."""
        return {
            "_id": entity.id,
            "checksum_sha256": entity.checksum_sha256,
            "filename": entity.filename,
            "extracted_text": entity.extracted_text,
            "page_count": entity.page_count,
            "file_size_bytes": entity.file_size_bytes,
            "metadata": entity.metadata,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    @staticmethod
    def _to_entity(doc: dict) -> Document:
        """Convierte un documento de BSON de MongoDB en una entidad de dominio.

        `extracted_text` se lee con .get() porque list_paginated lo proyecta
        fuera (proyección {"extracted_text": 0}); en ese caso se devuelve "".
        """
        return Document(
            id=doc["_id"],
            checksum_sha256=doc["checksum_sha256"],
            filename=doc["filename"],
            extracted_text=doc.get("extracted_text", ""),
            page_count=doc.get("page_count"),
            file_size_bytes=doc.get("file_size_bytes"),
            metadata=doc.get("metadata", {}) or {},
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    # ------------------------------------------------------------------
    # DocumentRepository implementation
    # ------------------------------------------------------------------

    async def save(self, document: Document) -> Document:
        try:
            await self._collection.insert_one(self._to_document(document))
            return document
        except DuplicateKeyError as exc:
            # Violación de unicidad del índice único en checksum_sha256.
            existing_id = await self._existing_id_for_checksum(document.checksum_sha256)
            raise DocumentAlreadyExistsError(
                checksum=document.checksum_sha256,
                existing_id=existing_id or document.id,
            ) from exc
        except PyMongoError as exc:
            raise PersistenceInfrastructureError(
                f"Error de MongoDB al guardar documento: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al guardar documento: {str(exc)}"
            ) from exc

    async def find_by_id(self, document_id: str) -> Optional[Document]:
        try:
            doc = await self._collection.find_one({"_id": document_id})
            return self._to_entity(doc) if doc else None
        except PyMongoError as exc:
            raise PersistenceInfrastructureError(
                f"Error de MongoDB al buscar por ID: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al buscar por ID: {str(exc)}"
            ) from exc

    async def find_by_checksum(self, checksum: str) -> Optional[Document]:
        try:
            doc = await self._collection.find_one({"checksum_sha256": checksum})
            return self._to_entity(doc) if doc else None
        except PyMongoError as exc:
            raise PersistenceInfrastructureError(
                f"Error de MongoDB al buscar por checksum: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al buscar por checksum: {str(exc)}"
            ) from exc

    async def list_paginated(
        self, skip: int = 0, limit: int = 20
    ) -> tuple[list[Document], int]:
        try:
            # Total con count_documents (sin traer documentos).
            total = await self._collection.count_documents({})

            # Listado paginado con proyección: NO traer extracted_text.
            # Orden determinista: created_at DESC, id (_id) ASC.
            cursor = (
                self._collection.find(
                    {},
                    projection={"extracted_text": 0},
                )
                .sort([("created_at", DESCENDING), ("_id", ASCENDING)])
                .skip(skip)
                .limit(limit)
            )
            docs = [self._to_entity(doc) async for doc in cursor]
            return docs, total
        except PyMongoError as exc:
            raise PersistenceInfrastructureError(
                f"Error de MongoDB al listar documentos: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al listar documentos: {str(exc)}"
            ) from exc

    async def delete(self, document_id: str) -> bool:
        try:
            result = await self._collection.delete_one({"_id": document_id})
            return result.deleted_count > 0
        except PyMongoError as exc:
            raise PersistenceInfrastructureError(
                f"Error de MongoDB al eliminar documento: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al eliminar documento: {str(exc)}"
            ) from exc

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _existing_id_for_checksum(self, checksum: str) -> Optional[str]:
        """Devuelve el id del documento existente con el checksum dado, si lo hay."""
        try:
            doc = await self._collection.find_one(
                {"checksum_sha256": checksum}, projection={"_id": 1}
            )
            return doc["_id"] if doc else None
        except PyMongoError:
            # Si no podemos recuperar el existing_id, no ocultamos el fallo:
            # lo dejamos como None y el caller usará document.id como fallback.
            return None
