"""CHN-01: the internal message model, the adapter contract, and the fake channel.

These tests are the contract the real Meta adapters will have to satisfy, so
they lean on the things that cause real damage if they are wrong: an identifier
that turns out to be empty, a timestamp without an offset, a batch where only
the first message is read, and a webhook delivery that carries no message at all
being mistaken for a failure.

Nothing here touches a network, a token or a database. That is the point of the
fake channel (hard rule 4).
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from rivon.channels import (
    AdapterRegistry,
    Attachment,
    AttachmentKind,
    Channel,
    InboundMessage,
    OutboundMessage,
    OutboundRequest,
    UnknownChannel,
    dedupe_key_for,
    registry,
)
from rivon.channels.fake import FAKE_ADAPTER, FakeAdapter, FakeProvider


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(account_id="acct-solar")


# --- Parsing ------------------------------------------------------------------


def test_a_message_survives_the_trip_intact(provider: FakeProvider) -> None:
    sent_at = datetime(2026, 9, 21, 9, 30, tzinfo=UTC)
    payload = provider.inbound("  Hi there  ", contact_id="c-1", message_id="m-1",
                               name="Ana", sent_at=sent_at)

    [message] = FAKE_ADAPTER.parse(payload)

    assert message.channel is Channel.FAKE
    assert message.account_id == "acct-solar"  # the routing key back to the tenant
    assert message.contact_id == "c-1"
    assert message.provider_message_id == "m-1"
    assert message.text == "Hi there"  # trimmed
    assert message.contact_name == "Ana"
    assert message.sent_at == sent_at
    assert message.has_text
    assert message.raw["id"] == "m-1", "the original fragment is kept for explaining later"


def test_every_message_in_a_batch_is_read(provider: FakeProvider) -> None:
    payload = provider.batch(
        {"id": "m-1", "from": "c-1", "text": "first"},
        {"id": "m-2", "from": "c-2", "text": "second"},
        {"id": "m-3", "from": "c-1", "text": "third"},
    )
    assert [m.provider_message_id for m in FAKE_ADAPTER.parse(payload)] == ["m-1", "m-2", "m-3"]


def test_a_delivery_with_no_message_is_not_an_error(provider: FakeProvider) -> None:
    # Read receipts and account updates arrive on the same webhook. Raising here
    # would make the provider retry something we handled correctly.
    assert FAKE_ADAPTER.parse(provider.receipt_only()) == []
    assert FAKE_ADAPTER.parse(provider.batch()) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"channel": "whatsapp", "account_id": "a", "messages": []},
        {"account_id": "a", "messages": []},
        {"channel": "fake", "messages": []},
        {"channel": "fake", "account_id": "", "messages": []},
    ],
)
def test_payloads_we_cannot_make_sense_of_are_rejected(payload: dict) -> None:
    with pytest.raises(ValueError):
        FAKE_ADAPTER.parse(payload)


def test_attachments_are_carried_across(provider: FakeProvider) -> None:
    payload = provider.inbound(
        None,
        attachments=({"kind": "image", "media_id": "media-9", "mime_type": "image/jpeg"},),
    )
    [message] = FAKE_ADAPTER.parse(payload)

    assert message.text is None
    assert message.has_text is False
    [attachment] = message.attachments
    assert attachment.kind is AttachmentKind.IMAGE
    assert attachment.provider_media_id == "media-9"
    assert attachment.mime_type == "image/jpeg"


def test_something_we_do_not_understand_is_recorded_not_dropped(provider: FakeProvider) -> None:
    # A sticker or a shared contact. The customer thinks they sent something, so
    # the turn has to exist even though we can't read it.
    payload = provider.inbound(None, attachments=({"kind": "other", "media_id": "x"},))
    [message] = FAKE_ADAPTER.parse(payload)
    assert message.attachments[0].kind is AttachmentKind.OTHER


# --- Timestamps ---------------------------------------------------------------


def test_timestamps_come_back_in_utc(provider: FakeProvider) -> None:
    berlin = timezone(timedelta(hours=2))
    payload = provider.inbound("hi", sent_at=datetime(2026, 9, 21, 11, 0, tzinfo=berlin))

    [message] = FAKE_ADAPTER.parse(payload)

    assert message.sent_at.tzinfo is UTC
    assert message.sent_at == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def test_a_time_without_an_offset_means_utc_not_this_machine(provider: FakeProvider) -> None:
    payload = provider.batch({"id": "m-1", "from": "c-1", "text": "hi",
                              "sent_at": "2026-09-21T09:00:00"})
    [message] = FAKE_ADAPTER.parse(payload)
    assert message.sent_at == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


def test_a_naive_timestamp_is_refused_by_the_model() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        InboundMessage(
            channel=Channel.FAKE,
            account_id="a",
            contact_id="c",
            provider_message_id="m",
            sent_at=datetime(2026, 9, 21, 9, 0),
            text="hi",
        )


# --- What the model refuses ---------------------------------------------------


@pytest.mark.parametrize("missing", ["account_id", "contact_id", "provider_message_id"])
def test_an_empty_identifier_is_refused(missing: str) -> None:
    fields = {
        "channel": Channel.FAKE,
        "account_id": "a",
        "contact_id": "c",
        "provider_message_id": "m",
        "sent_at": datetime.now(UTC),
        "text": "hi",
    }
    with pytest.raises(ValueError, match=missing):
        InboundMessage(**{**fields, missing: "   "})


def test_a_message_with_nothing_in_it_is_refused() -> None:
    with pytest.raises(ValueError, match="text or an attachment"):
        InboundMessage(
            channel=Channel.FAKE,
            account_id="a",
            contact_id="c",
            provider_message_id="m",
            sent_at=datetime.now(UTC),
            text="   ",
        )


def test_an_attachment_we_could_never_fetch_is_refused() -> None:
    with pytest.raises(ValueError, match="media id or a url"):
        Attachment(kind=AttachmentKind.IMAGE)
    # A location has no file to fetch, so it needs neither.
    assert Attachment(kind=AttachmentKind.LOCATION).url is None


def test_messages_cannot_be_edited_after_the_fact() -> None:
    message = InboundMessage(
        channel=Channel.FAKE,
        account_id="a",
        contact_id="c",
        provider_message_id="m",
        sent_at=datetime.now(UTC),
        text="hi",
    )
    with pytest.raises(FrozenInstanceError):
        message.text = "something else"  # type: ignore[misc]


# --- Replying -----------------------------------------------------------------


def test_a_reply_goes_back_where_it_came_from(provider: FakeProvider) -> None:
    [inbound] = FAKE_ADAPTER.parse(provider.inbound("hi", contact_id="c-7", message_id="m-7"))

    reply = OutboundMessage.reply_to(inbound, "Hello", dedupe_key="echo:m-7")

    assert reply.channel is inbound.channel
    assert reply.account_id == inbound.account_id
    assert reply.contact_id == "c-7"
    assert reply.reply_to_provider_message_id == "m-7"


def test_we_refuse_to_send_nothing() -> None:
    with pytest.raises(ValueError, match="empty message"):
        OutboundMessage(channel=Channel.FAKE, account_id="a", contact_id="c",
                        text="   ", dedupe_key="k")


def test_a_send_without_a_dedupe_key_is_refused() -> None:
    # Without it, a retried task means a second message to a real person.
    with pytest.raises(ValueError, match="dedupe_key"):
        OutboundMessage(channel=Channel.FAKE, account_id="a", contact_id="c",
                        text="Hello", dedupe_key="")


def test_dedupe_keys_are_the_same_every_time() -> None:
    assert dedupe_key_for("echo", "m-1") == "echo:m-1"
    assert dedupe_key_for("echo", "m-1") == dedupe_key_for("echo", "m-1")
    assert dedupe_key_for("echo", "m-1") != dedupe_key_for("echo", "m-2")


@pytest.mark.parametrize(("kind", "parts"), [("", ("m-1",)), ("echo", ("",)), ("echo", ("m-1", " "))])
def test_a_dedupe_key_built_from_nothing_is_refused(kind: str, parts: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        dedupe_key_for(kind, *parts)


# --- Rendering ----------------------------------------------------------------


def test_rendering_describes_the_call_without_making_it(provider: FakeProvider) -> None:
    message = OutboundMessage(channel=Channel.FAKE, account_id="acct-solar",
                              contact_id="c-1", text="Hello", dedupe_key="echo:m-1")

    request = FAKE_ADAPTER.render(message)

    assert request.method == "POST"
    assert request.path == "acct-solar/messages"
    assert request.json["to"] == "c-1"
    assert request.json["text"] == "Hello"
    assert "reply_to" not in request.json


def test_a_rendered_path_never_carries_its_own_host() -> None:
    # The base URL and pinned API version belong to the dispatcher, so an
    # adapter can't quietly send somewhere else.
    with pytest.raises(ValueError, match="relative"):
        OutboundRequest(path="https://graph.facebook.com/v25.0/x/messages", json={})


def test_the_provider_id_of_a_sent_message_is_read_back() -> None:
    assert FAKE_ADAPTER.read_send_result({"message_id": "out-1"}) == "out-1"
    with pytest.raises(ValueError):
        FAKE_ADAPTER.read_send_result({"error": "nope"})


# --- The registry -------------------------------------------------------------


def test_the_fake_channel_is_registered_like_any_other() -> None:
    assert registry.adapter_for(Channel.FAKE) is FAKE_ADAPTER
    assert registry.adapter_for("fake") is FAKE_ADAPTER
    assert Channel.FAKE in registry.registered()


@pytest.mark.parametrize("channel", ["telegram", "", "WHATSAPP ", Channel.WHATSAPP])
def test_a_channel_we_do_not_handle_says_so_clearly(channel: str | Channel) -> None:
    # Two different mistakes, one answer: a channel name this build has never
    # heard of, and a real channel whose adapter isn't built yet. Either must
    # fail loudly rather than fall through to some default adapter.
    with pytest.raises(UnknownChannel):
        AdapterRegistry().adapter_for(channel)


def test_two_adapters_cannot_claim_the_same_channel() -> None:
    class Impostor(FakeAdapter):
        pass

    own = AdapterRegistry()
    own.register(FakeAdapter())
    own.register(FakeAdapter())  # same type again: harmless re-import
    with pytest.raises(ValueError, match="already handled"):
        own.register(Impostor())


# --- The whole round trip -----------------------------------------------------


def test_hi_gets_hello_with_no_meta_account_anywhere(provider: FakeProvider) -> None:
    """The path CHN-02 to CHN-05 will run for real, proven end to end offline."""
    [inbound] = FAKE_ADAPTER.parse(provider.inbound("hi", contact_id="c-1", message_id="m-1"))

    reply = OutboundMessage.reply_to(
        inbound, "Hello 👋", dedupe_key=dedupe_key_for("echo", inbound.provider_message_id)
    )
    result = provider.deliver(FAKE_ADAPTER.render(reply))

    assert FAKE_ADAPTER.read_send_result(result) == "fake-out-1"
    assert provider.last_sent == {"to": "c-1", "text": "Hello 👋",
                                  "dedupe_key": "echo:m-1", "reply_to": "m-1"}


def test_a_redelivered_webhook_produces_the_same_reply_key(provider: FakeProvider) -> None:
    # Meta retries. Both attempts must aim at one send, which is what lets the
    # dispatcher drop the second (CHN-04).
    payload = provider.inbound("hi", message_id="m-1")
    keys = {
        dedupe_key_for("echo", FAKE_ADAPTER.parse(payload)[0].provider_message_id)
        for _ in range(2)
    }
    assert keys == {"echo:m-1"}
