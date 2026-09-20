import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

from rivon.business.models import (
    DEFAULT_ASSISTANT_NAME,
    ProjectSizeUnit,
    QuantityBasis,
    RuleCategory,
)


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown timezone {value!r}; use an IANA name like Europe/Berlin") from None
    return value


def _upper(value: object) -> object:
    return value.upper() if isinstance(value, str) else value


Timezone = Annotated[str, Field(max_length=64), AfterValidator(_valid_timezone)]
Country = Annotated[str, BeforeValidator(_upper), Field(pattern=r"^[A-Z]{2}$")]
Email = Annotated[str, Field(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Phone = Annotated[str, Field(max_length=32, pattern=r"^\+?[0-9][0-9 ()\-]{5,30}$")]
Website = Annotated[str, Field(max_length=300, pattern=r"^https?://\S+$")]
ClockTime = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]  # "HH:MM", 24h
Size = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Euros = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
# Gross margin on price, capped so price = cost / (1 - margin) stays sane.
MarginPercent = Annotated[Decimal, Field(ge=0, le=95, max_digits=5, decimal_places=2)]
VatPercent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Cost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Factor = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=4)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Patch(_Strict):
    """Partial update: only fields sent are changed. Fields listed in
    `_nullable` may be sent as null to clear them; others may not."""

    _nullable: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def _no_null_for_required(self) -> Self:
        for field in self.model_fields_set - self._nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} can't be null")
        return self


class OpeningPeriod(_Strict):
    opens: ClockTime
    closes: ClockTime

    @model_validator(mode="after")
    def _closes_after_opens(self) -> Self:
        # "HH:MM" strings sort chronologically. Overnight periods aren't supported.
        if self.closes <= self.opens:
            raise ValueError("closes must be after opens (on the same day)")
        return self


DayHours = Annotated[list[OpeningPeriod], Field(max_length=4)]


class WeeklyHours(_Strict):
    """Opening periods per day. An empty day means closed."""

    monday: DayHours = []
    tuesday: DayHours = []
    wednesday: DayHours = []
    thursday: DayHours = []
    friday: DayHours = []
    saturday: DayHours = []
    sunday: DayHours = []

    @model_validator(mode="after")
    def _no_overlaps(self) -> Self:
        for day, periods in self:
            ordered = sorted(periods, key=lambda p: p.opens)
            for earlier, later in zip(ordered, ordered[1:], strict=False):
                if later.opens < earlier.closes:
                    raise ValueError(f"{day}: opening periods overlap")
            setattr(self, day, ordered)
        return self


def _check_range(low: Decimal | None, high: Decimal | None, what: str) -> None:
    if low is not None and high is not None and low > high:
        raise ValueError(f"minimum {what} is larger than the maximum")


class BusinessProfileIn(_Strict):
    """The full profile. PUT replaces it; omitted optional fields are cleared."""

    name: Annotated[str, Field(min_length=1, max_length=200)]
    assistant_name: Annotated[str, Field(min_length=1, max_length=60)] = DEFAULT_ASSISTANT_NAME

    contact_email: Email | None = None
    contact_phone: Phone | None = None
    website: Website | None = None
    address_line: Annotated[str, Field(max_length=300)] | None = None
    city: Annotated[str, Field(max_length=120)] | None = None
    postal_code: Annotated[str, Field(max_length=20)] | None = None
    country: Country | None = None

    timezone: Timezone
    business_hours: WeeklyHours = WeeklyHours()

    min_project_size: Size | None = None
    max_project_size: Size | None = None
    project_size_unit: ProjectSizeUnit | None = None
    min_project_value_eur: Euros | None = None
    max_project_value_eur: Euros | None = None

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        has_size = self.min_project_size is not None or self.max_project_size is not None
        if has_size and self.project_size_unit is None:
            raise ValueError("project_size_unit is required when a project size is set")
        _check_range(self.min_project_size, self.max_project_size, "project size")
        _check_range(self.min_project_value_eur, self.max_project_value_eur, "project value")
        return self


