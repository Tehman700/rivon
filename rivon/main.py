import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from rivon.config import Settings, get_settings
from rivon.business import api as business_api
from rivon.channels import api as channels_api
from rivon.db import create_engine
from rivon.platform import api as platform_api
from rivon.platform.email import ConsoleEmailSender

HEALTH_CHECK_TIMEOUT_S = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = ConsoleEmailSender()
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # The API is private (no public sign-up). In production don't publish a map
    # of every endpoint and field: it only helps someone probing the service.
    published = settings.env != "production"
    app = FastAPI(
        title="Rivon",
        lifespan=lifespan,
        docs_url="/docs" if published else None,
        redoc_url="/redoc" if published else None,
        openapi_url="/openapi.json" if published else None,
    )
    app.include_router(platform_api.router)
    app.include_router(business_api.router)
    app.include_router(channels_api.router)
    return app


app = create_app()


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
