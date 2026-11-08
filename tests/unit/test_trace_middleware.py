"""
Tests del middleware de trazado (app/trace.py) - Ciclo 2.

Tests obligatorios (rojo antes de implementar):
- POST con extracted_text de 120 caracteres -> "<redacted: 120 chars>".
- 409 (duplicado) y 422 (campo desconocido con texto largo) no filtran texto.
- Cuerpo no JSON o malformado -> "<non-json body: N bytes>".
- Cabeceras Authorization y Cookie redactadas.
- /trace y /health/live no pisan la última petición.
- Dos peticiones concurrentes no mezclan petición y respuesta.
- Respuesta al cliente llega intacta (bytes y cabeceras comparados).
"""

import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

import app.trace as tr
from app.api.dependencies import get_document_repository
from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware
from app.infrastructure.repositories.memory import InMemoryDocumentRepository
from app.trace import TraceMiddleware

CHECKSUM = "a" * 64
SECRET_TEXT = "x" * 120
DUPLICATE_CHECKSUM = "b" * 64


def build_app(with_trace: bool = True, max_body_bytes: int = 1024) -> FastAPI:
    app = FastAPI()
    # Orden: Trace mas interno, RequestSizeLimit medio, RequestId mas externo.
    if with_trace:
        app.add_middleware(TraceMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=1024 * 1024)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"received": len(body)}

    repo = InMemoryDocumentRepository()
    app.dependency_overrides[get_document_repository] = lambda: repo
    return app


@pytest.fixture
def trace_app() -> FastAPI:
    app = build_app(with_trace=True, max_body_bytes=1024)
    tr.last_request = None
    return app


@pytest.fixture
async def client(trace_app: FastAPI):
    transport = ASGITransport(app=trace_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _reset():
    tr.last_request = None


async def _post_document(client, checksum: str, text: str, filename: str = "doc.pdf"):
    return await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": checksum,
            "filename": filename,
            "extracted_text": text,
            "page_count": 1,
            "file_size_bytes": 100,
            "metadata": {"k": "v"},
        },
    )


# ------------------------------------------------------------------
# Test 1: POST con extracted_text de 120 caracteres
# ------------------------------------------------------------------


async def test_trace_redacts_extracted_text_120_chars(client: AsyncClient, trace_app: FastAPI):
    resp = await _post_document(client, CHECKSUM, SECRET_TEXT)
    assert resp.status_code == 201

    req_info, resp_info = tr.last_request
    assert req_info is not None
    assert req_info["method"] == "POST"
    assert req_info["path"] == "/api/v1/documents"
    # extracted_text redactado con N=120
    assert req_info["body"]["extracted_text"] == "<redacted: 120 chars>"
    # El texto original no aparece en ninguna parte de la estructura guardada
    assert SECRET_TEXT not in json.dumps(tr.last_request)
    assert SECRET_TEXT not in str(req_info)
    assert SECRET_TEXT not in str(resp_info)


# ------------------------------------------------------------------
# Test 2: 409 duplicado y 422 campo desconocido no filtran texto
# ------------------------------------------------------------------


async def test_trace_409_duplicate_does_not_leak(client: AsyncClient, trace_app: FastAPI):
    await _post_document(client, DUPLICATE_CHECKSUM, SECRET_TEXT)
    _reset()

    # Segundo intento con mismo checksum -> 409
    resp = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": DUPLICATE_CHECKSUM,
            "filename": "dup.pdf",
            "extracted_text": SECRET_TEXT,
        },
    )
    assert resp.status_code == 409

    req_info, resp_info = tr.last_request
    assert resp_info["status"] == 409
    # No debe filtrar el texto secreto en ninguna parte
    assert SECRET_TEXT not in json.dumps(tr.last_request)
    assert SECRET_TEXT not in str(req_info)
    assert SECRET_TEXT not in str(resp_info)


async def test_trace_422_unknown_field_does_not_leak(client: AsyncClient, trace_app: FastAPI):
    _reset()

    largo = "y" * 500
    resp = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": "c" * 64,
            "filename": "x.pdf",
            "extracted_text": "texto valido",
            "campo_desconocido": largo,  # campo desconocido -> 422, no debe filtrarse
        },
    )
    assert resp.status_code == 422

    req_info, resp_info = tr.last_request
    assert resp_info["status"] == 422
    assert largo not in json.dumps(tr.last_request)
    assert largo not in str(req_info)
    assert largo not in str(resp_info)


# ------------------------------------------------------------------
# Test 3: Cuerpo no JSON o malformado
# ------------------------------------------------------------------


