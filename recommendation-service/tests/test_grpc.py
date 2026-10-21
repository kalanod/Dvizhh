import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import grpc
import pytest

from dvizh_recommendation.config import Settings
from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated import recommendation_service_pb2_grpc
from dvizh_recommendation.main import running_server


@pytest.fixture(autouse=True)
def stub_database_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def connect_databases(_settings: Settings) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr("dvizh_recommendation.main.connect_databases", connect_databases)


def valid_request() -> pb.GetRecommendationsRequest:
    return pb.GetRecommendationsRequest(
        user_id="user-1", session_id="session-1", request_id="request-1"
    )


async def call_recommendations(
    request: pb.GetRecommendationsRequest,
) -> pb.GetRecommendationsResponse:
    settings = Settings(
        grpc_bind_address="127.0.0.1:0",
        source_database_url="postgresql://reader:unused@source.invalid/source",
        vector_database_url="postgresql://writer:unused@vector.invalid/vectors",
        _env_file=None,
    )
    async with (
        running_server(settings) as (_, port),
        grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel,
    ):
        stub = recommendation_service_pb2_grpc.RecommendationServiceStub(channel)
        return await stub.GetRecommendations(request, timeout=5)


def test_get_recommendations_returns_empty_response() -> None:
    response = asyncio.run(call_recommendations(valid_request()))

    assert list(response.items) == []
    assert not response.HasField("next_page_token")


@pytest.mark.parametrize(
    ("field", "value"),
    [("user_id", None), ("session_id", None), ("request_id", None), ("user_id", " ")],
)
def test_required_ids_are_rejected_over_grpc(field: str, value: str | None) -> None:
    request = valid_request()
    if value is None:
        request.ClearField(field)
    else:
        setattr(request, field, value)

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(call_recommendations(request))

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_page_token_reports_unimplemented_pagination() -> None:
    request = valid_request()
    request.page_token = "opaque-token"

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(call_recommendations(request))

    assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED
