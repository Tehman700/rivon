"""auth: global email, login lookup policy, refresh and password reset tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
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


def _token_table(name: str, *columns: sa.Column) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *columns,
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{name}_tenant_id_tenants"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f(f"fk_{name}_user_id_users"), ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", "token_hash", name=op.f(f"uq_{name}_tenant_id_token_hash")),
    )
    op.create_index(f"ix_{name}_tenant_id_created_at", name, ["tenant_id", "created_at"])
    _enable_rls(name)


def upgrade() -> None:
    # Email becomes the global login identity.
    op.drop_constraint("uq_users_tenant_id_email", "users", type_="unique")
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])

    # Login happens before the tenant is known. This SELECT-only policy exposes
    # exactly one row: the user whose email the login code has put in
    # app.login_email for the current transaction. It adds no write access.
    op.execute(
        "CREATE POLICY login_lookup ON users FOR SELECT "
        "USING (email = NULLIF(current_setting('app.login_email', true), ''))"
    )

    _token_table(
        "refresh_tokens",
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refresh_tokens_tenant_id_family_id", "refresh_tokens", ["tenant_id", "family_id"])
    op.create_index("ix_refresh_tokens_tenant_id_user_id", "refresh_tokens", ["tenant_id", "user_id"])

    _token_table(
        "password_reset_tokens",
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_tokens")
    op.execute("DROP POLICY login_lookup ON users")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_unique_constraint("uq_users_tenant_id_email", "users", ["tenant_id", "email"])
