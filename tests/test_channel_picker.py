"""BETA: connecting by choosing a Page (picker.py, api_v2.py).

The point of the new flow is the ManyChat round trip: sign in, see your Pages,
none there, create one on Facebook, come back, Refresh, Connect. So the test
that matters most is that a Page created *after* signing in shows up on the
next listing — the thing the current flow cannot do.

The rest guards what makes holding a user token acceptable: it is encrypted,
it never reaches the browser, it dies with the session, and one business's
session is invisible to another. And that nothing is connected until the
customer presses Connect on a specific Page.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels import picker, service
from rivon.channels.api import get_graph
from rivon.channels.crypto import TokenCipher
from rivon.channels.messages import Channel
from rivon.channels.meta import MetaGraph
from rivon.channels.models import ConnectionStatus
from rivon.channels.oauth import ConnectFailed, PermissionsDeclined
from rivon.channels.service import ConnectionInput, OAuthStateInvalid
from rivon.platform.tenancy import set_current_tenant
from tests.conftest import Seed, TenantUsers

REDIRECT = "https://app.example/connect/meta/beta"
PAGE_SCOPES = ["pages_show_list", "pages_messaging", "pages_manage_metadata", "business_management"]
IG_SCOPES = ["instagram_basic", "instagram_manage_messages"]


class FakeMeta:
    """Meta for the picker: a person who manages some Pages, and may make more."""

    def __init__(self) -> None:
        self.mark = uuid.uuid4().hex[:8]
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.scopes = PAGE_SCOPES + IG_SCOPES
        self.pages: list[dict[str, Any]] = []
        self.subscribed: set[str] = set()

    def page(self, suffix: str, name: str, *, instagram: bool = False) -> str:
        page_id = f"page-{self.mark}-{suffix}"
        item: dict[str, Any] = {"id": page_id, "name": name, "access_token": f"PAGE-TOKEN-{suffix}"}
        if instagram:
            item["instagram_business_account"] = {"id": f"ig-{self.mark}-{suffix}", "username": f"{suffix}_ig"}
        self.pages.append(item)
        return page_id

    async def __call__(self, method: str, url: str, params: dict[str, Any], data: dict[str, Any] | None):  # type: ignore[no-untyped-def]
        path = url.split("/v25.0/", 1)[1]
        body = {**params, **(data or {})}
        self.calls.append((method, path, body))
        if path == "oauth/access_token" and body.get("grant_type") == "fb_exchange_token":
            assert body["fb_exchange_token"] == "SHORT-USER-TOKEN"
            return {"access_token": "LONG-USER-TOKEN", "token_type": "bearer", "expires_in": 5184000}
        if path == "oauth/access_token":
            return {"access_token": "SHORT-USER-TOKEN", "token_type": "bearer", "expires_in": 3600}
        if path == "debug_token":
            return {"data": {"scopes": list(self.scopes), "expires_at": 0, "is_valid": True}}
        if path == "me/accounts":
            assert body["access_token"] == "LONG-USER-TOKEN", "list with the long-lived token"
            return {"data": list(self.pages)}
        if path.endswith("/subscribed_apps"):
            self.subscribed.add(path.split("/", 1)[0])
            return {"success": True}
        raise AssertionError(f"unexpected Graph path: {path}")


@pytest.fixture
def meta() -> FakeMeta:
    return FakeMeta()


@pytest.fixture
def graph(meta: FakeMeta) -> MetaGraph:
    return MetaGraph("test-app-id", "test-app-secret", transport=meta)


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(TokenCipher.generate_key())


def state_from(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)["state"][0]


async def signed_in(session: AsyncSession, tenant_id: uuid.UUID, graph: MetaGraph, cipher: TokenCipher):  # type: ignore[no-untyped-def]
    url = await picker.begin(session, tenant_id, graph=graph, config_id="cfg-v2", redirect_uri=REDIRECT)
    return await picker.open_session(
        session, tenant_id, code="a-code", state=state_from(url), graph=graph,
        redirect_uri=REDIRECT, cipher=cipher,
    )


# --- Signing in ---------------------------------------------------------------


async def test_the_dialog_uses_the_beta_configuration(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    url = await picker.begin(db_session, seed.tenant_a.id, graph=graph, config_id="cfg-v2", redirect_uri=REDIRECT)
    assert "config_id=cfg-v2" in url
    assert "connect%2Fmeta%2Fbeta" in url
    assert "response_type=code" in url


async def test_signing_in_keeps_a_long_lived_token_sealed(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)

    # The short-lived token was traded for the long one, which is what is kept.
    assert cipher.open(opened.user_token_encrypted) == "LONG-USER-TOKEN"
    assert b"LONG-USER-TOKEN" not in opened.user_token_encrypted
    assert opened.expires_at <= datetime.now(UTC) + picker.SESSION_TTL
    grant_types = [b.get("grant_type") for _, p, b in meta.calls if p == "oauth/access_token"]
    assert grant_types == [None, "fb_exchange_token"]


async def test_signing_in_connects_nothing(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    # The difference from the old flow: access is not the same as choosing.
    meta.page("a", "Berlin Solar")
    await set_current_tenant(db_session, seed.tenant_a.id)
    await signed_in(db_session, seed.tenant_a.id, graph, cipher)

    assert await service.list_connections(db_session, seed.tenant_a.id) == []
    assert meta.subscribed == set()


async def test_a_declined_page_permission_stops_it(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.scopes = [s for s in meta.scopes if s != "pages_manage_metadata"]
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(PermissionsDeclined):
        await signed_in(db_session, seed.tenant_a.id, graph, cipher)


async def test_a_callback_cannot_be_replayed(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    url = await picker.begin(db_session, seed.tenant_a.id, graph=graph, config_id="c", redirect_uri=REDIRECT)
    state = state_from(url)
    await picker.open_session(db_session, seed.tenant_a.id, code="c", state=state, graph=graph,
                              redirect_uri=REDIRECT, cipher=cipher)
    with pytest.raises(OAuthStateInvalid):
        await picker.open_session(db_session, seed.tenant_a.id, code="c", state=state, graph=graph,
                                  redirect_uri=REDIRECT, cipher=cipher)


# --- The list, and the ManyChat round trip ------------------------------------


async def test_no_pages_is_an_empty_list_not_an_error(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    _, pages = await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)
    assert pages == []


async def test_a_page_created_after_signing_in_appears_on_refresh(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    """The whole reason for this flow."""
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    _, before = await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)
    assert before == []

    # They go to Facebook, create a Page, and come back.
    new_page = meta.page("new", "Tehman Testing")

    _, after = await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)
    assert [p.page.id for p in after] == [new_page]
    assert after[0].messenger_status == picker.AVAILABLE


async def test_the_list_says_what_is_already_connected_and_what_is_taken(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    ours = meta.page("ours", "Ours")
    theirs = meta.page("theirs", "Theirs")
    free = meta.page("free", "Free")

    await set_current_tenant(db_session, seed.tenant_b.id)
    await service.connect(db_session, seed.tenant_b.id,
                          ConnectionInput(provider=Channel.MESSENGER, external_id=theirs, access_token="T"),
                          cipher=cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    await service.connect(db_session, seed.tenant_a.id,
                          ConnectionInput(provider=Channel.MESSENGER, external_id=ours, access_token="T"),
                          cipher=cipher)

    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    _, pages = await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)
    status = {p.page.id: p.messenger_status for p in pages}
    assert status == {ours: picker.CONNECTED, theirs: picker.TAKEN, free: picker.AVAILABLE}


async def test_instagram_status_only_when_instagram_was_granted(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.page("a", "Berlin Solar", instagram=True)
    meta.scopes = list(PAGE_SCOPES)
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    _, pages = await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)
    assert pages[0].page.instagram_id is not None
    assert pages[0].instagram_status is None, "cannot be connected without its permissions"


# --- Connecting ---------------------------------------------------------------


async def test_only_the_chosen_page_is_connected(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    chosen = meta.page("a", "Berlin Solar")
    meta.page("b", "Other Page")
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)

    connected = await picker.connect_page(db_session, seed.tenant_a.id, opened.id, page_id=chosen,
                                          include_instagram=True, graph=graph, cipher=cipher)

    assert [(c.provider, c.external_id) for c in connected] == [(Channel.MESSENGER, chosen)]
    assert meta.subscribed == {chosen}, "subscribed, or it would receive nothing"
    token = await service.access_token_for(db_session, seed.tenant_a.id, connected[0].id, cipher=cipher)
    assert token == "PAGE-TOKEN-a", "the Page's own token, never the user's"
    assert await service.route_to_tenant(db_session, Channel.MESSENGER, chosen) == seed.tenant_a.id


async def test_instagram_comes_along_when_asked(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    page_id = meta.page("a", "Berlin Solar", instagram=True)
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)

    connected = await picker.connect_page(db_session, seed.tenant_a.id, opened.id, page_id=page_id,
                                          include_instagram=True, graph=graph, cipher=cipher)
    assert {c.provider for c in connected} == {Channel.MESSENGER, Channel.INSTAGRAM}
    instagram = next(c for c in connected if c.provider is Channel.INSTAGRAM)
    assert instagram.parent_external_id == page_id


async def test_instagram_is_left_alone_when_not_wanted(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    page_id = meta.page("a", "Berlin Solar", instagram=True)
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    connected = await picker.connect_page(db_session, seed.tenant_a.id, opened.id, page_id=page_id,
                                          include_instagram=False, graph=graph, cipher=cipher)
    assert [c.provider for c in connected] == [Channel.MESSENGER]


async def test_a_page_they_do_not_manage_cannot_be_connected(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    # The page id comes from the browser. It is only trusted if Meta lists it.
    meta.page("a", "Berlin Solar")
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    with pytest.raises(picker.PageNotFound):
        await picker.connect_page(db_session, seed.tenant_a.id, opened.id, page_id="someone-elses-page",
                                  include_instagram=True, graph=graph, cipher=cipher)
    assert await service.list_connections(db_session, seed.tenant_a.id) == []


async def test_a_page_another_business_holds_is_refused(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    page_id = meta.page("a", "Berlin Solar")
    await set_current_tenant(db_session, seed.tenant_b.id)
    await service.connect(db_session, seed.tenant_b.id,
                          ConnectionInput(provider=Channel.MESSENGER, external_id=page_id, access_token="T"),
                          cipher=cipher)
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    with pytest.raises(ConnectFailed, match="another business"):
        await picker.connect_page(db_session, seed.tenant_a.id, opened.id, page_id=page_id,
                                  include_instagram=True, graph=graph, cipher=cipher)


async def test_reconnecting_a_page_through_the_picker_updates_it(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    page_id = meta.page("a", "Berlin Solar")
    await set_current_tenant(db_session, seed.tenant_a.id)
    old = await service.connect(db_session, seed.tenant_a.id,
                                ConnectionInput(provider=Channel.MESSENGER, external_id=page_id, access_token="OLD"),
                                cipher=cipher)
    await service.mark_needs_reauth(db_session, seed.tenant_a.id, old.id, "revoked")

    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    [again] = await picker.connect_page(db_session, seed.tenant_a.id, opened.id, page_id=page_id,
                                        include_instagram=True, graph=graph, cipher=cipher)
    assert again.id == old.id
    assert again.status is ConnectionStatus.ACTIVE


# --- The session's lifetime ---------------------------------------------------


async def test_an_expired_session_is_refused(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    opened.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(picker.SessionExpired):
        await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)


async def test_closing_destroys_the_user_token(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    await picker.close(db_session, seed.tenant_a.id, opened.id)

    stored = (await db_session.execute(
        text("SELECT user_token_encrypted FROM channel_picker_sessions WHERE id = :id"), {"id": opened.id}
    )).scalar_one()
    assert bytes(stored) == b"\x00"
    with pytest.raises(picker.SessionExpired):
        await picker.list_pages(db_session, seed.tenant_a.id, opened.id, graph=graph, cipher=cipher)


async def test_another_business_cannot_use_our_session(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.page("a", "Berlin Solar")
    await set_current_tenant(db_session, seed.tenant_a.id)
    opened = await signed_in(db_session, seed.tenant_a.id, graph, cipher)

    # Even with the session id, and even with RLS still set to A, B gets nothing.
    with pytest.raises(picker.SessionExpired):
        await picker.list_pages(db_session, seed.tenant_b.id, opened.id, graph=graph, cipher=cipher)


async def test_expired_sessions_are_cleared_out(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    stale = await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    await signed_in(db_session, seed.tenant_a.id, graph, cipher)
    stale.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()
    assert await picker.purge_expired(db_session, seed.tenant_a.id) == 1


# --- Through the API ----------------------------------------------------------


@pytest.fixture
def api_graph(graph: MetaGraph):  # type: ignore[no-untyped-def]
    from rivon.main import app

    app.dependency_overrides[get_graph] = lambda: graph
    yield graph
    app.dependency_overrides.pop(get_graph, None)


async def api_sign_in(client: AsyncClient, tenant: TenantUsers) -> str:
    started = await client.post("/channels/v2/connect", headers=tenant.owner)
    assert started.status_code == 200, started.text
    done = await client.post(
        "/channels/v2/callback",
        json={"code": "a-code", "state": state_from(started.json()["authorize_url"])},
        headers=tenant.owner,
    )
    assert done.status_code == 200, done.text
    return done.json()["session_id"]


async def test_the_whole_round_trip_through_the_api(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeMeta
) -> None:
    session_id = await api_sign_in(client, tenant)

    empty = await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=tenant.owner)
    assert empty.status_code == 200
    assert empty.json()["pages"] == []
    assert empty.json()["create_page_url"] == "https://www.facebook.com/pages/create"

    page_id = meta.page("new", "Tehman Testing", instagram=True)
    listed = await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=tenant.owner)
    [page] = listed.json()["pages"]
    assert page["id"] == page_id and page["messenger_status"] == "available"

    connected = await client.post(
        f"/channels/v2/sessions/{session_id}/connect",
        json={"page_id": page_id, "include_instagram": True}, headers=tenant.owner,
    )
    assert connected.status_code == 200, connected.text
    assert {c["provider"] for c in connected.json()} == {"messenger", "instagram"}

    relisted = await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=tenant.owner)
    assert relisted.json()["pages"][0]["messenger_status"] == "connected"

    assert (await client.delete(f"/channels/v2/sessions/{session_id}", headers=tenant.owner)).status_code == 204
    gone = await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=tenant.owner)
    assert gone.status_code == 410


async def test_no_token_ever_reaches_the_browser(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeMeta
) -> None:
    meta.page("a", "Berlin Solar", instagram=True)
    session_id = await api_sign_in(client, tenant)
    listed = await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=tenant.owner)
    for secret in ("LONG-USER-TOKEN", "SHORT-USER-TOKEN", "PAGE-TOKEN", "test-app-secret"):
        assert secret not in listed.text


async def test_only_the_owner_uses_the_picker(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    session_id = await api_sign_in(client, tenant)
    for headers in (tenant.manager, tenant.agent):
        assert (await client.post("/channels/v2/connect", headers=headers)).status_code == 403
        assert (await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=headers)).status_code == 403
        assert (await client.post(f"/channels/v2/sessions/{session_id}/connect",
                                  json={"page_id": "x"}, headers=headers)).status_code == 403


async def test_another_business_gets_nothing_from_our_session_over_http(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    session_id = await api_sign_in(client, tenant)
    response = await client.get(f"/channels/v2/sessions/{session_id}/pages", headers=other_tenant.owner)
    assert response.status_code == 410


async def test_the_old_flow_is_untouched(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    # The beta must not change what the current Connect buttons do.
    started = await client.post("/channels/connect/messenger", headers=tenant.owner)
    assert "config_id=test-config-pages&" in started.json()["authorize_url"]
    assert "connect%2Fmeta%2Fcallback" in started.json()["authorize_url"]
