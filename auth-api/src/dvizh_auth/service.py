from pwdlib import PasswordHash

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .models import Account

password_hasher = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

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