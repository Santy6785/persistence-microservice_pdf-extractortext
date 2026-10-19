"""
DTOs (Data Transfer Objects) para la capa de aplicación.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from app.domain.models import Document


@dataclass
class CreateDocumentDTO:
    """Datos de entrada para persistir un nuevo documento."""

    checksum_sha256: str
    filename: str
    extracted_text: str
    page_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaginatedDocumentsDTO:
    """Resultado paginado de documentos."""

    items: list[Document]
    total: int
    skip: int
    limit: int
