import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.config import Settings, get_settings
from rivon.platform import auth
from rivon.platform.email import EmailSender
from rivon.platform.models import Region, User, UserRole
from rivon.platform.security import Principal
from rivon.platform.tenancy import TenantContext, get_current_principal, get_tenant_context

router = APIRouter(prefix="/auth", tags=["auth"])

# Upper bound stops very long inputs from being fed to the (deliberately slow) hasher.
Password = Annotated[str, Field(min_length=12, max_length=128)]
# Not validated as an address: an unknown email just fails to match.
EmailAddress = Annotated[str, Field(min_length=3, max_length=320)]


class LoginRequest(BaseModel):
    email: EmailAddress
    password: Annotated[str, Field(max_length=128)]


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, Field(max_length=256)]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PasswordResetRequest(BaseModel):
    email: EmailAddress


class PasswordResetConfirm(BaseModel):
    token: Annotated[str, Field(max_length=256)]
    new_password: Password


class MeResponse(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: UserRole
    region: Region


def _sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.sessionmaker


def _email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


Sessionmaker = Annotated[async_sessionmaker[AsyncSession], Depends(_sessionmaker)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _tokens(pair: auth.TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in
    )


def _http_error(exc: auth.AuthError) -> HTTPException:
    code = (
        status.HTTP_403_FORBIDDEN
        if isinstance(exc, auth.TenantNotActive)
        else status.HTTP_401_UNAUTHORIZED
    )
    return HTTPException(code, str(exc))


@router.post("/login")
async def login(body: LoginRequest, sessionmaker: Sessionmaker, settings: AppSettings) -> TokenResponse:
    try:
        return _tokens(await auth.login(sessionmaker, settings, body.email, body.password))
    except auth.AuthError as exc:
        raise _http_error(exc) from None


@router.post("/refresh")
async def refresh(
    body: RefreshRequest, sessionmaker: Sessionmaker, settings: AppSettings
) -> TokenResponse:
    try:
        return _tokens(await auth.refresh(sessionmaker, settings, body.refresh_token))
    except auth.AuthError as exc:
        raise _http_error(exc) from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, sessionmaker: Sessionmaker) -> Response:
    await auth.logout(sessionmaker, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: PasswordResetRequest,
    sessionmaker: Sessionmaker,
    settings: AppSettings,
    email_sender: Annotated[EmailSender, Depends(_email_sender)],
) -> Response:
    # Same response whether or not the email exists.
    await auth.request_password_reset(sessionmaker, settings, email_sender, body.email)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(body: PasswordResetConfirm, sessionmaker: Sessionmaker) -> Response:
    try:
        await auth.confirm_password_reset(sessionmaker, body.token, body.new_password)
    except auth.InvalidToken as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
async def me(
    principal: Annotated[Principal, Depends(get_current_principal)],
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
) -> MeResponse:
    user = await ctx.session.scalar(select(User).where(User.id == principal.user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return MeResponse(
        user_id=user.id, tenant_id=user.tenant_id, email=user.email, role=user.role, region=ctx.region
    )
