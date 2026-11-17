"""HTTP authentication and cross-origin guards for administrative endpoints."""

import asyncio
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request

from dvizh_backend.config import Settings, get_settings
from dvizh_backend.services.account_gateway import (
    AccountCommandError,
    AdminAccount,
    fetch_current_account,
)


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
        if origin:
            try:
                parsed = urlsplit(origin)
            except ValueError:
                raise HTTPException(403, "Invalid request origin") from None
            if (
                parsed.netloc.lower() != request.headers.get("host", "").lower()
                or parsed.scheme not in ("http", "https")
                or parsed.username is not None
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
            ):
                raise HTTPException(403, "Cross-origin admin requests are forbidden")
    try:
        account = await asyncio.to_thread(fetch_current_account, settings.auth_url, token)
    except AccountCommandError as error:
        raise HTTPException(error.status_code, str(error)) from None
    if account.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return account
