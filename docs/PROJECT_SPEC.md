# Rivon — Project Spec

**AI Lead-to-Lifecycle Platform for Service SMEs**

> **Status:** living document. Product name: **Rivon** (chosen Sep 2026,
> replacing the working title "LeadCraft", which collided with lead-craft.com,
> a US SEO agency). Trademark and domain checks still outstanding — see §16.
> **Context:** Final Year Project, UET Taxila, Dept. of Computer Engineering.
> Team of 3. Supervisor: Dr. Naveed Khan Baloch. Industry advisor: Hassan Abbas,
> Bluell AB (Sweden). Graduating ~mid-2027.
> **Purpose of this file:** single source of truth for implementation. Read fully
> before writing code.
> **See also:** `V1_SCOPE.md` — what ships in v1 and what is deliberately deferred.
> `FEATURE_LIST_V1.md` — feature-by-feature breakdown by module, with
> dependencies and effort sizing for costing.

## Naming conventions

Use these consistently across code, docs, and the report.

| Context | Form |
|---|---|
| Product / brand | Rivon |
| Report & formal writing | Rivon |
| Repo / package root | `rivon` |
| Python package | `rivon` (modules: `rivon.channels`, `rivon.quotations`, …) |
| Database name | `rivon` |
| Env var prefix | `RIVON_` |
| Docker image | `rivon-api`, `rivon-worker`, `rivon-web` |
| Celery queues | `rivon.inbound`, `rivon.ai`, `rivon.outbound`, `rivon.scheduled` |
| Domain (TBC) | `rivon.ai` preferred, `.io` fallback — verify availability |
| Default bot display name | Rivon (per-tenant overridable — see below) |

**Important:** the customer-facing bot should present as the **tenant's**
business, not as Rivon. A homeowner messaging a solar company expects to hear
from that company. The tenant sets the assistant's display name during
onboarding; Rivon is the vendor brand shown to the business owner, not to their
customers. This also keeps the AI disclosure (§15.3) honest and clear rather
than confusing the person about who they're dealing with.

---

## 1. What this is

A multi-tenant SaaS platform that takes a service business's customer from first
inquiry all the way through to repeat business, automating the middle.

It merges two previously separate concepts:

- **Front half (pre-sale):** conversational lead qualification → requirement
  extraction → ML lead scoring → rule-based feasibility check → quotation
  generation → human approval.
- **Back half (post-sale):** job execution → post-delivery rating loop →
  ticketing/complaints → retention and referral engine.

The front half alone acquires customers and then forgets they exist. The back
half closes the loop. **The join point is: an accepted quotation becomes a job;
a completed job triggers the rating loop.**

**Target verticals:** solar, HVAC, plumbing, construction SMEs.
**Target market:** the **EU** (decided Sep 2026 — see §15.11; first country
still to be named, §15.12). The original research targeted Pakistan and the GCC;
that is superseded. Not North America — Jobber/Housecall Pro/ServiceTitan
already bundle AI quoting there.
**Language:** English only. **Currency:** EUR.

**Positioning:** "An AI-powered lead qualification and feasibility engine that
turns service requests into business-aware quotations for small-to-mid-sized
service businesses." The differentiator is **feasibility before quotation** —
reasoning about whether a job *can and should* be quoted, using the business's
real inventory, workforce, and service-area state. An LLM alone cannot fake this.

---

## 2. Non-negotiable architectural rules

These exist because breaking them causes specific, known damage. Do not
"simplify" past them.

### 2.1 The WhatsApp bot is an ADAPTER, not the application
The bot's only job: receive webhook → verify signature → persist raw payload →
enqueue → return 200. On the way out: normalized outbound message → provider
format → send.

**No LLM call, no DB join, no business logic on the webhook path.** WhatsApp
Cloud API retries if you don't respond in seconds, and a slow-processed webhook
becomes a duplicate reply to a real customer.

This is hexagonal / ports-and-adapters. The system is the core; WhatsApp is one
adapter. Consequence: the whole system must be testable and demoable with no
live WhatsApp connection.

### 2.2 Not everything is AI
| Concern | Implementation |
|---|---|
| Intent, entities, sentiment, dialogue, requirement extraction | LLM |
| Quotation covering narrative (wording only) | LLM |
| Lead scoring | scikit-learn |
| Feasibility checks | Deterministic Python rules |
| Pricing arithmetic | Deterministic Python |
| Job state transitions | Deterministic |
| Engagement guardrails | Deterministic |

Pricing must **never** be produced by an LLM. The LLM writes the prose around a
number that deterministic code computed. Preserve this boundary rigorously — it
is the primary defence against "this is just a GPT wrapper."

### 2.3 Multi-tenant shared schema, never custom builds
- One codebase, one database.
- `tenant_id` on **every** table.
- Postgres Row-Level Security as a **backstop**, not the primary filter.
  Application code filters by tenant; RLS catches the query that forgot.
- **Every index leads with `tenant_id`** — e.g. `(tenant_id, created_at)`,
  `(tenant_id, status)`.
- Customization via **configuration, not code**: vertical configs, per-tenant
  pricing rules / prompts / templates as *data*, feature flags per plan tier.
- **Never fork per client.** A fork means two products and half the engineering
  time.

Rationale: the competitors being displaced *are* the custom-build model (Pakistan
agencies at PKR 50k+/mo, GCC at AED/SAR 15k–250k one-time). Building custom per
client means inheriting their economics.

### 2.4 Modular monolith, not microservices
One FastAPI deployable. Hard module boundaries enforced by interface contracts.
Each module owns its tables; nothing reaches into another module's tables.

