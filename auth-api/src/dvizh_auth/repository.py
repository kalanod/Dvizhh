"""Account persistence; business rules belong to AccountService."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Account


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, account_id: UUID) -> Account | None:
        return await self.session.get(Account, account_id)

    async def find(self, identifier: str) -> Account | None:
        column = Account.email if "@" in identifier else Account.username
        return await self.session.scalar(select(Account).where(column == identifier))

    async def create(self, **fields: object) -> Account | None:
        statement = insert(Account).values(**fields).on_conflict_do_nothing().returning(Account)
        return await self.session.scalar(statement)

    async def get_for_update(self, account_id: UUID) -> Account | None:
        # Refresh an identity already loaded by authentication after waiting for the lock.
        statement = (
            select(Account)
            .where(Account.id == account_id)
            .with_for_update(of=Account)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def update(self, account: Account, fields: dict[str, object]) -> None:
        async with self.session.begin_nested():
            for name, value in fields.items():
                setattr(account, name, value)
            await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()
