from fastapi import FastAPI

from .config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "recommendation-service"}


@app.get("/recommendations", tags=["recommendations"])
async def recommendations() -> dict[str, list[object]]:
    return {"items": []}
