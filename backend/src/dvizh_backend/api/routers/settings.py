
from fastapi import APIRouter, Depends, Response

from dvizh_backend.api.dependencies import (
    AccountContextDep,
    SettingsServiceDep,
)
from dvizh_backend.api.schemas.settings import (
    SettingsActionRequest,
    SettingsActionResponse,
    SettingsDocument,
)
from dvizh_backend.api.security import require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])


@router.get("", response_model_exclude_none=True)
async def get_settings(service: SettingsServiceDep, response: Response) -> SettingsDocument:
    response.headers["Cache-Control"] = "no-store"
    return await service.document()


@router.post("/actions/{action_id}", response_model_exclude_none=True)
async def execute_action(
    action_id: str,
    body: SettingsActionRequest,
    context: AccountContextDep,
    response: Response,
    service: SettingsServiceDep,
) -> SettingsActionResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.execute(action_id, body.rows, context)
