import asyncio
import hashlib
import warnings
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dvizh_backend.config import Settings
from dvizh_backend.database.models import Event, EventMedia, MediaAsset, Profile
from dvizh_backend.database.models.enums import (
    EventMediaRole,
    EventStatus,
    MediaStatus,
    ProfileStatus,
)
from dvizh_backend.database.services.access import can_view_event_media
from dvizh_backend.database.services.exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
)
from dvizh_backend.dto.event import EventDTO
from dvizh_backend.dto.media import MediaDTO
from dvizh_backend.storage import MediaStorage

from .event_service import EventService
from .media_errors import InvalidImageError, MediaTooLargeError, MediaUnavailableError
from .user_service import UserService


def normalize_image(data: bytes, *, max_pixels: int, max_bytes: int) -> tuple[bytes, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if (
                    source.format not in {"JPEG", "PNG", "WEBP"}
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise InvalidImageError("Use a static JPEG, PNG or WebP image")
                if source.width * source.height > max_pixels:
                    raise MediaTooLargeError("Image has too many pixels")
                source.load()
                image = ImageOps.exif_transpose(source)
                image = image.convert(
                    "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
                )
                image.info.clear()
                image.thumbnail((4096, 4096))
                output = BytesIO()
                image.save(output, format="WEBP", quality=85)
                result = output.getvalue()
                if len(result) > max_bytes:
                    raise MediaTooLargeError("Processed image exceeds upload limit")
                return result, image.width, image.height
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Invalid or corrupt image") from exc
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise MediaTooLargeError("Image has too many pixels") from exc


class MediaService:
    def __init__(self, session: AsyncSession, storage: MediaStorage, settings: Settings) -> None:
        self.session, self.storage, self.settings = session, storage, settings

    async def upload(self, user_id: UUID, data: bytes, filename: str | None) -> MediaDTO:
        await UserService(self.session).get_profile(user_id)
        limit = self.settings.media_max_mib * 1024 * 1024
        if len(data) > limit:
            raise MediaTooLargeError("Upload exceeds size limit")
        normalized, width, height = await asyncio.to_thread(
            normalize_image, data, max_pixels=self.settings.media_max_pixels, max_bytes=limit
        )
        media_id = uuid4()
        key = f"images/{user_id}/{media_id}.webp"
        media = MediaAsset(
            id=media_id,
            uploaded_by_user_id=user_id,
            bucket=self.settings.minio_bucket,
            object_key=key,
            original_filename=filename,
            content_type="image/webp",
            size_bytes=len(normalized),
            checksum_sha256=hashlib.sha256(normalized).hexdigest(),
            width=width,
            height=height,
            status=MediaStatus.UPLOADING,
        )
        self.session.add(media)
        await self.session.flush()

        async def cleanup() -> None:
            await self.storage.remove(self.settings.minio_bucket, key)

        self.session.info.setdefault("rollback_callbacks", []).append(cleanup)
        await self.storage.put(media.bucket, media.object_key, normalized)
        media.status, media.ready_at = MediaStatus.READY, datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(media)
        return MediaDTO.model_validate(media)

    async def require_owned(self, media_id: UUID, user_id: UUID) -> MediaAsset:
        media = await self.session.get(MediaAsset, media_id)
        if media is None:
            raise EntityNotFoundError("Media not found")
        if media.uploaded_by_user_id != user_id:
            raise PermissionDeniedError("Media belongs to another user")
        if media.status != MediaStatus.READY or media.deleted_at is not None:
            raise MediaUnavailableError("Media is not ready")
        return media

    async def content(self, media_id: UUID, viewer_id: UUID | None) -> tuple[bytes, str]:
        media = await self.session.get(MediaAsset, media_id)
        if media is None or media.status != MediaStatus.READY or media.deleted_at is not None:
            raise EntityNotFoundError("Media not found")
        if viewer_id is not None:
            await UserService(self.session).get_profile(viewer_id)
        allowed = media.uploaded_by_user_id == viewer_id
        if not allowed:
            allowed = bool(
                await self.session.scalar(
                    select(
                        exists().where(
                            Profile.avatar_media_id == media_id,
                            Profile.deleted_at.is_(None),
                            Profile.status == ProfileStatus.ACTIVE,
                        )
                    )
                )
            )
        if not allowed:
            events = (
                await self.session.scalars(
                    select(Event)
                    .join(EventMedia, EventMedia.event_id == Event.id)
                    .where(EventMedia.media_id == media_id, Event.deleted_at.is_(None))
                )
            ).all()
            for event in events:
                if await can_view_event_media(self.session, event, viewer_id):
                    allowed = True
                    break
        if not allowed:
            raise PermissionDeniedError("Media is not publicly available")
        return (
            await self.storage.read(
                media.bucket, media.object_key, self.settings.media_max_mib * 1024 * 1024
            ),
            media.content_type,
        )

    async def set_cover(self, event_id: UUID, actor_id: UUID, media_id: UUID | None) -> EventDTO:
        events = EventService(self.session)
        await events._require_active_profile(actor_id)
        event = await events.events._get_locked(event_id)
        await events.events._require_manager(event, actor_id)
        if event.status not in {EventStatus.DRAFT, EventStatus.PUBLISHED}:
            raise InvalidStateTransitionError("Cannot change the cover of this event")
        if media_id is not None:
            await self.require_owned(media_id, actor_id)
        existing = await self.session.scalar(
            select(EventMedia.media_id).where(
                EventMedia.event_id == event_id, EventMedia.role == EventMediaRole.COVER
            )
        )
        if existing != media_id:
            await self.session.execute(
                delete(EventMedia).where(
                    EventMedia.event_id == event_id, EventMedia.role == EventMediaRole.COVER
                )
            )
            if media_id is not None:
                self.session.add(
                    EventMedia(event_id=event_id, media_id=media_id, role=EventMediaRole.COVER)
                )
            event.updated_at = func.now()
            await self.session.flush()
            if event.status == EventStatus.PUBLISHED:
                await events.notifications.event_changed(
                    event, actor_id, kind="EVENT_UPDATED", changed_fields=["cover_media_id"]
                )
        return await events.get_event(event_id, viewer_id=actor_id)
