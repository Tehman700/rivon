"""BETA: connect by choosing a Page, the ManyChat way.

Runs beside the current connect flow (`oauth.py`) without changing it, so it
can be tried in production and then merged in or swapped for the old one.

What is different, and why:

**It logs in with a user token, not a business one.** A business token needs
the customer to have a Meta business portfolio, and only reaches the assets
ticked in Meta's dialog. A brand-new installer usually has neither a portfolio
nor a Page, and a Page created after the dialog would be invisible. A user token
can list every Page the person manages — including one they make halfway
through connecting.

**Rivon shows the list, and the customer chooses.** Meta's dialog only grants
access; our own screen lists the Pages with a Connect button each, and an empty
state that sends them to Facebook to create one, then refreshes when they come
back. Nothing is connected until they press Connect.

**The user token is held only while they choose.** Encrypted, for thirty
minutes at most, and destroyed when the session closes. What is kept afterwards
is the Page's own token, exactly as in the current flow — and a Page token read
with a long-lived user token does not expire.

Nobody can create the Page for them: Meta has no API for it. The best a product
can do is make the round trip to Facebook short, which is what the empty state
is for.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels import service
from rivon.channels.crypto import TokenCipher, TokenUnreadable
from rivon.channels.messages import Channel
from rivon.channels.meta import GrantedPage, MetaGraph
from rivon.channels.models import ChannelConnection, ChannelPickerSession, ConnectionStatus
from rivon.channels.oauth import (
    REQUIRED_INSTAGRAM_SCOPES,
    REQUIRED_PAGE_SCOPES,
    ConnectFailed,
    PermissionsDeclined,
)
from rivon.channels.service import AlreadyConnectedElsewhere, ConnectionInput, get_token_cipher

#: Long enough to create a Page on Facebook and come back; short enough that a
#: forgotten tab does not leave a usable token lying around.
SESSION_TTL = timedelta(minutes=30)

#: Facebook's own Page creator. Only a person can make a Page.
CREATE_PAGE_URL = "https://www.facebook.com/pages/create"

AVAILABLE = "available"
CONNECTED = "connected"
TAKEN = "taken"


class SessionExpired(ConnectFailed):
    def __init__(self) -> None:
        super().__init__("This connection window has closed. Please press Connect again.")


class PageNotFound(ConnectFailed):
    def __init__(self) -> None:
        super().__init__(
            "That Page is not one you manage, or Rivon was not given access to it. "
            "Use “I can't see my Page” to grant access."
        )


@dataclass(frozen=True, slots=True)
class PickerPage:
    page: GrantedPage
    messenger_status: str
    instagram_status: str | None


async def begin(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    graph: MetaGraph,
    config_id: str,
    redirect_uri: str,
    started_by_user_id: uuid.UUID | None = None,
) -> str:
    """The Meta dialog to send them to. Same single-use state as the old flow."""
    state = await service.start_oauth(
        session, tenant_id, Channel.MESSENGER, started_by_user_id=started_by_user_id
    )
    return graph.authorize_url(config_id=config_id, state=state, redirect_uri=redirect_uri)


async def open_session(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str,
    state: str,
    graph: MetaGraph,
    redirect_uri: str,
    started_by_user_id: uuid.UUID | None = None,
    cipher: TokenCipher | None = None,
) -> ChannelPickerSession:
    """Turn Meta's callback into a session the picker can list Pages from."""
    await service.consume_oauth_state(session, tenant_id, state)

    short = await graph.exchange_code(code, redirect_uri=redirect_uri)
    long = await graph.extend_user_token(short.access_token)
    granted = await graph.inspect_token(long.access_token)
    if not granted.is_valid:
        raise ConnectFailed("Meta says that sign-in is not valid. Please try again.")
    missing = tuple(s for s in REQUIRED_PAGE_SCOPES if s not in granted.scopes)
    if missing:
        raise PermissionsDeclined(missing)

    picker = ChannelPickerSession(
        tenant_id=tenant_id,
        user_token_encrypted=(cipher or get_token_cipher()).seal(long.access_token),
        granted_scopes=list(granted.scopes),
        started_by_user_id=started_by_user_id,
        expires_at=datetime.now(UTC) + SESSION_TTL,
    )
    session.add(picker)
    await session.flush()
    return picker


