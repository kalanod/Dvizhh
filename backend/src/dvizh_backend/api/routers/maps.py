from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from dvizh_backend.api.dependencies import (
    MapsServiceDep,
    get_discovery_viewer,
    get_timezone_service,
)
from dvizh_backend.api.schemas.maps import MapClientError
from dvizh_backend.api.schemas.timezone import EventTimezoneRequest, EventTimezoneResponse
from dvizh_backend.services.event_timezone_service import EventTimezoneService

router = APIRouter(prefix="/api/maps", tags=["maps"])


@router.post("/timezone", summary="Определить часовой пояс мероприятия.")
async def event_timezone(
    body: EventTimezoneRequest,
    response: Response,
    viewer_id: Annotated[UUID | None, Depends(get_discovery_viewer)],
    service: Annotated[EventTimezoneService, Depends(get_timezone_service)],
) -> EventTimezoneResponse:
    if body.user_id is not None and body.user_id != viewer_id:
        raise HTTPException(403, "Viewer must match the authenticated account")
    response.headers["Cache-Control"] = "no-store"
    return await service.resolve(body.model_copy(update={"user_id": viewer_id}))


@router.post("/client-error", status_code=204, summary="Ошибка карты из браузера в логи backend.")
async def client_error(body: MapClientError, service: MapsServiceDep) -> Response:
    service.report_client_error(stage=body.stage, online=body.online)
    return Response(status_code=204)


@router.get("/config", summary="Ключ для отображения Яндекс Карт в браузере.")
async def maps_config(service: MapsServiceDep, response: Response) -> dict[str, str | bool]:
    response.headers["Cache-Control"] = "no-store"
    return service.configuration()


@router.get("/suggest", summary="Подсказки адресов и заведений Яндекса.")
async def suggest(
    request: Request,
    response: Response,
    service: MapsServiceDep,
    text: Annotated[str, Query(min_length=3, max_length=500)],
    city: Annotated[str, Query(max_length=120)] = "",
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> list[dict[str, str | None]]:
    response.headers["Cache-Control"] = "no-store"
    return await service.suggest(
        text, city, latitude, longitude,
        request.headers.get("referer", str(request.base_url)),
    )


@router.get("/geocode", summary="Определить место по адресу, подсказке или координатам.")
async def geocode(
    request: Request,
    response: Response,
    service: MapsServiceDep,
    query: Annotated[str, Query(max_length=500)] = "",
    uri: Annotated[str, Query(max_length=4000)] = "",
) -> dict[str, str | None]:
    response.headers["Cache-Control"] = "no-store"
    return await service.geocode(
        query, uri, request.headers.get("referer", str(request.base_url)),
    )
