"""tenants and users, with row level security

Revision ID: 0001
Revises:
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NULLIF: once the setting has been set in a session, current_setting() returns
# '' (not NULL) after the transaction ends, and ''::uuid would raise. With no
# tenant set the predicate is NULL, so the policy fails closed: zero rows.
CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _enable_rls(table: str, key_column: str) -> None:
    # FORCE makes the policy apply to the table owner too. Without it the owner
    # role bypasses RLS and the policy silently does nothing for it.
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({key_column} = {CURRENT_TENANT}) "
        f"WITH CHECK ({key_column} = {CURRENT_TENANT})"
    )


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
        sa.CheckConstraint("region IN ('eu', 'non_eu')", name=op.f("ck_tenants_region")),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'suspended')", name=op.f("ck_tenants_status")
        ),
    )
    _enable_rls("tenants", "id")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id_tenants"), ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("tenant_id", "email", name=op.f("uq_users_tenant_id_email")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.CheckConstraint("role IN ('owner', 'manager', 'agent')", name=op.f("ck_users_role")),
    )
    op.create_index("ix_users_tenant_id_created_at", "users", ["tenant_id", "created_at"])
    _enable_rls("users", "tenant_id")


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("tenants")
