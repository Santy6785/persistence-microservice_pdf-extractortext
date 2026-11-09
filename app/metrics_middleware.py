"""
Middleware ASGI puro de métricas Prometheus.

Es el MÁS EXTERNO de la app (registrado último con add_middleware) para
contar también los 413 del RequestSizeLimitMiddleware.

No usa BaseHTTPMiddleware. Lleva los contadores en memoria (por proceso)
en un MetricRegistry compartido.
"""

from __future__ import annotations

import time
from typing import Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.metrics import MetricRegistry

_UNMATCHED = "unmatched"

# Buckets fijos (segundos) para el histograma de duración.
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float("inf"))


def _resolve_route(scope: Scope) -> str:
    """Reconstruye la plantilla de ruta completa incluyendo prefijos de mount.

    ``scope["route"].path`` solo trae la plantilla relativa del router más
    interno (p. ej. ``/documents/{id}``); este método le antepone el prefijo
    sobrante de ``scope["path"]`` (p. ej. ``/api/v1``) para obtener
    ``/api/v1/documents/{id}``. Si no hay match, devuelve ``unmatched``.
    """
    route_obj = scope.get("route")
    if route_obj is None:
        return _UNMATCHED
    route_path = getattr(route_obj, "path", None)
    if route_path is None:
        return _UNMATCHED

    path_params = scope.get("path_params", {}) or {}
    # Resolver la plantilla relativa a ruta cruda relativa sustituyendo params.
    relative_raw = route_path
    for name, value in path_params.items():
        relative_raw = relative_raw.replace("{" + name + "}", str(value))

    full_path = scope.get("path", "")
    if full_path.endswith(relative_raw) and relative_raw:
        prefix = full_path[: -len(relative_raw)]
    else:
        prefix = ""

    return prefix + route_path


class MetricsMiddleware:
    """Cuenta cada petición HTTP: método, plantilla de ruta y status.

    Mide la duración y la observa en un histograma. /metrics no se conta
    a sí mismo. Si la aplicación lanza una excepción sin respuesta,
    registra 500 y relanza.
    """

    def __init__(self, app: ASGIApp, registry: Optional[MetricRegistry] = None) -> None:
        self.app = app
        self.registry = registry or MetricRegistry()
        self.counter = self.registry.counter(
            "http_requests_total", ["method", "route", "status"]
        )
        self.histogram = self.registry.histogram(
            "http_request_duration_seconds", ["method", "route"],
            buckets=_DURATION_BUCKETS,
        )
        self.gauge = self.registry.gauge("mongodb_up")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # /metrics no se cuenta a sí mismo.
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

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
            status = 500
            raise
        finally:
            # route = plantilla de ruta completa (incluye prefijos de mount)
            # una vez que la app respondió. Si no hay match: "unmatched".
            route = _resolve_route(scope)

            duration = time.perf_counter() - start
            status_label = str(status) if status is not None else "500"

            labels = {
                "method": scope.get("method", ""),
                "route": route,
                "status": status_label,
            }
            self.counter.inc(labels, 1.0)
            self.histogram.observe(duration, labels)

    # Expuesto para que el endpoint /metrics pueda leer el registro.
    def get_registry(self) -> MetricRegistry:
        return self.registry
