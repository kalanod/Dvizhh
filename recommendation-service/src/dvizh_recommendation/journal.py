import asyncio
import hashlib
import json
from collections.abc import Sequence
from contextlib import suppress
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from .feedback_tables import recommendation_pages
from .recommendations import FeatureSnapshot, InvalidRequest, RecommendationQuery


class PageChanged(Exception):
    pass


class RecommendationJournal:
    def __init__(self, engine: AsyncEngine, *, timeout_seconds: float = 5) -> None:
        self.engine = engine
        self.timeout_seconds = timeout_seconds

    async def record(
        self,
        query: RecommendationQuery,
        session_id: str,
        request_id: str,
        item_ids: Sequence[str],
        snapshots: Sequence[FeatureSnapshot | None],
        *,
        page_size: int,
        page_token: str | None,
    ) -> None:
        with suppress(ValueError):
            request_id = str(UUID(request_id))
        parameters = json.dumps(
            [query.context, query.filters, page_size, page_token],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        parameters_hash = hashlib.sha256(parameters.encode()).hexdigest()
        snapshots = snapshots or (None,) * len(item_ids)
        items = [
            {"item_id": item_id} | (snapshot.model_dump(mode="json") if snapshot else {})
            for item_id, snapshot in zip(item_ids, snapshots, strict=True)
        ]
        page = recommendation_pages.c
        statement = (
            insert(recommendation_pages)
            .values(
                request_id=request_id,
                session_id=session_id,
                user_id=query.user_id,
                parameters_hash=parameters_hash,
                items=items,
            )
            .on_conflict_do_nothing(index_elements=[page.request_id])
            .returning(page.request_id)
        )
        async with asyncio.timeout(self.timeout_seconds), self.engine.begin() as connection:
            if await connection.scalar(statement) is not None:
                return
            recorded = (
                await connection.execute(
                    select(
                        and_(
                            page.session_id == session_id,
                            page.user_id == query.user_id,
                            page.parameters_hash == parameters_hash,
                        ).label("same_request"),
                        (page["items"] == items).label("same_items"),
                    ).where(page.request_id == request_id)
                )
            ).one_or_none()
            if recorded is None or not recorded.same_request:
                raise InvalidRequest("request_id was already used for a different page")
            if not recorded.same_items:
                raise PageChanged