Peak load is ~20 req/s. Microservices would buy independent scaling (not needed)
and charge network failures, distributed tracing, service discovery, and cross
-service consistency. Any module can be extracted later; the interface already
exists.

### 2.5 Event-driven internally, via transactional outbox
Postgres outbox table + Celery consumers. **Not Kafka.** Modules publish events
and subscribe to what they care about. `feedback` listens for `job.completed`
and knows nothing about the `jobs` module's internals.

This decoupling is what keeps the merged halves from tangling.

### 2.6 State lives in Postgres, never in worker memory
Redis caches the last N conversation turns. Any worker must be able to pick up
any turn of any conversation. This makes horizontal scaling a config change
rather than a rewrite.

### 2.7 Idempotency everywhere
- Unique constraint on `(tenant_id, provider_message_id)` for inbound.
- Dedupe key on every outbound send.
- Test by deliberately replaying a webhook.

A double-sent quotation to a real customer is an account-losing bug.

### 2.8 Analytics never queries live operational tables
Scheduled jobs precompute `daily_rollups`. The dashboard reads only from there.
(CQRS-lite.)

---

## 3. Modules

Eleven engineering modules. Origin: **[L]** front half, **[A]** back half,
**[N]** new to the merge.

| # | Module | Origin | Owns | Responsibility |
|---|---|---|---|---|
| 1 | `platform` | [N] | `tenants`, `users`, `roles`, `plans`, `feature_flags`, `usage_events`, `audit_log` | Tenancy, auth, RLS enforcement, LLM/message metering per tenant, owner-action audit |
| 2 | `channels` | [A] | `channels`, `messages`, `outbound_queue`, `consents`, `message_templates` | Provider adapters, inbound normalization, single outbound dispatcher w/ dedupe + backoff + rate limits + DLQ |
| 3 | `conversations` | [L+A] | `conversations`, `conversation_state`, `extracted_requirements` | Turn router (qualification / service / feedback / general), NLU, requirement extraction |
| 4 | `business` | [L] | `businesses`, `services`, `pricing_rules`, `service_areas`, `inventory_items`, `workforce`, `verticals` | Tenant config as data — the thing that makes customization codeless |
| 4b | `documents` | [N] | `documents`, `document_chunks` | Business knowledge base: upload, text extraction, onboarding pre-fill, full-context injection. **Never reachable from `feasibility` or `quotations`.** |
| 5 | `leads` | [L+A] | `contacts` (w/ `lifecycle_stage`), `lead_scores` | Unified contact record + scikit-learn scoring |
| 6 | `feasibility` | [L] | `feasibility_results` | Deterministic rules: service/area/inventory/crew/size. Zero LLM. |
| 7 | `quotations` | [L] | `quotations`, `quotation_items`, `approvals` | Deterministic pricing + margin + Good-Better-Best tiers; LLM narrative; approval workflow |
| 8 | `jobs` | [A] | `jobs`, `job_events` | Accepted quotation → job. Inventory reserve, crew allocate, append-only timeline. **The merge seam.** |
| 9 | `feedback` | [A] | `feedback`, `tickets` | Delayed rating trigger, 1–5 capture, branching auto-actions |
| 10 | `engagement` | [A] | `campaigns`, `retention_triggers`, `referrals`, `suppression_rules` | Scheduled outbound, NBA policy, consent/fatigue/post-complaint guardrails |
| 11 | `analytics` | [L] | `daily_rollups` | Precomputed aggregates for the dashboard |

### 3.1 Mapping to the approved FYP proposal
The approved proposal commits to five modules. Present the work as those five
plus two additions — an *extension* of approved scope, not a rewrite.

| Report module | Engineering modules |
|---|---|
| M1 — Business profiling & ad generation | `business`, part of `conversations` |
| M2 — Conversational qualification & requirement extraction | `channels`, `conversations` |
| M3 — Lead scoring & feasibility analysis | `leads`, `feasibility` |
| M4 — Quotation generation engine | `quotations` |
| M5 — Dashboard & human-in-the-loop validation | `analytics`, approval path, `platform` |
| **M6 — Job execution & post-delivery feedback** *(new)* | `jobs`, `feedback` |
| **M7 — Retention & engagement engine** *(new)* | `engagement` |

Framing for the supervisor: "closing the lifecycle loop" — the original proposal
acquires customers and then forgets them.

---

## 4. The pipeline flow

```
Stage 0  Onboarding          owner sets services, pricing rules, service areas,
                             inventory, workforce  → becomes static AI context
Stage 1  Demand capture      AI ad copy + inbound from WhatsApp/IG/Messenger/web
                             → all normalize to one message model
Stage 2  Qualification       classify intent + entities + sentiment + LIFECYCLE
                             CONTEXT (unknown number = new inquiry; open job =
                             service question; completed job = feedback/repeat)
Stage 3  Extraction          conversation → structured JSON, per-vertical schema,
                             enforced structured output
Stage 4  Lead scoring        scikit-learn → 0–100
Stage 5  Feasibility         deterministic rules → pass/fail WITH REASONS
Stage 6  Quotation           deterministic pricing + optional G-B-B tiers;
                             LLM writes narrative only
Stage 7  Approval            phone-first card (Approve/Reject/Edit); dashboard
                             secondary. Nothing reaches a customer unapproved.
Stage 8  Job                 accepted quote → job; inventory reserves, crew
                             allocates, append-only event timeline
Stage 9  Rating loop         delayed trigger on completion → 1–5 →
                             1-2: ticket + recovery msg + promo suppression
                             3:   watchlist + "what would have helped?"
                             4-5: review request + referral ask
Stage 10 Service/tickets     complaints, warranty callbacks, rework.
                             ticket → job → quotation → conversation audit chain
Stage 11 Retention           maintenance due, seasonal, dormancy, referral nudge
                             → produces new inbound-shaped conversation → Stage 2
```

