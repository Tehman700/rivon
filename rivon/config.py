from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from rivon.platform.models import Region


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RIVON_", env_file=".env", extra="ignore")

    env: str = "local"

    # Which region this deployment serves. Each region is a separate deployment
    # with its own database; a tenant is only ever served by its own region's.
    deployment_region: Region = Region.EU

    # Application role: not a superuser, not the table owner, so RLS applies.
    # The API and workers connect with this.
    database_url: str

    # Owner role: owns the schema. Used by Alembic only, never by the app.
    migration_database_url: str

    # Outbox relay role. Only the relay process needs it.
    relay_database_url: str | None = None
    relay_poll_interval_seconds: float = 0.5
    relay_batch_size: int = 100

    redis_url: str

    # Signs access tokens (HS256). At least 32 characters; rotate by redeploying.
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 30
    # A just-rotated refresh token presented again within this window is treated
    # as a concurrent refresh (e.g. two browser requests), not as theft.
    refresh_reuse_grace_seconds: int = 30
    password_reset_ttl_minutes: int = 60

    # Encrypts customers' channel access tokens before they reach the database
    # (CHN-07). A urlsafe base64 32-byte key; generate one with
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    # Changing it makes existing connections unreadable, and they need reconnecting.
    channel_token_key: SecretStr | None = None

    # Where the dashboard lives; used to build links in emails.
    public_app_url: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields come from the environment
