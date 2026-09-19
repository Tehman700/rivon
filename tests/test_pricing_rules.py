"""BIZ-03: pricing settings, per-service overrides, rate card lines."""

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

SETTINGS = {
    "default_target_margin_percent": "30",
    "minimum_margin_percent": "15",
    "default_vat_rate_percent": "19",
}

# The example rate card for a rooftop PV service.
RATE_CARD: list[dict[str, Any]] = [
    {"name": "Solar modules", "category": "materials", "quantity_basis": "system_size_kwp",
     "unit_label": "kWp", "unit_cost_eur": "320.00", "sort_order": 1},
    {"name": "Inverter", "category": "materials", "quantity_basis": "fixed",
     "unit_label": "item", "unit_cost_eur": "1400", "sort_order": 2},
    {"name": "Installation labour", "category": "labour", "quantity_basis": "system_size_kwp",
     "quantity_factor": "2.5", "unit_label": "h", "unit_cost_eur": "48", "minimum_quantity": "8",
     "round_up": True, "sort_order": 3},
    {"name": "Scaffolding", "category": "fees", "quantity_basis": "fixed",
     "unit_label": "item", "unit_cost_eur": "450", "sort_order": 4},
    {"name": "Travel", "category": "transport", "quantity_basis": "distance_km",
     "quantity_factor": "2", "unit_label": "km", "unit_cost_eur": "0.80",
     "included_quantity": "30", "sort_order": 5},
]


async def _service(client: AsyncClient, tenant: TenantUsers, name: str = "Rooftop PV", **extra: Any) -> dict:
    response = await client.post("/business/services", json={"name": name, **extra}, headers=tenant.owner)
    assert response.status_code == 201, response.text
    return response.json()


def _rules_url(service: dict) -> str:
    return f"/business/services/{service['id']}/pricing-rules"


async def _add_rule(client: AsyncClient, tenant: TenantUsers, service: dict, **rule: Any):  # type: ignore[no-untyped-def]
    return await client.post(_rules_url(service), json=rule, headers=tenant.owner)


# --- Pricing settings -------------------------------------------------------------


async def test_settings_are_404_until_set_then_round_trip(client: AsyncClient, tenant: TenantUsers) -> None:
    assert (await client.get("/business/pricing-settings", headers=tenant.owner)).status_code == 404

    saved = await client.put("/business/pricing-settings", json=SETTINGS, headers=tenant.owner)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert Decimal(body["default_target_margin_percent"]) == Decimal("30")
    assert Decimal(body["minimum_margin_percent"]) == Decimal("15")
    assert Decimal(body["default_vat_rate_percent"]) == Decimal("19")

    read = await client.get("/business/pricing-settings", headers=tenant.agent)
    assert read.json() == body

    replaced = await client.put(
        "/business/pricing-settings",
        json={**SETTINGS, "default_vat_rate_percent": "0"},  # e.g. German home solar
        headers=tenant.owner,
    )
    assert Decimal(replaced.json()["default_vat_rate_percent"]) == Decimal("0")


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_margin_percent": "35"},  # above the target
        {"default_target_margin_percent": "96"},  # price = cost / 0.04 is not a margin
        {"default_target_margin_percent": "-1"},
        {"default_vat_rate_percent": "101"},
        {"default_vat_rate_percent": "7.125"},
        {"minimum_margin_percent": None},
    ],
)
async def test_invalid_settings_are_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    response = await client.put("/business/pricing-settings", json={**SETTINGS, **changes}, headers=tenant.owner)
    assert response.status_code == 422, changes


async def test_only_the_owner_changes_settings(client: AsyncClient, tenant: TenantUsers) -> None:
    for headers in (tenant.manager, tenant.agent):
        response = await client.put("/business/pricing-settings", json=SETTINGS, headers=headers)
        assert response.status_code == 403


async def test_settings_are_isolated_between_tenants(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers
) -> None:
    await client.put("/business/pricing-settings", json=SETTINGS, headers=tenant.owner)
    assert (await client.get("/business/pricing-settings", headers=other_tenant.owner)).status_code == 404