The loop closes at Stage 11 → Stage 2.

---

## 5. Event contracts

```
channels      → message.received
conversations → lead.captured
              → requirements.extracted
leads         → lead.scored
feasibility   → feasibility.checked
quotations    → quotation.drafted
              → quotation.approved
jobs          → job.created
              → job.completed
feedback      → feedback.received
              → ticket.opened
engagement    → outbound.requested
```

Key subscriptions:
- `feedback` ← `job.completed` (fires the delayed rating trigger)
- `engagement` ← `feedback.received` (applies suppression on low scores)
- `jobs` ← `quotation.approved` + customer acceptance
- `analytics` ← all events (rollup aggregation)

Payload shapes: TBD — to be specified in a follow-up section.

---

## 6. Data model

~16–18 core tables. **Not 60.** Use `jsonb` for flexible parts (extracted
requirements, raw provider payloads, per-vertical fields) to get schema
flexibility without table sprawl.

**Two modeling decisions that define the merge:**

1. **A lead and a customer are the same entity at different lifecycle stages.**
   One `contacts` table with `lifecycle_stage`. This is what makes it one system
   rather than two apps sharing a database.
2. **An approved-and-accepted quotation becomes a `job`.** Same object the
   back half calls an "order." This transition is the hinge.

Full schemas: TBD — to be specified in a follow-up section.

---

## 7. Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js + Tailwind on Vercel | Server components; mobile web is first-class |
| Backend | Python 3.12 + FastAPI | Stateless |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | **Non-negotiable** for evolving a multi-tenant schema |
| Database | PostgreSQL (managed: Neon / Supabase / RDS) | `jsonb` for flexible fields |
| Cache / broker | Redis (Upstash / ElastiCache) | Hot conversation window, rate-limit counters, Celery broker |
| Async | Celery + Celery Beat | Queue split — see below |
| LLM | Direct SDK calls + Pydantic structured output | See 7.1 |
| ML | scikit-learn | Lead scoring. Real train/test split, feature importance, honest metrics |
| Channels | **WhatsApp Cloud API (official)** | See 7.2 |
| Auth | JWT w/ embedded tenant claim, short-lived access + refresh, RBAC (owner/manager/agent) | Don't hand-roll if avoidable |
| Files | S3 | Media, generated quotation PDFs |
| Observability | Structured JSON logs w/ request ID threaded through every layer, Sentry, per-tenant usage dashboard | Cheap now; proves the scalability claim |
| Deploy | Docker Compose on single EC2 / Railway | **Resist Kubernetes.** Path to ECS/Fargate is a config change because code is stateless |
| Integrations / ops automation | **n8n, self-hosted in the EU, team-managed** | Edge only — see §7.4 |

### 7.1 On LangChain / LlamaIndex
**Recommendation: drop both from the core path.** The pipeline is deterministic
(classify → extract → decide → generate). Direct SDK calls with Pydantic models
are simpler, cheaper, faster, easier to debug, and easier to defend.
LangChain's abstractions earn their keep for open-ended agent loops with dynamic
tool selection — which this doesn't have.

**Counter-argument:** some supervisors expect a named agent framework in the
report. **Action item: ask Dr. Baloch before deciding.** If a framework is
required, keep LlamaIndex only for RAG over business documents / FAQs.

### 7.2 On WhatsApp providers
Use the **official Meta WhatsApp Cloud API**. Do **not** use GreenAPI or any
WhatsApp Web automation provider. They automate WhatsApp Web and get numbers
banned on exactly the outbound retention traffic this product depends on.

### 7.3 Celery queue split
Separate queues by workload class, **not one shared queue**:

| Queue | Character |
|---|---|
| `inbound` | Latency-sensitive — a customer is actively waiting |
| `ai` | Slow, expensive, externally rate-limited |
| `outbound` | Rate-limited per tenant per channel |
| `scheduled` | Nightly rollups, rating triggers, retention sends |

Reason: a nightly analytics job must never sit in front of a customer's reply.

### 7.4 n8n — integration edge, team-managed

**Decision (Sep 2026):** the team uses n8n to build and change integrations and
ops automations without code changes — alerts, Slack/email notifications,
Sheets/CRM sync, internal reports, per-customer glue. Workflows are managed by
the Rivon team only. **Tenants never get n8n access.**

**Why at the edge and not in the core:** the core pipeline (message → qualify →
score → feasibility → quote → approve) depends on properties n8n cannot give:
unit-tested deterministic pricing and feasibility (§2.2), idempotent sends
(§2.7), tenant isolation via RLS (§2.3), and auditable GDPR / AI Act behaviour
(§15). Putting it in n8n would also weaken the FYP's engineering claim.

```
Rivon core (Python)  ── outbox ──► signed webhook ──► n8n ──► Slack / email /
                                                         │     Sheets / CRM
        ◄──────────── public API (scoped service token) ─┘
```

**Rules:**
- **Inbound to n8n:** domain events from the outbox, delivered as HMAC-signed
  webhooks with retries, backoff and a DLQ (OPS-10). At-least-once — workflows
  dedupe on event ID.
- **Outbound from n8n:** only through Rivon's public API with a scoped,
  revocable service token. **No direct Postgres or Redis access**, ever.
- **Never computes** prices, feasibility, or lead scores.
- **Never messages a customer directly.** Customer-facing sends go through the
  Rivon API → `channels` outbound dispatcher, so dedupe, consent, opt-out and AI
  disclosure still apply.
