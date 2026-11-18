from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_auth.config import get_settings
from dvizh_auth.database import Database
from dvizh_auth.models import Account
from dvizh_auth.repository import AccountRepository
from dvizh_auth.services.session_service import InvalidSessionError, SessionService


def get_database(request: Request) -> Database:
    return request.app.state.database


async def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async with database.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


async def require_account(request: Request, session: SessionDep) -> Account:
    try:
        return await SessionService(get_settings()).current_account(
            request.cookies.get("dvizh_access", ""), AccountRepository(session)
        )
    except InvalidSessionError:
        raise HTTPException(status_code=401, detail="Authentication required") from None


CurrentAccount = Annotated[Account, Depends(require_account)]


async def require_admin(account: CurrentAccount) -> Account:
    if account.role.name != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return account


def require_account_write(request: Request) -> None:
    if request.headers.get("x-dvizh-account") != "1":
        raise HTTPException(status_code=403, detail="Account write header required")
    require_same_origin(request)


def require_admin_write(request: Request) -> None:
    if request.headers.get("x-dvizh-admin") != "1":
        raise HTTPException(status_code=403, detail="Admin write header required")
    require_same_origin(request)


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid request origin") from None
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.lower() != request.headers.get("host", "").lower()
            or parsed.username is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise HTTPException(status_code=403, detail="Cross-origin account writes are forbidden")
