"""A placeholder reply, so the whole path can be watched working.

This is the seam the conversation engine drops into. Everything around it —
routing, deduplication, the dispatcher, the credential — is the real thing; only
the words are stand-ins. When CNV-01 arrives it replaces this handler and
nothing else has to move.

It answers on the `message.received` event rather than inside the webhook,
which is what keeps the webhook fast enough that Meta does not retry it.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels import outbound, service
from rivon.channels.crypto import TokenUnreadable
from rivon.channels.inbound import MESSAGE_RECEIVED
from rivon.channels.messages import Channel, OutboundMessage, dedupe_key_for
from rivon.channels.meta import MetaApiError
from rivon.channels.models import ConnectionStatus, ReceivedMessage
from rivon.config import get_settings
from rivon.events.core import Event, Queue, subscribe

log = logging.getLogger(__name__)

#: Says what it is. These are real messaging accounts even in testing, so a
#: stranger who finds one should not think a person is typing.
ECHO_TEXT = "Hello 👋 This is Rivon's automated assistant. We're still being set up."

#: Swapped for a fake in tests; built from settings in the worker.
_sender: outbound.Sender | None = None


def sender() -> outbound.Sender:
    global _sender
    if _sender is None:
        _sender = outbound.Sender(version=get_settings().meta_graph_version)
    return _sender


def use_sender(replacement: outbound.Sender | None) -> None:
    """Point the echo at a different sender. Tests only."""
    global _sender
    _sender = replacement


@subscribe(MESSAGE_RECEIVED, name="channels.echo_reply", queue=Queue.OUTBOUND)
async def echo_reply(session: AsyncSession, event: Event) -> None:
    """Answer one inbound message.

    The dedupe key is derived from the message being answered, so a redelivered
    event converges on the one reply instead of sending a second.
    """
    message = await session.get(ReceivedMessage, event.payload["message_id"])
    if message is None or message.tenant_id != event.tenant_id:
        log.warning("message.received for a message this tenant does not have")
        return

    connection = await service.connection_for(
        session, event.tenant_id, Channel(message.channel), message.account_id
    )
    if connection is None or connection.status is not ConnectionStatus.ACTIVE:
        # Disconnected between the message arriving and this running. Nothing to
        # reply with, and nothing worth retrying.
        log.info("no active connection for %s %s", message.channel, message.account_id)
        return

    reply = OutboundMessage(
        channel=Channel(message.channel),
        account_id=message.account_id,
        contact_id=message.contact_id,
        text=ECHO_TEXT,
        dedupe_key=dedupe_key_for("echo", message.id),
        reply_to_provider_message_id=message.provider_message_id,
    )

    record = await outbound.queue(session, event.tenant_id, reply)
    if record is None:
        return  # already claimed by an earlier delivery of this event

    try:
        token = await service.access_token_for(session, event.tenant_id, connection.id)
    except TokenUnreadable:
        log.warning("cannot read the credential for connection %s", connection.id)
        return

    try:
        await outbound.deliver(
            session, event.tenant_id, record, sender=sender(), access_token=token
        )
    except outbound.NotDeliverable as exc:
        # Recorded on the row with a reason; no point failing the event and
        # having the queue bring it back for the same answer. But a dead
        # credential is not just an undelivered message — the customer has to
        # be told to reconnect, or their business is left wondering why nobody
        # is being answered.
        if isinstance(exc.cause, MetaApiError) and exc.cause.is_auth_failure:
            await service.mark_needs_reauth(
                session, event.tenant_id, connection.id, "Meta rejected the stored credential"
            )
            return
        log.warning("giving up on reply %s: %s", record.dedupe_key, exc)
    except MetaApiError:
        raise  # retryable: let the queue bring it back
