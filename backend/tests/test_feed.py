"""Ranked feed: FeedService, the gRPC gateway and the HTTP endpoints, without a database."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import grpc
import httpx
import pytest

from dvizh_backend.database.services.event_queries import EventQueryService
from dvizh_backend.dto.event import FeedPageDTO
from dvizh_backend.main import app
from dvizh_backend.services.dependencies import get_feed_service
from dvizh_backend.services.feed_service import FeedInputError, FeedService
from dvizh_backend.services.recommendation_gateway import (
    GUEST_USER_ID,
    RecommendationError,
    RecommendationGateway,
    RecommendationPage,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
FIRST = UUID("00000000-0000-0000-0000-00000000000a")
SECOND = UUID("00000000-0000-0000-0000-00000000000b")
THIRD = UUID("00000000-0000-0000-0000-00000000000c")


def feed_service(page: RecommendationPage) -> tuple[FeedService, AsyncMock, AsyncMock]:
    recommendations = MagicMock()
    recommendations.get_page = AsyncMock(return_value=page)
    events = MagicMock()
    events.list_by_ids = AsyncMock(return_value=[])
    return FeedService(events, recommendations), recommendations.get_page, events.list_by_ids


def get_page(service: FeedService, **overrides) -> FeedPageDTO:
    arguments = {
        "viewer_id": None,
        "ranking": None,
        "session_id": None,
        "page_token": None,
        "page_size": 20,
        "latitude": None,
        "longitude": None,
    }
    return asyncio.run(service.get_page(**{**arguments, **overrides}))


@pytest.mark.parametrize(
    ("viewer_id", "user_id", "ranking"),
    [(None, GUEST_USER_ID, "novelty"), (USER_ID, str(USER_ID), "relevance")],
)
def test_feed_starts_session_with_default_ranking(viewer_id, user_id, ranking):
    service, recommend, list_by_ids = feed_service(RecommendationPage([SECOND, FIRST], "next"))

    page = get_page(service, viewer_id=viewer_id)

    call = recommend.await_args.kwargs
    assert call["user_id"] == user_id
    assert call["ranking"] == ranking
    assert call["context"] == {}
    assert call["page_token"] is None
    assert page.ranking == ranking
    assert page.session_id == call["session_id"]
    assert page.next_page_token == "next"
    # Cards are requested in the ranked order.
    list_by_ids.assert_awaited_once_with([SECOND, FIRST], viewer_id=viewer_id)


def test_feed_continues_session_and_passes_coordinates():
    service, recommend, _ = feed_service(RecommendationPage([], None))

    page = get_page(
        service,
        ranking="distance",
        session_id="session",
        page_token="token",
        latitude=59.93,
        longitude=30.31,
    )

    call = recommend.await_args.kwargs
    assert call["session_id"] == "session"
    assert call["page_token"] == "token"
    assert call["context"] == {"latitude": 59.93, "longitude": 30.31}
    assert page.next_page_token is None


@pytest.mark.parametrize(
    "overrides",
    [{"latitude": 59.93}, {"longitude": 30.31}, {"page_token": "token"}],
)
def test_feed_rejects_inconsistent_requests_before_calling_the_service(overrides):
    service, recommend, _ = feed_service(RecommendationPage([], None))

    with pytest.raises(FeedInputError):
        get_page(service, **overrides)

    recommend.assert_not_awaited()


def test_list_by_ids_keeps_ranked_order_and_skips_missing_events():
    queries = EventQueryService(MagicMock())
    rows = [SimpleNamespace(event=SimpleNamespace(id=event_id)) for event_id in (FIRST, THIRD)]
    queries._fetch = AsyncMock(return_value=rows)

    result = asyncio.run(queries.list_by_ids([THIRD, SECOND, FIRST]))

    assert [row.event.id for row in result] == [THIRD, FIRST]
    assert asyncio.run(queries.list_by_ids([])) == []


def call_gateway(stub: SimpleNamespace, **overrides) -> RecommendationPage:
    """A gRPC channel belongs to an event loop, so the gateway is created inside it."""
    arguments = {
        "user_id": "u",
        "session_id": "s",
        "ranking": "x",
        "context": {},
        "page_size": 20,
        "page_token": None,
    }

    async def scenario() -> RecommendationPage:
        gateway = RecommendationGateway("localhost:1", timeout_seconds=1)
        gateway._stub = stub
        try:
            return await gateway.get_page(**{**arguments, **overrides})
        finally:
            await gateway.close()

    return asyncio.run(scenario())


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (grpc.StatusCode.INVALID_ARGUMENT, 422),
        (grpc.StatusCode.FAILED_PRECONDITION, 409),
        (grpc.StatusCode.PERMISSION_DENIED, 403),
        (grpc.StatusCode.UNIMPLEMENTED, 400),
        (grpc.StatusCode.UNAVAILABLE, 503),
        (grpc.StatusCode.DEADLINE_EXCEEDED, 503),
        (grpc.StatusCode.INTERNAL, 502),
    ],
)
def test_gateway_translates_grpc_errors_to_http(code, status_code):
    rpc_error = grpc.aio.AioRpcError(
        code, grpc.aio.Metadata(), grpc.aio.Metadata(), "Unknown ranking 'x'"
    )

    with pytest.raises(RecommendationError) as error:
        call_gateway(SimpleNamespace(GetRecommendations=AsyncMock(side_effect=rpc_error)))

    assert error.value.status_code == status_code
    if code is grpc.StatusCode.INVALID_ARGUMENT:
        # The service explains what was wrong with the request.
        assert str(error.value) == "Unknown ranking 'x'"


def test_gateway_builds_request_and_reads_response():
    response = SimpleNamespace(
        items=[SimpleNamespace(item_id=str(SECOND)), SimpleNamespace(item_id=str(FIRST))],
        HasField=lambda field: False,
    )
    call = AsyncMock(return_value=response)

    page = call_gateway(
        SimpleNamespace(GetRecommendations=call),
        ranking="distance",
        context={"latitude": 59.93, "longitude": 30.31},
        page_size=5,
    )

    request = call.await_args.args[0]
    assert request.ranking == "distance"
    assert not request.HasField("page_token")
    assert request.context["latitude"].number_value == 59.93
    assert request.request_id
    assert page == RecommendationPage([SECOND, FIRST], None)


def request_feed(service, method: str, path: str) -> httpx.Response:
    async def scenario() -> httpx.Response:
        overrides = dict(app.dependency_overrides)
        app.dependency_overrides[get_feed_service] = lambda: service
        try:
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
                return await http.request(method, path)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides)

    return asyncio.run(scenario())


def test_feed_endpoint_passes_query_parameters():
    service = MagicMock()
    service.get_page = AsyncMock(
        return_value=FeedPageDTO(items=[], ranking="distance", session_id="s")
    )

    response = request_feed(
        service,
        "GET",
        f"/api/events/feed?ranking=distance&latitude=59.93&longitude=30.31&limit=5"
        f"&viewer_id={USER_ID}",
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "ranking": "distance",
        "session_id": "s",
        "next_page_token": None,
    }
    service.get_page.assert_awaited_once_with(
        viewer_id=USER_ID,
        ranking="distance",
        session_id=None,
        page_token=None,
        page_size=5,
        latitude=59.93,
        longitude=30.31,
    )


@pytest.mark.parametrize(
    "query", ["ranking=popularity", "limit=0", "limit=101", "latitude=91&longitude=0"]
)
def test_feed_endpoint_validates_parameters(query):
    service = MagicMock()
    service.get_page = AsyncMock()

    response = request_feed(service, "GET", f"/api/events/feed?{query}")

    assert response.status_code == 422
    service.get_page.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (RecommendationError(503, "Рекомендации временно недоступны"), 503),
        (RecommendationError(409, "Лента устарела, обновите её"), 409),
        (FeedInputError("latitude и longitude передаются вместе"), 422),
    ],
)
def test_feed_endpoint_returns_errors_as_json(error, status_code):
    service = MagicMock()
    service.get_page = AsyncMock(side_effect=error)

    response = request_feed(service, "GET", "/api/events/feed")

    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}


def test_refresh_endpoint_extends_session():
    service = MagicMock()
    service.refresh = AsyncMock()

    response = request_feed(service, "POST", f"/api/events/feed/s1/refresh?viewer_id={USER_ID}")

    assert response.status_code == 204
    service.refresh.assert_awaited_once_with(viewer_id=USER_ID, session_id="s1")
