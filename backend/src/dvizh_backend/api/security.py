"""HTTP authentication and cross-origin guards."""

import asyncio
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from dvizh_backend.config import Settings, get_settings
from dvizh_backend.services.account_gateway import (
    AccountCommandError,
    AdminAccount,
    fetch_current_account,
)


def require_write_origin(request: Request, detail: str, *, scheme: str | None = None) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    try:
        parsed = urlsplit(origin)
    except ValueError:
        raise HTTPException(403, "Invalid request origin") from None
    if (
        parsed.netloc.lower() != request.headers.get("host", "").lower()
        or parsed.scheme not in ("http", "https")
        or (scheme is not None and parsed.scheme != scheme)
        or parsed.username is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(403, detail)


async def _require_write_actor(
    request: Request, settings: Settings, *, allow_legacy_origin: bool = False
) -> UUID:
    token = request.cookies.get("dvizh_access")
    if not token:
        raise HTTPException(401, "Authentication required")
    write_header = request.headers.get("x-dvizh-account")
    scheme = None
    if write_header != "1":
        if write_header is not None or not allow_legacy_origin or not request.headers.get("origin"):
            raise HTTPException(403, "Account write header required")
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    require_write_origin(request, "Cross-origin account writes are forbidden", scheme=scheme)
    account = await asyncio.to_thread(fetch_current_account, settings.auth_url, token)
    return account.id


async def require_account_write(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> UUID:
    return await _require_write_actor(request, settings)


async def require_participation_write(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> UUID:
    return await _require_write_actor(request, settings, allow_legacy_origin=True)


async def get_occurrence_viewer(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    occurrence_id: UUID | None = None,
) -> UUID | None:
    token = request.cookies.get("dvizh_access")
    if occurrence_id is None or not token:
        return None
    account = await asyncio.to_thread(fetch_current_account, settings.auth_url, token)
    return account.id


AccountWriteActor = Annotated[UUID, Depends(require_account_write)]
ParticipationWriteActor = Annotated[UUID, Depends(require_participation_write)]
OccurrenceViewer = Annotated[UUID | None, Depends(get_occurrence_viewer)]


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
        require_write_origin(request, "Cross-origin admin requests are forbidden")
    try:
        account = await asyncio.to_thread(fetch_current_account, settings.auth_url, token)
    except AccountCommandError as error:
        raise HTTPException(error.status_code, str(error)) from None
    if account.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return account
