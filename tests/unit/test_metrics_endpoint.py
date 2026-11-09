"""
Tests del endpoint GET /metrics - Ciclo 4, ciclo 3.

Tests obligatorios (rojo antes de implementar):
- ping falla -> mongodb_up 0 con respuesta 200
- ping lento respeta el timeout de 2 s (configurable)
- contadores aumentan entre consultas
"""

import asyncio
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_document_repository
from app.api.error_handlers import register_error_handlers
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.api.health import router as health_router
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.metrics import MetricRegistry, render_text
from app.metrics_middleware import MetricsMiddleware
from app.trace import TraceMiddleware


def build_metrics_app(registry=None, max_body_bytes=1024 * 1024) -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=max_body_bytes)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(MetricsMiddleware, registry=registry)

    repo = InMemoryDocumentRepository()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.include_router(api_v1_router)
    app.include_router(health_router)
    register_error_handlers(app)

    from fastapi.responses import PlainTextResponse

    @app.get("/metrics")
    async def metrics_endpoint():
        texto = render_text(registry)
        return PlainTextResponse(
            content=texto,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


# ------------------------------------------------------------------
# Test 1: ping falla -> mongodb_up 0 con respuesta 200
# ------------------------------------------------------------------


async def test_metrics_mongodb_up_zero_when_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """Si el ping a Mongo falla, /metrics devuelve 200 con mongodb_up 0."""
    registry = MetricRegistry()
    app = build_metrics_app(registry=registry)

    async def false_ping(timeout_ms: int = 2000) -> bool:
        return False

    monkeypatch.setattr("app.metrics_middleware.check_mongodb_up", false_ping)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/metrics")
        assert resp.status_code == 200
        texto = resp.text
        assert "mongodb_up 0" in texto


# ------------------------------------------------------------------
# Test 2: ping lento respeta el timeout de 2 s
# ------------------------------------------------------------------


async def test_metrics_ping_timeout_respected(monkeypatch: pytest.MonkeyPatch):
    """Si el ping se duerme más que el timeout, /metrics responde 200 en
    menos de ~3 s y mongodb_up queda en 0."""
    registry = MetricRegistry()
    app = build_metrics_app(registry=registry)

    async def slow_ping(timeout_ms: int = 2000) -> bool:
        await asyncio.sleep(5)  # mucho más que el timeout de 2 s
        return True

    monkeypatch.setattr("app.metrics_middleware.check_mongodb_up", slow_ping)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=app, base_url="http://test") as ac:
        start = time.perf_counter()
        resp = await ac.get("/metrics")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < 3  # no debe esperar los 5 s del ping lento
        texto = resp.text
        assert "mongodb_up 0" in texto


# ------------------------------------------------------------------
# Test 3: contadores aumentan entre consultas
# ------------------------------------------------------------------


async def test_metrics_counters_increase_between_requests():
    """Entre dos consultas a /metrics, los contadores de otras rutas
    deben aumentar."""
    registry = MetricRegistry()
    app = build_metrics_app(registry=registry)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Primera consulta a /metrics (después de una petición a /health/live)
        await ac.get("/health/live")
        resp1 = await ac.get("/metrics")
        assert resp1.status_code == 200
        texto1 = resp1.text
        count1 = _extract_counter(texto1, "GET", "/health/live", "200")

        # Segunda consulta a /metrics (después de otra petición a /health/live)
        await ac.get("/health/live")
        resp2 = await ac.get("/metrics")
        assert resp2.status_code == 200
        texto2 = resp2.text
        count2 = _extract_counter(texto2, "GET", "/health/live", "200")

        assert count2 == count1 + 1


def _extract_counter(texto: str, method: str, route: str, status: str) -> int:
    """Extrae el valor de un counter del formato de texto de Prometheus."""
    import re

    pattern = (
        r'http_requests_total\{method="' + method + r'",route="' + route +
        r'",status="' + status + r'"\}\s*([0-9.]+)'
    )
    match = re.search(pattern, texto)
    if not match:
        return -1
    return int(float(match.group(1)))
