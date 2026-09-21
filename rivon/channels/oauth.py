"""CHN-13: the self-serve connect flow for Facebook Pages and Instagram.

What happens between the customer pressing *Connect* and their Page answering
messages. `meta.py` does the talking; `service.py` does the storing; this module
decides the order and what counts as a failure.

Instagram goes through the Page rather than Instagram's own login: one consent
screen, one token, and no 60-day refresh treadmill. So a single flow can return
a Messenger connection, an Instagram connection, or both, depending on what the
customer ticked.

Two things are checked rather than assumed. That the permissions we need were
actually granted — a customer can untick one in the dialog, and finding out
then is far better than as a 403 the first time a real customer is waiting. And
that each Page was successfully subscribed, because an unsubscribed Page looks
perfectly connected and silently receives nothing.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels import service
from rivon.channels.crypto import TokenCipher, TokenUnreadable
from rivon.channels.messages import Channel
from rivon.channels.meta import GrantedPage, MetaApiError, MetaGraph
from rivon.channels.models import ChannelConnection, ConnectionStatus
from rivon.channels.service import AlreadyConnectedElsewhere, ConnectionInput

#: Without these a Page cannot be subscribed, or replied on.
REQUIRED_PAGE_SCOPES = ("pages_messaging", "pages_manage_metadata")
#: Extra permissions before we will claim to handle someone's Instagram DMs.
REQUIRED_INSTAGRAM_SCOPES = ("instagram_basic", "instagram_manage_messages")

#: Which button the customer pressed. Both end up in the same dialog.
PAGE_ROUTE_CHANNELS = (Channel.MESSENGER, Channel.INSTAGRAM)


class ConnectFailed(Exception):
    """The flow could not be completed. The message is shown to the customer."""


class PermissionsDeclined(ConnectFailed):
    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__(
            "Rivon needs a little more access than was granted. Please connect again "
            "and leave every permission ticked."
        )


class NothingGranted(ConnectFailed):
    def __init__(self) -> None:
        super().__init__(
            "No Facebook Page was shared. Please connect again and choose the Page "
            "your customers message."
        )


@dataclass(frozen=True, slots=True)
class ConnectOutcome:
    connected: tuple[ChannelConnection, ...]
    #: (what it was, why it was left out) — shown to the customer, so they are
    #: never left wondering why a Page they picked is missing.
    skipped: tuple[tuple[str, str], ...] = ()


async def begin_page_connection(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: Channel,
    *,
    graph: MetaGraph,
    config_id: str,
    redirect_uri: str,
    started_by_user_id: uuid.UUID | None = None,
) -> str:
    """Mint a single-use state and return the Meta dialog to send them to."""
    if provider not in PAGE_ROUTE_CHANNELS:
        raise ConnectFailed(f"{provider} does not use the Page connect flow")
    state = await service.start_oauth(
        session, tenant_id, provider, started_by_user_id=started_by_user_id
    )
    return graph.authorize_url(config_id=config_id, state=state, redirect_uri=redirect_uri)


async def complete_page_connection(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str,
    state: str,
    graph: MetaGraph,
    redirect_uri: str,
    connected_by_user_id: uuid.UUID | None = None,
    cipher: TokenCipher | None = None,
) -> ConnectOutcome:
    """Turn a callback into working connections.

    Redeeming the state first is what stops a captured callback being replayed:
    everything after it is wasted work if the state is not ours and unused.
    """
    await service.consume_oauth_state(session, tenant_id, state)

    grant = await graph.exchange_code(code, redirect_uri=redirect_uri)
    granted = await graph.inspect_token(grant.access_token)
    if not granted.is_valid:
        raise ConnectFailed("Meta says that authorisation is not valid. Please try again.")

    missing = tuple(s for s in REQUIRED_PAGE_SCOPES if s not in granted.scopes)
    if missing:
        raise PermissionsDeclined(missing)
    instagram_allowed = all(s in granted.scopes for s in REQUIRED_INSTAGRAM_SCOPES)

    pages = await graph.granted_pages(grant.access_token)
    if not pages:
        raise NothingGranted()

    connected: list[ChannelConnection] = []
    skipped: list[tuple[str, str]] = []
    for page in pages:
        try:
            # Subscribe before storing: a connection we could not subscribe is
            # worse than no connection, because it looks like it works.
            await graph.subscribe_page(page.id, page.access_token)
        except MetaApiError as exc:
            skipped.append((page.name or page.id, f"Facebook would not enable messages: {exc}"))
            continue

        try:
            connected.append(
                await service.connect(
                    session,
                    tenant_id,
                    ConnectionInput(
                        provider=Channel.MESSENGER,
                        external_id=page.id,
                        access_token=page.access_token,
                        display_name=page.name or None,
                        token_type=grant.token_type,
                        expires_at=granted.expires_at,
                        granted_scopes=granted.scopes,
                    ),
                    connected_by_user_id=connected_by_user_id,
                    cipher=cipher,
                )
            )
        except AlreadyConnectedElsewhere:
            skipped.append((page.name or page.id, "already connected to another business"))
            continue

        if page.instagram_id and instagram_allowed:
            instagram = await _connect_instagram(
                session, tenant_id, page, grant, granted, connected_by_user_id, cipher
            )
            if instagram is not None:
                connected.append(instagram)
            else:
                skipped.append(
                    (page.instagram_username or page.instagram_id,
                     "already connected to another business")
                )
        elif page.instagram_id:
            skipped.append(
                (page.instagram_username or page.instagram_id,
                 "Instagram message access was not granted")
            )

    if not connected:
        raise ConnectFailed(
            "Nothing could be connected. " + "; ".join(reason for _, reason in skipped)
        )
    return ConnectOutcome(connected=tuple(connected), skipped=tuple(skipped))


async def _connect_instagram(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    page: GrantedPage,
    grant,  # TokenGrant
    granted,  # TokenInfo
    connected_by_user_id: uuid.UUID | None,
    cipher: TokenCipher | None,
) -> ChannelConnection | None:
    """The Instagram account hanging off a Page, on the Page's own token."""
    assert page.instagram_id is not None
    try:
        return await service.connect(
            session,
            tenant_id,
            ConnectionInput(
                provider=Channel.INSTAGRAM,
                external_id=page.instagram_id,
                access_token=page.access_token,
                parent_external_id=page.id,
                display_name=page.instagram_username or None,
                token_type=grant.token_type,
                expires_at=granted.expires_at,
                granted_scopes=granted.scopes,
            ),
            connected_by_user_id=connected_by_user_id,
            cipher=cipher,
        )
    except AlreadyConnectedElsewhere:
        return None


