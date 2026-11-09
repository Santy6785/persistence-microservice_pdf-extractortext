"""
Tests del middleware RequestLogMiddleware y de la lista blanca de
log_event - Ciclo 5, ciclo 3.

Tests obligatorios (rojo antes de implementar, verde después):
- log_event ignora campos fuera de la lista blanca:
  extracted_text, query, headers y body no salen.
- Una petición = una línea con los 9 campos (message="http_request").
- 413 se loguea con request_id.
- Excepción no controlada -> se loguea status 500 y se relanza.
- /health/live se loguea en DEBUG; el resto en INFO.
- path sin query string.
- El texto secreto no aparece en 409, 422 ni 500.
"""

import json
import logging

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_document_repository
from app.api.error_handlers import register_error_handlers
from app.api.health import router as health_router
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.api.v1.router import api_v1_router
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.observability import DOCUMENT_FIELDS, configure_logging, log_event
from app.request_log_middleware import RequestLogMiddleware

CHECKSUM_1 = "a" * 64
CHECKSUM_2 = "b" * 64
SECRET_TEXT = "SECRET_DO_NOT_LEAK"


def build_http_app() -> FastAPI:
    configure_logging()
    app = FastAPI()
    # Orden (de afuera hacia adentro): Metrics > RequestId > RequestLog >
    # SizeLimit > Trace. En código: Trace primero (más interno), luego
    # SizeLimit, RequestLog, RequestId y Metrics (más externo).
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=1024 * 1024)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"received": len(body)}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("excepción no controlada")

    repo = InMemoryDocumentRepository()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.include_router(api_v1_router)
    app.include_router(health_router)
    register_error_handlers(app)
    return app


@pytest.fixture
def app() -> FastAPI:
    return build_http_app()


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _http_logs(caplog: pytest.LogCaptureFixture) -> list[dict]:
    """Extrae los registros de persistence.events con message=http_request."""
    logs = []
    for record in caplog.records:
        if record.name != "persistence.events":
            continue
        try:
            payload = json.loads(record.getMessage())
        except (json.JSONDecodeError, ValueError):
            continue
        if payload.get("message") == "http_request":
            logs.append(payload)
    return logs


# ------------------------------------------------------------------
# Test 0: log_event ignora campos fuera de la lista blanca
# ------------------------------------------------------------------


def test_log_event_ignores_campos_fuera_de_lista_blanca():
    """extracted_text, query, headers y body no aparecen en el log."""
    log_event(
        "document_created",
        logging.INFO,
        "req-1",
        document_id="123",
        checksum="a" * 64,
        filename="a.pdf",
        text_length=5,
        extracted_text="TEXTO_SECRETO_QUE_NO_DEBE_SALIR",
        query="?skip=0&limit=20",
        headers={"authorization": "Bearer secreto"},
        body={"checksum_sha256": "a" * 64},
    )

    assert "extracted_text" not in DOCUMENT_FIELDS
    assert "query" not in DOCUMENT_FIELDS
    assert "headers" not in DOCUMENT_FIELDS
    assert "body" not in DOCUMENT_FIELDS


# ------------------------------------------------------------------
# Test 1: Una petición = una línea con los 9 campos
# ------------------------------------------------------------------


async def test_una_peticion_una_linea_con_9_campos(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO)
    await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": CHECKSUM_1,
            "filename": "a.pdf",
            "extracted_text": "texto de prueba",
            "page_count": 1,
            "file_size_bytes": 100,
            "metadata": {},
        },
    )

    logs = _http_logs(caplog)
    assert len(logs) >= 1, f"No se encontró línea http_request en: {caplog.records}"

    log = logs[-1]
    campos_esperados = {
        "timestamp",
        "level",
        "service",
        "request_id",
        "message",
        "method",
        "path",
        "status",
        "duration_s",
    }
    assert set(log) == campos_esperados, f"Campos inesperados: {set(log)}"
    assert log["message"] == "http_request"
    assert log["level"] == "INFO"
    assert log["service"] == "persistence"
    assert log["method"] == "POST"
    assert log["path"] == "/api/v1/documents"
    assert log["status"] == 201
    assert isinstance(log["duration_s"], float)
    assert log["duration_s"] >= 0


# ------------------------------------------------------------------
# Test 2: 413 se loguea con request_id
# ------------------------------------------------------------------


