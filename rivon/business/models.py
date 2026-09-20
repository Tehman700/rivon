from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from rivon.db import Base, BaseMixin, TenantScopedMixin

DEFAULT_ASSISTANT_NAME = "Rivon"


def _string_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )


class ProjectSizeUnit(StrEnum):
    """Unit a vertical measures job size in. Each vertical adds its own (BIZ-08)."""

    KWP = "kWp"  # solar: peak kilowatts


class RuleCategory(StrEnum):
    """How a rate card line is grouped on a quotation."""

    MATERIALS = "materials"
    LABOUR = "labour"
    TRANSPORT = "transport"
    FEES = "fees"


class QuantityBasis(StrEnum):
    """What a rate card line's quantity is derived from. The solar values move
    into the vertical config framework with BIZ-08."""

    FIXED = "fixed"  # quantity is the factor itself, e.g. 1 inverter
    SYSTEM_SIZE_KWP = "system_size_kwp"
    BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
    DISTANCE_KM = "distance_km"  # one-way distance from the business to the site


class Business(BaseMixin, TenantScopedMixin, Base):
    """The tenant's business profile. Exactly one per tenant."""

    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200))
    # What the bot calls itself to customers. Customers hear from the tenant's
    # business, not from Rivon (spec: naming conventions).
    assistant_name: Mapped[str] = mapped_column(String(60), server_default=DEFAULT_ASSISTANT_NAME)

    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    website: Mapped[str | None] = mapped_column(String(300))
    address_line: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2

    timezone: Mapped[str] = mapped_column(String(64))  # IANA name, e.g. Europe/Berlin
    # {"monday": [{"opens": "08:00", "closes": "17:00"}], ...}; validated by the API schema.
    business_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    # Job size bounds, both optional, checked by feasibility (FEAS-06).
    min_project_size: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_project_size: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    project_size_unit: Mapped[ProjectSizeUnit | None] = mapped_column(
        Enum(
            ProjectSizeUnit,
            name="project_size_unit",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda members: [m.value for m in members],
        )
    )
    min_project_value_eur: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_project_value_eur: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint("tenant_id"),
            CheckConstraint("country IS NULL OR country ~ '^[A-Z]{2}$'", name="country_iso2"),
            CheckConstraint(
                "(min_project_size IS NULL AND max_project_size IS NULL) "
                "OR project_size_unit IS NOT NULL",
                name="project_size_has_unit",
            ),
            CheckConstraint(
                "min_project_size IS NULL OR min_project_size > 0", name="min_project_size_positive"
            ),
            CheckConstraint(
                "min_project_size IS NULL OR max_project_size IS NULL "
                "OR min_project_size <= max_project_size",
                name="project_size_range",
            ),
            CheckConstraint(
                "min_project_value_eur IS NULL OR min_project_value_eur > 0",
                name="min_project_value_positive",
            ),
            CheckConstraint(
                "min_project_value_eur IS NULL OR max_project_value_eur IS NULL "
                "OR min_project_value_eur <= max_project_value_eur",
                name="project_value_range",
            ),
        )


class Service(BaseMixin, TenantScopedMixin, Base):
    """A service the business offers. Archived, never deleted: quotations will
    keep referring to services that are no longer offered."""

    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Overrides of the pricing settings for this service; NULL = use the default.
    target_margin_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    vat_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            # Names are unique per tenant, ignoring case, among active services.
            Index(
                "uq_services_tenant_id_name_active",
                "tenant_id",
                func.lower(text("name")),
                unique=True,
                postgresql_where=text("archived_at IS NULL"),
            ),
            CheckConstraint(
                "target_margin_percent IS NULL "
                "OR (target_margin_percent >= 0 AND target_margin_percent <= 95)",
                name="target_margin_range",
            ),
            CheckConstraint(
                "vat_rate_percent IS NULL OR (vat_rate_percent >= 0 AND vat_rate_percent <= 100)",
                name="vat_rate_range",
            ),
        )


class PricingSettings(BaseMixin, TenantScopedMixin, Base):
    """Business-wide pricing defaults. Exactly one per tenant.

    Margin is gross margin on the selling price: price = cost / (1 - margin).
    A 30% margin on a EUR 700 cost gives a EUR 1,000 price. Capped at 95%.
    """

    __tablename__ = "pricing_settings"

    default_target_margin_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Quotes below this margin get flagged to the owner (QUOT-01).
    minimum_margin_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    default_vat_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint("tenant_id"),
            CheckConstraint(
                "default_target_margin_percent >= 0 AND default_target_margin_percent <= 95",
                name="target_margin_range",
            ),
            CheckConstraint(
                "minimum_margin_percent >= 0 "
                "AND minimum_margin_percent <= default_target_margin_percent",
                name="minimum_margin_range",
            ),
            CheckConstraint(
                "default_vat_rate_percent >= 0 AND default_vat_rate_percent <= 100",
                name="vat_rate_range",
            ),
        )


