"""CHN-01: the three real Meta channels, as adapters.

Translation only (hard rule 4): a webhook payload in, `InboundMessage` out; an
`OutboundMessage` in, a described request out. No I/O, no decisions, no
database. Everything here is a pure function, which is why the whole set is
tested without a Meta account.

The shapes differ more than you would expect for three products from one
company. Messenger and Instagram share the `entry[].messaging[]` envelope and
identify the business by `entry[].id`. WhatsApp wraps everything in
`entry[].changes[].value`, puts the business's identity in `metadata`, and
reports timestamps as a string of whole seconds.

Three kinds of delivery carry no customer message at all — delivery receipts,
read receipts, and our own outbound echoed back — and all three arrive on the
same webhook as real messages. Each is returned as nothing rather than an
error, because raising would make Meta retry a delivery we handled correctly.
"""

from datetime import UTC, datetime
from typing import Any

from rivon.channels.adapters import ChannelAdapter, OutboundRequest, registry
from rivon.channels.messages import (
    Attachment,
    AttachmentKind,
    Channel,
    InboundMessage,
    OutboundMessage,
)

#: Meta's attachment types, mapped onto ours. Anything absent becomes OTHER,
#: which is recorded rather than dropped: the customer believes they sent it.
_MESSENGER_KINDS = {
    "image": AttachmentKind.IMAGE,
    "audio": AttachmentKind.AUDIO,
    "video": AttachmentKind.VIDEO,
    "file": AttachmentKind.DOCUMENT,
    "location": AttachmentKind.LOCATION,
}
_WHATSAPP_KINDS = {
    "image": AttachmentKind.IMAGE,
    "audio": AttachmentKind.AUDIO,
    "voice": AttachmentKind.AUDIO,
    "video": AttachmentKind.VIDEO,
    "document": AttachmentKind.DOCUMENT,
    "sticker": AttachmentKind.OTHER,
    "location": AttachmentKind.LOCATION,
}


def _seconds(value: Any) -> datetime:
    """WhatsApp sends whole seconds as a string; Messenger sends milliseconds."""
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(UTC)


