"""PLT-05: a tenant's region is fixed at provisioning and only its region serves it."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rivon.config import Settings, get_settings
from rivon.platform import auth, cli
from rivon.platform.models import Region, Tenant, UserRole
from rivon.platform.security import Principal, create_access_token, hash_password
from rivon.platform.tenancy import set_current_tenant, tenant_transaction

PASSWORD = "a long enough passphrase"


def test_deployment_region_defaults_to_eu() -> None:
    assert get_settings().deployment_region == Region.EU


async def test_region_cannot_be_changed(seed, app_sessionmaker) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(DBAPIError, match="tenants.region cannot change"):
        async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
            await session.execute(
                update(Tenant).where(Tenant.id == seed.tenant_a.id).values(region=Region.NON_EU)
            )

    # Other columns stay editable, and setting the same region is not a change.
    async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
        result = await session.execute(
            update(Tenant)
            .where(Tenant.id == seed.tenant_a.id)
            .values(name="Renamed", region=Region.EU)
        )
        assert result.rowcount == 1


async def test_cannot_provision_a_tenant_for_another_region(
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(auth.ProvisioningError, match="deployment serves region 'eu'"):
        await auth.provision_tenant(
            app_sessionmaker,
            get_settings(),
            name="Elsewhere",
            slug=f"elsewhere-{uuid.uuid4().hex[:8]}",
            region=Region.NON_EU,
            owner_email=f"elsewhere-{uuid.uuid4().hex[:8]}@example.com",
        )


def test_cli_refuses_another_region(capsys: pytest.CaptureFixture[str]) -> None:
    suffix = uuid.uuid4().hex[:8]
    code = cli.main(
        ["provision-tenant", "--name", "X", "--slug", f"x-{suffix}", "--region", "non_eu",
         "--owner-email", f"x-{suffix}@example.com"]
    )
    assert code == 1
    assert "region" in capsys.readouterr().err


async def _misplaced_tenant(owner_engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, str]:
    """A non-EU tenant sitting in the EU database: a misconfiguration that
    provisioning prevents, created directly to test the runtime guard."""
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    email = f"misplaced-{uuid.uuid4().hex[:8]}@example.com"
    async with owner_engine.begin() as conn:
        await set_current_tenant(conn, tenant_id)
        await conn.execute(
            text(
                "INSERT INTO tenants (id, name, slug, region, status) "
                "VALUES (:id, 'Misplaced', :slug, 'non_eu', 'active')"
            ),
            {"id": tenant_id, "slug": f"misplaced-{uuid.uuid4().hex[:8]}"},
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, role) "
                "VALUES (:id, :tenant_id, :email, :hash, 'owner')"
            ),
            {"id": user_id, "tenant_id": tenant_id, "email": email, "hash": hash_password(PASSWORD)},
        )
    return tenant_id, user_id, email


async def test_tenant_from_another_region_is_refused_at_runtime(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    tenant_id, user_id, email = await _misplaced_tenant(owner_engine)

    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 403
    assert "another region" in login.json()["detail"]

    # A valid token for that tenant is refused by every tenant-scoped route too.
    settings: Settings = get_settings()
    token = create_access_token(
        Principal(user_id, tenant_id, UserRole.OWNER),
        settings.jwt_secret.get_secret_value(),
        60,
    )
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 403
    assert "another region" in me.json()["detail"]