# --- Per-service overrides --------------------------------------------------------


async def test_services_can_override_margin_and_vat(client: AsyncClient, tenant: TenantUsers) -> None:
    service = await _service(client, tenant, target_margin_percent="40", vat_rate_percent="0")
    assert Decimal(service["target_margin_percent"]) == Decimal("40")
    assert Decimal(service["vat_rate_percent"]) == Decimal("0")

    url = f"/business/services/{service['id']}"
    back_to_default = await client.patch(
        url, json={"target_margin_percent": None, "vat_rate_percent": None}, headers=tenant.owner
    )
    assert back_to_default.json()["target_margin_percent"] is None
    assert back_to_default.json()["vat_rate_percent"] is None

    plain = await _service(client, tenant, name="Maintenance")
    assert plain["target_margin_percent"] is None


async def test_margin_override_cannot_go_below_the_minimum(client: AsyncClient, tenant: TenantUsers) -> None:
    await client.put("/business/pricing-settings", json=SETTINGS, headers=tenant.owner)  # minimum 15%

    too_low = await client.post(
        "/business/services", json={"name": "Cheap job", "target_margin_percent": "10"}, headers=tenant.owner
    )
    assert too_low.status_code == 409
    assert "15" in too_low.json()["detail"]

    service = await _service(client, tenant, target_margin_percent="20")
    lowered = await client.patch(
        f"/business/services/{service['id']}", json={"target_margin_percent": "12"}, headers=tenant.owner
    )
    assert lowered.status_code == 409


async def test_raising_the_minimum_above_a_service_margin_is_refused(
    client: AsyncClient, tenant: TenantUsers
) -> None:
    await _service(client, tenant, name="Battery add-on", target_margin_percent="20")
    response = await client.put(
        "/business/pricing-settings",
        json={**SETTINGS, "minimum_margin_percent": "25"},
        headers=tenant.owner,
    )
    assert response.status_code == 409
    assert "Battery add-on" in response.json()["detail"]
    # At or below the service's margin is fine.
    ok = await client.put(
        "/business/pricing-settings", json={**SETTINGS, "minimum_margin_percent": "20"}, headers=tenant.owner
    )
    assert ok.status_code == 200


@pytest.mark.parametrize("changes", [{"target_margin_percent": "96"}, {"vat_rate_percent": "-1"}])
async def test_invalid_service_overrides_are_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    response = await client.post("/business/services", json={"name": "X", **changes}, headers=tenant.owner)
    assert response.status_code == 422


# --- Rate card lines --------------------------------------------------------------


async def test_owner_builds_a_rate_card(client: AsyncClient, tenant: TenantUsers) -> None:
    service = await _service(client, tenant)
    for line in reversed(RATE_CARD):
        response = await _add_rule(client, tenant, service, **line)
        assert response.status_code == 201, response.text

    listing = await client.get(_rules_url(service), headers=tenant.agent)
    assert listing.status_code == 200
    rules = listing.json()
    assert [r["name"] for r in rules] == [line["name"] for line in RATE_CARD]  # by sort_order

    labour = rules[2]
    assert Decimal(labour["quantity_factor"]) == Decimal("2.5")
    assert Decimal(labour["minimum_quantity"]) == Decimal("8")
    assert labour["round_up"] is True
    travel = rules[4]
    assert Decimal(travel["unit_cost_eur"]) == Decimal("0.80")
    assert Decimal(travel["included_quantity"]) == Decimal("30")
    # Defaults on a line that didn't set them.
    inverter = rules[1]
    assert (Decimal(inverter["quantity_factor"]), Decimal(inverter["included_quantity"])) == (1, 0)
    assert inverter["round_up"] is False
    assert all(r["service_id"] == service["id"] for r in rules)


