"""BIZ-05/06/07: service areas, inventory and crews.

These three are what feasibility will check a job against, so the tests focus
on the guarantees that matter later: one tenant never sees another's capacity,
names stay unique, and impossible values can't be stored.
"""

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

AREA = {"name": "Berlin", "country": "de", "postal_prefixes": ["101", "102"]}
ITEM = {"name": "Solar module 430W", "sku": "PV-430", "unit_label": "panel", "quantity": "240",
        "low_stock_threshold": "40"}
CREW = {"name": "Team Nord", "headcount": 3, "weekly_capacity_hours": "120"}

COLLECTIONS = [
    ("/business/service-areas", AREA),
    ("/business/inventory", ITEM),
    ("/business/crews", CREW),
]


async def _create(client: AsyncClient, tenant: TenantUsers, url: str, body: dict[str, Any]):  # type: ignore[no-untyped-def]
    return await client.post(url, json=body, headers=tenant.owner)


# --- Service areas ------------------------------------------------------------


async def test_service_area_round_trip(client: AsyncClient, tenant: TenantUsers) -> None:
    created = await _create(client, tenant, "/business/service-areas", AREA)
    assert created.status_code == 201, created.text
    area = created.json()
    assert area["name"] == "Berlin"
    assert area["country"] == "DE"  # normalised
    assert area["postal_prefixes"] == ["101", "102"]

    listed = await client.get("/business/service-areas", headers=tenant.agent)
    assert [a["id"] for a in listed.json()] == [area["id"]]

    patched = await client.patch(
        f"/business/service-areas/{area['id']}",
        json={"postal_prefixes": ["104", "104", " 103 "]},
        headers=tenant.owner,
    )
    # Upper-cased, trimmed and de-duplicated, order kept.
    assert patched.json()["postal_prefixes"] == ["104", "103"]

    assert (await client.delete(f"/business/service-areas/{area['id']}", headers=tenant.owner)).status_code == 204
    assert (await client.get("/business/service-areas", headers=tenant.owner)).json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"country": "Germany"},
        {"country": ""},
        {"postal_prefixes": ["101 102"]},
        {"postal_prefixes": ["x" * 11]},
        {"unexpected": 1},
    ],
)
async def test_invalid_service_areas_are_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    response = await _create(client, tenant, "/business/service-areas", {**AREA, **changes})
    assert response.status_code == 422, changes


# --- Inventory ----------------------------------------------------------------


async def test_inventory_round_trip_and_low_stock_flag(client: AsyncClient, tenant: TenantUsers) -> None:
    created = await _create(client, tenant, "/business/inventory", ITEM)
    assert created.status_code == 201, created.text
    item = created.json()
    assert Decimal(item["quantity"]) == Decimal("240")
    assert item["low_stock"] is False

    low = await client.patch(
        f"/business/inventory/{item['id']}", json={"quantity": "40"}, headers=tenant.owner
    )
    assert low.json()["low_stock"] is True, "at or below the threshold counts as low"

    cleared = await client.patch(
        f"/business/inventory/{item['id']}",
        json={"low_stock_threshold": None, "sku": None},
        headers=tenant.owner,
    )
    assert cleared.json()["low_stock_threshold"] is None
    assert cleared.json()["sku"] is None
    assert cleared.json()["low_stock"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "-1"},
        {"quantity": "1.234"},
        {"low_stock_threshold": "-5"},
        {"unit_label": ""},
        {"name": "x" * 121},
        {"quantity": None},
    ],
)
async def test_invalid_inventory_is_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    response = await _create(client, tenant, "/business/inventory", {**ITEM, **changes})
    assert response.status_code == 422, changes


# --- Crews --------------------------------------------------------------------


async def test_crew_round_trip(client: AsyncClient, tenant: TenantUsers) -> None:
    created = await _create(client, tenant, "/business/crews", CREW)
    assert created.status_code == 201, created.text
    crew = created.json()
    assert crew["headcount"] == 3
    assert Decimal(crew["weekly_capacity_hours"]) == Decimal("120")
    assert crew["active"] is True

    off = await client.patch(f"/business/crews/{crew['id']}", json={"active": False}, headers=tenant.owner)
    assert off.json()["active"] is False
    assert off.json()["headcount"] == 3  # untouched


@pytest.mark.parametrize(
    "changes",
    [
        {"headcount": 0},
        {"headcount": -2},
        {"weekly_capacity_hours": "0"},
        {"weekly_capacity_hours": "-10"},
        {"active": None},
        {"name": ""},
    ],
)
async def test_invalid_crews_are_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    response = await _create(client, tenant, "/business/crews", {**CREW, **changes})
    assert response.status_code == 422, changes


# --- Shared behaviour across all three ----------------------------------------


@pytest.mark.parametrize(("url", "body"), COLLECTIONS)
async def test_names_are_unique_per_tenant_ignoring_case(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers, url: str, body: dict[str, Any]
) -> None:
    assert (await _create(client, tenant, url, body)).status_code == 201
    duplicate = await _create(client, tenant, url, {**body, "name": body["name"].upper()})
    assert duplicate.status_code == 409
    # Another business may use the same name.
    assert (await _create(client, other_tenant, url, body)).status_code == 201


