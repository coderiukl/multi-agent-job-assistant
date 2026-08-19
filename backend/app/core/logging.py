import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from logging.config import dictConfig
from typing import Any

from app.core.config import Settings

_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

def get_request_id() -> str:
    return _request_id_context.get()

def set_request_id(request_id: str) -> Token[str]:
    return _request_id_context.set(request_id)

def reset_request_id(token: Token[str]) -> None:
    _request_id_context.reset(token)

class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()

        return True

class JsonFormatter(logging.Formatter):
    """Convert log records to JSON for log aggregation systems."""

    EXTRA_FIELDS = (
        "method",
        "path",
        "status_code",
        "duration_ms",
        "error_code",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        for field in self.EXTRA_FIELDS:
            value = getattr(record, field, None)

            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str
        )

def configure_logging(settings: Settings) -> None:
    formatter_name = (
        "json" if settings.log_format == "json" else "console"
    )

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_context": {
                "()": RequestContextFilter,
            },
        },
        "formatters": {
            "console": {
                "format": (
                    "%(asctime)s | %(levelname)s | %(name)s | "
                    "request_id=%(request_id)s | %(message)s"
                ),
            },
            "json": {
                "()": JsonFormatter,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": formatter_name,
                "filters": ["request_context"],
            },
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["default"],
        },
        "loggers": {
            "uvicorn.error": {
                "level": settings.log_level,
                "handlers": ["default"],
                "propagate": False,
            },
            # Request access log sẽ do middleware quản lý.
            "uvicorn.access": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
        },
    }

    dictConfig(config)