async def test_line_names_are_unique_per_service(client: AsyncClient, tenant: TenantUsers) -> None:
    pv = await _service(client, tenant)
    battery = await _service(client, tenant, name="Battery storage")
    assert (await _add_rule(client, tenant, pv, **RATE_CARD[0])).status_code == 201
    duplicate = await _add_rule(client, tenant, pv, **{**RATE_CARD[0], "name": "SOLAR MODULES"})
    assert duplicate.status_code == 409
    # The same name on another service is fine.
    assert (await _add_rule(client, tenant, battery, **RATE_CARD[0])).status_code == 201


async def test_each_service_lists_only_its_own_lines(client: AsyncClient, tenant: TenantUsers) -> None:
    pv = await _service(client, tenant)
    battery = await _service(client, tenant, name="Battery storage")
    await _add_rule(client, tenant, pv, **RATE_CARD[0])
    await _add_rule(client, tenant, pv, **RATE_CARD[1])
    await _add_rule(
        client, tenant, battery,
        name="Battery pack", category="materials", quantity_basis="battery_capacity_kwh",
        unit_label="kWh", unit_cost_eur="450",
    )

    pv_lines = (await client.get(_rules_url(pv), headers=tenant.owner)).json()
    battery_lines = (await client.get(_rules_url(battery), headers=tenant.owner)).json()
    assert [r["name"] for r in pv_lines] == ["Solar modules", "Inverter"]
    assert [r["name"] for r in battery_lines] == ["Battery pack"]


async def test_patch_and_delete_a_line(client: AsyncClient, tenant: TenantUsers) -> None:
    service = await _service(client, tenant)
    rule = (await _add_rule(client, tenant, service, **RATE_CARD[2])).json()
    other = (await _add_rule(client, tenant, service, **RATE_CARD[3])).json()
    url = f"{_rules_url(service)}/{rule['id']}"

    patched = await client.patch(url, json={"unit_cost_eur": "52.50", "round_up": False}, headers=tenant.owner)
    assert patched.status_code == 200
    assert Decimal(patched.json()["unit_cost_eur"]) == Decimal("52.50")
    assert patched.json()["round_up"] is False
    assert Decimal(patched.json()["quantity_factor"]) == Decimal("2.5")  # untouched

    clash = await client.patch(url, json={"name": other["name"]}, headers=tenant.owner)
    assert clash.status_code == 409
    for bad in [{"unit_cost_eur": None}, {"quantity_factor": "0"}, {"colour": "red"}]:
        assert (await client.patch(url, json=bad, headers=tenant.owner)).status_code == 422, bad

    assert (await client.delete(url, headers=tenant.owner)).status_code == 204
    names = [r["name"] for r in (await client.get(_rules_url(service), headers=tenant.owner)).json()]
    assert names == [other["name"]]
    assert (await client.delete(url, headers=tenant.owner)).status_code == 404


async def test_line_must_be_addressed_through_its_own_service(
    client: AsyncClient, tenant: TenantUsers
) -> None:
    pv = await _service(client, tenant)
    battery = await _service(client, tenant, name="Battery storage")
    rule = (await _add_rule(client, tenant, pv, **RATE_CARD[0])).json()
    wrong_url = f"{_rules_url(battery)}/{rule['id']}"
    assert (await client.patch(wrong_url, json={"unit_cost_eur": "1"}, headers=tenant.owner)).status_code == 404
    assert (await client.delete(wrong_url, headers=tenant.owner)).status_code == 404


async def test_only_the_owner_changes_lines(client: AsyncClient, tenant: TenantUsers) -> None:
    service = await _service(client, tenant)
    rule = (await _add_rule(client, tenant, service, **RATE_CARD[0])).json()
    url = f"{_rules_url(service)}/{rule['id']}"
    for headers in (tenant.manager, tenant.agent):
        assert (await client.post(_rules_url(service), json=RATE_CARD[1], headers=headers)).status_code == 403
        assert (await client.patch(url, json={"unit_cost_eur": "1"}, headers=headers)).status_code == 403
        assert (await client.delete(url, headers=headers)).status_code == 403
        assert (await client.get(_rules_url(service), headers=headers)).status_code == 200


