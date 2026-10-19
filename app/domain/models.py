"""
Entidades puras de la capa de dominio.
Sin dependencias de frameworks ni librerías de infraestructura.
"""

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Optional

_HEX_64_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass
class Document:
    """Entidad principal que representa un documento con texto extraído y metadatos."""

    id: str
    checksum_sha256: str
    filename: str
    extracted_text: str
    created_at: datetime
    updated_at: datetime
    page_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _HEX_64_PATTERN.match(self.checksum_sha256):
            raise ValueError("Checksum must be a 64-character hexadecimal string.")
        if self.page_count is not None and self.page_count < 0:
            raise ValueError("page_count must be non-negative.")
        if self.file_size_bytes is not None and self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be non-negative.")
