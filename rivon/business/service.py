"""The business module's interface. Other modules read business config
through these functions, never from the tables directly.

Every query filters by tenant_id as well as running under tenant RLS.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from rivon.business.models import (
    Business,
    Crew,
    InventoryItem,
    PricingRule,
    PricingSettings,
    Service,
    ServiceArea,
)
from rivon.business.schemas import (
    BusinessProfileIn,
    PricingRuleIn,
    PricingRuleUpdate,
    PricingSettingsIn,
    ServiceCreate,
    ServiceUpdate,
)


class DuplicateServiceName(Exception):
    pass


class DuplicateRuleName(Exception):
    pass


class DuplicateName(Exception):
    """A service area, stock item or crew already uses that name."""


class MarginBelowMinimum(Exception):
    """A target margin would sit below the business's minimum margin."""

    def __init__(self, minimum: Decimal, services: list[str]) -> None:
        self.minimum = minimum
        self.services = services
        super().__init__(
            f"target margin below the {minimum}% minimum margin (services: {', '.join(services)})"
        )


async def get_profile(session: AsyncSession, tenant_id: uuid.UUID) -> Business | None:
    return await session.scalar(select(Business).where(Business.tenant_id == tenant_id))


async def put_profile(
    session: AsyncSession, tenant_id: uuid.UUID, profile: BusinessProfileIn
) -> Business:
    """Create or fully replace the tenant's profile (a single atomic upsert)."""
    values = profile.model_dump(mode="python")
    values["business_hours"] = profile.business_hours.model_dump(mode="json")
    await session.execute(
        insert(Business)
        .values(id=uuid.uuid4(), tenant_id=tenant_id, **values)
        .on_conflict_do_update(
            index_elements=[Business.tenant_id], set_={**values, "updated_at": func.now()}
        )
    )
    business = await get_profile(session, tenant_id)
    assert business is not None
    await session.refresh(business)
    return business


async def list_services(
    session: AsyncSession, tenant_id: uuid.UUID, *, include_archived: bool = False
) -> list[Service]:
    query = select(Service).where(Service.tenant_id == tenant_id)
    if not include_archived:
        query = query.where(Service.archived_at.is_(None))
    return list((await session.scalars(query.order_by(func.lower(Service.name)))).all())


async def get_service(
    session: AsyncSession, tenant_id: uuid.UUID, service_id: uuid.UUID
) -> Service | None:
    return await session.scalar(
        select(Service).where(Service.tenant_id == tenant_id, Service.id == service_id)
    )


_UNIQUE_NAME_ERRORS: dict[str, type[Exception]] = {
    "uq_services_tenant_id_name_active": DuplicateServiceName,
    "uq_pricing_rules_tenant_id_service_id_name": DuplicateRuleName,
    "uq_service_areas_tenant_id_name": DuplicateName,
    "uq_inventory_items_tenant_id_name": DuplicateName,
    "uq_crews_tenant_id_name": DuplicateName,
}


async def _flush_checking_names(session: AsyncSession) -> None:
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        for constraint, error in _UNIQUE_NAME_ERRORS.items():
            if constraint in str(exc.orig):
                raise error() from exc
        raise


async def _check_margin_override(
    session: AsyncSession, tenant_id: uuid.UUID, margin: Decimal | None, service_name: str
) -> None:
    if margin is None:
        return
    settings = await get_pricing_settings(session, tenant_id)
    if settings is not None and margin < settings.minimum_margin_percent:
        raise MarginBelowMinimum(settings.minimum_margin_percent, [service_name])


async def create_service(session: AsyncSession, tenant_id: uuid.UUID, data: ServiceCreate) -> Service:
    await _check_margin_override(session, tenant_id, data.target_margin_percent, data.name)
    service = Service(id=uuid.uuid4(), tenant_id=tenant_id, **data.model_dump())
    session.add(service)
    await _flush_checking_names(session)
    await session.refresh(service)
    return service


async def update_service(session: AsyncSession, service: Service, changes: ServiceUpdate) -> Service:
    fields = changes.model_fields_set
    for field in fields & {"name", "description", "target_margin_percent", "vat_rate_percent"}:
        setattr(service, field, getattr(changes, field))
    if "archived" in fields:
        if changes.archived and service.archived_at is None:
            service.archived_at = datetime.now(UTC)
        elif not changes.archived:
            service.archived_at = None
    await _check_margin_override(session, service.tenant_id, service.target_margin_percent, service.name)
    await _flush_checking_names(session)
    await session.refresh(service)
    return service


