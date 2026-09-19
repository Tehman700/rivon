"""OPS-02/03: transactional outbox, relay, Celery delivery, exactly-once effect."""

import asyncio
import random
import string
import uuid
from collections.abc import Iterator

import pytest
from celery.contrib.testing.worker import start_worker
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.events.core import Event, Queue, deliver, publish, subscribe, unsubscribe
from rivon.events.models import EventDelivery, OutboxEvent
from rivon.events.relay import celery_dispatch, relay_batch
from rivon.platform.tenancy import tenant_transaction
from tests.conftest import Seed

Dispatched = tuple[uuid.UUID, uuid.UUID, str, Queue]


def _letters(n: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


@pytest.fixture
def event_type() -> str:
    """A fresh event type per test, so relays only find this test's subscribers."""
    return f"probe.{_letters()}"


@pytest.fixture
def registered() -> Iterator[list[str]]:
    """Subscriber names registered by the test; unregistered afterwards."""
    names: list[str] = []
    yield names
    for name in names:
        unsubscribe(name)


def _subscribe(registered: list[str], event_type: str, queue: Queue, calls: list[Event]) -> str:
    name = f"test.{_letters()}"

    @subscribe(event_type, name=name, queue=queue)
    async def handler(session: AsyncSession, event: Event) -> None:
        calls.append(event)

    registered.append(name)
    return name


async def _publish(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, event_type: str, **payload: object
) -> uuid.UUID:
    async with tenant_transaction(sessionmaker, tenant_id) as session:
        return await publish(session, tenant_id, event_type, dict(payload))


async def _drain(
    relay_sessionmaker: async_sessionmaker[AsyncSession], dispatched: list[Dispatched]
) -> None:
    def dispatch(event_id: uuid.UUID, tenant_id: uuid.UUID, name: str, queue: Queue) -> None:
        dispatched.append((event_id, tenant_id, name, queue))

    while await relay_batch(relay_sessionmaker, dispatch, batch_size=50) == 50:
        pass


# --- Publishing ---------------------------------------------------------------


async def test_event_exists_only_if_the_transaction_commits(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession], event_type: str
) -> None:
    committed = await _publish(app_sessionmaker, seed.tenant_a.id, event_type, n=1)

    rolled_back: uuid.UUID | None = None
    with pytest.raises(RuntimeError):
        async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
            rolled_back = await publish(session, seed.tenant_a.id, event_type, {"n": 2})
            raise RuntimeError("the change failed")

    async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
        ids = set((await session.scalars(select(OutboxEvent.id))).all())
    assert committed in ids
    assert rolled_back not in ids


async def test_cannot_publish_for_another_tenant(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession], event_type: str
) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await _publish(app_sessionmaker, seed.tenant_a.id, event_type)  # control: this one works
        async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
            await publish(session, seed.tenant_b.id, event_type, {})


async def test_tenants_cannot_see_each_others_events(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession], event_type: str
) -> None:
    event_id = await _publish(app_sessionmaker, seed.tenant_a.id, event_type)
    async with tenant_transaction(app_sessionmaker, seed.tenant_b.id) as session:
        found = await session.scalar(text("SELECT count(*) FROM outbox_events WHERE id = :id"), {"id": event_id})
    assert found == 0


def test_event_types_are_validated() -> None:
    for bad in ["lead", "Lead.Scored", "lead.scored.extra", "lead.1"]:
        with pytest.raises(ValueError):
            subscribe(bad, name=f"x.{_letters()}", queue=Queue.AI)


# --- Relay --------------------------------------------------------------------


async def test_relay_dispatches_each_subscriber_on_its_queue_once(
    seed: Seed,
    app_sessionmaker: async_sessionmaker[AsyncSession],
    relay_sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    registered: list[str],
) -> None:
    ai = _subscribe(registered, event_type, Queue.AI, [])
    outbound = _subscribe(registered, event_type, Queue.OUTBOUND, [])
    events = {
        await _publish(app_sessionmaker, seed.tenant_a.id, event_type, n=1): seed.tenant_a.id,
        await _publish(app_sessionmaker, seed.tenant_a.id, event_type, n=2): seed.tenant_a.id,
        await _publish(app_sessionmaker, seed.tenant_b.id, event_type, n=3): seed.tenant_b.id,
    }

    dispatched: list[Dispatched] = []
    await _drain(relay_sessionmaker, dispatched)
    mine = [d for d in dispatched if d[0] in events]
    assert sorted(mine) == sorted(
        [(eid, tid, ai, Queue.AI) for eid, tid in events.items()]
        + [(eid, tid, outbound, Queue.OUTBOUND) for eid, tid in events.items()]
    )

    async with relay_sessionmaker() as session:
        rows = (await session.scalars(select(OutboxEvent).where(OutboxEvent.id.in_(events)))).all()
    assert all(row.published_at is not None for row in rows)

    again: list[Dispatched] = []
    await _drain(relay_sessionmaker, again)
    assert [d for d in again if d[0] in events] == []


async def test_failed_dispatch_is_retried_on_the_next_pass(
    seed: Seed,
    app_sessionmaker: async_sessionmaker[AsyncSession],
    relay_sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    registered: list[str],
) -> None:
    _subscribe(registered, event_type, Queue.AI, [])
    event_id = await _publish(app_sessionmaker, seed.tenant_a.id, event_type)

    def broken(event_id: uuid.UUID, *_: object) -> None:
        raise ConnectionError("redis is down")

    await relay_batch(relay_sessionmaker, broken, batch_size=500)
    async with relay_sessionmaker() as session:
        row = await session.get(OutboxEvent, event_id)
        assert row is not None
        assert (row.published_at, row.attempts) == (None, 1)
        assert "redis is down" in (row.last_error or "")

    dispatched: list[Dispatched] = []
    await _drain(relay_sessionmaker, dispatched)
    assert [d[0] for d in dispatched if d[0] == event_id] == [event_id]


