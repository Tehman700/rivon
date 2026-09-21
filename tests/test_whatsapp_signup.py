"""CHN-13: WhatsApp Embedded Signup.

A different shape from the Page flow, because Meta creates the customer's
WhatsApp account during the dialog rather than handing us one they already had.

Two things follow from that and are tested hardest. The account ids arrive
through a browser event rather than the redirect, so the request carries them
and nothing can recover them if they are lost. And the code lives thirty
seconds, so the exchange happens first, before anything that could be retried.

The rest is the same lesson as everywhere else in this module: an account that
was never subscribed looks perfectly connected and receives nothing.
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
from rivon.platform.tenancy import set_current_tenant
from tests.conftest import Seed, TenantUsers

WHATSAPP_SCOPES = ["whatsapp_business_messaging", "whatsapp_business_management"]


class FakeWhatsApp:
    """Meta's Graph API for the WhatsApp half."""

    def __init__(self) -> None:
        mark = uuid.uuid4().hex[:8]
        self.waba_id = f"waba-{mark}"
        self.phone_number_id = f"pn-{mark}"
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.scopes: list[str] = list(WHATSAPP_SCOPES)
        self.token_is_valid = True
        self.subscribed: set[str] = set()
        self.unsubscribed: set[str] = set()
        self.registered_with: str | None = None
        self.existing_pin: str | None = None
        self.subscribe_fails = False
        #: Meta can also refuse plainly, with no error object at all.
        self.subscribe_returns_false = False

    async def __call__(
        self, method: str, url: str, params: dict[str, Any], data: dict[str, Any] | None
    ) -> dict[str, Any]:
        path = url.split("/v25.0/", 1)[1]
        body = {**params, **(data or {})}
        self.calls.append((method, path, body))

        if path == "oauth/access_token":
            return {"access_token": "WABA-TOKEN", "token_type": "bearer", "expires_in": 0}
        if path == "debug_token":
            return {"data": {"scopes": list(self.scopes), "expires_at": 0,
                             "is_valid": self.token_is_valid}}
        if path.endswith("/subscribed_apps"):
            target = path.split("/", 1)[0]
            if method == "DELETE":
                self.unsubscribed.add(target)
                return {"success": True}
            if self.subscribe_fails:
                return {"error": {"message": "Cannot subscribe", "code": 200}}
            if self.subscribe_returns_false:
                return {"success": False}
            self.subscribed.add(target)
            return {"success": True}
        if path.endswith("/register"):
            if self.existing_pin and body.get("pin") != self.existing_pin:
                return {"error": {"message": "Incorrect PIN", "code": 133005}}
            self.registered_with = body.get("pin")
            return {"success": True}
        if path == self.phone_number_id:
            return {"display_phone_number": "+49 30 1234567", "verified_name": "Berlin Solar",
                    "quality_rating": "GREEN"}
        raise AssertionError(f"unexpected Graph path: {path}")

    @property
    def paths_called(self) -> list[str]:
        return [path for _, path, _ in self.calls]


@pytest.fixture
def meta() -> FakeWhatsApp:
    return FakeWhatsApp()


@pytest.fixture
def graph(meta: FakeWhatsApp) -> MetaGraph:
    return MetaGraph("test-app-id", "test-app-secret", transport=meta)


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(TokenCipher.generate_key())


async def signup(
    session: AsyncSession, tenant_id: uuid.UUID, graph: MetaGraph, meta: FakeWhatsApp,
    cipher: TokenCipher, *, pin: str | None = None,
) -> oauth.WhatsAppConnected:
    return await oauth.complete_whatsapp_signup(
        session, tenant_id, code="a-code", waba_id=meta.waba_id,
        phone_number_id=meta.phone_number_id, graph=graph, pin=pin, cipher=cipher,
    )


# --- The happy path -----------------------------------------------------------


