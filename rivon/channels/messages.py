"""CHN-01: one message shape, whatever platform it came from.

Everything downstream — conversations, leads, quotations — reads this model and
never a provider payload. That is what lets the same conversation code serve
WhatsApp, Messenger, Instagram and the fake channel without knowing which it is.

Two identifiers carry the weight:

`account_id` is the business's account on that platform — a Page ID, an
Instagram account ID, a WhatsApp phone number ID. It is how an inbound webhook
finds the tenant it belongs to, because the webhook itself is app-wide and says
nothing about who we are.

`provider_message_id` is the platform's own ID for the message. Meta retries a
webhook it thinks we mishandled, so the same message arrives more than once;
storing this under a unique constraint is what stops a customer getting two
replies (hard rule 7).

The original payload travels along in `raw` so a message can always be
explained, or re-parsed after a bug is fixed, without going back to Meta.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Channel(StrEnum):
    """Platforms a message can arrive on. Stored as-is in the database."""

    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    INSTAGRAM = "instagram"
    #: Not a real platform. Drives the whole pipeline in tests and demos with no
    #: Meta account at all (hard rule 4), so it is a first-class value, not a mock.
    FAKE = "fake"


class AttachmentKind(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    #: Something arrived that we can't interpret — a sticker, a contact card, a
    #: share. Recorded rather than dropped, so a conversation isn't silently
    #: missing a turn the customer thinks they sent.
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file or place attached to a message.

    Media is referenced, never inlined: providers hand us a short-lived ID or
    URL, and fetching it is a later, separate job.
    """

    kind: AttachmentKind
    provider_media_id: str | None = None
    url: str | None = None
    mime_type: str | None = None
    filename: str | None = None

    def __post_init__(self) -> None:
        if self.kind is not AttachmentKind.LOCATION and not (self.provider_media_id or self.url):
            raise ValueError(f"{self.kind} attachment needs a media id or a url")


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """Something a customer sent to a business."""

    channel: Channel
    #: The business's account on the platform. The routing key: account -> tenant.
    account_id: str
    #: The customer, as the platform identifies them. Scoped to `account_id`:
    #: the same person messaging two businesses is two different contact IDs.
    contact_id: str
    #: The platform's message ID. Unique per tenant; the idempotency key.
    provider_message_id: str
    sent_at: datetime
    text: str | None = None
    attachments: tuple[Attachment, ...] = ()
    #: Display name, where the platform gives one. Often absent on WhatsApp.
    contact_name: str | None = None
    #: Set when the customer replied to a specific earlier message.
    reply_to_provider_message_id: str | None = None
    #: The provider fragment this was parsed from, kept verbatim.
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("account_id", "contact_id", "provider_message_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.sent_at.tzinfo is None:
            raise ValueError("sent_at must be timezone-aware")
        # Compare in UTC so a message stamped in another offset isn't wrongly
        # rejected, and normalise it while we are here.
        object.__setattr__(self, "sent_at", self.sent_at.astimezone(UTC))
        if self.text is not None:
            object.__setattr__(self, "text", self.text.strip() or None)
        if self.text is None and not self.attachments:
            raise ValueError("a message must carry text or an attachment")

    @property
    def has_text(self) -> bool:
        return bool(self.text)


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """Something a business is sending to a customer.

    `dedupe_key` is set by whoever asks for the send and is what makes retrying
    safe: the dispatcher sends a given key at most once, so a redelivered event
    or a retried task can never produce a second message to a real person.
    """

    channel: Channel
    account_id: str
    contact_id: str
    text: str
    dedupe_key: str
    #: The message being answered, where the platform supports threading.
    reply_to_provider_message_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("account_id", "contact_id", "dedupe_key"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        object.__setattr__(self, "text", self.text.strip())
        if not self.text:
            raise ValueError("refusing to send an empty message")

    @classmethod
    def reply_to(cls, inbound: InboundMessage, text: str, *, dedupe_key: str) -> "OutboundMessage":
        """Answer `inbound` on the channel it arrived on."""
        return cls(
            channel=inbound.channel,
            account_id=inbound.account_id,
            contact_id=inbound.contact_id,
            text=text,
            dedupe_key=dedupe_key,
            reply_to_provider_message_id=inbound.provider_message_id,
        )


def dedupe_key_for(kind: str, *parts: str | uuid.UUID) -> str:
    """Build an outbound dedupe key, e.g. `echo:<message id>`.

    Deterministic on purpose: the same cause must produce the same key however
    many times it is retried.
    """
    if not kind or any(not str(part).strip() for part in parts):
        raise ValueError("a dedupe key needs a kind and non-empty parts")
    return ":".join([kind, *(str(part) for part in parts)])
