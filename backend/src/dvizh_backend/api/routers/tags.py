
from fastapi import APIRouter

from dvizh_backend.api.dependencies import TagServiceDep
from dvizh_backend.api.schemas.tag import CategoryTagsDTO

router = APIRouter(prefix="/api/tags", tags=["Тематики"])


@router.get("", summary="Каталог активных тематик по категориям.")
async def catalog(service: TagServiceDep) -> list[CategoryTagsDTO]:
    return await service.catalog()
