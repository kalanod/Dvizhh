from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from dvizh_auth.api.dependencies import SessionDep, require_admin, require_admin_write
from dvizh_auth.api.schemas.account import (
    AdminUserPage,
    ChangeRoleRequest,
    CurrentAccountResponse,
    ResetPasswordRequest,
)
from dvizh_auth.models import Account
from dvizh_auth.services.account_service import AccountService

router = APIRouter(prefix="/api/auth/admin/users", tags=["admin"])
AdminAccount = Annotated[Account, Depends(require_admin)]


@router.get("")
async def list_users(
    session: SessionDep,
    actor: AdminAccount,
    response: Response,
    q: str = Query("", max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> AdminUserPage:
    response.headers["Cache-Control"] = "no-store"
    return await AccountService(session).search(q, offset, limit)


@router.patch("/{user_id}/role", dependencies=[Depends(require_admin_write)])
async def change_role(
    user_id: UUID, data: ChangeRoleRequest, actor: AdminAccount, session: SessionDep,
    response: Response,
) -> CurrentAccountResponse:
    response.headers["Cache-Control"] = "no-store"
    service = AccountService(session)
    return service.summary(await service.change_role(actor.id, user_id, data.role))


@router.post("/{user_id}/password", status_code=204, dependencies=[Depends(require_admin_write)])
async def reset_password(
    user_id: UUID, data: ResetPasswordRequest, actor: AdminAccount, session: SessionDep,
) -> Response:
    await AccountService(session).reset_password(
        actor.id, user_id, data.new_password.get_secret_value(),
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
