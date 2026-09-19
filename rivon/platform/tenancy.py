"""Tenant context: which tenant a unit of work runs as.

The tenant ID is set with `set_config(..., is_local => true)`, which scopes it
to the current transaction. A connection-scoped `SET` would survive the
connection's return to the pool and leak into the next request that borrows
it. Everything that touches tenant data runs inside `tenant_transaction`.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from rivon.config import Settings, get_settings
from rivon.platform.models import Region, Tenant, TenantStatus
from rivon.platform.security import Principal, decode_access_token

TENANT_SETTING = "app.current_tenant_id"


async def set_current_tenant(conn: AsyncSession | AsyncConnection, tenant_id: uuid.UUID) -> None:
    """Set the tenant for the transaction `conn` is currently in."""
    await conn.execute(select(func.set_config(TENANT_SETTING, str(tenant_id), True)))


@asynccontextmanager
async def tenant_transaction(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> AsyncIterator[AsyncSession]:
    """Open a session and transaction scoped to one tenant. Commits on success."""
    async with sessionmaker() as session, session.begin():
        await set_current_tenant(session, tenant_id)
        yield session


@dataclass(frozen=True)
class TenantContext:
    tenant_id: uuid.UUID
    region: Region
    session: AsyncSession


_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """The caller, from a verified access token in the Authorization header."""
    if credentials is None:
        raise _unauthorized()
    try:
        return decode_access_token(credentials.credentials, settings.jwt_secret.get_secret_value())
    except jwt.InvalidTokenError:
        raise _unauthorized() from None


async def get_current_tenant_id(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> uuid.UUID:
    """Which tenant the caller acts as: the tenant claim of their access token."""
    return principal.tenant_id


async def get_tenant_context(
    request: Request, tenant_id: Annotated[uuid.UUID, Depends(get_current_tenant_id)]
) -> AsyncIterator[TenantContext]:
    """FastAPI dependency: a tenant-scoped transaction for the request."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with tenant_transaction(sessionmaker, tenant_id) as session:
        # Application-level filter; RLS on `tenants` also limits this to the one row.
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if tenant is None or tenant.status != TenantStatus.ACTIVE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant is not active")
        yield TenantContext(tenant_id=tenant.id, region=tenant.region, session=session)