# --- Pricing (BIZ-03) ---------------------------------------------------------


async def get_pricing_settings(session: AsyncSession, tenant_id: uuid.UUID) -> PricingSettings | None:
    return await session.scalar(select(PricingSettings).where(PricingSettings.tenant_id == tenant_id))


async def put_pricing_settings(
    session: AsyncSession, tenant_id: uuid.UUID, data: PricingSettingsIn
) -> PricingSettings:
    """Create or replace the pricing settings. Refuses a minimum margin that
    would leave any service's own target margin below it."""
    below = (
        await session.scalars(
            select(Service.name)
            .where(
                Service.tenant_id == tenant_id,
                Service.target_margin_percent < data.minimum_margin_percent,
            )
            .order_by(func.lower(Service.name))
        )
    ).all()
    if below:
        raise MarginBelowMinimum(data.minimum_margin_percent, list(below))

    values = data.model_dump()
    await session.execute(
        insert(PricingSettings)
        .values(id=uuid.uuid4(), tenant_id=tenant_id, **values)
        .on_conflict_do_update(
            index_elements=[PricingSettings.tenant_id], set_={**values, "updated_at": func.now()}
        )
    )
    settings = await get_pricing_settings(session, tenant_id)
    assert settings is not None
    await session.refresh(settings)
    return settings


async def list_pricing_rules(session: AsyncSession, service: Service) -> list[PricingRule]:
    rows = await session.scalars(
        select(PricingRule)
        .where(PricingRule.tenant_id == service.tenant_id, PricingRule.service_id == service.id)
        .order_by(PricingRule.sort_order, func.lower(PricingRule.name))
    )
    return list(rows.all())


async def get_pricing_rule(
    session: AsyncSession, service: Service, rule_id: uuid.UUID
) -> PricingRule | None:
    return await session.scalar(
        select(PricingRule).where(
            PricingRule.tenant_id == service.tenant_id,
            PricingRule.service_id == service.id,
            PricingRule.id == rule_id,
        )
    )


async def create_pricing_rule(session: AsyncSession, service: Service, data: PricingRuleIn) -> PricingRule:
    rule = PricingRule(
        id=uuid.uuid4(), tenant_id=service.tenant_id, service_id=service.id, **data.model_dump()
    )
    session.add(rule)
    await _flush_checking_names(session)
    await session.refresh(rule)
    return rule


async def update_pricing_rule(
    session: AsyncSession, rule: PricingRule, changes: PricingRuleUpdate
) -> PricingRule:
    for field in changes.model_fields_set:
        setattr(rule, field, getattr(changes, field))
    await _flush_checking_names(session)
    await session.refresh(rule)
    return rule


async def delete_pricing_rule(session: AsyncSession, rule: PricingRule) -> None:
    """Hard delete: quotations keep their own copy of the lines they priced."""
    await session.delete(rule)
    await session.flush()


# --- Capacity (BIZ-05/06/07) --------------------------------------------------
#
# Three near-identical collections, so they share these helpers rather than
# repeating the same five functions three times.

CapacityModel = TypeVar("CapacityModel", ServiceArea, InventoryItem, Crew)


async def list_capacity(
    session: AsyncSession, model: type[CapacityModel], tenant_id: uuid.UUID
) -> list[CapacityModel]:
    rows = await session.scalars(
        select(model).where(model.tenant_id == tenant_id).order_by(func.lower(model.name))
    )
    return list(rows.all())


async def get_capacity(
    session: AsyncSession, model: type[CapacityModel], tenant_id: uuid.UUID, row_id: uuid.UUID
) -> CapacityModel | None:
    return await session.scalar(
        select(model).where(model.tenant_id == tenant_id, model.id == row_id)
    )


async def create_capacity(
    session: AsyncSession, model: type[CapacityModel], tenant_id: uuid.UUID, data: BaseModel
) -> CapacityModel:
    row = model(id=uuid.uuid4(), tenant_id=tenant_id, **data.model_dump())
    session.add(row)
    await _flush_checking_names(session)
    await session.refresh(row)
    return row


async def update_capacity(
    session: AsyncSession, row: CapacityModel, changes: BaseModel
) -> CapacityModel:
    for field in changes.model_fields_set:
        setattr(row, field, getattr(changes, field))
    await _flush_checking_names(session)
    await session.refresh(row)
    return row


async def delete_capacity(session: AsyncSession, row: CapacityModel) -> None:
    await session.delete(row)
    await session.flush()
