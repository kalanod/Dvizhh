"""Authenticate administrators through the account service, never client-supplied IDs."""

import asyncio
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, StrictBool, ValidationError

from ..config import Settings, get_settings


class AdminAccount(BaseModel):
    id: UUID
    is_admin: StrictBool


def _fetch_account(auth_url: str, token: str) -> AdminAccount:
    request = UrlRequest(
        f"{auth_url.rstrip('/')}/api/auth/me", headers={"Cookie": f"dvizh_access={token}"}
    )
    try:
        with urlopen(request, timeout=5) as response:
            return AdminAccount.model_validate_json(response.read(16384))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(401, "Authentication required") from None
        raise HTTPException(503, "Authentication service unavailable") from None
    except (URLError, TimeoutError, OSError, ValidationError):
        raise HTTPException(503, "Authentication service unavailable") from None


async def require_admin(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> AdminAccount:
    token = request.cookies.get("dvizh_access")
    if not token:
        raise HTTPException(401, "Authentication required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # A non-simple header forces a browser preflight for cross-origin writes.
        if request.headers.get("x-dvizh-admin") != "1":
            raise HTTPException(403, "X-Dvizh-Admin: 1 header required")
        origin = request.headers.get("origin")
        if origin and (
            urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower()
            or urlsplit(origin).scheme not in ("http", "https")
        ):
            raise HTTPException(403, "Cross-origin admin requests are forbidden")
    account = await asyncio.to_thread(_fetch_account, settings.auth_url, token)
    if not account.is_admin:
        raise HTTPException(403, "Administrator access required")
    return account
