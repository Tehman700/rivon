import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, MetaData, func, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names, so migrations and models always agree.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class BaseMixin:
    """Columns every table has: UUID primary key and UTC timestamps."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantScopedMixin:
    """Adds `tenant_id` and the `(tenant_id, created_at)` index.

    Every index on a tenant-scoped table must lead with `tenant_id`. Tables that
    need more table args override `__table_args__` and pass them through
    `tenant_table_args()` so the base index is kept.

    The migration for each tenant-scoped table must also ENABLE and FORCE row
    level security with the `tenant_isolation` policy (see 0001 for the SQL).
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))

    @classmethod
    def tenant_table_args(cls, *extra: Any) -> tuple[Any, ...]:
        tablename = cls.__tablename__  # type: ignore[attr-defined]
        return (Index(f"ix_{tablename}_tenant_id_created_at", "tenant_id", "created_at"), *extra)

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args()


def create_engine(url: str, **kwargs: Any) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, **kwargs)
