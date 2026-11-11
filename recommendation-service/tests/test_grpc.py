import asyncio
import json
import logging
from contextlib import asynccontextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import grpc
import pytest
from dvizh_logging import JsonFormatter
from redis.exceptions import ConnectionError as RedisConnectionError

from dvizh_recommendation.config import Settings
from dvizh_recommendation.database import Databases
from dvizh_recommendation.generated import recommendation_service_pb2 as pb
from dvizh_recommendation.generated import recommendation_service_pb2_grpc
from dvizh_recommendation.main import _grpc_server
from dvizh_recommendation.pagination import (
    InvalidPageToken,
    Pagination,
    RecommendationPage,
    SessionNotFound,
    SessionOwnerMismatch,
)
from dvizh_recommendation.recommendations import RecommendationQuery


def valid_request(**kwargs) -> pb.GetRecommendationsRequest:
    return pb.GetRecommendationsRequest(
        user_id="user-1", session_id="session-1", request_id="request-1", **kwargs
    )


@asynccontextmanager
async def grpc_client(pagination):
    settings = Settings(
        grpc_bind_address="127.0.0.1:0",
        source_database_url="postgresql://reader:unused@source.invalid/source",
        vector_database_url="postgresql://writer:unused@vector.invalid/vectors",
        redis_url="redis://redis.invalid:6379/0",
        _env_file=None,
    )
    redis = SimpleNamespace(ping=AsyncMock(return_value=True))
    databases = Databases(
        source=SimpleNamespace(fetchval=AsyncMock(return_value=1)),
        vector=SimpleNamespace(fetchval=AsyncMock(return_value=1)),
    )
    async with (
        _grpc_server(settings, pagination, redis, databases) as (_, port),
        grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel,
    ):
        yield recommendation_service_pb2_grpc.RecommendationServiceStub(channel)


def test_grpc_preserves_query_page_and_renewal_contract() -> None:
    async def run():
        pagination = SimpleNamespace(
            get_page=AsyncMock(return_value=RecommendationPage(("item-1", "item-2"), "next")),
            refresh=AsyncMock(),
        )
        request = valid_request(page_token="previous", page_size=30)
        request.context["city"].string_value = "Москва"
        request.filters["free"].bool_value = True
        async with grpc_client(pagination) as client:
            response = await client.GetRecommendations(request, timeout=5)
            assert [item.item_id for item in response.items] == ["item-1", "item-2"]
            assert response.next_page_token == "next"
            pagination.get_page.assert_awaited_once_with(
                RecommendationQuery("user-1", {"city": "Москва"}, {"free": True}),
                "session-1",
                page_size=30,
                page_token="previous",
            )
            pagination.get_page.return_value = RecommendationPage((), None)
            final = await client.GetRecommendations(valid_request(), timeout=5)
            assert not final.items
            assert not final.HasField("next_page_token")
            assert pagination.get_page.call_args.kwargs == {"page_size": 20, "page_token": None}
            await client.RefreshSession(
                pb.RefreshSessionRequest(user_id="user-1", session_id="session-1"), timeout=5
            )
            pagination.refresh.assert_awaited_once_with("user-1", "session-1")

    asyncio.run(run())


def test_concurrent_grpc_requests_keep_ids_and_log_safe_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run():
        get_entered = asyncio.Event()
        refresh_entered = asyncio.Event()
        finish_refresh = asyncio.Event()

        async def get_page(*args, **kwargs):
            get_entered.set()
            await refresh_entered.wait()
            logger.info("Page read")
            return RecommendationPage((), None)

        async def refresh(*args):
            refresh_entered.set()
            await finish_refresh.wait()
            raise RuntimeError("redis://:test-secret@redis.invalid")

        pagination = SimpleNamespace(get_page=get_page, refresh=refresh)
        async with grpc_client(pagination) as client:
            get_call = client.GetRecommendations(valid_request(), timeout=5)
            await asyncio.wait_for(get_entered.wait(), timeout=2)
            refresh_call = client.RefreshSession(
                pb.RefreshSessionRequest(user_id="user-1", session_id="session-2"),
                metadata=(("x-request-id", "request-2"),),
                timeout=5,
            )
            assert isinstance(await get_call, pb.GetRecommendationsResponse)
            finish_refresh.set()
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await refresh_call
            assert error.value.code() == grpc.StatusCode.INTERNAL

    logger = logging.getLogger("dvizh_recommendation")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter("recommendation-service"))
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.INFO, logger.name):
            asyncio.run(run())
    finally:
        logger.removeHandler(handler)

    assert "test-secret" not in output.getvalue()
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    completed = {record["operation"]: record for record in records if "operation" in record}
    assert len(records) == 3
    page_read = next(record for record in records if record["message"] == "Page read")
    assert page_read["request_id"] == completed["GetRecommendations"]["request_id"] == "request-1"
    assert page_read["session_id"] == completed["GetRecommendations"]["session_id"] == "session-1"
    assert completed["GetRecommendations"]["status"] == "OK"
    refresh_log = completed["RefreshSession"]
    assert (refresh_log["request_id"], refresh_log["session_id"]) == ("request-2", "session-2")
    assert refresh_log["status"] == "INTERNAL"
    assert refresh_log["error_type"] == "RuntimeError"
    assert refresh_log["error_stack"]


