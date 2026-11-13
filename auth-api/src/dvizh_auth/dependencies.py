from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request

from .config import get_settings
from .database import SessionDep
from .models import Account


async def require_account(request: Request, session: SessionDep) -> Account:
    settings = get_settings()
    try:
        payload = jwt.decode(
            request.cookies.get("dvizh_access", ""),
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        account_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=401, detail="Authentication required") from None
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return account


CurrentAccount = Annotated[Account, Depends(require_account)]


async def require_admin(account: CurrentAccount) -> Account:
    if account.role.name != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return account


def require_account_write(request: Request) -> None:
    if request.headers.get("x-dvizh-account") != "1":
        raise HTTPException(status_code=403, detail="Account write header required")
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
