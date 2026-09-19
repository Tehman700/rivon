import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from rivon.business import service as business
from rivon.business.models import PricingRule, Service
from rivon.business.schemas import (
    BusinessProfileIn,
    BusinessProfileOut,
    PricingRuleIn,
    PricingRuleOut,
    PricingRuleUpdate,
    PricingSettingsIn,
    PricingSettingsOut,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
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
