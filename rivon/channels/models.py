"""CHN-07: which messaging accounts a business has connected, and the tokens for them.

One row per connected account: a Facebook Page, an Instagram account, a WhatsApp
phone number. `external_id` is the platform's ID for it, and it is what an
inbound webhook has to turn into a tenant.

**`external_id` is unique across the whole table, not per tenant.** Hard rule 2
says every index leads with `tenant_id`; this one cannot, because at lookup time
the tenant is precisely what we are trying to find. The exception is deliberate
and it is also a safeguard: without global uniqueness two businesses could claim
the same Page, and one of them would start receiving the other's customers.
Every other query on this table still leads with `tenant_id`, and RLS stays on.

The lookup itself goes through the `channel_route` SQL function (migration
0010), which is the only thing in the system allowed to read across tenants —
and all it ever returns is one UUID.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from rivon.channels.messages import Channel
from rivon.db import Base, BaseMixin, TenantScopedMixin


def _string_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Stored as text with a check constraint, so values stay readable in psql."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )


class ConnectionStatus(StrEnum):
    ACTIVE = "active"
    #: The token stopped working, or the customer removed us at Meta's end. We
    #: keep the row so the dashboard can say so instead of failing silently.
    NEEDS_REAUTH = "needs_reauth"
    #: Disconnected from our side. Kept for the audit trail.
    REVOKED = "revoked"


class ChannelConnection(BaseMixin, TenantScopedMixin, Base):
    __tablename__ = "channel_connections"

    provider: Mapped[Channel] = mapped_column(_string_enum(Channel, "channel_provider"))
    #: Page ID, Instagram account ID, or WhatsApp phone number ID. The routing key.
    external_id: Mapped[str] = mapped_column(String(64))
    #: The WABA a number belongs to, or the Page an Instagram account hangs off.
    parent_external_id: Mapped[str | None] = mapped_column(String(64), default=None)
    #: What the customer sees in the dashboard — their Page or account name.
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)

    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    token_type: Mapped[str] = mapped_column(String(32), default="business_system_user")
    #: Null for tokens Meta issues without an expiry, which is the normal case
    #: on the Page route.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: What the customer actually granted. Compared against what we need, so a
    #: downgrade is caught at connect time rather than as a 403 days later.
    granted_scopes: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)

    status: Mapped[ConnectionStatus] = mapped_column(
        _string_enum(ConnectionStatus, "channel_connection_status"),
        default=ConnectionStatus.ACTIVE,
    )
    #: Why it is not active, in words a support person can use.
    status_detail: Mapped[str | None] = mapped_column(String(200), default=None)

    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    #: Anything the provider returned that we may need later without a refetch.
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            # The exception to hard rule 2, argued in this module's docstring.
            UniqueConstraint("provider", "external_id", name="uq_channel_connections_provider_external_id"),
            Index("ix_channel_connections_tenant_id_provider", "tenant_id", "provider"),
            CheckConstraint("length(external_id) > 0", name="ck_channel_connections_external_id_present"),
            CheckConstraint(
                "octet_length(access_token_encrypted) > 0",
                name="ck_channel_connections_token_present",
            ),
        )

    @property
    def is_usable(self) -> bool:
        return self.status is ConnectionStatus.ACTIVE


class ChannelOAuthState(BaseMixin, TenantScopedMixin, Base):
    """The `state` value handed to Meta when a connect flow starts.

    It is what ties the callback back to the tenant and user who began it, and
    what stops someone else's callback being replayed into this account. In
    Postgres rather than Redis because it is flow state, not a cache
    (hard rule 6), and because a single-use record has to be reliably
    single-use.
    """

    __tablename__ = "channel_oauth_states"

    state: Mapped[str] = mapped_column(String(64))
    provider: Mapped[Channel] = mapped_column(_string_enum(Channel, "channel_provider"))
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Set the moment it is redeemed. A second callback with the same state is
    #: refused rather than processed twice.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint("state", name="uq_channel_oauth_states_state"),
            Index("ix_channel_oauth_states_expires_at", "expires_at"),
        )


class ReceivedMessage(BaseMixin, TenantScopedMixin, Base):
    """CHN-02/04: a customer message, exactly as it arrived.

    Written by the webhook before any work is done on it, so a message is never
    lost to a crash further down. `provider_message_id` is unique per tenant:
    Meta retries anything it thinks we mishandled, and that constraint is what
    turns a retry into a no-op instead of a second reply to a real person.

    `raw` keeps the provider's own fragment, so a conversation can be explained
    later, or re-read after a parsing bug is fixed, without asking Meta again.
    """

    __tablename__ = "inbound_messages"

    channel: Mapped[Channel] = mapped_column(_string_enum(Channel, "channel_provider"))
    #: The business account it arrived at. Kept alongside tenant_id because one
    #: business can connect several numbers or Pages.
    account_id: Mapped[str] = mapped_column(String(64))
    contact_id: Mapped[str] = mapped_column(String(128))
    contact_name: Mapped[str | None] = mapped_column(String(120), default=None)
    provider_message_id: Mapped[str] = mapped_column(String(128))
    text: Mapped[str | None] = mapped_column(Text, default=None)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    reply_to_provider_message_id: Mapped[str | None] = mapped_column(String(128), default=None)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint(
                "tenant_id", "provider_message_id",
                name="uq_inbound_messages_tenant_id_provider_message_id",
            ),
            Index("ix_inbound_messages_tenant_id_account_id", "tenant_id", "account_id"),
        )
