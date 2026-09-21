"""Channel adapters and the internal message model (CHN-01).

Downstream modules import from here and never from a provider's payload shape.
"""

from rivon.channels.adapters import (
    AdapterRegistry,
    ChannelAdapter,
    OutboundRequest,
    UnknownChannel,
    registry,
)
from rivon.channels.messages import (
    Attachment,
    AttachmentKind,
    Channel,
    InboundMessage,
    OutboundMessage,
    dedupe_key_for,
)

__all__ = [
    "AdapterRegistry",
    "Attachment",
    "AttachmentKind",
    "Channel",
    "ChannelAdapter",
    "InboundMessage",
    "OutboundMessage",
    "OutboundRequest",
    "UnknownChannel",
    "dedupe_key_for",
    "registry",
]
