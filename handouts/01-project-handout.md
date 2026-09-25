# Rivon — project handout

Everything someone new needs to understand what Rivon is and how it is put
together. For where it stands today, see [`02-project-status.md`](02-project-status.md).

---

## 1. What Rivon is

Rivon is a multi-tenant SaaS for **service businesses that quote from a rate
card** — solar installers first. When a customer messages the business on
WhatsApp, Facebook Messenger or Instagram, Rivon:

1. **answers immediately**, at any hour, and says plainly that it is an assistant;
2. **qualifies the enquiry** — asks only the questions still missing (postal
   code, property type, roof, consumption, timeframe, ownership);
3. **checks feasibility** — service area, stock, crew capacity, project size;
4. **prepares a quotation** from the installer's own prices, for the installer
   to approve before it goes anywhere.

The problem it solves is ordinary and expensive. Small installers lose work
because enquiries arrive in the evening, on channels nobody is watching, and the
first business to reply usually wins.

### What makes it different

**Numbers are computed, never generated.** Every price, system size and
feasibility verdict comes from deterministic Python run against the installer's
own configuration. A language model only ever writes the words *around* figures
the code has already produced. That is the difference between a quote a
business can stand behind and one it has to double-check. (Hard rule 1.)

**Nothing is finally rejected by a machine.** Where a job looks unfeasible, a
person confirms it or the outcome stays provisional with a route to human
review. (GDPR Art 22.)

**It never scores ability to pay.** Scoring looks at intent, urgency,
completeness and fit — never credit or financial standing, which would make it
a high-risk system under the EU AI Act. (Hard rule 9.)

---

## 2. Who it is for

| | |
|---|---|
| **Customer** (who pays) | A small or medium service business — a solar installer with a handful of crews |
| **User** (who logs in) | The owner, plus managers and agents, in the Rivon dashboard |
| **End customer** (who messages) | A homeowner asking "how much for panels on my roof?" |
| **Launch market** | The European Union — confirmed September 2026 |
| **Language / currency** | English only; prices in EUR |

Rivon is **invitation only** for now. There is no public sign-up: a business
requests access by email (`rivonna.ai@gmail.com`) and the team provisions it.

---

## 3. Two things at once

Rivon is being built as **both**:

- a **Final Year Project** at UET Taxila, by a team of three, which needs a
  complete working loop to defend; and
- a **commercial v1**, which needs to be safe to put real customer data through.

They mostly want the same things. Where they differ, `docs/V1_SCOPE.md` decides
what ships to paying customers and spec §11.2 decides what gets built for the
defence. The most visible difference: a thin `jobs` + `feedback` slice is built
for the FYP (it closes the loop, which is the novelty claim) but is v2 for the
commercial product.

---

## 4. How it is built

### 4.1 Architecture in one picture

```
   Customer on WhatsApp / Messenger / Instagram
                     │
                     ▼
        Meta ──► /webhooks/{channel}          verify signature → route → store → 200
                     │                         (does no other work — hard rule 3)
                     ▼
              inbound_messages ──► outbox (message.received)
                                          │
                                   relay ─┴─► Celery queues
                                               │
                     ┌─────────────────────────┴──────────────┐
                     ▼                                        ▼
              conversations  (Phase 2 — not built yet;   outbound dispatcher
              today a placeholder "echo" reply)          dedupe key → send via Meta
                     │
                     ▼
        leads · feasibility · quotations · analytics      (not built yet)

   Owner ──► app.tideover.site (Next.js) ──► /api/backend (BFF proxy) ──► FastAPI
```

### 4.2 The shape of the code

A **modular monolith**: one deployable, split into modules that own their own
tables and talk only through service interfaces and events (hard rule 8).

| Module | Owns | Status |
|---|---|---|
| `platform` | Tenants, users, auth, roles, regions | Built |
| `business` | Profile, services, rate cards, pricing, service areas, stock, crews, solar configuration | Built |
| `channels` | Message model, adapters, connected accounts, webhooks, inbound and outbound messages | Built |
| `events` | Transactional outbox, relay, exactly-once delivery | Built |
| `conversations` | Agent, qualification, extraction, AI disclosure | **Not started** |
| `documents` | Knowledge base uploads | Not started |
| `leads` | Contacts, lead scoring | Not started |
| `feasibility` | Deterministic rules | Not started |
| `quotations` | Pricing, approval | Not started |
| `analytics` | Nightly rollups | Not started |

### 4.3 Stack

