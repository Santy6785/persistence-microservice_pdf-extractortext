"""
Endpoints de healthcheck operativos para Kubernetes, Docker y balanceadores de carga (/health).
Nota: Es la única excepción al formato uniforme de error, respetando contratos estándar de probes.
"""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.dependencies import get_session_factory

logger = logging.getLogger("persistence.health")
router = APIRouter(prefix="/health", tags=["Health"])


async def check_db_health() -> bool:
    """Ejecuta una consulta liviana (SELECT 1) para comprobar conectividad activa a la base de datos."""
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1;"))
        return True
    except Exception as exc:
        logger.warning("Database connectivity health check failed: %s", exc)
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
