import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from rivon.business import service as business
from rivon.business.models import Service
from rivon.business.schemas import (
    BusinessProfileIn,
    BusinessProfileOut,
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
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _duplicate_name() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "An active service with this name already exists")


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
