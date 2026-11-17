"""Purpose-bound signed read selectors; never grant access or contain event-ID lists."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class DiscoveryContextError(Exception):
    pass


class DiscoveryTokens:
    def __init__(self, secret: str, ttl: int = 600):
        self.secret, self.ttl = secret.encode(), ttl

    def encode(self, purpose: str, data: dict[str, Any]) -> str:
        payload = json.dumps(
            {"v": 1, "purpose": purpose, "exp": int(time.time()) + self.ttl, "data": data},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.digest(self.secret, b"event-discovery:" + encoded, "sha256")
        return (encoded + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()

    def decode(self, purpose: str, token: str) -> dict[str, Any]:
        try:
            encoded, signature = token.encode().split(b".")
            expected = hmac.digest(self.secret, b"event-discovery:" + encoded, "sha256")
            actual = base64.b64decode(
                signature + b"=" * (-len(signature) % 4), altchars=b"-_", validate=True
            )
            if not hmac.compare_digest(actual, expected):
                raise ValueError
            payload = json.loads(
                base64.b64decode(
                    encoded + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True
                )
            )
            if payload["v"] != 1 or payload["purpose"] != purpose or payload["exp"] <= time.time():
                raise ValueError
            if not isinstance(payload["data"], dict):
                raise ValueError
            return payload["data"]
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise DiscoveryContextError("Область поиска устарела. Обновите выдачу.") from None


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
