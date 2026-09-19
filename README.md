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

## Tenants and login

Provisioning is invite-only: the team creates tenants.

```sh
docker compose exec api python -m rivon.platform.cli provision-tenant \
  --name "Demo Solar" --slug demo-solar --owner-email owner@example.com
```

The owner gets a "set your password" link by email. Until an email provider is
chosen, emails are written to the API log (`docker compose logs api`).

| Endpoint | Purpose |
|---|---|
| `POST /auth/login` | email + password → access token (15 min) + refresh token (30 days) |
| `POST /auth/refresh` | rotate: returns a new pair; replaying a used refresh token revokes the whole session family |
| `POST /auth/logout` | revoke the refresh token's family |
| `POST /auth/password-reset` | email a reset link (always 202, never reveals whether the email exists) |
| `POST /auth/password-reset/confirm` | set a new password; signs out all sessions |
| `GET /auth/me` | the current user |

Access tokens are HS256 JWTs carrying the tenant ID; every tenant-scoped request
runs under that tenant's RLS context.

## Domain events and workers

Modules talk through events in a transactional outbox (`rivon/events`):

```python
async with tenant_transaction(sessionmaker, tenant_id) as session:
    ...                                    # the change
    await publish(session, tenant_id, "lead.scored", {"lead_id": str(lead_id)})

@subscribe("lead.scored", name="feasibility.on_lead_scored", queue=Queue.AI)
async def on_lead_scored(session: AsyncSession, event: Event) -> None: ...
```

- The event is committed with the change, or not at all.
- The `relay` service moves committed events onto Celery queues
  (`rivon.inbound`, `rivon.ai`, `rivon.outbound`, `rivon.scheduled`).
- The `worker` service runs subscribers. Each (event, subscriber) takes effect
  exactly once: the handler runs in the same transaction that records the
  delivery, so redeliveries are skipped and a failed handler leaves nothing behind.
- Register subscriber modules in `rivon/subscribers.py`.
- Locally one worker consumes every queue. In production, run one worker pool
  per queue so slow AI or scheduled work never delays a customer's reply.

## Database roles

| Role | Used by | Notes |
|---|---|---|
| `rivon_owner` | Alembic only | Owns the schema |
| `rivon_app` | API and workers | Not superuser, not owner, no `BYPASSRLS` |
| `rivon_relay` | Outbox relay | `SELECT`/`UPDATE` on `outbox_events` only, via a role-scoped policy |

Both are created by `docker/postgres/init/01-roles.sh` the first time the data
volume is created. After changing that script, recreate the volume:
`docker compose down -v`.

Every tenant-scoped table has `ENABLE` + `FORCE ROW LEVEL SECURITY` and a
`tenant_isolation` policy keyed on the `app.current_tenant_id` setting, which is
set **per transaction** (`rivon.platform.tenancy.tenant_transaction`). With no
tenant set, queries return zero rows.

## Migrations

```sh
uv run alembic revision --rev-id 0002 -m "describe the change"   # then write it by hand
uv run alembic upgrade head
uv run alembic check                                              # models and migrations agree
```

Conventions (OPS-09). Everything marked ✓ is enforced by
`tests/test_schema_conventions.py`, so breaking it fails CI:

- ✓ Revision IDs are sequential four-digit numbers (`0001`, `0002`, …), the file
  name starts with the ID, and there is a single head.
- ✓ Migrations never import `rivon` code. A migration must mean forever what it
  meant when it ran, so helpers and SQL are written inline.
- ✓ Models and migrations agree (`alembic check`).
- ✓ Every table has `id` (UUID), `created_at`, `updated_at` (timestamptz, not null).
- ✓ Every table except `tenants` has `tenant_id` (UUID, not null, FK to `tenants`).
- ✓ Every table has `ENABLE` + `FORCE ROW LEVEL SECURITY` and a `tenant_isolation` policy.
- ✓ Every index on a tenant-scoped table leads with `tenant_id`. Exceptions go in
  `INDEX_EXCEPTIONS` in that test, each with a reason.
- ✓ Every migration has a working `downgrade()`. The test run goes up, down, up.
- Constraint names follow the naming convention in `rivon/db.py`; use `op.f(...)`.
- New modules add their models to `rivon/models.py`.
- Never edit a migration that has run anywhere, including on a teammate's machine.
  Write a new one.
