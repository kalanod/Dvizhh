from secrets import token_urlsafe

from pwdlib import PasswordHash

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .models import Account

password_hasher = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

dummy_password_hash = hash_password(token_urlsafe(32))


async def authenticate_account(
    session: AsyncSession,
    email: str,
    password: str,
) -> Account | None:
    email = email.strip().lower()
    account = await session.scalar(
        select(Account).where(Account.email == email)
    )

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
    email: str,
    password: str,
) -> Account | None:
    email = email.strip().lower()
    password_hash = await run_in_threadpool(hash_password, password)

    statement = (
        insert(Account)
        .values(email=email, password_hash=password_hash)
        .on_conflict_do_nothing(index_elements=[Account.email])
        .returning(Account)
    )
    return await session.scalar(statement)