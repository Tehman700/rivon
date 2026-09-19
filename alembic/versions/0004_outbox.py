"""transactional outbox and consumer deduplication

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19

outbox_events: domain events written in the same transaction as the change.
event_deliveries: one row per (event, subscriber) handled, for idempotency.

The relay reads unpublished events across all tenants, which tenant RLS
forbids. Instead of loosening RLS, the rivon_relay role (created with the
database, see docker/postgres/init) gets a policy on outbox_events alone and
SELECT/UPDATE on that table only.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"), ondelete="RESTRICT"
    )


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        _tenant_fk("outbox_events"),
    )
    op.create_index("ix_outbox_events_tenant_id_created_at", "outbox_events", ["tenant_id", "created_at"])
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    _enable_rls("outbox_events")
    op.execute(
        "CREATE POLICY relay_access ON outbox_events TO rivon_relay USING (true) WITH CHECK (true)"
    )
    op.execute("GRANT SELECT, UPDATE ON outbox_events TO rivon_relay")

    op.create_table(
        "event_deliveries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("subscriber", sa.String(100), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_deliveries")),
        _tenant_fk("event_deliveries"),
        sa.UniqueConstraint(
            "tenant_id", "event_id", "subscriber", name=op.f("uq_event_deliveries_tenant_id_event_id_subscriber")
        ),
    )
    op.create_index("ix_event_deliveries_tenant_id_created_at", "event_deliveries", ["tenant_id", "created_at"])
    _enable_rls("event_deliveries")


def downgrade() -> None:
    op.drop_table("event_deliveries")
    op.drop_table("outbox_events")
