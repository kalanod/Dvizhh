from time import perf_counter

from sqlalchemy import event
from sqlalchemy.engine import Engine, ExceptionContext

from . import log_dependency, record_dependency


def trace_sqlalchemy(engine: Engine) -> None:
    @event.listens_for(engine, "do_connect")
    def connect(dialect, _connection_record, args, kwargs):
        with log_dependency("postgres", "connect"):
            return dialect.connect(*args, **kwargs)

    @event.listens_for(engine, "before_cursor_execute")
    def start(_connection, _cursor, _statement, _parameters, context, _executemany):
        context._dvizh_started = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def finish(_connection, _cursor, _statement, _parameters, context, _executemany):
        record_dependency("postgres", "query", context._dvizh_started)

    @event.listens_for(engine, "handle_error")
    def fail(context: ExceptionContext) -> None:
        if context.is_pre_ping:
            operation = "ping"
        elif context.execution_context is not None:
            operation = "query"
        elif context.connection is not None:
            operation = "transaction"
        else:
            return
        started = getattr(context.execution_context, "_dvizh_started", None)
        record_dependency("postgres", operation, started, context.original_exception)
