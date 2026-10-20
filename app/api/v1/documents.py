"""
Rutas para la gestión de documentos (/api/v1/documents).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.dependencies import get_document_service
from app.api.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentSummaryResponse,
    PaginatedDocumentsResponse,
)
from app.application.document_service import DocumentService
from app.application.dtos import CreateDocumentDTO
from app.observability import log_event

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear y persistir un nuevo documento",
)
async def create_document(
    request: DocumentCreateRequest,
    response: Response,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    dto = CreateDocumentDTO(
        checksum_sha256=request.checksum_sha256,
        filename=request.filename,
        extracted_text=request.extracted_text,
        page_count=request.page_count,
        file_size_bytes=request.file_size_bytes,
        metadata=request.metadata,
    )
    doc = await service.create_document(dto)
    log_event(
        "document_created",
        document_id=doc.id,
        checksum=doc.checksum_sha256,
        filename=doc.filename,
        text_length=len(doc.extracted_text),
    )
    response.headers["Location"] = f"/api/v1/documents/{doc.id}"
    return DocumentResponse.from_entity(doc)


@router.get(
    "/by-checksum/{checksum}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar un documento por su hash SHA-256",
)
async def get_document_by_checksum(
    checksum: Annotated[
        str,
        Path(
            pattern=r"^[a-fA-F0-9]{64}$",
            description="Hash SHA-256 de 64 caracteres hexadecimales",
        ),
    ],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    doc = await service.get_document_by_checksum(checksum.lower())
    return DocumentResponse.from_entity(doc)


@router.get(
    "/{id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar un documento por su UUID",
)
async def get_document_by_id(
    id: Annotated[uuid.UUID, Path(description="UUID v4 del documento")],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    doc = await service.get_document_by_id(str(id))
    return DocumentResponse.from_entity(doc)


@router.get(
    "",
    response_model=PaginatedDocumentsResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar documentos con paginación determinista (excluye extracted_text)",
)
async def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
    skip: Annotated[int, Query(ge=0, description="Número de documentos a omitir")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Límite máximo de documentos a retornar (1-100)"),
    ] = 20,
) -> PaginatedDocumentsResponse:
    paged = await service.list_documents(skip=skip, limit=limit)
    return PaginatedDocumentsResponse(
        items=[DocumentSummaryResponse.from_entity(d) for d in paged.items],
        total=paged.total,
        skip=paged.skip,
        limit=paged.limit,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un documento por su UUID",
)
async def delete_document(
    id: Annotated[uuid.UUID, Path(description="UUID v4 del documento a eliminar")],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> None:
    await service.delete_document(str(id))
