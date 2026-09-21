"""CHN-02/03/04: the three URLs Meta calls, and what happens behind them.

These endpoints are the only unauthenticated ones in the service, and the only
place a stranger can reach. So the signature check gets tested hardest: not
only that a good signature passes, but that a body altered after signing, a
different secret, and a re-serialised copy of the same JSON all fail.

After that, the two failures that would reach a real customer: a retried
delivery answered twice, and a message surfacing for the wrong business.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.channels import inbound, service
from rivon.channels.messages import Channel
from rivon.channels.models import ReceivedMessage
from rivon.channels.providers import (
    INSTAGRAM_ADAPTER,
    MESSENGER_ADAPTER,
    WHATSAPP_ADAPTER,
)
from rivon.channels.service import ConnectionInput
from rivon.events.models import OutboxEvent
from rivon.platform.tenancy import tenant_transaction
from tests.conftest import TenantUsers

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def messenger_payload(page_id: str, *, mid: str = "m-1", text: str | None = "hi",
                      sender: str = "psid-1", **extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {"mid": mid}
    if text is not None:
        message["text"] = text
    message.update(extra)
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1758000000000,
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": page_id},
                        "timestamp": 1758000000000,
                        "message": message,
                    }
                ],
            }
        ],
    }


def whatsapp_payload(phone_number_id: str, *, wamid: str = "wamid.1",
                     body: str = "hi", frm: str = "4915112345678") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "4930123456",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Ana"}, "wa_id": frm}],
                            "messages": [
                                {
                                    "from": frm,
                                    "id": wamid,
                                    "timestamp": "1758000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# --- The signature ------------------------------------------------------------


def test_a_correctly_signed_body_is_accepted() -> None:
    body = b'{"object":"page"}'
    assert inbound.signature_is_valid(body, sign(body), APP_SECRET)


@pytest.mark.parametrize(
    "header",
    [None, "", "deadbeef", "sha1=abc", "sha256=", "sha256=not-hex"],
)
def test_a_missing_or_malformed_signature_is_refused(header: str | None) -> None:
    assert not inbound.signature_is_valid(b'{"object":"page"}', header, APP_SECRET)


def test_someone_elses_secret_does_not_pass() -> None:
    body = b'{"object":"page"}'
    assert not inbound.signature_is_valid(body, sign(body, "a-different-secret"), APP_SECRET)


def test_a_body_altered_after_signing_is_refused() -> None:
    body = b'{"object":"page","entry":[]}'
    header = sign(body)
    assert not inbound.signature_is_valid(body.replace(b"[]", b'[{"id":"x"}]'), header, APP_SECRET)


def test_the_signature_is_over_the_bytes_received_not_the_parsed_json() -> None:
    """Why the endpoint reads request.body() before parsing.

    Re-serialising changes whitespace and key order, so a signature computed
    over the original no longer matches — which is exactly how a real
    deployment breaks if someone moves the check after the parse.
    """
    original = b'{"object": "page",  "entry": []}'
    header = sign(original)
    reserialised = json.dumps(json.loads(original)).encode()

    assert inbound.signature_is_valid(original, header, APP_SECRET)
    assert not inbound.signature_is_valid(reserialised, header, APP_SECRET)


# --- The subscription check ---------------------------------------------------


async def test_meta_can_verify_the_webhook_url(client: AsyncClient) -> None:
    response = await client.get(
        "/webhooks/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "1158201444"},
    )
    assert response.status_code == 200
    assert response.text == "1158201444"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
        {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "x"},
        {"hub.challenge": "x"},
        {},
    ],
)
async def test_the_url_is_not_confirmed_to_anyone_else(
    client: AsyncClient, params: dict[str, str]
) -> None:
    assert (await client.get("/webhooks/messenger", params=params)).status_code == 403


async def test_only_the_three_real_channels_have_webhooks(client: AsyncClient) -> None:
    assert (await client.get("/webhooks/fake")).status_code == 404
    assert (await client.post("/webhooks/telegram", content=b"{}")).status_code == 404


# --- Parsing, per platform ----------------------------------------------------


def test_a_messenger_message_is_read_correctly() -> None:
    [message] = MESSENGER_ADAPTER.parse(messenger_payload("page-9"))

    assert message.channel is Channel.MESSENGER
    assert message.account_id == "page-9"  # the routing key
    assert message.contact_id == "psid-1"
    assert message.provider_message_id == "m-1"
    assert message.text == "hi"
    # Milliseconds. Read as seconds this would land in the year 57726.
    assert message.sent_at == datetime(2025, 9, 16, 5, 20, tzinfo=UTC)


def test_our_own_reply_coming_back_is_not_treated_as_a_customer_message() -> None:
    # Meta echoes outbound messages to the same webhook. Without this the
    # assistant would answer itself, forever.
    payload = messenger_payload("page-9", is_echo=True, app_id=1234)
    assert MESSENGER_ADAPTER.parse(payload) == []


def test_receipts_and_postbacks_carry_no_message() -> None:
    delivery = {
        "object": "page",
        "entry": [{"id": "page-9", "messaging": [{"sender": {"id": "psid-1"},
                                                  "delivery": {"mids": ["m-1"], "watermark": 1}}]}],
    }
    assert MESSENGER_ADAPTER.parse(delivery) == []
    assert MESSENGER_ADAPTER.parse({"object": "page", "entry": []}) == []


def test_a_sticker_still_counts_as_a_turn() -> None:
    # The customer believes they sent something; a conversation missing it
    # reads as though we ignored them.
    payload = messenger_payload("page-9", text=None)
    [message] = MESSENGER_ADAPTER.parse(payload)
    assert message.text is None
    assert message.attachments[0].kind.value == "other"


def test_an_instagram_message_uses_the_same_shape() -> None:
    payload = messenger_payload("ig-9")
    payload["object"] = "instagram"
    [message] = INSTAGRAM_ADAPTER.parse(payload)
    assert message.channel is Channel.INSTAGRAM
    assert message.account_id == "ig-9"


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (MESSENGER_ADAPTER, {"object": "instagram", "entry": []}),
        (INSTAGRAM_ADAPTER, {"object": "page", "entry": []}),
        (WHATSAPP_ADAPTER, {"object": "page", "entry": []}),
        (MESSENGER_ADAPTER, {"entry": []}),
    ],
)
def test_a_payload_from_the_wrong_platform_is_refused(adapter, payload: dict) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        adapter.parse(payload)


def test_a_message_without_an_id_is_refused() -> None:
    # Without it there is no way to recognise a retry, which is the one thing
    # standing between Meta's retries and a second reply.
    payload = messenger_payload("page-9")
    del payload["entry"][0]["messaging"][0]["message"]["mid"]
    with pytest.raises(ValueError, match="deduplicated"):
        MESSENGER_ADAPTER.parse(payload)


def test_a_whatsapp_message_is_read_correctly() -> None:
    [message] = WHATSAPP_ADAPTER.parse(whatsapp_payload("pn-7"))

    assert message.channel is Channel.WHATSAPP
    assert message.account_id == "pn-7", "the phone number id, not the WABA id"
    assert message.contact_id == "4915112345678"
    assert message.contact_name == "Ana", "taken from the contacts block"
    assert message.text == "hi"
    # Whole seconds, as a string. The same instant as the Messenger fixture.
    assert message.sent_at == datetime(2025, 9, 16, 5, 20, tzinfo=UTC)


def test_a_whatsapp_photo_keeps_its_caption() -> None:
    # "how much for this roof?" attached to a picture of the roof.
    payload = whatsapp_payload("pn-7")
    payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
        "from": "4915112345678", "id": "wamid.2", "timestamp": "1758000000", "type": "image",
        "image": {"id": "media-3", "mime_type": "image/jpeg", "caption": "how much for this roof?"},
    }
    [message] = WHATSAPP_ADAPTER.parse(payload)
    assert message.text == "how much for this roof?"
    assert message.attachments[0].provider_media_id == "media-3"


def test_a_whatsapp_button_reply_reads_as_what_the_customer_saw() -> None:
    payload = whatsapp_payload("pn-7")
    payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
        "from": "4915112345678", "id": "wamid.3", "timestamp": "1758000000", "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "yes", "title": "Yes, I own it"}},
    }
    [message] = WHATSAPP_ADAPTER.parse(payload)
    assert message.text == "Yes, I own it"


def test_whatsapp_delivery_statuses_are_not_messages() -> None:
    payload = whatsapp_payload("pn-7")
    payload["entry"][0]["changes"][0]["value"] = {
        "metadata": {"phone_number_id": "pn-7"},
        "statuses": [{"id": "wamid.1", "status": "read", "timestamp": "1758000001"}],
    }
    assert WHATSAPP_ADAPTER.parse(payload) == []


def test_an_account_update_is_not_a_message() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba-1", "changes": [{"field": "account_update",
                                                "value": {"event": "PARTNER_ADDED"}}]}],
    }
    assert WHATSAPP_ADAPTER.parse(payload) == []


def test_only_the_messages_field_is_read() -> None:
    # Meta adds webhook fields over time, and some carry values shaped like
    # ones we already handle. Reading anything we did not subscribe to would
    # turn an unrelated notification into a customer message.
    payload = whatsapp_payload("pn-7")
    payload["entry"][0]["changes"][0]["field"] = "message_template_status_update"
    assert WHATSAPP_ADAPTER.parse(payload) == []


# --- Rendering a reply --------------------------------------------------------


def test_replies_are_addressed_the_way_each_platform_expects() -> None:
    from rivon.channels.messages import OutboundMessage

    message = OutboundMessage(channel=Channel.WHATSAPP, account_id="pn-7",
                              contact_id="4915112345678", text="Hello", dedupe_key="k")
    request = WHATSAPP_ADAPTER.render(message)
    assert request.path == "pn-7/messages"
    assert request.json["messaging_product"] == "whatsapp"
    assert request.json["text"]["body"] == "Hello"

    message = OutboundMessage(channel=Channel.MESSENGER, account_id="page-9",
                              contact_id="psid-1", text="Hello", dedupe_key="k")
    request = MESSENGER_ADAPTER.render(message)
    assert request.json["recipient"] == {"id": "psid-1"}
    assert request.json["messaging_type"] == "RESPONSE", (
        "what keeps a reply inside the 24-hour window without a message tag"
    )


def test_the_provider_id_of_a_sent_message_is_read_back() -> None:
    assert WHATSAPP_ADAPTER.read_send_result({"messages": [{"id": "wamid.out"}]}) == "wamid.out"
    assert MESSENGER_ADAPTER.read_send_result({"message_id": "m-out"}) == "m-out"
    for adapter, bad in ((WHATSAPP_ADAPTER, {"messages": []}), (MESSENGER_ADAPTER, {})):
        with pytest.raises(ValueError):
            adapter.read_send_result(bad)


# --- End to end, through HTTP -------------------------------------------------


@pytest.fixture
async def connected(
    app_sessionmaker: async_sessionmaker[AsyncSession], tenant: TenantUsers
) -> str:
    """A Page this tenant has connected, ready to receive."""
    page_id = f"page-{uuid.uuid4().hex[:8]}"
    async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
        await service.connect(
            session,
            tenant.tenant_id,
            ConnectionInput(
                provider=Channel.MESSENGER, external_id=page_id,
                access_token="PAGE-TOKEN", display_name="Berlin Solar",
            ),
        )
    return page_id


async def post_webhook(client: AsyncClient, name: str, payload: dict, *, secret: str = APP_SECRET):  # type: ignore[no-untyped-def]
    body = json.dumps(payload).encode()
    return await client.post(
        f"/webhooks/{name}", content=body,
        headers={"X-Hub-Signature-256": sign(body, secret), "content-type": "application/json"},
    )


async def stored_messages(
    app_sessionmaker: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> list[ReceivedMessage]:
    async with tenant_transaction(app_sessionmaker, tenant_id) as session:
        result = await session.execute(
            select(ReceivedMessage).where(ReceivedMessage.tenant_id == tenant_id)
        )
        return list(result.scalars())


async def event_count(
    app_sessionmaker: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> int:
    async with tenant_transaction(app_sessionmaker, tenant_id) as session:
        return await session.scalar(
            select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == inbound.MESSAGE_RECEIVED,
            )
        ) or 0


async def test_a_signed_message_is_stored_and_enqueued(
    client: AsyncClient, tenant: TenantUsers, connected: str,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    response = await post_webhook(client, "messenger", messenger_payload(connected, mid="m-100"))
    assert response.status_code == 200

    [message] = await stored_messages(app_sessionmaker, tenant.tenant_id)
    assert message.provider_message_id == "m-100"
    assert message.text == "hi"
    assert message.account_id == connected
    assert message.raw, "the provider's own fragment is kept"
    assert await event_count(app_sessionmaker, tenant.tenant_id) == 1


async def test_an_unsigned_webhook_never_reaches_the_database(
    client: AsyncClient, tenant: TenantUsers, connected: str,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    body = json.dumps(messenger_payload(connected)).encode()
    assert (await client.post("/webhooks/messenger", content=body)).status_code == 403
    response = await post_webhook(client, "messenger", messenger_payload(connected),
                                  secret="not-our-secret")
    assert response.status_code == 403
    assert await stored_messages(app_sessionmaker, tenant.tenant_id) == []


async def test_a_retried_delivery_is_stored_and_enqueued_once(
    client: AsyncClient, tenant: TenantUsers, connected: str,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Meta retries. Twice through must not mean two replies to a customer."""
    payload = messenger_payload(connected, mid="m-repeat")
    for _ in range(3):
        assert (await post_webhook(client, "messenger", payload)).status_code == 200

    assert len(await stored_messages(app_sessionmaker, tenant.tenant_id)) == 1
    assert await event_count(app_sessionmaker, tenant.tenant_id) == 1


