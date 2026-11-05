import asyncio
from io import BytesIO

import urllib3
from minio import Minio
from minio.error import S3Error

from .config import Settings
from .services.media_errors import StorageUnavailableError


class MediaStorage:
    """Blocking MinIO SDK work is isolated from the ASGI event loop."""

    def __init__(self, settings: Settings) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            http_client=urllib3.PoolManager(
                timeout=urllib3.Timeout(
                    connect=settings.minio_timeout_seconds, read=settings.minio_timeout_seconds
                ),
                retries=False,
            ),
        )

    async def put(self, bucket: str, key: str, data: bytes) -> None:
        def upload() -> None:
            self.client.put_object(bucket, key, BytesIO(data), len(data), content_type="image/webp")

        task = asyncio.create_task(asyncio.to_thread(upload))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Wait for the thread before rollback removes its object.
            try:
                await task
            finally:
                raise
        except (S3Error, urllib3.exceptions.HTTPError, OSError) as exc:
            raise StorageUnavailableError("Media storage is unavailable") from exc

    async def read(self, bucket: str, key: str, limit: int) -> bytes:
        def download() -> bytes:
            response = self.client.get_object(bucket, key)
            try:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise StorageUnavailableError("Stored media exceeds the size limit")
                return data
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(download)
        except (S3Error, urllib3.exceptions.HTTPError, OSError) as exc:
            raise StorageUnavailableError("Media storage is unavailable") from exc

    async def remove(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self.client.remove_object, bucket, key)