class BusinessProfileOut(BusinessProfileIn):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime


ServiceName = Annotated[str, Field(min_length=1, max_length=120)]
ServiceDescription = Annotated[str, Field(max_length=2000)]


class ServiceCreate(_Strict):
    name: ServiceName
    description: ServiceDescription | None = None
    # Overrides of the business-wide pricing settings; None = use the default.
    target_margin_percent: MarginPercent | None = None
    vat_rate_percent: VatPercent | None = None


class ServiceUpdate(_Patch):
    """Only the fields sent are changed. `archived` hides or restores the service.
    Send a margin or VAT override as null to go back to the default."""

    _nullable = frozenset({"description", "target_margin_percent", "vat_rate_percent"})

    name: ServiceName | None = None
    description: ServiceDescription | None = None
    archived: bool | None = None
    target_margin_percent: MarginPercent | None = None
    vat_rate_percent: VatPercent | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    archived: bool
    archived_at: datetime | None
    target_margin_percent: Decimal | None
    vat_rate_percent: Decimal | None
    created_at: datetime
    updated_at: datetime


class PricingSettingsIn(_Strict):
    default_target_margin_percent: MarginPercent
    minimum_margin_percent: MarginPercent
    default_vat_rate_percent: VatPercent

    @model_validator(mode="after")
    def _minimum_below_target(self) -> Self:
        if self.minimum_margin_percent > self.default_target_margin_percent:
            raise ValueError("minimum margin can't be above the target margin")
        return self


class PricingSettingsOut(PricingSettingsIn):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime


RuleName = Annotated[str, Field(min_length=1, max_length=120)]
UnitLabel = Annotated[str, Field(min_length=1, max_length=20)]
SortOrder = Annotated[int, Field(ge=0, le=10_000)]


class PricingRuleIn(_Strict):
    """One rate card line. Amounts are costs in EUR, net of VAT.

    chargeable quantity = max(minimum_quantity, basis x quantity_factor - included_quantity),
    rounded up to a whole number if round_up; cost = chargeable quantity x unit_cost_eur.
    """

    name: RuleName
    category: RuleCategory
    quantity_basis: QuantityBasis
    quantity_factor: Factor = Decimal(1)
    unit_label: UnitLabel
    unit_cost_eur: Cost
    included_quantity: Quantity = Decimal(0)
    minimum_quantity: Quantity = Decimal(0)
    round_up: bool = False
    sort_order: SortOrder = 0


class PricingRuleUpdate(_Patch):
    name: RuleName | None = None
    category: RuleCategory | None = None
    quantity_basis: QuantityBasis | None = None
    quantity_factor: Factor | None = None
    unit_label: UnitLabel | None = None
    unit_cost_eur: Cost | None = None
    included_quantity: Quantity | None = None
    minimum_quantity: Quantity | None = None
    round_up: bool | None = None
    sort_order: SortOrder | None = None


class PricingRuleOut(PricingRuleIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    service_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --- Capacity: where you work, what you hold, who can go (BIZ-05/06/07) -------

PostalPrefix = Annotated[str, Field(pattern=r"^[A-Za-z0-9]{1,10}$")]
PlaceName = Annotated[str, Field(min_length=1, max_length=120)]
Quantity12 = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
CapacityHours = Annotated[Decimal, Field(gt=0, max_digits=6, decimal_places=2)]
Headcount = Annotated[int, Field(ge=1, le=500)]


def _tidy_prefixes(values: list[str]) -> list[str]:
    """Upper-case and de-duplicate, keeping the order the owner typed."""
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value.strip().upper(), None)
    return list(seen)


