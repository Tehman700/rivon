"""CHN-13: the endpoints behind the dashboard's Connect buttons."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from rivon.channels import oauth, service
from rivon.channels.messages import Channel
from rivon.channels.meta import MetaApiError, MetaGraph
from rivon.channels.models import ChannelConnection, ConnectionStatus
from rivon.channels.schemas import (
    ConnectCallbackIn,
    ConnectionOut,
    ConnectOutcomeOut,
    ConnectStartOut,
    SkippedOut,
    WhatsAppConnectedOut,
    WhatsAppSignupIn,
    WhatsAppStartOut,
)
from rivon.channels.service import ConnectionNotFound, OAuthStateInvalid
from rivon.config import Settings, get_settings
from rivon.platform.permissions import require_owner
from rivon.platform.security import Principal
from rivon.platform.tenancy import TenantContext, get_tenant_context

router = APIRouter(prefix="/channels", tags=["channels"])

Tenant = Annotated[TenantContext, Depends(get_tenant_context)]
Owner = Annotated[Principal, Depends(require_owner)]


def get_graph(settings: Annotated[Settings, Depends(get_settings)]) -> MetaGraph:
    """The Graph client for this deployment.

    Overridden in tests with a fake, which is how the whole connect flow is
    exercised without a Meta app.
    """
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Messaging channels are not configured on this deployment",
        )
    return MetaGraph(
        settings.meta_app_id,
        settings.meta_app_secret.get_secret_value(),
        version=settings.meta_graph_version,
    )


Graph = Annotated[MetaGraph, Depends(get_graph)]
Config = Annotated[Settings, Depends(get_settings)]


def _out(row: ChannelConnection) -> ConnectionOut:
    return ConnectionOut(
        id=row.id,
        provider=row.provider,
        external_id=row.external_id,
        display_name=row.display_name,
        status=row.status,
        status_detail=row.status_detail,
        granted_scopes=list(row.granted_scopes),
        expires_at=row.expires_at,
        connected_at=row.connected_at,
        needs_attention=row.status is ConnectionStatus.NEEDS_REAUTH,
    )


@router.get("", response_model=list[ConnectionOut])
async def list_channels(tenant: Tenant) -> list[ConnectionOut]:
    rows = await service.list_connections(tenant.session, tenant.tenant_id)
    return [_out(row) for row in rows]


@router.post("/connect/{provider}", response_model=ConnectStartOut)
async def start_connect(
    provider: Channel, tenant: Tenant, owner: Owner, graph: Graph, settings: Config
) -> ConnectStartOut:
    """Step one: where to send the customer."""
    if provider not in oauth.PAGE_ROUTE_CHANNELS:
        # WhatsApp goes through Embedded Signup, which is a different flow.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{provider.value} is not connected this way"
        )
    if not settings.meta_login_config_pages:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No Facebook login configuration is set for this deployment",
        )
    url = await oauth.begin_page_connection(
        tenant.session,
        tenant.tenant_id,
        provider,
        graph=graph,
        config_id=settings.meta_login_config_pages,
        redirect_uri=settings.meta_redirect_uri,
        started_by_user_id=owner.user_id,
    )
    return ConnectStartOut(authorize_url=url)


@router.post("/callback", response_model=ConnectOutcomeOut)
async def finish_connect(
    body: ConnectCallbackIn, tenant: Tenant, owner: Owner, graph: Graph, settings: Config
) -> ConnectOutcomeOut:
    """Step two: the customer is back from Meta with a code."""
    try:
        outcome = await oauth.complete_page_connection(
            tenant.session,
            tenant.tenant_id,
            code=body.code,
            state=body.state,
            graph=graph,
            redirect_uri=settings.meta_redirect_uri,
            connected_by_user_id=owner.user_id,
        )
    except OAuthStateInvalid as exc:
        # Stale, replayed, or not ours. Say so plainly and let them start again.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Connection could not be completed: {exc}")
    except oauth.ConnectFailed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except MetaApiError as exc:
        # Meta said no. Ours to report, not to retry blindly.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Facebook rejected the connection: {exc}")

    return ConnectOutcomeOut(
        connected=[_out(row) for row in outcome.connected],
        skipped=[SkippedOut(account=account, reason=reason) for account, reason in outcome.skipped],
    )


@router.post("/whatsapp/start", response_model=WhatsAppStartOut)
async def start_whatsapp_signup(tenant: Tenant, owner: Owner, settings: Config) -> WhatsAppStartOut:
    """What the browser needs to open Embedded Signup.

    A POST, owner only, so only someone allowed to connect a number learns
    which configuration to open.
    """
    if not settings.meta_app_id or not settings.meta_login_config_whatsapp:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "WhatsApp is not configured on this deployment",
        )
    return WhatsAppStartOut(
        app_id=settings.meta_app_id,
        config_id=settings.meta_login_config_whatsapp,
        graph_version=settings.meta_graph_version,
    )


@router.post("/whatsapp/complete", response_model=WhatsAppConnectedOut)
async def finish_whatsapp_signup(
    body: WhatsAppSignupIn, tenant: Tenant, owner: Owner, graph: Graph
) -> WhatsAppConnectedOut:
    """Finish Embedded Signup.

    No `state` to redeem: the browser hands the code straight back rather than
    going through a redirect, so what proves this request is genuine is the
    caller's own session. The code lives thirty seconds, so nothing is queued.
    """
    try:
        result = await oauth.complete_whatsapp_signup(
            tenant.session,
            tenant.tenant_id,
            code=body.code,
            waba_id=body.waba_id,
            phone_number_id=body.phone_number_id,
            graph=graph,
            pin=body.pin,
            connected_by_user_id=owner.user_id,
        )
    except oauth.ConnectFailed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except MetaApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp setup failed: {exc}")

    return WhatsAppConnectedOut(
        connection=_out(result.connection), registration_pin=result.registration_pin
    )


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_channel(
    connection_id: uuid.UUID, tenant: Tenant, owner: Owner, graph: Graph
) -> Response:
    try:
        await oauth.disconnect_and_unsubscribe(
            tenant.session, tenant.tenant_id, connection_id, graph=graph
        )
    except ConnectionNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such connection")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
