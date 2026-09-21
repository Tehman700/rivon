"""connected messaging accounts and their sealed credentials

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22

One row per Facebook Page, Instagram account or WhatsApp number a business has
connected (CHN-07), with the access token encrypted before it ever arrives here.

Two things in this migration are deliberate departures worth reading:

`(provider, external_id)` is unique across the whole table rather than per
tenant. The routing lookup cannot lead with `tenant_id` because finding the
tenant *is* the query. Global uniqueness also makes it impossible for two
businesses to claim the same Page, which would be a cross-tenant message leak.

`channel_route()` is SECURITY DEFINER, so it runs as the table's owner and sees
past RLS. It is the only cross-tenant read in the system. It takes a provider
and an external id and returns a single UUID — never a row, never a token — and
only for a connection that is currently active.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
PROVIDERS = "('whatsapp', 'messenger', 'instagram', 'fake')"
STATUSES = "('active', 'needs_reauth', 'revoked')"


def _tenant_isolation(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def upgrade() -> None:
    op.create_table(
        "channel_connections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("parent_external_id", sa.String(64), nullable=True),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("token_type", sa.String(32), server_default="business_system_user", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "granted_scopes",
            postgresql.ARRAY(sa.String(64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("status_detail", sa.String(200), nullable=True),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "provider_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_connections")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_channel_connections_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["connected_by_user_id"], ["users.id"],
            name=op.f("fk_channel_connections_connected_by_user_id_users"), ondelete="SET NULL",
        ),
        # Not led by tenant_id, on purpose — see the module docstring.
        sa.UniqueConstraint(
            "provider", "external_id", name="uq_channel_connections_provider_external_id"
        ),
        sa.CheckConstraint(f"provider IN {PROVIDERS}", name=op.f("ck_channel_connections_provider")),
        sa.CheckConstraint(f"status IN {STATUSES}", name=op.f("ck_channel_connections_status")),
        sa.CheckConstraint(
            "length(external_id) > 0", name="ck_channel_connections_external_id_present"
        ),
        sa.CheckConstraint(
            "octet_length(access_token_encrypted) > 0", name="ck_channel_connections_token_present"
        ),
    )
    op.create_index(
        "ix_channel_connections_tenant_id_created_at", "channel_connections", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_channel_connections_tenant_id_provider", "channel_connections", ["tenant_id", "provider"]
    )
    _tenant_isolation("channel_connections")

    op.create_table(
        "channel_oauth_states",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_oauth_states")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_channel_oauth_states_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"],
            name=op.f("fk_channel_oauth_states_started_by_user_id_users"), ondelete="SET NULL",
        ),
        sa.UniqueConstraint("state", name="uq_channel_oauth_states_state"),
        sa.CheckConstraint(f"provider IN {PROVIDERS}", name=op.f("ck_channel_oauth_states_provider")),
        sa.CheckConstraint("length(state) >= 16", name="ck_channel_oauth_states_state_long_enough"),
    )
    op.create_index(
        "ix_channel_oauth_states_tenant_id_created_at", "channel_oauth_states", ["tenant_id", "created_at"]
    )
    op.create_index("ix_channel_oauth_states_expires_at", "channel_oauth_states", ["expires_at"])
    _tenant_isolation("channel_oauth_states")

    # The one cross-tenant read in the system.
    #
    # `FORCE ROW LEVEL SECURITY` binds the table's owner as well, so a
    # SECURITY DEFINER function is not on its own enough — it would be filtered
    # like anyone else and return nothing. Rather than let the owner read every
    # row (which is what a plain owner policy would mean), the function raises a
    # transaction-local flag around its single query, and the policy below only
    # opens while that flag is set. The application role is not covered by that
    # policy at all, so setting the flag itself gains it nothing.
    op.execute(
        """
        CREATE POLICY route_lookup ON channel_connections
        FOR SELECT TO rivon_owner
        USING (current_setting('app.channel_route', true) = 'on')
        """
    )
    op.execute(
        """
        CREATE FUNCTION channel_route(p_provider text, p_external_id text)
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            owning_tenant uuid;
        BEGIN
            PERFORM set_config('app.channel_route', 'on', true);
            SELECT tenant_id INTO owning_tenant
            FROM channel_connections
            WHERE provider = p_provider
              AND external_id = p_external_id
              AND status = 'active';
            PERFORM set_config('app.channel_route', 'off', true);
            RETURN owning_tenant;
        EXCEPTION WHEN OTHERS THEN
            -- Never leave the flag raised for the rest of the transaction.
            PERFORM set_config('app.channel_route', 'off', true);
            RAISE;
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION channel_route(text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION channel_route(text, text) TO rivon_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS channel_route(text, text)")
    op.drop_table("channel_oauth_states")
    op.drop_table("channel_connections")
