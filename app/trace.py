"""
Middleware ASGI puro de trazado de la última petición y respuesta.

No usa BaseHTTPMiddleware. Se registra DENTRO de RequestSizeLimitMiddleware
para no leer cuerpos que se rechacen con 413.

Guarda en memoria SOLO la última petición y respuesta (método, ruta, query,
status, cabeceras, cuerpo), como una tupla asignada de forma atómica al
terminar la respuesta.

N es siempre la cantidad de caracteres (len del str), nunca bytes.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Tuple

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.redaction import non_json_body, redact_extracted_text, redact_headers

# Última petición/respuesta capturada. Se asigna de forma atómica al terminar
# cada respuesta (asyncio es single-thread, por lo que la asignación simple es
# atómica y no mezclar peticiones concurrentes).
last_request: Optional[Tuple[dict[str, Any], dict[str, Any]]] = None


def _headers_dict(raw_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Convierte cabeceras ASGI (lista de pares de bytes) a dict str->str."""
    return {k.decode("latin1"): v.decode("latin1") for k, v in raw_headers}


def _process_body(raw: bytes) -> Any:
    """Procesa un cuerpo capturado: si es JSON valido lo redacta; si no,
    devuelve una descripcion que nunca filtra el contenido crudo."""
    if not raw:
        return non_json_body(raw)
    try:
        parsed = json.loads(raw)
        return redact_extracted_text(parsed)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return non_json_body(raw)


class TraceMiddleware:
    """Guarda en memoria la última petición y respuesta con redacción de
    datos sensibles (extracted_text, Authorization, Cookie)."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = 1024 * 1024) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # /trace y /health/* no se registran como última petición.
        if path == "/trace" or path.startswith("/health/"):
            await self.app(scope, receive, send)
            return

        # ------------------------------------------------------------------
        # Captura del cuerpo de la petición (envuelve receive y reenvía chunks intactos)
        # ------------------------------------------------------------------
        request_chunks: list[bytes] = []
        request_total_stored = 0   # bytes acumulados en memoria (hasta el tope)
        request_total_received = 0 # bytes totales recibidos (incluye lo excedido)
        request_exceeded = False

        async def trace_receive() -> Message:
            nonlocal request_total_stored, request_total_received, request_exceeded
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                request_total_received += len(chunk)
                if not request_exceeded:
                    if request_total_stored + len(chunk) > self.max_body_bytes:
                        request_exceeded = True
                    else:
                        request_chunks.append(chunk)
                        request_total_stored += len(chunk)
            return message

        # ------------------------------------------------------------------
        # Captura de la respuesta (envuelve send; respuesta llega intacta al cliente)
        # ------------------------------------------------------------------
        response_status: Optional[int] = None
        response_headers_raw: list[tuple[bytes, bytes]] = []
        response_chunks: list[bytes] = []
        response_total = 0
        response_exceeded = False

        async def trace_send(message: Message) -> None:
            nonlocal response_status, response_headers_raw, response_total, response_exceeded
            if message["type"] == "http.response.start":
                response_status = message.get("status")
                response_headers_raw = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if not response_exceeded:
                    if response_total + len(chunk) > self.max_body_bytes:
                        response_exceeded = True
                    else:
                        response_chunks.append(chunk)
                        response_total += len(chunk)
            await send(message)

        # Ejecutar la app con receive/send envueltos.
        # Nota: este middleware esta DENTRO de RequestSizeLimitMiddleware, por lo
        # que si este rechaza con 413 nunca se llega a ejecutar este bloque.
        await self.app(scope, trace_receive, trace_send)

        # ------------------------------------------------------------------
        # Una sola asignacion al terminar la respuesta
        # ------------------------------------------------------------------
        global last_request

        request_headers = redact_headers(_headers_dict(scope.get("headers", [])))
        # En respuestas de error (4xx/5xx) se omite el cuerpo de la peticion
        # para no filtrar datos sensibles (p. ej. campos desconocidos con texto
        # largo en un 422).
        if response_status is not None and response_status >= 400:
            request_body_stored = f"<body omitted: {response_status} error>"
        elif request_exceeded:
            request_body_stored = f"<body: {request_total_received} bytes>"
        else:
            request_body_stored = _process_body(b"".join(request_chunks))

        response_headers = redact_headers(_headers_dict(response_headers_raw))
        if response_exceeded:
            response_body_stored = f"<body: {response_total} bytes>"
        else:
            response_body_stored = _process_body(b"".join(response_chunks))

        last_request = (
            {
                "method": scope.get("method"),
                "path": path,
                "query": scope.get("query_string", b"").decode("latin1"),
                "headers": request_headers,
                "body": request_body_stored,
            },
            {
                "status": response_status,
                "headers": response_headers,
                "body": response_body_stored,
            },
        )
