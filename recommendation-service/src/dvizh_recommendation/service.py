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
from dvizh_logging.tracing import finish_span, record_span_error, server_span
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToDict
from redis.exceptions import RedisError

from .generated import recommendation_service_pb2 as pb
from .generated import recommendation_service_pb2_grpc
from .pagination import (
    IncompleteRecommendations,
    InvalidPageToken,
    InvalidRequest,
    Pagination,
    SessionNotFound,
    SessionOwnerMismatch,
    SessionParametersMismatch,
)
from .recommendations import RecommendationQuery

SERVICE_NAME = pb.DESCRIPTOR.services_by_name["RecommendationService"].full_name
logger = logging.getLogger(__name__)
_LOG_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}")


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
        case InvalidPageToken():
            return grpc.StatusCode.INVALID_ARGUMENT, "Invalid page_token"
        case InvalidRequest():
            return grpc.StatusCode.INVALID_ARGUMENT, str(exc)
        case NotImplementedError():
            return grpc.StatusCode.UNIMPLEMENTED, "Filters are not implemented"
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
    context: grpc.aio.ServicerContext, operation: str, request_id: str, session_id: str
) -> AsyncIterator[None]:
    started = monotonic()
    status = grpc.StatusCode.OK
    level = logging.INFO
    details = {}
    request_id = _log_id(request_id) or uuid4().hex
    carrier = {
        key: value
        for key, value in context.invocation_metadata()
        if key in {"traceparent", "tracestate"} and isinstance(value, str)
    }
    with (
        request_context(request_id=request_id, session_id=_log_id(session_id)),
        server_span(operation, request_id, carrier=carrier) as span,
    ):
        try:
            yield
        except asyncio.CancelledError:
            remaining = context.time_remaining()
            status = (
                grpc.StatusCode.DEADLINE_EXCEEDED
                if remaining is not None and remaining <= 0
                else grpc.StatusCode.CANCELLED
            )
            raise
        except Exception as exc:
            status, message = _rpc_error(exc)
            details = error_fields(exc)
            record_span_error(span, exc, fields=details)
            if status is grpc.StatusCode.INTERNAL:
                level = logging.ERROR
            elif status is grpc.StatusCode.UNAVAILABLE:
                level = logging.WARNING
            await context.abort(status, message)
        finally:
            finish_span(
                span,
                status.name,
                failed=status not in (grpc.StatusCode.OK, grpc.StatusCode.CANCELLED),
            )
            logger.log(
                level,
                "gRPC request completed",
                extra={
                    "operation": operation,
                    "status": status.name,
                    "duration_ms": round((monotonic() - started) * 1000, 3),
                    **details,
                },
            )


class RecommendationService(recommendation_service_pb2_grpc.RecommendationServiceServicer):
    def __init__(self, pagination: Pagination) -> None:
        self.pagination = pagination

    async def GetRecommendations(
        self, request: pb.GetRecommendationsRequest, context: grpc.aio.ServicerContext
    ) -> pb.GetRecommendationsResponse:
        async with _rpc_request(
            context, "GetRecommendations", request.request_id, request.session_id
        ):
            _require_fields(request, "user_id", "session_id", "request_id")
            try:
                parameters = MessageToDict(request)
            except ValueError as exc:
                raise InvalidRequest("context and filters must contain valid JSON values") from exc
            page = await self.pagination.get_page(
                RecommendationQuery(
                    request.user_id,
                    parameters.get("context", {}),
                    parameters.get("filters", {}),
                ),
                request.session_id,
                page_size=request.page_size if request.HasField("page_size") else 20,
                page_token=request.page_token if request.HasField("page_token") else None,
            )
            return pb.GetRecommendationsResponse(
                items=[pb.RecommendationItem(item_id=item_id) for item_id in page.item_ids],
                next_page_token=page.next_page_token,
            )

    async def RefreshSession(
        self, request: pb.RefreshSessionRequest, context: grpc.aio.ServicerContext
    ) -> Empty:
        request_id = next(
            (value for key, value in context.invocation_metadata() if key == "x-request-id"), ""
        )
        async with _rpc_request(context, "RefreshSession", request_id, request.session_id):
            _require_fields(request, "user_id", "session_id")
            await self.pagination.refresh(request.user_id, request.session_id)
            return Empty()
