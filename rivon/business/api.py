import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from rivon.business import service as business
from rivon.business.models import Crew, InventoryItem, PricingRule, Service, ServiceArea
from rivon.business.verticals import VERTICALS, estimate_system_size
from rivon.business.schemas import (
    BusinessProfileIn,
    BusinessProfileOut,
    CrewIn,
    CrewOut,
    CrewUpdate,
    InventoryItemIn,
    InventoryItemOut,
    InventoryItemUpdate,
    PricingRuleIn,
    PricingRuleOut,
    PricingRuleUpdate,
    PricingSettingsIn,
    PricingSettingsOut,
    FieldGroupOut,
    FieldOut,
    ServiceAreaIn,
    ServiceAreaOut,
    ServiceAreaUpdate,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    SizeEstimateOut,
    SizeEstimateRequest,
    VerticalOut,
    VerticalSettingsIn,
    VerticalSettingsOut,
)
from rivon.platform.permissions import require_owner
from rivon.platform.security import Principal
from rivon.platform.tenancy import TenantContext, get_tenant_context

router = APIRouter(prefix="/business", tags=["business"])

Tenant = Annotated[TenantContext, Depends(get_tenant_context)]
Owner = Annotated[Principal, Depends(require_owner)]


def _service_out(row: Service) -> ServiceOut:
    return ServiceOut(
        id=row.id,
        name=row.name,
        description=row.description,
        archived=row.archived_at is not None,
        archived_at=row.archived_at,
        target_margin_percent=row.target_margin_percent,
        vat_rate_percent=row.vat_rate_percent,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _duplicate_name() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "An active service with this name already exists")


def _margin_conflict(exc: business.MarginBelowMinimum) -> HTTPException:
    message = str(exc)
    return HTTPException(status.HTTP_409_CONFLICT, message[:1].upper() + message[1:])


# --- Profile (BIZ-01) ---------------------------------------------------------


