import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any
from uuid import uuid4

from . import configure_logging, error_fields, request_context
from .tracing import finish_span, record_span_error, server_span

type Scope = dict[str, Any]
type Message = dict[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_PATTERN = re.compile(rb"[0-9a-f]{32}")
_HEALTH_PATHS = {"/health", "/api/health"}
_logger = logging.getLogger(__name__)


def _request_id(scope: Scope) -> str:
    supplied = [
        value for name, value in scope.get("headers", ()) if name.lower() == _REQUEST_ID_HEADER
    ]
    if len(supplied) == 1 and _REQUEST_ID_PATTERN.fullmatch(supplied[0]):
        return supplied[0].decode("ascii")
    return uuid4().hex


def _trace_carrier(scope: Scope) -> dict[str, str]:
    supplied = [value for name, value in scope.get("headers", ()) if name.lower() == b"traceparent"]
    if len(supplied) == 1 and len(supplied[0]) <= 128:
        return {"traceparent": supplied[0].decode("latin-1")}
    return {}


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._log_lifespan(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        is_health = scope["path"] in _HEALTH_PATHS
        carrier = _trace_carrier(scope)
        started = perf_counter()
        status = None
        failure = None

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        with (
            request_context(request_id=request_id, log_dependency_success=not is_health),
            server_span(
                scope["method"], request_id, carrier=carrier, health_probe=is_health and not carrier
            ) as span,
        ):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception as exc:
                failure = exc
                raise
            finally:
                if failure is not None or status is not None:
                    route = getattr(scope.get("route"), "path", None)
                    operation = f"{scope['method']} {route}" if route else scope["method"]
                    response_status = status if status is not None else 500
                    span.update_name(operation)
                    span.set_attribute("http.request.method", scope["method"])
                    span.set_attribute("http.response.status_code", response_status)
                    if route:
                        span.set_attribute("http.route", route)
                    finish_span(
                        span, response_status, failed=failure is not None or response_status >= 500
                    )
                    fields = {
                        "operation": operation,
                        "status": response_status,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                    }
                    if failure is not None:
                        details = error_fields(failure)
                        record_span_error(span, failure, fields=details)
                        _logger.error(
                            "HTTP request failed",
                            extra={**fields, **details},
                        )
                        failure._dvizh_request_logged = True
                    elif status >= 400 or not is_health:
                        level = logging.ERROR if status >= 500 else logging.INFO
                        _logger.log(level, "HTTP request completed", extra=fields)

    async def _log_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_safely(message: Message) -> None:
            if message["type"] in {
                "lifespan.startup.failed",
                "lifespan.shutdown.failed",
            }:
                message = {**message, "message": ""}
            await send(message)

        try:
            await self.app(scope, receive, send_safely)
        except Exception as exc:
            _logger.error("Application lifespan failed", extra=error_fields(exc))
            raise


class _DuplicateRequestErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.exc_info and getattr(record.exc_info[1], "_dvizh_request_logged", False))


def configure_http_logging(service: str) -> None:
    configure_logging(service)
    logging.getLogger("uvicorn.error").addFilter(_DuplicateRequestErrorFilter())