@pytest.mark.parametrize(("url", "body"), COLLECTIONS)
async def test_only_the_owner_changes_capacity(
    client: AsyncClient, tenant: TenantUsers, url: str, body: dict[str, Any]
) -> None:
    row = (await _create(client, tenant, url, body)).json()
    for headers in (tenant.manager, tenant.agent):
        assert (await client.post(url, json={**body, "name": "Sneaky"}, headers=headers)).status_code == 403
        assert (await client.patch(f"{url}/{row['id']}", json={"name": "Nope"}, headers=headers)).status_code == 403
        assert (await client.delete(f"{url}/{row['id']}", headers=headers)).status_code == 403
        assert (await client.get(url, headers=headers)).status_code == 200


@pytest.mark.parametrize(("url", "body"), COLLECTIONS)
async def test_capacity_is_isolated_between_tenants(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers, url: str, body: dict[str, Any]
) -> None:
    mine = (await _create(client, tenant, url, body)).json()
    assert (await client.get(url, headers=other_tenant.owner)).json() == []
    assert (await client.patch(f"{url}/{mine['id']}", json={"name": "Stolen"}, headers=other_tenant.owner)).status_code == 404
    assert (await client.delete(f"{url}/{mine['id']}", headers=other_tenant.owner)).status_code == 404
    assert [r["id"] for r in (await client.get(url, headers=tenant.owner)).json()] == [mine["id"]]


@pytest.mark.parametrize(("url", "body"), COLLECTIONS)
async def test_unknown_id_is_404(
    client: AsyncClient, tenant: TenantUsers, url: str, body: dict[str, Any]
) -> None:
    assert (await client.patch(f"{url}/{uuid.uuid4()}", json={"name": "x"}, headers=tenant.owner)).status_code == 404
    assert (await client.delete(f"{url}/{uuid.uuid4()}", headers=tenant.owner)).status_code == 404


@pytest.mark.parametrize(("url", "body"), COLLECTIONS)
async def test_capacity_requires_login(client: AsyncClient, url: str, body: dict[str, Any]) -> None:
    assert (await client.get(url)).status_code == 401
    assert (await client.post(url, json=body)).status_code == 401


async def test_lists_are_sorted_by_name(client: AsyncClient, tenant: TenantUsers) -> None:
    for name in ("Potsdam", "berlin", "Cottbus"):
        await _create(client, tenant, "/business/service-areas", {**AREA, "name": name})
    listed = await client.get("/business/service-areas", headers=tenant.owner)
    assert [a["name"] for a in listed.json()] == ["berlin", "Cottbus", "Potsdam"]


async def test_database_enforces_capacity_rules(
    tenant: TenantUsers, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """The API validates first; these are the backstops."""
    statements = [
        # lower case: the column stores ISO codes upper case only
        "INSERT INTO service_areas (tenant_id, name, country) VALUES (:t, 'X', 'de')",
        "INSERT INTO service_areas (tenant_id, name, country, postal_prefixes) "
        "VALUES (:t, 'Y', 'DE', '\"not-an-array\"'::jsonb)",
        "INSERT INTO inventory_items (tenant_id, name, unit_label, quantity) VALUES (:t, 'X', 'panel', -1)",
        "INSERT INTO crews (tenant_id, name, headcount, weekly_capacity_hours) VALUES (:t, 'X', 0, 10)",
        "INSERT INTO crews (tenant_id, name, headcount, weekly_capacity_hours) VALUES (:t, 'X', 1, 0)",
    ]
    for statement in statements:
        with pytest.raises(IntegrityError):
            async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
                await session.execute(text(statement), {"t": tenant.tenant_id})


async def test_queries_filter_by_tenant_even_with_rls_satisfied(
    client: AsyncClient,
    tenant: TenantUsers,
    other_tenant: TenantUsers,
    app_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Rule 2: application code filters by tenant as well as RLS.

    RLS alone would hide the difference, so this asks for another tenant's
    rows from inside a valid session and expects the query itself to exclude
    them. Without the tenant_id filter, this session's own rows come back.
    """
    from rivon.business import service as business
    from rivon.business.models import Crew, InventoryItem, ServiceArea

    await _create(client, tenant, "/business/service-areas", AREA)
    await _create(client, tenant, "/business/inventory", ITEM)
    await _create(client, tenant, "/business/crews", CREW)

    async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
        for model in (ServiceArea, InventoryItem, Crew):
            mine = await business.list_capacity(session, model, tenant.tenant_id)
            assert len(mine) == 1, model.__name__
            theirs = await business.list_capacity(session, model, other_tenant.tenant_id)
            assert theirs == [], f"{model.__name__}: query returned rows for another tenant"
            assert (
                await business.get_capacity(session, model, other_tenant.tenant_id, mine[0].id)
            ) is None, f"{model.__name__}: lookup ignored the tenant"
