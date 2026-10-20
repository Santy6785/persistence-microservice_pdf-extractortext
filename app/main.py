"""
Punto de entrada principal para la aplicación FastAPI del microservicio persistence.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.error_handlers import register_error_handlers
from app.api.health import router as health_router
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.config import get_settings
from app.observability import configure_logging, log_event


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manejador del ciclo de vida de la aplicación con apagado ordenado (graceful shutdown)."""
    configure_logging()
    yield
    # Limpieza de conexiones activas al cerrar el servicio
    from app.api.dependencies import _engine

    if _engine is not None:
        await _engine.dispose()
        log_event("database_engine_disposed")


def create_app() -> FastAPI:
    """Fábrica de creación y configuración de la aplicación FastAPI."""
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="PDF Extraction - Persistence Microservice",
        version="0.1.0",
        description="Microservicio de persistencia para el sistema de extracción de texto de PDFs",
        lifespan=lifespan,
    )

    # 1. Middlewares (RequestSizeLimit evalúa antes, RequestId propaga ID)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=settings.max_payload_size_bytes)
    app.add_middleware(RequestIdMiddleware)

    # 2. Manejadores de error uniformes
    register_error_handlers(app)

    # 3. Registro de routers
    app.include_router(health_router)
    app.include_router(api_v1_router)

    return app


app = create_app()
