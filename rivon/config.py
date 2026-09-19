from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RIVON_", env_file=".env", extra="ignore")

    env: str = "local"

    # Application role: not a superuser, not the table owner, so RLS applies.
    # The API and workers connect with this.
    database_url: str

    # Owner role: owns the schema. Used by Alembic only, never by the app.
    migration_database_url: str

    redis_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields come from the environment