- **Not on the critical path.** If n8n is down, leads are still qualified and
  quoted; webhook deliveries retry and then land in the DLQ for replay.
- **Data minimisation:** event payloads carry IDs and non-personal fields by
  default; workflows fetch personal data from the API only when they need it.
  n8n execution-log retention is kept short (days, not months).
- **GDPR:** n8n is self-hosted in the EU, alongside the rest of the stack. It
  appears in the records of processing (GDPR-05) and in the erasure design
  (GDPR-02) — personal data held in execution logs must be purgeable.
- **Version control:** workflows are exported as JSON to `n8n/workflows/` and
  reviewed like code. Credentials live in n8n's credential store, never in the
  exported JSON or the repo.

**Licence:** n8n is under the Sustainable Use License, which permits internal
business use — team-only use fits. Exposing n8n to tenants (letting them build
workflows) would likely require n8n's commercial Embed licence. **Verify the
licence terms before launch.**

---

## 8. Interaction surfaces

> **EU caveat:** the WhatsApp-first argument below was made for Pakistan/GCC.
> It holds for Southern Europe but not for Nordics/DACH — see §15.12 before
> relying on it.

~95% of all human interaction happens on WhatsApp — a client we didn't write and
don't maintain. State this ratio in the report; it justifies where the
engineering attention goes.

| Surface | User | Job | Why |
|---|---|---|---|
| **WhatsApp** (also IG, Messenger, web widget) | End customer | Entire qualification conversation | Zero install, zero signup. In PK/GCC, WhatsApp *is* the channel for local commerce. A competitor whose funnel starts with "visit our site" loses leads at that step. |
| **WhatsApp / Telegram card** | Business owner | Approve quotation — urgent, one-handed, 30s | He's on a roof. Template message w/ customer name, amount, lead score, feasibility verdict + quick-reply Approve/Reject + URL button to edit. Should never open a laptop for this. |
| **Next.js dashboard** | Business owner | Setup + analytics — deliberate, desktop, occasional | Rate cards, inventory, crew capacity = real data entry wanting a keyboard. Responsive, but designed desktop-first. |

**No native mobile app in v1.** The owner's urgent job is solved by a WhatsApp
message he's guaranteed to see; his slow job is better on desktop. An app serves
neither, and costs two platform builds plus an install step contractors won't
adopt. A PWA covers any later gap (offline job status, on-site photo capture).
Native only becomes justified with field operations, which is explicitly out of
scope.

### 8.1 Approval template detail
The approval notification is business-initiated → needs a **pre-approved
WhatsApp template**. Templates support static quick-reply buttons (Approve /
Reject) plus a URL button deep-linking to a single-screen mobile web view of the
quotation. This sidesteps interactive-message limits outside the 24-hour window.

**Submit this template early.** Approval takes weeks. A demo that can't send its
own approval notification is an avoidable disaster.

---

## 9. Scalability — what actually breaks

Do the arithmetic first: 200 tenants × 300 leads/mo × ~12 messages ≈ 24,000
messages/day ≈ well under 1 req/s average, ~20 req/s peak. **FastAPI on one
modest instance handles this. The API layer will never be the bottleneck.**
Neither will Postgres until well past 1,000 tenants.

The four things that actually break:

### 9.1 LLM cost per lead — the commercial make-or-break
EU pricing in EUR is still to be set (§15.11 — the old PKR 15,000–25,000/mo
Starter tier is void). Whatever the tier price, a 12-turn conversation where
every turn is a frontier-model call carrying the full business profile can burn a
meaningful fraction of that on one engaged lead.

Mitigations, in order of impact:
1. **Tiered model routing** — small cheap model for intent classification and
   routine turns; frontier model for requirement extraction and quotation
   narrative. Most turns are routine → several-fold cost cut, no quality loss.
2. **Prompt caching** — the business profile is large, static per tenant, and
   repeated every call. Highest-leverage cache in the system.
3. **Rules over inference** — feasibility, pricing, state transitions never call
   a model. Also the main cost control.
4. **Structured outputs** — eliminates parse-and-retry loops (a silent doubling).
5. **Per-tenant token budgets, enforced in code, metered per call** →
   `usage_events` is a **v1 requirement**, not a v2 nicety.

### 9.2 Provider rate limits
WhatsApp caps by tier + quality rating; LLM APIs cap tokens/min. Both external.
Handle with per-tenant token buckets in Redis, exponential backoff, circuit
breakers, DLQ with replay.

### 9.3 The `messages` table
The only unbounded-growth table. ~9M rows/year — Postgres handles it fine.
Design append-only **now**; plan monthly partitioning as a later migration.
Do not build partitioning yet.

### 9.4 Analytics on the write path
Covered by rule 2.8. Precomputed rollups now, read replica later.

**Governing principle: build for one instance, code so that N instances requires
no rewrite.** Stateless services, external state, queued work, no in-process
caching of anything mutable.

---

## 10. Tenant onboarding — the hard operational problem

**Each tenant needs their own WhatsApp Business number.** Customers message
*their* contractor, not us. One number cannot be shared across tenants.

Inbound routing: the `channels` table maps
`provider_phone_number_id → tenant_id`. That lookup is the first thing the
gateway does.

Every tenant onboarding therefore involves Meta Business verification + number
registration — slow, and friction we own. **Investigate WhatsApp Embedded Signup
(Tech Provider route)** so tenants connect their own number through our app
rather than us doing it manually per client.

For the FYP: one test number, one demo tenant. But **document the multi-number
design** — "how does this scale to 100 businesses" is a guaranteed viva question.

---

