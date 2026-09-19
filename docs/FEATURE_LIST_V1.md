# Rivon — V1 Feature List (for costing & architecture)

> Companion to `PROJECT_SPEC.md` (architecture, stack, compliance) and
> `V1_SCOPE.md` (scope reasoning, what's deferred and why).
> **Purpose:** a feature-by-feature breakdown, grouped by module, sized for cost
> estimation and safe to design architecture against.

---

## 0. Read this before costing

**Decisions that affect cost — decided ones struck through, open ones in bold.**

| Open decision | Cost impact |
|---|---|
| **Platform target: service SMEs vs Shopify retail** | **MAJOR.** Shopify retail deletes modules FEAS and QUOT entirely (~30% of the build) and replaces CHN. **This list assumes service SMEs — the approved FYP proposal.** |
| Pilot tenant identity | None on cost; changes which vertical schema is built first |
| ~~EU as launch market~~ **DECIDED: EU is the launch market** | Adds OPS-08 (EU hosting) to the critical path and puts legal spend on the critical path. **Also voids the PKR/AED pricing tiers — all pricing now in EUR.** |
| ~~Second language~~ **DECIDED: English only** | None — removes a localisation cost |
| ~~n8n~~ **DECIDED: team-managed n8n at the edge** | Adds OPS-10/11 (~6 days). No change to core modules. |
| **NEW BLOCKER: which EU market first?** | **MAJOR on CHN.** Southern Europe keeps WhatsApp primary. Nordics/DACH makes the web widget primary and adds an **email inbound adapter** — new v1 scope. See spec §15.12. Do not cost CHN until settled. |
| Invite-only vs self-serve provisioning | Minor — self-serve adds PLT-08 and billing integration |

Everything below is **locked conditional on the service-SME path**. If the
platform target changes, this document is void and needs rewriting, not
patching.

### Sizing key
Effort is in **person-days for one experienced full-stack developer**, excluding
requirements clarification and excluding the FYP report. Apply your own
multiplier for a 3-person student team working around coursework — 2x to 2.5x
is realistic.

| Size | Days |
|---|---|
| S | 1–2 |
| M | 3–5 |
| L | 6–10 |
| XL | 11–20 |

---

## Module PLT — Platform & Tenancy
*Owns: `tenants`, `users`, `roles`, `plans`, `feature_flags`, `usage_events`, `audit_log`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| PLT-01 | Multi-tenant schema foundation: `tenant_id` on all tables, RLS policies, `TenantContext` FastAPI dependency | L | — |
| PLT-02 | Owner auth: registration, login, JWT + refresh, password reset | M | PLT-01 |
| PLT-03 | RBAC: owner / manager / agent roles + permission checks | M | PLT-02 |
| PLT-04 | Tenant provisioning (invite-only): create tenant, invite owner, activate | M | PLT-02 |
| PLT-05 | Tenant `region` attribute (EU / non-EU) + region-aware config resolution | S | PLT-01 |
| PLT-06 | Plan tiers as data + per-tenant feature flags | M | PLT-01 |
| PLT-07 | Usage metering: `usage_events` written per LLM call and per message, with cost attribution | M | PLT-01 |
| PLT-08 | Quota enforcement: soft warning threshold, hard stop, per-plan limits | M | PLT-07 |
| PLT-09 | Audit log for owner actions (approvals, edits, config changes) | S | PLT-03 |

**Subtotal: ~30 days**

> PLT-01 is the highest-risk item in the entire build. Retrofitting tenancy is a
> rewrite. Write the "tenant A cannot read tenant B" test on day one.

---

## Module BIZ — Business Profile & Configuration
*Owns: `businesses`, `services`, `pricing_rules`, `service_areas`, `inventory_items`, `workforce`, `verticals`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| BIZ-01 | Business profile CRUD (name, contact, hours, min/max project size) | M | PLT-01 |
| BIZ-02 | Services catalogue CRUD | M | BIZ-01 |
| BIZ-03 | Pricing rules engine data model: rate cards, per-unit costs, labour, transport, margin targets | L | BIZ-02 |
| BIZ-04 | Discount rules | M | BIZ-03 |
| BIZ-05 | Service areas (named regions/cities — not polygons in v1) | S | BIZ-01 |
| BIZ-06 | Inventory items + quantities | M | BIZ-01 |
| BIZ-07 | Workforce / crews + availability | M | BIZ-01 |
| BIZ-08 | Vertical config framework (requirement schema, question set, pricing rule types per vertical) — **solar only in v1** | L | BIZ-02 |
| BIZ-09 | Guided onboarding wizard: progress, partial save, skip-for-now, incomplete indicators | L | BIZ-01…08 |
| BIZ-10 | Sandbox mode — owner chats with their own bot before going live | M | CNV-04 |

**Subtotal: ~42 days**

> BIZ-08 is what makes customization configuration-not-code (spec §2.3). Build it
> as a framework even though only one vertical uses it, or v2 becomes a rewrite.

---

## Module DOC — Business Knowledge Documents
*Owns: `documents`, `document_chunks` (schema only in v1)*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| DOC-01 | Document upload (PDF/DOCX/TXT), storage to S3, per-tenant corpus | M | PLT-01 |
| DOC-02 | Text extraction pipeline | M | DOC-01 |
| DOC-03 | Full-context injection with prompt caching + per-tenant token budget | M | DOC-02, CNV-03 |
| DOC-04 | Draft profile extraction at onboarding (pre-fill services/products/policies, owner confirms) | L | DOC-02, BIZ-09 |
| DOC-05 | Document library view: list, age display, review prompt, delete (text + embeddings together) | M | DOC-01 |
| DOC-06 | PII pattern scan on upload + warning | S | DOC-02 |
| DOC-07 | Contradiction flag at upload | M | DOC-02 |

**Subtotal: ~22 days**

> **No vector RAG in v1.** `pgvector` retrieval is a fallback strategy behind the
> same interface, built only when a tenant exceeds the token budget. Reserve the
> `document_chunks` table now; leave it empty.
>
> **Hard boundary:** the document-context service must not be injected into FEAS
> or QUOT. Enforce structurally, not by prompt instruction.

---

## Module CHN — Channels
*Owns: `channels`, `messages`, `outbound_queue`, `consents`, `message_templates`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| CHN-01 | Internal message model + inbound normalization interface (adapter pattern) | M | PLT-01 |
| CHN-02 | WhatsApp Cloud API inbound: webhook receiver, signature verification, raw payload persist, enqueue, fast 200 | L | CHN-01 |
| CHN-03 | Tenant routing: `provider_phone_number_id → tenant_id` | S | CHN-01 |
| CHN-04 | Idempotency: unique `(tenant_id, provider_message_id)` + replay test | S | CHN-02 |
| CHN-05 | Outbound dispatcher: single queue, dedupe key, backoff, per-tenant rate limits, DLQ | L | CHN-01 |
| CHN-06 | WhatsApp template management + approval-card template | M | CHN-05 |
| CHN-07 | Channel credential storage (encrypted) + token refresh | M | CHN-03 |
| CHN-08 | Per-channel health check + auth-failure alerting | M | CHN-07 |
| CHN-09 | Web widget (embeddable JS) + tenant embed key | L | CHN-01 |
| CHN-10 | Telegram adapter (owner-side only, bot token) | M | CHN-01, CHN-05 |
| CHN-11 | Consent records: timestamp, source, `consent_text_version` | S | PLT-01 |
| CHN-12 | Opt-out keyword/link handling | S | CHN-05, CHN-11 |

**Subtotal: ~45 days**

> The adapter interface (CHN-01) is what makes Instagram/Messenger a contained
> addition in v2 rather than a refactor. Do not shortcut it because v1 has one
> real channel.
>
> **External dependency with a multi-week lead time:** Meta Business verification
> and template approval. Start during the first sprint, not when CHN-06 begins.

---

## Module CNV — Conversation & Agent
*Owns: `conversations`, `conversation_state`, `extracted_requirements`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| CNV-01 | Conversation + message persistence (append-only messages), state in Postgres | M | CHN-01 |
| CNV-02 | Turn router: intent classification → handler dispatch (qualification / service / general) | L | CNV-01 |
| CNV-03 | Tiered model routing + prompt caching infrastructure | M | CNV-02, PLT-07 |
| CNV-04 | Qualification dialogue — asks only for fields still missing | L | CNV-02, BIZ-08 |
| CNV-05 | Requirement extraction to per-vertical JSON schema (Pydantic-enforced structured output) | L | CNV-04, BIZ-08 |
| CNV-06 | Sentiment classification for routing/escalation only | S | CNV-02 |
| CNV-07 | Bot ↔ human handoff (take over live conversation, hand back) | L | CNV-02 |
| CNV-08 | Failure surfacing: bot admits uncertainty, flags conversation for owner | M | CNV-02 |
| CNV-09 | AI disclosure at conversation start — configurable, not disableable, logged as event, repeat on resume and on handoff | M | CNV-01, CHN-05 |

**Subtotal: ~48 days**

> CNV-09 is a **legal requirement**, not a feature (AI Act Art 50, applicable
> since 2 Aug 2026). Penalties reach €15M / 3% turnover.

---

## Module LEAD — Contacts & Lead Scoring
*Owns: `contacts`, `lead_scores`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| LEAD-01 | Unified `contacts` model with `lifecycle_stage` (the lead/customer merge point) | M | PLT-01 |
| LEAD-02 | Contact dedupe + phone normalization | M | LEAD-01 |
| LEAD-03 | Feature engineering pipeline for scoring | M | CNV-05, LEAD-01 |
| LEAD-04 | Synthetic/bootstrap training dataset generation | M | LEAD-03 |
| LEAD-05 | scikit-learn model: train, evaluate, feature importance, model selection | L | LEAD-04 |
| LEAD-06 | Scoring service + per-score persistence of model version and input features | M | LEAD-05 |
| LEAD-07 | Objection-to-profiling flag (disables scoring for a contact) | S | LEAD-06 |

**Subtotal: ~27 days**

> LEAD-04/05 is the part FYP examiners probe hardest. Budget time for honest
> evaluation, not just a trained artifact.
> **Constraint:** never score ability to pay or financial standing — that becomes
> creditworthiness assessment, which is Annex III high-risk (spec §15.2).

---

## Module FEAS — Feasibility Engine
*Owns: `feasibility_results`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| FEAS-01 | Rules engine framework (strategy pattern, per-vertical rule sets) | L | BIZ-08 |
| FEAS-02 | Service match check | S | FEAS-01, BIZ-02 |
| FEAS-03 | Service-area match check | S | FEAS-01, BIZ-05 |
| FEAS-04 | Inventory sufficiency check | M | FEAS-01, BIZ-06 |
| FEAS-05 | Workforce/crew availability check | M | FEAS-01, BIZ-07 |
| FEAS-06 | Project size bounds check | S | FEAS-01, BIZ-01 |
| FEAS-07 | Structured reason output (not just pass/fail) | M | FEAS-02…06 |
| FEAS-08 | **Non-terminal rejection path** — route to owner or produce non-final outcome with human route | M | FEAS-07, QUOT-05 |
| FEAS-09 | Human-review request endpoint + message-triggered route | M | FEAS-08 |

**Subtotal: ~28 days**

> **Zero LLM calls in this module.** It is the differentiator and the most
> unit-testable component — heavy test coverage here goes in the report.
>
> FEAS-08/09 are **required by GDPR Art 22** (SCHUFA, C-634/21). The original
> activity diagram's `not feasible → lead closed` terminal state is
> non-compliant. This is a design change, not an optional extra.

---

## Module QUOT — Quotation & Approval
*Owns: `quotations`, `quotation_items`, `approvals`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| QUOT-01 | Deterministic pricing calculator against rate card + margin logic | L | BIZ-03, CNV-05 |
| QUOT-02 | Quotation + line item data model, status lifecycle | M | QUOT-01 |
| QUOT-03 | LLM covering narrative (wording only, never numbers) | M | QUOT-02 |
| QUOT-04 | Good–Better–Best tiering | M | QUOT-01 |
| QUOT-05 | Phone-first approval card: Approve / Reject quick replies + URL button | L | CHN-06, QUOT-02 |
| QUOT-06 | Mobile web single-screen edit view | M | QUOT-05 |
| QUOT-07 | Dashboard approval path | M | QUOT-02, DASH-01 |
| QUOT-08 | Edit-before-approve with sync back | M | QUOT-06, QUOT-07 |
| QUOT-09 | PDF generation | M | QUOT-02 |
| QUOT-10 | Delivery on original channel | M | QUOT-09, CHN-05 |
| QUOT-11 | Email delivery of PDF | M | QUOT-09 |
| QUOT-12 | Status tracking: draft → pending → approved/rejected → sent → accepted/declined | M | QUOT-02 |

**Subtotal: ~48 days**

> QUOT-04 (Good–Better–Best) is the one item here that can slip to v1.1 without
> breaking the product.

---

## Module DASH — Owner Dashboard (Next.js)

| ID | Feature | Size | Depends on |
|---|---|---|---|
| DASH-01 | App shell: auth, layout, tenant context, responsive | M | PLT-02 |
| DASH-02 | Lead list: score, status, source, filtering | M | LEAD-01 |
| DASH-03 | **Conversation viewer** — owner reads exactly what the bot said | L | CNV-01 |
| DASH-04 | Quotation queue (pending) + history | M | QUOT-02 |
| DASH-05 | Business profile editing screens (reuses onboarding forms) | L | BIZ-01…08 |
| DASH-06 | Document library UI | M | DOC-05 |
| DASH-07 | Analytics: lead volume, qualification rate, quote conversion, avg value, response time | L | ANL-02 |
| DASH-08 | Usage / quota display against plan | S | PLT-08 |
| DASH-09 | New-lead notification to owner | M | LEAD-06, CHN-05 |
| DASH-10 | Data subject rights UI: export, erase, rectify, object | M | GDPR-01…04 |

**Subtotal: ~42 days**

> DASH-03 is the highest-value item in this module. Without it no contractor will
> let a bot speak to their customers. Rank it above analytics.

---

## Module ANL — Analytics
*Owns: `daily_rollups`*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| ANL-01 | Domain event capture into rollup source | M | OPS-02 |
| ANL-02 | Nightly rollup aggregation job | M | ANL-01 |
| ANL-03 | Read API for dashboard (never queries live operational tables) | S | ANL-02 |

**Subtotal: ~10 days**

---

## Module OPS — Operations & Infrastructure

| ID | Feature | Size | Depends on |
|---|---|---|---|
| OPS-01 | Docker Compose local + deploy environment; CI/CD via GitHub Actions | M | — |
| OPS-02 | Transactional outbox + Celery event consumers | L | PLT-01 |
| OPS-03 | Celery queue split: `inbound` / `ai` / `outbound` / `scheduled` + Beat | M | OPS-02 |
| OPS-04 | Structured JSON logging with request ID threaded through all layers | M | — |
| OPS-05 | Sentry integration | S | OPS-01 |
| OPS-06 | Redis: conversation cache + rate-limit token buckets | M | OPS-03 |
| OPS-07 | Backups + **tested restore** | M | OPS-01 |
| OPS-08 | EU deployment target (region-aware infra) | M | PLT-05, OPS-01 |
| OPS-09 | Alembic migration baseline + conventions | S | PLT-01 |
| OPS-10 | Outbound event webhooks for n8n: HMAC-signed, per-destination event allowlist, retries + backoff, DLQ + replay, minimal (ID-first) payloads | M | OPS-02 |
| OPS-11 | n8n service: self-hosted EU in Compose, team-only access, scoped/revocable API service tokens, short execution-log retention, workflow JSON exported to `n8n/workflows/` | S | OPS-01, OPS-10, PLT-02 |

**Subtotal: ~38 days**

> OPS-10/11 put n8n at the **edge** (spec §7.4, CLAUDE.md hard rule 11). n8n
> never computes prices/feasibility/scores, never touches the database, and
> never messages a customer except via the Rivon API.

---

## Module GDPR — Compliance Engineering
*Cross-cutting. Listed separately so it is costed, not absorbed.*

| ID | Feature | Size | Depends on |
|---|---|---|---|
| GDPR-01 | Data export endpoint (machine-readable, all data for one contact) | M | LEAD-01, CNV-01 |
| GDPR-02 | Erasure: cascade rules across contacts/messages/conversations/scores + documented crypto-shred or field-redaction strategy vs append-only messages | L | GDPR-01 |
| GDPR-03 | Rectification endpoint | S | GDPR-01 |
| GDPR-04 | Per-jurisdiction consent model configuration | M | CHN-11 |
| GDPR-05 | Records-of-processing support (what's stored where, per tenant) | S | PLT-01 |

**Subtotal: ~16 days**

> Legal deliverables — privacy notice, ToS, DPA template, sub-processor list, AI
> Act risk classification, DPIA, Art 27 representative — are **legal spend, not
> engineering days.** Cost them separately. Not required for the FYP demo;
> required before the first real tenant.

---

## Module SITE — Marketing Site

| ID | Feature | Size | Depends on |
|---|---|---|---|
| SITE-01 | Static Next.js landing page: positioning, pricing, waitlist form | M | — |
| SITE-02 | Demo video or interactive demo | M | v1 working |
| SITE-03 | Legal pages + cookie consent banner | S | GDPR docs |

**Subtotal: ~9 days**

> Cheapest artifact in v1 and the easiest to over-polish. Do not let it consume
> dashboard time.

---

## Totals

| Module | Days | % |
|---|---|---|
| PLT — Platform & Tenancy | 30 | 7% |
| BIZ — Business Profile | 42 | 10% |
| DOC — Knowledge Documents | 22 | 5% |
| CHN — Channels | 45 | 11% |
| CNV — Conversation & Agent | 48 | 12% |
| LEAD — Contacts & Scoring | 27 | 7% |
| FEAS — Feasibility | 28 | 7% |
| QUOT — Quotation & Approval | 48 | 12% |
| DASH — Dashboard | 42 | 10% |
| ANL — Analytics | 10 | 2% |
| OPS — Operations | 38 | 9% |
| GDPR — Compliance | 16 | 4% |
| SITE — Marketing | 9 | 2% |
| **Subtotal** | **405** | |
| Integration, bug-fixing, polish (+20%) | 81 | |
| **TOTAL** | **~486 person-days** | |

**Roughly 97 person-weeks, or ~24 person-months for experienced developers.**

Sanity checks on that number:
- 3 experienced full-time developers: ~8 months
- 3 students around coursework, 2x multiplier: **well over an academic year**
- **Conclusion: v1 as fully specified does not fit the FYP timeline.** See below.

---

## FYP subset — what to actually build for the defense

The defense needs the loop working end to end, not every feature. Cut to a
demonstrable vertical slice and mark the rest designed-not-implemented.

**Build (target ~160–190 days across the team, including the jobs/feedback thin slice):**

| Keep | Items |
|---|---|
| PLT | 01, 02, 05, 07 (skip RBAC depth, plans, quota enforcement, audit log) |
| BIZ | 01, 02, 03, 05, 06, 07, 08 (skip 04 discounts, 09 wizard — plain forms are fine, 10 sandbox) |
| DOC | 01, 02, 03 (skip 04, 05, 06, 07) |
| CHN | 01, 02, 03, 04, 05, 06, 11 (skip web widget, Telegram, health checks, token refresh) |
| CNV | 01, 02, **03**, 04, 05, 09 (skip sentiment, handoff, failure surfacing). **CNV-03 is required — DOC-03 depends on it, and it is the LLM cost control.** |
| LEAD | 01, 03, 04, 05, 06 (skip dedupe, profiling flag) |
| FEAS | **all of it** — this is the differentiator |
| QUOT | 01, 02, 03, 05, 09, 10, 12 (skip tiering, mobile edit, dashboard approval, email) |
| DASH | 01, 02, 03, 05 (basic), 07 (basic) |
| ANL | 01, 02, 03 |
| OPS | 01, 02, 03, 04, 09, 10, 11 (n8n edge — cheap, and shows the event-driven design paying off) |
| GDPR | 01, 02 (+ CNV-09, FEAS-08/09, LEAD-06, CHN-11, PLT-05 above). GDPR-03/04/05, LEAD-07, CHN-12 are required **before the first real tenant**, not for the demo — see `CLAUDE.md` legal tiers. |
| **JOBS+FB** | **Thin slice, ~15–20 days.** Accepted quotation → job → owner marks complete → delayed rating fires → 1–5 captured → low score opens ticket. No inventory reservation, crew allocation, SLA tracking or timeline UI. **Required for the FYP: the closed loop is the novelty claim.** See spec §11.2. |
| SITE | 01 |

**Document as designed, not implemented:** everything else, plus the full v2
lifecycle depth (inventory reservation, SLA tracking, tickets beyond the basic
open, retention/engagement).

> **Note on the jobs/feedback apparent contradiction:** `V1_SCOPE.md` puts them
> in v2 and is authoritative for *what ships to paying tenants*. Spec §11.2 puts
> a thin slice in the FYP and is authoritative for *what gets built for the
> defense*. Both are correct — see §11.2 for why.

Examiners reward a complete working loop over an ambitious half-built system.
Deliberate scope discipline, documented with reasoning, reads as engineering
maturity — see spec §14.

---

## Module dependency order (build sequence)

```
PLT-01 ──┬─> OPS-02 ──> OPS-03
         ├─> BIZ-01..08 ──> BIZ-08 ──┬─> CNV-04/05
         ├─> CHN-01 ──> CHN-02/03/04 │  └─> FEAS-01..07
         │       └────> CHN-05/06     │
         ├─> LEAD-01 ─────────────────┤
         └─> DOC-01/02 ───────────────┘
                                      │
                            QUOT-01 <─┴─ (needs BIZ-03 + CNV-05)
                                      │
                            QUOT-05 <──┴── (needs CHN-06)
                                      │
                            DASH-* <───┴── (needs stable APIs)
                                      │
                            ANL-* <────┘
```

Critical path: **PLT-01 → BIZ-08 → CNV-05 → FEAS/QUOT → QUOT-05**.

Build order per `PROJECT_SPEC.md` §11.3 (build phases), with one addition: **start Meta
Business verification and WhatsApp template submission in week one**, in
parallel with PLT-01. It is external, slow, and blocks QUOT-05 at the end.

---

## Sign-off

This list is locked for architecture and costing **on the condition that the
platform target is service SMEs (solar first)**, per the approved FYP proposal.

Confirm that before design begins. If it becomes Shopify retail instead, FEAS
and QUOT are void, CHN is replaced, and this needs rewriting from §0.
