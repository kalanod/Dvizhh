"""gRPC transport to the recommendation service. Contains no ranking rules."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid4

import grpc
from google.protobuf.json_format import ParseDict

from ..generated import recommendation_service_pb2 as pb
from ..generated.recommendation_service_pb2_grpc import RecommendationServiceStub

# The recommendation service requires a user ID; guests share this one.
GUEST_USER_ID = "guest"


class RecommendationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


# gRPC status of the recommendation service -> HTTP status and message for the client.
_ERRORS: dict[grpc.StatusCode, tuple[int, str | None]] = {
    # Unknown ranking, missing coordinates, bad page_token: the service explains why.
    grpc.StatusCode.INVALID_ARGUMENT: (422, None),
    # The session expired or its parameters changed: the client starts a new feed.
    grpc.StatusCode.FAILED_PRECONDITION: (409, "Лента устарела, обновите её"),
    grpc.StatusCode.PERMISSION_DENIED: (403, "Лента принадлежит другому пользователю"),
    grpc.StatusCode.UNIMPLEMENTED: (400, "Эти параметры ленты пока не поддерживаются"),
    grpc.StatusCode.UNAVAILABLE: (503, "Рекомендации временно недоступны"),
    grpc.StatusCode.DEADLINE_EXCEEDED: (503, "Рекомендации временно недоступны"),
}


@dataclass(frozen=True)
class RecommendationPage:
    item_ids: list[UUID]
    next_page_token: str | None


class RecommendationGateway:
    """One shared channel per application; create in lifespan, close on shutdown."""

    def __init__(self, address: str, timeout_seconds: float) -> None:
        self._channel = grpc.aio.insecure_channel(address)
        self._stub = RecommendationServiceStub(self._channel)
        self._timeout = timeout_seconds

    async def close(self) -> None:
        await self._channel.close()

    async def get_page(
        self,
        *,
        user_id: str,
        session_id: str,
        ranking: str | None,
        context: Mapping[str, object],
        page_size: int,
        page_token: str | None,
    ) -> RecommendationPage:
        request = pb.GetRecommendationsRequest(
            user_id=user_id,
            session_id=session_id,
            request_id=str(uuid4()),
            page_size=page_size,
        )
        if ranking is not None:
            request.ranking = ranking
        if page_token is not None:
            request.page_token = page_token
        ParseDict({"context": dict(context)}, request)
        response = await self._call(self._stub.GetRecommendations, request)
        return RecommendationPage(
            item_ids=[UUID(item.item_id) for item in response.items],
            next_page_token=(
                response.next_page_token if response.HasField("next_page_token") else None
            ),
        )

    async def refresh(self, *, user_id: str, session_id: str) -> None:
        request = pb.RefreshSessionRequest(user_id=user_id, session_id=session_id)
        await self._call(self._stub.RefreshSession, request)

    async def _call(self, method, request):
        try:
            return await method(request, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            status_code, detail = _ERRORS.get(exc.code(), (502, "Ошибка сервиса рекомендаций"))
            raise RecommendationError(status_code, detail or exc.details() or "") from exc
