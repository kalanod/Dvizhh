"""Transport to the credential owner. Contains no password rules or hashing."""

import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..dto.account import AccountRequestContext, ChangePasswordCommand


class AccountCommandError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


class AccountGateway:
    def __init__(self, auth_url: str) -> None:
        self.auth_url = auth_url.rstrip("/")

    async def change_password(
        self, command: ChangePasswordCommand, context: AccountRequestContext
    ) -> None:
        await asyncio.to_thread(self._change_password, command, context)

    def _change_password(
        self, command: ChangePasswordCommand, context: AccountRequestContext
    ) -> None:
        headers = {
            "Content-Type": "application/json",
            "Cookie": f"dvizh_access={context.token}",
            "Host": context.host,
            "X-Dvizh-Account": context.write_header,
        }
        if context.origin is not None:
            headers["Origin"] = context.origin
        request = Request(
            f"{self.auth_url}/api/auth/password",
            data=json.dumps({
                "current_password": command.current_password.get_secret_value(),
                "new_password": command.new_password.get_secret_value(),
            }).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                if response.status != 204:
                    raise AccountCommandError(503, "Authentication service unavailable")
        except HTTPError as exc:
            # Never relay upstream validation bodies: they may include credentials.
            details = {
                400: "Invalid current password",
                401: "Authentication required",
                403: "Account write forbidden",
                422: "Invalid password change request",
            }
            with exc:
                detail = details.get(exc.code)
                if detail is not None:
                    raise AccountCommandError(exc.code, detail) from None
            raise AccountCommandError(503, "Authentication service unavailable") from None
        except (URLError, TimeoutError, OSError):
            raise AccountCommandError(503, "Authentication service unavailable") from None
