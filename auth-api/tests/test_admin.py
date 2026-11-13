import pytest
from pydantic import ValidationError

from dvizh_auth.config import Settings
from dvizh_auth.main import RegisterRequest


def test_public_registration_cannot_grant_admin() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="admin@example.com", password="test-password-123", is_admin=True)


def test_missing_signing_secret_is_random_and_explicit_secret_is_stable() -> None:
    first = Settings(_env_file=None, jwt_secret="")
    second = Settings(_env_file=None, jwt_secret="")
    assert len(first.jwt_secret) >= 32
    assert first.jwt_secret != second.jwt_secret
    explicit = "test-signing-secret-longer-than-32-characters"
    assert Settings(_env_file=None, jwt_secret=explicit).jwt_secret == explicit
