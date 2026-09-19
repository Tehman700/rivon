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
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from rivon.config import Settings, get_settings
from rivon.db import create_engine
from rivon.platform.tenancy import set_current_tenant

TEST_DATABASE = "rivon_test"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _to_test_database(url: str) -> str:
    return make_url(url).set(database=TEST_DATABASE).render_as_string(hide_password=False)


# Point everything, including rivon.config.get_settings(), at the test database.
_base = Settings()  # type: ignore[call-arg]
os.environ["RIVON_DATABASE_URL"] = _to_test_database(_base.database_url)
os.environ["RIVON_MIGRATION_DATABASE_URL"] = _to_test_database(_base.migration_database_url)
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
        await conn.execute(text("TRUNCATE users, tenants"))


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
