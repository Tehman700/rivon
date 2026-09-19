"""tenants.region can never change

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19

A tenant's region decides where its data lives (spec §15.6). Moving a tenant
between regions is a data migration between deployments, never an UPDATE.

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION tenants_region_is_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.region IS DISTINCT FROM OLD.region THEN
            RAISE EXCEPTION 'tenants.region cannot change (tenant %)', OLD.id
              USING ERRCODE = 'check_violation',
                    HINT = 'Moving a tenant between regions is a data migration.';
          END IF;
          RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER tenants_region_immutable BEFORE UPDATE OF region ON tenants "
        "FOR EACH ROW EXECUTE FUNCTION tenants_region_is_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER tenants_region_immutable ON tenants")
    op.execute("DROP FUNCTION tenants_region_is_immutable()")
