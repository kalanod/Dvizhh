from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID

from dvizh_backend.api import security
from dvizh_backend.services.account_gateway import AdminAccount

_SESSION_PREFIX = "integration-account-"


def account_headers(user_id: str) -> dict[str, str]:
    return {"Cookie": f"dvizh_access={_SESSION_PREFIX}{user_id}", "X-Dvizh-Account": "1"}


@contextmanager
def account_gateway() -> Iterator[None]:
    original = security.fetch_current_account

    def current_account(auth_url: str, token: str) -> AdminAccount:
        if token.startswith(_SESSION_PREFIX):
            return AdminAccount(id=UUID(token.removeprefix(_SESSION_PREFIX)), role="user")
        return original(auth_url, token)

    with patch("dvizh_backend.api.security.fetch_current_account", current_account):
        yield