## 11. Scope discipline for the defense

Full merged scope is roughly double the original proposal, which was already
rated High complexity on four Washington Accord attributes. Three people,
academic deadline.

**Strategy: present the full merged architecture; implement a vertical slice.**
One vertical (solar), one channel (WhatsApp), one demo tenant, the complete loop
working end to end including the rating and ticket branch. Everything else
designed, documented, explicitly marked future work.

Examiners reward a working end-to-end system over an ambitious half-built one.
Deliberate scope discipline reads as engineering maturity, not shortfall.

| Depth | Modules |
|---|---|
| **Deep and complete** | `channels` (WhatsApp only), `conversations`, `leads`, `feasibility`, `quotations` |
| **Thin but working** | `platform`, `business`, `documents`, `analytics` |
| **Thin slice — enough to demo the closed loop** | `jobs`, `feedback` |
| **Designed, not implemented** | `engagement` |

### 11.2 Why `jobs` and `feedback` are in the FYP but not in commercial v1

These two documents appear to disagree; they don't. The split is deliberate:

- **Commercial v1** (`V1_SCOPE.md`) ships the funnel only. The post-sale half is
  v2, because the funnel is what generates revenue and doubling v1 delays it.
- **The FYP demo** needs a thin `jobs` + `feedback` slice anyway, because
  **closing the lifecycle loop is the project's novelty claim.** Without it the
  FYP is the original LeadCraft proposal and the merge contributed nothing
  academically.

"Thin slice" means: accepted quotation → job created → owner marks complete →
delayed rating request fires → 1–5 captured → low score opens a ticket. No
inventory reservation, no crew allocation, no SLA tracking, no timeline UI.
Roughly 15–20 days, not the full modules.

`V1_SCOPE.md` remains authoritative for what ships to paying tenants.
This section is authoritative for what gets built for the defense.

### 11.1 Demo plan
Phone 1: live WhatsApp conversation qualifying a lead.
Phone 2: owner approving the generated quotation.
Laptop: dashboard updating + rating loop firing.
Three screens, one continuous loop, no simulated data.

---

## 11.3 Build phases

Referenced by `FEATURE_LIST_V1.md`. Sizing and feature IDs live there; this is
the order and the reasoning.

| Phase | Focus | Why here |
|---|---|---|
| **0** | Foundations: repo, Docker, Postgres, Redis, Alembic, tenancy (PLT-01), outbox + one worker | Tenancy retrofitted is a rewrite. Prove isolation on day one. |
| **1** | Business config (`business` module, solar vertical config) | Unglamorous CRUD, but every later module reads from it |
| **2** | **Fake channel** + conversation core: internal message model, turn router, NLU, extraction | A test endpoint, no Meta account needed. Exercises the whole pipeline and stays as the permanent test harness. |
| **3** | Decision layer: `feasibility` then `quotations` | Feasibility before scoring — pure logic, no training data needed, and it's the differentiator |
| **4** | Lead scoring | Fourth, not second: only now are the real feature shapes known |
| **5** | WhatsApp adapter | The pipeline already works, so this phase is plumbing |
| **6** | Thin `jobs` + `feedback` (FYP only) | Closes the loop for the defense |
| **7** | Dashboard | Last: API contracts are stable, so each screen is built once |
| **8** | Polish, observability, demo rehearsal | — |

**Run in parallel from Phase 0, off-keyboard:** Meta Business verification,
WhatsApp template submission, EU hosting setup, legal engagement. All are
external, slow, and block late-phase work.

---

## 12. Known risks

| Risk | Detail | Mitigation |
|---|---|---|
| **WhatsApp policy** | Entire retention half depends on business-initiated outbound → requires pre-approved templates + 24-hour window rules. Neither source document mentioned this. **Largest operational risk.** | Official Cloud API. Design + submit templates early. Model the 24h window explicitly in `engagement` guardrails. |
| **Scope** | Merge roughly doubles an already-High-complexity project | Vertical slice (§11) |
| **ML cold start** | Lead scoring needs labeled outcomes that don't exist | Bootstrap with synthetic/heuristic labels for the FYP; design the labeling feedback loop as the production improvement mechanism. Be upfront — examiners will ask. |
| **LLM unit cost** | Could exceed subscription revenue per engaged lead | §9.1, and `usage_events` metering from day one |
| **Vertical mismatch** | A retail shop and a solar contractor do not want the same product | Build the service-business version. Retail mode is a documented extension path, not v1. |
| **Two masters** | A client expecting Sheets + n8n on a client timeline vs. an FYP on Postgres + FastAPI = building two systems badly | Either they become a tenant with a fitting vertical config (Sheets sync can be a team-managed n8n workflow at the edge, §7.4), or it's a separate engagement that does not touch this codebase. **Not a fork.** |
| **n8n creep** | Logic migrates into n8n workflows because it's quicker than code, until pricing or customer messaging depends on an untested flow | Hard rule 11 / §7.4. Code review of exported workflow JSON. Anything touching price, feasibility, score or a customer send goes in Python. |
| **Naming** | Collision with lead-craft.com (US SEO agency), already flagged in own market research | Resolve before landing page / domain |

---

## 13. Competitive context (for report framing)

