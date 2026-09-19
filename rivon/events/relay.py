"""Outbox relay: moves committed events onto the Celery queues.

    python -m rivon.events.relay

Connects as rivon_relay, which can read and update outbox_events across all
tenants and nothing else. Several relays can run at once: rows are claimed
with FOR UPDATE SKIP LOCKED. A crash after dispatch but before marking the
event published means it is dispatched again; `deliver` deduplicates that.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.config import get_settings
from rivon.db import create_engine
from rivon.events.core import Queue, subscribers_for
from rivon.events.models import OutboxEvent

logger = logging.getLogger("rivon.relay")

# (event_id, tenant_id, subscriber_name, queue) -> None; raises if it couldn't enqueue.
Dispatch = Callable[[uuid.UUID, uuid.UUID, str, Queue], None]

MAX_ERROR_LENGTH = 2000


async def relay_batch(
    sessionmaker: async_sessionmaker[AsyncSession], dispatch: Dispatch, batch_size: int
) -> int:
    """Dispatch up to `batch_size` unpublished events. Returns how many were
    handled (published or failed), so the caller knows whether to sleep."""
    async with sessionmaker() as session, session.begin():
        events = (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for event in events:
            try:
                for subscriber in subscribers_for(event.event_type):
                    dispatch(event.id, event.tenant_id, subscriber.name, subscriber.queue)
            except Exception as exc:
                event.attempts += 1
                event.last_error = repr(exc)[:MAX_ERROR_LENGTH]
                logger.warning("dispatch failed event=%s attempts=%d", event.id, event.attempts)
                continue
            event.published_at = datetime.now(UTC)
        return len(events)


def celery_dispatch(event_id: uuid.UUID, tenant_id: uuid.UUID, subscriber: str, queue: Queue) -> None:
    from rivon.worker import celery_app

    celery_app.send_task(
        "rivon.events.deliver", args=[str(event_id), str(tenant_id), subscriber], queue=queue.value
    )


async def run() -> None:
    settings = get_settings()
    if settings.relay_database_url is None:
        raise SystemExit("RIVON_RELAY_DATABASE_URL is not set")

    import rivon.subscribers  # noqa: F401  (registers every subscriber)

    engine = create_engine(settings.relay_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("relay started")
    try:
        while True:
            handled = await relay_batch(sessionmaker, celery_dispatch, settings.relay_batch_size)
            if handled < settings.relay_batch_size:
                await asyncio.sleep(settings.relay_poll_interval_seconds)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())
