from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .database_service import DatabaseService


def get_database_service(request: Request) -> DatabaseService:
    return request.app.state.database_service


async def get_db_session(
    database_service: Annotated[DatabaseService, Depends(get_database_service)],
) -> AsyncIterator[AsyncSession]:
    async with database_service.session() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
