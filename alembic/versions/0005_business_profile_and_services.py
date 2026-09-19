"""business profile (one per tenant) and services catalogue

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
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
        "businesses",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("assistant_name", sa.String(60), server_default="Rivon", nullable=False),
        sa.Column("contact_email", sa.String(320), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        sa.Column("website", sa.String(300), nullable=True),
        sa.Column("address_line", sa.String(300), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column(
            "business_hours", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("min_project_size", sa.Numeric(12, 2), nullable=True),
        sa.Column("max_project_size", sa.Numeric(12, 2), nullable=True),
        sa.Column("project_size_unit", sa.String(16), nullable=True),
        sa.Column("min_project_value_eur", sa.Numeric(12, 2), nullable=True),
        sa.Column("max_project_value_eur", sa.Numeric(12, 2), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_businesses")),
        _tenant_fk("businesses"),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_businesses_tenant_id")),
        sa.CheckConstraint("country IS NULL OR country ~ '^[A-Z]{2}$'", name=op.f("ck_businesses_country_iso2")),
        sa.CheckConstraint(
            "project_size_unit IN ('kWp')", name=op.f("ck_businesses_project_size_unit")
        ),
        sa.CheckConstraint(
            "(min_project_size IS NULL AND max_project_size IS NULL) OR project_size_unit IS NOT NULL",
            name=op.f("ck_businesses_project_size_has_unit"),
        ),
        sa.CheckConstraint(
            "min_project_size IS NULL OR min_project_size > 0",
            name=op.f("ck_businesses_min_project_size_positive"),
        ),
        sa.CheckConstraint(
            "min_project_size IS NULL OR max_project_size IS NULL OR min_project_size <= max_project_size",
            name=op.f("ck_businesses_project_size_range"),
        ),
        sa.CheckConstraint(
            "min_project_value_eur IS NULL OR min_project_value_eur > 0",
            name=op.f("ck_businesses_min_project_value_positive"),
        ),
        sa.CheckConstraint(
            "min_project_value_eur IS NULL OR max_project_value_eur IS NULL "
            "OR min_project_value_eur <= max_project_value_eur",
            name=op.f("ck_businesses_project_value_range"),
        ),
    )
    op.create_index("ix_businesses_tenant_id_created_at", "businesses", ["tenant_id", "created_at"])
    _enable_rls("businesses")

    op.create_table(
        "services",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
        _tenant_fk("services"),
    )
    op.create_index("ix_services_tenant_id_created_at", "services", ["tenant_id", "created_at"])
    op.create_index(
        "uq_services_tenant_id_name_active",
        "services",
        ["tenant_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    _enable_rls("services")


def downgrade() -> None:
    op.drop_table("services")
    op.drop_table("businesses")
