import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

_MINUTE = timedelta(minutes=1)
_COMMIT_GRACE = timedelta(seconds=10)


async def reporting_minutes() -> AsyncIterator[tuple[datetime, datetime]]:
    while True:
        now = datetime.now(UTC)
        end = (now - _COMMIT_GRACE).replace(second=0, microsecond=0)
        yield end - _MINUTE, end
        next_report = end + _MINUTE + _COMMIT_GRACE
        await asyncio.sleep(max(0, (next_report - datetime.now(UTC)).total_seconds()))
