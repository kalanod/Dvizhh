"""Read-only discovery endpoint; actors come from the verified account cookie."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from dvizh_backend.api.dependencies import get_discovery_service, get_discovery_viewer
from dvizh_backend.api.schemas.discovery import (
    DiscoveryBootstrapRequest,
    DiscoveryBootstrapResponse,
    DiscoveryRequest,
    DiscoveryResponse,
)
from dvizh_backend.services.discovery_service import EventDiscoveryService

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/discovery/bootstrap", summary="Ближайшая опорная точка для начальной камеры.")
async def bootstrap(
    body: DiscoveryBootstrapRequest,
    response: Response,
    service: Annotated[EventDiscoveryService, Depends(get_discovery_service)],
    viewer_id: Annotated[UUID | None, Depends(get_discovery_viewer)],
) -> DiscoveryBootstrapResponse:
    if body.filters.viewer_id is not None and body.filters.viewer_id != viewer_id:
        raise HTTPException(403, "Viewer must match the authenticated account")
    if body.filters.friends_of is not None and body.filters.friends_of != viewer_id:
        raise HTTPException(403, "Friend ranking requires your authenticated account")
    response.headers["Cache-Control"] = "private, no-store"
    return await service.bootstrap(body, viewer_id)


@router.post("/discovery", summary="Единая географическая выдача карты и ленты.")
async def discovery(
    body: DiscoveryRequest,
    response: Response,
    service: Annotated[EventDiscoveryService, Depends(get_discovery_service)],
    viewer_id: Annotated[UUID | None, Depends(get_discovery_viewer)],
) -> DiscoveryResponse:
    if body.filters.viewer_id is not None and body.filters.viewer_id != viewer_id:
        raise HTTPException(403, "Viewer must match the authenticated account")
    if body.filters.friends_of is not None and body.filters.friends_of != viewer_id:
        raise HTTPException(403, "Friend ranking requires your authenticated account")
    response.headers["Cache-Control"] = "private, no-store"
    return await service.discover(body, viewer_id)
