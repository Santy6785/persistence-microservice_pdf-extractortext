"""Structured, privacy-safe application and HTTP access logging."""

import contextvars
import json
import logging
import sys
from contextvars import Token
from datetime import datetime, timezone

SERVICE_NAME = "persistence"
REQUEST_ID = contextvars.ContextVar("request_id", default="unknown")
DOCUMENT_FIELDS = (
    "document_id",
    "checksum",
    "filename",
    "text_length",
    "method",
    "path",
    "status",
    "duration_s",
)
EVENT_LOGGER = logging.getLogger("persistence.events")


def bind_request_id(request_id: str) -> Token[str]:
    return REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    REQUEST_ID.reset(token)


def _event_payload(
    level: str,
    message: str,
    request_id: str | None = None,
    **fields: str | int | None,
) -> dict[str, str | int]:
    payload: dict[str, str | int] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": level,
        "service": SERVICE_NAME,
        "request_id": request_id or REQUEST_ID.get(),
        "message": message,
    }
    payload.update(
        {
            field: fields[field]
            for field in DOCUMENT_FIELDS
            if fields.get(field) is not None
        }
    )
    return payload


def log_event(
    message: str,
    level: int = logging.INFO,
    request_id: str | None = None,
    **fields: str | int | None,
) -> None:
    payload = _event_payload(logging.getLevelName(level), message, request_id, **fields)
    EVENT_LOGGER.log(level, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


class UvicornAccessJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = _event_payload(record.levelname, "http_access")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    from app.config import get_settings

    settings = get_settings()
    nivel = settings.log_level  # ya validado: DEBUG/INFO/WARNING/ERROR

    EVENT_LOGGER.disabled = False
    EVENT_LOGGER.setLevel(nivel)
    EVENT_LOGGER.propagate = True
    if not any(getattr(handler, "_persistence_json", False) for handler in EVENT_LOGGER.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._persistence_json = True
        EVENT_LOGGER.addHandler(handler)

    # Desactivar uvicorn.access: RequestLogMiddleware ya emite una línea
    # por petición con el esquema estructurado. Sin esto se duplicarían líneas.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True
    access_logger.propagate = False