| Layer | Choice |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 |
| Data | PostgreSQL with **forced row-level security**, SQLAlchemy 2.0 (async), Alembic |
| Queues | Redis, Celery, and a Postgres transactional outbox with its own relay |
| Frontend | Next.js 16 (App Router), Tailwind v4, shadcn/ui, GSAP on the landing page |
| Crypto | `cryptography` (Fernet) for customers' channel tokens; Argon2 for passwords |
| HTTP out | `httpx` |
| Packaging | `uv` |
| Runtime | Docker Compose, Caddy for TLS — **no Kubernetes** |
| Integrations | n8n at the edge only (planned, not built) |

**Deliberately not used:** LangChain, LlamaIndex, Pinecone or any separate vector
database (pgvector when needed), Kafka (the Postgres outbox does that job).

### 4.4 Where it runs

Everything is in the **EU**, in Frankfurt, because EU tenant data must stay in
the EU (GDPR Ch. V, feature PLT-05).

| Part | Service | Address |
|---|---|---|
| Dashboard + landing page | Vercel, region `fra1` | `https://app.tideover.site` |
| API, workers, relay | AWS EC2 in `eu-central-1`, Docker Compose, Caddy | `https://api.tideover.site` |
| Database | Neon Postgres, Frankfurt | (private) |
| Code | GitHub, public | `github.com/Tehman700/rivon` |

---

## 5. The eleven hard rules

Condensed from `CLAUDE.md`, which is authoritative.

1. Pricing and feasibility are deterministic Python. **No LLM.**
2. `tenant_id` on every table; every index leads with it. RLS as a backstop, and
   application code filters by tenant too.
3. The webhook path does no work: verify, persist, enqueue, return 200.
4. Channel adapters are thin — translation only. Runnable with no live connection.
5. Uploaded documents never reach pricing or feasibility.
6. Conversation state lives in Postgres, never in worker memory.
7. Idempotency is not optional: unique inbound message ids, a dedupe key on every send.
8. No module reaches into another module's tables.
9. Never score ability to pay, payment history or financial standing.
10. Analytics never queries live operational tables.
11. n8n lives at the edge, never in the core pipeline.

One exception to rule 2 has been taken deliberately, reviewed and tested — see
[`05-design-deviations.md`](05-design-deviations.md) §3.

---

## 6. The legal floor

These bind as soon as real personal data is processed, and must never be
weakened (from `CLAUDE.md`):

| Requirement | Why | Status |
|---|---|---|
| AI disclosure at conversation start, logged, not disableable (CNV-09) | EU AI Act Art 50 | Not built — ships with the conversation engine |
| No terminal auto-rejection (FEAS-08/09) | GDPR Art 22 | Not built |
| Model version + inputs stored per score (LEAD-06) | Explainability | Not built |
| Data export + erasure (GDPR-01/02) | GDPR Arts 15, 17 | Not built |
| Versioned consent records (CHN-11) | ePrivacy | Not built |
| Tenant region; EU data stays in the EU (PLT-05) | GDPR Ch. V | **Built** |

The placeholder reply that runs today already identifies itself as an
automated assistant, so nothing misleading reaches a person even in testing.

---

## 7. Running it locally

```
docker compose up -d              # Postgres, Redis, migrations, API, worker, relay
uv run pytest -q                  # 409 tests against a real Postgres
cd web && npm install && npm run dev
```

- API on `http://localhost:8000` (docs at `/docs` locally; hidden in production)
- Dashboard on `http://localhost:3000`
- A tenant is created with the CLI:
  `uv run python -m rivon.platform.cli provision-tenant --name "…" --slug … --owner-email …`
  (`--region` defaults to `eu`)
- Local secrets live in `.env` (gitignored). `.env.example` lists every setting.

Tests need Docker running: they use a real Postgres with real roles, so RLS is
in force exactly as in production.

---

## 8. Where to find things

| You want | Look in |
|---|---|
| The rules | `CLAUDE.md` |
| The original plan | `docs/PROJECT_SPEC.md`, `docs/V1_SCOPE.md`, `docs/FEATURE_LIST_V1.md` |
| How to deploy | `docs/DEPLOY.md`, and [`10-operations.md`](10-operations.md) |
| What is built / left | [`03-done.md`](03-done.md), [`04-remaining.md`](04-remaining.md) |
| Why something is the way it is | [`06-decisions.md`](06-decisions.md), and the commit message — they are written to be read |
| Meta, WhatsApp, Messenger, Instagram | [`09-channels-meta.md`](09-channels-meta.md) |
