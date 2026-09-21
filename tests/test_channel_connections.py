"""CHN-07: connected accounts, sealed tokens, and the one cross-tenant lookup.

The things that would do real damage are the ones tested hardest here: a token
readable straight out of the database, one business connecting a Page that
belongs to another, a revoked connection that still routes, and a replayed
OAuth callback.

`route_to_tenant` deliberately reads across tenants, so it gets the most
attention of all — including proof that it hands back nothing but a UUID.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels.crypto import TokenCipher, TokenUnreadable
from rivon.channels.messages import Channel
from rivon.channels.models import ChannelConnection, ConnectionStatus
from rivon.channels.service import (
    AlreadyConnectedElsewhere,
    ConnectionInput,
    ConnectionNotFound,
    OAuthStateInvalid,
    access_token_for,
    connect,
    consume_oauth_state,
    disconnect,
    get_connection,
    list_connections,
    mark_needs_reauth,
    purge_expired_states,
    route_to_tenant,
    start_oauth,
)
from rivon.platform.tenancy import set_current_tenant
from tests.conftest import Seed

TOKEN = "EAAG-a-real-looking-page-token-0123456789"


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(TokenCipher.generate_key())


def page(external_id: str = "page-1", **overrides) -> ConnectionInput:  # type: ignore[no-untyped-def]
    fields = {
        "provider": Channel.MESSENGER,
        "external_id": external_id,
        "access_token": TOKEN,
        "display_name": "Berlin Solar",
        "granted_scopes": ("pages_messaging", "pages_manage_metadata"),
    }
    return ConnectionInput(**{**fields, **overrides})


async def as_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await set_current_tenant(session, tenant_id)


# --- Sealing ------------------------------------------------------------------


def test_a_sealed_token_does_not_contain_the_token(cipher: TokenCipher) -> None:
    sealed = cipher.seal(TOKEN)
    assert TOKEN.encode() not in sealed
    assert cipher.open(sealed) == TOKEN


def test_the_same_token_seals_differently_each_time(cipher: TokenCipher) -> None:
    # Otherwise equal ciphertexts would reveal which businesses share a token.
    assert cipher.seal(TOKEN) != cipher.seal(TOKEN)


def test_another_key_cannot_open_it(cipher: TokenCipher) -> None:
    sealed = cipher.seal(TOKEN)
    with pytest.raises(TokenUnreadable):
        TokenCipher(TokenCipher.generate_key()).open(sealed)


def test_a_tampered_row_fails_loudly(cipher: TokenCipher) -> None:
    # Authenticated encryption: an edited ciphertext is rejected rather than
    # decrypting into something that looks like a token and isn't.
    sealed = bytearray(cipher.seal(TOKEN))
    sealed[-5] ^= 0xFF
    with pytest.raises(TokenUnreadable):
        cipher.open(bytes(sealed))


def test_an_empty_token_is_refused(cipher: TokenCipher) -> None:
    with pytest.raises(ValueError):
        cipher.seal("   ")


def test_a_key_that_is_not_a_key_says_so() -> None:
    with pytest.raises(ValueError, match="RIVON_CHANNEL_TOKEN_KEY"):
        TokenCipher("hunter2")


# --- Connecting ---------------------------------------------------------------


async def test_connecting_stores_a_usable_but_unreadable_credential(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)

    assert connection.status is ConnectionStatus.ACTIVE
    assert connection.display_name == "Berlin Solar"
    assert connection.granted_scopes == ["pages_messaging", "pages_manage_metadata"]

    # What actually sits in the column is ciphertext.
    stored = await db_session.execute(
        text("SELECT access_token_encrypted FROM channel_connections WHERE id = :id"),
        {"id": connection.id},
    )
    raw = stored.scalar_one()
    assert TOKEN.encode() not in raw

    opened = await access_token_for(db_session, seed.tenant_a.id, connection.id, cipher=cipher)
    assert opened == TOKEN


async def test_reconnecting_refreshes_rather_than_duplicating(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    # How a customer fixes an expired or downgraded token: connect again.
    await as_tenant(db_session, seed.tenant_a.id)
    first = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)
    again = await connect(
        db_session,
        seed.tenant_a.id,
        page(access_token="EAAG-a-fresh-token-9876543210", granted_scopes=("pages_messaging",)),
        cipher=cipher,
    )

    assert again.id == first.id
    assert len(await list_connections(db_session, seed.tenant_a.id)) == 1
    assert await access_token_for(db_session, seed.tenant_a.id, first.id, cipher=cipher) == (
        "EAAG-a-fresh-token-9876543210"
    )


async def test_reconnecting_clears_a_previous_failure(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)
    await mark_needs_reauth(db_session, seed.tenant_a.id, connection.id, "token expired")

    revived = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)
    assert revived.status is ConnectionStatus.ACTIVE
    assert revived.status_detail is None


async def test_two_businesses_cannot_claim_the_same_page(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    """The failure this guards against is a customer's leads going to a stranger."""
    await as_tenant(db_session, seed.tenant_a.id)
    await connect(db_session, seed.tenant_a.id, page("page-shared"), cipher=cipher)

    await as_tenant(db_session, seed.tenant_b.id)
    with pytest.raises(AlreadyConnectedElsewhere) as caught:
        await connect(db_session, seed.tenant_b.id, page("page-shared"), cipher=cipher)
    # And it does not say who has it — that would leak one customer to another.
    assert str(seed.tenant_a.id) not in str(caught.value)

    # The transaction survived the clash, so the request can answer cleanly.
    assert await list_connections(db_session, seed.tenant_b.id) == []


