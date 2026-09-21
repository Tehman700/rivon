"""CHN-05: the dispatcher and the echo reply.

The failure these tests exist to prevent is a customer receiving the same
message twice. Events are delivered at least once and tasks are retried, so
"asked to send this again" is the normal case, not the exception — and every
one of those paths has to converge on a single message.

The rest is about not going quiet: a send that fails leaves a row with a
reason, a dead credential marks its connection for reconnection, and a message
nobody can deliver is given up on rather than retried forever.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels import echo, outbound, service
from rivon.channels.crypto import TokenCipher
from rivon.channels.messages import Channel, OutboundMessage, dedupe_key_for
from rivon.channels.meta import MetaApiError
from rivon.channels.models import (
    ConnectionStatus,
    OutboundMessageRecord,
    ReceivedMessage,
    SendStatus,
)
from rivon.channels.service import ConnectionInput
from rivon.events.core import Event
from rivon.platform.tenancy import set_current_tenant
from tests.conftest import Seed


class FakeSend:
    """Stands in for Meta's send endpoint."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.error: dict[str, Any] | None = None
        self.raise_once: Exception | None = None

    async def __call__(
        self, method: str, url: str, params: dict[str, Any], data: dict[str, Any] | None
    ) -> dict[str, Any]:
        if self.raise_once is not None:
            failure, self.raise_once = self.raise_once, None
            raise failure
        if self.error:
            return {"error": self.error}
        self.sent.append({"url": url, "params": params, "body": data})
        return {"message_id": f"m-out-{len(self.sent)}"}


@pytest.fixture
def transport() -> FakeSend:
    return FakeSend()


@pytest.fixture
def sender(transport: FakeSend) -> outbound.Sender:
    return outbound.Sender(transport=transport)


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(TokenCipher.generate_key())


def reply(dedupe_key: str = "echo:m-1", text: str = "Hello") -> OutboundMessage:
    return OutboundMessage(
        channel=Channel.MESSENGER, account_id="page-1", contact_id="psid-1",
        text=text, dedupe_key=dedupe_key,
    )


# --- Claiming the right to send -----------------------------------------------


async def test_the_first_claim_wins_and_the_rest_are_no_ops(
    db_session: AsyncSession, seed: Seed
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)

    first = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert first is not None and first.status is SendStatus.PENDING

    for _ in range(3):
        assert await outbound.queue(db_session, seed.tenant_a.id, reply()) is None

    count = await db_session.scalar(
        select(func.count()).select_from(OutboundMessageRecord).where(
            OutboundMessageRecord.tenant_id == seed.tenant_a.id
        )
    )
    assert count == 1


