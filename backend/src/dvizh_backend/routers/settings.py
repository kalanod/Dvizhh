from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from ..dto.account import AccountRequestContext
from ..dto.settings import SettingsActionRequest, SettingsActionResponse, SettingsDocument
from ..services.admin_auth import require_admin
from ..services.dependencies import UserServiceDep
from ..services.settings_service import SettingsService
from .tags import TagServiceDep

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])


def get_settings_service(tags: TagServiceDep, users: UserServiceDep) -> SettingsService:
    return SettingsService(tags, users)


SettingsServiceDep = Annotated[SettingsService, Depends(get_settings_service)]


@router.get("", response_model_exclude_none=True)
async def get_settings(service: SettingsServiceDep, response: Response) -> SettingsDocument:
    response.headers["Cache-Control"] = "no-store"
    return await service.document()


@router.post("/actions/{action_id}", response_model_exclude_none=True)
async def execute_action(
    action_id: str,
    body: SettingsActionRequest,
    request: Request,
    response: Response,
    service: SettingsServiceDep,
) -> SettingsActionResponse:
    response.headers["Cache-Control"] = "no-store"
    context = AccountRequestContext(
        token=request.cookies.get("dvizh_access", ""),
        host=request.headers.get("host", ""),
        origin=request.headers.get("origin"),
        write_header=request.headers.get("x-dvizh-account", ""),
    )
    return await service.execute(action_id, body.rows, context)
