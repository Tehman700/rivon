"""pricing: settings per tenant, per-service overrides, rate card lines

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-19

Margin is gross margin on price: price = cost / (1 - margin). Capped at 95%
so the division is always safe. All rate card amounts are costs, net of VAT.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
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
    op.add_column("services", sa.Column("target_margin_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("services", sa.Column("vat_rate_percent", sa.Numeric(5, 2), nullable=True))
    op.create_check_constraint(
        op.f("ck_services_target_margin_range"),
        "services",
        "target_margin_percent IS NULL OR (target_margin_percent >= 0 AND target_margin_percent <= 95)",
    )
    op.create_check_constraint(
        op.f("ck_services_vat_rate_range"),
        "services",
        "vat_rate_percent IS NULL OR (vat_rate_percent >= 0 AND vat_rate_percent <= 100)",
    )

    op.create_table(
        "pricing_settings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("default_target_margin_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("minimum_margin_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("default_vat_rate_percent", sa.Numeric(5, 2), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_settings")),
        _tenant_fk("pricing_settings"),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_pricing_settings_tenant_id")),
        sa.CheckConstraint(
            "default_target_margin_percent >= 0 AND default_target_margin_percent <= 95",
            name=op.f("ck_pricing_settings_target_margin_range"),
        ),
        sa.CheckConstraint(
            "minimum_margin_percent >= 0 AND minimum_margin_percent <= default_target_margin_percent",
            name=op.f("ck_pricing_settings_minimum_margin_range"),
        ),
        sa.CheckConstraint(
            "default_vat_rate_percent >= 0 AND default_vat_rate_percent <= 100",
            name=op.f("ck_pricing_settings_vat_rate_range"),
        ),
    )
    op.create_index("ix_pricing_settings_tenant_id_created_at", "pricing_settings", ["tenant_id", "created_at"])
    _enable_rls("pricing_settings")

    op.create_table(
        "pricing_rules",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("quantity_basis", sa.String(32), nullable=False),
        sa.Column("quantity_factor", sa.Numeric(10, 4), server_default="1", nullable=False),
        sa.Column("unit_label", sa.String(20), nullable=False),
        sa.Column("unit_cost_eur", sa.Numeric(12, 2), nullable=False),
        sa.Column("included_quantity", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("minimum_quantity", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("round_up", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_rules")),
        _tenant_fk("pricing_rules"),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name=op.f("fk_pricing_rules_service_id_services"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "category IN ('materials', 'labour', 'transport', 'fees')", name=op.f("ck_pricing_rules_category")
        ),
        sa.CheckConstraint(
            "quantity_basis IN ('fixed', 'system_size_kwp', 'battery_capacity_kwh', 'distance_km')",
            name=op.f("ck_pricing_rules_quantity_basis"),
        ),
        sa.CheckConstraint("quantity_factor > 0", name=op.f("ck_pricing_rules_quantity_factor_positive")),
        sa.CheckConstraint("unit_cost_eur >= 0", name=op.f("ck_pricing_rules_unit_cost_not_negative")),
        sa.CheckConstraint(
            "included_quantity >= 0", name=op.f("ck_pricing_rules_included_quantity_not_negative")
        ),
        sa.CheckConstraint(
            "minimum_quantity >= 0", name=op.f("ck_pricing_rules_minimum_quantity_not_negative")
        ),
    )
    op.create_index("ix_pricing_rules_tenant_id_created_at", "pricing_rules", ["tenant_id", "created_at"])
    op.create_index("ix_pricing_rules_tenant_id_service_id", "pricing_rules", ["tenant_id", "service_id"])
    op.create_index(
        "uq_pricing_rules_tenant_id_service_id_name",
        "pricing_rules",
        ["tenant_id", "service_id", sa.text("lower(name)")],
        unique=True,
    )
    _enable_rls("pricing_rules")


def downgrade() -> None:
    op.drop_table("pricing_rules")
    op.drop_table("pricing_settings")
    op.drop_constraint(op.f("ck_services_vat_rate_range"), "services", type_="check")
    op.drop_constraint(op.f("ck_services_target_margin_range"), "services", type_="check")
    op.drop_column("services", "vat_rate_percent")
    op.drop_column("services", "target_margin_percent")
