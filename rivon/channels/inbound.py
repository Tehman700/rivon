"""CHN-02/03/04: what happens to a webhook delivery, and in what order.

    verify the signature -> find the tenant -> store the message -> enqueue -> 200

Hard rule 3 says the webhook path does no work, and this is the least that
still satisfies it. Parsing is pure translation with no I/O. Routing is one
indexed lookup returning a single UUID. Storing is the "persist the raw
payload" the rule asks for. Everything after — reading it, answering it — is a
worker's job, reached through the `message.received` event on the outbox.

The reason for the discipline is concrete: Meta retries anything we are slow to
acknowledge, and a retried delivery that gets processed twice is a second reply
to a real customer.

Three outcomes are normal and none of them is an error:

*stored* — a new message, now on the outbox.
*duplicate* — a retry. Recognised by `(tenant_id, provider_message_id)` and
 dropped without a second event.
*unrouted* — an account nobody has connected, or one that was disconnected.
 Meta keeps sending for a while after a customer removes us, so this is
 expected traffic, not a failure. Answering anything other than 200 would make
 it retry for hours.
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.channels import service
from rivon.channels.adapters import registry
from rivon.channels.messages import Channel, InboundMessage
from rivon.channels.models import ReceivedMessage
from rivon.events.core import publish
from rivon.platform.tenancy import tenant_transaction

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
MESSAGE_RECEIVED = "message.received"


@dataclass
class ReceiptSummary:
    """What a single webhook delivery amounted to. Returned for tests and logs."""

    stored: int = 0
    duplicates: int = 0
    unrouted: int = 0
    unparsed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.stored + self.duplicates + self.unrouted


def signature_is_valid(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """Is this really from Meta?

    HMAC-SHA256 of the **raw** body, keyed with the app secret. It must be the
    exact bytes received: re-serialising the parsed JSON changes whitespace and
    key order, and the signature stops matching.

    Compared with `compare_digest` so the comparison cannot be timed.
    """
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def verify_challenge(params: dict[str, str], verify_token: str) -> str | None:
    """Meta's one-time check when a webhook URL is first configured.

    It calls with a token we chose and a challenge; echoing the challenge back
    proves the endpoint is ours. Returns None when it does not add up, so the
    caller answers 403 rather than confirming a URL to someone else.
    """
    if params.get("hub.mode") != "subscribe":
        return None
    given = params.get("hub.verify_token") or ""
    if not hmac.compare_digest(given, verify_token):
        return None
    return params.get("hub.challenge")


async def receive(
    sessionmaker: async_sessionmaker[AsyncSession],
    channel: Channel,
    payload: dict,
) -> ReceiptSummary:
    """Route, store and enqueue everything in one delivery."""
    summary = ReceiptSummary()
    adapter = registry.adapter_for(channel)
    try:
        messages = adapter.parse(payload)
    except ValueError as exc:
        # Something we could not make sense of. Recorded and acknowledged: a
        # retry would deliver the same thing we already cannot read.
        log.warning("unreadable %s webhook payload: %s", channel, exc)
        summary.unparsed.append(str(exc))
        return summary

    # One lookup per account rather than per message: a busy Page can deliver a
    # dozen messages from different people in a single call.
    routes: dict[str, object] = {}
    async with sessionmaker() as session:
        for account_id in {m.account_id for m in messages}:
            routes[account_id] = await service.route_to_tenant(session, channel, account_id)

    for message in messages:
        tenant_id = routes.get(message.account_id)
        if tenant_id is None:
            summary.unrouted += 1
            log.info("no active connection for %s account %s", channel, message.account_id)
            continue
        async with tenant_transaction(sessionmaker, tenant_id) as session:  # type: ignore[arg-type]
            if await _store(session, tenant_id, message):  # type: ignore[arg-type]
                summary.stored += 1
            else:
                summary.duplicates += 1
    return summary


async def _store(session: AsyncSession, tenant_id, message: InboundMessage) -> bool:  # type: ignore[no-untyped-def]
    """Insert the message and enqueue it, unless we have seen it before.

    The insert and the event share one transaction, so a message is never
    stored without being enqueued, and never enqueued twice.
    """
    statement = (
        insert(ReceivedMessage)
        .values(
            tenant_id=tenant_id,
            channel=message.channel,
            account_id=message.account_id,
            contact_id=message.contact_id,
            contact_name=message.contact_name,
            provider_message_id=message.provider_message_id,
            text=message.text,
            attachments=[
                {
                    "kind": a.kind.value,
                    "url": a.url,
                    "media_id": a.provider_media_id,
                    "mime_type": a.mime_type,
                    "filename": a.filename,
                }
                for a in message.attachments
            ],
            reply_to_provider_message_id=message.reply_to_provider_message_id,
            sent_at=message.sent_at,
            raw=message.raw,
        )
        # The retry case. DO NOTHING returns no row, which is how we tell a new
        # message from one Meta has sent us before.
        .on_conflict_do_nothing(
            constraint="uq_inbound_messages_tenant_id_provider_message_id"
        )
        .returning(ReceivedMessage.id)
    )
    stored_id = (await session.execute(statement)).scalar_one_or_none()
    if stored_id is None:
        return False

    await publish(
        session,
        tenant_id,
        MESSAGE_RECEIVED,
        {
            "message_id": str(stored_id),
            "channel": message.channel.value,
            "account_id": message.account_id,
            "contact_id": message.contact_id,
            "provider_message_id": message.provider_message_id,
        },
    )
    return True


async def messages_for_contact(
    session: AsyncSession, tenant_id, account_id: str, contact_id: str, limit: int = 50
):  # type: ignore[no-untyped-def]
    """The conversation so far, oldest first. Used by the worker and the UI."""
    result = await session.execute(
        select(ReceivedMessage)
        .where(
            ReceivedMessage.tenant_id == tenant_id,
            ReceivedMessage.account_id == account_id,
            ReceivedMessage.contact_id == contact_id,
        )
        .order_by(ReceivedMessage.sent_at.desc())
        .limit(limit)
    )
    return list(reversed(list(result.scalars())))
