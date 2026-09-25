# What is done

Everything built so far, grouped by module and feature ID from
`docs/FEATURE_LIST_V1.md`. Each entry says what it does, what makes it
trustworthy, and the commit that introduced it — `git show <hash>` explains the
reasoning in full, because commit messages here are written to be read.

**Totals at `cf98ef1`:** 39 commits · 12 migrations · 18 tables · 28 API routes ·
18 web pages · 409 tests.

Legend: ✅ complete · 🟡 partial (what is missing is stated)

---

## Platform — `rivon/platform`

| ID | | What exists | Commit |
|---|---|---|---|
| PLT-01 | ✅ | Multi-tenant foundation. `tenant_id` on every table, every index led by it, **forced** row-level security so even the table owner is filtered, a per-transaction tenant setting, and application-level tenant filters as a second lock. Three database roles: `rivon_owner` (migrations), `rivon_app` (the API), `rivon_relay` (the outbox relay). | `913e310` |
| PLT-02 | ✅ | Owner authentication: Argon2 passwords, 15-minute JWT access tokens, opaque rotating refresh tokens with family revocation, and a 30-second grace window so two browser tabs refreshing at once are not mistaken for token theft. Password reset. | `e7b4bb0`, `37eda8a` |
| PLT-03 | 🟡 | Roles `owner` / `manager` / `agent` and `require_owner` / `require_roles` checks, enforced on every write. *Missing:* finer-grained permissions — not needed for the FYP. | `e7b4bb0` onward |
| PLT-04 | 🟡 | Invite-only provisioning through a CLI (`provision-tenant`). *Missing:* an invite email and self-activation flow. | `913e310` |
| PLT-05 | ✅ | Tenant `region`, fixed at provisioning (a database trigger refuses changes), and each deployment serves only its own region's tenants. | `53b32cf` |

## Operations

| ID | | What exists | Commit |
|---|---|---|---|
| OPS-01 | ✅ | Docker Compose for local and production; CI on GitHub Actions, including a check that the worker and relay actually start. | `f74ac6f`, `9d29cec` |
| OPS-02 | ✅ | Transactional outbox. Events are written in the same transaction as the change they describe, and delivered exactly once in effect: each handler runs in the transaction that records its delivery. | `174733a` |
| OPS-03 | 🟡 | Celery queues split by workload: `rivon.inbound`, `rivon.ai`, `rivon.outbound`, `rivon.scheduled`. *Missing:* Beat schedules — nothing scheduled exists yet. | `174733a` |
| OPS-08 | ✅ | EU deployment: API on EC2 Frankfurt, Neon Frankfurt, Vercel `fra1`. Caddy for TLS; API docs hidden in production. | `137dc9a`, `71400df` |
| OPS-09 | ✅ | Migration conventions, enforced by tests: every migration runs up, down and up again on every test run; the chain must be single and numbered; migrations must not import application code. | `8b1e88a` |

## Business configuration — `rivon/business`

| ID | | What exists | Commit |
|---|---|---|---|
| BIZ-01 | ✅ | Business profile: name, assistant name, contact, address, time zone, opening hours per weekday, minimum and maximum project size and value. | `57e0db0` |
| BIZ-02 | ✅ | Services catalogue with archive rather than delete, per-service margin and VAT overrides, names unique per business ignoring case. | `57e0db0` |
| BIZ-03 | ✅ | Pricing rules: rate-card lines by category (materials, labour, transport, fees), quantity bases (fixed, kWp, battery kWh, km), included and minimum quantities, rounding; business-wide margin, minimum margin and VAT settings. **Data model only** — the calculator is QUOT-01. | `d4da9fc` |
| BIZ-05 | ✅ | Service areas: named regions with a country and postal-code prefixes, normalised and de-duplicated. | `1479094` |
| BIZ-06 | ✅ | Inventory items with quantities and a low-stock threshold. | `1479094` |
| BIZ-07 | ✅ | Crews with headcount, weekly capacity hours and an active flag. | `1479094` |
| BIZ-08 | ✅ | The solar vertical: a fixed question set (what the assistant asks), `missing_for_quote()`, and deterministic system sizing from consumption, capped by roof area, tunable per business. No model involved. | `1850809` |

