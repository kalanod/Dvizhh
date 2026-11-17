"""Access-token policy shared by session creation and verification."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from dvizh_auth.config import Settings
from dvizh_auth.models import Account
from dvizh_auth.repository import AccountRepository


class InvalidSessionError(Exception):
    pass


class SessionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def issue_access_token(self, account_id: UUID) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(account_id),
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
                "iat": now,
                "exp": now + timedelta(seconds=self.settings.access_token_ttl_seconds),
            },
            self.settings.jwt_secret,
            algorithm=self.settings.jwt_algorithm,
        )

    def verify_access_token(self, token: str) -> UUID:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=[self.settings.jwt_algorithm],
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["sub", "exp", "iat", "iss", "aud"]},
            )
            return UUID(payload["sub"])
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise InvalidSessionError("Invalid session") from None

    async def current_account(self, token: str, accounts: AccountRepository) -> Account:
        account_id = self.verify_access_token(token)
        account = await accounts.get(account_id)
        if account is None:
            raise InvalidSessionError("Invalid session")
        return account
