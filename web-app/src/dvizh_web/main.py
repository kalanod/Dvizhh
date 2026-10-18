from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings

settings = get_settings()
static_dir = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.backend_client = httpx.AsyncClient(
        base_url=settings.backend_url,
        timeout=10.0,
    )
    yield
    await app.state.backend_client.aclose()


app = FastAPI(
    title=settings.app_name,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
# Сборка фронтенда (web-app/frontend) появляется в static/ после `npm run build`.
app.mount(
    "/assets",
    StaticFiles(directory=static_dir / "assets", check_dir=False),
    name="assets",
)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "web-app"}


@app.api_route(
    "/api",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
@app.api_route(
    "/api/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def proxy_backend(request: Request, path: str = "") -> Response:
    target = f"/api/{path}" if path else "/api"
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }

    try:
        upstream = await request.app.state.backend_client.request(
            request.method,
            target,
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Backend is unavailable") from exc

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower()
        not in {"content-encoding", "content-length", "transfer-encoding", "connection"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str = "") -> FileResponse:
    """Отдаёт файлы сборки, а для остальных путей — index.html (маршрутизация SPA)."""
    root = static_dir.resolve()
    candidate = (root / path).resolve()
    if path and candidate.is_relative_to(root) and candidate.is_file():
        return FileResponse(candidate)

    index_file = root / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=503, detail="Frontend is not built")
    return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