@router.get("/profile")
async def get_profile(ctx: Tenant) -> BusinessProfileOut:
    profile = await business.get_profile(ctx.session, ctx.tenant_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business profile not set up yet")
    return BusinessProfileOut.model_validate(profile)


@router.put("/profile")
async def put_profile(body: BusinessProfileIn, ctx: Tenant, _: Owner) -> BusinessProfileOut:
    profile = await business.put_profile(ctx.session, ctx.tenant_id, body)
    return BusinessProfileOut.model_validate(profile)


# --- Services (BIZ-02) --------------------------------------------------------


@router.get("/services")
async def list_services(ctx: Tenant, include_archived: bool = False) -> list[ServiceOut]:
    rows = await business.list_services(ctx.session, ctx.tenant_id, include_archived=include_archived)
    return [_service_out(row) for row in rows]


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(body: ServiceCreate, ctx: Tenant, _: Owner) -> ServiceOut:
    try:
        return _service_out(await business.create_service(ctx.session, ctx.tenant_id, body))
    except business.DuplicateServiceName:
        raise _duplicate_name() from None
    except business.MarginBelowMinimum as exc:
        raise _margin_conflict(exc) from None


async def _service_or_404(ctx: TenantContext, service_id: uuid.UUID) -> Service:
    row = await business.get_service(ctx.session, ctx.tenant_id, service_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    return row


@router.get("/services/{service_id}")
async def get_service(service_id: uuid.UUID, ctx: Tenant) -> ServiceOut:
    return _service_out(await _service_or_404(ctx, service_id))


@router.patch("/services/{service_id}")
async def update_service(
    service_id: uuid.UUID, body: ServiceUpdate, ctx: Tenant, _: Owner
) -> ServiceOut:
    row = await _service_or_404(ctx, service_id)
    try:
        return _service_out(await business.update_service(ctx.session, row, body))
    except business.DuplicateServiceName:
        raise _duplicate_name() from None
    except business.MarginBelowMinimum as exc:
        raise _margin_conflict(exc) from None


# --- Pricing (BIZ-03) ---------------------------------------------------------


@router.get("/pricing-settings")
async def get_pricing_settings(ctx: Tenant) -> PricingSettingsOut:
    settings = await business.get_pricing_settings(ctx.session, ctx.tenant_id)
    if settings is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pricing settings not set up yet")
    return PricingSettingsOut.model_validate(settings)


@router.put("/pricing-settings")
async def put_pricing_settings(body: PricingSettingsIn, ctx: Tenant, _: Owner) -> PricingSettingsOut:
    try:
        settings = await business.put_pricing_settings(ctx.session, ctx.tenant_id, body)
    except business.MarginBelowMinimum as exc:
        raise _margin_conflict(exc) from None
    return PricingSettingsOut.model_validate(settings)


def _duplicate_rule() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "This service already has a line with that name")


async def _rule_or_404(ctx: TenantContext, service_id: uuid.UUID, rule_id: uuid.UUID) -> PricingRule:
    service = await _service_or_404(ctx, service_id)
    rule = await business.get_pricing_rule(ctx.session, service, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pricing rule not found")
    return rule


@router.get("/services/{service_id}/pricing-rules")
async def list_pricing_rules(service_id: uuid.UUID, ctx: Tenant) -> list[PricingRuleOut]:
    service = await _service_or_404(ctx, service_id)
    rules = await business.list_pricing_rules(ctx.session, service)
    return [PricingRuleOut.model_validate(rule) for rule in rules]


@router.post("/services/{service_id}/pricing-rules", status_code=status.HTTP_201_CREATED)
async def create_pricing_rule(
    service_id: uuid.UUID, body: PricingRuleIn, ctx: Tenant, _: Owner
) -> PricingRuleOut:
    service = await _service_or_404(ctx, service_id)
    try:
        rule = await business.create_pricing_rule(ctx.session, service, body)
    except business.DuplicateRuleName:
        raise _duplicate_rule() from None
    return PricingRuleOut.model_validate(rule)


@router.patch("/services/{service_id}/pricing-rules/{rule_id}")
async def update_pricing_rule(
    service_id: uuid.UUID, rule_id: uuid.UUID, body: PricingRuleUpdate, ctx: Tenant, _: Owner
) -> PricingRuleOut:
    rule = await _rule_or_404(ctx, service_id, rule_id)
    try:
        rule = await business.update_pricing_rule(ctx.session, rule, body)
    except business.DuplicateRuleName:
        raise _duplicate_rule() from None
    return PricingRuleOut.model_validate(rule)


@router.delete(
    "/services/{service_id}/pricing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_pricing_rule(
    service_id: uuid.UUID, rule_id: uuid.UUID, ctx: Tenant, _: Owner
) -> Response:
    await business.delete_pricing_rule(ctx.session, await _rule_or_404(ctx, service_id, rule_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Capacity: service areas, inventory, crews (BIZ-05/06/07) -----------------


def _duplicate(what: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, f"You already have {what} with that name")


async def _capacity_or_404(
    ctx: TenantContext, model: type, row_id: uuid.UUID, what: str
):  # type: ignore[no-untyped-def]
    row = await business.get_capacity(ctx.session, model, ctx.tenant_id, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")
    return row


@router.get("/service-areas")
async def list_service_areas(ctx: Tenant) -> list[ServiceAreaOut]:
    rows = await business.list_capacity(ctx.session, ServiceArea, ctx.tenant_id)
    return [ServiceAreaOut.model_validate(row) for row in rows]


@router.post("/service-areas", status_code=status.HTTP_201_CREATED)
async def create_service_area(body: ServiceAreaIn, ctx: Tenant, _: Owner) -> ServiceAreaOut:
    try:
        row = await business.create_capacity(ctx.session, ServiceArea, ctx.tenant_id, body)
    except business.DuplicateName:
        raise _duplicate("a service area") from None
    return ServiceAreaOut.model_validate(row)


@router.patch("/service-areas/{area_id}")
async def update_service_area(
    area_id: uuid.UUID, body: ServiceAreaUpdate, ctx: Tenant, _: Owner
) -> ServiceAreaOut:
    row = await _capacity_or_404(ctx, ServiceArea, area_id, "Service area")
    try:
        row = await business.update_capacity(ctx.session, row, body)
    except business.DuplicateName:
        raise _duplicate("a service area") from None
    return ServiceAreaOut.model_validate(row)


@router.delete("/service-areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_area(area_id: uuid.UUID, ctx: Tenant, _: Owner) -> Response:
    await business.delete_capacity(ctx.session, await _capacity_or_404(ctx, ServiceArea, area_id, "Service area"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/inventory")
async def list_inventory(ctx: Tenant) -> list[InventoryItemOut]:
    rows = await business.list_capacity(ctx.session, InventoryItem, ctx.tenant_id)
    return [InventoryItemOut.model_validate(row) for row in rows]


@router.post("/inventory", status_code=status.HTTP_201_CREATED)
async def create_inventory_item(body: InventoryItemIn, ctx: Tenant, _: Owner) -> InventoryItemOut:
    try:
        row = await business.create_capacity(ctx.session, InventoryItem, ctx.tenant_id, body)
    except business.DuplicateName:
        raise _duplicate("an item") from None
    return InventoryItemOut.model_validate(row)


@router.patch("/inventory/{item_id}")
async def update_inventory_item(
    item_id: uuid.UUID, body: InventoryItemUpdate, ctx: Tenant, _: Owner
) -> InventoryItemOut:
    row = await _capacity_or_404(ctx, InventoryItem, item_id, "Item")
    try:
        row = await business.update_capacity(ctx.session, row, body)
    except business.DuplicateName:
        raise _duplicate("an item") from None
    return InventoryItemOut.model_validate(row)


@router.delete("/inventory/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(item_id: uuid.UUID, ctx: Tenant, _: Owner) -> Response:
    await business.delete_capacity(ctx.session, await _capacity_or_404(ctx, InventoryItem, item_id, "Item"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/crews")
async def list_crews(ctx: Tenant) -> list[CrewOut]:
    rows = await business.list_capacity(ctx.session, Crew, ctx.tenant_id)
    return [CrewOut.model_validate(row) for row in rows]


@router.post("/crews", status_code=status.HTTP_201_CREATED)
async def create_crew(body: CrewIn, ctx: Tenant, _: Owner) -> CrewOut:
    try:
        row = await business.create_capacity(ctx.session, Crew, ctx.tenant_id, body)
    except business.DuplicateName:
        raise _duplicate("a crew") from None
    return CrewOut.model_validate(row)


@router.patch("/crews/{crew_id}")
async def update_crew(crew_id: uuid.UUID, body: CrewUpdate, ctx: Tenant, _: Owner) -> CrewOut:
    row = await _capacity_or_404(ctx, Crew, crew_id, "Crew")
    try:
        row = await business.update_capacity(ctx.session, row, body)
    except business.DuplicateName:
        raise _duplicate("a crew") from None
    return CrewOut.model_validate(row)


@router.delete("/crews/{crew_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_crew(crew_id: uuid.UUID, ctx: Tenant, _: Owner) -> Response:
    await business.delete_capacity(ctx.session, await _capacity_or_404(ctx, Crew, crew_id, "Crew"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Vertical configuration (BIZ-08) -----------------------------------------


def _vertical_out(settings) -> VerticalOut:  # type: ignore[no-untyped-def]
    vertical = VERTICALS[settings.vertical]
    return VerticalOut(
        key=vertical.key,
        label=vertical.label,
        groups=[
            FieldGroupOut(
                key=group.key,
                label=group.label,
                fields=[
                    FieldOut(
                        name=f.name,
                        kind=f.kind.value,
                        label=f.label,
                        question=f.question,
                        unit=f.unit,
                        choices=list(f.choices),
                        required=f.required,
                    )
                    for f in group.fields
                ],
            )
            for group in vertical.groups
        ],
        required_any_of=[list(group) for group in vertical.required_any_of],
        settings=VerticalSettingsOut.model_validate(settings),
    )


@router.get("/vertical")
async def get_vertical(ctx: Tenant) -> VerticalOut:
    """What the assistant asks, plus this business's tuning."""
    settings = await business.ensure_vertical_settings(ctx.session, ctx.tenant_id)
    return _vertical_out(settings)


@router.put("/vertical/settings")
async def put_vertical_settings(body: VerticalSettingsIn, ctx: Tenant, _: Owner) -> VerticalOut:
    settings = await business.put_vertical_settings(ctx.session, ctx.tenant_id, body)
    return _vertical_out(settings)


@router.post("/vertical/size-estimate")
async def preview_size_estimate(body: SizeEstimateRequest, ctx: Tenant) -> SizeEstimateOut:
    """Show how the sizing rule behaves with this business's numbers.

    The same arithmetic quotations will use: no model is involved, so the
    owner can check it and adjust the constants until it matches their judgement.
    """
    settings = await business.ensure_vertical_settings(ctx.session, ctx.tenant_id)
    requirements = body.model_dump(exclude_none=True)
    estimate = estimate_system_size(requirements, business.sizing_constants(settings))
    return SizeEstimateOut(
        system_size_kwp=estimate.system_size_kwp,
        basis=estimate.basis,
        explanation=estimate.explanation,
        missing_for_quote=VERTICALS[settings.vertical].missing_for_quote(requirements),
    )
