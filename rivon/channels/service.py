"""CHN-07/CHN-13: connecting, disconnecting and looking up messaging accounts.

The channels module's interface. Nothing outside it touches these tables.

Every function here except `route_to_tenant` runs inside a tenant transaction
and filters by `tenant_id` as well as relying on RLS. `route_to_tenant` is the
deliberate exception: it is the webhook's first step, before any tenant is
known, and it goes through the `channel_route` SQL function so that the only
thing crossing a tenant boundary is a single UUID.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels.crypto import TokenCipher, TokenUnreadable
from rivon.channels.messages import Channel
from rivon.channels.models import ChannelConnection, ChannelOAuthState, ConnectionStatus
from rivon.config import get_settings

#: How long a customer has to finish the Meta dialog before the state expires.
OAUTH_STATE_TTL = timedelta(minutes=15)


class ConnectionNotFound(Exception):
    """No such connection for this tenant."""


class AlreadyConnectedElsewhere(Exception):
    """Another business has already connected this account.

    Says nothing about which business — that would leak one customer's
    arrangements to another. Support can look it up; the API cannot.
    """


class OAuthStateInvalid(Exception):
    """The callback's state is unknown, expired, or has already been used."""


@lru_cache
def get_token_cipher() -> TokenCipher:
    key = get_settings().channel_token_key
    if key is None:
        raise RuntimeError(
            "RIVON_CHANNEL_TOKEN_KEY is not set, so channel credentials cannot be "
            "stored or read. Generate one with TokenCipher.generate_key()."
        )
    return TokenCipher(key.get_secret_value())


@dataclass(frozen=True, slots=True)
class ConnectionInput:
    """What a completed OAuth flow gives us about one account."""

    provider: Channel
    external_id: str
    access_token: str
    parent_external_id: str | None = None
    display_name: str | None = None
    token_type: str = "business_system_user"
    expires_at: datetime | None = None
    granted_scopes: tuple[str, ...] = ()
    provider_metadata: dict | None = None


async def connect(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    details: ConnectionInput,
    *,
    connected_by_user_id: uuid.UUID | None = None,
    cipher: TokenCipher | None = None,
) -> ChannelConnection:
    """Record a connected account, or refresh one this tenant already has.

    Reconnecting the same account is the normal way a customer fixes an expired
    or downgraded token, so it updates in place rather than failing.
    """
    cipher = cipher or get_token_cipher()
    sealed = cipher.seal(details.access_token)

    existing = await _find(session, tenant_id, details.provider, details.external_id)
    if existing is not None:
        existing.access_token_encrypted = sealed
        existing.token_type = details.token_type
        existing.expires_at = details.expires_at
        existing.granted_scopes = list(details.granted_scopes)
        existing.parent_external_id = details.parent_external_id
        existing.display_name = details.display_name or existing.display_name
        existing.provider_metadata = details.provider_metadata or {}
        existing.status = ConnectionStatus.ACTIVE
        existing.status_detail = None
        existing.connected_by_user_id = connected_by_user_id
        existing.connected_at = datetime.now(UTC)
        await session.flush()
        return existing

    connection = ChannelConnection(
        tenant_id=tenant_id,
        provider=details.provider,
        external_id=details.external_id,
        parent_external_id=details.parent_external_id,
        display_name=details.display_name,
        access_token_encrypted=sealed,
        token_type=details.token_type,
        expires_at=details.expires_at,
        granted_scopes=list(details.granted_scopes),
        status=ConnectionStatus.ACTIVE,
        connected_by_user_id=connected_by_user_id,
        provider_metadata=details.provider_metadata or {},
    )
    try:
        # The savepoint is opened *before* the row is added, so a clash rolls
        # back to it and leaves the surrounding transaction usable. Adding first
        # would let begin_nested()'s autoflush do the insert outside the
        # savepoint, and the whole transaction would die with it.
        async with session.begin_nested():
            session.add(connection)
            await session.flush()
    except IntegrityError as exc:
        # The row exists but this tenant cannot see it, so it belongs to someone
        # else. Without the global unique constraint both would "work", and one
        # business would start receiving the other's customers.
        raise AlreadyConnectedElsewhere(
            f"that {details.provider} account is already connected to another business"
        ) from exc
    return connection


async def list_connections(
    session: AsyncSession, tenant_id: uuid.UUID, *, include_revoked: bool = False
) -> list[ChannelConnection]:
    query = select(ChannelConnection).where(ChannelConnection.tenant_id == tenant_id)
    if not include_revoked:
        query = query.where(ChannelConnection.status != ConnectionStatus.REVOKED)
    result = await session.execute(query.order_by(ChannelConnection.created_at))
    return list(result.scalars())


