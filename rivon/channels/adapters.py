"""CHN-01: the contract every channel implements.

Adapters are thin by rule (hard rule 4): they translate a provider payload into
`InboundMessage`, and an `OutboundMessage` into the request that sends it. They
hold no business logic, make no decisions, and — deliberately — perform no I/O.

`render()` returns a *description* of an HTTP call rather than making one. That
keeps every adapter a pure function, so the whole translation layer is tested
without a network, a token, or a live WhatsApp connection. The dispatcher
(CHN-05) owns the transport, the credentials and the retries.

Signature verification lives in the webhook layer, not here: all three Meta
channels share one app secret and one scheme, so duplicating it per adapter
would be three chances to get it wrong.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from rivon.channels.messages import Channel, InboundMessage, OutboundMessage


@dataclass(frozen=True, slots=True)
class OutboundRequest:
    """What to send, and where — but not with whose credentials.

    `path` is relative to the provider's API root. The dispatcher prepends the
    base URL and pinned API version, and adds the access token, so neither is
    baked into a translation.
    """

    path: str
    json: dict[str, Any]
    method: str = "POST"

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith(("http://", "https://")):
            raise ValueError("path must be relative to the provider's API root")


class UnknownChannel(LookupError):
    """No adapter is registered for that channel."""


class ChannelAdapter(ABC):
    """Translate one platform's payloads to and from the internal model."""

    channel: ClassVar[Channel]

    @abstractmethod
    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        """Pull every customer message out of one webhook delivery.

        Returns an empty list — never an error — for deliveries that carry no
        customer message. Providers send plenty of those: delivery receipts,
        read receipts, account updates. Treating them as failures would make the
        webhook retry something that was handled correctly.

        Anything malformed enough that we cannot be sure what it means raises
        `ValueError`, so it is recorded and inspected rather than dropped.
        """

    @abstractmethod
    def render(self, message: OutboundMessage) -> OutboundRequest:
        """Describe the call that delivers `message`."""

    @abstractmethod
    def read_send_result(self, response: dict[str, Any]) -> str:
        """Pull the provider's ID for the message we just sent.

        Stored against the outbound record, so a later delivery or read receipt
        can be matched back to it.
        """


@dataclass
class AdapterRegistry:
    """Which adapter handles which channel.

    A registry rather than a dictionary literal so tests can register the fake
    channel without the production code importing test code.
    """

    _adapters: dict[Channel, ChannelAdapter] = field(default_factory=dict)

    def register(self, adapter: ChannelAdapter) -> ChannelAdapter:
        channel = adapter.channel
        existing = self._adapters.get(channel)
        if existing is not None and type(existing) is not type(adapter):
            raise ValueError(f"{channel} is already handled by {type(existing).__name__}")
        self._adapters[channel] = adapter
        return adapter

    def adapter_for(self, channel: Channel | str) -> ChannelAdapter:
        try:
            key = Channel(channel)
        except ValueError as exc:  # a channel name from the database we don't know
            raise UnknownChannel(str(channel)) from exc
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise UnknownChannel(key) from exc

    def registered(self) -> frozenset[Channel]:
        return frozenset(self._adapters)


#: The registry the application uses. Adapters register themselves on import.
registry = AdapterRegistry()
