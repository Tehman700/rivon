"""Schema and migration conventions (OPS-09), checked against the migrated database.

These run against the schema the real migrations produce, so a future
migration that forgets `tenant_id`, RLS, or a tenant-led index fails here
rather than in review.
"""

import re
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rivon.models import metadata
from tests.conftest import REPO_ROOT

VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"

# Tables that are not tenant-scoped, and why.
NOT_TENANT_SCOPED = {
    "alembic_version": "Alembic bookkeeping",
    "tenants": "the tenancy root; its id is the tenant_id",
}

# Indexes on tenant-scoped tables that may not lead with tenant_id, and why.
# Every entry needs a reason a reviewer would accept.
INDEX_EXCEPTIONS: dict[str, str] = {}


async def _rows(engine: AsyncEngine, sql: str) -> list:
    async with engine.connect() as conn:
        return list(await conn.execute(text(sql)))


async def _tables(engine: AsyncEngine) -> set[str]:
    rows = await _rows(engine, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {row.tablename for row in rows}


async def test_models_match_migrations(owner_engine: AsyncEngine) -> None:
    """`alembic check` equivalent: no difference between models and the migrated schema."""

    def compare(sync_conn):  # type: ignore[no-untyped-def]
        return compare_metadata(MigrationContext.configure(sync_conn), metadata)

    async with owner_engine.connect() as conn:
        diff = await conn.run_sync(compare)
    assert diff == []


async def test_every_table_has_standard_columns(owner_engine: AsyncEngine) -> None:
    rows = await _rows(
        owner_engine,
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns WHERE table_schema = 'public'
        """,
    )
    columns = {(r.table_name, r.column_name): (r.data_type, r.is_nullable) for r in rows}
    expected = {
        "id": ("uuid", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    }
    for table in await _tables(owner_engine) - {"alembic_version"}:
        for column, spec in expected.items():
            assert columns.get((table, column)) == spec, f"{table}.{column}"


async def test_tenant_scoped_tables_have_tenant_id(owner_engine: AsyncEngine) -> None:
    rows = await _rows(
        owner_engine,
        """
        SELECT c.table_name, c.data_type, c.is_nullable,
               EXISTS (
                 SELECT 1 FROM information_schema.table_constraints tc
                 JOIN information_schema.key_column_usage k
                   ON k.constraint_name = tc.constraint_name AND k.table_name = tc.table_name
                 JOIN information_schema.constraint_column_usage u
                   ON u.constraint_name = tc.constraint_name
                 WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = c.table_name
                   AND k.column_name = 'tenant_id' AND u.table_name = 'tenants'
               ) AS references_tenants
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id'
        """,
    )
    tenant_columns = {r.table_name: r for r in rows}
    for table in await _tables(owner_engine) - NOT_TENANT_SCOPED.keys():
        column = tenant_columns.get(table)
        assert column is not None, f"{table} has no tenant_id"
        assert (column.data_type, column.is_nullable) == ("uuid", "NO"), table
        assert column.references_tenants, f"{table}.tenant_id has no FK to tenants"


async def test_every_table_forces_rls_with_tenant_policy(owner_engine: AsyncEngine) -> None:
    rows = await _rows(
        owner_engine,
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               EXISTS (SELECT 1 FROM pg_policies p
                       WHERE p.tablename = c.relname AND p.policyname = 'tenant_isolation')
                 AS has_policy
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version'
        """,
    )
    assert rows, "no tables found"
    for row in rows:
        assert row.relrowsecurity and row.relforcerowsecurity, f"{row.relname}: RLS not forced"
        assert row.has_policy, f"{row.relname}: no tenant_isolation policy"


async def test_indexes_on_tenant_tables_lead_with_tenant_id(owner_engine: AsyncEngine) -> None:
    rows = await _rows(
        owner_engine,
        """
        SELECT t.relname AS table_name, i.relname AS index_name,
               a.attname AS first_column, ix.indisprimary
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ix.indkey[0]
        WHERE n.nspname = 'public'
        """,
    )
    offenders = [
        row.index_name
        for row in rows
        if row.table_name not in NOT_TENANT_SCOPED
        and not row.indisprimary
        and row.first_column != "tenant_id"
        and row.index_name not in INDEX_EXCEPTIONS
    ]
    assert offenders == [], f"indexes not led by tenant_id: {offenders}"
    for name in INDEX_EXCEPTIONS:
        assert any(row.index_name == name for row in rows), f"stale exception: {name}"


def test_migrations_are_a_single_numbered_chain() -> None:
    script = ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1, "multiple heads: merge or renumber"

    revisions = sorted(rev.revision for rev in script.walk_revisions())
    assert revisions == [f"{n:04d}" for n in range(1, len(revisions) + 1)]

    for rev in script.walk_revisions():
        assert Path(rev.path).name.startswith(f"{rev.revision}_"), rev.path


def test_migrations_do_not_import_app_code() -> None:
    """A migration must keep meaning what it meant when it ran, so it can't
    depend on app code that will change later."""
    for path in VERSIONS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+rivon\b", source, re.MULTILINE), path.name