class ServiceAreaIn(_Strict):
    """Somewhere you'll travel to. Postal prefixes make address matching exact:
    "101" covers every Berlin postcode starting 101."""

    name: PlaceName
    country: Country
    postal_prefixes: Annotated[list[PostalPrefix], Field(max_length=50)] = []

    @model_validator(mode="after")
    def _normalise(self) -> Self:
        self.postal_prefixes = _tidy_prefixes(self.postal_prefixes)
        return self


class ServiceAreaUpdate(_Patch):
    name: PlaceName | None = None
    country: Country | None = None
    postal_prefixes: Annotated[list[PostalPrefix], Field(max_length=50)] | None = None

    @model_validator(mode="after")
    def _normalise(self) -> Self:
        if self.postal_prefixes is not None:
            self.postal_prefixes = _tidy_prefixes(self.postal_prefixes)
        return self


class ServiceAreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: str
    postal_prefixes: list[str]
    created_at: datetime
    updated_at: datetime


class InventoryItemIn(_Strict):
    name: PlaceName
    sku: Annotated[str, Field(max_length=60)] | None = None
    unit_label: UnitLabel
    quantity: Quantity12 = Decimal(0)
    low_stock_threshold: Quantity12 | None = None


class InventoryItemUpdate(_Patch):
    _nullable = frozenset({"sku", "low_stock_threshold"})

    name: PlaceName | None = None
    sku: Annotated[str, Field(max_length=60)] | None = None
    unit_label: UnitLabel | None = None
    quantity: Quantity12 | None = None
    low_stock_threshold: Quantity12 | None = None


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sku: str | None
    unit_label: str
    quantity: Decimal
    low_stock_threshold: Decimal | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def low_stock(self) -> bool:
        """Warned about, never blocking: stock can be bought in."""
        return self.low_stock_threshold is not None and self.quantity <= self.low_stock_threshold


class CrewIn(_Strict):
    """Availability is weekly hours rather than a calendar: enough to tell
    whether a job fits, without asking owners to keep a roster up to date."""

    name: PlaceName
    headcount: Headcount = 1
    weekly_capacity_hours: CapacityHours
    active: bool = True


class CrewUpdate(_Patch):
    name: PlaceName | None = None
    headcount: Headcount | None = None
    weekly_capacity_hours: CapacityHours | None = None
    active: bool | None = None


class CrewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    headcount: int
    weekly_capacity_hours: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


# --- Vertical configuration (BIZ-08) -----------------------------------------


class VerticalSettingsIn(_Strict):
    """The numbers a business tunes. The questions themselves are fixed."""

    annual_kwh_per_kwp: Annotated[Decimal, Field(gt=0, le=2000, max_digits=6, decimal_places=2)]
    roof_area_m2_per_kwp: Annotated[Decimal, Field(gt=0, le=50, max_digits=6, decimal_places=2)]
    max_followups: Annotated[int, Field(ge=0, le=5)]


class VerticalSettingsOut(VerticalSettingsIn):
    model_config = ConfigDict(from_attributes=True)

    vertical: str
    updated_at: datetime


class FieldOut(BaseModel):
    name: str
    kind: str
    label: str
    question: str
    unit: str | None
    choices: list[str]
    required: bool


class FieldGroupOut(BaseModel):
    key: str
    label: str
    fields: list[FieldOut]


class VerticalOut(BaseModel):
    """What the assistant will ask, and what a quote needs before it can be priced."""

    key: str
    label: str
    groups: list[FieldGroupOut]
    required_any_of: list[list[str]]
    settings: VerticalSettingsOut


class SizeEstimateRequest(_Strict):
    """A slice of the requirements, for previewing how the sizing behaves."""

    system_size_kwp: Annotated[Decimal, Field(gt=0, le=10_000)] | None = None
    annual_consumption_kwh: Annotated[Decimal, Field(gt=0, le=10_000_000)] | None = None
    roof_area_m2: Annotated[Decimal, Field(gt=0, le=100_000)] | None = None


class SizeEstimateOut(BaseModel):
    system_size_kwp: Decimal | None
    basis: str
    explanation: str
    missing_for_quote: list[str]
