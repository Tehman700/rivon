"""BIZ-08: the solar question set, and turning answers into a system size.

The sizing rule is what a quotation's kWp comes from, so it gets the same
scrutiny as pricing: exact numbers, explainable, and no model involved.
"""

from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rivon.business.verticals import SOLAR, SizingConstants, estimate_system_size
from rivon.platform.tenancy import tenant_transaction
from tests.conftest import TenantUsers

DEFAULTS = SizingConstants()


# --- The question set ---------------------------------------------------------


def test_solar_asks_what_a_quote_needs() -> None:
    fields = SOLAR.fields
    # Enough to find the property, judge the job and know who decides.
    for expected in ("postal_code", "property_type", "roof_type", "annual_consumption_kwh",
                     "wants_battery", "battery_capacity_kwh", "timeframe", "owns_property"):
        assert expected in fields, expected
    # Every question is phrased for a customer, not a form.
    for field in fields.values():
        assert "?" in field.question, field.name
        assert field.label and field.label[0].isupper(), field.name


def test_choice_fields_list_their_options() -> None:
    for field in SOLAR.fields.values():
        if field.kind in ("choice", "multi_choice"):
            assert field.choices, field.name
        else:
            assert field.choices == (), field.name


@pytest.mark.parametrize(
    ("requirements", "expected"),
    [
        ({}, ["postal_code", "property_type", "timeframe", "owns_property",
              "system_size_kwp or annual_consumption_kwh"]),
        # A size on its own still leaves the property questions open.
        ({"system_size_kwp": 10}, ["postal_code", "property_type", "timeframe", "owns_property"]),
        # Blank answers don't count as answered.
        ({"postal_code": "  ", "property_type": None}, ["postal_code", "property_type", "timeframe",
                                                        "owns_property",
                                                        "system_size_kwp or annual_consumption_kwh"]),
        ({"postal_code": "10115", "property_type": "house", "timeframe": "asap",
          "owns_property": True, "annual_consumption_kwh": 4200}, []),
        # owns_property is answered even when the answer is "no".
        ({"postal_code": "10115", "property_type": "house", "timeframe": "asap",
          "owns_property": False, "system_size_kwp": 8}, []),
    ],
)
def test_missing_for_quote(requirements: dict[str, Any], expected: list[str]) -> None:
    assert SOLAR.missing_for_quote(requirements) == expected


# --- Sizing -------------------------------------------------------------------


def test_stated_size_wins() -> None:
    estimate = estimate_system_size({"system_size_kwp": "9.5", "annual_consumption_kwh": 20000}, DEFAULTS)
    assert estimate.system_size_kwp == Decimal("9.5")
    assert estimate.basis == "stated"


def test_size_from_yearly_usage() -> None:
    estimate = estimate_system_size({"annual_consumption_kwh": 11400}, DEFAULTS)
    assert estimate.system_size_kwp == Decimal("12.0")  # 11400 / 950
    assert estimate.basis == "annual_consumption"
    assert "11400 kWh" in estimate.explanation and "950" in estimate.explanation


def test_roof_area_caps_the_size() -> None:
    estimate = estimate_system_size({"annual_consumption_kwh": 11400, "roof_area_m2": 40}, DEFAULTS)
    assert estimate.system_size_kwp == Decimal("8.0")  # 40 m² / 5 m² per kWp
    assert estimate.basis == "roof_limited"
    assert "12" in estimate.explanation, "says what the usage alone would have suggested"


def test_roomy_roof_does_not_cap() -> None:
    estimate = estimate_system_size({"annual_consumption_kwh": 11400, "roof_area_m2": 200}, DEFAULTS)
    assert estimate.system_size_kwp == Decimal("12.0")
    assert estimate.basis == "annual_consumption"


def test_no_size_without_usage_or_a_stated_size() -> None:
    estimate = estimate_system_size({"roof_area_m2": 60}, DEFAULTS)
    assert estimate.system_size_kwp is None
    assert estimate.basis == "unknown"


@pytest.mark.parametrize(
    "requirements",
    [
        {"annual_consumption_kwh": 0},
        {"annual_consumption_kwh": -500},
        {"annual_consumption_kwh": "not a number"},
        {"annual_consumption_kwh": None},
        {"annual_consumption_kwh": True},  # a boolean is not a reading
        {"system_size_kwp": 0},
    ],
)
def test_nonsense_answers_never_produce_a_size(requirements: dict[str, Any]) -> None:
    assert estimate_system_size(requirements, DEFAULTS).system_size_kwp is None


def test_tuning_changes_the_result() -> None:
    sunny = SizingConstants(annual_kwh_per_kwp=Decimal("1400"), roof_area_m2_per_kwp=Decimal("5"))
    assert estimate_system_size({"annual_consumption_kwh": 14000}, sunny).system_size_kwp == Decimal("10.0")
    assert estimate_system_size({"annual_consumption_kwh": 14000}, DEFAULTS).system_size_kwp > Decimal("14")

    dense = SizingConstants(annual_kwh_per_kwp=Decimal("950"), roof_area_m2_per_kwp=Decimal("3"))
    packed = estimate_system_size({"annual_consumption_kwh": 11400, "roof_area_m2": 30}, dense)
    assert packed.system_size_kwp == Decimal("10.0")  # 30 / 3


