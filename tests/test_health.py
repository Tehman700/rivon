from httpx import AsyncClient
from redis.asyncio import Redis

from rivon.main import app


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "redis": True}


async def test_health_reports_redis_down(client: AsyncClient) -> None:
    working = app.state.redis
    # Nothing listens on port 1.
    app.state.redis = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5)
    try:
        response = await client.get("/health")
    finally:
        await app.state.redis.aclose()
        app.state.redis = working
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": True, "redis": False}
