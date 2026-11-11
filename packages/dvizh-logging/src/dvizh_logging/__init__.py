import asyncio
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from time import perf_counter, time_ns

from .errors import error_fields as error_fields
from .tracing import (
    configure_tracing,
    dependency_span,
    finish_span,
    record_span_error,
    trace_fields,
)

_context: ContextVar[dict[str, object] | None] = ContextVar("request_log_context", default=None)
_logger = logging.getLogger(__name__)
_fields = (
    "operation",
    "status",
    "duration_ms",
    "request_id",
    "session_id",
    "dependency",
    "error_type",
    "error_stack",
    "error_reason",
    "error_location",
    "error_file",
    "error_line",
    "error_function",
    "stage",
    "online",
    "upstream",
    "upstream_status",
    "key_source",
)


@contextmanager
def request_context(**fields: object) -> Iterator[None]:
    token = _context.set({**(_context.get() or {}), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def record_dependency(
    dependency: str,
    operation: str,
    started: float | None,
    error: BaseException | None = None,
    **fields: object,
) -> None:
    context = _context.get() or {}
    request_id = context.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return
    if error is None and not context.get("log_dependency_success", True):
        return

    fields.update(dependency=dependency, operation=operation)
    duration = None if started is None else perf_counter() - started
    end_time = time_ns()
    if duration is not None:
        fields["duration_ms"] = round(duration * 1000, 3)

    if error is None:
        level, status, message = logging.INFO, "OK", "Dependency call completed"
    elif isinstance(error, asyncio.CancelledError):
        level, status, message = logging.WARNING, "CANCELLED", "Dependency call interrupted"
    else:
        level, status, message = logging.ERROR, "ERROR", "Dependency call failed"

    with dependency_span(dependency, operation, duration, request_id, end_time=end_time) as span:
        if error is not None and status == "ERROR":
            details = error_fields(error)
            record_span_error(span, error, fields=details, timestamp=end_time)
            fields.update(details)
        for key in ("upstream", "upstream_status"):
            value = fields.get(key)
            if isinstance(value, (str, int)):
                span.set_attribute(key, value)
        finish_span(span, status, failed=status == "ERROR")
        _logger.log(level, message, extra={**fields, "status": status})


@contextmanager
def log_dependency(dependency: str, operation: str) -> Iterator[None]:
    started = perf_counter()
    try:
        yield
    except (Exception, asyncio.CancelledError) as error:
        record_dependency(dependency, operation, started, error)
        raise
    else:
        record_dependency(dependency, operation, started)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        fields = {**(_context.get() or {}), **record.__dict__}
        if record.exc_info and record.exc_info[1] is not None:
            fields.update(error_fields(record.exc_info[1]))
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "service": self.service,
            "message": record.getMessage(),
            **trace_fields(),
            **{key: fields[key] for key in _fields if fields.get(key) is not None},
        }
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    configure_tracing(service)
