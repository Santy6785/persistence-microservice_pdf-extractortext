"""
Punto de entrada principal para la aplicación FastAPI del microservicio persistence.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manejador del ciclo de vida de la aplicación con apagado ordenado (graceful shutdown)."""
    yield
    # Limpieza de conexiones activas al cerrar el servicio
    from app.api.dependencies import _engine

    if _engine is not None:
        await _engine.dispose()


def create_app() -> FastAPI:
    """Fábrica de creación y configuración de la aplicación FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="PDF Extraction - Persistence Microservice",
        version="0.1.0",
        description="Microservicio de persistencia para el sistema de extracción de texto de PDFs",
        lifespan=lifespan,
    )

    # 1. Middlewares (en orden inverso de ejecución: RequestSizeLimit evalúa antes, RequestId propaga ID)
    app.add_middleware(
        RequestSizeLimitMiddleware, max_size_bytes=settings.max_payload_size_bytes
    )
    app.add_middleware(RequestIdMiddleware)

    # 2. Manejadores de error uniformes
    register_error_handlers(app)

    # 3. Registro de routers
    app.include_router(api_v1_router)

    return app


app = create_app()
