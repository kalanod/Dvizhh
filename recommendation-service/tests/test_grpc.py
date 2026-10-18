
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import grpc
import pytest

from dvizh_recommendation.config import Settings
from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated import recommendation_service_pb2_grpc
from dvizh_recommendation.main import running_server


class FakeConnection:
    def __init__(self) -> None:
        self.event_ids = [uuid4(), uuid4()]
        self.error = None

    async def fetch(self, query: str, limit: int):
        assert "FROM events AS e" in query
        assert "EXISTS" in query

        if self.error is not None:
            raise self.error

        return [
            {"id": event_id}
            for event_id in self.event_ids[:limit]
        ]


class FakePool:

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.fixture(autouse=True)
def stub_database_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeConnection:
    connection = FakeConnection()

    @asynccontextmanager
    async def connect_databases(
        _settings: Settings,
    ) -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(
            source=FakePool(connection),
            vector=None,
        )

    monkeypatch.setattr(
        "dvizh_recommendation.main.connect_databases",
        connect_databases,
    )

    return connection


def valid_request() -> pb.GetRecommendationsRequest:
    return pb.GetRecommendationsRequest(
        user_id="user-1",
        session_id="session-1",
        request_id="request-1",
    )


async def call_recommendations(
    request: pb.GetRecommendationsRequest,
) -> pb.GetRecommendationsResponse:
    settings = Settings(
        grpc_bind_address="127.0.0.1:0",
        source_database_url=(
            "postgresql://reader:unused@source.invalid/source"
        ),
        vector_database_url=(
            "postgresql://writer:unused@vector.invalid/vectors"
        ),
        _env_file=None,
    )

    async with (
        running_server(settings) as (_, port),
        grpc.aio.insecure_channel(
            f"127.0.0.1:{port}"
        ) as channel,
    ):
        stub = (
            recommendation_service_pb2_grpc
            .RecommendationServiceStub(channel)
        )

        return await stub.GetRecommendations(
            request,
            timeout=5,
        )


# Вместо старого теста пустой заглушки
def test_get_recommendations_returns_candidates(
    stub_database_connections: FakeConnection,
) -> None:
    response = asyncio.run(
        call_recommendations(valid_request())
    )

    expected_ids = [
        str(event_id)
        for event_id in stub_database_connections.event_ids
    ]

    actual_ids = [
        item.item_id
        for item in response.items
    ]

    assert actual_ids == expected_ids
    assert not response.HasField("next_page_token")


def test_empty_catalog_returns_empty_response(
    stub_database_connections: FakeConnection,
) -> None:
    stub_database_connections.event_ids = []

    response = asyncio.run(
        call_recommendations(valid_request())
    )

    assert len(response.items) == 0


def test_page_size_limits_results() -> None:
    request = valid_request()
    request.page_size = 1

    response = asyncio.run(
        call_recommendations(request)
    )

    assert len(response.items) == 1


def test_database_failure_returns_unavailable(
    stub_database_connections: FakeConnection,
) -> None:
    stub_database_connections.error = (
        asyncpg.PostgresConnectionError("Connection lost")
    )

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(
            call_recommendations(valid_request())
        )

    assert error.value.code() == grpc.StatusCode.UNAVAILABLE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_id", None),
        ("session_id", None),
        ("request_id", None),
        ("user_id", " "),
    ],
)
def test_required_ids_are_rejected_over_grpc(
    field: str,
    value: str | None,
) -> None:
    request = valid_request()

    if value is None:
        request.ClearField(field)
    else:
        setattr(request, field, value)

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(
            call_recommendations(request)
        )

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_page_token_reports_unimplemented_pagination() -> None:
    request = valid_request()
    request.page_token = "opaque-token"

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(
            call_recommendations(request)
        )

    assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED


def test_invalid_page_size_is_rejected() -> None:
    request = valid_request()
    request.page_size = 0

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(
            call_recommendations(request)
        )

    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_unsupported_filters_are_rejected() -> None:
    request = valid_request()
    request.filters["unknown"].string_value = "value"

    with pytest.raises(grpc.aio.AioRpcError) as error:
        asyncio.run(
            call_recommendations(request)
        )

    assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED
