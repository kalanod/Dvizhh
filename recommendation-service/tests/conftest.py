import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.pool import NullPool

from dvizh_recommendation.database import create_database_engine


@dataclass(frozen=True)
class IntegrationDatabases:
    source_url: str = field(repr=False)
    source_admin_url: str = field(repr=False)
    vector_url: str = field(repr=False)

    @asynccontextmanager
    async def connections(self) -> AsyncIterator[tuple[AsyncConnection, AsyncConnection]]:
        async with (
            create_database_engine(self.source_url, poolclass=NullPool).connect() as source,
            create_database_engine(self.vector_url, poolclass=NullPool).connect() as vectors,
        ):
            yield source, vectors


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires explicit disposable databases or Redis"
    )


@pytest.fixture(scope="session")
def integration_databases() -> IntegrationDatabases:
    names = (
        "TEST_SOURCE_DATABASE_URL",
        "TEST_SOURCE_ADMIN_DATABASE_URL",
        "TEST_VECTOR_DATABASE_URL",
    )
    values = [os.environ.get(name) for name in names]
    if not any(values):
        pytest.skip(
            "Set TEST_SOURCE_DATABASE_URL, TEST_SOURCE_ADMIN_DATABASE_URL, "
            "and TEST_VECTOR_DATABASE_URL to run database integration tests"
        )
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        pytest.fail("Incomplete database integration configuration: " + ", ".join(missing))
    return IntegrationDatabases(*(str(value) for value in values))


@pytest.fixture(scope="session")
def integration_redis_url() -> str:
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to run Redis integration tests")
    return url
