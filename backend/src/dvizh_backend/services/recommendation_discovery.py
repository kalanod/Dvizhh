import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.api.schemas.discovery import DiscoveryFeed, DiscoveryFilters, DiscoveryRequest
from dvizh_backend.database.models import DiscoveryPage
from dvizh_backend.database.services.discovery import DiscoveryRepository
from dvizh_backend.database.services.discovery_state import DiscoveryState
from dvizh_backend.database.services.event_queries import EventQueryService
from dvizh_backend.services.discovery_tokens import DiscoveryContextError, DiscoveryTokens
from dvizh_backend.services.event_presenter import EventPresenter
from dvizh_backend.services.recommendation_client import (
    RecommendationClient,
    RecommendationPage,
    RecommendationUnavailable,
)

logger = logging.getLogger(__name__)


class RecommendationDiscovery:
    def __init__(
        self, session: AsyncSession, tokens: DiscoveryTokens, client: RecommendationClient | None
    ) -> None:
        self.session = session
        self.tokens = tokens
        self.client = client
        self.state = DiscoveryState(session)
        self.presenter = EventPresenter(EventQueryService(session))

    async def refresh(self, cursor: str, viewer_id: UUID) -> str:
        data = self.tokens.decode("cursor", cursor)
        if data.get("owner") != str(viewer_id):
            raise DiscoveryContextError("Выдача устарела. Обновите ленту.")
        session_id = UUID(data["recsys_session"])
        previous = await self.state.page(session_id, data["page"] - 1)
        if previous is None or (
            previous.next_page_token is None and previous.fallback_after is None
        ):
            raise DiscoveryContextError("Выдача устарела. Обновите ленту.")

        now = datetime.now(UTC)
        next_cursor = self.tokens.encode("cursor", data)
        if not await self.state.renew(session_id, now, now + timedelta(seconds=self.tokens.ttl)):
            raise DiscoveryContextError("Выдача устарела. Обновите ленту.")

        if self.client is not None and previous.next_page_token is not None:
            await self.session.commit()
            with suppress(RecommendationUnavailable):
                await self.client.refresh_session(user_id=viewer_id, session_id=session_id)
        return next_cursor

    async def feed(
        self,
        request: DiscoveryRequest,
        filters: DiscoveryFilters,
        viewer_id: UUID,
        as_of: datetime,
        context_key: str,
        session_id: UUID | None,
        position: int,
    ) -> DiscoveryFeed:
        now = datetime.now(UTC)
        previous = None
        saved = None
        if session_id is None:
            session_id = uuid4()
        else:
            if await self.state.active(session_id, now) is None:
                raise DiscoveryContextError("Выдача устарела. Обновите ленту.")
            previous = await self.state.page(session_id, position - 1)
            if previous is None or (
                previous.next_page_token is None and previous.fallback_after is None
            ):
                raise DiscoveryContextError("Выдача устарела. Обновите ленту.")
            saved = await self.state.page(session_id, position)

        fallback_after = previous.fallback_after if previous else None
        page_token = previous.next_page_token if previous else None
        recommendation = None
        failure = None
        if saved is None and self.client is not None and (position == 0 or page_token is not None):
            await self.session.commit()
            try:
                recommendation = await self._recommend(
                    self.client, request, filters, viewer_id, session_id, position, page_token
                )
            except RecommendationUnavailable as error:
                failure = error

        now = datetime.now(UTC)
        repository = DiscoveryRepository(self.session, filters, now, request.viewport)
        active = None
        if position > 0:
            active = await self.state.active(session_id, now, lock=True)
            if active is None:
                raise DiscoveryContextError("Выдача устарела. Обновите ленту.")
            saved = await self.state.page(session_id, position)

        is_new = saved is None
        if saved is not None:
            pairs = [(UUID(item_id), UUID(occurrence_id)) for item_id, occurrence_id in saved.items]
        elif recommendation is not None:
            pairs = [(item.item_id, item.occurrence_id) for item in recommendation.items]
            saved = DiscoveryPage(
                session_id=session_id,
                page=position,
                request_id=recommendation.request_id,
                next_page_token=recommendation.next_page_token,
            )
        else:
            if failure is not None:
                logger.info("Recommendation feed fallback: %s", failure)
            exclude = (
                await self.state.delivered_recommendations(session_id, position) if position else ()
            )
            rows, has_more = await repository.feed_by_publication(
                request.limit, fallback_after, exclude
            )
            pairs = [(row["event_id"], row["occurrence_id"]) for row in rows]
            saved = DiscoveryPage(
                session_id=session_id,
                page=position,
                fallback_after=rows[-1]["after"] if has_more and rows else None,
            )

        rows_by_pair = {
            (row.event.id, row.occurrence.id): row for row in await repository.eligible_rows(pairs)
        }
        items = await self.presenter.to_dtos(
            [rows_by_pair[pair] for pair in pairs if pair in rows_by_pair], viewer_id=viewer_id
        )
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.tokens.ttl)
        if active is None:
            await self.state.create(session_id, now, expires_at)
        else:
            active.expires_at = expires_at
        if is_new:
            saved.items = [[str(item.id), str(item.occurrence_id)] for item in items]
            self.state.save(saved)

        next_cursor = None
        if saved.next_page_token is not None or saved.fallback_after is not None:
            next_cursor = self.tokens.encode(
                "cursor",
                {
                    "context": context_key,
                    "as_of": as_of.isoformat(),
                    "recsys_session": str(session_id),
                    "page": position + 1,
                    "owner": str(viewer_id),
                },
            )
        return DiscoveryFeed(
            items=items,
            next_cursor=next_cursor,
            refresh_after_seconds=self.tokens.ttl // 2 if next_cursor else None,
            session_id=session_id if saved.request_id is not None else None,
            request_id=saved.request_id,
        )

    @staticmethod
    async def _recommend(
        client: RecommendationClient,
        request: DiscoveryRequest,
        filters: DiscoveryFilters,
        viewer_id: UUID,
        session_id: UUID,
        position: int,
        page_token: str | None,
    ) -> RecommendationPage:
        values = filters.model_dump(
            mode="json", exclude={"viewer_id", "friends_of"}, exclude_none=True
        )
        if request.viewport is not None:
            values["viewport"] = request.viewport.model_dump(
                include={"west", "south", "east", "north"}
            )
        return await client.get_page(
            user_id=viewer_id,
            session_id=session_id,
            request_id=uuid5(session_id, str(position)),
            filters=values,
            page_size=request.limit,
            page_token=page_token,
        )
