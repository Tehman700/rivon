"""per-business tuning for the vertical configuration

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-20

The question set lives in code and is the same for every solar installer
(BIZ-08). These are the numbers each business adjusts: yield per kWp, roof
area per kWp, and how often the assistant chases an answer before handing
the conversation over.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "vertical_settings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vertical", sa.String(32), server_default="solar", nullable=False),
        sa.Column("annual_kwh_per_kwp", sa.Numeric(6, 2), server_default="950", nullable=False),
        sa.Column("roof_area_m2_per_kwp", sa.Numeric(6, 2), server_default="5", nullable=False),
        sa.Column("max_followups", sa.Integer(), server_default="2", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vertical_settings")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_vertical_settings_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_vertical_settings_tenant_id")),
        sa.CheckConstraint("vertical IN ('solar')", name=op.f("ck_vertical_settings_known_vertical")),
        sa.CheckConstraint(
            "annual_kwh_per_kwp > 0", name=op.f("ck_vertical_settings_annual_kwh_per_kwp_positive")
        ),
        sa.CheckConstraint(
            "roof_area_m2_per_kwp > 0", name=op.f("ck_vertical_settings_roof_area_per_kwp_positive")
        ),
        sa.CheckConstraint(
            "max_followups BETWEEN 0 AND 5", name=op.f("ck_vertical_settings_max_followups_range")
        ),
    )
    op.create_index(
        "ix_vertical_settings_tenant_id_created_at", "vertical_settings", ["tenant_id", "created_at"]
    )
    op.execute("ALTER TABLE vertical_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE vertical_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON vertical_settings "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def downgrade() -> None:
    op.drop_table("vertical_settings")
