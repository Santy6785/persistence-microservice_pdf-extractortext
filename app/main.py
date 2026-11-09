"""
Punto de entrada principal para la aplicación FastAPI del microservicio persistence.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.error_handlers import build_error_payload, register_error_handlers
from app.api.health import router as health_router
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.config import get_settings
from app.infrastructure.database.connection import (
    close_client,
    ensure_indexes,
    get_client,
)
from app.metrics import MetricRegistry
from app.metrics_middleware import MetricsMiddleware
from app.observability import configure_logging, log_event
from app.trace import TraceMiddleware, last_request


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

    # 1. Middlewares.
    # TraceMiddleware se registra PRIMERO para quedar DENTRO de
    # RequestSizeLimitMiddleware: si este rechaza con 413, TraceMiddleware
    # nunca lee el cuerpo.
    app.add_middleware(TraceMiddleware, max_body_bytes=settings.trace_max_body_bytes)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=settings.max_payload_size_bytes)
    app.add_middleware(RequestIdMiddleware)
    # MetricsMiddleware es el MÁS EXTERNO (registrado último) para contar
    # también los 413 del RequestSizeLimitMiddleware.
    metrics_registry = MetricRegistry()
    app.add_middleware(MetricsMiddleware, registry=metrics_registry)
    # Guardar referencia al registro para que el endpoint /metrics pueda
    # renderizar las métricas.
    app.state.metrics_registry = metrics_registry

    # 2. Manejadores de error uniformes
    register_error_handlers(app)

    # 3. Registro de routers
    app.include_router(health_router)
    app.include_router(api_v1_router)

    # 4. Endpoint de diagnóstico /trace (fuera del router v1 para que su
    # path sea exactamente "/trace" y el middleware lo excluya de la captura).
    @app.get("/trace")
    async def trace_endpoint():
        """Devuelve la última petición y respuesta capturadas (redactadas).

        Sin petición previa devuelve 404 con formato de error uniforme.
        """
        if last_request is None:
            payload = build_error_payload(
                code="NOT_FOUND",
                message="No hay registro de la última petición.",
                details={},
                request_id="unknown",
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=404, content=payload)

        request_info, response_info = last_request
        return {
            "request": request_info,
            "response": response_info,
        }

    # 5. Endpoint de métricas Prometheus (formato texto, sin auth, solo red
    # interna). Cada réplica tiene sus propios contadores en memoria.
    @app.get("/metrics")
    async def metrics_endpoint():
        from fastapi.responses import PlainTextResponse

        from app.metrics import render_text

        registry = app.state.metrics_registry
        texto = render_text(registry)
        return PlainTextResponse(
            content=texto,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


app = create_app()
