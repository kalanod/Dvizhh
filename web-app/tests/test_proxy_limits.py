import asyncio

import httpx
import pytest

from dvizh_web import main
from dvizh_web.config import Settings


class Backend:
    def __init__(self) -> None:
        self.calls = 0

    async def request(self, *args: object, **kwargs: object) -> httpx.Response:
        self.calls += 1
        assert len(kwargs["content"]) <= 1024 * 1024
        return httpx.Response(200, content=b"ok")


def test_exact_limit_and_chunked_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        backend = Backend()
        monkeypatch.setattr(main, "settings", Settings(media_max_mib=1, _env_file=None))
        monkeypatch.setattr(main.app.state, "backend_client", backend, raising=False)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post("/api/media", content=b"x" * (1024 * 1024))
            assert response.status_code == 200 and backend.calls == 1

            async def oversized():
                yield b"x" * 524288
                yield b"x" * 524289

            assert (await client.post("/api/media", content=oversized())).status_code == 413
            assert backend.calls == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(("length", "status"), [("1048577", 413), ("-1", 400), ("bad", 400)])
def test_bad_declared_length_never_reaches_backend(
    monkeypatch: pytest.MonkeyPatch, length: str, status: int
) -> None:
    async def scenario() -> None:
        backend = Backend()
        monkeypatch.setattr(main, "settings", Settings(media_max_mib=1, _env_file=None))
        monkeypatch.setattr(main.app.state, "backend_client", backend, raising=False)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/media", content=b"x", headers={"Content-Length": length}
            )
            assert response.status_code == status and backend.calls == 0

    asyncio.run(scenario())
