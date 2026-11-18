import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

import asyncpg
import grpc
from dvizh_logging import error_fields, request_context
from dvizh_logging.tracing import finish_span, keep_request_log, record_span_error, server_span
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToDict
from redis.exceptions import RedisError

from .generated import recommendation_service_pb2 as pb
from .generated import recommendation_service_pb2_grpc
from .journal import PageChanged, RecommendationJournal
from .pagination import (
    IncompleteRecommendations,
    InvalidPageToken,
    Pagination,
    SessionNotFound,
    SessionOwnerMismatch,
    SessionParametersMismatch,
    SessionVersionUnavailable,
)
from .recommendations import GeneratorUnavailable, InvalidRequest, NoUserVector, RecommendationQuery

SERVICE_NAME = pb.DESCRIPTOR.services_by_name["RecommendationService"].full_name
logger = logging.getLogger(__name__)
_LOG_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_DEPENDENCY_FAILURES = {
    grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.INTERNAL, grpc.StatusCode.UNAVAILABLE,
}


def _log_id(value: str) -> str | None:
    return value if _LOG_ID.fullmatch(value) else None


def _require_fields(
    request: pb.GetRecommendationsRequest | pb.RefreshSessionRequest, *fields: str
) -> None:
    for field in fields:
        if not request.HasField(field) or not getattr(request, field).strip():
            raise InvalidRequest(f"{field} is required")


def _rpc_error(exc: Exception) -> tuple[grpc.StatusCode, str]:
    match exc:
        case SessionNotFound():
            return grpc.StatusCode.FAILED_PRECONDITION, "Session is no longer available"
        case SessionOwnerMismatch():
            return grpc.StatusCode.PERMISSION_DENIED, "Session belongs to another user"
        case SessionParametersMismatch():
            return grpc.StatusCode.FAILED_PRECONDITION, "Session parameters have changed"
        case SessionVersionUnavailable():
            return grpc.StatusCode.FAILED_PRECONDITION, "Session version is no longer available"
        case InvalidPageToken():
            return grpc.StatusCode.INVALID_ARGUMENT, "Invalid page_token"
        case PageChanged():
            return grpc.StatusCode.ABORTED, "Page changed. Retry with a new request_id."
        case NoUserVector():
            return grpc.StatusCode.FAILED_PRECONDITION, "User vector is unavailable"
        case GeneratorUnavailable():
            return grpc.StatusCode.FAILED_PRECONDITION, "No candidate source can serve this request"
        case InvalidRequest():
            return grpc.StatusCode.INVALID_ARGUMENT, str(exc)
        case NotImplementedError():
            return grpc.StatusCode.UNIMPLEMENTED, "Unsupported recommendations filters"
        case (
            RedisError()
            | asyncpg.PostgresConnectionError()
            | asyncpg.InterfaceError()
            | OSError()
            | IncompleteRecommendations()
        ):
            return grpc.StatusCode.UNAVAILABLE, "Recommendations are temporarily unavailable"
        case asyncpg.PostgresError():
            return grpc.StatusCode.INTERNAL, "Recommendation query failed"
        case _:
            return grpc.StatusCode.INTERNAL, "Recommendation request failed"


