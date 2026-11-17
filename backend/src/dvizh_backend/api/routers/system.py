from fastapi import APIRouter, Request

from dvizh_backend.database.database_service import DatabaseService

router = APIRouter()


@router.get(
    "/api/health",
    tags=["system"],
    summary="Состояние сервиса (используется healthcheck-ом контейнера).",
)
async def health(request: Request) -> dict[str, str]:
    database_service: DatabaseService = request.app.state.database_service
    await database_service.ping()
    return {"status": "ok", "service": "backend", "database": "ok"}


@router.get("/api", tags=["system"], summary="Проверка, что API запущен.")
async def root() -> dict[str, str]:
    return {"message": "Dvizh API is running"}