async def disconnect_and_unsubscribe(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    graph: MetaGraph,
    cipher: TokenCipher | None = None,
) -> ChannelConnection:
    """Disconnect here, and stop Meta sending, when nothing else needs the Page.

    A Page and the Instagram account attached to it share one token and one
    subscription, so unsubscribing while the other is still connected would
    quietly break it.
    """
    connection = await service.get_connection(session, tenant_id, connection_id)
    page_id = connection.parent_external_id or connection.external_id
    try:
        page_token = await service.access_token_for(
            session, tenant_id, connection_id, cipher=cipher
        )
    except TokenUnreadable:
        page_token = None  # nothing to unsubscribe with; still disconnect locally

    disconnected = await service.disconnect(session, tenant_id, connection_id)

    if page_token and not await _page_still_in_use(session, tenant_id, page_id):
        try:
            await graph.unsubscribe_page(page_id, page_token)
        except MetaApiError:
            # Meta's side is now out of step with ours, but the customer asked
            # to be disconnected and locally they are: we no longer hold a
            # usable token or route anything to them.
            pass
    return disconnected


async def _page_still_in_use(session: AsyncSession, tenant_id: uuid.UUID, page_id: str) -> bool:
    result = await session.execute(
        select(ChannelConnection.id).where(
            ChannelConnection.tenant_id == tenant_id,
            ChannelConnection.status == ConnectionStatus.ACTIVE,
            (ChannelConnection.external_id == page_id)
            | (ChannelConnection.parent_external_id == page_id),
        )
    )
    return result.first() is not None
