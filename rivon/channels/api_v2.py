"""BETA endpoints for the Page picker (see `picker.py`).

Mounted at `/channels/v2`, beside the current flow, sharing nothing with it but
the storage both end in. When the beta is proven, the current flow's endpoints
either call into `picker.py` or are removed; until then, neither can break the
other.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from rivon.channels import picker
from rivon.channels.api import Config, Graph, Owner, Tenant, _out
from rivon.channels.meta import MetaApiError
from rivon.channels.oauth import ConnectFailed
from rivon.channels.schemas import (
    ConnectCallbackIn,
    ConnectionOut,
    ConnectStartOut,
    PickerConnectIn,
    PickerInstagramOut,
    PickerPageOut,
    PickerPagesOut,
    PickerSessionOut,
)
from rivon.channels.service import OAuthStateInvalid
from rivon.config import Settings

router = APIRouter(prefix="/channels/v2", tags=["channels (beta)"])


def _require_beta(settings: Settings) -> str:
    if not settings.meta_login_config_pages_v2:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The new connect flow is not configured on this deployment",
        )
    return settings.meta_login_config_pages_v2


def _meta_failure(exc: MetaApiError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Facebook rejected the request: {exc}")


@router.post("/connect", response_model=ConnectStartOut)
async def start(tenant: Tenant, owner: Owner, graph: Graph, settings: Config) -> ConnectStartOut:
    config_id = _require_beta(settings)
    url = await picker.begin(
        tenant.session,
        tenant.tenant_id,
        graph=graph,
        config_id=config_id,
        redirect_uri=settings.meta_redirect_uri_v2,
        started_by_user_id=owner.user_id,
    )
    return ConnectStartOut(authorize_url=url)


@router.post("/callback", response_model=PickerSessionOut)
async def callback(
    body: ConnectCallbackIn, tenant: Tenant, owner: Owner, graph: Graph, settings: Config
) -> PickerSessionOut:
    _require_beta(settings)
    try:
        opened = await picker.open_session(
            tenant.session,
            tenant.tenant_id,
            code=body.code,
            state=body.state,
            graph=graph,
            redirect_uri=settings.meta_redirect_uri_v2,
            started_by_user_id=owner.user_id,
        )
    except OAuthStateInvalid as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Connection could not be completed: {exc}")
    except ConnectFailed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except MetaApiError as exc:
        raise _meta_failure(exc)
    return PickerSessionOut(session_id=opened.id, expires_at=opened.expires_at)


@router.get("/sessions/{session_id}/pages", response_model=PickerPagesOut)
async def pages(
    session_id: uuid.UUID, tenant: Tenant, owner: Owner, graph: Graph
) -> PickerPagesOut:
    """Every Page the person manages right now. Calling it again is Refresh."""
    try:
        opened, listed = await picker.list_pages(
            tenant.session, tenant.tenant_id, session_id, graph=graph
        )
    except ConnectFailed as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc))
    except MetaApiError as exc:
        raise _meta_failure(exc)
    return PickerPagesOut(
        pages=[
            PickerPageOut(
                id=item.page.id,
                name=item.page.name,
                instagram=(
                    PickerInstagramOut(id=item.page.instagram_id, username=item.page.instagram_username)
                    if item.page.instagram_id
                    else None
                ),
                messenger_status=item.messenger_status,
                instagram_status=item.instagram_status,
            )
            for item in listed
        ],
        create_page_url=picker.CREATE_PAGE_URL,
        expires_at=opened.expires_at,
    )


@router.post("/sessions/{session_id}/connect", response_model=list[ConnectionOut])
async def connect(
    session_id: uuid.UUID, body: PickerConnectIn, tenant: Tenant, owner: Owner, graph: Graph
) -> list[ConnectionOut]:
    try:
        connected = await picker.connect_page(
            tenant.session,
            tenant.tenant_id,
            session_id,
            page_id=body.page_id,
            include_instagram=body.include_instagram,
            graph=graph,
            connected_by_user_id=owner.user_id,
        )
    except picker.SessionExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc))
    except ConnectFailed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except MetaApiError as exc:
        raise _meta_failure(exc)
    return [_out(row) for row in connected]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def finish(session_id: uuid.UUID, tenant: Tenant, owner: Owner) -> Response:
    await picker.close(tenant.session, tenant.tenant_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

