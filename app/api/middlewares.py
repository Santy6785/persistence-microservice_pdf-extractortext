"""
Middlewares ASGI para la capa API:
1. RequestIdMiddleware: Extracción o generación de X-Request-ID y propagación en respuesta.
2. RequestSizeLimitMiddleware: Rechazo temprano (HTTP 413) por Content-Length o streaming.
"""

import uuid

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.error_handlers import build_error_payload


class PayloadTooLargeException(Exception):
    """Excepción interna lanzada cuando un stream supera el límite de bytes permitidos."""

    def __init__(self, bytes_received: int, max_size_bytes: int):
        self.bytes_received = bytes_received
        self.max_size_bytes = max_size_bytes
        super().__init__(f"Payload stream exceeded limit of {max_size_bytes} bytes.")


class RequestIdMiddleware:
    """Extrae o genera un X-Request-ID único y lo añade a request.state y cabeceras de respuesta."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id")
        if not request_id or not request_id.strip():
            request_id = str(uuid.uuid4())
        else:
            request_id = request_id.strip()

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", request_id.encode("latin1")))
                message["headers"] = headers_list
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class RequestSizeLimitMiddleware:
    """
    Rechaza solicitudes con HTTP 413 con formato uniforme.
    1. Si Content-Length viene en headers y supera max_size_bytes, rechaza de inmediato.
    2. Si el cuerpo viene en stream (chunked), corta el stream al superar max_size_bytes.
    """

    def __init__(self, app: ASGIApp, max_size_bytes: int):
        self.app = app
        self.max_size_bytes = max_size_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id", "unknown")

        content_length_str = headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > self.max_size_bytes:
                    payload = build_error_payload(
                        code="PAYLOAD_TOO_LARGE",
                        message=(
                            f"Request payload exceeds maximum allowed size of "
                            f"{self.max_size_bytes} bytes."
                        ),
                        details={
                            "content_length": content_length,
                            "max_size_bytes": self.max_size_bytes,
                        },
                        request_id=request_id,
                    )
                    response = JSONResponse(status_code=413, content=payload)
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        bytes_received = 0

        async def stream_limiting_receive() -> Message:
            nonlocal bytes_received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                bytes_received += len(chunk)
                if bytes_received > self.max_size_bytes:
                    raise PayloadTooLargeException(bytes_received, self.max_size_bytes)
            return message

        try:
            await self.app(scope, stream_limiting_receive, send)
        except PayloadTooLargeException as exc:
            state_req_id = scope.get("state", {}).get("request_id", request_id)
            payload = build_error_payload(
                code="PAYLOAD_TOO_LARGE",
                message=(
                    f"Request payload exceeds maximum allowed size of "
                    f"{self.max_size_bytes} bytes."
                ),
                details={
                    "bytes_received": exc.bytes_received,
                    "max_size_bytes": self.max_size_bytes,
                },
                request_id=state_req_id,
            )
            response = JSONResponse(status_code=413, content=payload)
            await response(scope, receive, send)
