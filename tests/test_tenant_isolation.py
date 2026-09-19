"""Tenant A must never see tenant B's rows.

Most of these tests use raw SQL with no WHERE clause, so the only thing
standing between tenants is the Postgres RLS policy, not an ORM filter.
"""

import uuid
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.config import get_settings
from rivon.db import create_engine
from rivon.platform.models import User
from rivon.platform.tenancy import (
    TenantContext,
    get_current_tenant_id,
    get_tenant_context,
    set_current_tenant,
    tenant_transaction,
)
from tests.conftest import Seed

TENANT_TABLES = ("tenants", "users")


async def _emails(session: AsyncSession) -> set[str]:
    rows = await session.execute(text("SELECT * FROM users"))
    return {row.email for row in rows}


# --- The database roles are set up so RLS cannot be bypassed ------------------


async def test_app_role_cannot_bypass_rls(db_session: AsyncSession) -> None:
    role = (
        await db_session.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
    ).one()
    assert role.rolname == "rivon_app"
    assert role.rolsuper is False
    assert role.rolbypassrls is False

    owners = await db_session.execute(
        text("SELECT tableowner FROM pg_tables WHERE tablename = ANY(:tables)"),
        {"tables": list(TENANT_TABLES)},
    )
    assert {row.tableowner for row in owners} == {"rivon_owner"}


async def test_rls_is_enabled_and_forced(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(:tables)"
        ),
        {"tables": list(TENANT_TABLES)},
    )
    flags = {row.relname: (row.relrowsecurity, row.relforcerowsecurity) for row in rows}
    assert flags == {table: (True, True) for table in TENANT_TABLES}


# --- Reads -----------------------------------------------------------------


async def test_raw_select_returns_only_current_tenant(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
        assert await _emails(session) == seed.tenant_a.emails
        tenant_ids = (await session.execute(text("SELECT id FROM tenants"))).scalars().all()
        assert tenant_ids == [seed.tenant_a.id]


async def test_no_tenant_context_returns_zero_rows(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Negative control: the policy is active and fails closed."""
    async with app_sessionmaker() as session:
        assert await _emails(session) == set()
        assert (await session.execute(text("SELECT * FROM tenants"))).all() == []


async def test_unknown_tenant_sees_nothing(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with tenant_transaction(app_sessionmaker, uuid.uuid4()) as session:
        assert await _emails(session) == set()


async def test_orm_query_is_scoped_too(seed: Seed, db_session: AsyncSession) -> None:
    await set_current_tenant(db_session, seed.tenant_b.id)
    users = (await db_session.scalars(select(User))).all()
    assert {u.email for u in users} == seed.tenant_b.emails
    assert {u.tenant_id for u in users} == {seed.tenant_b.id}


async def test_pooled_connection_does_not_leak_tenant(seed: Seed) -> None:
    """Reuse one pooled connection for A, then B, then no tenant.

    A connection-scoped `SET` would leave A's ID on the connection, and the
    third transaction would still see A's rows.
    """
    engine = create_engine(get_settings().database_url, pool_size=1, max_overflow=0)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    backend_pid = text("SELECT pg_backend_pid()")
    try:
        async with tenant_transaction(sessionmaker, seed.tenant_a.id) as session:
            pid_a = await session.scalar(backend_pid)
            assert await _emails(session) == seed.tenant_a.emails

        async with tenant_transaction(sessionmaker, seed.tenant_b.id) as session:
            pid_b = await session.scalar(backend_pid)
            assert await _emails(session) == seed.tenant_b.emails

        async with sessionmaker() as session:
            pid_none = await session.scalar(backend_pid)
            assert await _emails(session) == set()

        assert pid_a == pid_b == pid_none, "test must reuse a single pooled connection"
    finally:
        await engine.dispose()


# --- Writes ----------------------------------------------------------------


async def test_cannot_insert_row_for_another_tenant(seed: Seed, db_session: AsyncSession) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(DBAPIError, match="row-level security"):
        await db_session.execute(
            text(
                "INSERT INTO users (tenant_id, email, password_hash, role) "
                "VALUES (:tenant_id, 'mallory@b.example', 'x', 'owner')"
            ),
            {"tenant_id": seed.tenant_b.id},
        )


async def test_cannot_update_or_delete_another_tenants_rows(
    seed: Seed, db_session: AsyncSession
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    updated = await db_session.execute(
        text("UPDATE users SET role = 'agent' WHERE tenant_id = :b"), {"b": seed.tenant_b.id}
    )
    deleted = await db_session.execute(
        text("DELETE FROM users WHERE tenant_id = :b"), {"b": seed.tenant_b.id}
    )
    assert updated.rowcount == 0
    assert deleted.rowcount == 0


# --- The FastAPI dependency ------------------------------------------------


def _probe_app(sessionmaker: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = FastAPI()
    app.state.sessionmaker = sessionmaker

    @app.get("/probe")
    async def probe(ctx: Annotated[TenantContext, Depends(get_tenant_context)]) -> dict[str, object]:
        return {
            "tenant_id": str(ctx.tenant_id),
            "region": ctx.region,
            "emails": sorted(await _emails(ctx.session)),
        }

    return app


async def _get_probe(app: FastAPI, tenant_id: uuid.UUID | None) -> tuple[int, dict]:
    if tenant_id is not None:
        app.dependency_overrides[get_current_tenant_id] = lambda: tenant_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/probe")
    return response.status_code, response.json()


async def test_dependency_scopes_request_to_tenant(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    status, body = await _get_probe(_probe_app(app_sessionmaker), seed.tenant_b.id)
    assert status == 200
    assert body == {
        "tenant_id": str(seed.tenant_b.id),
        "region": "eu",
        "emails": sorted(seed.tenant_b.emails),
    }


async def test_dependency_rejects_unauthenticated_request(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    status, _ = await _get_probe(_probe_app(app_sessionmaker), None)
    assert status == 401


@pytest.mark.parametrize("which", ["suspended", "unknown"])
async def test_dependency_rejects_inactive_or_unknown_tenant(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession], which: str
) -> None:
    tenant_id = seed.suspended.id if which == "suspended" else uuid.uuid4()
    status, _ = await _get_probe(_probe_app(app_sessionmaker), tenant_id)
    assert status == 403
