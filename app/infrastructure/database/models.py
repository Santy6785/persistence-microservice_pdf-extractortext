"""
Modelos ORM de SQLAlchemy para PostgreSQL.
Viven exclusivamente dentro de la capa de infraestructura.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Clase base declarativa para SQLAlchemy."""

    pass


class DocumentORM(Base):
    """Modelo ORM que mapea la tabla 'documents' en PostgreSQL."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checksum_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_documents_created_at_id", "created_at", "id"),)
