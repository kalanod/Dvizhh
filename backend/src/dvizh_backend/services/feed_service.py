"""Ranked feed: the order comes from the recommendation service, cards from the database."""

from uuid import UUID, uuid4

from dvizh_backend.dto.event import FeedPageDTO, FeedRanking

from .event_service import EventService
from .recommendation_gateway import GUEST_USER_ID, RecommendationGateway


class FeedInputError(ValueError):
    """The feed request is inconsistent (for example, only one coordinate)."""


class FeedService:
    """Joins two sources and adds no ranking of its own.

    * the recommendation service decides the order and paginates;
    * ``EventService`` turns the returned IDs into cards, keeping that order.
    """

    def __init__(self, events: EventService, recommendations: RecommendationGateway) -> None:
        self.events = events
        self.recommendations = recommendations

    async def get_page(
        self,
        *,
        viewer_id: UUID | None,
        ranking: FeedRanking | None,
        session_id: str | None,
        page_token: str | None,
        page_size: int,
        latitude: float | None,
        longitude: float | None,
    ) -> FeedPageDTO:
        if page_token is not None and session_id is None:
            raise FeedInputError("page_token передаётся вместе с session_id")
        if (latitude is None) != (longitude is None):
            raise FeedInputError("latitude и longitude передаются вместе")
        ranking = ranking or self.default_ranking(viewer_id)
        session_id = session_id or str(uuid4())
        context = {} if latitude is None else {"latitude": latitude, "longitude": longitude}

        page = await self.recommendations.get_page(
            user_id=self._user_id(viewer_id),
            session_id=session_id,
            ranking=ranking,
            context=context,
            page_size=page_size,
            page_token=page_token,
        )
        return FeedPageDTO(
            items=await self.events.list_by_ids(page.item_ids, viewer_id=viewer_id),
            ranking=ranking,
            session_id=session_id,
            next_page_token=page.next_page_token,
        )

    async def refresh(self, *, viewer_id: UUID | None, session_id: str) -> None:
        await self.recommendations.refresh(user_id=self._user_id(viewer_id), session_id=session_id)

    @staticmethod
    def default_ranking(viewer_id: UUID | None) -> FeedRanking:
        """Signed-in users get the personal feed; guests have no history to use."""
        return "relevance" if viewer_id is not None else "novelty"

    @staticmethod
    def _user_id(viewer_id: UUID | None) -> str:
        return str(viewer_id) if viewer_id is not None else GUEST_USER_ID
