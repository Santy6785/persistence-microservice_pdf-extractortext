import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.middlewares import RequestIdMiddleware, RequestSizeLimitMiddleware


@pytest.fixture
def app_with_middlewares() -> FastAPI:
    app = FastAPI()
    # Límite bajo para tests: 1024 bytes (1 KB)
    app.add_middleware(RequestSizeLimitMiddleware, max_size_bytes=1024)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/test-upload")
    async def upload(request: Request):
        body = await request.body()
        req_id = getattr(request.state, "request_id", "none")
        return JSONResponse({"status": "ok", "size": len(body), "request_id": req_id})

    return app


async def test_request_id_generated_and_returned_in_headers(app_with_middlewares: FastAPI):
    transport = ASGITransport(app=app_with_middlewares)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sin X-Request-ID: se genera uno
        resp = await client.post("/test-upload", json={"hello": "world"})
        assert resp.status_code == 200
        req_id = resp.headers.get("x-request-id")
        assert req_id is not None
        assert len(req_id) > 10
        assert resp.json()["request_id"] == req_id

        # 2. Con X-Request-ID: se preserva
        resp2 = await client.post(
            "/test-upload",
            json={"hello": "world"},
            headers={"x-request-id": "custom-trace-123"},
        )
        assert resp2.status_code == 200
        assert resp2.headers.get("x-request-id") == "custom-trace-123"
        assert resp2.json()["request_id"] == "custom-trace-123"


async def test_payload_rejected_by_content_length_header_413(app_with_middlewares: FastAPI):
    transport = ASGITransport(app=app_with_middlewares)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Enviamos Content-Length mayor al límite (1024)
        large_body = b"x" * 2048
        resp = await client.post(
            "/test-upload",
            content=large_body,
            headers={"content-length": "2048"},
        )
        assert resp.status_code == 413
        data = resp.json()
        assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"
        assert "exceeds maximum allowed size" in data["error"]["message"]
        assert data["error"]["request_id"] is not None


async def test_payload_rejected_by_streaming_stream_without_content_length_413(
    app_with_middlewares: FastAPI,
):
    transport = ASGITransport(app=app_with_middlewares)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Generador de chunks sin header Content-Length
        async def chunk_generator():
            for _ in range(5):
                yield b"a" * 300  # Total 1500 bytes > 1024 bytes límite

        resp = await client.post(
            "/test-upload",
            content=chunk_generator(),
        )
        assert resp.status_code == 413
        data = resp.json()
        assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"
