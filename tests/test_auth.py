"""PLT-02: login, access tokens, refresh rotation, logout, password reset."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.config import get_settings
from rivon.platform import auth, cli
from rivon.platform.models import (
    PasswordResetToken,
    Region,
    Tenant,
    TenantStatus,
    UserRole,
)
from rivon.platform.security import (
    Principal,
    create_access_token,
    decode_access_token,
    parse_opaque_token,
)
from rivon.platform.tenancy import tenant_transaction
from tests.conftest import CapturingEmailSender

PASSWORD = "correct horse battery staple"


@dataclass(frozen=True)
class Owner:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    password: str


def _reset_token(email_sender: CapturingEmailSender) -> str:
    match = re.search(r"token=(\S+)", email_sender.sent[-1].body)
    assert match, email_sender.sent[-1].body
    return match.group(1)


async def _provision_owner(
    sessionmaker: async_sessionmaker[AsyncSession], email_sender: CapturingEmailSender
) -> Owner:
    suffix = uuid.uuid4().hex[:10]
    email = f"owner-{suffix}@example.com"
    tenant = await auth.provision_tenant(
        sessionmaker, name="Solar Co", slug=f"solar-{suffix}", region=Region.EU, owner_email=email
    )
    await auth.request_password_reset(sessionmaker, get_settings(), email_sender, email)
    await auth.confirm_password_reset(sessionmaker, _reset_token(email_sender), PASSWORD)
    return Owner(tenant.tenant_id, tenant.owner_id, email, PASSWORD)


@pytest.fixture
async def owner(
    app_sessionmaker: async_sessionmaker[AsyncSession], email_sender: CapturingEmailSender
) -> Owner:
    return await _provision_owner(app_sessionmaker, email_sender)


async def _login(client: AsyncClient, email: str, password: str):  # type: ignore[no-untyped-def]
    return await client.post("/auth/login", json={"email": email, "password": password})


async def _tokens(client: AsyncClient, owner: Owner) -> dict:
    response = await _login(client, owner.email, owner.password)
    assert response.status_code == 200, response.text
    return response.json()


async def _me(client: AsyncClient, access_token: str):  # type: ignore[no-untyped-def]
    return await client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})


# --- Login ------------------------------------------------------------------


async def test_login_returns_tokens_that_identify_the_user(client: AsyncClient, owner: Owner) -> None:
    tokens = await _tokens(client, owner)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == get_settings().access_token_ttl_seconds

    me = await _me(client, tokens["access_token"])
    assert me.status_code == 200
    assert me.json() == {
        "user_id": str(owner.user_id),
        "tenant_id": str(owner.tenant_id),
        "email": owner.email,
        "role": "owner",
        "region": "eu",
    }


async def test_login_email_is_case_insensitive(client: AsyncClient, owner: Owner) -> None:
    response = await _login(client, f"  {owner.email.upper()} ", owner.password)
    assert response.status_code == 200


async def test_wrong_password_and_unknown_email_look_identical(
    client: AsyncClient, owner: Owner
) -> None:
    wrong_password = await _login(client, owner.email, "not the password at all")
    unknown_email = await _login(client, "nobody@example.com", owner.password)
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_provisioned_owner_cannot_log_in_before_setting_password(
    client: AsyncClient, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    email = f"new-{uuid.uuid4().hex[:8]}@example.com"
    await auth.provision_tenant(
        app_sessionmaker, name="New", slug=f"new-{uuid.uuid4().hex[:8]}", region=Region.EU,
        owner_email=email,
    )
    for guess in ["!", "", "password1234"]:
        assert (await _login(client, email, guess)).status_code in (401, 422)


async def test_suspended_tenant_cannot_log_in(
    client: AsyncClient, owner: Owner, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_transaction(app_sessionmaker, owner.tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == owner.tenant_id).values(status=TenantStatus.SUSPENDED)
        )
    response = await _login(client, owner.email, owner.password)
    assert response.status_code == 403


# --- Access tokens ------------------------------------------------------------


async def test_me_requires_a_valid_access_token(client: AsyncClient, owner: Owner) -> None:
    tokens = await _tokens(client, owner)
    secret = get_settings().jwt_secret.get_secret_value()
    principal = Principal(owner.user_id, owner.tenant_id, UserRole.OWNER)
    expired = create_access_token(principal, secret, 60, now=datetime.now(UTC) - timedelta(hours=1))
    forged = create_access_token(principal, "x" * 40, 60)

    assert (await client.get("/auth/me")).status_code == 401
    for bad in ["garbage", expired, forged, tokens["refresh_token"]]:
        response = await _me(client, bad)
        assert response.status_code == 401, bad
        assert response.headers["www-authenticate"] == "Bearer"


def test_access_token_round_trip_and_rejections() -> None:
    secret = "s" * 40
    principal = Principal(uuid.uuid4(), uuid.uuid4(), UserRole.MANAGER)
    assert decode_access_token(create_access_token(principal, secret, 60), secret) == principal

    claims = {
        "iss": "rivon", "aud": "rivon-api", "typ": "refresh", "sub": str(principal.user_id),
        "tid": str(principal.tenant_id), "role": "owner",
        "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=1),
    }
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(jwt.encode(claims, secret, algorithm="HS256"), secret)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(jwt.encode({**claims, "typ": "access", "aud": "other"}, secret), secret)
    with pytest.raises(jwt.InvalidTokenError):  # algorithm "none" must never be accepted
        decode_access_token(jwt.encode({**claims, "typ": "access"}, None, algorithm="none"), secret)


def test_opaque_token_parsing() -> None:
    tenant_id = uuid.uuid4()
    assert parse_opaque_token(f"{tenant_id}.abc") is not None
    for bad in ["", "abc", f"{tenant_id}.", "not-a-uuid.abc", f"{tenant_id}." + "a" * 200]:
        assert parse_opaque_token(bad) is None


# --- Refresh and logout -------------------------------------------------------


async def test_refresh_rotates_and_reuse_revokes_the_family(client: AsyncClient, owner: Owner) -> None:
    first = await _tokens(client, owner)

    rotated = await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await _me(client, second["access_token"])).status_code == 200

    # Replaying the first (already used) token is treated as theft...
    replay = await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401
    # ...so the legitimate newer token is revoked too.
    after = await client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert after.status_code == 401


async def test_refresh_rejects_tampered_and_expired_tokens(
    client: AsyncClient, owner: Owner, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    tokens = await _tokens(client, owner)
    _, _, secret = tokens["refresh_token"].partition(".")
    for bad in [f"{uuid.uuid4()}.{secret}", f"{owner.tenant_id}.wrong", "junk"]:
        response = await client.post("/auth/refresh", json={"refresh_token": bad})
        assert response.status_code == 401, bad

    async with tenant_transaction(app_sessionmaker, owner.tenant_id) as session:
        await session.execute(
            text("UPDATE refresh_tokens SET expires_at = now() - interval '1 second'")
        )
    expired = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert expired.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient, owner: Owner) -> None:
    tokens = await _tokens(client, owner)
    assert (await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})).status_code == 204
    again = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401
    # Unknown tokens are accepted silently.
    assert (await client.post("/auth/logout", json={"refresh_token": "junk"})).status_code == 204


async def test_refresh_fails_once_tenant_is_suspended(
    client: AsyncClient, owner: Owner, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    tokens = await _tokens(client, owner)
    async with tenant_transaction(app_sessionmaker, owner.tenant_id) as session:
        await session.execute(
            update(Tenant).where(Tenant.id == owner.tenant_id).values(status=TenantStatus.SUSPENDED)
        )
    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 403
    assert (await _me(client, tokens["access_token"])).status_code == 403


# --- Password reset -----------------------------------------------------------


async def test_password_reset_flow(
    client: AsyncClient, owner: Owner, email_sender: CapturingEmailSender
) -> None:
    old_session = await _tokens(client, owner)
    sent_before = len(email_sender.sent)

    assert (await client.post("/auth/password-reset", json={"email": owner.email})).status_code == 202
    assert len(email_sender.sent) == sent_before + 1
    assert email_sender.sent[-1].to == owner.email
    token = _reset_token(email_sender)

    new_password = "a completely different passphrase"
    confirm = await client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": new_password}
    )
    assert confirm.status_code == 204

    assert (await _login(client, owner.email, owner.password)).status_code == 401
    assert (await _login(client, owner.email, new_password)).status_code == 200
    # Changing the password signs out existing sessions.
    stale = await client.post("/auth/refresh", json={"refresh_token": old_session["refresh_token"]})
    assert stale.status_code == 401
    # Reset tokens are single-use.
    reuse = await client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "yet another passphrase"}
    )
    assert reuse.status_code == 400


async def test_password_reset_for_unknown_email_sends_nothing(
    client: AsyncClient, email_sender: CapturingEmailSender
) -> None:
    response = await client.post("/auth/password-reset", json={"email": "ghost@example.com"})
    assert response.status_code == 202
    assert email_sender.sent == []


async def test_expired_reset_token_is_rejected(
    client: AsyncClient,
    owner: Owner,
    email_sender: CapturingEmailSender,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await client.post("/auth/password-reset", json={"email": owner.email})
    token = _reset_token(email_sender)
    async with tenant_transaction(app_sessionmaker, owner.tenant_id) as session:
        await session.execute(
            update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    response = await client.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "fresh passphrase 123"}
    )
    assert response.status_code == 400


async def test_short_passwords_are_refused(
    client: AsyncClient, owner: Owner, email_sender: CapturingEmailSender
) -> None:
    await client.post("/auth/password-reset", json={"email": owner.email})
    response = await client.post(
        "/auth/password-reset/confirm",
        json={"token": _reset_token(email_sender), "new_password": "short"},
    )
    assert response.status_code == 422


# --- Row level security around login -----------------------------------------


async def test_login_lookup_policy_exposes_only_the_one_user(
    owner: Owner, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with app_sessionmaker() as session, session.begin():
        await session.execute(text("SELECT set_config('app.login_email', :e, true)"), {"e": owner.email})
        users = (await session.execute(text("SELECT id FROM users"))).scalars().all()
        assert users == [owner.user_id]
        # Read-only: the lookup policy grants no writes...
        updated = await session.execute(text("UPDATE users SET role = 'agent'"))
        assert updated.rowcount == 0
        # ...and nothing in other tables.
        assert (await session.execute(text("SELECT * FROM refresh_tokens"))).all() == []
        assert (await session.execute(text("SELECT * FROM tenants"))).all() == []


# --- Provisioning -------------------------------------------------------------


async def test_provisioning_rejects_duplicate_slug_and_email(
    owner: Owner, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(auth.ProvisioningError):
        await auth.provision_tenant(
            app_sessionmaker, name="Dup", slug=f"x-{uuid.uuid4().hex[:8]}", region=Region.EU,
            owner_email=owner.email.upper(),
        )


def test_cli_provisions_a_tenant(capsys: pytest.CaptureFixture[str]) -> None:
    suffix = uuid.uuid4().hex[:8]
    args = ["provision-tenant", "--name", "CLI Solar", "--slug", f"cli-{suffix}",
            "--owner-email", f"cli-{suffix}@example.com"]
    assert cli.main(args) == 0
    assert "created" in capsys.readouterr().out
    assert cli.main(args) == 1  # same slug and email again
    assert "exists" in capsys.readouterr().err
