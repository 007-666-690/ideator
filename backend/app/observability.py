"""Logs estructurados (JSON), id de solicitud, métricas Prometheus."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)

HTTP_REQUESTS = Counter("ideator_http_requests_total", "Solicitudes HTTP", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "ideator_http_request_duration_seconds",
    "Duración de solicitudes HTTP",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
LLM_REQUESTS = Counter("ideator_llm_requests_total", "Llamadas al modelo de IA", ["task", "outcome"])
LLM_LATENCY = Histogram(
    "ideator_llm_request_duration_seconds",
    "Duración de llamadas al modelo de IA",
    ["task"],
    buckets=(1, 2.5, 5, 10, 20, 40, 60, 90, 120, 180, 300),
)
LLM_TOKENS = Counter("ideator_llm_tokens_total", "Tokens consumidos", ["task", "kind"])

_RESERVED = set(logging.LogRecord("x", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


def current_request_id() -> str | None:
    return _request_id.get()


def set_current_user(user_id: str | None) -> None:
    _user_id.set(user_id)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if rid := _request_id.get():
            data["request_id"] = rid
        if uid := _user_id.get():
            data["user_id"] = uid
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class RequestContextMiddleware:
    """Asigna un X-Request-ID, mide la duración y registra cada solicitud."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("ideator.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        incoming = headers.get("x-request-id", "")
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        rid_token = _request_id.set(request_id)
        uid_token = _user_id.set(None)
        status_holder = {"status": 500}
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            route = scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            method = scope.get("method", "")
            status = status_holder["status"]
            if route_path not in ("/metrics", "/api/health"):
                HTTP_REQUESTS.labels(method, route_path, str(status)).inc()
                HTTP_LATENCY.labels(method, route_path).observe(duration)
                self.logger.info(
                    "%s %s -> %s",
                    method,
                    scope.get("path", ""),
                    status,
                    extra={"route": route_path, "status": status, "duration_ms": round(duration * 1000, 1)},
                )
            _request_id.reset(rid_token)
            _user_id.reset(uid_token)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