async def list_pages(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    graph: MetaGraph,
    cipher: TokenCipher | None = None,
) -> tuple[ChannelPickerSession, list[PickerPage]]:
    """Every Page the person manages, as of now — which is what makes Refresh work."""
    picker, token = await _open(session, tenant_id, session_id, cipher)
    pages = await graph.granted_pages(token)
    instagram_allowed = all(s in picker.granted_scopes for s in REQUIRED_INSTAGRAM_SCOPES)

    listed = []
    for page in pages:
        instagram_status = None
        if page.instagram_id and instagram_allowed:
            instagram_status = await _status(session, tenant_id, Channel.INSTAGRAM, page.instagram_id)
        listed.append(
            PickerPage(
                page=page,
                messenger_status=await _status(session, tenant_id, Channel.MESSENGER, page.id),
                instagram_status=instagram_status,
            )
        )
    return picker, listed


async def connect_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    page_id: str,
    include_instagram: bool,
    graph: MetaGraph,
    connected_by_user_id: uuid.UUID | None = None,
    cipher: TokenCipher | None = None,
) -> list[ChannelConnection]:
    """Connect the one Page they chose, and its Instagram account if they want it."""
    picker, token = await _open(session, tenant_id, session_id, cipher)

    # Read the Page's token fresh rather than trusting anything the browser sent.
    page = next((p for p in await graph.granted_pages(token) if p.id == page_id), None)
    if page is None:
        raise PageNotFound()

    # Subscribe before storing: an unsubscribed Page looks connected and
    # receives nothing.
    await graph.subscribe_page(page.id, page.access_token)

    scopes = tuple(picker.granted_scopes)
    try:
        messenger = await service.connect(
            session,
            tenant_id,
            ConnectionInput(
                provider=Channel.MESSENGER,
                external_id=page.id,
                access_token=page.access_token,
                display_name=page.name or None,
                token_type="page",
                granted_scopes=scopes,
            ),
            connected_by_user_id=connected_by_user_id,
            cipher=cipher,
        )
    except AlreadyConnectedElsewhere as exc:
        raise ConnectFailed("That Page is already connected to another business.") from exc
    connected = [messenger]
    instagram_allowed = all(s in scopes for s in REQUIRED_INSTAGRAM_SCOPES)
    if include_instagram and page.instagram_id and instagram_allowed:
        try:
            connected.append(
                await service.connect(
                    session,
                    tenant_id,
                    ConnectionInput(
                        provider=Channel.INSTAGRAM,
                        external_id=page.instagram_id,
                        access_token=page.access_token,
                        parent_external_id=page.id,
                        display_name=page.instagram_username or None,
                        token_type="page",
                        granted_scopes=scopes,
                    ),
                    connected_by_user_id=connected_by_user_id,
                    cipher=cipher,
                )
            )
        except AlreadyConnectedElsewhere:
            pass  # the Page itself connected; the listing will say the account is taken
    return connected


async def close(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> None:
    """Finished choosing: destroy the user token now rather than at expiry."""
    picker = await _get(session, tenant_id, session_id)
    if picker is not None and picker.closed_at is None:
        picker.closed_at = datetime.now(UTC)
        picker.user_token_encrypted = b"\x00"
        await session.flush()


async def purge_expired(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Housekeeping: drop sessions nobody finished."""
    result = await session.execute(
        select(ChannelPickerSession).where(
            ChannelPickerSession.tenant_id == tenant_id,
            ChannelPickerSession.expires_at <= datetime.now(UTC),
        )
    )
    stale = list(result.scalars())
    for picker in stale:
        await session.delete(picker)
    await session.flush()
    return len(stale)


# --- Internals ----------------------------------------------------------------


async def _get(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> ChannelPickerSession | None:
    result = await session.execute(
        select(ChannelPickerSession).where(
            ChannelPickerSession.tenant_id == tenant_id,
            ChannelPickerSession.id == session_id,
        )
    )
    return result.scalar_one_or_none()


async def _open(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    cipher: TokenCipher | None,
) -> tuple[ChannelPickerSession, str]:
    picker = await _get(session, tenant_id, session_id)
    if picker is None or picker.closed_at is not None or picker.expires_at <= datetime.now(UTC):
        raise SessionExpired()
    try:
        return picker, (cipher or get_token_cipher()).open(picker.user_token_encrypted)
    except TokenUnreadable as exc:
        raise SessionExpired() from exc


async def _status(
    session: AsyncSession, tenant_id: uuid.UUID, provider: Channel, external_id: str
) -> str:
    """Whether an account is free, already ours, or held by another business.

    "Taken" says nothing about *which* business — that would leak one
    customer's arrangements to another.
    """
    ours = await service.connection_for(session, tenant_id, provider, external_id)
    if ours is not None and ours.status is ConnectionStatus.ACTIVE:
        return CONNECTED
    owner = await service.route_to_tenant(session, provider, external_id)
    if owner is not None and owner != tenant_id:
        return TAKEN
    return AVAILABLE
