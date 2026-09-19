# Session 1 — Bootstrap (PLT-01)

Paste this as your first Claude Code prompt, after placing `CLAUDE.md` in the
repo root and the three reference docs in `/docs`.

---

## The prompt

> Read `CLAUDE.md`, then `docs/PROJECT_SPEC.md` sections 2 and 7 only.
>
> This session: repo scaffold + feature **PLT-01** (multi-tenant schema
> foundation). Nothing else. Do not build features beyond PLT-01.
>
> **1. Scaffold**
> - `pyproject.toml` (uv or poetry), Python 3.12
> - `rivon/` package with `main.py`, `config.py` (pydantic-settings, `RIVON_` prefix), `db.py`
> - `rivon/platform/` as the only module for now
> - `alembic/` initialised with async SQLAlchemy 2.0
> - `docker-compose.yml`: api, postgres 16, redis
> - `.env.example`, `.gitignore`, `README.md`
> - `tests/` with pytest + pytest-asyncio, a Postgres fixture using a
>   transactional rollback per test
>
> **2. PLT-01**
> - `Base` model mixin: `id` UUID pk, `created_at`, `updated_at` (UTC,
>   timezone-aware)
> - `TenantScopedMixin` adding `tenant_id` with an index
> - `tenants` table: id, name, slug, `region` enum (`eu` / `non_eu`), status, timestamps
> - `users` table: tenant-scoped, email unique per tenant, password hash, role enum
> - Alembic migration creating both
> - **Postgres RLS, done correctly — this is the part that is easy to get
>   subtly wrong:**
>   - `ALTER TABLE users ENABLE ROW LEVEL SECURITY` **and**
>     `FORCE ROW LEVEL SECURITY`. Without FORCE, RLS is bypassed for superusers
>     and for the role that owns the table, so the policy silently does nothing.
>   - Create **two DB roles**: a migration/owner role used only by Alembic, and
>     a separate application role (non-superuser, not the table owner) that the
>     API and workers connect as. Belt and braces alongside FORCE.
>   - Policy predicate reads a session variable, e.g.
>     `tenant_id = current_setting('app.current_tenant_id', true)::uuid`.
>   - **Set it per transaction**, not per connection:
>     `SELECT set_config('app.current_tenant_id', :tid, true)` — the `true`
>     makes it transaction-local (equivalent to `SET LOCAL`). With a connection
>     pool, a connection-scoped `SET` leaks one tenant's ID into the next
>     request that reuses the connection. This is a cross-tenant data leak, not
>     a style preference.
> - A `TenantContext` FastAPI dependency that resolves the tenant and calls
>   `set_config(..., true)` inside the request's transaction
> - `GET /health` returning db + redis connectivity
>
> **3. The test that matters**
> Write `tests/test_tenant_isolation.py`. It must connect as the **application
> role** (not the owner/migration role), and must include:
> - With tenant A's context set, a raw `SELECT * FROM users` with no WHERE
>   clause returns none of tenant B's rows — so RLS is exercised, not the ORM
>   filter
> - A **negative control**: with no tenant context set, the same query returns
>   zero rows (proving the policy is active and fails closed)
> - A **pooled-connection test**: run a request as tenant A, then reuse the same
>   pooled connection for tenant B, and assert B sees only B's rows. This is
>   what catches connection-scoped `SET` leaking across requests.
>
> Make `docker compose up` work and all tests pass. Then stop and summarise
> what exists and what's next.

---

## What to give Claude Code, and when

**In the repo from day one:**

```
rivon/
├── CLAUDE.md              ← auto-loaded every session. Keep it tight.
└── docs/
    ├── PROJECT_SPEC.md
    ├── V1_SCOPE.md
    └── FEATURE_LIST_V1.md
```

`CLAUDE.md` is the only always-loaded file. The three docs are reference —
point at specific sections per task rather than letting it read all three every
session.

**Per session after this one:** one feature ID, plus which spec section is
relevant. For example:

> Feature CHN-02 (WhatsApp inbound webhook). See `docs/PROJECT_SPEC.md` §2.1 and
> `docs/FEATURE_LIST_V1.md` module CHN. Remember hard rules 3 and 7.

---

## Session order for the first month

Following the critical path `PLT-01 → BIZ-08 → CNV-05 → FEAS/QUOT → QUOT-05`:

| # | Feature | Why here |
|---|---|---|
| 1 | PLT-01 | Tenancy first. Retrofitting it is a rewrite. |
| 2 | OPS-01, OPS-09 | CI + migration conventions before there's much to migrate |
| 3 | PLT-02, PLT-05 | Auth + region attribute |
| 4 | OPS-02, OPS-03 | Outbox + Celery queues |
| 5 | BIZ-01, BIZ-02 | Business profile, services |
| 6 | BIZ-03 | Pricing rules data model — feeds QUOT-01 later |
| 7 | BIZ-05, BIZ-06, BIZ-07 | Areas, inventory, workforce |
| 8 | BIZ-08 | Vertical config framework (solar) |
| 9 | CHN-01 | Internal message model + adapter interface |
| 10 | **Fake channel** | A test endpoint that accepts a message and returns a reply. Not a numbered feature — build it anyway. |

**Build the fake channel before WhatsApp.** It exercises the whole pipeline with
no Meta account, no webhook tunnel, no template approval, and it stays as your
permanent test harness. WhatsApp then becomes a two-day adapter swap.

---

## Do this outside Claude Code, starting week one

- [ ] Start Meta Business verification
- [ ] Submit the WhatsApp approval-card message template
- [ ] Register `rivon.ai` (or `.io`)
- [ ] Trademark search: PK, UAE, Saudi, EU
- [ ] Confirm with Dr. Baloch: service SMEs (not Shopify retail), and whether a
      named agent framework is expected in the report

Meta verification and template approval take weeks and block QUOT-05 at the very
end of the build, when there's no slack left.

---

## Things that will go wrong if you skip them

- **No `CLAUDE.md`** → it re-derives conventions each session and they drift
- **Handing it the whole spec** → it builds breadth, not the critical path
- **Multiple features per session** → wide diffs, hard review, broken tests
- **Skipping the tenant isolation test** → the bug surfaces when a real tenant
  sees another tenant's quotation
- **Editing a migration that already ran** → divergent schemas across machines
