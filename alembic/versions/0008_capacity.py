"""service areas, inventory and crews

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-20

The three things feasibility checks a job against: do we cover the address,
do we hold the stock, is a crew free (BIZ-05, BIZ-06, BIZ-07).

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TENANT = "NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"


def _common(table: str) -> list:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _constraints(table: str) -> list:
    return [
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"), ondelete="RESTRICT"
        ),
    ]


def _finish(table: str) -> None:
    op.create_index(f"ix_{table}_tenant_id_created_at", table, ["tenant_id", "created_at"])
    op.create_index(
        f"uq_{table}_tenant_id_name", table, ["tenant_id", sa.text("lower(name)")], unique=True
    )
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {CURRENT_TENANT}) WITH CHECK (tenant_id = {CURRENT_TENANT})"
    )


def upgrade() -> None:
    op.create_table(
        "service_areas",
        *_common("service_areas"),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column(
            "postal_prefixes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        *_constraints("service_areas"),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_service_areas_country_iso2")),
        sa.CheckConstraint(
            "jsonb_typeof(postal_prefixes) = 'array'", name=op.f("ck_service_areas_postal_prefixes_array")
        ),
    )
    _finish("service_areas")

    op.create_table(
        "inventory_items",
        *_common("inventory_items"),
        sa.Column("sku", sa.String(60), nullable=True),
        sa.Column("unit_label", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("low_stock_threshold", sa.Numeric(12, 2), nullable=True),
        *_constraints("inventory_items"),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_inventory_items_quantity_not_negative")),
        sa.CheckConstraint(
            "low_stock_threshold IS NULL OR low_stock_threshold >= 0",
            name=op.f("ck_inventory_items_low_stock_threshold_not_negative"),
        ),
    )
    _finish("inventory_items")

    op.create_table(
        "crews",
        *_common("crews"),
        sa.Column("headcount", sa.Integer(), server_default="1", nullable=False),
        sa.Column("weekly_capacity_hours", sa.Numeric(6, 2), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        *_constraints("crews"),
        sa.CheckConstraint("headcount >= 1", name=op.f("ck_crews_headcount_positive")),
        sa.CheckConstraint("weekly_capacity_hours > 0", name=op.f("ck_crews_weekly_capacity_positive")),
    )
    _finish("crews")


def downgrade() -> None:
    op.drop_table("crews")
    op.drop_table("inventory_items")
    op.drop_table("service_areas")