| Platform | Segment | Pricing (2026) | What it does |
|---|---|---|---|
| QuoteIQ | SME home-service contractors | Company-tier | Closest benchmark. Broad CRM/FSM + AI quoting + review automation |
| DinoQuote | HVAC | — | Vertical-specialization benchmark |
| Jobber | Small-mid ($100K–1M rev) | $25–699/mo | Scheduling, quoting, invoicing, AI-assisted quoting |
| Housecall Pro | Solo–small (1–10 techs) | $59–299/mo | Scheduling, dispatch, payments, AI estimates |
| ServiceTitan | 20+ techs | ~$245–398/tech/mo | Enterprise FSM. Avoid copying breadth. |
| Rebar (US) | Commercial HVAC | VC-funded 2026 | Closest direct functional competitor found anywhere — HVAC-only AI quoting |
| PK chatbot agencies | Any local SME | PKR 50k–300k/mo | Qualification only, **no quotation layer** |
| GCC chatbot agencies | Any local SME | AED/SAR 15k–250k+ one-time | Qualification only, **no quotation layer** |

**The gap:** no reviewed product combines conversational qualification + ML
scoring + rule-based feasibility + capacity-aware quotation into one pipeline for
these verticals. This is the most defensible claim in the research because it
rests on an absence found across many searches, not a single fragile statistic.

Adding the lifecycle half strengthens it further — QuoteIQ, Jobber and Housecall
Pro all ship review automation, so closing the loop turns a gap into parity-plus.

**Do NOT:** clone QuoteIQ's full ecosystem · build accounting/ERP/payroll ·
build route optimization · build warehouse management · target every vertical
day one · use "AI-powered" as the only differentiation · compete on price alone.

---

## 14. Report framing notes

Name these patterns explicitly — it reads as deliberate design:
- Hexagonal architecture (channel layer)
- Shared-schema multi-tenancy with row-level security
- Modular monolith with extraction path to services
- Event-driven orchestration via transactional outbox
- Strategy pattern for vertical-specific rules
- CQRS-lite for analytics
- Light event sourcing for the job timeline

**Include a section on what was deliberately NOT done** — microservices,
per-tenant schemas, Kubernetes, LangChain in the core path — with reasoning.
Justified restraint is one of the strongest signals of engineering judgment
available, and most student projects lack it.

**Include the intelligence-type table from §2.2.** Seven of eleven modules
involve no AI at all. Stating that explicitly is the best answer to "isn't this
a GPT wrapper?"

---

## 15. EU / EEA compliance requirements

> Researched 19 Sep 2026. **Not legal advice** — verify against primary sources
> before any commercial launch. The engineering requirements below are cheap if
> designed in now and expensive to retrofit.

Both regimes are **extraterritorial**: they apply based on where the *people* are,
not where the company is. Being based in Pakistan provides no shelter if the
system serves EU users or its output is used in the EU.

### 15.1 EU AI Act — current status

The timeline was amended by **Regulation (EU) 2026/1744**, published in the
Official Journal on 24 July 2026 and now in force. Live milestones:

| Date | What |
|---|---|
| Already live | Prohibited practices (Art 5), AI literacy (Art 4), GPAI rules |
| **2 Aug 2026** | **Article 50 transparency obligations — ALREADY APPLICABLE** |
| 2 Dec 2026 | New prohibitions + transitional marking requirements |
| 2 Dec 2027 | Annex III standalone high-risk systems |
| 2 Aug 2028 | Annex I product-embedded high-risk systems |

### 15.2 Risk classification of this system

**Assessment: limited-risk / transparency-only, NOT high-risk.** B2B lead
qualification and quotation for service businesses is not an Annex III category.

**Two things would push it into high-risk. Avoid both by design:**

1. **Do not let lead scoring become creditworthiness assessment of natural
   persons.** Creditworthiness evaluation *is* Annex III. Score intent, urgency,
   requirement completeness, and service compatibility. Never score ability to
   pay, payment history, or financial standing of an individual.
2. **Be careful with the sentiment/emotion component.** Emotion recognition in
   workplace and education contexts is prohibited outright under Art 5. Customer
   -message sentiment is outside those contexts, but Art 50(3) requires deployers
   of emotion recognition systems to inform exposed persons. **Design decision:
   label this component "sentiment classification for routing and escalation,"
   keep it operating on message text only, and never infer emotional state of a
   person as such.**

Record this classification assessment in writing. It is the document a regulator
or an enterprise buyer asks for first.

### 15.3 Article 50 — the bot must announce itself (HARD REQUIREMENT)

Providers of AI systems that interact directly with natural persons must design
them so people are informed they are dealing with AI, unless it is obvious to a
reasonably well-informed person. Disclosure must come **at first contact**, be
clearly noticeable, and not buried in a terms page. For a chatbot this means
before or at the very beginning of the conversation. In some contexts one-time
disclosure is insufficient and must be repeated.

**Implementation:**
- First outbound message of every new conversation carries the AI disclosure.
- Disclosure text is per-tenant configurable but **not disableable**.
- Repeat the disclosure when a conversation resumes after a long gap, and when
  handing back from human to bot.
- On handoff to a human agent, say so — the transition must be visible.
- Log the disclosure as an event. "We disclosed" is a claim you must evidence.

Penalties for Art 50 breaches reach **€15 million or 3% of worldwide turnover**.

Art 50(2) machine-readable marking of synthetic content sits mainly with the
upstream model provider (OpenAI/Gemini) rather than with us as deployer. The
Art 50(4) duty to label AI-generated text applies to text published to inform
the public on matters of public interest — a quotation is not that, so it does
not bite here.

### 15.4 GDPR Article 22 — THIS CONTRADICTS THE CURRENT DESIGN

Art 22 restricts decisions based **solely** on automated processing that produce
legal effects or similarly significantly affect a person. In **SCHUFA
(C-634/21)** the CJEU held that automated scoring can itself be the relevant
decision where a third party draws strongly on that score in deciding whether to
enter a contractual relationship. Case law is also explicit that **a nominal
human sign-off does not establish meaningful human intervention** — the whole
decision process is examined.

