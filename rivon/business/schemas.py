import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from rivon.business.models import DEFAULT_ASSISTANT_NAME, ProjectSizeUnit


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


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


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


class ServiceUpdate(_Strict):
    """Only the fields sent are changed. `archived` hides or restores the service."""

    name: ServiceName | None = None
    description: ServiceDescription | None = None
    archived: bool | None = None

    @model_validator(mode="after")
    def _name_not_null(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name can't be empty")
        if "archived" in self.model_fields_set and self.archived is None:
            raise ValueError("archived must be true or false")
        return self


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
