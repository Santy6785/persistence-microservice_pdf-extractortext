"""
Implementación concreta de DocumentRepository para PostgreSQL con SQLAlchemy 2.0 y asyncpg.
"""

from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.exceptions import (
    DocumentAlreadyExistsError,
    PersistenceInfrastructureError,
)
from app.domain.models import Document
from app.domain.repositories import DocumentRepository
from app.infrastructure.database.models import DocumentORM


class PostgresDocumentRepository(DocumentRepository):
    """Repositorio asíncrono de documentos para PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_entity(orm: DocumentORM) -> Document:
        return Document(
            id=orm.id,
            checksum_sha256=orm.checksum_sha256,
            filename=orm.filename,
            extracted_text=orm.extracted_text,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            page_count=orm.page_count,
            file_size_bytes=orm.file_size_bytes,
            metadata=dict(orm.metadata_json) if orm.metadata_json else {},
        )

    @staticmethod
    def _to_orm(entity: Document) -> DocumentORM:
        return DocumentORM(
            id=entity.id,
            checksum_sha256=entity.checksum_sha256,
            filename=entity.filename,
            extracted_text=entity.extracted_text,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            page_count=entity.page_count,
            file_size_bytes=entity.file_size_bytes,
            metadata_json=entity.metadata,
        )

    async def save(self, document: Document) -> Document:
        try:
            async with self._session_factory() as session:
                orm_doc = self._to_orm(document)
                session.add(orm_doc)
                await session.commit()
                await session.refresh(orm_doc)
                return self._to_entity(orm_doc)
        except IntegrityError as exc:
            # Violación de unicidad por checksum_sha256 o primary key
            existing_id: Optional[str] = None
            try:
                async with self._session_factory() as session:
                    stmt = select(DocumentORM.id).where(
                        DocumentORM.checksum_sha256 == document.checksum_sha256
                    )
                    result = await session.execute(stmt)
                    existing_id = result.scalar_one_or_none()
            except Exception:
                existing_id = None

            raise DocumentAlreadyExistsError(
                checksum=document.checksum_sha256,
                existing_id=existing_id or "unknown",
            ) from exc
        except SQLAlchemyError as exc:
            raise PersistenceInfrastructureError(
                f"Error en base de datos al guardar documento: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al guardar documento: {str(exc)}"
            ) from exc

    async def find_by_id(self, document_id: str) -> Optional[Document]:
        try:
            async with self._session_factory() as session:
                stmt = select(DocumentORM).where(DocumentORM.id == document_id)
                result = await session.execute(stmt)
                orm_doc = result.scalar_one_or_none()
                return self._to_entity(orm_doc) if orm_doc else None
        except SQLAlchemyError as exc:
            raise PersistenceInfrastructureError(
                f"Error en base de datos al buscar por ID: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al buscar por ID: {str(exc)}"
            ) from exc

    async def find_by_checksum(self, checksum: str) -> Optional[Document]:
        try:
            async with self._session_factory() as session:
                stmt = select(DocumentORM).where(DocumentORM.checksum_sha256 == checksum)
                result = await session.execute(stmt)
                orm_doc = result.scalar_one_or_none()
                return self._to_entity(orm_doc) if orm_doc else None
        except SQLAlchemyError as exc:
            raise PersistenceInfrastructureError(
                f"Error en base de datos al buscar por checksum: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al buscar por checksum: {str(exc)}"
            ) from exc

    async def list_paginated(self, skip: int = 0, limit: int = 20) -> tuple[list[Document], int]:
        try:
            async with self._session_factory() as session:
                count_stmt = select(func.count()).select_from(DocumentORM)
                total = (await session.execute(count_stmt)).scalar() or 0

                stmt = (
                    select(DocumentORM)
                    .order_by(DocumentORM.created_at.desc(), DocumentORM.id.asc())
                    .offset(skip)
                    .limit(limit)
                )
                result = await session.execute(stmt)
                orm_docs = result.scalars().all()
                return [self._to_entity(doc) for doc in orm_docs], total
        except SQLAlchemyError as exc:
            raise PersistenceInfrastructureError(
                f"Error en base de datos al listar documentos: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al listar documentos: {str(exc)}"
            ) from exc

    async def delete(self, document_id: str) -> bool:
        try:
            async with self._session_factory() as session:
                stmt = delete(DocumentORM).where(DocumentORM.id == document_id)
                result = await session.execute(stmt)
                await session.commit()
                return bool(result.rowcount and result.rowcount > 0)
        except SQLAlchemyError as exc:
            raise PersistenceInfrastructureError(
                f"Error en base de datos al eliminar documento: {str(exc)}"
            ) from exc
        except Exception as exc:
            raise PersistenceInfrastructureError(
                f"Error inesperado al eliminar documento: {str(exc)}"
            ) from exc
