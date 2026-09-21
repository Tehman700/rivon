"""what we intend to say, written before we say it

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-22

CHN-05. The unique `(tenant_id, dedupe_key)` is the reason the table exists:
events are delivered at least once and tasks are retried, so two attempts must
converge on one message rather than two to a real person.

Rows are kept after sending — a failed send that nobody can see is a customer's
question going unanswered with no trace of why.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
PROVIDERS = "('whatsapp', 'messenger', 'instagram', 'fake')"
STATUSES = "('pending', 'sent', 'failed')"


def upgrade() -> None:
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("contact_id", sa.String(128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.Column("reply_to_provider_message_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_messages")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_outbound_messages_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "dedupe_key", name="uq_outbound_messages_tenant_id_dedupe_key"
        ),
        sa.CheckConstraint(f"channel IN {PROVIDERS}", name=op.f("ck_outbound_messages_channel")),
        sa.CheckConstraint(f"status IN {STATUSES}", name=op.f("ck_outbound_messages_status")),
        sa.CheckConstraint("length(text) > 0", name="ck_outbound_messages_text_present"),
        sa.CheckConstraint("attempts >= 0", name="ck_outbound_messages_attempts_not_negative"),
    )
    op.create_index(
        "ix_outbound_messages_tenant_id_created_at", "outbound_messages", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_outbound_messages_tenant_id_status", "outbound_messages", ["tenant_id", "status"]
    )
    op.execute("ALTER TABLE outbound_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outbound_messages FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON outbound_messages "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def downgrade() -> None:
    op.drop_table("outbound_messages")
