"""
Esquemas Pydantic v2 para validación de entrada y serialización de salida en la API HTTP.
"""

from datetime import datetime, timezone
import re
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.domain.models import Document

_HEX_64_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class ErrorDetail(BaseModel):
    """Estructura interna del detalle de error."""

    code: str
    message: str
    details: Any = Field(default_factory=dict)
    request_id: str
    timestamp: str


class ErrorEnvelope(BaseModel):
    """Envoltorio estándar y uniforme para todas las respuestas de error."""

    error: ErrorDetail


class DocumentCreateRequest(BaseModel):
    """Cuerpo de la petición para crear y persistir un documento."""

    model_config = ConfigDict(extra="forbid")

    checksum_sha256: str = Field(
        ...,
        description="Hash SHA-256 del PDF original (64 caracteres hexadecimales)",
    )
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Nombre original del archivo",
    )
    extracted_text: str = Field(
        ...,
        description="Texto completo extraído del documento",
    )
    page_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Cantidad total de páginas del PDF",
    )
    file_size_bytes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Tamaño en bytes del archivo original",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadatos libres asociados al documento",
    )

    @field_validator("checksum_sha256", mode="before")
    @classmethod
    def normalize_checksum(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("Checksum must be a string.")
        normalized = v.strip().lower()
        if not _HEX_64_PATTERN.match(normalized):
            raise ValueError("Checksum must be a 64-character hexadecimal string.")
        return normalized


class DocumentResponse(BaseModel):
    """Respuesta completa de un documento individual."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    checksum_sha256: str
    filename: str
    extracted_text: str
    page_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, doc: Document) -> "DocumentResponse":
        return cls(
            id=doc.id,
            checksum_sha256=doc.checksum_sha256,
            filename=doc.filename,
            extracted_text=doc.extracted_text,
            page_count=doc.page_count,
            file_size_bytes=doc.file_size_bytes,
            metadata=doc.metadata,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


class DocumentSummaryResponse(BaseModel):
    """Respuesta resumida de un documento para listados (excluye extracted_text)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    checksum_sha256: str
    filename: str
    page_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, doc: Document) -> "DocumentSummaryResponse":
        return cls(
            id=doc.id,
            checksum_sha256=doc.checksum_sha256,
            filename=doc.filename,
            page_count=doc.page_count,
            file_size_bytes=doc.file_size_bytes,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


class PaginatedDocumentsResponse(BaseModel):
    """Respuesta paginada con lista de documentos resumidos y total."""

    items: list[DocumentSummaryResponse]
    total: int
    skip: int
    limit: int
