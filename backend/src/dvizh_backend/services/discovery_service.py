"""Single application pipeline for map aggregates and paginated event cards."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.api.schemas.discovery import (
    DiscoveryFeed,
    DiscoveryMap,
    DiscoveryRequest,
    DiscoveryResponse,
    MapBounds,
    MapItem,
    MapViewport,
)
from dvizh_backend.config import Settings
from dvizh_backend.database.services.discovery import DiscoveryRepository
from dvizh_backend.database.services.event_queries import EventQueryService
from dvizh_backend.services.discovery_tokens import (
    DiscoveryContextError,
    DiscoveryTokens,
    fingerprint,
)
from dvizh_backend.services.event_presenter import EventPresenter
from dvizh_backend.services.map_clustering import cluster_map
from dvizh_backend.services.user_service import UserService


class EventDiscoveryService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.tokens = DiscoveryTokens(
            settings.discovery_token_secret, settings.discovery_token_ttl_seconds
        )
        self.queries = EventQueryService(session)
        self.presenter = EventPresenter(self.queries)

    async def discover(
        self, request: DiscoveryRequest, viewer_id: UUID | None,
    ) -> DiscoveryResponse:
        filters = request.filters.model_copy(
            update={"q": request.filters.q.strip(), "viewer_id": viewer_id}
        )
        if viewer_id is not None:
            await UserService(self.session).get_profile(viewer_id)
        filter_key = fingerprint(filters.model_dump(mode="json"))
        as_of = datetime.now(UTC)
        scope = request.viewport
        cell = None
        if request.selection_token:
            selection = self.tokens.decode("cluster", request.selection_token)
            if selection.get("filters") != filter_key:
                raise DiscoveryContextError("Фильтры изменились. Выберите группу заново.")
            scope = MapViewport.model_validate(selection["viewport"])
            cell = selection["cell"]
            as_of = datetime.fromisoformat(selection["as_of"])
        context_key = fingerprint(
            {
                "filters": filter_key,
                "scope": scope.model_dump(mode="json") if scope else None,
                "cell": cell,
                "sort": request.sort,
            }
        )
        after = None
        if request.cursor:
            cursor = self.tokens.decode("cursor", request.cursor)
            if cursor.get("context") != context_key:
                raise DiscoveryContextError("Порядок или область выдачи изменились.")
            as_of = datetime.fromisoformat(cursor["as_of"])
            after = cursor["after"]
        feed_repository = DiscoveryRepository(self.session, filters, as_of, scope)
        center = scope.center if scope else None
        rows, total, has_more = await feed_repository.feed(
            request.sort,
            center,
            request.limit,
            after,
            cell,
        )
        occurrences = [row["occurrence_id"] for row in rows]
        cards = await self.queries.get_occurrences(occurrences)
        by_occurrence = {card.occurrence.id: card for card in cards}
        items = await self.presenter.to_dtos(
            [by_occurrence[key] for key in occurrences], viewer_id=viewer_id
        )
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = self.tokens.encode(
                "cursor",
                {
                    "context": context_key,
                    "as_of": as_of.isoformat(),
                    "after": [
                        int(last["friends_rank"]),
                        float(last["score"]),
                        last["starts_at"].isoformat(),
                        str(last["event_id"]),
                    ],
                },
            )
        map_result = None
        if request.include_map and request.viewport is not None:
            map_repository = DiscoveryRepository(self.session, filters, as_of, request.viewport)
            groups = await cluster_map(map_repository, request.viewport.zoom)
            markers = []
            for group in groups:
                node = [group["level"], int(group["x"]), int(group["y"])]
                count = int(group["count"])
                token = None
                if count > 1:
                    token = self.tokens.encode(
                        "cluster",
                        {
                            "filters": filter_key,
                            "viewport": request.viewport.model_dump(mode="json"),
                            "cell": node,
                            "as_of": as_of.isoformat(),
                        },
                    )
                markers.append(
                    MapItem(
                        id=f"cell:{node[0]}:{node[1]}:{node[2]}",
                        type="event" if count == 1 else "cluster",
                        count=count,
                        latitude=float(group["latitude"]),
                        longitude=float(group["longitude"]),
                        event_id=UUID(group["event_id"]) if count == 1 else None,
                        selection_token=token,
                        bounds=MapBounds(
                            **{key: float(group[key]) for key in ["west", "south", "east", "north"]}
                        ),
                    )
                )
            map_result = DiscoveryMap(
                items=markers, total_events=sum(item.count for item in markers)
            )
        return DiscoveryResponse(
            as_of=as_of,
            map=map_result,
            feed=DiscoveryFeed(items=items, total_events=total, next_cursor=next_cursor),
        )