@asynccontextmanager
async def _rpc_request(
    context: grpc.aio.ServicerContext, operation: str, session_id: str, recommendation_id: str = "",
) -> AsyncIterator[None]:
    started = monotonic()
    status = grpc.StatusCode.OK
    details: dict[str, object] = {}
    metadata = {
        key: value for key, value in context.invocation_metadata()
        if key in {"x-request-id", "traceparent", "tracestate"} and isinstance(value, str)
    }
    recommendation_request_id = _log_id(recommendation_id)
    request_id = (
        _log_id(metadata.pop("x-request-id", "")) or recommendation_request_id or uuid4().hex
    )
    session = _log_id(session_id)
    with (
        request_context(
            request_id=request_id, session_id=session,
            recommendation_request_id=recommendation_request_id,
        ),
        server_span(operation, request_id, carrier=metadata) as span,
    ):
        if session is not None:
            span.set_attribute("session_id", session)
        if recommendation_request_id is not None:
            span.set_attribute("recommendation_request_id", recommendation_request_id)
        try:
            yield
        except asyncio.CancelledError:
            remaining = context.time_remaining()
            if remaining is not None and remaining <= 0:
                status = grpc.StatusCode.DEADLINE_EXCEEDED
                details = {"error_reason": "Recommendation request deadline exceeded"}
            else:
                status = grpc.StatusCode.CANCELLED
            raise
        except Exception as exc:
            status, message = _rpc_error(exc)
            if status in _DEPENDENCY_FAILURES:
                details = {"error_reason": message, **error_fields(exc)}
                record_span_error(span, exc, fields=details)
            else:
                details = {"error_reason": message}
            trailers = (
                (("recsys-reason", "no-user-vector"),) if isinstance(exc, NoUserVector) else ()
            )
            await context.abort(status, message, trailing_metadata=trailers)
        finally:
            failed = status in _DEPENDENCY_FAILURES
            finish_span(span, status.name, failed=failed)
            duration_ms = (monotonic() - started) * 1000
            if keep_request_log(span, duration_ms, failed=failed):
                level = logging.ERROR if status is grpc.StatusCode.INTERNAL else (
                    logging.WARNING if failed else logging.INFO
                )
                logger.log(
                    level,
                    "gRPC request completed",
                    extra={
                        "operation": operation,
                        "status": status.name,
                        "duration_ms": round(duration_ms, 3),
                        **details,
                    },
                )


class RecommendationService(recommendation_service_pb2_grpc.RecommendationServiceServicer):
    def __init__(
        self,
        pagination: Pagination,
        journal: RecommendationJournal | None = None,
        *,
        timeout_seconds: float = 5,
    ) -> None:
        self.pagination = pagination
        self.journal = journal
        self.timeout_seconds = timeout_seconds

    async def GetRecommendations(
        self, request: pb.GetRecommendationsRequest, context: grpc.aio.ServicerContext
    ) -> pb.GetRecommendationsResponse:
        async with (
            _rpc_request(context, "GetRecommendations", request.session_id, request.request_id),
            asyncio.timeout(self.timeout_seconds),
        ):
            _require_fields(request, "user_id", "session_id", "request_id")
            try:
                parameters = MessageToDict(request)
            except ValueError as exc:
                raise InvalidRequest("context and filters must contain valid JSON values") from exc
            query = RecommendationQuery(
                request.user_id,
                parameters.get("context", {}),
                parameters.get("filters", {}),
            )
            page_size = request.page_size if request.HasField("page_size") else 20
            page_token = request.page_token if request.HasField("page_token") else None
            page = await self.pagination.get_page(
                query,
                request.session_id,
                page_size=page_size,
                page_token=page_token,
            )
            if self.journal is not None:
                await self.journal.record(
                    query,
                    request.session_id,
                    request.request_id,
                    page.item_ids,
                    page.snapshots,
                    page_size=page_size,
                    page_token=page_token,
                )
            snapshots = page.snapshots or (None,) * len(page.item_ids)
            return pb.GetRecommendationsResponse(
                items=[
                    pb.RecommendationItem(
                        item_id=item_id,
                        occurrence_id=str(snapshot.occurrence_id) if snapshot else None,
                    )
                    for item_id, snapshot in zip(page.item_ids, snapshots, strict=True)
                ],
                next_page_token=page.next_page_token,
            )

    async def RefreshSession(
        self, request: pb.RefreshSessionRequest, context: grpc.aio.ServicerContext
    ) -> Empty:
        async with (
            _rpc_request(context, "RefreshSession", request.session_id),
            asyncio.timeout(self.timeout_seconds),
        ):
            _require_fields(request, "user_id", "session_id")
            await self.pagination.refresh(request.user_id, request.session_id)
            return Empty()
