"""Transport to the credential owner. Contains no password rules or hashing."""

import asyncio
import json
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from uuid import UUID

from pydantic import BaseModel, ValidationError

from dvizh_backend.api.schemas.account import ChangePasswordCommand
from dvizh_backend.api.schemas.admin_user import (
    AdminUserDTO,
    AdminUserPage,
    ChangeRoleCommand,
    ResetPasswordCommand,
)
from dvizh_backend.services.account_context import AccountRequestContext


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

    async def search_users(
        self, query: str, offset: int, limit: int, context: AccountRequestContext,
    ) -> AdminUserPage:
        path = "/api/auth/admin/users?" + urlencode({"q": query, "offset": offset, "limit": limit})
        result = await asyncio.to_thread(self._admin_request, "GET", path, None, context)
        try:
            return AdminUserPage.model_validate_json(result)
        except ValidationError:
            raise AccountCommandError(503, "Authentication service unavailable") from None

    async def change_role(
        self, user_id: UUID, command: ChangeRoleCommand, context: AccountRequestContext,
    ) -> AdminUserDTO:
        result = await asyncio.to_thread(
            self._admin_request, "PATCH", f"/api/auth/admin/users/{user_id}/role",
            {"role": command.role}, context,
        )
        try:
            return AdminUserDTO.model_validate_json(result)
        except ValidationError:
            raise AccountCommandError(503, "Authentication service unavailable") from None

    async def reset_password(
        self, user_id: UUID, command: ResetPasswordCommand, context: AccountRequestContext,
    ) -> None:
        await asyncio.to_thread(
            self._admin_request, "POST", f"/api/auth/admin/users/{user_id}/password",
            {"new_password": command.new_password.get_secret_value()}, context,
        )

    def _admin_request(
        self, method: str, path: str, payload: dict[str, str] | None,
        context: AccountRequestContext,
    ) -> bytes:
        headers = {
            "Cookie": f"dvizh_access={context.token}", "Host": context.host,
            "Content-Type": "application/json", "X-Dvizh-Admin": "1",
        }
        if context.origin is not None:
            headers["Origin"] = context.origin
        request = Request(
            f"{self.auth_url}{path}",
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers, method=method,
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                if response.status != (204 if path.endswith("/password") else 200):
                    raise AccountCommandError(503, "Authentication service unavailable")
                return response.read(262144)
        except HTTPError as exc:
            details = {
                401: "Authentication required", 403: "Administrator access required",
                404: "Account not found", 409: "Cannot remove your own administrator role",
                422: (
                    "Invalid password change request" if path.endswith("/password")
                    else "Invalid account command"
                ),
            }
            with exc:
                detail = details.get(exc.code)
                if detail is not None:
                    raise AccountCommandError(exc.code, detail) from None
            raise AccountCommandError(503, "Authentication service unavailable") from None
        except (URLError, TimeoutError, OSError):
            raise AccountCommandError(503, "Authentication service unavailable") from None

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


class AdminAccount(BaseModel):
    id: UUID
    role: Literal["user", "admin"]


def fetch_current_account(auth_url: str, token: str) -> AdminAccount:
    request = Request(
        f"{auth_url.rstrip('/')}/api/auth/me", headers={"Cookie": f"dvizh_access={token}"}
    )
    try:
        with urlopen(request, timeout=5) as response:
            return AdminAccount.model_validate_json(response.read(16384))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise AccountCommandError(401, "Authentication required") from None
        raise AccountCommandError(503, "Authentication service unavailable") from None
    except (URLError, TimeoutError, OSError, ValidationError):
        raise AccountCommandError(503, "Authentication service unavailable") from None