async def test_two_different_messages_both_arrive(
    client: AsyncClient, tenant: TenantUsers, connected: str,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await post_webhook(client, "messenger", messenger_payload(connected, mid="m-1", text="hi"))
    await post_webhook(client, "messenger", messenger_payload(connected, mid="m-2", text="hello"))
    stored = await stored_messages(app_sessionmaker, tenant.tenant_id)
    assert {m.text for m in stored} == {"hi", "hello"}


async def test_a_message_for_an_account_nobody_connected_is_acknowledged_and_dropped(
    client: AsyncClient, tenant: TenantUsers,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Meta keeps delivering for a while after a customer removes us. Anything
    # other than 200 makes it retry for hours.
    response = await post_webhook(client, "messenger", messenger_payload("page-nobody-owns"))
    assert response.status_code == 200
    assert await stored_messages(app_sessionmaker, tenant.tenant_id) == []


async def test_a_disconnected_account_stops_receiving(
    client: AsyncClient, tenant: TenantUsers, connected: str,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
        [connection] = await service.list_connections(session, tenant.tenant_id)
        await service.disconnect(session, tenant.tenant_id, connection.id)

    assert (await post_webhook(client, "messenger", messenger_payload(connected))).status_code == 200
    assert await stored_messages(app_sessionmaker, tenant.tenant_id) == []


async def test_a_message_only_ever_reaches_the_business_it_was_sent_to(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers, connected: str,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await post_webhook(client, "messenger", messenger_payload(connected, mid="m-private"))

    mine = await stored_messages(app_sessionmaker, tenant.tenant_id)
    theirs = await stored_messages(app_sessionmaker, other_tenant.tenant_id)
    assert [m.provider_message_id for m in mine] == ["m-private"]
    assert theirs == []


async def test_a_body_we_cannot_read_is_still_acknowledged(
    client: AsyncClient, tenant: TenantUsers, connected: str
) -> None:
    for body in (b"not json at all", b"[]", b'{"object":"page","entry":[{"messaging":[]}]}'):
        response = await client.post(
            "/webhooks/messenger", content=body,
            headers={"X-Hub-Signature-256": sign(body), "content-type": "application/json"},
        )
        assert response.status_code == 200, body


async def test_a_whatsapp_message_arrives_on_its_own_webhook(
    client: AsyncClient, tenant: TenantUsers,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    number_id = f"pn-{uuid.uuid4().hex[:8]}"
    async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
        await service.connect(
            session, tenant.tenant_id,
            ConnectionInput(provider=Channel.WHATSAPP, external_id=number_id,
                            access_token="WABA-TOKEN", parent_external_id="waba-1"),
        )

    response = await post_webhook(client, "whatsapp", whatsapp_payload(number_id, wamid="wamid.9"))
    assert response.status_code == 200

    [message] = await stored_messages(app_sessionmaker, tenant.tenant_id)
    assert message.channel is Channel.WHATSAPP
    assert message.provider_message_id == "wamid.9"
    assert message.contact_name == "Ana"
