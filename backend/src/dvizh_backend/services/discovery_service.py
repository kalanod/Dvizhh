"""Single application pipeline for map aggregates and paginated event cards."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.api.schemas.discovery import (
    DiscoveryAnchor,
    DiscoveryBootstrapRequest,
    DiscoveryBootstrapResponse,
    DiscoveryFeed,
    DiscoveryFilters,
    DiscoveryMap,
    DiscoveryRequest,
    DiscoveryResponse,
    MapBounds,
    MapItem,
    MapPoint,
    MapViewport,
)
from dvizh_backend.config import Settings
from dvizh_backend.database.models.enums import MapMarkerPriority
from dvizh_backend.database.services.discovery import DiscoveryRepository
from dvizh_backend.database.services.event_queries import EventQueryService
from dvizh_backend.database.services.exceptions import EventSortError
from dvizh_backend.services.discovery_tokens import (
    DiscoveryContextError,
    DiscoveryTokens,
    fingerprint,
)
from dvizh_backend.services.event_presenter import EventPresenter
from dvizh_backend.services.map_clustering import cluster_map
from dvizh_backend.services.place_geocoding import ProfileCityGeocoder
from dvizh_backend.services.recommendation_client import RecommendationClient
from dvizh_backend.services.recommendation_discovery import RecommendationDiscovery
from dvizh_backend.services.user_service import UserService


class EventDiscoveryService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        cities: ProfileCityGeocoder | None = None,
        *,
        recommendation_client: RecommendationClient | None = None,
        manage_snapshot: bool = False,
    ):
        self.cities = cities or ProfileCityGeocoder.from_settings(settings)
        self.session = session
        self.tokens = DiscoveryTokens(
            settings.discovery_token_secret, settings.discovery_token_ttl_seconds
        )
        self.queries = EventQueryService(session)
        self.presenter = EventPresenter(self.queries)
        self.recommendation_client = recommendation_client
        self.manage_snapshot = manage_snapshot

    async def refresh_cursor(self, cursor: str, viewer_id: UUID) -> str:
        recommendations = RecommendationDiscovery(
            self.session, self.tokens, self.recommendation_client
        )
        return await recommendations.refresh(cursor, viewer_id)

    async def bootstrap(
        self, request: DiscoveryBootstrapRequest, viewer_id: UUID | None,
    ) -> DiscoveryBootstrapResponse:
        if self.manage_snapshot:
            await DiscoveryRepository.begin_snapshot(self.session)
        if viewer_id:
            await UserService(self.session).get_profile(viewer_id)
        filters = request.filters.model_copy(
            update={"q": request.filters.q.strip(), "viewer_id": viewer_id}
        )
        repository = DiscoveryRepository(self.session, filters, datetime.now(UTC), None)
        nearest = await repository.nearest(request.origin)
        anchor = DiscoveryAnchor(
            event_id=nearest["event_id"],
            point=MapPoint(latitude=nearest["latitude"], longitude=nearest["longitude"]),
        ) if nearest else None
        return DiscoveryBootstrapResponse(nearest=anchor)

    async def discover(
        self,
        request: DiscoveryRequest,
        viewer_id: UUID | None,
    ) -> DiscoveryResponse:
        cursor = self.tokens.decode("cursor", request.cursor) if request.cursor else None
        managed = (
            "recsys_session" in cursor
            if cursor is not None
            else (
                viewer_id is not None
                and self.recommendation_client is not None
                and request.sort == "relevance"
                and request.filters.friends_of is None
                and request.selection_token is None
            )
        )
        if self.manage_snapshot and not managed:
            await DiscoveryRepository.begin_snapshot(self.session)
        filters = request.filters.model_copy(
            update={"q": request.filters.q.strip(), "viewer_id": viewer_id}
        )
        profile = await UserService(self.session).get_profile(viewer_id) if viewer_id else None
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
                "origin": request.origin.model_dump(mode="json") if request.origin else None,
                "ordering_version": 2,
            }
        )
        if managed:
            context_key = fingerprint({"context": context_key, "limit": request.limit})
        if cursor is not None:
            if cursor.get("context") != context_key:
                raise DiscoveryContextError("Порядок или область выдачи изменились.")
            as_of = datetime.fromisoformat(cursor["as_of"])
        if managed and viewer_id is not None:
            feed = await RecommendationDiscovery(
                self.session, self.tokens, self.recommendation_client
            ).feed(
                request,
                filters,
                viewer_id,
                as_of,
                context_key,
                UUID(cursor["recsys_session"]) if cursor is not None else None,
                cursor["page"] if cursor is not None else 0,
            )
        else:
            center = scope.center if scope else request.origin
            ranking = cursor["ranking"] if cursor is not None else None
            if (
                request.sort == "distance"
                and center is None
                and ranking is None
                and profile
                and profile.city
            ):
                city = await self.cities.coordinates(profile.city)
                if city:
                    center = MapPoint(latitude=city[0].latitude, longitude=city[0].longitude)
            feed = await self._catalog_feed(
                request, filters, as_of, scope, center, cell, context_key,
                cursor["after"] if cursor is not None else None, ranking,
            )
        map_result = await self._map(request, filters, as_of, filter_key)
        return DiscoveryResponse(as_of=as_of, map=map_result, feed=feed)

    async def _catalog_feed(
        self,
        request: DiscoveryRequest,
        filters: DiscoveryFilters,
        as_of: datetime,
        scope: MapViewport | None,
        center: MapPoint | None,
        cell: list[int] | None,
        context_key: str,
        after,
        ranking,
    ) -> DiscoveryFeed:
        feed_repository = DiscoveryRepository(self.session, filters, as_of, scope)
        try:
            rows, has_more = await feed_repository.feed(
                request.sort,
                center,
                request.limit,
                after,
                cell,
                ranking=ranking,
            )
        except EventSortError as error:
            if request.cursor:
                raise DiscoveryContextError(str(error)) from error
            raise
        total = (
            await feed_repository.count(cell)
            if cell is not None or request.sort != "relevance" else None
        )
        occurrences = [row["occurrence_id"] for row in rows]
        cards = await self.queries.get_occurrences(occurrences)
        by_occurrence = {card.occurrence.id: card for card in cards}
        items = await self.presenter.to_dtos(
            [by_occurrence[key] for key in occurrences], viewer_id=filters.viewer_id
        )
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = self.tokens.encode(
                "cursor",
                {
                    "context": context_key,
                    "as_of": as_of.isoformat(),
                    "after": last["after"],
                    "ranking": feed_repository.ranking,
                },
            )
        return DiscoveryFeed(items=items, total_events=total, next_cursor=next_cursor)

    async def _map(
        self, request: DiscoveryRequest, filters: DiscoveryFilters, as_of: datetime, filter_key: str
    ) -> DiscoveryMap | None:
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
                        state=MapMarkerPriority(group.get("marker_priority", 0)).name.lower(),
                        title=group.get("title") if count == 1 else None,
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
        return map_result
