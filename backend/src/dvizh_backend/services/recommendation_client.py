import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from dvizh_logging import current_request_id
from dvizh_logging.tracing import client_span, finish_span, trace_headers
from google.protobuf.struct_pb2 import Struct
from grpc import StatusCode, aio

from dvizh_backend.generated.recommendation_service_pb2 import (
    GetRecommendationsRequest,
    RefreshSessionRequest,
)
from dvizh_backend.generated.recommendation_service_pb2_grpc import RecommendationServiceStub

logger = logging.getLogger(__name__)


class RecommendationUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RecommendationItem:
    item_id: UUID
    occurrence_id: UUID


@dataclass(frozen=True)
class RecommendationPage:
    items: tuple[RecommendationItem, ...]
    next_page_token: str | None
    request_id: UUID


_FALLBACK_STATUSES = {
    StatusCode.ABORTED,
    StatusCode.CANCELLED,
    StatusCode.DEADLINE_EXCEEDED,
    StatusCode.FAILED_PRECONDITION,
    StatusCode.INTERNAL,
    StatusCode.RESOURCE_EXHAUSTED,
    StatusCode.UNAVAILABLE,
    StatusCode.UNIMPLEMENTED,
    StatusCode.UNKNOWN,
}


@contextmanager
def _recommendation_rpc(
    operation: str, session_id: UUID, recommendation_request_id: UUID | None = None,
) -> Iterator[tuple[tuple[str, str], ...]]:
    fields = {"session_id": str(session_id)}
    if recommendation_request_id is not None:
        fields["recommendation_request_id"] = str(recommendation_request_id)
    request_id = current_request_id()
    if request_id is not None:
        fields["request_id"] = request_id
    with client_span("grpc", operation, **fields) as span:
        metadata = trace_headers()
        if request_id is not None:
            metadata["x-request-id"] = request_id
        try:
            yield tuple(metadata.items())
        except aio.AioRpcError as exc:
            code = exc.code()
            failed = code not in {
                StatusCode.ABORTED, StatusCode.CANCELLED, StatusCode.FAILED_PRECONDITION,
            }
            finish_span(span, code.name, failed=failed)
            if failed:
                logger.warning(
                    "Recommendation RPC failed",
                    extra={"operation": operation, "status": code.name, **fields},
                )
            raise
        else:
            finish_span(span, StatusCode.OK.name)


class RecommendationClient:
    def __init__(self, channel: aio.Channel, *, timeout_seconds: float) -> None:
        self.stub = RecommendationServiceStub(channel)
        self.timeout_seconds = timeout_seconds

    async def get_page(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        request_id: UUID,
        filters: dict[str, object],
        page_size: int,
        page_token: str | None,
    ) -> RecommendationPage:
        values = Struct()
        values.update(filters)
        request = GetRecommendationsRequest(
            user_id=str(user_id),
            session_id=str(session_id),
            request_id=str(request_id),
            filters=values.fields,
            page_size=page_size,
            page_token=page_token,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout_seconds
        try:
            try:
                with _recommendation_rpc("GetRecommendations", session_id, request_id) as metadata:
                    response = await self.stub.GetRecommendations(
                        request, timeout=self.timeout_seconds, metadata=metadata,
                    )
            except aio.AioRpcError as exc:
                remaining = deadline - loop.time()
                if exc.code() != StatusCode.ABORTED or remaining <= 0:
                    raise
                request_id = uuid4()
                request.request_id = str(request_id)
                with _recommendation_rpc("GetRecommendations", session_id, request_id) as metadata:
                    response = await self.stub.GetRecommendations(
                        request, timeout=remaining, metadata=metadata,
                    )
        except aio.AioRpcError as exc:
            if exc.code() in _FALLBACK_STATUSES or (
                page_token is not None and exc.code() == StatusCode.INVALID_ARGUMENT
            ):
                raise RecommendationUnavailable(exc.code().name) from exc
            raise

        try:
            items = tuple(
                RecommendationItem(UUID(item.item_id), UUID(item.occurrence_id))
                for item in response.items
            )
        except ValueError:
            raise RecommendationUnavailable("Invalid recommendation items") from None
        if len(items) > page_size or len({item.item_id for item in items}) != len(items):
            raise RecommendationUnavailable("Invalid recommendation page size or duplicate IDs")
        return RecommendationPage(items, response.next_page_token or None, request_id)

    async def refresh_session(self, *, user_id: UUID, session_id: UUID) -> None:
        request = RefreshSessionRequest(user_id=str(user_id), session_id=str(session_id))
        try:
            with _recommendation_rpc("RefreshSession", session_id) as metadata:
                await self.stub.RefreshSession(
                    request, timeout=self.timeout_seconds, metadata=metadata,
                )
        except aio.AioRpcError as exc:
            if exc.code() in _FALLBACK_STATUSES:
                raise RecommendationUnavailable(exc.code().name) from exc
            raise
