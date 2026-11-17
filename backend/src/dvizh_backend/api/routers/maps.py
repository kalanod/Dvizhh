from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from dvizh_backend.api.dependencies import MapsServiceDep
from dvizh_backend.api.schemas.maps import MapClientError

router = APIRouter(prefix="/api/maps", tags=["maps"])


@router.post("/client-error", status_code=204, summary="Ошибка карты из браузера в логи backend.")
async def client_error(body: MapClientError, request: Request, service: MapsServiceDep) -> Response:
    service.report_client_error(
        stage=body.stage, online=body.online, message=body.message,
        origin=request.headers.get("origin", request.headers.get("referer", "")),
    )
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
