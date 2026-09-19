"""refresh_tokens.rotated_at, for the concurrent-refresh grace window

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "rotated_at")
