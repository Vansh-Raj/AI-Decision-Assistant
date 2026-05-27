from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", _request_id.get()),
            "timestamp": self.formatTime(record, self.datefmt),
        }

        event = getattr(record, "event", None)
        if event:
            payload["event"] = event

        extra = getattr(record, "extra_data", None)
        if isinstance(extra, dict):
            payload.update(extra)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
        token = _request_id.set(request_id)
        request.state.request_id = request_id
        start = time.perf_counter()

        logger = get_logger("http")
        log_event(
            logger,
            "http_request_started",
            method=request.method,
            path=request.url.path,
            query=str(request.url.query),
            client=getattr(request.client, "host", None),
        )

        try:
            response = await call_next(request)
        except Exception:
            latency_ms = round((time.perf_counter() - start) * 1000)
            log_event(
                logger,
                "http_request_failed",
                level=logging.exception,
                method=request.method,
                path=request.url.path,
                latency_ms=latency_ms,
            )
            _request_id.reset(token)
            raise

        latency_ms = round((time.perf_counter() - start) * 1000)
        response.headers["x-request-id"] = request_id
        log_event(
            logger,
            "http_request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        _request_id.reset(token)
        return response


def configure_logging(log_level: str) -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_ai_decision_logging_configured", False):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
    root_logger._ai_decision_logging_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ai_decision.{name}")


def log_event(
    logger: logging.Logger,
    event: str,
    level: Any = logging.INFO,
    **extra_data: Any,
) -> None:
    log_fn = level if callable(level) else logger.log
    if callable(level):
        log_fn(
            event,
            extra={"event": event, "extra_data": extra_data},
        )
        return

    logger.log(
        level,
        event,
        extra={"event": event, "extra_data": extra_data},
    )