async def test_the_same_id_on_a_different_platform_is_a_different_account(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    await connect(db_session, seed.tenant_a.id, page("12345"), cipher=cipher)
    await connect(
        db_session,
        seed.tenant_a.id,
        ConnectionInput(provider=Channel.INSTAGRAM, external_id="12345", access_token=TOKEN),
        cipher=cipher,
    )
    assert len(await list_connections(db_session, seed.tenant_a.id)) == 2


# --- Isolation ----------------------------------------------------------------


async def test_one_business_never_sees_another_s_connections(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    mine = await connect(db_session, seed.tenant_a.id, page("page-a"), cipher=cipher)

    await as_tenant(db_session, seed.tenant_b.id)
    assert await list_connections(db_session, seed.tenant_b.id) == []
    with pytest.raises(ConnectionNotFound):
        await get_connection(db_session, seed.tenant_b.id, mine.id)
    with pytest.raises(ConnectionNotFound):
        await disconnect(db_session, seed.tenant_b.id, mine.id)


async def test_queries_filter_by_tenant_even_with_rls_satisfied(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    # RLS would already stop this. The application filter is the second lock,
    # and this proves it is actually there rather than being masked by the first.
    await as_tenant(db_session, seed.tenant_a.id)
    mine = await connect(db_session, seed.tenant_a.id, page("page-a"), cipher=cipher)
    with pytest.raises(ConnectionNotFound):
        await get_connection(db_session, seed.tenant_b.id, mine.id)


async def test_connecting_never_overwrites_a_row_rls_happens_to_expose(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    """The nastiest version of relying on RLS alone.

    Tenant A owns the Page. If the lookup behind `connect` matched on the Page
    alone, then a call made on behalf of tenant B — while the session's RLS
    context still says A — would find A's row and quietly overwrite A's
    credential with B's. No error, no new row, and one business silently
    holding another's connection. The tenant filter is what makes it a refusal.
    """
    await as_tenant(db_session, seed.tenant_a.id)
    theirs = await connect(db_session, seed.tenant_a.id, page("page-contested"), cipher=cipher)

    # Refused — by the unique constraint, or by RLS rejecting a write for a
    # tenant that is not the session's. Which one is not the point.
    with pytest.raises((AlreadyConnectedElsewhere, DBAPIError)):
        await connect(
            db_session,
            seed.tenant_b.id,
            page("page-contested", access_token="EAAG-token-belonging-to-b"),
            cipher=cipher,
        )

    # This is the point: A's connection is untouched, and still A's.
    await db_session.refresh(theirs)
    assert theirs.tenant_id == seed.tenant_a.id
    assert await access_token_for(db_session, seed.tenant_a.id, theirs.id, cipher=cipher) == TOKEN


# --- Routing ------------------------------------------------------------------


async def test_routing_finds_the_owner_without_a_tenant_in_context(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    """The webhook's first move: an account id in, one tenant id out."""
    await as_tenant(db_session, seed.tenant_a.id)
    await connect(db_session, seed.tenant_a.id, page("page-routed"), cipher=cipher)

    # No tenant set at all, exactly as the webhook sees things.
    await db_session.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
    assert await route_to_tenant(db_session, Channel.MESSENGER, "page-routed") == seed.tenant_a.id


async def test_routing_reveals_nothing_but_the_tenant_id(db_session: AsyncSession, seed: Seed,
                                                         cipher: TokenCipher) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    await connect(db_session, seed.tenant_a.id, page("page-secret"), cipher=cipher)
    await db_session.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))

    # The function is the only cross-tenant read; the table itself stays shut.
    rows = await db_session.execute(text("SELECT count(*) FROM channel_connections"))
    assert rows.scalar_one() == 0, "RLS must still hide the rows themselves"

    # And raising the flag the function uses gains the application role nothing:
    # the policy that honours it applies to the owner role only.
    await db_session.execute(text("SELECT set_config('app.channel_route', 'on', true)"))
    rows = await db_session.execute(
        text("SELECT count(*), count(access_token_encrypted) FROM channel_connections")
    )
    assert rows.one() == (0, 0), "the routing flag must not be a way in"


@pytest.mark.parametrize(
    ("provider", "external_id"),
    [(Channel.MESSENGER, "never-connected"), (Channel.WHATSAPP, "page-known"), (Channel.MESSENGER, "")],
)
async def test_routing_an_unknown_account_returns_nothing(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher, provider: Channel, external_id: str
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    await connect(db_session, seed.tenant_a.id, page("page-known"), cipher=cipher)
    assert await route_to_tenant(db_session, provider, external_id) is None


async def test_a_disconnected_account_stops_routing(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page("page-gone"), cipher=cipher)
    assert await route_to_tenant(db_session, Channel.MESSENGER, "page-gone") == seed.tenant_a.id

    await disconnect(db_session, seed.tenant_a.id, connection.id)
    assert await route_to_tenant(db_session, Channel.MESSENGER, "page-gone") is None


async def test_an_account_needing_reauth_stops_routing(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    # We cannot reply, so accepting the message would leave the customer waiting
    # for an answer that is never coming.
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page("page-stale"), cipher=cipher)
    await mark_needs_reauth(db_session, seed.tenant_a.id, connection.id, "customer revoked access")
    assert await route_to_tenant(db_session, Channel.MESSENGER, "page-stale") is None


# --- Disconnecting ------------------------------------------------------------


async def test_disconnecting_destroys_the_credential(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)

    await disconnect(db_session, seed.tenant_a.id, connection.id)

    assert connection.status is ConnectionStatus.REVOKED
    with pytest.raises(TokenUnreadable):
        await access_token_for(db_session, seed.tenant_a.id, connection.id, cipher=cipher)


async def test_a_revoked_connection_is_out_of_the_way_but_not_gone(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)
    await disconnect(db_session, seed.tenant_a.id, connection.id)

    assert await list_connections(db_session, seed.tenant_a.id) == []
    kept = await list_connections(db_session, seed.tenant_a.id, include_revoked=True)
    assert [c.id for c in kept] == [connection.id], "the audit trail survives"


async def test_an_unreadable_credential_marks_itself_for_reconnection(
    db_session: AsyncSession, seed: Seed, cipher: TokenCipher
) -> None:
    # What happens after the encryption key is rotated: the customer is told to
    # reconnect, instead of every send failing with nothing explaining why.
    await as_tenant(db_session, seed.tenant_a.id)
    connection = await connect(db_session, seed.tenant_a.id, page(), cipher=cipher)

    other_key = TokenCipher(TokenCipher.generate_key())
    with pytest.raises(TokenUnreadable):
        await access_token_for(db_session, seed.tenant_a.id, connection.id, cipher=other_key)

    assert connection.status is ConnectionStatus.NEEDS_REAUTH
    assert await route_to_tenant(db_session, Channel.MESSENGER, connection.external_id) is None


# --- The OAuth handshake ------------------------------------------------------


async def test_a_state_can_be_redeemed_once(db_session: AsyncSession, seed: Seed) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    state = await start_oauth(db_session, seed.tenant_a.id, Channel.MESSENGER)

    redeemed = await consume_oauth_state(db_session, seed.tenant_a.id, state)
    assert redeemed.provider is Channel.MESSENGER
    assert redeemed.consumed_at is not None

    # A captured callback replayed at us is refused.
    with pytest.raises(OAuthStateInvalid, match="already been used"):
        await consume_oauth_state(db_session, seed.tenant_a.id, state)


async def test_states_are_long_and_unguessable(db_session: AsyncSession, seed: Seed) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    states = {await start_oauth(db_session, seed.tenant_a.id, Channel.WHATSAPP) for _ in range(5)}
    assert len(states) == 5
    assert all(len(s) >= 32 for s in states)


async def test_an_unknown_state_is_refused(db_session: AsyncSession, seed: Seed) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(OAuthStateInvalid, match="unknown"):
        await consume_oauth_state(db_session, seed.tenant_a.id, "not-a-state-we-issued")


async def test_another_tenant_cannot_redeem_our_state(db_session: AsyncSession, seed: Seed) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    state = await start_oauth(db_session, seed.tenant_a.id, Channel.MESSENGER)

    await as_tenant(db_session, seed.tenant_b.id)
    with pytest.raises(OAuthStateInvalid):
        await consume_oauth_state(db_session, seed.tenant_b.id, state)


async def test_a_state_is_not_redeemable_by_a_tenant_rls_happens_to_expose(
    db_session: AsyncSession, seed: Seed
) -> None:
    # The session's RLS context still says A, so A's state row is visible. If
    # the lookup matched on the state value alone, a call made for tenant B
    # would consume it and hand B a connection meant for A. Matching on the
    # tenant as well is what makes this a refusal rather than a hijack.
    await as_tenant(db_session, seed.tenant_a.id)
    state = await start_oauth(db_session, seed.tenant_a.id, Channel.MESSENGER)

    with pytest.raises(OAuthStateInvalid):
        await consume_oauth_state(db_session, seed.tenant_b.id, state)

    # And A can still use it, because nothing consumed it.
    assert (await consume_oauth_state(db_session, seed.tenant_a.id, state)).state == state


async def test_an_expired_state_is_refused(db_session: AsyncSession, seed: Seed) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    state = await start_oauth(db_session, seed.tenant_a.id, Channel.MESSENGER)
    await db_session.execute(
        text("UPDATE channel_oauth_states SET expires_at = :past WHERE state = :state"),
        {"past": datetime.now(UTC) - timedelta(seconds=1), "state": state},
    )
    with pytest.raises(OAuthStateInvalid, match="expired"):
        await consume_oauth_state(db_session, seed.tenant_a.id, state)


async def test_expired_states_are_cleared_out(db_session: AsyncSession, seed: Seed) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    stale = await start_oauth(db_session, seed.tenant_a.id, Channel.MESSENGER)
    fresh = await start_oauth(db_session, seed.tenant_a.id, Channel.INSTAGRAM)
    await db_session.execute(
        text("UPDATE channel_oauth_states SET expires_at = :past WHERE state = :state"),
        {"past": datetime.now(UTC) - timedelta(hours=1), "state": stale},
    )

    assert await purge_expired_states(db_session, seed.tenant_a.id) == 1
    assert (await consume_oauth_state(db_session, seed.tenant_a.id, fresh)).state == fresh


# --- The schema itself --------------------------------------------------------


async def test_the_database_refuses_a_second_claim_on_a_page(
    db_session: AsyncSession, seed: Seed
) -> None:
    """Belt and braces: the guarantee holds even if the service layer is bypassed."""
    await as_tenant(db_session, seed.tenant_a.id)
    await db_session.execute(
        text(
            "INSERT INTO channel_connections (tenant_id, provider, external_id,"
            " access_token_encrypted) VALUES (:t, 'messenger', 'page-raw', '\\x01'::bytea)"
        ),
        {"t": seed.tenant_a.id},
    )
    await db_session.flush()

    await as_tenant(db_session, seed.tenant_b.id)
    with pytest.raises(Exception) as caught:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO channel_connections (tenant_id, provider, external_id,"
                    " access_token_encrypted) VALUES (:t, 'messenger', 'page-raw', '\\x01'::bytea)"
                ),
                {"t": seed.tenant_b.id},
            )
    assert "uq_channel_connections_provider_external_id" in str(caught.value)


async def test_a_connection_cannot_be_stored_without_a_credential(
    db_session: AsyncSession, seed: Seed
) -> None:
    await as_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(Exception, match="ck_channel_connections_token_present"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO channel_connections (tenant_id, provider, external_id,"
                    " access_token_encrypted) VALUES (:t, 'messenger', 'p', ''::bytea)"
                ),
                {"t": seed.tenant_a.id},
            )
