"""Administrative account operations delegated to the single credential owner."""

from uuid import UUID

from dvizh_backend.api.schemas.admin_user import (
    AdminUserDTO,
    AdminUserPage,
    ChangeRoleCommand,
    ResetPasswordCommand,
)
from dvizh_backend.services.account_context import AccountRequestContext
from dvizh_backend.services.account_gateway import AccountGateway


class AdminUserService:
    def __init__(self, accounts: AccountGateway) -> None:
        self.accounts = accounts

    async def search(
        self, query: str, offset: int, limit: int, context: AccountRequestContext,
    ) -> AdminUserPage:
        return await self.accounts.search_users(query, offset, limit, context)

    async def change_role(
        self, user_id: UUID, command: ChangeRoleCommand, context: AccountRequestContext,
    ) -> AdminUserDTO:
        return await self.accounts.change_role(user_id, command, context)

    async def reset_password(
        self, user_id: UUID, command: ResetPasswordCommand, context: AccountRequestContext,
    ) -> None:
        await self.accounts.reset_password(user_id, command, context)
