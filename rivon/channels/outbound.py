"""CHN-05: saying something back.

One dispatcher for every channel. The adapter decides what the request looks
like, the connection supplies the credential, and this module decides whether
the send happens at all.

That last part is the whole job. Events are delivered at least once and tasks
are retried, so the same reply can be asked for several times. Each request
carries a `dedupe_key` derived from its cause, and the first one to claim that
key is the only one that sends. Everything else is a no-op. The alternative is
a customer receiving the same message three times, which is the most visible
way for this system to look broken.

Sending is recorded before it is attempted and updated afterwards, so a message
that never arrived leaves a trace with a reason, rather than vanishing.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels.adapters import registry
from rivon.channels.messages import Channel, OutboundMessage
from rivon.channels.meta import GRAPH_HOST, MetaApiError, Transport
from rivon.channels.models import OutboundMessageRecord, SendStatus

log = logging.getLogger(__name__)

#: After this many tries a message is marked failed and left alone. Meta is not
#: going to change its mind, and a queue retrying forever hides the problem.
MAX_ATTEMPTS = 5


class NotDeliverable(Exception):
    """The message cannot be sent, and retrying will not help.

    Carries the original failure: the caller has to be able to tell a dead
    credential (the connection needs reconnecting, and the dashboard must say
    so) from a message that simply cannot be delivered.
    """

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


@dataclass
class Sender:
    """Performs what an adapter described.

    The transport is injected for the same reason as in `meta.py`: the entire
    outbound path is then testable with no network and no credentials.
    """

    version: str = "v25.0"
    transport: Transport | None = None

    async def send(self, channel: Channel, message: OutboundMessage, access_token: str) -> str:
        adapter = registry.adapter_for(channel)
        request = adapter.render(message)
        transport = self.transport or _default_transport
        payload = await transport(
            request.method,
            f"{GRAPH_HOST}/{self.version}/{request.path}",
            {"access_token": access_token},
            request.json,
        )
        error = payload.get("error")
        if error:
            raise MetaApiError(
                error.get("message") or "Meta rejected the message",
                code=error.get("code"),
                subcode=error.get("error_subcode"),
            )
        return adapter.read_send_result(payload)


async def queue(
    session: AsyncSession, tenant_id: Any, message: OutboundMessage
) -> OutboundMessageRecord | None:
    """Claim the right to send this message.

    Returns the row on the first claim and None on every repeat. The uniqueness
    is enforced by the database rather than by looking first and inserting
    after, because two workers can be holding the same event at the same moment.
    """
    statement = (
        insert(OutboundMessageRecord)
        .values(
            tenant_id=tenant_id,
            channel=message.channel,
            account_id=message.account_id,
            contact_id=message.contact_id,
            text=message.text,
            dedupe_key=message.dedupe_key,
            reply_to_provider_message_id=message.reply_to_provider_message_id,
            status=SendStatus.PENDING,
        )
        .on_conflict_do_nothing(constraint="uq_outbound_messages_tenant_id_dedupe_key")
        .returning(OutboundMessageRecord.id)
    )
    new_id = (await session.execute(statement)).scalar_one_or_none()
    if new_id is None:
        log.info("outbound %s already claimed; not sending again", message.dedupe_key)
        return None
    return await session.get(OutboundMessageRecord, new_id)


async def deliver(
    session: AsyncSession,
    tenant_id: Any,
    record: OutboundMessageRecord,
    *,
    sender: Sender,
    access_token: str,
) -> OutboundMessageRecord:
    """Send a claimed message, and record what happened either way.

    A message already sent is left alone: this runs under at-least-once
    delivery, so being asked twice is normal rather than exceptional.
    """
    if record.status is SendStatus.SENT:
        return record
    if record.status is SendStatus.FAILED:
        raise NotDeliverable(record.last_error or "this message was given up on")

    record.attempts += 1
    try:
        provider_message_id = await sender.send(
            record.channel,
            OutboundMessage(
                channel=record.channel,
                account_id=record.account_id,
                contact_id=record.contact_id,
                text=record.text,
                dedupe_key=record.dedupe_key,
                reply_to_provider_message_id=record.reply_to_provider_message_id,
            ),
            access_token,
        )
    except (MetaApiError, ValueError) as exc:
        record.last_error = str(exc)[:300]
        if record.attempts >= MAX_ATTEMPTS or _is_permanent(exc):
            record.status = SendStatus.FAILED
            await session.flush()
            raise NotDeliverable(record.last_error, cause=exc) from exc
        await session.flush()
        raise  # a retryable failure: let the queue bring it back

    record.provider_message_id = provider_message_id
    record.status = SendStatus.SENT
    record.sent_at = datetime.now(UTC)
    record.last_error = None
    await session.flush()
    return record


def _is_permanent(exc: Exception) -> bool:
    """Retrying an expired token or a closed window only wastes attempts.

    190 is "this token no longer works"; 131047 is WhatsApp's "more than 24
    hours since the customer wrote", which needs an approved template rather
    than another try.
    """
    return isinstance(exc, MetaApiError) and exc.code in (190, 131047)


async def pending_for(session: AsyncSession, tenant_id: Any, limit: int = 100):  # type: ignore[no-untyped-def]
    result = await session.execute(
        select(OutboundMessageRecord)
        .where(
            OutboundMessageRecord.tenant_id == tenant_id,
            OutboundMessageRecord.status == SendStatus.PENDING,
        )
        .order_by(OutboundMessageRecord.created_at)
        .limit(limit)
    )
    return list(result.scalars())


async def _default_transport(
    method: str, url: str, params: dict[str, Any], data: dict[str, Any] | None
) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(method, url, params=params or None, json=data)
    try:
        payload = response.json()
    except ValueError:
        raise MetaApiError(f"Meta returned {response.status_code} with no JSON body") from None
    return payload if isinstance(payload, dict) else {"data": payload}
