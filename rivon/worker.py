"""Celery app and the event delivery task.

    celery -A rivon.worker worker -Q rivon.inbound,rivon.ai,rivon.outbound,rivon.scheduled

Tasks are sync; each worker process keeps one event loop and one database
engine, created lazily after the prefork so nothing is shared across processes.
"""

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any, TypeVar

from celery import Celery
from celery.signals import worker_process_shutdown
from kombu import Queue as KombuQueue
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import rivon.subscribers  # noqa: F401  (registers every subscriber)
from rivon.config import get_settings
from rivon.db import create_engine
from rivon.events.core import Queue, deliver

T = TypeVar("T")

celery_app = Celery("rivon", broker=get_settings().redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_queues=[KombuQueue(q.value) for q in Queue],
    task_default_queue=Queue.SCHEDULED.value,
    # A task is acknowledged only after it finishes, and one at a time per
    # process, so a crashed worker's task is redelivered instead of lost.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

_loop: asyncio.AbstractEventLoop | None = None
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop.run_until_complete(coro)


def worker_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = create_engine(get_settings().database_url)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


@worker_process_shutdown.connect
def _dispose_engine(**_: Any) -> None:
    if _engine is not None:
        run_async(_engine.dispose())


@celery_app.task(
    name="rivon.events.deliver",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=8,
)
def deliver_event(event_id: str, tenant_id: str, subscriber: str) -> bool:
    return run_async(
        deliver(worker_sessionmaker(), uuid.UUID(event_id), uuid.UUID(tenant_id), subscriber)
    )
