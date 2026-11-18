from secrets import token_urlsafe
from typing import Literal
from uuid import UUID

from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from dvizh_auth.api.schemas.account import (
    AdminUserPage,
    ChangePasswordRequest,
    CurrentAccountResponse,
    RegisterRequest,
    UpdateAccountRequest,
)
from dvizh_auth.models import ADMIN_ROLE_ID, USER_ROLE_ID, Account
from dvizh_auth.repository import AccountRepository

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


dummy_password_hash = hash_password(token_urlsafe(32))


class AccountConflictError(Exception):
    pass


class InvalidCurrentPasswordError(Exception):
    pass


class AdminAccessDeniedError(Exception):
    pass


class AccountNotFoundError(Exception):
    pass


class SelfDemotionError(Exception):
    pass


class AccountService:
    """Account rules, independent of HTTP and backend profile storage.

    The caller owns the transaction; repositories only read and persist data.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.accounts = AccountRepository(session)

    async def username_available(self, username: str) -> bool:
        return not await self.accounts.username_exists(username)

    @staticmethod
    def summary(account: Account) -> CurrentAccountResponse:
        return CurrentAccountResponse(
            id=account.id, username=account.username, email=account.email,
            role="admin" if account.role_id == ADMIN_ROLE_ID else "user",
        )

    async def search(self, query: str, offset: int, limit: int) -> AdminUserPage:
        accounts = await self.accounts.search(query.strip().lower(), offset, limit + 1)
        return AdminUserPage(
            items=[self.summary(account) for account in accounts[:limit]],
            offset=offset, limit=limit, has_more=len(accounts) > limit,
        )

    async def _admin_target(self, actor_id: UUID, target_id: UUID) -> Account:
        accounts = await self.accounts.lock_accounts({actor_id, target_id})
        actor = accounts.get(actor_id)
        if actor is None or actor.role_id != ADMIN_ROLE_ID:
            raise AdminAccessDeniedError
        target = accounts.get(target_id)
        if target is None:
            raise AccountNotFoundError
        return target

    async def change_role(
        self, actor_id: UUID, target_id: UUID, role: Literal["user", "admin"],
    ) -> Account:
        target = await self._admin_target(actor_id, target_id)
        if actor_id == target_id and role != "admin":
            raise SelfDemotionError
        target.role_id = ADMIN_ROLE_ID if role == "admin" else USER_ROLE_ID
        await self.accounts.flush()
        return target

    async def reset_password(self, actor_id: UUID, target_id: UUID, password: str) -> None:
        target = await self._admin_target(actor_id, target_id)
        target.password_hash = await run_in_threadpool(hash_password, password)
        await self.accounts.flush()

    async def authenticate(self, login: str, password: str) -> Account | None:
        account = await self.accounts.find(login.strip().lower())
        stored_hash = account.password_hash if account is not None else dummy_password_hash
        matches = await run_in_threadpool(password_hasher.verify, password, stored_hash)
        return account if matches else None

    async def register(self, data: RegisterRequest) -> Account:
        password_hash = await run_in_threadpool(hash_password, data.password.get_secret_value())
        account = await self.accounts.create(
            username=data.username,
            email=str(data.email) if data.email is not None else None,
            password_hash=password_hash,
            role_id=USER_ROLE_ID,
        )
        if account is None:
            raise AccountConflictError
        return account

    async def update(self, account: Account, data: UpdateAccountRequest) -> None:
        try:
            await self.accounts.update(account, data.model_dump(exclude_unset=True))
        except IntegrityError:
            raise AccountConflictError from None

    async def change_password(self, account_id: UUID, data: ChangePasswordRequest) -> None:
        account = await self.accounts.get_for_update(account_id)
        if account is None:
            raise InvalidCurrentPasswordError
        matches = await run_in_threadpool(
            password_hasher.verify, data.current_password.get_secret_value(), account.password_hash
        )
        if not matches:
            raise InvalidCurrentPasswordError
        account.password_hash = await run_in_threadpool(
            hash_password, data.new_password.get_secret_value()
        )
        await self.accounts.flush()
