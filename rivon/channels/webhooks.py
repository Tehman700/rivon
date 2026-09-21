"""CHN-02: the three URLs Meta calls.

One endpoint per platform, serving every customer: Meta has no idea which
business a delivery belongs to, so working that out is the first thing that
happens inside (see `inbound.py`).

These are the only unauthenticated endpoints in the service. What stands in for
authentication is the signature on the body, checked before the payload is even
parsed, so an unsigned request never reaches the database.

After a valid signature the answer is always 200, whatever we made of the
contents. Meta retries anything else, and a retry of something we could not
read delivers exactly the same thing again — while a retry of something we
*did* read risks a second reply to a real person.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rivon.channels import inbound
from rivon.channels.messages import Channel
from rivon.config import Settings, get_settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

Config = Annotated[Settings, Depends(get_settings)]

#: The URL segment Meta is configured with, and the channel it means.
WEBHOOK_CHANNELS = {
    "whatsapp": Channel.WHATSAPP,
    "messenger": Channel.MESSENGER,
    "instagram": Channel.INSTAGRAM,
}


def _channel(name: str) -> Channel:
    try:
        return WEBHOOK_CHANNELS[name]
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such webhook") from None


@router.get("/{name}")
async def verify_webhook(name: str, request: Request, settings: Config) -> Response:
    """Meta's one-time check when the URL is first configured."""
    _channel(name)
    if not settings.meta_verify_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks are not configured on this deployment"
        )
    challenge = inbound.verify_challenge(
        dict(request.query_params), settings.meta_verify_token.get_secret_value()
    )
    if challenge is None:
        # Wrong token, or not a subscription check. Confirming the URL to
        # someone else would let them point their own app at it.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")
    return Response(content=challenge, media_type="text/plain")


@router.post("/{name}")
async def receive_webhook(name: str, request: Request, settings: Config) -> Response:
    channel = _channel(name)
    if not settings.meta_app_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks are not configured on this deployment"
        )

    # The raw bytes, before anything parses them: the signature is over exactly
    # what was sent, and re-serialising the JSON would change it.
    raw = await request.body()
    if not inbound.signature_is_valid(
        raw, request.headers.get(inbound.SIGNATURE_HEADER), settings.meta_app_secret.get_secret_value()
    ):
        log.warning("rejected an unsigned or mis-signed %s webhook", channel)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")

    try:
        payload = json.loads(raw)
    except ValueError:
        log.warning("%s webhook body was not JSON", channel)
        return Response(status_code=status.HTTP_200_OK)
    if not isinstance(payload, dict):
        return Response(status_code=status.HTTP_200_OK)

    summary = await inbound.receive(request.app.state.sessionmaker, channel, payload)
    if summary.total or summary.unparsed:
        log.info(
            "%s webhook: %d stored, %d duplicate, %d unrouted",
            channel, summary.stored, summary.duplicates, summary.unrouted,
        )
    return Response(status_code=status.HTTP_200_OK)
