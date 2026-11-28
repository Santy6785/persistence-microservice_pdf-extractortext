"""
Endpoints de healthcheck operativos para Kubernetes, Docker y balanceadores de carga (/health).
Nota: Es la única excepción al formato uniforme de error, respetando contratos estándar de probes.
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.infrastructure.database.connection import ping
from app.observability import log_event

router = APIRouter(prefix="/health", tags=["Health"])


async def check_db_health() -> bool:
    """Ejecuta un ping liviano contra MongoDB con timeout acotado."""
    settings = get_settings()
    timeout_s = settings.mongodb_ping_timeout_ms / 1000.0
    try:
        async with asyncio.timeout(timeout_s):
            is_healthy = await ping()
        if not is_healthy:
            log_event("database_health_check_failed", level=logging.WARNING)
        return is_healthy
    except Exception:
        log_event("database_health_check_failed", level=logging.WARNING)
        return False


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness probe: confirma que el proceso web está vivo y respondiendo",
)
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness probe: confirma que el servicio tiene conectividad a la base de datos",
)
async def readiness(
    is_healthy: Annotated[bool, Depends(check_db_health)],
) -> JSONResponse:
    if is_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "database": "connected"},
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "unhealthy", "database": "disconnected"},
    )
