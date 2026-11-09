"""
Tests de LOG_LEVEL (ciclo 5, ciclo 4).

Tests obligatorios (rojo antes de implementar):
- LOG_LEVEL=error: no sale ninguna línea info de persistence.events ni de
  uvicorn/uvicorn.error; una línea error sí sale.
- LOG_LEVEL=debug: salen las líneas de /health/*.
- configure_logging puede llamarse varias veces sin duplicar handlers.
- El nivel se aplica a persistence.events, uvicorn y uvicorn.error.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_document_repository
from app.api.error_handlers import register_error_handlers
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.api.health import router as health_router
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.request_log_middleware import RequestLogMiddleware
from app.observability import configure_logging, EVENT_LOGGER


def build_http_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=1024 * 1024)
    app.add_middleware(RequestIdMiddleware)

    repo = InMemoryDocumentRepository()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.include_router(api_v1_router)
    app.include_router(health_router)
    register_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("excepción no controlada")

    return app


@pytest.fixture
def app() -> FastAPI:
    return build_http_app()


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ------------------------------------------------------------------
# Test 1: LOG_LEVEL=error -> solo líneas error en persistence.events
#         y uvicorn; ninguna línea info
# ------------------------------------------------------------------


async def test_log_level_error_no_info_lines(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    """Con LOG_LEVEL=error, persistence.events y uvicorn solo emiten error."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("LOG_LEVEL", "error")
    from app.config import get_settings

    get_settings.cache_clear()
    configure_logging()

    await client.get("/health/live")
    await client.get("/api/v1/documents?skip=0&limit=10")

    # No debe haber ninguna línea INFO ni DEBUG de persistence.events
    persistence_info = [
        r
        for r in caplog.records
        if r.name == "persistence.events" and r.levelno <= logging.INFO
    ]
    assert len(persistence_info) == 0, f"Líneas INFO en persistence.events: {persistence_info}"

    # No debe haber ninguna línea INFO ni DEBUG de uvicorn
    uvicorn_info = [
        r for r in caplog.records if r.name.startswith("uvicorn") and r.levelno <= logging.INFO
    ]
    assert len(uvicorn_info) == 0, f"Líneas INFO en uvicorn: {uvicorn_info}"


async def test_log_level_error_sale_linea_error(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    """Con LOG_LEVEL=error, una línea error SÍ sale."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("LOG_LEVEL", "error")
    from app.config import get_settings

    get_settings.cache_clear()
    configure_logging()

    # Forzar un error 500
    with pytest.raises(RuntimeError):
        await client.get("/boom")

    persistence_error = [
        r
        for r in caplog.records
        if r.name == "persistence.events" and r.levelno >= logging.ERROR
    ]
    assert len(persistence_error) >= 1, "No hay línea error en persistence.events"


# ------------------------------------------------------------------
# Test 2: LOG_LEVEL=debug -> salen las líneas de /health/*
# ------------------------------------------------------------------


async def test_log_level_debug_sale_health_lines(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    """Con LOG_LEVEL=debug, /health/* se loguea en DEBUG."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("LOG_LEVEL", "debug")
    from app.config import get_settings

    get_settings.cache_clear()
    configure_logging()

    await client.get("/health/live")

    persistence_debug = [
        r
        for r in caplog.records
        if r.name == "persistence.events"
        and r.levelno == logging.DEBUG
        and "http_request" in r.getMessage()
    ]
    assert len(persistence_debug) >= 1, "No hay línea DEBUG de /health/live"


# ------------------------------------------------------------------
# Test 3: configure_logging se puede llamar varias veces sin duplicar
#         handlers
# ------------------------------------------------------------------


async def test_configure_logging_sin_duplicar_handlers(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """configure_logging puede llamarse varias veces sin duplicar handlers."""
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    from app.config import get_settings

    get_settings.cache_clear()

    configure_logging()
    configure_logging()
    configure_logging()

    handlers = EVENT_LOGGER.handlers
    assert len(handlers) == 1, f"Se esperaban 1 handler, hay {len(handlers)}: {handlers}"
    # El handler debe tener _persistence_json = True
    assert getattr(handlers[0], "_persistence_json", False) is True


# ------------------------------------------------------------------
# Test 4: El nivel se aplica a uvicorn y uvicorn.error
# ------------------------------------------------------------------


async def test_log_level_aplica_a_uvicorn(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    """Con LOG_LEVEL=error, uvicorn.error no emite líneas info y su nivel
    se ajusta a ERROR."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("LOG_LEVEL", "error")
    from app.config import get_settings

    get_settings.cache_clear()
    configure_logging()

    # El nivel se aplicó al logger de uvicorn.error
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    assert uvicorn_error_logger.level == logging.ERROR

    await client.get("/health/live")

    uvicorn_info = [
        r
        for r in caplog.records
        if r.name in ("uvicorn", "uvicorn.error") and r.levelno <= logging.INFO
    ]
    assert len(uvicorn_info) == 0, f"Líneas INFO en uvicorn/uvicorn.error: {uvicorn_info}"
