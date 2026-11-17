from fastapi import APIRouter, HTTPException, Request, Response, status

from dvizh_auth.api.dependencies import SessionDep, require_account, require_account_write
from dvizh_auth.api.schemas.account import (
    ChangePasswordRequest,
    CurrentAccountResponse,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    UpdateAccountRequest,
    Username,
    UsernameAvailabilityResponse,
)
from dvizh_auth.config import get_settings
from dvizh_auth.services.account_service import (
    AccountConflictError,
    AccountService,
    InvalidCurrentPasswordError,
)
from dvizh_auth.services.session_service import SessionService

settings = get_settings()
router = APIRouter(prefix="/api/auth")


@router.get("/username-availability", response_model=UsernameAvailabilityResponse)
async def username_availability(
    username: Username, session: SessionDep, response: Response,
) -> UsernameAvailabilityResponse:
    response.headers["Cache-Control"] = "no-store"
    return UsernameAvailabilityResponse(
        username=username, available=await AccountService(session).username_available(username),
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
)
async def register(
    data: RegisterRequest,
    session: SessionDep,
) -> RegisterResponse:
    try:
        account = await AccountService(session).register(data)
    except AccountConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered",
        ) from None

    return RegisterResponse(id=account.id, username=account.username, email=account.email)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(data: LoginRequest, session: SessionDep) -> Response:
    account = await AccountService(session).authenticate(
        login=str(data.login),
        password=data.password.get_secret_value(),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login or password",
        )

    ttl = settings.access_token_ttl_seconds
    access_token = SessionService(settings).issue_access_token(account.id)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key="dvizh_access",
        value=access_token,
        max_age=ttl,
        path="/",
        httponly=True,
        secure=settings.access_cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/me", response_model=CurrentAccountResponse)
async def current_account(request: Request, session: SessionDep) -> CurrentAccountResponse:
    account = await require_account(request, session)
    return CurrentAccountResponse(
        id=account.id,
        username=account.username,
        email=account.email,
        role=account.role.name,
    )


@router.patch("/me", response_model=CurrentAccountResponse)
async def update_current_account(
    data: UpdateAccountRequest,
    request: Request,
    session: SessionDep,
) -> CurrentAccountResponse:
    account = await require_account(request, session)
    require_account_write(request)
    try:
        await AccountService(session).update(account, data)
    except AccountConflictError:
        raise HTTPException(
            status_code=409, detail="Username or email is already registered"
        ) from None
    return CurrentAccountResponse(
        id=account.id,
        username=account.username,
        email=account.email,
        role=account.role.name,
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    session: SessionDep,
) -> Response:
    account = await require_account(request, session)
    require_account_write(request)
    try:
        await AccountService(session).change_password(account.id, data)
    except InvalidCurrentPasswordError:
        raise HTTPException(status_code=400, detail="Invalid current password") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie("dvizh_access", path="/", httponly=True, samesite="lax")
    return response
