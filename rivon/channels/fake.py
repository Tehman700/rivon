"""CHN-01: a channel that behaves like the real ones and needs no Meta account.

Hard rule 4 says the system must be fully testable and runnable with no live
WhatsApp connection. This is how. The fake channel implements the same adapter
contract as the real ones, so inbound parsing, routing, deduplication, the
dispatcher and the reply worker all run against it end to end — in tests, in CI,
and in a demo on a laptop with no internet.

Its payload deliberately mirrors the shape of a real one: a batch of messages
under one business account, possibly mixed with deliveries that carry no
message at all. Code that only ever saw one tidy message at a time would fall
over the first time Meta sent two.

`FakeProvider` stands in for the platform itself: it records what was "sent"
and builds inbound payloads to feed back in.
"""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, field
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


class FakeAdapter(ChannelAdapter):
    channel = Channel.FAKE

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        if payload.get("channel") != Channel.FAKE:
            raise ValueError("not a fake-channel payload")
        account_id = payload.get("account_id")
        if not account_id:
            raise ValueError("payload has no account_id")

        messages = []
        for item in payload.get("messages", ()):
            attachments = tuple(
                Attachment(
                    kind=AttachmentKind(a.get("kind", AttachmentKind.OTHER)),
                    provider_media_id=a.get("media_id"),
                    url=a.get("url"),
                    mime_type=a.get("mime_type"),
                    filename=a.get("filename"),
                )
                for a in item.get("attachments", ())
            )
            messages.append(
                InboundMessage(
                    channel=Channel.FAKE,
                    account_id=account_id,
                    contact_id=item["from"],
                    provider_message_id=item["id"],
                    sent_at=_parse_time(item.get("sent_at")),
                    text=item.get("text"),
                    attachments=attachments,
                    contact_name=item.get("name"),
                    reply_to_provider_message_id=item.get("reply_to"),
                    raw=item,
                )
            )
        return messages

    def render(self, message: OutboundMessage) -> OutboundRequest:
        body: dict[str, Any] = {
            "to": message.contact_id,
            "text": message.text,
            "dedupe_key": message.dedupe_key,
        }
        if message.reply_to_provider_message_id:
            body["reply_to"] = message.reply_to_provider_message_id
        return OutboundRequest(path=f"{message.account_id}/messages", json=body)

    def read_send_result(self, response: dict[str, Any]) -> str:
        try:
            return response["message_id"]
        except KeyError as exc:
            raise ValueError(f"no message id in response: {response!r}") from exc


def _parse_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    # A caller that leaves the offset off means UTC here, rather than local time,
    # which would make a test's result depend on the machine running it.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass
class FakeProvider:
    """The platform, in memory: builds inbound payloads, records outbound sends."""

    account_id: str = "fake-account"
    sent: list[dict[str, Any]] = field(default_factory=list)
    _ids: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def inbound(
        self,
        text: str | None = "hi",
        *,
        contact_id: str = "fake-contact",
        message_id: str | None = None,
        name: str | None = None,
        sent_at: datetime | None = None,
        attachments: tuple[dict[str, Any], ...] = (),
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """One message, in the shape a webhook would deliver it."""
        return self.batch(
            {
                "id": message_id or f"fake-msg-{next(self._ids)}",
                "from": contact_id,
                "text": text,
                "name": name,
                "sent_at": (sent_at or datetime.now(UTC)).isoformat(),
                "attachments": list(attachments),
                "reply_to": reply_to,
            }
        )

    def batch(self, *messages: dict[str, Any], **extra: Any) -> dict[str, Any]:
        """Several messages in one delivery, as the real platforms do."""
        return {
            "channel": Channel.FAKE.value,
            "account_id": self.account_id,
            "messages": list(messages),
            **extra,
        }

    def receipt_only(self) -> dict[str, Any]:
        """A delivery carrying no customer message — a read receipt, say."""
        return {
            "channel": Channel.FAKE.value,
            "account_id": self.account_id,
            "statuses": [{"id": "fake-msg-1", "status": "read"}],
        }

    def deliver(self, request: OutboundRequest) -> dict[str, Any]:
        """Accept a rendered send, as the provider's API would."""
        self.sent.append(request.json)
        return {"message_id": f"fake-out-{len(self.sent)}"}

    @property
    def last_sent(self) -> dict[str, Any] | None:
        return self.sent[-1] if self.sent else None


FAKE_ADAPTER = registry.register(FakeAdapter())
