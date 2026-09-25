"""Test fixtures. Tests run against the `rivon_test` database from docker compose.

The schema is built by running the real Alembic migrations as the owner role.
Tests themselves connect as the application role, so RLS is in force exactly
as it is in production.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import ASGITransport, AsyncClient

from rivon.config import Settings, get_settings
from rivon.db import create_engine
from rivon.platform.email import Email
from rivon.platform.tenancy import set_current_tenant

TEST_DATABASE = "rivon_test"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _to_test_database(url: str) -> str:
    return make_url(url).set(database=TEST_DATABASE).render_as_string(hide_password=False)


# Point everything, including rivon.config.get_settings(), at the test database.
_base = Settings()  # type: ignore[call-arg]
os.environ["RIVON_DATABASE_URL"] = _to_test_database(_base.database_url)
os.environ["RIVON_MIGRATION_DATABASE_URL"] = _to_test_database(_base.migration_database_url)
assert _base.relay_database_url, "RIVON_RELAY_DATABASE_URL must be set for tests"
os.environ["RIVON_RELAY_DATABASE_URL"] = _to_test_database(_base.relay_database_url)
# Keep test queues away from a running dev worker on database 0.
os.environ["RIVON_REDIS_URL"] = _base.redis_url.rsplit("/", 1)[0] + "/1"
# Channel credentials are encrypted with a throwaway key, and the Meta app is a
# stand-in: every test drives the connect flow through a fake Graph.
os.environ.setdefault("RIVON_CHANNEL_TOKEN_KEY", Fernet.generate_key().decode())
os.environ.setdefault("RIVON_META_APP_ID", "test-app-id")
os.environ.setdefault("RIVON_META_APP_SECRET", "test-app-secret")
os.environ.setdefault("RIVON_META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("RIVON_META_LOGIN_CONFIG_PAGES", "test-config-pages")
os.environ.setdefault("RIVON_META_LOGIN_CONFIG_WHATSAPP", "test-config-whatsapp")
os.environ.setdefault("RIVON_META_LOGIN_CONFIG_PAGES_V2", "test-config-pages-v2")
os.environ.setdefault("RIVON_META_REDIRECT_URI_V2", "https://app.example/connect/meta/beta")
os.environ.setdefault("RIVON_META_REDIRECT_URI", "https://app.example/connect/meta/callback")
get_settings.cache_clear()


# Drops everything the migrations create, whatever revision the test database
# is at (including a revision whose file no longer exists).
RESET_SCHEMA_SQL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', r.tablename);
  END LOOP;
  FOR r IN SELECT p.oid::regprocedure AS signature FROM pg_proc p
           JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public' LOOP
    EXECUTE 'DROP FUNCTION IF EXISTS ' || r.signature || ' CASCADE';
  END LOOP;
END $$;
"""


