# CLAUDE.md — Rivon

Multi-tenant SaaS: AI lead qualification → feasibility check → quotation for
service SMEs (solar first). **Launch market: EU** (confirmed Sep 2026) — so EU
hosting and GDPR/AI Act obligations are live requirements, not future work.
**English only** (no second language). **Prices in EUR.**

**Open blocker:** the first EU market is not yet named, and it decides the
primary channel — WhatsApp for Southern Europe, web widget + email for
Nordics/DACH. See spec §15.12. **Do not start `channels` work until this is
settled.**

Reference docs in `/docs`: `PROJECT_SPEC.md` (architecture), `V1_SCOPE.md`
(scope), `FEATURE_LIST_V1.md` (features with IDs). **Read the relevant section
before starting a task. Do not read all three every session.**

---

## Hard rules — never violate

**1. Pricing and feasibility are deterministic Python. No LLM.**
The LLM writes prose *around* numbers that code computed. If you find yourself
passing a price to a model and asking for a number back, stop.

**2. `tenant_id` on every table. Every index leads with it.**
`(tenant_id, created_at)`, `(tenant_id, status)`. RLS policies as a backstop —
application code filters by tenant too. Never rely on RLS alone.

**3. The webhook path does no work.**
Verify signature → persist raw payload → enqueue → return 200. No LLM call, no
DB join, no business logic. WhatsApp retries if we're slow, and a retried
webhook becomes a duplicate reply to a real customer.

**4. Channel adapters are thin.**
Translate provider payload ↔ internal message model. Nothing else. All logic
lives in `conversations` and downstream. The system must be fully testable and
runnable with no live WhatsApp connection.

**5. Document context never reaches pricing or feasibility.**
Uploaded business documents inform conversational answers only. Do not inject
the document service into `quotations` or `feasibility` — enforce structurally,
not with a prompt instruction.

**6. Conversation state lives in Postgres, never in worker memory.**
Redis caches only. Any worker must be able to handle any turn of any
conversation.

**7. Idempotency is not optional.**
Unique `(tenant_id, provider_message_id)` inbound. Dedupe key on every outbound.

**8. No module reaches into another module's tables.**
Cross-module communication is service interfaces or domain events on the outbox.

**9. Never score ability to pay, payment history, or financial standing.**
That becomes creditworthiness assessment = EU AI Act Annex III high-risk. Score
intent, urgency, requirement completeness, service fit.

**10. Analytics never queries live operational tables.**
Dashboard reads from `daily_rollups` only.

**11. n8n lives at the edge, never in the core pipeline.** (spec §7.4)
It receives signed event webhooks and calls the public API with a scoped
service token — nothing else. No direct Postgres/Redis access. It never
computes prices, feasibility or scores, and never messages a customer except
through the Rivon API (so dedupe, consent and AI disclosure still apply). If n8n
is down, leads still get qualified and quoted. Workflows are team-managed only;
tenants never get n8n access.

---

## Legally required

**The EU is the confirmed launch market** (spec §15.11), so these are real
obligations, not future work. But they bind when *real personal data* is
processed — a demo on synthetic data does not trigger them. Two tiers:

**Architectural — build in the FYP. Never remove or weaken:**

| Feature | Requirement |
|---|---|
| CNV-09 — AI disclosure at conversation start, logged, not disableable | EU AI Act Art 50 (in force since 2 Aug 2026) |
| FEAS-08/09 — no terminal auto-rejection; human confirmation or non-final outcome + human-review route | GDPR Art 22 / SCHUFA C-634/21 |
| LEAD-06 — model version + input features stored per score | GDPR Art 22 explainability |
| GDPR-01/02 — data export + erasure | GDPR Arts 15, 17 |
| CHN-11 — versioned consent records | ePrivacy |
| PLT-05 — tenant region attribute; EU tenant data stays in the EU | GDPR Ch. V |

Retrofitting any of these is a schema or flow change, which is why they're in
the FYP build even though no real data flows yet.

**Required before the first real tenant — may be deferred past the FYP demo:**
GDPR-03 (rectification), LEAD-07 (object-to-profiling flag), CHN-12 (opt-out
handling), GDPR-04 (per-jurisdiction consent), GDPR-05 (records of processing).

If a task would delete or weaken anything in the first table, say so and stop.

---

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- PostgreSQL (`jsonb` for flexible fields), Redis, S3
- Celery + Beat. Queues: `rivon.inbound`, `rivon.ai`, `rivon.outbound`, `rivon.scheduled`
- Next.js App Router + Tailwind (separate `web/` directory)
- OpenAI / Gemini via **direct SDK calls + Pydantic structured output**
- scikit-learn for lead scoring
- Docker Compose. **No Kubernetes.**
- n8n (self-hosted, EU, team-managed) for integrations and ops automation —
  edge only, see hard rule 11. Workflow JSON exported to `n8n/workflows/`.

**Do not add:** LangChain, LlamaIndex, Pinecone or any separate vector DB (use
`pgvector` when needed), Kafka (use the Postgres outbox).
If you think one is needed, ask first.

---

## Conventions

- Package root `rivon`, modules `rivon.channels`, `rivon.quotations`, …
- Env prefix `RIVON_`. Database `rivon`.
- Images `rivon-api`, `rivon-worker`, `rivon-web`
- snake_case Python, PascalCase models, plural table names
- Every table: `id` (UUID), `tenant_id`, `created_at`, `updated_at`
- All timestamps UTC, timezone-aware
- Type hints everywhere. Pydantic schemas for every API boundary.
- Alembic migration for every schema change. Never edit a migration that ran.
- `pytest`. Tests alongside the module.

---

## Modules

`platform` tenancy/auth/metering · `channels` adapters + outbound ·
`conversations` agent/NLU/extraction · `business` tenant config as data ·
`documents` knowledge base · `leads` contacts + scoring · `feasibility` rules ·
`quotations` pricing + approval · `analytics` rollups

v2 (do not build now): `jobs`, `feedback`, `engagement`

Each owns its tables, exposes a service interface, publishes events.

---

## Domain events (outbox)

```
message.received · lead.captured · requirements.extracted · lead.scored
feasibility.checked · quotation.drafted · quotation.approved
```

Events are also delivered to n8n via signed outbound webhooks (OPS-10) —
at-least-once, so consumers dedupe on event ID.

---

## Working style

- **One feature ID per session.** Ask which if unclear.
- Feature IDs and build phases: `docs/FEATURE_LIST_V1.md` and spec §11.3.
- Write the migration and the test with the feature, not after.
- Prefer boring and explicit over clever.
- If a task conflicts with a hard rule above, stop and say so.
- Don't scaffold ahead. No empty modules for future features.
- Don't add dependencies without asking.
- Never commit secrets. `.env.example` only.