async def test_different_causes_are_different_messages(
    db_session: AsyncSession, seed: Seed
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    assert await outbound.queue(db_session, seed.tenant_a.id, reply("echo:m-1")) is not None
    assert await outbound.queue(db_session, seed.tenant_a.id, reply("echo:m-2")) is not None


async def test_two_businesses_can_use_the_same_key(
    db_session: AsyncSession, seed: Seed
) -> None:
    # Dedupe keys are derived from provider ids, which are only unique per
    # account. Making them globally unique would let one business's reply
    # silence another's.
    await set_current_tenant(db_session, seed.tenant_a.id)
    assert await outbound.queue(db_session, seed.tenant_a.id, reply()) is not None
    await set_current_tenant(db_session, seed.tenant_b.id)
    assert await outbound.queue(db_session, seed.tenant_b.id, reply()) is not None


# --- Sending ------------------------------------------------------------------


async def test_a_sent_message_records_what_meta_called_it(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None

    await outbound.deliver(db_session, seed.tenant_a.id, record, sender=sender, access_token="T")

    assert record.status is SendStatus.SENT
    assert record.provider_message_id == "m-out-1"
    assert record.sent_at is not None
    assert record.attempts == 1

    [call] = transport.sent
    assert call["url"].endswith("/page-1/messages")
    assert call["params"]["access_token"] == "T"
    assert call["body"]["recipient"] == {"id": "psid-1"}


async def test_delivering_an_already_sent_message_does_nothing(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    # The at-least-once case. Being asked again must not mean a second message.
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None

    for _ in range(3):
        await outbound.deliver(
            db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
        )

    assert len(transport.sent) == 1
    assert record.attempts == 1


async def test_a_retryable_failure_is_raised_and_counted(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None
    transport.error = {"message": "Please reduce the amount of data", "code": 4}

    with pytest.raises(MetaApiError):
        await outbound.deliver(
            db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
        )

    assert record.status is SendStatus.PENDING, "still deliverable"
    assert record.attempts == 1
    assert "reduce the amount of data" in (record.last_error or "")


async def test_a_dead_token_is_not_retried(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    # Code 190 means the credential is gone. Trying again just burns attempts.
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None
    transport.error = {"message": "Error validating access token", "code": 190}

    with pytest.raises(outbound.NotDeliverable):
        await outbound.deliver(
            db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
        )
    assert record.status is SendStatus.FAILED


async def test_a_closed_24_hour_window_is_not_retried(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None
    transport.error = {"message": "Message failed to send because more than 24 hours "
                                  "have passed", "code": 131047}

    with pytest.raises(outbound.NotDeliverable):
        await outbound.deliver(
            db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
        )
    assert record.status is SendStatus.FAILED


async def test_a_message_is_given_up_on_rather_than_retried_forever(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None
    transport.error = {"message": "Temporary failure", "code": 2}

    for _ in range(outbound.MAX_ATTEMPTS - 1):
        with pytest.raises(MetaApiError):
            await outbound.deliver(
                db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
            )
    with pytest.raises(outbound.NotDeliverable):
        await outbound.deliver(
            db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
        )

    assert record.status is SendStatus.FAILED
    assert record.attempts == outbound.MAX_ATTEMPTS
    assert record.last_error, "a failed send always says why"


async def test_a_failed_message_is_not_quietly_resurrected(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    record = await outbound.queue(db_session, seed.tenant_a.id, reply())
    assert record is not None
    record.status = SendStatus.FAILED
    record.last_error = "given up on"

    with pytest.raises(outbound.NotDeliverable):
        await outbound.deliver(
            db_session, seed.tenant_a.id, record, sender=sender, access_token="T"
        )
    assert transport.sent == []


async def test_whatsapp_and_messenger_are_addressed_differently(
    db_session: AsyncSession, seed: Seed, sender: outbound.Sender, transport: FakeSend
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    whatsapp = OutboundMessage(
        channel=Channel.WHATSAPP, account_id="pn-1", contact_id="4915112345678",
        text="Hello", dedupe_key="echo:w-1",
    )
    record = await outbound.queue(db_session, seed.tenant_a.id, whatsapp)
    assert record is not None
    transport.error = None

    # WhatsApp answers with messages[0].id rather than message_id.
    async def whatsapp_transport(method, url, params, data):  # type: ignore[no-untyped-def]
        transport.sent.append({"url": url, "params": params, "body": data})
        return {"messages": [{"id": "wamid.out"}]}

    await outbound.deliver(
        db_session, seed.tenant_a.id, record,
        sender=outbound.Sender(transport=whatsapp_transport), access_token="T",
    )

    assert record.provider_message_id == "wamid.out"
    assert transport.sent[-1]["body"]["messaging_product"] == "whatsapp"


# --- The echo -----------------------------------------------------------------


@pytest.fixture
def echo_sender(sender: outbound.Sender):  # type: ignore[no-untyped-def]
    echo.use_sender(sender)
    yield sender
    echo.use_sender(None)


async def arrive(
    session: AsyncSession, tenant_id: uuid.UUID, cipher: TokenCipher, *,
    account_id: str = "page-echo", provider_message_id: str = "m-1",
) -> tuple[ReceivedMessage, Any]:
    """A connected account with one message waiting to be answered."""
    connection = await service.connect(
        session, tenant_id,
        ConnectionInput(provider=Channel.MESSENGER, external_id=account_id,
                        access_token="PAGE-TOKEN"),
        cipher=cipher,
    )
    message = ReceivedMessage(
        tenant_id=tenant_id, channel=Channel.MESSENGER, account_id=account_id,
        contact_id="psid-1", provider_message_id=provider_message_id, text="hi",
        sent_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    session.add(message)
    await session.flush()
    return message, connection


def received_event(tenant_id: uuid.UUID, message: ReceivedMessage) -> Event:
    from datetime import UTC, datetime

    return Event(
        id=uuid.uuid4(), tenant_id=tenant_id, type="message.received",
        payload={"message_id": str(message.id)}, occurred_at=datetime.now(UTC),
    )


async def test_a_message_gets_one_reply(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    message, _ = await arrive(db_session, seed.tenant_a.id, cipher)

    await echo.echo_reply(db_session, received_event(seed.tenant_a.id, message))

    assert len(transport.sent) == 1
    assert transport.sent[0]["body"]["message"]["text"] == echo.ECHO_TEXT
    assert transport.sent[0]["params"]["access_token"] == "PAGE-TOKEN"


async def test_the_reply_says_it_is_an_assistant(
    db_session: AsyncSession, seed: Seed
) -> None:
    # These are real accounts even while testing. Someone who finds one should
    # not believe a person is typing.
    assert "assistant" in echo.ECHO_TEXT.lower()


async def test_a_redelivered_event_does_not_send_a_second_reply(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one that would be visible to a customer."""
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    message, _ = await arrive(db_session, seed.tenant_a.id, cipher)
    event = received_event(seed.tenant_a.id, message)

    for _ in range(3):
        await echo.echo_reply(db_session, event)

    assert len(transport.sent) == 1


async def test_two_different_messages_get_two_replies(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    first, _ = await arrive(db_session, seed.tenant_a.id, cipher, provider_message_id="m-1")
    second = ReceivedMessage(
        tenant_id=seed.tenant_a.id, channel=Channel.MESSENGER, account_id="page-echo",
        contact_id="psid-1", provider_message_id="m-2", text="hello",
        sent_at=first.sent_at,
    )
    db_session.add(second)
    await db_session.flush()

    await echo.echo_reply(db_session, received_event(seed.tenant_a.id, first))
    await echo.echo_reply(db_session, received_event(seed.tenant_a.id, second))

    assert len(transport.sent) == 2


async def test_nothing_is_sent_for_a_disconnected_account(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    message, connection = await arrive(db_session, seed.tenant_a.id, cipher)
    await service.disconnect(db_session, seed.tenant_a.id, connection.id)

    await echo.echo_reply(db_session, received_event(seed.tenant_a.id, message))
    assert transport.sent == []


async def test_nothing_is_sent_on_a_connection_waiting_to_be_reconnected(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unlike a disconnect, this one keeps its token — the customer revoked us at
    # Meta's end, so the credential is still there and still useless. Trying
    # anyway just burns attempts against an account we know is not listening.
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    message, connection = await arrive(db_session, seed.tenant_a.id, cipher)
    await service.mark_needs_reauth(
        db_session, seed.tenant_a.id, connection.id, "customer revoked access"
    )

    await echo.echo_reply(db_session, received_event(seed.tenant_a.id, message))
    assert transport.sent == []


async def test_a_rejected_credential_marks_the_connection_for_reconnection(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The customer removed us at Meta's end. The dashboard has to say so, or the
    # business is left wondering why nobody is being answered.
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    message, connection = await arrive(db_session, seed.tenant_a.id, cipher)
    transport.error = {"message": "Error validating access token", "code": 190}

    await echo.echo_reply(db_session, received_event(seed.tenant_a.id, message))

    assert connection.status is ConnectionStatus.NEEDS_REAUTH


async def test_an_event_for_someone_elses_message_is_ignored(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher,
    echo_sender: outbound.Sender, transport: FakeSend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_token_cipher", lambda: cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    message, _ = await arrive(db_session, seed.tenant_a.id, cipher)

    event = received_event(seed.tenant_b.id, message)
    await echo.echo_reply(db_session, event)
    assert transport.sent == []


async def test_the_reply_key_is_derived_from_the_message_it_answers() -> None:
    assert dedupe_key_for("echo", "abc") == "echo:abc"
    assert dedupe_key_for("echo", "abc") != dedupe_key_for("echo", "abd")