async def test_rate_cards_are_isolated_between_tenants(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers
) -> None:
    service = await _service(client, tenant)
    rule = (await _add_rule(client, tenant, service, **RATE_CARD[0])).json()
    url = f"{_rules_url(service)}/{rule['id']}"

    assert (await client.get(_rules_url(service), headers=other_tenant.owner)).status_code == 404
    assert (await client.post(_rules_url(service), json=RATE_CARD[1], headers=other_tenant.owner)).status_code == 404
    assert (await client.patch(url, json={"unit_cost_eur": "0"}, headers=other_tenant.owner)).status_code == 404
    assert (await client.delete(url, headers=other_tenant.owner)).status_code == 404

    mine = (await client.get(_rules_url(service), headers=tenant.owner)).json()
    assert Decimal(mine[0]["unit_cost_eur"]) == Decimal("320")


async def test_archived_service_keeps_its_rate_card(client: AsyncClient, tenant: TenantUsers) -> None:
    service = await _service(client, tenant)
    await _add_rule(client, tenant, service, **RATE_CARD[0])
    await client.patch(f"/business/services/{service['id']}", json={"archived": True}, headers=tenant.owner)
    rules = await client.get(_rules_url(service), headers=tenant.owner)
    assert len(rules.json()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity_factor": "0"},
        {"quantity_factor": "1.23456"},
        {"unit_cost_eur": "-1"},
        {"unit_cost_eur": "1.999"},
        {"included_quantity": "-5"},
        {"minimum_quantity": "-1"},
        {"category": "snacks"},
        {"quantity_basis": "roof_area_m2"},
        {"unit_label": ""},
        {"name": ""},
        {"sort_order": -1},
        {"unit_cost_eur": None},
    ],
)
async def test_invalid_lines_are_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    service = await _service(client, tenant)
    response = await _add_rule(client, tenant, service, **{**RATE_CARD[0], **changes})
    assert response.status_code == 422, changes


async def test_unknown_service_has_no_rate_card(client: AsyncClient, tenant: TenantUsers) -> None:
    response = await client.get(f"/business/services/{uuid.uuid4()}/pricing-rules", headers=tenant.owner)
    assert response.status_code == 404


# --- Database backstops -------------------------------------------------------------


async def test_database_enforces_pricing_rules(
    client: AsyncClient, tenant: TenantUsers, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    service = await _service(client, tenant)
    bad_statements = [
        ("INSERT INTO pricing_settings (tenant_id, default_target_margin_percent, "
         "minimum_margin_percent, default_vat_rate_percent) VALUES (:t, 20, 30, 19)"),  # min > target
        ("INSERT INTO pricing_settings (tenant_id, default_target_margin_percent, "
         "minimum_margin_percent, default_vat_rate_percent) VALUES (:t, 99, 10, 19)"),  # margin > 95
        "UPDATE services SET target_margin_percent = 99 WHERE tenant_id = :t",
        ("INSERT INTO pricing_rules (tenant_id, service_id, name, category, quantity_basis, "
         "unit_label, unit_cost_eur) VALUES (:t, :s, 'x', 'materials', 'fixed', 'item', -1)"),
        ("INSERT INTO pricing_rules (tenant_id, service_id, name, category, quantity_basis, "
         "unit_label, unit_cost_eur, quantity_factor) VALUES (:t, :s, 'x', 'materials', 'fixed', "
         "'item', 1, 0)"),
        ("INSERT INTO pricing_rules (tenant_id, service_id, name, category, quantity_basis, "
         "unit_label, unit_cost_eur) VALUES (:t, :s, 'x', 'materials', 'vibes', 'item', 1)"),
    ]
    for statement in bad_statements:
        with pytest.raises(IntegrityError):
            async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
                await session.execute(text(statement), {"t": tenant.tenant_id, "s": service["id"]})
