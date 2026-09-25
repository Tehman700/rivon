"""a customer part-way through choosing which Page to connect

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-25

For the beta "choose your Page" flow, which logs in with a user token rather
than a business one so it can list every Page the person manages — including one
they go off and create on Facebook in the middle of connecting.

The token is kept encrypted for the length of the session only. Nothing is
routed through this table, so it needs no exception to any schema rule.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "channel_picker_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "granted_scopes",
            postgresql.ARRAY(sa.String(64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_picker_sessions")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_channel_picker_sessions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"],
            name=op.f("fk_channel_picker_sessions_started_by_user_id_users"), ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "octet_length(user_token_encrypted) > 0", name="ck_channel_picker_sessions_token_present"
        ),
    )
    op.create_index(
        "ix_channel_picker_sessions_tenant_id_created_at",
        "channel_picker_sessions",
        ["tenant_id", "created_at"],
    )
    # Led by tenant_id like every other index: the sweep is always per tenant.
    op.create_index(
        "ix_channel_picker_sessions_tenant_id_expires_at",
        "channel_picker_sessions",
        ["tenant_id", "expires_at"],
    )
    op.execute("ALTER TABLE channel_picker_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE channel_picker_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON channel_picker_sessions "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def downgrade() -> None:
    op.drop_table("channel_picker_sessions")
