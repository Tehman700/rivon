"""Domain events: publish into the outbox, subscribe, deliver exactly once.

    # inside a tenant transaction, alongside the change it describes
    await publish(session, tenant_id, "lead.scored", {"lead_id": str(lead.id)})

    @subscribe("lead.scored", name="feasibility.on_lead_scored", queue=Queue.AI)
    async def on_lead_scored(session: AsyncSession, event: Event) -> None: ...

Delivery is at-least-once from the queue and exactly-once in effect: the
handler runs in the same transaction that records the delivery, so a
redelivered event is skipped and a failed handler leaves no record behind.
"""

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.events.models import EventDelivery, OutboxEvent
from rivon.platform.tenancy import tenant_transaction


class Queue(StrEnum):
    """Celery queues, split by workload class (spec §7.3)."""

    INBOUND = "rivon.inbound"  # latency-sensitive: a customer is waiting
    AI = "rivon.ai"  # slow, expensive, externally rate-limited
    OUTBOUND = "rivon.outbound"  # rate-limited per tenant per channel
    SCHEDULED = "rivon.scheduled"  # nightly rollups, delayed triggers


EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")


@dataclass(frozen=True)
class Event:
    id: uuid.UUID
    tenant_id: uuid.UUID
    type: str
    payload: dict[str, Any]
    occurred_at: datetime


Handler = Callable[[AsyncSession, Event], Awaitable[None]]


@dataclass(frozen=True)
class Subscriber:
    name: str
    event_type: str
    queue: Queue
    handler: Handler


_subscribers: dict[str, Subscriber] = {}


def subscribe(event_type: str, *, name: str, queue: Queue) -> Callable[[Handler], Handler]:
    """Register `handler` for `event_type`. `name` is stored with each delivery,
    so it must stay stable once events have been delivered to it."""
    if not EVENT_TYPE_PATTERN.match(event_type):
        raise ValueError(f"bad event type {event_type!r}")

    def register(handler: Handler) -> Handler:
        if name in _subscribers:
            raise ValueError(f"subscriber {name!r} is already registered")
        _subscribers[name] = Subscriber(name, event_type, queue, handler)
        return handler

    return register


def unsubscribe(name: str) -> None:
    _subscribers.pop(name, None)


def subscribers_for(event_type: str) -> list[Subscriber]:
    return [s for s in _subscribers.values() if s.event_type == event_type]


async def publish(
    session: AsyncSession, tenant_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> uuid.UUID:
    """Add an event to the outbox. Must run inside the tenant transaction that
    makes the change, so the event exists if and only if the change commits."""
    if not EVENT_TYPE_PATTERN.match(event_type):
        raise ValueError(f"bad event type {event_type!r}")
    event = OutboxEvent(id=uuid.uuid4(), tenant_id=tenant_id, event_type=event_type, payload=payload)
    session.add(event)
    await session.flush()
    return event.id


async def deliver(
    sessionmaker: async_sessionmaker[AsyncSession],
    event_id: uuid.UUID,
    tenant_id: uuid.UUID,
    subscriber_name: str,
) -> bool:
    """Run one subscriber for one event. Returns False if it already ran."""
    subscriber = _subscribers.get(subscriber_name)
    if subscriber is None:
        raise LookupError(f"no subscriber named {subscriber_name!r} in this process")

    async with tenant_transaction(sessionmaker, tenant_id) as session:
        claimed = await session.scalar(
            insert(EventDelivery)
            .values(id=uuid.uuid4(), tenant_id=tenant_id, event_id=event_id, subscriber=subscriber_name)
            .on_conflict_do_nothing(index_elements=["tenant_id", "event_id", "subscriber"])
            .returning(EventDelivery.id)
        )
        if claimed is None:
            return False
        row = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
        if row is None:
            raise LookupError(f"event {event_id} not found for tenant {tenant_id}")
        await subscriber.handler(
            session,
            Event(row.id, row.tenant_id, row.event_type, row.payload, row.occurred_at),
        )
    return True
