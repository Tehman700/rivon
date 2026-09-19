import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from rivon.db import Base, BaseMixin, TenantScopedMixin


class OutboxEvent(BaseMixin, TenantScopedMixin, Base):
    """A domain event, written in the same transaction as the change it
    describes. The relay later puts it on the Celery queues."""

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(100))
    # IDs and non-personal fields by default (data minimisation, spec §7.4).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            # The relay's work queue, across tenants: unpublished events, oldest first.
            Index(
                "ix_outbox_events_unpublished",
                "created_at",
                postgresql_where=text("published_at IS NULL"),
            ),
        )


class EventDelivery(BaseMixin, TenantScopedMixin, Base):
    """Records that a subscriber handled an event. Written in the same
    transaction as the handler's effects, so a redelivered event is skipped."""

    __tablename__ = "event_deliveries"

    event_id: Mapped[uuid.UUID]
    subscriber: Mapped[str] = mapped_column(String(100))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(UniqueConstraint("tenant_id", "event_id", "subscriber"))