class PricingRule(BaseMixin, TenantScopedMixin, Base):
    """One line of a service's rate card. All amounts are costs, net of VAT.

    chargeable quantity = max(minimum_quantity, basis x quantity_factor - included_quantity),
    rounded up to a whole number if round_up. Line cost = chargeable quantity x unit_cost_eur.
    For the fixed basis, "basis" is 1, so the quantity is the factor.
    """

    __tablename__ = "pricing_rules"

    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[RuleCategory] = mapped_column(_string_enum(RuleCategory, "category"))
    quantity_basis: Mapped[QuantityBasis] = mapped_column(
        _string_enum(QuantityBasis, "quantity_basis")
    )
    quantity_factor: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default="1")
    unit_label: Mapped[str] = mapped_column(String(20))  # shown on the quote: "kWp", "h", "km"
    unit_cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    included_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default="0")
    minimum_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default="0")
    round_up: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            Index("ix_pricing_rules_tenant_id_service_id", "tenant_id", "service_id"),
            Index(
                "uq_pricing_rules_tenant_id_service_id_name",
                "tenant_id",
                "service_id",
                func.lower(text("name")),
                unique=True,
            ),
            CheckConstraint("quantity_factor > 0", name="quantity_factor_positive"),
            CheckConstraint("unit_cost_eur >= 0", name="unit_cost_not_negative"),
            CheckConstraint("included_quantity >= 0", name="included_quantity_not_negative"),
            CheckConstraint("minimum_quantity >= 0", name="minimum_quantity_not_negative"),
        )


class ServiceArea(BaseMixin, TenantScopedMixin, Base):
    """Somewhere the business will travel to. Named places, not map polygons
    (spec BIZ-05); postal prefixes make matching an address reliable."""

    __tablename__ = "service_areas"

    name: Mapped[str] = mapped_column(String(120))  # "Berlin", "Brandenburg"
    country: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    # e.g. ["101", "102"]: an address matches if its postcode starts with one.
    postal_prefixes: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            Index(
                "uq_service_areas_tenant_id_name",
                "tenant_id",
                func.lower(text("name")),
                unique=True,
            ),
            CheckConstraint("country ~ '^[A-Z]{2}$'", name="country_iso2"),
            CheckConstraint("jsonb_typeof(postal_prefixes) = 'array'", name="postal_prefixes_array"),
        )


class InventoryItem(BaseMixin, TenantScopedMixin, Base):
    """Stock the business holds. Feasibility checks quantities against what a
    job needs (BIZ-06); reservations come with the jobs module in v2."""

    __tablename__ = "inventory_items"

    name: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str | None] = mapped_column(String(60))
    unit_label: Mapped[str] = mapped_column(String(20))  # panel, kWh, metre
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    # Below this, the owner is warned rather than blocked.
    low_stock_threshold: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            Index(
                "uq_inventory_items_tenant_id_name",
                "tenant_id",
                func.lower(text("name")),
                unique=True,
            ),
            CheckConstraint("quantity >= 0", name="quantity_not_negative"),
            CheckConstraint(
                "low_stock_threshold IS NULL OR low_stock_threshold >= 0",
                name="low_stock_threshold_not_negative",
            ),
        )


class Crew(BaseMixin, TenantScopedMixin, Base):
    """A team that can be sent to a job. Availability is weekly capacity in
    hours (BIZ-07): enough for the feasibility check, without a calendar."""

    __tablename__ = "crews"

    name: Mapped[str] = mapped_column(String(120))
    headcount: Mapped[int] = mapped_column(Integer, server_default="1")
    weekly_capacity_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    # Off means on leave, between hires, or otherwise not schedulable.
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            Index("uq_crews_tenant_id_name", "tenant_id", func.lower(text("name")), unique=True),
            CheckConstraint("headcount >= 1", name="headcount_positive"),
            CheckConstraint("weekly_capacity_hours > 0", name="weekly_capacity_positive"),
        )


class VerticalSettings(BaseMixin, TenantScopedMixin, Base):
    """The tunable half of a vertical's configuration (BIZ-08). The questions
    themselves live in code (rivon/business/verticals.py); these are the
    numbers each business adjusts. One row per tenant."""

    __tablename__ = "vertical_settings"

    vertical: Mapped[str] = mapped_column(String(32), server_default="solar")
    # How much a kWp generates in a year here, and how much roof it needs.
    annual_kwh_per_kwp: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="950")
    roof_area_m2_per_kwp: Mapped[Decimal] = mapped_column(Numeric(6, 2), server_default="5")
    # How many times the assistant chases a missing answer before handing the
    # conversation to the owner (CNV-04). 0 means hand over immediately.
    max_followups: Mapped[int] = mapped_column(Integer, server_default="2")

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return cls.tenant_table_args(
            UniqueConstraint("tenant_id"),
            CheckConstraint("vertical IN ('solar')", name="known_vertical"),
            CheckConstraint("annual_kwh_per_kwp > 0", name="annual_kwh_per_kwp_positive"),
            CheckConstraint("roof_area_m2_per_kwp > 0", name="roof_area_per_kwp_positive"),
            CheckConstraint("max_followups BETWEEN 0 AND 5", name="max_followups_range"),
        )
