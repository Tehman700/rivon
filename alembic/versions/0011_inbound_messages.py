"""customer messages, as they arrived

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-22

Written by the webhook before anything is done with the message, so nothing is
lost to a crash downstream (CHN-02).

The unique `(tenant_id, provider_message_id)` is the whole of CHN-04: Meta
retries any delivery it thinks we mishandled, and without this a retry becomes
a second reply to a real customer.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
PROVIDERS = "('whatsapp', 'messenger', 'instagram', 'fake')"


def upgrade() -> None:
    op.create_table(
        "inbound_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("contact_id", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(120), nullable=True),
        sa.Column("provider_message_id", sa.String(128), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "attachments", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("reply_to_provider_message_id", sa.String(128), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_messages")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_inbound_messages_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        # CHN-04. Per tenant, not global: two businesses could in principle be
        # handed the same provider id, and neither should block the other.
        sa.UniqueConstraint(
            "tenant_id", "provider_message_id",
            name="uq_inbound_messages_tenant_id_provider_message_id",
        ),
        sa.CheckConstraint(f"channel IN {PROVIDERS}", name=op.f("ck_inbound_messages_channel")),
        sa.CheckConstraint(
            "length(provider_message_id) > 0", name="ck_inbound_messages_provider_message_id_present"
        ),
    )
    op.create_index(
        "ix_inbound_messages_tenant_id_created_at", "inbound_messages", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_inbound_messages_tenant_id_account_id", "inbound_messages", ["tenant_id", "account_id"]
    )
    op.execute("ALTER TABLE inbound_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inbound_messages FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON inbound_messages "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def downgrade() -> None:
    op.drop_table("inbound_messages")
