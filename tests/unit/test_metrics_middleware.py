"""
Tests del middleware ASGI puro de métricas (app/metrics_middleware.py)
- Ciclo 4, ciclo 2.

Tests obligatorios (rojo antes de implementar):
- El contador aumenta con cada petición.
- Dos GET a /api/v1/documents/{id} con ids distintos = una sola serie
  con route="/api/v1/documents/{id}".
- Ruta inexistente = route="unmatched".
- Un 413 se cuenta.
- /metrics no se cuenta a sí mismo.
- /metrics no pisa la última petición de /trace.
- Una excepción no controlada se cuenta como 500.
"""

import asyncio
import time

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.routing import Route

import app.trace as tr
from app.trace import TraceMiddleware
from app.api.dependencies import get_document_repository
from app.api.error_handlers import register_error_handlers
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.api.health import router as health_router
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.metrics import MetricRegistry
from app.metrics_middleware import MetricsMiddleware

CHECKSUM_1 = "a" * 64
CHECKSUM_2 = "b" * 64


# ------------------------------------------------------------------
# Helpers para construir apps de prueba
# ------------------------------------------------------------------

def build_http_app(registry=None, max_body_bytes=1024 * 1024) -> FastAPI:
    """App completa con todos los middlewares y routers."""
    app = FastAPI()
    # Orden: Metrics es el MÁS EXTERNO (registrado último), para contar
    # también los 413 del RequestSizeLimit.
    app.add_middleware(TraceMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=max_body_bytes)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(MetricsMiddleware, registry=registry)

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"received": len(body)}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("excepcion no controlada")

    repo = InMemoryDocumentRepository()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.include_router(api_v1_router)
    app.include_router(health_router)
    register_error_handlers(app)
    return app


def build_minimal_app(registry=None) -> Starlette:
    """App mínima (sin FastAPI) para probar el middleware directamente."""
    async def boom_endpoint(request):
        raise RuntimeError("boom directo")

    routes = [Route("/boom", boom_endpoint)]
    app = Starlette(routes=routes)
    app.add_middleware(MetricsMiddleware, registry=registry)
    return app


def _counter_value(registry, method, route, status):
    c = registry.counters()["http_requests_total"]
    return c.value({"method": method, "route": route, "status": status})


# ------------------------------------------------------------------
# Test 1: El contador aumenta con cada petición
# ------------------------------------------------------------------


async def test_counter_increases_per_request():
    registry = MetricRegistry()
    app = build_http_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(3):
            resp = await ac.get("/health/live")
            assert resp.status_code == 200
    assert _counter_value(registry, "GET", "/health/live", "200") == 3


# ------------------------------------------------------------------
# Test 2: Dos GET a /api/v1/documents/{id} con ids distintos =
#         una sola serie con route="/api/v1/documents/{id}"
# ------------------------------------------------------------------


async def test_route_template_not_real_id():
    registry = MetricRegistry()
    app = build_http_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Crear dos documentos con ids distintos
        r1 = await ac.post(
            "/api/v1/documents",
            json={"checksum_sha256": CHECKSUM_1, "filename": "a.pdf",
                  "extracted_text": "texto 1", "page_count": 1,
                  "file_size_bytes": 100, "metadata": {}},
        )
        assert r1.status_code == 201
        id1 = r1.json()["id"]

        r2 = await ac.post(
            "/api/v1/documents",
            json={"checksum_sha256": CHECKSUM_2, "filename": "b.pdf",
                  "extracted_text": "texto 2", "page_count": 1,
                  "file_size_bytes": 100, "metadata": {}},
        )
        assert r2.status_code == 201
        id2 = r2.json()["id"]

        # GET a ambos ids distintos
        resp1 = await ac.get(f"/api/v1/documents/{id1}")
        assert resp1.status_code == 200
        resp2 = await ac.get(f"/api/v1/documents/{id2}")
        assert resp2.status_code == 200

    # Una sola serie con route="/api/v1/documents/{id}", status 200, valor 2
    assert _counter_value(registry, "GET", "/api/v1/documents/{id}", "200") == 2
    # No debe haber serie con el id crudo como etiqueta
    assert _counter_value(registry, "GET", id1, "200") == 0
    assert _counter_value(registry, "GET", id2, "200") == 0


# ------------------------------------------------------------------
# Test 3: Ruta inexistente = route="unmatched"
# ------------------------------------------------------------------


async def test_unmatched_route_is_unmatched():
    registry = MetricRegistry()
    app = build_http_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/ruta-que-no-existe")
        assert resp.status_code == 404
    assert _counter_value(registry, "GET", "unmatched", "404") == 1


# ------------------------------------------------------------------
# Test 4: Un 413 se cuenta
# ------------------------------------------------------------------


async def test_413_is_counted():
    registry = MetricRegistry()
    # Límite muy pequeño para forzar 413
    app = build_http_app(registry=registry, max_body_bytes=10)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/echo", content=b"x" * 100)
        assert resp.status_code == 413
    assert _counter_value(registry, "POST", "unmatched", "413") == 1


# ------------------------------------------------------------------
# Test 5: /metrics no se cuenta a sí mismo
# ------------------------------------------------------------------


async def test_metrics_not_counted_itself():
    registry = MetricRegistry()
    app = build_http_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/metrics")
        assert resp.status_code == 200
    # No debe haber ninguna métrica con route="/metrics"
    c = registry.counters()["http_requests_total"]
    for key, _ in c.items():
        assert key[1] != "/metrics"  # key = (method, route, status)


# ------------------------------------------------------------------
# Test 6: /metrics no pisa la última petición de /trace
# ------------------------------------------------------------------


async def test_metrics_does_not_overwrite_trace_last_request():
    registry = MetricRegistry()
    app = build_http_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Petición de documento (se guarda como última en trace)
        await ac.post(
            "/api/v1/documents",
            json={"checksum_sha256": "c" * 64, "filename": "t.pdf",
                  "extracted_text": "texto trace", "page_count": 1,
                  "file_size_bytes": 100, "metadata": {}},
        )
        assert tr.last_request is not None
        saved_req = tr.last_request

        # GET /metrics no debe pisar la última petición de trace
        resp = await ac.get("/metrics")
        assert resp.status_code == 200
        assert tr.last_request == saved_req


# ------------------------------------------------------------------
# Test 7: Una excepción no controlada se cuenta como 500
# ------------------------------------------------------------------


async def test_unhandled_exception_counted_as_500():
    registry = MetricRegistry()
    app = build_minimal_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with pytest.raises(Exception):
            await ac.get("/boom")
    # La excepción se contó como 500
    assert _counter_value(registry, "GET", "/boom", "500") == 1


# ------------------------------------------------------------------
# Test 8: La duración se observa en el histograma
# ------------------------------------------------------------------


async def test_duration_observed_in_histogram():
    registry = MetricRegistry()
    app = build_http_app(registry=registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/health/live")
    h = registry.histograms()["http_request_duration_seconds"]
    assert h.count({"method": "GET", "route": "/health/live"}) >= 1
