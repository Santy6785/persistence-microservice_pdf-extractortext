"""
Middleware ASGI puro de registro de peticiones (RequestLog).

Emite UNA línea por petición con message="http_request" y el esquema:
timestamp, level, service, request_id, method, path, status, duration_s.

No usa BaseHTTPMiddleware. Se registra entre RequestSizeLimit y RequestId
(orden de afuera hacia adentro: Metrics > RequestId > RequestLog >
SizeLimit > Trace), de modo que tiene request_id y loguea también los 413.

/health/* y /metrics se loguean en DEBUG; el resto en INFO.
Una excepción sin respuesta se loguea con status 500 y se relanza.
Nunca se loguean extracted_text, query, cabeceras, cuerpo ni texto de
excepciones.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability import REQUEST_ID, log_event

# Rutas que se loguean en DEBUG en lugar de INFO.
_DEBUG_PATHS = ("/health/", "/metrics")


class RequestLogMiddleware:
    """Guarda en el log una línea por petición HTTP con el esquema completo."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        start = time.perf_counter()
        status: Optional[int] = None

        async def traced_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message.get("status")
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        except Exception:
            # La app lanzó una excepción sin haber enviado respuesta.
            request_id = REQUEST_ID.get()
            level = (
                logging.DEBUG
                if path == "/metrics" or path.startswith("/health/")
                else logging.INFO
            )
            log_event(
                "http_request",
                level=level,
                request_id=request_id,
                method=scope.get("method", ""),
                path=path,
                status=500,
                duration_s=round(time.perf_counter() - start, 4),
            )
            raise

        duration_s = round(time.perf_counter() - start, 4)
        request_id = REQUEST_ID.get()
        level = (
            logging.DEBUG
            if path == "/metrics" or path.startswith("/health/")
            else logging.INFO
        )
        log_event(
            "http_request",
            level=level,
            request_id=request_id,
            method=scope.get("method", ""),
            path=path,
            status=status,
            duration_s=duration_s,
        )
