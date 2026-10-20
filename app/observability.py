"""Structured, privacy-safe application and HTTP access logging."""

import contextvars
import json
import logging
import sys
from contextvars import Token
from datetime import datetime, timezone

SERVICE_NAME = "persistence"
REQUEST_ID = contextvars.ContextVar("request_id", default="unknown")
DOCUMENT_FIELDS = ("document_id", "checksum", "filename", "text_length")
EVENT_LOGGER = logging.getLogger("persistence.events")


def bind_request_id(request_id: str) -> Token[str]:
    return REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    REQUEST_ID.reset(token)


def _event_payload(
    level: str,
    event: str,
    request_id: str | None = None,
    **fields: str | int | None,
) -> dict[str, str | int]:
    payload: dict[str, str | int] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": level,
        "service": SERVICE_NAME,
        "request_id": request_id or REQUEST_ID.get(),
        "event": event,
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
    event: str,
    level: int = logging.INFO,
    request_id: str | None = None,
    **fields: str | int | None,
) -> None:
    payload = _event_payload(logging.getLevelName(level), event, request_id, **fields)
    EVENT_LOGGER.log(level, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


class UvicornAccessJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = _event_payload(record.levelname, "http_access")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    EVENT_LOGGER.disabled = False
    EVENT_LOGGER.setLevel(logging.INFO)
    EVENT_LOGGER.propagate = True
    if not any(getattr(handler, "_persistence_json", False) for handler in EVENT_LOGGER.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._persistence_json = True
        EVENT_LOGGER.addHandler(handler)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_handler = logging.StreamHandler(sys.stdout)
    access_handler.setFormatter(UvicornAccessJsonFormatter())
    access_logger.addHandler(access_handler)
    access_logger.disabled = False
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
