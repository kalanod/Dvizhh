# import grpc

# from .generated import recommendation_service_pb2 as pb
# from .generated import recommendation_service_pb2_grpc

# SERVICE_NAME = pb.DESCRIPTOR.services_by_name["RecommendationService"].full_name


# class RecommendationService(recommendation_service_pb2_grpc.RecommendationServiceServicer):
#     async def GetRecommendations(
#         self, request: pb.GetRecommendationsRequest, context: grpc.aio.ServicerContext
#     ) -> pb.GetRecommendationsResponse:
#         for field in ("user_id", "session_id", "request_id"):
#             if not request.HasField(field) or not getattr(request, field).strip():
#                 await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"{field} is required")
#         if request.HasField("page_token"):
#             await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Pagination is not implemented")
#         return pb.GetRecommendationsResponse()


import logging

import asyncpg
import grpc

from .candidates import get_candidates
from .generated import recommendation_service_pb2 as pb
from .generated import recommendation_service_pb2_grpc

SERVICE_NAME = pb.DESCRIPTOR.services_by_name[
    "RecommendationService"
].full_name

logger = logging.getLogger(__name__)


class RecommendationService(
    recommendation_service_pb2_grpc.RecommendationServiceServicer
):
    def __init__(self, source_pool: asyncpg.Pool) -> None:
        self.source_pool = source_pool

    async def GetRecommendations(
        self,
        request: pb.GetRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.GetRecommendationsResponse:

        # Проверяем обязательные параметры
        for field in ("user_id", "session_id", "request_id"):
            if (
                not request.HasField(field)
                or not getattr(request, field).strip()
            ):
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    f"{field} is required",
                )

        # Пагинация пока не поддерживается
        if request.HasField("page_token"):
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                "Pagination is not implemented",
            )

        # Не игнорируем переданные фильтры
        if request.filters:
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                "Filters are not implemented",
            )

        # Количество мероприятий
        limit = (
            request.page_size
            if request.HasField("page_size")
            else 20
        )

        if not 1 <= limit <= 100:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "page_size must be between 1 and 100",
            )

        # Получаем мероприятия из PostgreSQL
        try:
            event_ids = await get_candidates(
                self.source_pool,
                limit=limit,
            )

        except (
            asyncpg.PostgresConnectionError,
            asyncpg.InterfaceError,
            OSError,
            TimeoutError,
        ):
            logger.exception("Source database unavailable")
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "Source database is unavailable",
            )

        except asyncpg.PostgresError:
            logger.exception("Source database query failed")
            await context.abort(
                grpc.StatusCode.INTERNAL,
                "Source database query failed",
            )

        # Формируем gRPC-ответ
        return pb.GetRecommendationsResponse(
            items=[
                pb.RecommendationItem(item_id=str(event_id))
                for event_id in event_ids
            ]
        )

