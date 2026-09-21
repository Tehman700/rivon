"""CHN-13: the self-serve connect flow for Pages and Instagram.

Everything here runs against a fake Graph — no network, no Meta app, no app
secret. That is the point of keeping the HTTP call injectable: this flow is the
part a customer sees first, so it has to be testable long before Meta approves
anything.

The cases that get the most attention are the ones that look like success and
are not: a Page that was never subscribed (connected, and silently receives
nothing), a permission the customer quietly unticked, and a Page some other
business has already claimed.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.channels import oauth, service
from rivon.channels.api import get_graph
from rivon.channels.crypto import TokenCipher
from rivon.channels.messages import Channel
from rivon.channels.meta import MetaGraph
from rivon.channels.models import ConnectionStatus
from rivon.channels.service import OAuthStateInvalid
from rivon.platform.tenancy import set_current_tenant
from tests.conftest import Seed, TenantUsers

PAGE_SCOPES = ["pages_show_list", "pages_messaging", "pages_manage_metadata", "business_management"]
INSTAGRAM_SCOPES = ["instagram_basic", "instagram_manage_messages"]
REDIRECT = "https://app.example/connect/meta/callback"


class FakeMeta:
    """Meta's Graph API, in memory: canned answers plus a record of what we asked."""

    def __init__(self) -> None:
        # Unique per instance: external ids are unique across every tenant, and
        # the API tests all share one committed database.
        mark = uuid.uuid4().hex[:8]
        self.page_id = f"page-{mark}"
        self.instagram_id = f"ig-{mark}"
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.scopes: list[str] = PAGE_SCOPES + INSTAGRAM_SCOPES
        self.token_is_valid = True
        self.pages: list[dict[str, Any]] = [
            {
                "id": self.page_id,
                "name": "Berlin Solar",
                "access_token": "PAGE-TOKEN-1",
                "instagram_business_account": {"id": self.instagram_id, "username": "berlinsolar"},
            }
        ]
        self.subscribed: set[str] = set()
        self.unsubscribed: set[str] = set()
        self.subscribe_fails_for: set[str] = set()

    async def __call__(
        self, method: str, url: str, params: dict[str, Any], data: dict[str, Any] | None
    ) -> dict[str, Any]:
        path = url.split("/v25.0/", 1)[1]
        self.calls.append((method, path, {**params, **(data or {})}))

        if path == "oauth/access_token":
            return {"access_token": "BUSINESS-TOKEN", "token_type": "bearer", "expires_in": 0}
        if path == "debug_token":
            return {
                "data": {
                    "scopes": list(self.scopes),
                    "expires_at": 0,
                    "is_valid": self.token_is_valid,
                }
            }
        if path == "me/accounts":
            return {"data": list(self.pages)}
        if path.endswith("/subscribed_apps"):
            page_id = path.split("/", 1)[0]
            if method == "DELETE":
                self.unsubscribed.add(page_id)
                return {"success": True}
            if page_id in self.subscribe_fails_for:
                return {"error": {"message": "Page is restricted", "code": 200}}
            self.subscribed.add(page_id)
            return {"success": True}
        raise AssertionError(f"the fake Graph was asked for something unexpected: {path}")

    @property
    def paths_called(self) -> list[str]:
        return [path for _, path, _ in self.calls]


@pytest.fixture
def meta() -> FakeMeta:
    return FakeMeta()


@pytest.fixture
def graph(meta: FakeMeta) -> MetaGraph:
    return MetaGraph("test-app-id", "test-app-secret", transport=meta)


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(TokenCipher.generate_key())


async def begin(session: AsyncSession, tenant_id: uuid.UUID, graph: MetaGraph) -> str:
    return await oauth.begin_page_connection(
        session, tenant_id, Channel.MESSENGER, graph=graph,
        config_id="test-config-pages", redirect_uri=REDIRECT,
    )


def state_from(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)["state"][0]


async def run_flow(
    session: AsyncSession, tenant_id: uuid.UUID, graph: MetaGraph, cipher: TokenCipher
) -> oauth.ConnectOutcome:
    url = await begin(session, tenant_id, graph)
    return await oauth.complete_page_connection(
        session, tenant_id, code="a-code", state=state_from(url), graph=graph,
        redirect_uri=REDIRECT, cipher=cipher,
    )


# --- Starting -----------------------------------------------------------------


