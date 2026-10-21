from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..dto.event import EventDTO
from ..dto.media import MediaDTO, MediaSelectionDTO
from ..dto.user import ProfileDTO, UpdateProfileDTO
from ..services.dependencies import MediaServiceDep, SettingsDep, UserServiceDep
from ..services.media_errors import MediaTooLargeError

router = APIRouter(prefix="/api", tags=["media"])


@router.get("/media/config", summary="Ограничения загрузки изображений.")
async def media_config(settings: SettingsDep) -> dict[str, object]:
    return {
        "max_bytes": settings.media_max_mib * 1024 * 1024,
        "max_pixels": settings.media_max_pixels,
        "formats": ["JPEG", "PNG", "WEBP"],
    }


@router.post(
    "/media",
    status_code=201,
    summary="Загрузить JPEG, PNG или WebP.",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload_media(
    request: Request,
    user_id: UUID,
    media: MediaServiceDep,
    settings: SettingsDep,
    filename: Annotated[str | None, Query(max_length=255)] = None,
) -> MediaDTO:
    limit = settings.media_max_mib * 1024 * 1024
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length") from exc
        if size < 0:
            raise HTTPException(400, "Invalid Content-Length")
        if size > limit:
            raise MediaTooLargeError("Upload exceeds size limit")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise MediaTooLargeError("Upload exceeds size limit")
        data.extend(chunk)
    return await media.upload(user_id, bytes(data), filename)


@router.get("/media/{media_id}/content", summary="Получить изображение.")
async def media_content(
    media_id: UUID, media: MediaServiceDep, viewer_id: UUID | None = None
) -> Response:
    data, content_type = await media.content(media_id, viewer_id)
    return Response(
        data,
        media_type=content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.put("/users/{user_id}/avatar", summary="Назначить или убрать аватар.")
async def set_avatar(
    user_id: UUID, body: MediaSelectionDTO, users: UserServiceDep, media: MediaServiceDep
) -> ProfileDTO:
    if body.media_id is not None:
        await media.require_owned(body.media_id, user_id)
    return await users.update_profile(user_id, UpdateProfileDTO(avatar_media_id=body.media_id))


@router.put("/events/{event_id}/cover", summary="Назначить или убрать обложку.")
async def set_cover(
    event_id: UUID,
    actor_id: UUID,
    body: MediaSelectionDTO,
    media: MediaServiceDep,
) -> EventDTO:
    return await media.set_cover(event_id, actor_id, body.media_id)
