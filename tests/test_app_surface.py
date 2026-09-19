"""What the API exposes publicly, per environment."""

from httpx import ASGITransport, AsyncClient

from rivon.config import Settings, get_settings
from rivon.main import create_app

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


def _settings(env: str) -> Settings:
    return get_settings().model_copy(update={"env": env})


async def _status(app, path: str) -> int:  # type: ignore[no-untyped-def]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return (await client.get(path)).status_code


async def test_docs_are_hidden_in_production() -> None:
    app = create_app(_settings("production"))
    assert (app.docs_url, app.redoc_url, app.openapi_url) == (None, None, None)
    for path in DOC_PATHS:
        assert await _status(app, path) == 404, path


async def test_docs_are_available_outside_production() -> None:
    app = create_app(_settings("local"))
    for path in DOC_PATHS:
        assert await _status(app, path) == 200, path


async def test_hiding_the_docs_does_not_change_the_api() -> None:
    """Only the documentation disappears: the endpoints still answer."""
    for env in ("production", "local"):
        app = create_app(_settings(env))
        # Stand-ins for what the lifespan would set up: these requests fail
        # validation or authentication before anything touches them.
        app.state.sessionmaker = object()
        app.state.email_sender = object()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Routed and validating (422), not missing (404).
            assert (await client.post("/auth/login", json={})).status_code == 422, env
            assert (await client.post("/auth/password-reset", json={})).status_code == 422, env
            assert (await client.get("/auth/me")).status_code == 401, env