## Channels — `rivon/channels`

The whole transport layer for WhatsApp, Messenger and Instagram.

| ID | | What exists | Commit |
|---|---|---|---|
| CHN-01 | ✅ | One internal message model for every platform. Adapters that only translate, and `render()` *describes* an HTTP call rather than making one, so every adapter is a pure function. A **fake channel** that behaves like the real ones, so the whole path runs with no Meta account. Real adapters for all three Meta platforms. | `9fdbc0e`, `b5c28db` |
| CHN-02 | ✅ | Webhooks at `/webhooks/{whatsapp,messenger,instagram}`: Meta's verification handshake, and HMAC-SHA256 signature checks over the **raw** request bytes before anything is parsed. | `b5c28db` |
| CHN-03 | ✅ | Tenant routing from the account id in the payload (Page id, Instagram id, WhatsApp phone number id) through one SQL function — the only cross-tenant read in the system, returning a single UUID. | `067d058`, `b5c28db` |
| CHN-04 | ✅ | Idempotency: unique `(tenant_id, provider_message_id)`; a retried delivery is stored and enqueued once. | `b5c28db` |
| CHN-05 | ✅ | Outbound dispatcher: claims each send by a dedupe key in the database, sends through the right adapter, tells a dead token or a closed 24-hour window apart from a retryable failure, gives up after five attempts, and keeps the reason on the row. | `21502c9` |
| CHN-07 | ✅ | Connected accounts, with access tokens **encrypted** (Fernet) before they reach the database; revocation, re-authorisation status, and reconnecting in place. | `067d058` |
| CHN-13 | ✅ | *New feature, not in the original list.* Self-serve connection, the ManyChat model: Facebook Login for Business for Pages and Instagram, WhatsApp Embedded Signup for WhatsApp — backend and the browser half (Facebook's JS SDK popup, pairing the code with the account ids from the browser event). Checks the permissions actually granted, subscribes each account before storing it, and explains anything it had to leave out. | `f930aa4`, `ab865b4`, `946b757`, `cf98ef1` |
| — | ✅ | A placeholder **echo reply** so the path can be watched working. Identifies itself as an automated assistant. Replaced by the conversation engine in Phase 2. | `21502c9` |

## Dashboard and site — `web/`

| ID | | What exists | Commit |
|---|---|---|---|
| DASH-01 | ✅ | App shell: sign-in, sidebar, role-aware read-only notices, silent session refresh, and a **BFF proxy** so the browser never holds a token — cookie sessions, allow-listed paths, origin check, JSON-only writes. | `9ef4cb8` |
| DASH-05 | ✅ | Configuration screens for everything in BIZ: profile, services and rate cards, pricing, service areas, inventory, crews, assistant and sizing. | `9ef4cb8`, `2b9ab8c`, `a4b99b9` |
| — | ✅ | **Channels page**: three cards, connect and disconnect, status per account, and the return screen from Meta that reports what was connected and what was left out. WhatsApp's card opens Embedded Signup in Facebook's popup and shows the PIN once. | `aac3a81`, `cf98ef1` |
| SITE-01 | ✅ | Public landing page with GSAP animations, sign-in in the header, request-access page. | `eb21a8b` |
| SITE-03 | 🟡 | Privacy notice at `/privacy` and data-deletion instructions at `/data-deletion`. *Missing:* terms of service. A cookie banner is not needed: only two strictly necessary cookies are set. | `de5d58b`, `2155071` |
| — | ✅ | Brand: logo traced from the supplied PNG into an SVG that works on light and dark; channel icons drawn inline. | `55b5c03`, `aac3a81` |

## Hardening that is not a feature ID, but matters

| What | Why | Commit |
|---|---|---|
| Schema review gates | Every table must force RLS; every extra policy and every index not led by `tenant_id` must be listed with a reason, or the tests fail | `8b1e88a`, `067d058` |
| Dependency guard | Every package imported by `rivon/` must be a runtime dependency — the production image has no dev dependencies | `7640d2f` |
| API docs hidden in production | Do not publish a map of every endpoint | `71400df` |
| Credential notes ignored by git | After a near-miss with a secrets file in the repo root | `9d916bc` |
