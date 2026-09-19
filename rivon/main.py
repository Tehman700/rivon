import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from rivon.config import get_settings
from rivon.db import create_engine

HEALTH_CHECK_TIMEOUT_S = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=HEALTH_CHECK_TIMEOUT_S,
        socket_timeout=HEALTH_CHECK_TIMEOUT_S,
    )
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await engine.dispose()


app = FastAPI(title="Rivon", lifespan=lifespan)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    redis: bool


async def _database_ok(engine: AsyncEngine) -> bool:
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _redis_ok(redis: Redis) -> bool:
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
            return bool(await redis.ping())
    except Exception:
        return False


@app.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    database, redis = await asyncio.gather(
        _database_ok(request.app.state.engine), _redis_ok(request.app.state.redis)
    )
    healthy = database and redis
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", database=database, redis=redis)
