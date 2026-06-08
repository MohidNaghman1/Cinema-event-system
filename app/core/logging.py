from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.config import dictConfig
from typing import Any


class JsonFormatter(logging.Formatter):
    """Serialize log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure application logging once."""

    if getattr(configure_logging, "_configured", False):
        return

    formatter_name = "json"
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {formatter_name: {"()": JsonFormatter}},
        "handlers": {
            formatter_name: {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
                "stream": "ext://sys.stdout",
            }
        },
        "root": {
            "handlers": [formatter_name],
            "level": level.upper(),
        },
        "loggers": {
            "uvicorn": {
                "handlers": [formatter_name],
                "level": level.upper(),
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": [formatter_name],
                "level": level.upper(),
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": [formatter_name],
                "level": level.upper(),
                "propagate": False,
            },
        },
    }
    dictConfig(logging_config)
    setattr(configure_logging, "_configured", True)


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name or "cinema-event-system")
