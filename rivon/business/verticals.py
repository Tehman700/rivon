"""Vertical configuration (BIZ-08): what the assistant asks, what it extracts,
and how those answers become the numbers pricing needs.

The question set is defined here in code and is the same for every business in
a vertical, so extraction stays predictable. What each business tunes is the
numbers (see VerticalSettings): how much a kWp generates in their climate, how
much roof it needs, how often to chase a customer before handing over.

Adding a vertical means adding a Vertical here plus its pricing bases; it does
not mean new code paths. Solar is the only one in v1.

Nothing in this module calls a language model. The assistant fills in
`requirements`; turning them into a system size is arithmetic, so that a
quotation can always be explained.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class FieldKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    MULTI_CHOICE = "multi_choice"


@dataclass(frozen=True)
class FieldSpec:
    """One thing the assistant tries to establish."""

    name: str
    kind: FieldKind
    label: str
    question: str
    unit: str | None = None
    choices: tuple[str, ...] = ()
    #: Without it (or an alternative from `required_any_of`) a quote can't be priced.
    required: bool = False


@dataclass(frozen=True)
class FieldGroup:
    key: str
    label: str
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True)
class Vertical:
    key: str
    label: str
    groups: tuple[FieldGroup, ...]
    #: Each tuple is a set of alternatives: at least one must be answered.
    required_any_of: tuple[tuple[str, ...], ...] = ()

    @property
    def fields(self) -> dict[str, FieldSpec]:
        return {f.name: f for group in self.groups for f in group.fields}

    def missing_for_quote(self, requirements: dict[str, Any]) -> list[str]:
        """Field names still needed before this job can be priced."""
        answered = {name for name, value in requirements.items() if _is_answered(value)}
        missing = [f.name for f in self.fields.values() if f.required and f.name not in answered]
        for alternatives in self.required_any_of:
            if not any(name in answered for name in alternatives):
                missing.append(" or ".join(alternatives))
        return missing


def _is_answered(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


SOLAR = Vertical(
    key="solar",
    label="Solar installation",
    groups=(
        FieldGroup(
            key="property",
            label="Property and roof",
            fields=(
                FieldSpec("postal_code", FieldKind.TEXT, "Postcode",
                          "What's the postcode of the property?", required=True),
                FieldSpec("city", FieldKind.TEXT, "City or town",
                          "Which town or city is that in?"),
                FieldSpec("address_line", FieldKind.TEXT, "Street address",
                          "What's the street address?"),
                FieldSpec("property_type", FieldKind.CHOICE, "Property type",
                          "Is it a house, an apartment building or a commercial property?",
                          choices=("house", "apartment", "commercial", "other"), required=True),
                FieldSpec("roof_type", FieldKind.CHOICE, "Roof type",
                          "What kind of roof is it: tiled, flat, metal or slate?",
                          choices=("tiled", "flat", "metal", "slate", "other")),
                FieldSpec("roof_area_m2", FieldKind.NUMBER, "Usable roof area",
                          "Roughly how much usable roof area is there?", unit="m²"),
                FieldSpec("storeys", FieldKind.NUMBER, "Storeys",
                          "How many storeys is the building?"),
                FieldSpec("shading", FieldKind.CHOICE, "Shading",
                          "Is the roof shaded by trees or other buildings at any point in the day?",
                          choices=("none", "partial", "significant")),
            ),
        ),
        FieldGroup(
            key="energy",
            label="Energy use and goals",
            fields=(
                FieldSpec("annual_consumption_kwh", FieldKind.NUMBER, "Yearly electricity use",
                          "Roughly how much electricity do you use a year? Your last bill usually says.",
                          unit="kWh"),
                FieldSpec("monthly_bill_eur", FieldKind.NUMBER, "Monthly bill",
                          "About how much is your monthly electricity bill?", unit="€"),
                FieldSpec("system_size_kwp", FieldKind.NUMBER, "System size, if known",
                          "Do you already know what size system you're after?", unit="kWp"),
                FieldSpec("goals", FieldKind.MULTI_CHOICE, "What they want from it",
                          "What matters most: lower bills, backup power, or charging an EV?",
                          choices=("lower_bills", "backup_power", "ev_charging", "independence")),
                FieldSpec("wants_battery", FieldKind.BOOLEAN, "Wants a battery",
                          "Would you like battery storage as well?"),
                FieldSpec("battery_capacity_kwh", FieldKind.NUMBER, "Battery size, if known",
                          "Do you have a battery size in mind?", unit="kWh"),
                FieldSpec("has_existing_system", FieldKind.BOOLEAN, "Existing panels",
                          "Do you have any solar panels installed already?"),
            ),
        ),
        FieldGroup(
            key="timing",
            label="Timing and decision",
            fields=(
                FieldSpec("timeframe", FieldKind.CHOICE, "Timeframe",
                          "When would you like the work done?",
                          choices=("asap", "1_3_months", "3_6_months", "later", "just_exploring"),
                          required=True),
                FieldSpec("owns_property", FieldKind.BOOLEAN, "Owns the property",
                          "Do you own the property?", required=True),
                FieldSpec("decision_makers", FieldKind.CHOICE, "Who decides",
                          "Is it just you deciding, or someone else too?",
                          choices=("just_me", "with_partner", "landlord_or_board", "other")),
            ),
        ),
    ),
    # Pricing needs a size: either stated, or worked out from yearly use.
    required_any_of=(("system_size_kwp", "annual_consumption_kwh"),),
)

VERTICALS: dict[str, Vertical] = {SOLAR.key: SOLAR}
DEFAULT_VERTICAL = SOLAR.key


# --- Turning answers into the numbers pricing uses ----------------------------


@dataclass(frozen=True)
class SizingConstants:
    """The per-business tuning. Defaults suit central European sunlight and
    typical panel density; every installer can adjust them."""

    annual_kwh_per_kwp: Decimal = Decimal("950")
    roof_area_m2_per_kwp: Decimal = Decimal("5")


@dataclass(frozen=True)
class SizeEstimate:
    system_size_kwp: Decimal | None
    #: Where the number came from, so a quotation can show its working.
    basis: str
    explanation: str


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number > 0 else None


def estimate_system_size(
    requirements: dict[str, Any], constants: SizingConstants | None = None
) -> SizeEstimate:
    """Work out the system size to price, from what the customer told us.

    Deterministic and explainable: a stated size always wins, otherwise yearly
    consumption sets the size and the usable roof caps it.
    """
    constants = constants or SizingConstants()

    stated = _to_decimal(requirements.get("system_size_kwp"))
    if stated is not None:
        return SizeEstimate(_round_kwp(stated), "stated", f"{_fmt(stated)} kWp, as the customer asked for")

    consumption = _to_decimal(requirements.get("annual_consumption_kwh"))
    if consumption is None:
        return SizeEstimate(
            None,
            "unknown",
            "No system size yet: the customer hasn't given a size or their yearly electricity use",
        )

    from_usage = consumption / constants.annual_kwh_per_kwp
    explanation = (
        f"{_fmt(_round_kwp(from_usage))} kWp from {_fmt(consumption)} kWh a year "
        f"at {_fmt(constants.annual_kwh_per_kwp)} kWh per kWp"
    )

    roof_area = _to_decimal(requirements.get("roof_area_m2"))
    if roof_area is not None:
        roof_limit = roof_area / constants.roof_area_m2_per_kwp
        if roof_limit < from_usage:
            return SizeEstimate(
                _round_kwp(roof_limit),
                "roof_limited",
                f"{_fmt(_round_kwp(roof_limit))} kWp: the roof allows less than the "
                f"{_fmt(_round_kwp(from_usage))} kWp their usage suggests "
                f"({_fmt(roof_area)} m² at {_fmt(constants.roof_area_m2_per_kwp)} m² per kWp)",
            )

    return SizeEstimate(_round_kwp(from_usage), "annual_consumption", explanation)


def _round_kwp(value: Decimal) -> Decimal:
    """Panels come in steps, so tenths of a kWp is as precise as is meaningful."""
    return value.quantize(Decimal("0.1"))


def _fmt(value: Decimal) -> str:
    return f"{value.normalize():f}"
