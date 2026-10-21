import os
from dataclasses import dataclass, field

import pytest


@dataclass(frozen=True)
class IntegrationDatabases:
    source_url: str = field(repr=False)
    source_admin_url: str = field(repr=False)
    vector_url: str = field(repr=False)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires explicit disposable PostgreSQL test databases"
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
