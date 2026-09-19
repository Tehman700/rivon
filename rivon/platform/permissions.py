"""Role checks for routes. Minimal until PLT-03 (full RBAC) replaces it.

The role comes from the access token, so a role change takes effect when the
user's current access token expires (at most its TTL, 15 minutes).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from rivon.platform.models import UserRole
from rivon.platform.security import Principal
from rivon.platform.tenancy import get_current_principal


def require_roles(*roles: UserRole) -> Callable[..., Awaitable[Principal]]:
    async def check(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role can't make this change")
        return principal

    return check


require_owner = require_roles(UserRole.OWNER)
