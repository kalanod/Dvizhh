from collections.abc import Iterator
from contextlib import contextmanager
from os import environ

from opentelemetry.context import Context
from opentelemetry.trace import INVALID_SPAN, Span, SpanKind, StatusCode, Tracer, get_current_span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from .errors import error_fields

_tracer: Tracer | None = None
_propagator = TraceContextTextMapPropagator()
_HEALTH_PROBE = "dvizh.health_probe"


def configure_tracing(service: str) -> None:
    global _tracer
    endpoint = environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if not endpoint or _tracer is not None:
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    class ProbeFilteringProcessor(BatchSpanProcessor):
        def on_end(self, span: ReadableSpan) -> None:
            probe = span.attributes and span.attributes.get(_HEALTH_PROBE)
            if not probe or span.status.status_code is StatusCode.ERROR:
                super().on_end(span)

    provider = TracerProvider(resource=Resource({"service.name": service}))
    provider.add_span_processor(
        ProbeFilteringProcessor(
            OTLPSpanExporter(endpoint=endpoint, timeout=2),
            max_queue_size=512,
            max_export_batch_size=128,
            schedule_delay_millis=1000,
        )
    )
    _tracer = provider.get_tracer(__name__)


@contextmanager
def server_span(
    operation: str,
    request_id: str,
    *,
    carrier: dict[str, str] | None = None,
    health_probe: bool = False,
) -> Iterator[Span]:
    if _tracer is None:
        yield INVALID_SPAN
        return

    parent = _propagator.extract(carrier or {}, context=Context())
    with _tracer.start_as_current_span(
        operation,
        context=parent,
        kind=SpanKind.SERVER,
        attributes={"request_id": request_id},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        if health_probe:
            span.set_attribute(_HEALTH_PROBE, True)
        yield span


@contextmanager
def dependency_span(
    dependency: str, operation: str, duration: float | None, request_id: str, *, end_time: int
) -> Iterator[Span]:
    if _tracer is None or not get_current_span().is_recording():
        yield INVALID_SPAN
        return

    start = end_time if duration is None else end_time - round(duration * 1_000_000_000)
    with _tracer.start_as_current_span(
        f"{dependency} {operation}",
        kind=SpanKind.CLIENT,
        attributes={"request_id": request_id, "dependency": dependency, "operation": operation},
        start_time=start,
        end_on_exit=False,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        finally:
            span.end(end_time=end_time)


def trace_fields() -> dict[str, str]:
    context = get_current_span().get_span_context()
    if not context.is_valid or not context.trace_flags.sampled:
        return {}
    return {"trace_id": f"{context.trace_id:032x}", "span_id": f"{context.span_id:016x}"}


def finish_span(span: Span, status: str | int, *, failed: bool = False) -> None:
    span.set_attribute("status", status)
    if failed:
        span.set_status(StatusCode.ERROR)


def record_span_error(
    span: Span,
    error: BaseException,
    *,
    fields: dict[str, object] | None = None,
    timestamp: int | None = None,
) -> None:
    if not span.is_recording():
        return
    fields = fields if fields is not None else error_fields(error)
    attributes: dict[str, str | int] = {"exception.type": type(error).__name__}
    for field in ("error_reason", "error_location", "error_file", "error_line", "error_function"):
        value = fields.get(field)
        if isinstance(value, (str, int)):
            span.set_attribute(field, value)
            if field == "error_reason" and isinstance(value, str):
                attributes["exception.message"] = value
    stack = fields.get("error_stack")
    if isinstance(stack, list):
        attributes["exception.stacktrace"] = "\n".join(
            f"{frame['file']}:{frame['line']} in {frame['function']}" for frame in stack
        )
    span.set_attribute("error.type", type(error).__name__)
    span.add_event("exception", attributes, timestamp=timestamp)