@pytest.mark.parametrize("field", ["user_id", "session_id", "request_id"])
def test_grpc_rejects_missing_ids_before_calculation(field: str) -> None:
    async def run():
        pagination = SimpleNamespace(get_page=AsyncMock(), refresh=AsyncMock())
        request = valid_request()
        setattr(request, field, " ")
        async with grpc_client(pagination) as client:
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await client.GetRecommendations(request, timeout=5)
            assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            if field != "request_id":
                renewal = pb.RefreshSessionRequest(user_id="user-1", session_id="session-1")
                renewal.ClearField(field)
                with pytest.raises(grpc.aio.AioRpcError) as error:
                    await client.RefreshSession(renewal, timeout=5)
                assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            pagination.get_page.assert_not_awaited()
            pagination.refresh.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (InvalidPageToken(), grpc.StatusCode.INVALID_ARGUMENT),
        (SessionNotFound(), grpc.StatusCode.FAILED_PRECONDITION),
        (SessionOwnerMismatch(), grpc.StatusCode.PERMISSION_DENIED),
        (RedisConnectionError("redis://:secret@redis.invalid"), grpc.StatusCode.UNAVAILABLE),
        (ValueError("internal secret"), grpc.StatusCode.INTERNAL),
    ],
)
def test_grpc_reports_session_and_dependency_failures(failure, status, caplog) -> None:
    async def run():
        pagination = SimpleNamespace(
            get_page=AsyncMock(side_effect=failure), refresh=AsyncMock(side_effect=failure)
        )
        async with grpc_client(pagination) as client:
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await client.GetRecommendations(valid_request(), timeout=5)
            assert error.value.code() == status
            assert "secret" not in error.value.details()

    asyncio.run(run())
    assert "secret" not in caplog.text


@pytest.mark.parametrize("parameters", [{"page_size": 0}, {"page_size": 101}, {"page_token": ""}])
def test_grpc_rejects_invalid_pagination_before_accessing_storage(parameters) -> None:
    async def run():
        store = SimpleNamespace(read_page=AsyncMock())
        provider = SimpleNamespace(recommend=AsyncMock())
        check_availability = AsyncMock()
        async with grpc_client(Pagination(store, provider, check_availability)) as client:
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await client.GetRecommendations(valid_request(**parameters), timeout=5)
            assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
            store.read_page.assert_not_awaited()
            provider.recommend.assert_not_awaited()
            check_availability.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["connection", "timeout"])
def test_grpc_does_not_return_unchecked_items_when_availability_check_fails(failure) -> None:
    async def run():
        page = RecommendationPage(("item-1", "item-2"), "next")
        store = SimpleNamespace(read_page=AsyncMock(return_value=page))
        provider = SimpleNamespace(recommend=AsyncMock())

        async def unavailable(item_ids):
            if failure == "connection":
                raise asyncpg.PostgresConnectionError("database unavailable")
            await asyncio.Event().wait()

        check_availability = AsyncMock(side_effect=unavailable)
        pagination = Pagination(store, provider, check_availability, timeout_seconds=0.05)
        async with grpc_client(pagination) as client:
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await client.GetRecommendations(valid_request(), timeout=2)
            assert error.value.code() == grpc.StatusCode.UNAVAILABLE
            check_availability.side_effect = None
            check_availability.return_value = ("item-2",)
            response = await client.GetRecommendations(valid_request(), timeout=2)
            assert [item.item_id for item in response.items] == ["item-2"]
            assert response.next_page_token == page.next_page_token
            assert all(call.args == (page.item_ids,) for call in check_availability.await_args_list)
            provider.recommend.assert_not_awaited()

    asyncio.run(run())