def test_sizes_are_rounded_to_a_tenth() -> None:
    estimate = estimate_system_size({"annual_consumption_kwh": 5000}, DEFAULTS)
    assert estimate.system_size_kwp == Decimal("5.3")  # 5.263...
    assert estimate.system_size_kwp.as_tuple().exponent == -1


# --- Through the API ----------------------------------------------------------


async def test_vertical_is_readable_with_defaults(client: AsyncClient, tenant: TenantUsers) -> None:
    response = await client.get("/business/vertical", headers=tenant.agent)
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "solar"
    assert [g["key"] for g in body["groups"]] == ["property", "energy", "timing"]
    assert body["required_any_of"] == [["system_size_kwp", "annual_consumption_kwh"]]
    # Defaults are there from the start: no form to fill before it works.
    assert Decimal(body["settings"]["annual_kwh_per_kwp"]) == Decimal("950")
    assert body["settings"]["max_followups"] == 2


async def test_owner_tunes_the_numbers(client: AsyncClient, tenant: TenantUsers) -> None:
    saved = await client.put(
        "/business/vertical/settings",
        json={"annual_kwh_per_kwp": "1150", "roof_area_m2_per_kwp": "4.5", "max_followups": 3},
        headers=tenant.owner,
    )
    assert saved.status_code == 200
    assert Decimal(saved.json()["settings"]["annual_kwh_per_kwp"]) == Decimal("1150")

    # And the sizing preview uses them.
    preview = await client.post(
        "/business/vertical/size-estimate", json={"annual_consumption_kwh": "11500"}, headers=tenant.owner
    )
    assert preview.json()["system_size_kwp"] == "10.0"  # 11500 / 1150
    assert "1150" in preview.json()["explanation"]


async def test_size_preview_reports_what_is_still_missing(
    client: AsyncClient, tenant: TenantUsers
) -> None:
    response = await client.post("/business/vertical/size-estimate", json={}, headers=tenant.owner)
    body = response.json()
    assert body["system_size_kwp"] is None
    assert body["basis"] == "unknown"
    assert "postal_code" in body["missing_for_quote"]


@pytest.mark.parametrize(
    "changes",
    [
        {"annual_kwh_per_kwp": "0"},
        {"annual_kwh_per_kwp": "-100"},
        {"annual_kwh_per_kwp": "3000"},
        {"roof_area_m2_per_kwp": "0"},
        {"max_followups": -1},
        {"max_followups": 9},
        {"vertical": "hvac"},
    ],
)
async def test_invalid_tuning_is_rejected(
    client: AsyncClient, tenant: TenantUsers, changes: dict[str, Any]
) -> None:
    body = {"annual_kwh_per_kwp": "950", "roof_area_m2_per_kwp": "5", "max_followups": 2, **changes}
    response = await client.put("/business/vertical/settings", json=body, headers=tenant.owner)
    assert response.status_code == 422, changes


async def test_only_the_owner_tunes(client: AsyncClient, tenant: TenantUsers) -> None:
    body = {"annual_kwh_per_kwp": "1000", "roof_area_m2_per_kwp": "5", "max_followups": 2}
    for headers in (tenant.manager, tenant.agent):
        assert (await client.put("/business/vertical/settings", json=body, headers=headers)).status_code == 403
        assert (await client.get("/business/vertical", headers=headers)).status_code == 200


async def test_tuning_is_per_business(
    client: AsyncClient, tenant: TenantUsers, other_tenant: TenantUsers
) -> None:
    await client.put(
        "/business/vertical/settings",
        json={"annual_kwh_per_kwp": "1300", "roof_area_m2_per_kwp": "5", "max_followups": 0},
        headers=tenant.owner,
    )
    theirs = await client.get("/business/vertical", headers=other_tenant.owner)
    assert Decimal(theirs.json()["settings"]["annual_kwh_per_kwp"]) == Decimal("950")
    assert theirs.json()["settings"]["max_followups"] == 2


async def test_vertical_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/business/vertical")).status_code == 401
    assert (await client.post("/business/vertical/size-estimate", json={})).status_code == 401


async def test_database_enforces_tuning_limits(
    tenant: TenantUsers, app_sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    insert = text(
        "INSERT INTO vertical_settings (tenant_id, vertical, annual_kwh_per_kwp, "
        "roof_area_m2_per_kwp, max_followups) VALUES (:t, :v, :a, :r, :m)"
    )
    bad = [
        {"v": "hvac", "a": 950, "r": 5, "m": 2},
        {"v": "solar", "a": 0, "r": 5, "m": 2},
        {"v": "solar", "a": 950, "r": 0, "m": 2},
        {"v": "solar", "a": 950, "r": 5, "m": 6},
    ]
    for row in bad:
        with pytest.raises(IntegrityError):
            async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
                await session.execute(insert, {"t": tenant.tenant_id, **row})

    # One row per tenant.
    good = {"v": "solar", "a": 950, "r": 5, "m": 2}
    async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
        await session.execute(insert, {"t": tenant.tenant_id, **good})
    with pytest.raises(IntegrityError):
        async with tenant_transaction(app_sessionmaker, tenant.tenant_id) as session:
            await session.execute(insert, {"t": tenant.tenant_id, **good})
