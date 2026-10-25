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
from app.infrastructure.database.connection import (
    close_client,
    ensure_indexes,
    get_client,
)
from app.observability import configure_logging, log_event


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manejador del ciclo de vida de la aplicación con apagado ordenado (graceful shutdown).

    Crea el cliente singleton de MongoDB al arrancar y lo cierra al apagar.
    """
    configure_logging()
    # Crear cliente singleton de Mongo al arrancar (conexión perezosa; se valida en health).
    get_client()
    # Crear índices obligatorios al arrancar. Si falla, el arranque falla.
    await ensure_indexes()
    log_event("mongodb_indexes_ensured")
    yield
    # Cerrar el cliente de MongoDB al apagar el servicio
    await close_client()
    log_event("mongodb_client_closed")


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