async def test_the_dialog_url_asks_for_a_code_not_a_token(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    url = await begin(db_session, seed.tenant_a.id, graph)

    assert url.startswith("https://www.facebook.com/v25.0/dialog/oauth?")
    assert "config_id=test-config-pages" in url
    assert "response_type=code" in url
    assert "override_default_response_type=true" in url, (
        "without this Meta returns a token in the browser and the secret exchange is skipped"
    )
    assert "test-app-secret" not in url


async def test_each_attempt_gets_its_own_state(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    first = state_from(await begin(db_session, seed.tenant_a.id, graph))
    second = state_from(await begin(db_session, seed.tenant_a.id, graph))
    assert first != second


async def test_whatsapp_does_not_use_this_flow(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(oauth.ConnectFailed):
        await oauth.begin_page_connection(
            db_session, seed.tenant_a.id, Channel.WHATSAPP, graph=graph,
            config_id="c", redirect_uri=REDIRECT,
        )


# --- Completing ---------------------------------------------------------------


async def test_a_completed_flow_connects_the_page_and_its_instagram(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert {(c.provider, c.external_id) for c in outcome.connected} == {
        (Channel.MESSENGER, meta.page_id),
        (Channel.INSTAGRAM, meta.instagram_id),
    }
    assert outcome.skipped == ()

    messenger = next(c for c in outcome.connected if c.provider is Channel.MESSENGER)
    instagram = next(c for c in outcome.connected if c.provider is Channel.INSTAGRAM)
    assert messenger.display_name == "Berlin Solar"
    assert instagram.display_name == "berlinsolar"
    assert instagram.parent_external_id == meta.page_id, "Instagram hangs off its Page"
    assert messenger.expires_at is None, "a business token does not expire"

    # Both are usable, and both carry the Page's own token — not the business one.
    for connection in (messenger, instagram):
        token = await service.access_token_for(
            db_session, seed.tenant_a.id, connection.id, cipher=cipher
        )
        assert token == "PAGE-TOKEN-1"


async def test_the_page_is_subscribed_before_it_is_stored(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    """An unsubscribed Page looks connected and receives nothing."""
    await set_current_tenant(db_session, seed.tenant_a.id)
    await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert meta.subscribed == {meta.page_id}
    subscribe = next(call for call in meta.calls if call[1] == f"{meta.page_id}/subscribed_apps")
    assert subscribe[2]["subscribed_fields"] == "messages,messaging_postbacks"
    assert subscribe[2]["access_token"] == "PAGE-TOKEN-1"


async def test_the_code_is_exchanged_server_side(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    exchange = next(call for call in meta.calls if call[1] == "oauth/access_token")
    assert exchange[2]["client_secret"] == "test-app-secret"
    assert exchange[2]["redirect_uri"] == REDIRECT, "must match the App Dashboard exactly"
    assert meta.paths_called[0] == "oauth/access_token", "nothing happens before the exchange"


async def test_routing_works_the_moment_a_page_is_connected(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert await service.route_to_tenant(db_session, Channel.MESSENGER, meta.page_id) == seed.tenant_a.id
    assert await service.route_to_tenant(db_session, Channel.INSTAGRAM, meta.instagram_id) == seed.tenant_a.id


# --- When the customer grants less than we need -------------------------------


async def test_a_missing_page_permission_stops_the_whole_flow(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    # Unticking this one is the classic: everything looks fine and no message
    # ever arrives, because the Page can never be subscribed.
    meta.scopes = [s for s in meta.scopes if s != "pages_manage_metadata"]
    await set_current_tenant(db_session, seed.tenant_a.id)

    with pytest.raises(oauth.PermissionsDeclined) as caught:
        await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert caught.value.missing == ("pages_manage_metadata",)
    assert await service.list_connections(db_session, seed.tenant_a.id) == []


async def test_instagram_is_left_out_when_its_permissions_were_not_granted(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.scopes = list(PAGE_SCOPES)
    await set_current_tenant(db_session, seed.tenant_a.id)

    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert [c.provider for c in outcome.connected] == [Channel.MESSENGER]
    assert outcome.skipped == (("berlinsolar", "Instagram message access was not granted"),)


async def test_no_page_shared_is_explained_not_swallowed(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.pages = []
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(oauth.NothingGranted):
        await run_flow(db_session, seed.tenant_a.id, graph, cipher)


async def test_a_token_meta_calls_invalid_is_refused(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.token_is_valid = False
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(oauth.ConnectFailed):
        await run_flow(db_session, seed.tenant_a.id, graph, cipher)
    assert await service.list_connections(db_session, seed.tenant_a.id) == []


async def test_a_page_without_its_own_token_is_ignored(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    # We could neither subscribe it nor reply on it, so storing it would create
    # a connection that does nothing.
    meta.pages = [{"id": f"{meta.page_id}-b", "name": "No Token", "access_token": ""}, *meta.pages]
    await set_current_tenant(db_session, seed.tenant_a.id)

    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)
    assert {c.external_id for c in outcome.connected} == {meta.page_id, meta.instagram_id}


async def test_a_page_meta_will_not_subscribe_is_reported_not_stored(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    meta.pages = [
        {"id": f"{meta.page_id}-bad", "name": "Restricted", "access_token": "PAGE-TOKEN-2"},
        *meta.pages,
    ]
    meta.subscribe_fails_for = {f"{meta.page_id}-bad"}
    await set_current_tenant(db_session, seed.tenant_a.id)

    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert {c.external_id for c in outcome.connected} == {meta.page_id, meta.instagram_id}
    assert any("Restricted" == account for account, _ in outcome.skipped)
    assert await service.route_to_tenant(db_session, Channel.MESSENGER, f"{meta.page_id}-bad") is None


async def test_a_page_another_business_already_has_is_skipped_not_stolen(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_b.id)
    await run_flow(db_session, seed.tenant_b.id, graph, cipher)

    meta.pages = [
        {"id": f"{meta.page_id}-b", "name": "Second Page", "access_token": "PAGE-TOKEN-2"},
        *meta.pages,
    ]
    await set_current_tenant(db_session, seed.tenant_a.id)
    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    # The contested Page stays with B; the rest of A's connect still succeeds.
    assert {c.external_id for c in outcome.connected} == {f"{meta.page_id}-b"}
    assert ("Berlin Solar", "already connected to another business") in outcome.skipped
    assert await service.route_to_tenant(db_session, Channel.MESSENGER, meta.page_id) == seed.tenant_b.id


# --- The state ----------------------------------------------------------------


async def test_a_callback_cannot_be_replayed(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    url = await begin(db_session, seed.tenant_a.id, graph)
    state = state_from(url)

    await oauth.complete_page_connection(
        db_session, seed.tenant_a.id, code="a-code", state=state, graph=graph,
        redirect_uri=REDIRECT, cipher=cipher,
    )
    with pytest.raises(OAuthStateInvalid):
        await oauth.complete_page_connection(
            db_session, seed.tenant_a.id, code="a-code", state=state, graph=graph,
            redirect_uri=REDIRECT, cipher=cipher,
        )


async def test_nothing_is_asked_of_meta_before_the_state_is_checked(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    # A forged callback must cost us nothing: no code exchange, no Graph call.
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(OAuthStateInvalid):
        await oauth.complete_page_connection(
            db_session, seed.tenant_a.id, code="a-code", state="x" * 40, graph=graph,
            redirect_uri=REDIRECT, cipher=cipher,
        )
    assert meta.calls == []


# --- Disconnecting ------------------------------------------------------------


async def test_disconnecting_the_last_thing_on_a_page_unsubscribes_it(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)
    messenger = next(c for c in outcome.connected if c.provider is Channel.MESSENGER)
    instagram = next(c for c in outcome.connected if c.provider is Channel.INSTAGRAM)

    # Instagram shares the Page's subscription, so the Page stays subscribed.
    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, messenger.id, graph=graph, cipher=cipher
    )
    assert meta.unsubscribed == set(), "unsubscribing now would break Instagram"

    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, instagram.id, graph=graph, cipher=cipher
    )
    assert meta.unsubscribed == {meta.page_id}


async def test_disconnecting_stops_routing_and_destroys_the_token(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)
    messenger = next(c for c in outcome.connected if c.provider is Channel.MESSENGER)

    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, messenger.id, graph=graph, cipher=cipher
    )

    assert messenger.status is ConnectionStatus.REVOKED
    assert await service.route_to_tenant(db_session, Channel.MESSENGER, meta.page_id) is None


async def test_reconnecting_after_a_disconnect_works(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeMeta, cipher: TokenCipher
) -> None:
    # A revoked row still holds the Page's id, so the unique constraint must not
    # lock the customer out of ever reconnecting.
    await set_current_tenant(db_session, seed.tenant_a.id)
    outcome = await run_flow(db_session, seed.tenant_a.id, graph, cipher)
    messenger = next(c for c in outcome.connected if c.provider is Channel.MESSENGER)
    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, messenger.id, graph=graph, cipher=cipher
    )

    again = await run_flow(db_session, seed.tenant_a.id, graph, cipher)

    assert {c.external_id for c in again.connected} == {meta.page_id, meta.instagram_id}
    assert await service.route_to_tenant(db_session, Channel.MESSENGER, meta.page_id) == seed.tenant_a.id


# --- Through the API ----------------------------------------------------------


@pytest.fixture
def api_graph(graph: MetaGraph):  # type: ignore[no-untyped-def]
    """Point the running app at the fake Graph for the duration of a test."""
    from rivon.main import app

    app.dependency_overrides[get_graph] = lambda: graph
    yield graph
    app.dependency_overrides.pop(get_graph, None)


async def test_connect_and_list_through_the_api(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeMeta
) -> None:
    started = await client.post("/channels/connect/messenger", headers=tenant.owner)
    assert started.status_code == 200
    url = started.json()["authorize_url"]

    done = await client.post(
        "/channels/callback", json={"code": "a-code", "state": state_from(url)},
        headers=tenant.owner,
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert {c["provider"] for c in body["connected"]} == {"messenger", "instagram"}

    listed = await client.get("/channels", headers=tenant.agent)
    assert {c["external_id"] for c in listed.json()} == {meta.page_id, meta.instagram_id}
    assert all(c["status"] == "active" for c in listed.json())


async def test_the_api_never_returns_a_token(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    started = await client.post("/channels/connect/messenger", headers=tenant.owner)
    url = started.json()["authorize_url"]
    done = await client.post(
        "/channels/callback", json={"code": "a-code", "state": state_from(url)},
        headers=tenant.owner,
    )
    listed = await client.get("/channels", headers=tenant.owner)

    for text_body in (done.text, listed.text, url):
        assert "PAGE-TOKEN-1" not in text_body
        assert "BUSINESS-TOKEN" not in text_body
        assert "test-app-secret" not in text_body


async def test_only_the_owner_connects_or_disconnects(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    for headers in (tenant.manager, tenant.agent):
        assert (await client.post("/channels/connect/messenger", headers=headers)).status_code == 403
        assert (
            await client.post(
                "/channels/callback", json={"code": "c", "state": "s" * 40}, headers=headers
            )
        ).status_code == 403
        assert (
            await client.delete(f"/channels/{uuid.uuid4()}", headers=headers)
        ).status_code == 403
        # Everyone can see what is connected.
        assert (await client.get("/channels", headers=headers)).status_code == 200


async def test_signed_out_requests_are_refused(client: AsyncClient) -> None:
    assert (await client.get("/channels")).status_code == 401
    assert (await client.post("/channels/connect/messenger")).status_code == 401


async def test_whatsapp_is_refused_by_the_page_endpoint(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    response = await client.post("/channels/connect/whatsapp", headers=tenant.owner)
    assert response.status_code == 400
    assert "not connected this way" in response.json()["detail"]


async def test_an_unknown_provider_is_rejected(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    assert (await client.post("/channels/connect/telegram", headers=tenant.owner)).status_code == 422


async def test_a_bad_callback_explains_itself(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    response = await client.post(
        "/channels/callback", json={"code": "a-code", "state": "n" * 40}, headers=tenant.owner
    )
    assert response.status_code == 400
    assert "could not be completed" in response.json()["detail"]


async def test_disconnecting_through_the_api(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeMeta
) -> None:
    started = await client.post("/channels/connect/messenger", headers=tenant.owner)
    await client.post(
        "/channels/callback",
        json={"code": "a-code", "state": state_from(started.json()["authorize_url"])},
        headers=tenant.owner,
    )
    listed = (await client.get("/channels", headers=tenant.owner)).json()

    for connection in listed:
        assert (
            await client.delete(f"/channels/{connection['id']}", headers=tenant.owner)
        ).status_code == 204

    assert (await client.get("/channels", headers=tenant.owner)).json() == []
    assert meta.unsubscribed == {meta.page_id}


async def test_disconnecting_something_that_is_not_ours(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph
) -> None:
    response = await client.delete(f"/channels/{uuid.uuid4()}", headers=tenant.owner)
    assert response.status_code == 404