async def test_a_completed_signup_connects_the_number(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    result = await signup(db_session, seed.tenant_a.id, graph, meta, cipher)

    connection = result.connection
    assert connection.provider is Channel.WHATSAPP
    assert connection.external_id == meta.phone_number_id, "routing is by number, not account"
    assert connection.parent_external_id == meta.waba_id
    assert connection.display_name == "Berlin Solar"
    assert connection.provider_metadata["display_phone_number"] == "+49 30 1234567"
    assert connection.status is ConnectionStatus.ACTIVE


async def test_the_code_is_exchanged_before_anything_else(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    # It lives thirty seconds. Anything done first is a chance to lose it.
    await set_current_tenant(db_session, seed.tenant_a.id)
    await signup(db_session, seed.tenant_a.id, graph, meta, cipher)
    assert meta.paths_called[0] == "oauth/access_token"


async def test_the_account_is_subscribed_and_the_number_registered(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    await signup(db_session, seed.tenant_a.id, graph, meta, cipher)

    assert meta.subscribed == {meta.waba_id}, "an unsubscribed account receives nothing"
    assert meta.registered_with is not None
    assert meta.paths_called.index(f"{meta.waba_id}/subscribed_apps") < meta.paths_called.index(
        f"{meta.phone_number_id}/register"
    ), "subscribe before registering"


async def test_routing_works_as_soon_as_the_number_is_connected(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    await signup(db_session, seed.tenant_a.id, graph, meta, cipher)
    assert await service.route_to_tenant(
        db_session, Channel.WHATSAPP, meta.phone_number_id
    ) == seed.tenant_a.id


# --- The PIN ------------------------------------------------------------------


async def test_a_new_number_gets_a_pin_we_hand_back_once(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    result = await signup(db_session, seed.tenant_a.id, graph, meta, cipher)

    assert result.registration_pin is not None
    assert len(result.registration_pin) == 6 and result.registration_pin.isdigit()
    assert meta.registered_with == result.registration_pin
    # It is the customer's PIN, not ours: nothing about it is stored.
    stored = str(result.connection.provider_metadata)
    assert result.registration_pin not in stored


async def test_a_pin_the_customer_supplies_is_used_and_not_echoed(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    meta.existing_pin = "246810"
    await set_current_tenant(db_session, seed.tenant_a.id)

    result = await signup(db_session, seed.tenant_a.id, graph, meta, cipher, pin="246810")

    assert meta.registered_with == "246810"
    assert result.registration_pin is None, "we never hand back something they already knew"


async def test_the_wrong_pin_asks_for_the_right_one(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    # Only the customer knows an existing PIN, so the message has to ask for it
    # rather than reporting a failure they cannot act on.
    meta.existing_pin = "246810"
    await set_current_tenant(db_session, seed.tenant_a.id)

    with pytest.raises(oauth.RegistrationPinWrong) as caught:
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher, pin="111111")
    assert "existing PIN" in str(caught.value)
    assert await service.list_connections(db_session, seed.tenant_a.id) == []


@pytest.mark.parametrize("pin", ["12345", "1234567", "abcdef", ""])
async def test_a_pin_that_is_not_six_digits_is_refused(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp,
    cipher: TokenCipher, pin: str,
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(ValueError):
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher, pin=pin)


def test_generated_pins_are_six_digits_and_not_all_the_same() -> None:
    pins = {oauth.generate_registration_pin() for _ in range(50)}
    assert all(len(p) == 6 and p.isdigit() for p in pins)
    assert len(pins) > 1


# --- When it goes wrong -------------------------------------------------------


async def test_missing_whatsapp_permissions_stop_the_signup(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    meta.scopes = ["whatsapp_business_messaging"]
    await set_current_tenant(db_session, seed.tenant_a.id)

    with pytest.raises(oauth.PermissionsDeclined) as caught:
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher)

    assert caught.value.missing == ("whatsapp_business_management",)
    assert meta.registered_with is None, "nothing is touched once we know it cannot work"


async def test_a_number_is_not_stored_if_it_could_not_be_subscribed(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    meta.subscribe_fails = True
    await set_current_tenant(db_session, seed.tenant_a.id)

    with pytest.raises(Exception):
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher)
    assert await service.list_connections(db_session, seed.tenant_a.id) == []


async def test_a_plain_refusal_to_subscribe_is_not_mistaken_for_success(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    # Meta does not always send an error object; sometimes it just says the
    # request did not succeed. Reading that as success would store a number
    # that looks connected and receives nothing.
    meta.subscribe_returns_false = True
    await set_current_tenant(db_session, seed.tenant_a.id)

    with pytest.raises(Exception):
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher)
    assert await service.list_connections(db_session, seed.tenant_a.id) == []


async def test_a_token_meta_calls_invalid_is_refused(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    meta.token_is_valid = False
    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(oauth.ConnectFailed):
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher)


async def test_a_number_another_business_has_cannot_be_taken(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_b.id)
    await signup(db_session, seed.tenant_b.id, graph, meta, cipher)

    await set_current_tenant(db_session, seed.tenant_a.id)
    with pytest.raises(service.AlreadyConnectedElsewhere):
        await signup(db_session, seed.tenant_a.id, graph, meta, cipher)

    assert await service.route_to_tenant(
        db_session, Channel.WHATSAPP, meta.phone_number_id
    ) == seed.tenant_b.id


# --- Disconnecting ------------------------------------------------------------


async def test_the_account_is_unsubscribed_once_the_last_number_goes(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    first = (await signup(db_session, seed.tenant_a.id, graph, meta, cipher)).connection

    # A second number on the same WhatsApp account.
    second_id = f"{meta.phone_number_id}-b"
    second = await service.connect(
        db_session, seed.tenant_a.id,
        service.ConnectionInput(
            provider=Channel.WHATSAPP, external_id=second_id, access_token="WABA-TOKEN",
            parent_external_id=meta.waba_id,
        ),
        cipher=cipher,
    )

    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, first.id, graph=graph, cipher=cipher
    )
    assert meta.unsubscribed == set(), "the other number still needs the account"

    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, second.id, graph=graph, cipher=cipher
    )
    assert meta.unsubscribed == {meta.waba_id}


async def test_disconnecting_stops_routing(
    db_session: AsyncSession, seed: Seed, graph: MetaGraph, meta: FakeWhatsApp, cipher: TokenCipher
) -> None:
    await set_current_tenant(db_session, seed.tenant_a.id)
    connection = (await signup(db_session, seed.tenant_a.id, graph, meta, cipher)).connection

    await oauth.disconnect_and_unsubscribe(
        db_session, seed.tenant_a.id, connection.id, graph=graph, cipher=cipher
    )
    assert await service.route_to_tenant(db_session, Channel.WHATSAPP, meta.phone_number_id) is None


# --- Through the API ----------------------------------------------------------


@pytest.fixture
def api_graph(graph: MetaGraph):  # type: ignore[no-untyped-def]
    from rivon.main import app

    app.dependency_overrides[get_graph] = lambda: graph
    yield graph
    app.dependency_overrides.pop(get_graph, None)


async def test_signing_up_through_the_api(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeWhatsApp
) -> None:
    response = await client.post(
        "/channels/whatsapp/complete",
        json={"code": "a-code", "waba_id": meta.waba_id,
              "phone_number_id": meta.phone_number_id},
        headers=tenant.owner,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["connection"]["provider"] == "whatsapp"
    assert body["connection"]["display_name"] == "Berlin Solar"
    assert len(body["registration_pin"]) == 6

    listed = await client.get("/channels", headers=tenant.owner)
    assert meta.phone_number_id in {c["external_id"] for c in listed.json()}


async def test_the_api_never_returns_the_token(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeWhatsApp
) -> None:
    response = await client.post(
        "/channels/whatsapp/complete",
        json={"code": "a-code", "waba_id": meta.waba_id,
              "phone_number_id": meta.phone_number_id},
        headers=tenant.owner,
    )
    assert "WABA-TOKEN" not in response.text
    assert "test-app-secret" not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"code": "a-code", "waba_id": "w-1"},
        {"code": "a-code", "waba_id": "w-1", "phone_number_id": "p-1", "pin": "12345"},
        {"code": "", "waba_id": "w-1", "phone_number_id": "p-1"},
        {"code": "a-code", "waba_id": "w-1", "phone_number_id": "p-1", "unexpected": 1},
    ],
)
async def test_an_incomplete_signup_is_rejected(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, body: dict
) -> None:
    # Losing waba_id or phone_number_id is the classic Embedded Signup mistake:
    # they only arrive via a browser event, and nothing can recover them.
    response = await client.post("/channels/whatsapp/complete", json=body, headers=tenant.owner)
    assert response.status_code == 422


async def test_only_the_owner_can_finish_a_signup(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeWhatsApp
) -> None:
    for headers in (tenant.manager, tenant.agent):
        response = await client.post(
            "/channels/whatsapp/complete",
            json={"code": "a-code", "waba_id": meta.waba_id,
                  "phone_number_id": meta.phone_number_id},
            headers=headers,
        )
        assert response.status_code == 403


async def test_a_wrong_pin_is_explained_through_the_api(
    client: AsyncClient, tenant: TenantUsers, api_graph: MetaGraph, meta: FakeWhatsApp
) -> None:
    meta.existing_pin = "246810"
    response = await client.post(
        "/channels/whatsapp/complete",
        json={"code": "a-code", "waba_id": meta.waba_id,
              "phone_number_id": meta.phone_number_id, "pin": "111111"},
        headers=tenant.owner,
    )
    assert response.status_code == 400
    assert "existing PIN" in response.json()["detail"]