def _millis(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(UTC)


class _MessagingAdapter(ChannelAdapter):
    """Messenger and Instagram: one envelope, two products."""

    #: The value Meta puts in the payload's `object` field.
    object_name: str

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        if payload.get("object") != self.object_name:
            raise ValueError(f"not a {self.object_name} payload")

        messages: list[InboundMessage] = []
        for entry in payload.get("entry") or ():
            account_id = str(entry.get("id") or "")
            if not account_id:
                raise ValueError("webhook entry has no account id")
            for item in entry.get("messaging") or ():
                message = item.get("message")
                if not message:
                    continue  # a delivery or read receipt, or a postback
                if message.get("is_echo"):
                    continue  # our own outbound, handed back to us
                if not message.get("mid"):
                    raise ValueError("message has no id, so it cannot be deduplicated")

                attachments = tuple(
                    Attachment(
                        kind=_MESSENGER_KINDS.get(a.get("type", ""), AttachmentKind.OTHER),
                        url=(a.get("payload") or {}).get("url"),
                        provider_media_id=(a.get("payload") or {}).get("attachment_id"),
                    )
                    for a in message.get("attachments") or ()
                    # A location arrives with coordinates and no file to fetch.
                    if (a.get("payload") or {}).get("url")
                    or (a.get("payload") or {}).get("attachment_id")
                )
                text = message.get("text")
                if not text and not attachments:
                    # A sticker or share we cannot read: keep the turn.
                    attachments = (Attachment(kind=AttachmentKind.OTHER, provider_media_id=message["mid"]),)

                messages.append(
                    InboundMessage(
                        channel=self.channel,
                        account_id=account_id,
                        contact_id=str((item.get("sender") or {}).get("id") or ""),
                        provider_message_id=str(message["mid"]),
                        sent_at=_millis(item.get("timestamp")),
                        text=text,
                        attachments=attachments,
                        reply_to_provider_message_id=(message.get("reply_to") or {}).get("mid"),
                        raw=item,
                    )
                )
        return messages

    def render(self, message: OutboundMessage) -> OutboundRequest:
        return OutboundRequest(
            path=f"{message.account_id}/messages",
            json={
                "recipient": {"id": message.contact_id},
                "message": {"text": message.text},
                # RESPONSE means "answering something they sent", which is what
                # keeps us inside the 24-hour window without a tag.
                "messaging_type": "RESPONSE",
            },
        )

    def read_send_result(self, response: dict[str, Any]) -> str:
        try:
            return str(response["message_id"])
        except KeyError:
            raise ValueError(f"no message id in response: {response!r}") from None


class MessengerAdapter(_MessagingAdapter):
    channel = Channel.MESSENGER
    object_name = "page"


class InstagramAdapter(_MessagingAdapter):
    channel = Channel.INSTAGRAM
    object_name = "instagram"


class WhatsAppAdapter(ChannelAdapter):
    channel = Channel.WHATSAPP

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        if payload.get("object") != "whatsapp_business_account":
            raise ValueError("not a whatsapp_business_account payload")

        messages: list[InboundMessage] = []
        for entry in payload.get("entry") or ():
            for change in entry.get("changes") or ():
                if change.get("field") != "messages":
                    continue
                value = change.get("value") or {}
                # The business's identity lives here, not on the entry: one WABA
                # can hold several numbers, and each is a separate connection.
                account_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
                if not account_id and value.get("messages"):
                    raise ValueError("whatsapp payload has no phone_number_id")

                names = {
                    str(c.get("wa_id")): (c.get("profile") or {}).get("name")
                    for c in value.get("contacts") or ()
                }
                for item in value.get("messages") or ():
                    if not item.get("id"):
                        raise ValueError("message has no id, so it cannot be deduplicated")
                    contact_id = str(item.get("from") or "")
                    text, attachments = self._content(item)
                    context = item.get("context") or {}
                    messages.append(
                        InboundMessage(
                            channel=Channel.WHATSAPP,
                            account_id=account_id,
                            contact_id=contact_id,
                            provider_message_id=str(item["id"]),
                            sent_at=_seconds(item.get("timestamp")),
                            text=text,
                            attachments=attachments,
                            contact_name=names.get(contact_id),
                            reply_to_provider_message_id=context.get("id"),
                            raw=item,
                        )
                    )
        return messages

    @staticmethod
    def _content(item: dict[str, Any]) -> tuple[str | None, tuple[Attachment, ...]]:
        kind = item.get("type")
        if kind == "text":
            return (item.get("text") or {}).get("body"), ()
        if kind == "interactive":
            # A button or list reply: the title is what the customer sees, so it
            # is what the conversation should read back.
            interactive = item.get("interactive") or {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            return reply.get("title"), ()
        if kind == "button":
            return (item.get("button") or {}).get("text"), ()
        if kind == "location":
            return None, (Attachment(kind=AttachmentKind.LOCATION),)

        media = item.get(kind or "", {}) if isinstance(item.get(kind or ""), dict) else {}
        attachment = Attachment(
            kind=_WHATSAPP_KINDS.get(kind or "", AttachmentKind.OTHER),
            provider_media_id=media.get("id") or item["id"],
            mime_type=media.get("mime_type"),
            filename=media.get("filename"),
        )
        # Images and documents can carry a caption, which is often the whole
        # question: "how much for this roof?".
        return media.get("caption"), (attachment,)

    def render(self, message: OutboundMessage) -> OutboundRequest:
        return OutboundRequest(
            path=f"{message.account_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": message.contact_id,
                "type": "text",
                "text": {"preview_url": False, "body": message.text},
            },
        )

    def read_send_result(self, response: dict[str, Any]) -> str:
        try:
            return str(response["messages"][0]["id"])
        except (KeyError, IndexError, TypeError):
            raise ValueError(f"no message id in response: {response!r}") from None


MESSENGER_ADAPTER = registry.register(MessengerAdapter())
INSTAGRAM_ADAPTER = registry.register(InstagramAdapter())
WHATSAPP_ADAPTER = registry.register(WhatsAppAdapter())