async def test_concurrent_relays_never_dispatch_an_event_twice(
    seed: Seed,
    app_sessionmaker: async_sessionmaker[AsyncSession],
    relay_sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    registered: list[str],
) -> None:
    _subscribe(registered, event_type, Queue.AI, [])
    events = {await _publish(app_sessionmaker, seed.tenant_a.id, event_type, n=i) for i in range(30)}

    dispatched: list[Dispatched] = []

    def dispatch(event_id: uuid.UUID, tenant_id: uuid.UUID, name: str, queue: Queue) -> None:
        dispatched.append((event_id, tenant_id, name, queue))

    async def relay_until_empty() -> None:
        while await relay_batch(relay_sessionmaker, dispatch, batch_size=3):
            await asyncio.sleep(0)

    await asyncio.gather(*(relay_until_empty() for _ in range(3)))
    mine = [d[0] for d in dispatched if d[0] in events]
    assert sorted(mine) == sorted(events)  # each exactly once


async def test_relay_role_is_confined_to_the_outbox(
    seed: Seed, relay_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    for statement in [
        "SELECT * FROM users",
        "SELECT * FROM tenants",
        "SELECT * FROM event_deliveries",
        "DELETE FROM outbox_events",
        f"INSERT INTO outbox_events (tenant_id, event_type, payload) "
        f"VALUES ('{seed.tenant_a.id}', 'x.y', '{{}}')",
    ]:
        async with relay_sessionmaker() as session:
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(text(statement))


# --- Delivery -----------------------------------------------------------------


async def test_delivery_runs_the_handler_exactly_once(
    seed: Seed,
    app_sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    registered: list[str],
) -> None:
    calls: list[Event] = []
    name = _subscribe(registered, event_type, Queue.AI, calls)
    event_id = await _publish(app_sessionmaker, seed.tenant_b.id, event_type, lead="L-1")

    assert await deliver(app_sessionmaker, event_id, seed.tenant_b.id, name) is True
    assert await deliver(app_sessionmaker, event_id, seed.tenant_b.id, name) is False
    assert len(calls) == 1
    assert (calls[0].id, calls[0].tenant_id, calls[0].type, calls[0].payload) == (
        event_id, seed.tenant_b.id, event_type, {"lead": "L-1"},
    )


async def test_failed_handler_rolls_back_and_can_be_retried(
    seed: Seed,
    app_sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    registered: list[str],
) -> None:
    follow_up_type = f"probe.{_letters()}"
    attempts: list[int] = []
    name = f"test.{_letters()}"

    @subscribe(event_type, name=name, queue=Queue.AI)
    async def flaky(session: AsyncSession, event: Event) -> None:
        attempts.append(1)
        # Handler effects share the delivery's transaction...
        await publish(session, event.tenant_id, follow_up_type, {"attempt": len(attempts)})
        if len(attempts) == 1:
            raise TimeoutError("LLM timed out")

    registered.append(name)
    event_id = await _publish(app_sessionmaker, seed.tenant_a.id, event_type)

    with pytest.raises(TimeoutError):
        await deliver(app_sessionmaker, event_id, seed.tenant_a.id, name)
    assert await deliver(app_sessionmaker, event_id, seed.tenant_a.id, name) is True

    async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
        follow_ups = (
            await session.scalars(select(OutboxEvent.payload).where(OutboxEvent.event_type == follow_up_type))
        ).all()
        deliveries = await session.scalar(
            select(text("count(*)")).select_from(EventDelivery).where(EventDelivery.event_id == event_id)
        )
    # ...so the failed attempt left nothing behind: one follow-up, one delivery.
    assert follow_ups == [{"attempt": 2}]
    assert deliveries == 1


async def test_delivery_to_unknown_subscriber_fails_loudly(
    seed: Seed, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(LookupError):
        await deliver(app_sessionmaker, uuid.uuid4(), seed.tenant_a.id, "nobody.here")


# --- End to end through Redis and a real Celery worker --------------------------


async def test_event_reaches_subscriber_through_celery(
    seed: Seed,
    app_sessionmaker: async_sessionmaker[AsyncSession],
    relay_sessionmaker: async_sessionmaker[AsyncSession],
    event_type: str,
    registered: list[str],
) -> None:
    from rivon.worker import celery_app

    calls: list[Event] = []
    name = _subscribe(registered, event_type, Queue.INBOUND, calls)
    event_id = await _publish(app_sessionmaker, seed.tenant_a.id, event_type, message="hi")

    with start_worker(
        celery_app,
        pool="solo",
        perform_ping_check=False,
        queues=[q.value for q in Queue],
        shutdown_timeout=30,
    ):
        while await relay_batch(relay_sessionmaker, celery_dispatch, batch_size=50) == 50:
            pass
        for _ in range(150):
            if calls:
                break
            await asyncio.sleep(0.1)

    assert [(c.id, c.payload) for c in calls] == [(event_id, {"message": "hi"})]
    async with tenant_transaction(app_sessionmaker, seed.tenant_a.id) as session:
        delivered = await session.scalar(
            select(EventDelivery.subscriber).where(EventDelivery.event_id == event_id)
        )
    assert delivered == name