async def test_413_se_loguea_con_request_id(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)

    # RequestLogMiddleware debe quedar FUERA de RequestSizeLimitMiddleware
    # para capturar el 413. En código: RequestSizeLimit primero (más interno),
    # luego RequestLog (más externo).
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=10)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"received": len(body)}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/echo", content=b"x" * 100)
        assert resp.status_code == 413

    logs = _http_logs(caplog)
    http_413 = [entry for entry in logs if entry.get("status") == 413]
    assert len(http_413) >= 1, f"No se encontró 413 en: {logs}"
    assert http_413[-1]["request_id"] not in (None, "", "unknown")
    assert "SECRET_DO_NOT_LEAK" not in caplog.text


# ------------------------------------------------------------------
# Test 3: Excepción no controlada -> 500 y relanza
# ------------------------------------------------------------------


async def test_excepcion_no_controlada_loguea_500_y_relanza(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO)

    with pytest.raises(RuntimeError):
        await client.get("/boom")

    logs = _http_logs(caplog)
    http_500 = [entry for entry in logs if entry.get("status") == 500]
    assert len(http_500) >= 1, f"No se encontró 500 en: {logs}"
    assert http_500[-1]["request_id"] not in (None, "", "unknown")


# ------------------------------------------------------------------
# Test 4: /health/live se loguea en DEBUG
# ------------------------------------------------------------------


async def test_health_live_se_loguea_en_debug(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    from app.config import get_settings

    get_settings.cache_clear()
    configure_logging()

    await client.get("/health/live")

    logs = _http_logs(caplog)
    http_live = [entry for entry in logs if entry.get("path") == "/health/live"]
    assert len(http_live) >= 1, f"No se encontró /health/live en: {logs}"
    assert http_live[-1]["level"] == "DEBUG"


# ------------------------------------------------------------------
# Test 5: path sin query string
# ------------------------------------------------------------------


async def test_path_sin_query_string(client: AsyncClient, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)

    await client.get("/api/v1/documents?skip=0&limit=10")

    logs = _http_logs(caplog)
    http_list = [entry for entry in logs if entry.get("path") == "/api/v1/documents"]
    assert len(http_list) >= 1, f"No se encontró /api/v1/documents en: {logs}"
    assert "?" not in http_list[-1]["path"]
    assert http_list[-1]["path"] == "/api/v1/documents"


# ------------------------------------------------------------------
# Test 6: El texto secreto no aparece en 409, 422 ni 500
# ------------------------------------------------------------------


async def test_texto_secreto_no_aparece_en_409_422_500(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.INFO)

    # Crear documento para luego obtener 409
    await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": CHECKSUM_1,
            "filename": "a.pdf",
            "extracted_text": SECRET_TEXT,
            "page_count": 1,
            "file_size_bytes": 100,
            "metadata": {},
        },
    )

    # 409: checksum duplicado
    resp409 = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": CHECKSUM_1,
            "filename": "b.pdf",
            "extracted_text": SECRET_TEXT,
            "page_count": 1,
            "file_size_bytes": 100,
            "metadata": {},
        },
    )
    assert resp409.status_code == 409

    # 422: campo desconocido
    resp422 = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": "c" * 64,
            "filename": "x.pdf",
            "extracted_text": "texto valido",
            "campo_desconocido": SECRET_TEXT,
        },
    )
    assert resp422.status_code == 422

    # 500: excepción no controlada
    with pytest.raises(RuntimeError):
        await client.get("/boom")

    # Verificar que el secreto no aparece en ningún log
    caplog_text = caplog.text
    assert SECRET_TEXT not in caplog_text


# ------------------------------------------------------------------
# Test 7: Evento fuera de una petición no lleva method ni path
# ------------------------------------------------------------------


async def test_evento_fuera_de_peticion_no_lleva_method_path(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.INFO)
    log_event(
        "document_created",
        logging.INFO,
        "req-fuera-peticion",
        document_id="x",
        checksum="a" * 64,
        filename="f.pdf",
        text_length=1,
    )
    logs = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "persistence.events"
    ]
    doc_created = [entry for entry in logs if entry["message"] == "document_created"]
    assert len(doc_created) == 1
    assert "method" not in doc_created[0]
    assert "path" not in doc_created[0]
    assert doc_created[0]["request_id"] == "req-fuera-peticion"
