# Rivon

AI lead qualification → feasibility check → quotation for service SMEs.

Start with [`CLAUDE.md`](CLAUDE.md) (rules and conventions), then the reference
docs in [`docs/`](docs/).

## Prerequisites

- Docker Desktop
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically)

## Run it

```sh
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
```

Compose starts Postgres 16, Redis 7, a one-shot `migrate` service
(`alembic upgrade head`) and the API. Host ports are **5433** (Postgres) and
**6380** (Redis) so they don't clash with local installs.

## Tests

```sh
uv sync
uv run pytest
```

Tests need the compose Postgres and Redis running. They use a separate
`rivon_test` database, rebuilt from the migrations at the start of every run.

## Database roles

| Role | Used by | Notes |
|---|---|---|
| `rivon_owner` | Alembic only | Owns the schema |
| `rivon_app` | API and workers | Not superuser, not owner, no `BYPASSRLS` |

Both are created by `docker/postgres/init/01-roles.sh` the first time the data
volume is created. After changing that script, recreate the volume:
`docker compose down -v`.

Every tenant-scoped table has `ENABLE` + `FORCE ROW LEVEL SECURITY` and a
`tenant_isolation` policy keyed on the `app.current_tenant_id` setting, which is
set **per transaction** (`rivon.platform.tenancy.tenant_transaction`). With no
tenant set, queries return zero rows.

## Migrations

```sh
uv run alembic revision -m "describe the change"   # write it by hand
uv run alembic upgrade head
uv run alembic check                                # models and migrations agree
```

Never edit a migration that has run anywhere. Migrations don't import app code.
