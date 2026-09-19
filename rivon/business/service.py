"""The business module's interface. Other modules read business config
through these functions, never from the tables directly.

Every query filters by tenant_id as well as running under tenant RLS.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rivon.business.models import Business, Service
from rivon.business.schemas import BusinessProfileIn, ServiceCreate, ServiceUpdate


class DuplicateServiceName(Exception):
    pass


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


async def _flush_checking_name(session: AsyncSession) -> None:
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        if "uq_services_tenant_id_name_active" in str(exc.orig):
            raise DuplicateServiceName() from exc
        raise


async def create_service(session: AsyncSession, tenant_id: uuid.UUID, data: ServiceCreate) -> Service:
    service = Service(id=uuid.uuid4(), tenant_id=tenant_id, name=data.name, description=data.description)
    session.add(service)
    await _flush_checking_name(session)
    await session.refresh(service)
    return service


async def update_service(session: AsyncSession, service: Service, changes: ServiceUpdate) -> Service:
    fields = changes.model_fields_set
    if "name" in fields and changes.name is not None:
        service.name = changes.name
    if "description" in fields:
        service.description = changes.description
    if "archived" in fields:
        if changes.archived and service.archived_at is None:
            service.archived_at = datetime.now(UTC)
        elif not changes.archived:
            service.archived_at = None
    await _flush_checking_name(session)
    await session.refresh(service)
    return service
