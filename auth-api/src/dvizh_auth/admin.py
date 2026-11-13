"""Grant or revoke administrator access from the server console."""

import argparse
import asyncio

from sqlalchemy import select

from .config import get_settings
from .database import Database
from .models import Account


async def set_admin(email: str, enabled: bool) -> None:
    database = Database(get_settings().database_url)
    try:
        async with database.session() as session:
            account = await session.scalar(
                select(Account).where(Account.email == email.strip().lower()).with_for_update()
            )
            if account is None:
                raise ValueError("Account not found; register it first")
            account.is_admin = enabled
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--grant", action="store_true")
    action.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(set_admin(args.email, args.grant))
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print("Administrator access updated")


if __name__ == "__main__":
    main()
