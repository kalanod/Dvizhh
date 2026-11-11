import asyncio
import json
import logging

import pytest
from dvizh_logging import JsonFormatter, log_dependency, tracing
from dvizh_logging.http import RequestLoggingMiddleware
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode


@pytest.mark.parametrize(
    ("trace_prefix", "expect_log"), [("0ccb", True), ("0ccc", False)]
)
def test_success_sampling_keeps_dependency_span(
    monkeypatch, caplog, request, trace_prefix, expect_log
):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    request.addfinalizer(provider.shutdown)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "_tracer", provider.get_tracer("test"))
    monkeypatch.setattr(caplog.handler, "formatter", JsonFormatter("backend"))

    async def app(_scope, _receive, send):
        with log_dependency("postgres", "query"):
            await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(_message):
        pass

    async def receive():
        return {"type": "http.request"}

    trace_id = f"{trace_prefix}{'1' * 28}"
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/events",
        "headers": [(b"traceparent", f"00-{trace_id}-1234567890abcdef-01".encode())],
    }
    with caplog.at_level(logging.INFO):
        asyncio.run(RequestLoggingMiddleware(app)(scope, receive, send))

    dependency, server = exporter.get_finished_spans()
    assert dependency.name == "postgres query"
    assert dependency.parent.span_id == server.context.span_id
    records = [json.loads(line) for line in caplog.text.splitlines()]
    assert len(records) == int(expect_log)
    if expect_log:
        (record,) = records
        assert record["status"] == 200
        assert record["trace_id"] == trace_id
        assert "message" not in record
        assert "span_id" not in record


def test_forwarded_http_trace_correlates_the_failed_dependency_without_sensitive_data(
    monkeypatch, caplog
):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "_tracer", provider.get_tracer("test"))
    monkeypatch.setattr(caplog.handler, "formatter", JsonFormatter("backend"))

    trace_id = "1234567890abcdef1234567890abcdef"
    parent_id = "1234567890abcdef"
    request_id = "abcdef1234567890abcdef1234567890"
    secret = "postgresql://private:secret@example.invalid/db"

    async def app(_scope, _receive, send):
        try:
            with log_dependency("postgres", "connect"):
                raise ConnectionRefusedError(secret)
        except ConnectionRefusedError:
            await send({"type": "http.response.start", "status": 500, "headers": []})
            raise

    async def send(_message):
        pass

    async def receive():
        return {"type": "http.request"}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/events",
        "headers": [
            (b"x-request-id", request_id.encode()),
            (b"traceparent", f"00-{trace_id}-{parent_id}-01".encode()),
        ],
    }
    try:
        with pytest.raises(ConnectionRefusedError), caplog.at_level(logging.INFO):
            asyncio.run(RequestLoggingMiddleware(app)(scope, receive, send))

        dependency, http = exporter.get_finished_spans()
        assert dependency.parent.span_id == http.context.span_id
        assert http.parent.span_id == int(parent_id, 16)
        assert http.context.trace_id == int(trace_id, 16)
        assert dependency.status.status_code is StatusCode.ERROR
        assert http.status.status_code is StatusCode.ERROR
        assert (
            dependency.attributes["error_reason"]
            == "Connection refused by the dependency"
        )
        assert (
            dependency.start_time
            <= dependency.events[0].timestamp
            <= dependency.end_time
        )

        records = [json.loads(line) for line in caplog.text.splitlines()]
        assert [record["span_id"] for record in records] == [
            f"{dependency.context.span_id:016x}",
            f"{http.context.span_id:016x}",
        ]
        assert all(record["trace_id"] == trace_id for record in records)
        assert all(record["request_id"] == request_id for record in records)
        assert secret not in caplog.text
        assert all(secret not in span.to_json() for span in (dependency, http))
    finally:
        provider.shutdown()
