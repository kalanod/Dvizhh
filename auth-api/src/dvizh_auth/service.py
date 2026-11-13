from secrets import token_urlsafe

from pwdlib import PasswordHash
from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .models import USER_ROLE_ID, Account

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


dummy_password_hash = hash_password(token_urlsafe(32))


class AccountConflictError(Exception):
    pass


def account_statement(identifier: str) -> Select[tuple[Account]]:
    normalized = identifier.strip().lower()
    column = Account.email if "@" in normalized else Account.username
    return select(Account).where(column == normalized)


async def authenticate_account(
    session: AsyncSession,
    login: str,
    password: str,
) -> Account | None:
    account = await session.scalar(account_statement(login))

    stored_hash = account.password_hash if account is not None else dummy_password_hash
    password_matches = await run_in_threadpool(
        password_hasher.verify,
        password,
        stored_hash,
    )

    if not password_matches:
        return None

    return account


async def register_account(
    session: AsyncSession,
    username: str,
    email: str | None,
    password: str,
) -> Account | None:
    username = username.strip().lower()
    email = email.strip().lower() if email else None
    password_hash = await run_in_threadpool(hash_password, password)

    statement = (
        insert(Account)
        .values(username=username, email=email, password_hash=password_hash, role_id=USER_ROLE_ID)
        .on_conflict_do_nothing()
        .returning(Account)
    )
    return await session.scalar(statement)


async def update_account(session: AsyncSession, account: Account, fields: dict) -> None:
    try:
        async with session.begin_nested():
            for name, value in fields.items():
                if name not in {"username", "email"}:
                    raise ValueError("Unknown account field")
                setattr(account, name, value)
            await session.flush()
    except IntegrityError:
        raise AccountConflictError from None