async def _reset_schema(url: str) -> None:
    engine = create_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(RESET_SCHEMA_SQL))
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    url = get_settings().migration_database_url
    asyncio.run(_reset_schema(url))
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False
    # Up, down, up: every migration's downgrade is exercised on each run.
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(get_settings().migration_database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def app_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def relay_engine() -> AsyncIterator[AsyncEngine]:
    url = get_settings().relay_database_url
    assert url is not None
    engine = create_engine(url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def relay_sessionmaker(relay_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(relay_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def app_sessionmaker(app_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(app_engine, expire_on_commit=False)


@dataclass(frozen=True)
class SeededTenant:
    id: uuid.UUID
    emails: frozenset[str]


@dataclass(frozen=True)
class Seed:
    tenant_a: SeededTenant
    tenant_b: SeededTenant
    suspended: SeededTenant


async def _insert_tenant(
    conn: AsyncConnection, slug: str, status: str, emails: list[str]
) -> SeededTenant:
    tenant_id = uuid.uuid4()
    # FORCE RLS applies to the owner role as well, so even seeding has to set
    # the tenant before writing that tenant's rows.
    await set_current_tenant(conn, tenant_id)
    await conn.execute(
        text(
            "INSERT INTO tenants (id, name, slug, region, status) "
            "VALUES (:id, :name, :slug, 'eu', :status)"
        ),
        {"id": tenant_id, "name": slug.title(), "slug": slug, "status": status},
    )
    for email in emails:
        await conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, password_hash, role) "
                "VALUES (:tenant_id, :email, 'not-a-real-hash', 'owner')"
            ),
            {"tenant_id": tenant_id, "email": email},
        )
    return SeededTenant(id=tenant_id, emails=frozenset(emails))


@pytest.fixture(scope="session")
async def seed(migrated_database: None, owner_engine: AsyncEngine) -> AsyncIterator[Seed]:
    async with owner_engine.begin() as conn:
        seeded = Seed(
            tenant_a=await _insert_tenant(
                conn, "tenant-a", "active", ["alice@a.example", "adam@a.example"]
            ),
            tenant_b=await _insert_tenant(
                conn, "tenant-b", "active", ["bob@b.example", "bea@b.example", "ben@b.example"]
            ),
            suspended=await _insert_tenant(conn, "tenant-s", "suspended", ["sam@s.example"]),
        )
    yield seeded
    async with owner_engine.begin() as conn:
        # TRUNCATE is not subject to RLS, so the owner can clear every tenant.
        await conn.execute(text("TRUNCATE tenants CASCADE"))


@pytest.fixture
async def db_session(app_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """App-role session inside a transaction that is rolled back after the test."""
    async with app_engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


class CapturingEmailSender:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)


@pytest.fixture
def email_sender() -> CapturingEmailSender:
    return CapturingEmailSender()


@pytest.fixture
async def client(
    migrated_database: None, email_sender: CapturingEmailSender
) -> AsyncIterator[AsyncClient]:
    """The real app, lifespan included, with outgoing email captured."""
    from rivon.main import app

    async with app.router.lifespan_context(app):
        app.state.email_sender = email_sender
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http


@dataclass(frozen=True)
class TenantUsers:
    """A provisioned tenant with an owner, a manager and an agent, and an
    Authorization header for each."""

    tenant_id: uuid.UUID
    owner: dict[str, str]
    manager: dict[str, str]
    agent: dict[str, str]


async def make_tenant(sessionmaker: async_sessionmaker[AsyncSession]) -> TenantUsers:
    from rivon.platform.auth import provision_tenant
    from rivon.platform.models import Region, User, UserRole
    from rivon.platform.security import UNUSABLE_PASSWORD, Principal, create_access_token
    from rivon.platform.tenancy import tenant_transaction

    settings = get_settings()
    suffix = uuid.uuid4().hex[:10]
    tenant = await provision_tenant(
        sessionmaker, settings, name=f"Tenant {suffix}", slug=f"t-{suffix}", region=Region.EU,
        owner_email=f"owner-{suffix}@example.com",
    )
    users = {UserRole.OWNER: tenant.owner_id}
    async with tenant_transaction(sessionmaker, tenant.tenant_id) as session:
        for role in (UserRole.MANAGER, UserRole.AGENT):
            users[role] = uuid.uuid4()
            session.add(
                User(id=users[role], tenant_id=tenant.tenant_id, role=role,
                     email=f"{role.value}-{suffix}@example.com", password_hash=UNUSABLE_PASSWORD)
            )

    def header(role: UserRole) -> dict[str, str]:
        token = create_access_token(
            Principal(users[role], tenant.tenant_id, role),
            settings.jwt_secret.get_secret_value(),
            settings.access_token_ttl_seconds,
        )
        return {"Authorization": f"Bearer {token}"}

    return TenantUsers(
        tenant.tenant_id, header(UserRole.OWNER), header(UserRole.MANAGER), header(UserRole.AGENT)
    )


@pytest.fixture
async def tenant(app_sessionmaker: async_sessionmaker[AsyncSession]) -> TenantUsers:
    return await make_tenant(app_sessionmaker)


@pytest.fixture
async def other_tenant(app_sessionmaker: async_sessionmaker[AsyncSession]) -> TenantUsers:
    return await make_tenant(app_sessionmaker)
