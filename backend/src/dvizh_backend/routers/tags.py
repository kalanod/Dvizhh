from typing import Annotated

from fastapi import APIRouter, Depends

from ..database.dependencies import DatabaseSession
from ..dto.tag import CategoryTagsDTO
from ..services.tag_service import TagService

router = APIRouter(prefix="/api/tags", tags=["tags"])


def get_tag_service(session: DatabaseSession) -> TagService:
    return TagService(session)


TagServiceDep = Annotated[TagService, Depends(get_tag_service)]


@router.get("")
async def catalog(service: TagServiceDep) -> list[CategoryTagsDTO]:
    return await service.catalog()
