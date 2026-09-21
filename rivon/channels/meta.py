"""CHN-13: talking to Meta's Graph API.

Everything Rivon needs from Meta during a connect flow, and nothing else. The
class holds no state about a tenant and makes no decisions — it translates our
questions into Graph calls and Graph's answers into small frozen records. What
to do with those answers lives in `oauth.py`.

The HTTP call itself is injected, so the whole flow can be exercised against a
fake Graph in tests: no network, no app secret, no live Meta app (hard rule 4).

One deliberate omission: no method here takes a tenant id or touches the
database. A credential arrives as an argument and leaves as a return value.
"""

import urllib.parse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

GRAPH_HOST = "https://graph.facebook.com"
DIALOG_HOST = "https://www.facebook.com"

#: What a Page must be subscribed to before its messages reach our webhook.
PAGE_WEBHOOK_FIELDS = ("messages", "messaging_postbacks")

#: Transport: (method, url, params, data) -> decoded JSON.
Transport = Callable[[str, str, dict[str, Any], dict[str, Any] | None], Awaitable[dict[str, Any]]]


class MetaApiError(Exception):
    """Graph answered with an error.

    Carries Meta's own code and subcode because they are what distinguish "the
    customer revoked us" from "we asked for something wrong", and the two need
    opposite responses.
    """

    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.subcode = subcode

    @property
    def is_auth_failure(self) -> bool:
        """Code 190 is Meta's "this token no longer works", whatever the reason."""
        return self.code == 190


@dataclass(frozen=True, slots=True)
class TokenGrant:
    access_token: str
    token_type: str = "business_system_user"
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TokenInfo:
    """What Meta says about a token we hold."""

    scopes: tuple[str, ...]
    expires_at: datetime | None
    is_valid: bool


@dataclass(frozen=True, slots=True)
class GrantedPage:
    """A Page the customer chose to share, and its own access token."""

    id: str
    name: str
    access_token: str
    instagram_id: str | None = None
    instagram_username: str | None = None


@dataclass(frozen=True, slots=True)
class GraphCall:
    """One request, recorded for tests and for debugging a live connect."""

    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)


def _expiry(seconds: Any) -> datetime | None:
    """Meta reports either a lifetime in seconds or an absolute timestamp.

    Zero means "never expires", which is the usual answer for a business
    integration token — and must not be read as "expired in 1970".
    """
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return datetime.fromtimestamp(value, UTC)


class MetaGraph:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        version: str = "v25.0",
        transport: Transport | None = None,
    ) -> None:
        self.app_id = app_id
        self.version = version
        self._app_secret = app_secret
        self._transport = transport or _httpx_transport

    # --- The dialog the customer sees ----------------------------------------

    def authorize_url(self, *, config_id: str, state: str, redirect_uri: str) -> str:
        """Where to send the customer to choose what they are sharing.

        `override_default_response_type` is what makes the dialog return a code
        for a server-side exchange instead of a token in the browser, which is
        the whole reason the secret never leaves our side.
        """
        query = urllib.parse.urlencode(
            {
                "client_id": self.app_id,
                "config_id": config_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "response_type": "code",
                "override_default_response_type": "true",
            }
        )
        return f"{DIALOG_HOST}/{self.version}/dialog/oauth?{query}"

    # --- Credentials ---------------------------------------------------------

    async def exchange_code(self, code: str, *, redirect_uri: str) -> TokenGrant:
        """Trade the callback's code for the customer's own token.

        Server to server, with the app secret. On WhatsApp's Embedded Signup
        this code lives 30 seconds, so nothing may sit between the callback and
        this call.
        """
        payload = await self._get(
            "oauth/access_token",
            {
                "client_id": self.app_id,
                "client_secret": self._app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        token = payload.get("access_token")
        if not token:
            raise MetaApiError("Meta returned no access token for that code")
        return TokenGrant(
            access_token=token,
            token_type=payload.get("token_type") or "business_system_user",
            expires_at=_expiry(payload.get("expires_in")),
        )

    async def inspect_token(self, token: str) -> TokenInfo:
        """What the customer actually granted.

        Asking rather than assuming: a customer can untick a permission in the
        dialog, and we would rather refuse the connection now than discover it
        as a 403 the first time a real message needs answering.
        """
        payload = await self._get(
            "debug_token", {"input_token": token, "access_token": self._app_token()}
        )
        data = payload.get("data") or {}
        return TokenInfo(
            scopes=tuple(data.get("scopes") or ()),
            expires_at=_expiry(data.get("expires_at")),
            is_valid=bool(data.get("is_valid")),
        )

    # --- Assets --------------------------------------------------------------

    async def granted_pages(self, token: str) -> list[GrantedPage]:
        """The Pages the customer shared, each with its own token.

        Instagram comes back attached to its Page, which is why we take the Page
        route: one call, one consent screen, and no second token to refresh.
        """
        payload = await self._get(
            "me/accounts",
            {
                "access_token": token,
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "limit": 100,
            },
        )
        pages = []
        for item in payload.get("data") or ():
            instagram = item.get("instagram_business_account") or {}
            if not item.get("access_token"):
                # Without a Page token we cannot subscribe it or reply on it, so
                # recording it would create a connection that silently does
                # nothing.
                continue
            pages.append(
                GrantedPage(
                    id=str(item["id"]),
                    name=item.get("name") or "",
                    access_token=item["access_token"],
                    instagram_id=str(instagram["id"]) if instagram.get("id") else None,
                    instagram_username=instagram.get("username"),
                )
            )
        return pages

    async def subscribe_page(self, page_id: str, page_token: str) -> None:
        """Point a Page's messages at our webhook.

        The step everyone forgets. Without it the connection looks perfect and
        no message ever arrives.
        """
        payload = await self._post(
            f"{page_id}/subscribed_apps",
            {
                "access_token": page_token,
                "subscribed_fields": ",".join(PAGE_WEBHOOK_FIELDS),
            },
        )
        if not payload.get("success", True):
            raise MetaApiError(f"Meta refused to subscribe page {page_id}")

    async def unsubscribe_page(self, page_id: str, page_token: str) -> None:
        """Stop a Page's messages reaching us. Best effort: a customer who has
        already revoked us at Meta's end leaves nothing to unsubscribe."""
        try:
            await self._delete(f"{page_id}/subscribed_apps", {"access_token": page_token})
        except MetaApiError as exc:
            if not exc.is_auth_failure:
                raise

    # --- Plumbing ------------------------------------------------------------

    def _app_token(self) -> str:
        return f"{self.app_id}|{self._app_secret}"

    def _url(self, path: str) -> str:
        return f"{GRAPH_HOST}/{self.version}/{path}"

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._checked(await self._transport("GET", self._url(path), params, None))

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._checked(await self._transport("POST", self._url(path), {}, data))

    async def _delete(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._checked(await self._transport("DELETE", self._url(path), params, None))

    @staticmethod
    def _checked(payload: dict[str, Any]) -> dict[str, Any]:
        error = payload.get("error")
        if error:
            raise MetaApiError(
                error.get("message") or "Meta rejected the request",
                code=error.get("code"),
                subcode=error.get("error_subcode"),
            )
        return payload


async def _httpx_transport(
    method: str, url: str, params: dict[str, Any], data: dict[str, Any] | None
) -> dict[str, Any]:
    """The real call. Imported here so tests never need the library loaded."""
    import httpx

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(method, url, params=params or None, data=data)
    try:
        payload = response.json()
    except ValueError:
        raise MetaApiError(f"Meta returned {response.status_code} with no JSON body") from None
    return payload if isinstance(payload, dict) else {"data": payload}
