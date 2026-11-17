import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from dvizh_auth.config import Settings
from dvizh_auth.services.session_service import InvalidSessionError, SessionService


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret="session-unit-test-key-" * 4,
        jwt_algorithm="HS512",
        jwt_issuer="test-session-issuer",
        jwt_audience="test-session-audience",
        access_token_ttl_seconds=120,
    )


def claims(settings: Settings) -> dict:
    now = datetime.now(UTC)
    return {
        "sub": str(uuid4()), "iss": settings.jwt_issuer, "aud": settings.jwt_audience,
        "iat": now, "exp": now + timedelta(seconds=120),
    }


def test_issue_and_verify_use_configured_identity_signature_and_lifetime(
    settings: Settings,
) -> None:
    account_id = uuid4()
    service = SessionService(settings)
    before = int(datetime.now(UTC).timestamp())
    token = service.issue_access_token(account_id)
    after = int(datetime.now(UTC).timestamp())
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS512"],
        issuer="test-session-issuer", audience="test-session-audience",
    )
    assert jwt.get_unverified_header(token)["alg"] == "HS512"
    assert payload["sub"] == str(account_id)
    assert payload["iss"] == "test-session-issuer"
    assert payload["aud"] == "test-session-audience"
    assert before <= payload["iat"] <= after
    assert payload["exp"] - payload["iat"] == 120
    assert service.verify_access_token(token) == account_id


@pytest.mark.parametrize("field", ["sub", "exp", "iat", "iss", "aud"])
def test_verify_requires_every_session_claim(settings: Settings, field: str) -> None:
    payload = claims(settings)
    del payload[field]
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidSessionError):
        SessionService(settings).verify_access_token(token)


@pytest.mark.parametrize("overrides", [
    {"exp": datetime.now(UTC) - timedelta(minutes=1)},
    {"iat": datetime.now(UTC) + timedelta(minutes=10)},
    {"sub": "not-an-account-uuid"},
    {"iss": "untrusted-issuer"},
    {"aud": "another-application"},
])
def test_verify_rejects_expired_future_and_wrong_identity_claims(settings, overrides) -> None:
    token = jwt.encode({**claims(settings), **overrides}, settings.jwt_secret,
                       algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidSessionError):
        SessionService(settings).verify_access_token(token)


@pytest.mark.parametrize("overrides", [
    {"jwt_secret": "different-unit-test-key-" * 4},
    {"jwt_algorithm": "HS256"},
    {"jwt_issuer": "another-issuer"},
    {"jwt_audience": "another-audience"},
])
def test_verify_honors_verifier_configuration(settings: Settings, overrides: dict) -> None:
    token = SessionService(settings).issue_access_token(uuid4())
    verifier_settings = settings.model_copy(update=overrides)
    with pytest.raises(InvalidSessionError) as error:
        SessionService(verifier_settings).verify_access_token(token)
    assert token not in str(error.value)
    assert settings.jwt_secret not in str(error.value)


@pytest.mark.parametrize("token", ["", "invalid-token", "e30.e30.invalid"])
def test_malformed_tokens_raise_domain_error(settings: Settings, token: str) -> None:
    with pytest.raises(InvalidSessionError, match="Invalid session"):
        SessionService(settings).verify_access_token(token)


def test_current_account_requires_live_account(settings):
    async def scenario():
        account = object()
        accounts = SimpleNamespace(get=AsyncMock(return_value=account))
        service = SessionService(settings)
        account_id = uuid4()
        token = service.issue_access_token(account_id)
        assert await service.current_account(token, accounts) is account
        accounts.get.assert_awaited_once_with(account_id)
        accounts.get.return_value = None
        with pytest.raises(InvalidSessionError):
            await service.current_account(token, accounts)
        accounts.get.reset_mock()
        with pytest.raises(InvalidSessionError):
            await service.current_account("invalid-token", accounts)
        accounts.get.assert_not_awaited()
    asyncio.run(scenario())
