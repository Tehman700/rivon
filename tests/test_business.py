"""BIZ-01 business profile and BIZ-02 services catalogue."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.platform.tenancy import tenant_transaction
from tests.conftest import TenantUsers

PROFILE: dict[str, Any] = {
    "name": "Sonnenkraft Solar GmbH",
    "assistant_name": "Mia",
    "contact_email": "info@sonnenkraft.example",
    "contact_phone": "+49 30 1234567",
    "website": "https://sonnenkraft.example",
    "address_line": "Solarweg 1",
    "city": "Berlin",
    "postal_code": "10115",
    "country": "de",
    "timezone": "Europe/Berlin",
    "business_hours": {
        "monday": [{"opens": "13:00", "closes": "17:00"}, {"opens": "08:00", "closes": "12:00"}],
        "saturday": [{"opens": "09:00", "closes": "13:00"}],
    },
    "min_project_size": "3",
    "max_project_size": "30.5",
    "project_size_unit": "kWp",
    "min_project_value_eur": "5000",
    "max_project_value_eur": "60000",
}


async def _put_profile(client: AsyncClient, headers: dict[str, str], **changes: Any):  # type: ignore[no-untyped-def]
    return await client.put("/business/profile", json={**PROFILE, **changes}, headers=headers)


# --- Profile ------------------------------------------------------------------


async def test_profile_is_404_until_set_up(client: AsyncClient, tenant: TenantUsers) -> None:
    response = await client.get("/business/profile", headers=tenant.owner)
    assert response.status_code == 404


async def test_owner_sets_up_and_reads_the_profile(client: AsyncClient, tenant: TenantUsers) -> None:
    response = await _put_profile(client, tenant.owner)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["name"] == "Sonnenkraft Solar GmbH"
    assert body["assistant_name"] == "Mia"
    assert body["country"] == "DE"  # normalised
    # Periods come back sorted; unspecified days are closed.
    assert body["business_hours"]["monday"] == [
        {"opens": "08:00", "closes": "12:00"},
        {"opens": "13:00", "closes": "17:00"},
    ]
    assert body["business_hours"]["sunday"] == []
    # Money and sizes are exact decimals, not floats.
    assert Decimal(body["max_project_size"]) == Decimal("30.5")
    assert Decimal(body["min_project_value_eur"]) == Decimal("5000")
    assert isinstance(body["max_project_value_eur"], str)

    read_back = await client.get("/business/profile", headers=tenant.owner)
    assert read_back.status_code == 200
    assert read_back.json() == body


async def test_put_replaces_the_whole_profile(client: AsyncClient, tenant: TenantUsers) -> None:
    await _put_profile(client, tenant.owner)
    minimal = {"name": "Renamed Solar", "timezone": "Europe/Madrid"}
    response = await client.put("/business/profile", json=minimal, headers=tenant.owner)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Solar"
    assert body["assistant_name"] == "Rivon"  # default restored
    assert body["contact_email"] is None
    assert body["min_project_size"] is None
    assert body["business_hours"]["monday"] == []


async def test_manager_and_agent_can_read_but_not_edit_the_profile(
    client: AsyncClient, tenant: TenantUsers
) -> None:
    await _put_profile(client, tenant.owner)
    for headers in (tenant.manager, tenant.agent):
        assert (await _put_profile(client, headers, name="Hijacked")).status_code == 403
        read = await client.get("/business/profile", headers=headers)
        assert read.status_code == 200
        assert read.json()["name"] == PROFILE["name"]


async def test_profile_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/business/profile")).status_code == 401
    assert (await client.put("/business/profile", json=PROFILE)).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"name": "x" * 201},
        {"timezone": "Mars/Olympus"},
        {"timezone": "../../etc/passwd"},
        {"country": "Germany"},
        {"contact_email": "not-an-email"},
        {"contact_phone": "call me"},
        {"website": "sonnenkraft.example"},
        {"min_project_size": "0"},
        {"min_project_size": "-5"},
        {"min_project_size": "40", "max_project_size": "30"},
        {"project_size_unit": None},
        {"project_size_unit": "gallons"},
        {"min_project_value_eur": "70000", "max_project_value_eur": "60000"},
        {"min_project_value_eur": "1.234"},
        {"business_hours": {"monday": [{"opens": "17:00", "closes": "08:00"}]}},
        {"business_hours": {"monday": [{"opens": "08:00", "closes": "12:00"},
                                       {"opens": "11:00", "closes": "15:00"}]}},
        {"business_hours": {"monday": [{"opens": "8am", "closes": "5pm"}]}},
        {"business_hours": {"funday": []}},
        {"unexpected_field": 1},
    ],
)
async def test_invalid_profiles_are_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    response = await _put_profile(client, tenant.owner, **changes)
    assert response.status_code == 422, changes


async def test_profiles_are_isolated_between_tenants(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers
) -> None:
    await _put_profile(client, tenant.owner)
    assert (await client.get("/business/profile", headers=other_tenant.owner)).status_code == 404

    await _put_profile(client, other_tenant.owner, name="Other Solar")
    mine = await client.get("/business/profile", headers=tenant.owner)
    theirs = await client.get("/business/profile", headers=other_tenant.owner)
    assert mine.json()["name"] == PROFILE["name"]
    assert theirs.json()["name"] == "Other Solar"


async def test_database_enforces_profile_rules(
    tenant: TenantUsers, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """The API validates first; the database is the backstop."""
    insert = text(
        "INSERT INTO businesses (tenant_id, name, timezone, min_project_size, max_project_size, "
        "project_size_unit) VALUES (:t, 'X', 'UTC', :lo, :hi, :unit)"
    )
    bad_rows = [
        {"lo": 10, "hi": 5, "unit": "kWp"},  # min > max
        {"lo": 5, "hi": 10, "unit": None},  # size without a unit
        {"lo": 0, "hi": 10, "unit": "kWp"},  # non-positive
    ]
    for row in bad_rows:
        with pytest.raises(IntegrityError):
            async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
                await session.execute(insert, {"t": tenant.tenant_id, **row})

    # Exactly one profile per tenant.
    good = {"lo": None, "hi": None, "unit": None}
    async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
        await session.execute(insert, {"t": tenant.tenant_id, **good})
    with pytest.raises(IntegrityError):
        async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
            await session.execute(insert, {"t": tenant.tenant_id, **good})


# --- Services -----------------------------------------------------------------


async def _create(client: AsyncClient, headers: dict[str, str], name: str, **extra: Any):  # type: ignore[no-untyped-def]
    return await client.post("/business/services", json={"name": name, **extra}, headers=headers)


async def test_owner_creates_lists_and_reads_services(client: AsyncClient, tenant: TenantUsers) -> None:
    created = await _create(client, tenant.owner, "Rooftop PV installation", description="Up to 30 kWp")
    assert created.status_code == 201, created.text
    service = created.json()
    assert service["name"] == "Rooftop PV installation"
    assert service["archived"] is False

    await _create(client, tenant.owner, "battery storage")
    listing = await client.get("/business/services", headers=tenant.owner)
    assert [s["name"] for s in listing.json()] == ["battery storage", "Rooftop PV installation"]

    one = await client.get(f"/business/services/{service['id']}", headers=tenant.agent)
    assert one.status_code == 200
    assert one.json() == service


async def test_service_names_are_unique_per_tenant_ignoring_case(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers
) -> None:
    assert (await _create(client, tenant.owner, "Battery Storage")).status_code == 201
    duplicate = await _create(client, tenant.owner, "  battery storage ")
    assert duplicate.status_code == 409
    # Another tenant may use the same name.
    assert (await _create(client, other_tenant.owner, "Battery Storage")).status_code == 201


async def test_archiving_hides_a_service_and_frees_its_name(
    client: AsyncClient, tenant: TenantUsers
) -> None:
    old = (await _create(client, tenant.owner, "Maintenance")).json()
    archived = await client.patch(
        f"/business/services/{old['id']}", json={"archived": True}, headers=tenant.owner
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert archived.json()["archived_at"] is not None

    active = await client.get("/business/services", headers=tenant.owner)
    assert old["id"] not in [s["id"] for s in active.json()]
    everything = await client.get("/business/services?include_archived=true", headers=tenant.owner)
    assert old["id"] in [s["id"] for s in everything.json()]
    # Still readable by id: quotations will keep pointing at it.
    assert (await client.get(f"/business/services/{old['id']}", headers=tenant.owner)).status_code == 200

    # The name is free again for a new active service...
    new = await _create(client, tenant.owner, "Maintenance")
    assert new.status_code == 201
    # ...so restoring the old one would clash.
    restore = await client.patch(
        f"/business/services/{old['id']}", json={"archived": False}, headers=tenant.owner
    )
    assert restore.status_code == 409


async def test_patch_changes_only_the_fields_sent(client: AsyncClient, tenant: TenantUsers) -> None:
    service = (await _create(client, tenant.owner, "Inverter swap", description="Same-day")).json()
    url = f"/business/services/{service['id']}"

    renamed = await client.patch(url, json={"name": "Inverter replacement"}, headers=tenant.owner)
    assert renamed.json()["name"] == "Inverter replacement"
    assert renamed.json()["description"] == "Same-day"

    cleared = await client.patch(url, json={"description": None}, headers=tenant.owner)
    assert cleared.json()["description"] is None
    assert cleared.json()["name"] == "Inverter replacement"

    for bad in [{"name": None}, {"name": ""}, {"archived": None}, {"price": 10}]:
        assert (await client.patch(url, json=bad, headers=tenant.owner)).status_code == 422, bad


async def test_renaming_into_an_existing_name_conflicts(client: AsyncClient, tenant: TenantUsers) -> None:
    await _create(client, tenant.owner, "Design")
    other = (await _create(client, tenant.owner, "Install")).json()
    response = await client.patch(
        f"/business/services/{other['id']}", json={"name": "DESIGN"}, headers=tenant.owner
    )
    assert response.status_code == 409


async def test_only_the_owner_changes_services(client: AsyncClient, tenant: TenantUsers) -> None:
    service = (await _create(client, tenant.owner, "Consultation")).json()
    for headers in (tenant.manager, tenant.agent):
        assert (await _create(client, headers, "Sneaky")).status_code == 403
        patch = await client.patch(
            f"/business/services/{service['id']}", json={"archived": True}, headers=headers
        )
        assert patch.status_code == 403
        assert (await client.get("/business/services", headers=headers)).status_code == 200


async def test_services_are_isolated_between_tenants(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers
) -> None:
    mine = (await _create(client, tenant.owner, "Private service")).json()
    url = f"/business/services/{mine['id']}"

    assert (await client.get(url, headers=other_tenant.owner)).status_code == 404
    patch = await client.patch(url, json={"name": "Stolen"}, headers=other_tenant.owner)
    assert patch.status_code == 404
    listing = await client.get("/business/services?include_archived=true", headers=other_tenant.owner)
    assert mine["id"] not in [s["id"] for s in listing.json()]

    still_mine = await client.get(url, headers=tenant.owner)
    assert still_mine.json()["name"] == "Private service"


async def test_unknown_service_is_404(client: AsyncClient, tenant: TenantUsers) -> None:
    response = await client.get(f"/business/services/{uuid.uuid4()}", headers=tenant.owner)
    assert response.status_code == 404


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "x" * 121}, {"description": "no name"},
                                  {"name": "ok", "description": "x" * 2001}])
async def test_invalid_services_are_rejected(
    client: AsyncClient, tenant: TenantUsers, body: dict[str, Any]
) -> None:
    response = await client.post("/business/services", json=body, headers=tenant.owner)
    assert response.status_code == 422
