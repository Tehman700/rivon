"""Authentication: login, token refresh, logout, password reset, provisioning.

Every function opens its own transaction(s). Before the tenant is known
(login, reset request) the only rows visible are the one user matched through
the `login_lookup` policy. Everything after that runs tenant-scoped.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.config import Settings
from rivon.platform.email import Email, EmailSender
from rivon.platform.models import (
    PasswordResetToken,
    RefreshToken,
    Region,
    Tenant,
    TenantStatus,
    User,
    UserRole,
)
from rivon.platform.security import (
    UNUSABLE_PASSWORD,
    Principal,
    burn_password_check,
    create_access_token,
    hash_password,
    new_opaque_token,
    parse_opaque_token,
    verify_password,
)
from rivon.platform.tenancy import set_current_tenant, tenant_transaction

LOGIN_EMAIL_SETTING = "app.login_email"


class AuthError(Exception):
    """Base for auth failures. Messages are safe to show to the caller."""


class InvalidCredentials(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class TenantNotActive(AuthError):
    def __init__(self) -> None:
        super().__init__("This account is not active")


class InvalidToken(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid or expired token")


class ProvisioningError(AuthError):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


async def _find_user_by_email(session: AsyncSession, email: str) -> User | None:
    await session.execute(select(func.set_config(LOGIN_EMAIL_SETTING, email, True)))
    return await session.scalar(select(User).where(User.email == email))


async def _issue_tokens(
    session: AsyncSession, user: User, settings: Settings, family_id: uuid.UUID
) -> TokenPair:
    refresh = new_opaque_token(user.tenant_id)
    session.add(
        RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            family_id=family_id,
            token_hash=refresh.hash,
            expires_at=_now() + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    access = create_access_token(
        Principal(user_id=user.id, tenant_id=user.tenant_id, role=user.role),
        settings.jwt_secret.get_secret_value(),
        settings.access_token_ttl_seconds,
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh.value,
        expires_in=settings.access_token_ttl_seconds,
    )


async def _require_active_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None or tenant.status != TenantStatus.ACTIVE:
        raise TenantNotActive()
    return tenant


async def login(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, email: str, password: str
) -> TokenPair:
    email = normalize_email(email)
    async with sessionmaker() as session, session.begin():
        user = await _find_user_by_email(session, email)
        if user is None:
            burn_password_check(password)
            raise InvalidCredentials()
        matches, new_hash = verify_password(password, user.password_hash)
        if not matches:
            raise InvalidCredentials()

        await set_current_tenant(session, user.tenant_id)
        await _require_active_tenant(session, user.tenant_id)
        if new_hash is not None:
            user.password_hash = new_hash
        return await _issue_tokens(session, user, settings, family_id=uuid.uuid4())


async def refresh(
    sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, refresh_token: str
) -> TokenPair:
    token = parse_opaque_token(refresh_token)
    if token is None:
        raise InvalidToken()

    async with tenant_transaction(sessionmaker, token.tenant_id) as session:
        row = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token.hash).with_for_update()
        )
        if row is None or row.expires_at <= _now():
            raise InvalidToken()
        if row.revoked_at is None:
            user = await session.scalar(select(User).where(User.id == row.user_id))
            if user is None:
                raise InvalidToken()
            await _require_active_tenant(session, user.tenant_id)
            row.revoked_at = _now()
            return await _issue_tokens(session, user, settings, family_id=row.family_id)

        # A revoked token came back: it was stolen or replayed. Kill the whole
        # family so neither party can keep refreshing.
        await _revoke_family(session, row.family_id)
    # Only reached on reuse, after the revocation above has committed.
    raise InvalidToken()


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def logout(sessionmaker: async_sessionmaker[AsyncSession], refresh_token: str) -> None:
    """Revokes the token's family. Silently does nothing for unknown tokens."""
    token = parse_opaque_token(refresh_token)
    if token is None:
        return
    async with tenant_transaction(sessionmaker, token.tenant_id) as session:
        row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token.hash))
        if row is not None:
            await _revoke_family(session, row.family_id)


async def request_password_reset(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    email_sender: EmailSender,
    email: str,
) -> None:
    """Emails a reset link if the account exists. Callers must respond the same
    way either way, so this never reveals whether an email is registered."""
    email = normalize_email(email)
    async with sessionmaker() as session, session.begin():
        user = await _find_user_by_email(session, email)
        if user is None:
            return
        await set_current_tenant(session, user.tenant_id)
        token = new_opaque_token(user.tenant_id)
        session.add(
            PasswordResetToken(
                tenant_id=user.tenant_id,
                user_id=user.id,
                token_hash=token.hash,
                expires_at=_now() + timedelta(minutes=settings.password_reset_ttl_minutes),
            )
        )
    link = f"{settings.public_app_url.rstrip('/')}/reset-password?token={token.value}"
    await email_sender.send(
        Email(
            to=email,
            subject="Set your Rivon password",
            body=(
                f"Use this link to set your password:\n\n{link}\n\n"
                f"It expires in {settings.password_reset_ttl_minutes} minutes. "
                "If you didn't ask for this, ignore this email."
            ),
        )
    )


async def confirm_password_reset(
    sessionmaker: async_sessionmaker[AsyncSession], reset_token: str, new_password: str
) -> None:
    token = parse_opaque_token(reset_token)
    if token is None:
        raise InvalidToken()
    async with tenant_transaction(sessionmaker, token.tenant_id) as session:
        row = await session.scalar(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token.hash)
            .with_for_update()
        )
        if row is None or row.used_at is not None or row.expires_at <= _now():
            raise InvalidToken()
        user = await session.scalar(select(User).where(User.id == row.user_id))
        if user is None:
            raise InvalidToken()
        user.password_hash = hash_password(new_password)
        row.used_at = _now()
        # A password change signs the user out everywhere.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )


@dataclass(frozen=True)
class ProvisionedTenant:
    tenant_id: uuid.UUID
    owner_id: uuid.UUID


async def provision_tenant(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    name: str,
    slug: str,
    region: Region,
    owner_email: str,
) -> ProvisionedTenant:
    """Team-only (invite-only provisioning): create an active tenant and its
    owner. The owner has no password until they use a reset link."""
    tenant_id = uuid.uuid4()
    owner = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=normalize_email(owner_email),
        password_hash=UNUSABLE_PASSWORD,
        role=UserRole.OWNER,
    )
    try:
        async with tenant_transaction(sessionmaker, tenant_id) as session:
            session.add(
                Tenant(id=tenant_id, name=name, slug=slug, region=region, status=TenantStatus.ACTIVE)
            )
            await session.flush()
            session.add(owner)
    except IntegrityError as exc:
        raise ProvisioningError("A tenant with that slug or a user with that email exists") from exc
    return ProvisionedTenant(tenant_id=tenant_id, owner_id=owner.id)
