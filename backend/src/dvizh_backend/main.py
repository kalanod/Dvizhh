from fastapi import FastAPI

from .config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/api", tags=["system"])
async def root() -> dict[str, str]:
    return {"message": "Dvizh API is running"}