async def get_connection(
    session: AsyncSession, tenant_id: uuid.UUID, connection_id: uuid.UUID
) -> ChannelConnection:
    connection = await session.get(ChannelConnection, connection_id)
    if connection is None or connection.tenant_id != tenant_id:
        raise ConnectionNotFound(str(connection_id))
    return connection


async def access_token_for(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    cipher: TokenCipher | None = None,
) -> str:
    """Open a stored credential for use.

    A token that will not open means the key changed or the row was altered.
    Either way the connection is no longer usable, so it is marked for
    re-authorisation rather than left to fail on every send.
    """
    connection = await get_connection(session, tenant_id, connection_id)
    try:
        return (cipher or get_token_cipher()).open(connection.access_token_encrypted)
    except TokenUnreadable:
        connection.status = ConnectionStatus.NEEDS_REAUTH
        connection.status_detail = "stored credential could not be read"
        await session.flush()
        raise


async def mark_needs_reauth(
    session: AsyncSession, tenant_id: uuid.UUID, connection_id: uuid.UUID, detail: str
) -> ChannelConnection:
    """The customer revoked us, or the token stopped working.

    The row stays so the dashboard can say so. Silence here is the failure mode
    that leaves a business wondering why nobody is replying to their customers.
    """
    connection = await get_connection(session, tenant_id, connection_id)
    connection.status = ConnectionStatus.NEEDS_REAUTH
    connection.status_detail = detail[:200]
    await session.flush()
    return connection


async def disconnect(
    session: AsyncSession, tenant_id: uuid.UUID, connection_id: uuid.UUID
) -> ChannelConnection:
    """Stop using an account. Kept for the audit trail, and no longer routable.

    The token is destroyed here: once disconnected we have no business holding a
    working credential for someone else's Page.
    """
    connection = await get_connection(session, tenant_id, connection_id)
    connection.status = ConnectionStatus.REVOKED
    connection.status_detail = "disconnected by the business"
    connection.access_token_encrypted = b"\x00"
    await session.flush()
    return connection


async def route_to_tenant(
    session: AsyncSession, provider: Channel, external_id: str
) -> uuid.UUID | None:
    """Which tenant owns this Page / Instagram account / WhatsApp number.

    The webhook's first step, before any tenant context exists. Goes through the
    `channel_route` SQL function (migration 0010), which is the only read in the
    system that crosses a tenant boundary — and all it returns is this UUID.
    Returns None for an account nobody has connected, or one that is revoked.
    """
    result = await session.execute(
        text("SELECT channel_route(:provider, :external_id)"),
        {"provider": Channel(provider).value, "external_id": external_id},
    )
    return result.scalar_one_or_none()


# --- The OAuth handshake ------------------------------------------------------


async def start_oauth(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: Channel,
    *,
    started_by_user_id: uuid.UUID | None = None,
) -> str:
    """Mint the `state` we hand to Meta, and remember who it belongs to."""
    state = secrets.token_urlsafe(32)
    session.add(
        ChannelOAuthState(
            tenant_id=tenant_id,
            state=state,
            provider=provider,
            started_by_user_id=started_by_user_id,
            expires_at=datetime.now(UTC) + OAUTH_STATE_TTL,
        )
    )
    await session.flush()
    return state


async def consume_oauth_state(
    session: AsyncSession, tenant_id: uuid.UUID, state: str
) -> ChannelOAuthState:
    """Redeem a state exactly once.

    Refuses an unknown, expired or already-used value. Single use is what stops
    a captured callback being replayed, so the check and the marking happen in
    the same transaction.
    """
    result = await session.execute(
        select(ChannelOAuthState)
        .where(ChannelOAuthState.tenant_id == tenant_id, ChannelOAuthState.state == state)
        .with_for_update()
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise OAuthStateInvalid("unknown state")
    if record.consumed_at is not None:
        raise OAuthStateInvalid("state has already been used")
    if record.expires_at <= datetime.now(UTC):
        raise OAuthStateInvalid("state has expired")
    record.consumed_at = datetime.now(UTC)
    await session.flush()
    return record


async def purge_expired_states(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Housekeeping: drop states nobody came back for."""
    result = await session.execute(
        select(ChannelOAuthState).where(
            ChannelOAuthState.tenant_id == tenant_id,
            ChannelOAuthState.expires_at <= datetime.now(UTC),
        )
    )
    stale = list(result.scalars())
    for record in stale:
        await session.delete(record)
    await session.flush()
    return len(stale)


async def _find(
    session: AsyncSession, tenant_id: uuid.UUID, provider: Channel, external_id: str
) -> ChannelConnection | None:
    result = await session.execute(
        select(ChannelConnection).where(
            ChannelConnection.tenant_id == tenant_id,
            ChannelConnection.provider == provider,
            ChannelConnection.external_id == external_id,
        )
    )
    return result.scalar_one_or_none()
