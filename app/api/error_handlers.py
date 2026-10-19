"""
Manejadores globales y centralizados de errores HTTP.
Transforman cualquier excepción a la estructura de error uniforme del microservicio.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    PersistenceInfrastructureError,
)

logger = logging.getLogger("persistence.error_handlers")


def build_error_payload(
    code: str,
    message: str,
    details: Any = None,
    request_id: str = "unknown",
) -> dict[str, Any]:
    """Construye el diccionario conforme al esquema uniforme ErrorEnvelope."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    }


def _get_request_id(request: Request) -> str:
    """Extrae el request_id del estado de la solicitud o cabecera."""
    if hasattr(request.state, "request_id"):
        return str(request.state.request_id)
    header_val = request.headers.get("X-Request-ID")
    return header_val if header_val else "unknown"


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Mapea errores de validación de Pydantic/FastAPI a 422 con formato uniforme."""
    req_id = _get_request_id(request)
    formatted_errors = []
    for err in exc.errors():
        formatted_errors.append(
            {
                "location": err.get("loc", []),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )

    payload = build_error_payload(
        code="VALIDATION_ERROR",
        message="Validation failed for the requested payload or parameters.",
        details={"validation_errors": formatted_errors},
        request_id=req_id,
    )
    return JSONResponse(status_code=422, content=payload)


async def document_not_found_handler(request: Request, exc: DocumentNotFoundError) -> JSONResponse:
    """Mapea DocumentNotFoundError a 404 con formato uniforme."""
    req_id = _get_request_id(request)
    payload = build_error_payload(
        code="DOCUMENT_NOT_FOUND",
        message=str(exc),
        details={"document_id": exc.document_id},
        request_id=req_id,
    )
    return JSONResponse(status_code=404, content=payload)


async def document_already_exists_handler(
    request: Request, exc: DocumentAlreadyExistsError
) -> JSONResponse:
    """Mapea DocumentAlreadyExistsError a 409 con formato uniforme (sin filtrar texto)."""
    req_id = _get_request_id(request)
    payload = build_error_payload(
        code="DOCUMENT_ALREADY_EXISTS",
        message="A document with the provided checksum already exists.",
        details={"checksum": exc.checksum, "existing_id": exc.existing_id},
        request_id=req_id,
    )
    return JSONResponse(status_code=409, content=payload)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Mapea excepciones HTTP estándar (404 ruta inexistente, 405, 413, etc.) a formato uniforme."""
    req_id = _get_request_id(request)
    code_map = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        413: "PAYLOAD_TOO_LARGE",
    }
    code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    payload = build_error_payload(
        code=code,
        message=str(exc.detail),
        details={},
        request_id=req_id,
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def persistence_infrastructure_handler(
    request: Request, exc: PersistenceInfrastructureError
) -> JSONResponse:
    """Mapea fallas de infraestructura de persistencia a 500 uniforme sin exponer secretos."""
    req_id = _get_request_id(request)
    logger.error("Persistence infrastructure failure [req_id=%s]: %s", req_id, str(exc))
    payload = build_error_payload(
        code="PERSISTENCE_INFRASTRUCTURE_ERROR",
        message="A database or infrastructure failure occurred.",
        details={},
        request_id=req_id,
    )
    return JSONResponse(status_code=500, content=payload)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Mapea cualquier excepción inesperada a 500 uniforme."""
    req_id = _get_request_id(request)
    logger.error("Unhandled exception [req_id=%s]: %s", req_id, str(exc), exc_info=True)
    payload = build_error_payload(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred.",
        details={},
        request_id=req_id,
    )
    return JSONResponse(status_code=500, content=payload)


def register_error_handlers(app: FastAPI) -> None:
    """Registra todos los manejadores de excepciones en la aplicación FastAPI."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DocumentNotFoundError, document_not_found_handler)
    app.add_exception_handler(DocumentAlreadyExistsError, document_already_exists_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(PersistenceInfrastructureError, persistence_infrastructure_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
