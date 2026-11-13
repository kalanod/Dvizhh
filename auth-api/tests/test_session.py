import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
from fastapi import HTTPException
from starlette.requests import Request

from dvizh_auth.main import current_account, logout, settings


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cookie_identity_requires_valid_signature_and_expiry(self):
        account = SimpleNamespace(id=uuid4(), email="session@example.com", is_admin=False)
        now = datetime.now(UTC)
        claims = dict(sub=str(account.id), iss=settings.jwt_issuer,
                      aud=settings.jwt_audience, iat=now,
                      exp=now + timedelta(minutes=5))
        valid = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        expired = jwt.encode({**claims, "exp": now - timedelta(minutes=1)},
                             settings.jwt_secret, algorithm=settings.jwt_algorithm)
        forged = jwt.encode(claims, "different-secret-with-at-least-32-characters",
                            algorithm=settings.jwt_algorithm)
        session = SimpleNamespace(get=AsyncMock(return_value=account))
        for token in ("", expired, forged):
            request = Request({"type": "http", "headers": [
                (b"cookie", f"dvizh_access={token}".encode())]})
            with self.assertRaises(HTTPException) as error:
                await current_account(request, session)
            self.assertEqual(error.exception.status_code, 401)
        session.get.assert_not_awaited()
        request = Request({"type": "http", "headers": [
            (b"cookie", f"dvizh_access={valid}".encode())]})
        self.assertEqual((await current_account(request, session)).id, account.id)
        self.assertFalse((await current_account(request, session)).is_admin)
        account.is_admin = True
        self.assertTrue((await current_account(request, session)).is_admin)
        account.is_admin = False
        self.assertFalse((await current_account(request, session)).is_admin)
        session.get.return_value = None
        with self.assertRaises(HTTPException):
            await current_account(request, session)

    async def test_logout_expires_cookie(self):
        response = await logout()
        self.assertEqual(response.status_code, 204)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
