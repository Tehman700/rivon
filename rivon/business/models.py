from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
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


class ProjectSizeUnit(StrEnum):
    """Unit a vertical measures job size in. Each vertical adds its own (BIZ-08)."""

    KWP = "kWp"  # solar: peak kilowatts


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
        )
