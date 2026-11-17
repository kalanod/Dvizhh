import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import grpc
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


@asynccontextmanager
async def _handle_errors(context: grpc.aio.ServicerContext) -> AsyncIterator[None]:
    try:
        yield
    except SessionNotFound:
        await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Session is no longer available")
    except SessionOwnerMismatch:
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Session belongs to another user")
    except SessionParametersMismatch:
        await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Session parameters have changed")
    except InvalidPageToken:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid page_token")
    except InvalidRequest as exc:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
    except NotImplementedError:
        await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Filters are not implemented")
    except (
        RedisError,
        asyncpg.PostgresConnectionError,
        asyncpg.InterfaceError,
        OSError,
        TimeoutError,
        IncompleteRecommendations,
    ) as exc:
        logger.warning("Recommendations unavailable (%s)", type(exc).__name__)
        await context.abort(
            grpc.StatusCode.UNAVAILABLE, "Recommendations are temporarily unavailable"
        )
    except asyncpg.PostgresError as exc:
        logger.error("Recommendation query failed (%s)", type(exc).__name__)
        await context.abort(grpc.StatusCode.INTERNAL, "Recommendation query failed")
    except Exception as exc:
        logger.error("Recommendation request failed (%s)", type(exc).__name__)
        await context.abort(grpc.StatusCode.INTERNAL, "Recommendation request failed")


class RecommendationService(recommendation_service_pb2_grpc.RecommendationServiceServicer):
    def __init__(self, pagination: Pagination) -> None:
        self.pagination = pagination

    async def GetRecommendations(
        self, request: pb.GetRecommendationsRequest, context: grpc.aio.ServicerContext
    ) -> pb.GetRecommendationsResponse:
        for field in ("user_id", "session_id", "request_id"):
            if not request.HasField(field) or not getattr(request, field).strip():
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"{field} is required")
        async with _handle_errors(context):
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
        for field in ("user_id", "session_id"):
            if not request.HasField(field) or not getattr(request, field).strip():
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"{field} is required")
        async with _handle_errors(context):
            await self.pagination.refresh(request.user_id, request.session_id)
        return Empty()