**Where we are fine:** the quotation path. `quotation.drafted → owner reviews →
Approve / Edit / Reject` is genuine human intervention, and the owner sees the
score and feasibility verdict before deciding.

**Where we are NOT fine:** the activity diagram's `Feasible? → No → Notify
customer, not feasible → Lead closed` branch, and any auto-disqualification on
low lead score. **These reject a person with no human in the loop.** Under
SCHUFA reasoning, that is exactly the shape Art 22 catches.

**Required design changes:**
- Auto-rejection on score or feasibility must **not** be the terminal state for
  an EU-region tenant. Either route the rejection to the owner for confirmation,
  or make the outcome non-final ("we can't serve this right now" + a route to a
  human) rather than a closed door.
- Feasibility failures must return **reasons** (already specified in §4) and
  those reasons must be surfaceable to the person.
- Provide a documented path to request human review of any automated outcome —
  an endpoint plus a message-triggered route, not just an email address.
- Record the score, the model version, the input features, and the human
  decision for every lead. Explainability is not optional here.
- `feature_flags` gains a per-tenant `eu_region` flag that enforces the
  human-confirmation path.

### 15.5 ePrivacy — the retention half needs consent

Direct electronic marketing generally requires **prior opt-in consent** under
Art 13 ePrivacy Directive. The `engagement` module is squarely in scope.

**Soft opt-in exception (Art 13(2))**, available where all three hold: the
contact details were obtained in the context of a sale of a product or service;
the marketing is for the organisation's own **similar** products or services;
and the person can object easily and free of charge **both at collection and in
every subsequent message**.

**Inteligo Media SA v ANSPDCP (C-654/23, 13 Nov 2025)** confirmed that ePrivacy
is *lex specialis* — where the soft opt-in conditions are met, no separate GDPR
Art 6 legal basis is needed. The exception is to be construed narrowly.

**Practical classification for the `engagement` module:**

| Message type | Basis | Notes |
|---|---|---|
| Post-job rating request | Service message, not marketing | Safest category. Keep it purely about the completed job — no offer attached. |
| Maintenance-due reminder | Soft opt-in likely available | Tied to a prior sale, genuinely similar service |
| Seasonal promo, win-back, coupon | **Marketing — needs consent or soft opt-in** | Highest risk |
| Referral ask | Marketing | Treat as marketing |

**Implementation:**
- Opt-out link/keyword in **every** outbound marketing message. Not optional.
- Consent capture at point of collection, with timestamp, source, and wording
  version stored — `consents` table already exists; add `consent_text_version`.
- Do not mix an offer into the rating request. Keeping them separate is what
  keeps the rating request in the service-message category.
- **Member state implementations differ.** Germany is strictest and requires
  double opt-in per binding court ruling; Austria and Greece regulators expect
  it too. B2B is treated more leniently in NL/UK/IE/BE/Nordics. Make the consent
  model **per-tenant-jurisdiction configurable**, not one global setting.

### 15.6 International transfers — ARCHITECTURE DECISION

Pakistan has **no EU adequacy decision**. Transfers from an EEA tenant to us
require appropriate safeguards — in practice the 2021 **Standard Contractual
Clauses** (Commission Implementing Decision (EU) 2021/914), Module 2
(controller-to-processor) or Module 3 (processor-to-processor), plus a documented
transfer impact assessment of the destination country's legal environment.

**The engineering answer that shrinks this problem: host EU tenant data in the
EU.** Postgres, Redis, and S3 in an EU region (Frankfurt / Ireland). Then the
only transfer surface is support access from Pakistan, which is far easier to
document and restrict.

**Requires in the architecture:**
- Region as a **tenant-level attribute**, decided at provisioning. Not a global
  config, and not something that can be changed later without a migration.
- An EU deployment target from the start — even if unused during the FYP, the
  code must not assume a single region.
- Check LLM provider EU data-residency options (both OpenAI and Google offer
  EU processing terms) and record them as sub-processor commitments.
- Audit-logged, least-privilege, justified support access to EU data.

### 15.7 Our dual role, and the paperwork

We are a **processor** for tenant customer data and a **controller** for tenant
account data. Both roles carry obligations.

| Requirement | Detail |
|---|---|
| **Art 28 DPA** | Must offer every tenant a Data Processing Agreement. Also a hard requirement in any serious B2B sale. |
| **Art 27 EU representative** | Non-EU controllers/processors serving EU data subjects must appoint one, established in a member state where the data subjects are. The representative can be held **directly liable** under Art 27(4). Ireland, Netherlands, Germany are common choices. |
| **Sub-processor disclosure** | OpenAI/Google, AWS, Meta are sub-processors. Publish the list; notify tenants of changes. |
| **Records of processing (Art 30)** | Maintain them. |
| **DPIA (Art 35)** | Likely required — systematic profiling at scale. Do it before EU launch. |
| **Art 4 AI literacy** | Already live. Keep training records. |

### 15.8 Data subject rights — build these as endpoints

Not policy documents. Actual working functionality, per tenant:

- **Access / portability** — export all data for one contact, machine-readable
- **Erasure** — hard delete across `contacts`, `messages`, `conversations`,
  `feedback`, and derived scores. Design for this now: cascade rules and an
  anonymise-vs-delete decision per table.
- **Rectification** — edit a contact's data
- **Objection to profiling** — a flag that disables scoring for that contact
- **Human review of an automated decision** — see §15.4

Note the tension with §2.7's append-only `messages` table and the job event
timeline. Resolve it deliberately: crypto-shredding or field-level redaction
rather than row deletion, documented either way.

### 15.9 Also check before EU launch

- **European Accessibility Act** — in application since 28 June 2025 for certain
  products and services; whether a B2B SaaS dashboard is in scope depends on the
  service category and member state implementation. **Not verified in this
  research.** Building the dashboard to WCAG 2.1 AA / EN 301 549 is the safe
  default and is good practice regardless.
- **Data Act**, **NIS2** — likely out of scope at this size, but confirm.
- **Consent for the web widget** — cookie/consent banner obligations apply to
  the tenant's site, which affects widget design.

### 15.10 What to actually do for the FYP

The full programme — Art 27 representative, SCCs, DPIA, DPA templates, records
of processing — is **legal work that costs money**, not engineering work. Do not
attempt to complete it for the FYP.

**Build compliance-ready architecture; document the legal steps as a launch
checklist.** Specifically, implement:

1. AI disclosure at conversation start, logged (§15.3)
2. No terminal auto-rejection; human-confirmation path (§15.4)
3. Consent records with versioned text + opt-out in every marketing message (§15.5)
4. Tenant-level region attribute (§15.6)
5. Data subject rights endpoints (§15.8)
6. Model version + input features recorded per score (§15.4)

Then write a compliance chapter covering the classification assessment, the Art
22 analysis, and the launch checklist. **This is a genuine differentiator in an
FYP** — most student projects have no compliance chapter at all, and it directly
supports the Bluell AB (Sweden) advisory relationship and any Nordic go-to-market.

### 15.11 DECIDED: the EU is the launch market

**Confirmed Sep 2026.** This is now a launch-market decision, not a design
property. Consequences that follow automatically:

| Consequence | Detail |
|---|---|
| **EU hosting from day one** | Postgres, Redis, S3 in Frankfurt or Ireland. Not a later migration. OPS-08 moves into the critical path. |
| **Legal work is on the critical path** | Art 27 representative, SCCs, DPIA, DPA template all required before the first paying tenant, not "before launch someday". Budget real money. |
| **The §15.10 list is mandatory, in full** | Not a subset. |
| **LLM provider EU processing terms** | Must be signed and recorded as sub-processor commitments before any real personal data flows. |
| **Pricing must be rebuilt** | The PKR/AED/SAR tiers in the market research are void. **All pricing in EUR**, set against the EU competitive set at EU price points. |
| **Language** | **English only** (decided Sep 2026). No second language in v1, whichever EU market is first. |

**Open issue this creates — see §15.12.**

### 15.12 The EU decision undermines the WhatsApp-first thesis

This needs resolving before the channel work starts, because it may change what
v1's primary channel is.

The "~95% of interaction happens on WhatsApp" argument (§8) was built on
Pakistan and the GCC, where WhatsApp genuinely is the default channel for local
commerce. **That does not transfer evenly to the EU.**

- WhatsApp is dominant for business messaging in **Southern Europe** — Spain,
  Italy, Portugal, Greece.
- In the **Nordics and Germany** — the markets the research flagged for high AI
  adoption, and where the Bluell AB relationship sits — a contractor lead is far
  more likely to arrive by **web form, email, or phone call**.
- EU business-messaging norms also carry stronger expectations around consent
  and channel choice than PK/GCC.

**Implications to decide:**
1. **Which EU market first?** Southern Europe keeps WhatsApp-first intact.
   Nordics/DACH probably makes the **web widget** the primary channel and
   WhatsApp secondary.
2. If Nordics/DACH: CHN-09 (web widget) is promoted from "nice to have" to
   primary, and **email becomes a required inbound channel**, not just a
   quotation delivery option. That is a new adapter and new v1 scope.
3. The adapter pattern (§2.1) is what makes this survivable — the core pipeline
   is unchanged either way. This is the payoff for building it properly.

**Do not start CHN work until the first EU market is named.**

---

## 16. Open items

- [ ] **Rivon** trademark search — PK, UAE, Saudi, EU
- [ ] **Rivon** domain acquisition (`rivon.ai` preferred)
- [ ] Check for existing SaaS named Rivon (Product Hunt, Shopify App Store, Crunchbase)
- [ ] Ask Dr. Baloch: is a named agent framework expected in the report? (§7.1)
- [ ] Full table schemas (§6)
- [ ] Event payload shapes (§5)
- [ ] Per-vertical requirement schemas (solar first)
- [ ] WhatsApp message template drafts + submission
- [ ] Investigate WhatsApp Embedded Signup / Tech Provider route (§10)
- [ ] Model LLM cost per lead against Starter tier pricing (§9.1)
- [ ] Decide status of the retail/Alma client engagement (§12, "two masters")
- [ ] Phased build plan with defense-deliverable vs. documented-future split
- [x] ~~Decide: EU as launch market, or EU-readiness as design property?~~ **EU is the launch market (§15.11)**
- [x] ~~Second language~~ **English only**
- [ ] **Name the first EU market** — decides the primary channel (§15.12)
- [ ] EU pricing tiers in EUR (§9.1, §15.11)
- [ ] Verify n8n licence terms for team-only internal use (§7.4)
- [ ] Redesign the `Not feasible → Lead closed` branch in the activity diagram (§15.4)
- [ ] Write the AI Act risk classification assessment (§15.2)
- [ ] Draft AI disclosure text + repeat-disclosure rules (§15.3)
- [ ] Add `consent_text_version` to `consents`; per-jurisdiction consent model (§15.5)
- [ ] Add tenant-level `region` attribute + EU deployment target (§15.6)
- [ ] Check OpenAI / Google EU data residency terms (§15.6)
- [ ] Verify European Accessibility Act applicability to a B2B SaaS dashboard (§15.9)