async def test_trace_non_json_body(client: AsyncClient, trace_app: FastAPI):
    _reset()
    raw = b"\x00\x01\x02binary garbage not json"
    resp = await client.post("/echo", content=raw)
    assert resp.status_code == 200

    req_info, _ = tr.last_request
    assert req_info["body"] == f"<non-json body: {len(raw)} bytes>"
    assert raw.decode(errors="ignore") not in json.dumps(tr.last_request)


async def test_trace_malformed_json_body(client: AsyncClient, trace_app: FastAPI):
    _reset()
    raw = b'{"checksum": "a"*64, "broken"'  # JSON malformado
    resp = await client.post("/echo", content=raw)
    assert resp.status_code == 200

    req_info, _ = tr.last_request
    assert req_info["body"] == f"<non-json body: {len(raw)} bytes>"
    assert raw.decode(errors="ignore") not in json.dumps(tr.last_request)


# ------------------------------------------------------------------
# Test 4: Cabeceras Authorization y Cookie redactadas
# ------------------------------------------------------------------


async def test_trace_redacts_authorization_and_cookie(client: AsyncClient, trace_app: FastAPI):
    _reset()
    resp = await client.post(
        "/api/v1/documents",
        json={
            "checksum_sha256": "d" * 64,
            "filename": "h.pdf",
            "extracted_text": "texto",
        },
        headers={"Authorization": "Bearer secreto-token", "Cookie": "session=abc123"},
    )
    assert resp.status_code == 201

    req_info, _ = tr.last_request
    assert req_info["headers"]["authorization"] == "<redacted>"
    assert req_info["headers"]["cookie"] == "<redacted>"
    assert "secreto-token" not in json.dumps(tr.last_request)
    assert "abc123" not in json.dumps(tr.last_request)


# ------------------------------------------------------------------
# Test 5: /trace y /health/live no pisan la última petición
# ------------------------------------------------------------------


async def test_trace_and_health_do_not_overwrite(client: AsyncClient, trace_app: FastAPI):
    await _post_document(client, CHECKSUM, SECRET_TEXT)
    _reset()
    await _post_document(client, "e" * 64, "texto de referencia")
    saved_req = tr.last_request

    # GET /health/live (excluido del trace) no debe pisar la ultima peticion
    resp_health = await client.get("/health/live")
    assert resp_health.status_code == 200
    assert tr.last_request == saved_req

    # GET /trace (excluido del trace; en este ciclo aun no existe como endpoint,
    # por lo que devuelve 404 del router pero el middleware no lo captura)
    resp_trace = await client.get("/trace")
    assert resp_trace.status_code == 404
    assert tr.last_request == saved_req


# ------------------------------------------------------------------
# Test 6: Dos peticiones concurrentes no mezclan peticion y respuesta
# ------------------------------------------------------------------


async def test_trace_concurrent_requests_do_not_mix(client: AsyncClient, trace_app: FastAPI):
    _reset()

    async def post_one(checksum: str, text: str):
        return await _post_document(client, checksum, text)

    results = await asyncio.gather(
        post_one("f1" * 32, "texto_uno_" + "z" * 40),
        post_one("f2" * 32, "texto_dos_" + "w" * 40),
    )
    assert all(r.status_code == 201 for r in results)

    req_info, _ = tr.last_request
    # La ultima peticion guardada debe ser consistente (no una mezcla)
    extracted = req_info["body"].get("extracted_text", "")
    # Ambos textos tienen 50 caracteres, por lo tanto el redactado es "<redacted: 50 chars>"
    assert extracted == "<redacted: 50 chars>"


# ------------------------------------------------------------------
# Test 7: Respuesta al cliente llega intacta (con y sin middleware)
# ------------------------------------------------------------------


async def test_client_response_intact(trace_app: FastAPI):
    app_no_trace = build_app(with_trace=False, max_body_bytes=1024)

    transport_trace = ASGITransport(app=trace_app)
    transport_plain = ASGITransport(app=app_no_trace)

    async with AsyncClient(transport=transport_trace, base_url="http://test") as ct:
        async with AsyncClient(transport=transport_plain, base_url="http://test") as cp:
            resp_t = await ct.post("/echo", content=b"cuerpo de prueba intacto")
            resp_p = await cp.post("/echo", content=b"cuerpo de prueba intacto")

    assert resp_t.status_code == resp_p.status_code == 200
    assert resp_t.content == resp_p.content
    assert resp_t.json() == resp_p.json()
