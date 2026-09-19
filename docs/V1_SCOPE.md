# Rivon — V1 Scope Definition

> Companion to `PROJECT_SPEC.md`. Read that first for architecture, stack, and
> naming conventions.
> **Status:** draft for discussion. Living document.

---

## 0. The problem with the proposed v1

Stated v1 was: lead system · landing page · account connections (Instagram,
others) · OAuth · compliance throughout.

**That ships a product with no moat.** Lead capture plus conversational
qualification is exactly what the GCC and Pakistan chatbot agencies already
sell — the competitor set the market research identified as beatable *because
they stop at qualification*. A v1 that also stops at qualification is not a
cheaper better product; it is the same product with a different logo.

It also has no pricing story. No contractor pays a monthly subscription (EUR
pricing TBD) for a bot that collects names and phone numbers. **The quotation is the thing worth paying for.**

**V1 must therefore include feasibility + quotation + approval.** That is the
minimum coherent product. Everything else on the stated list is real and stays,
but it isn't sufficient on its own.

### The v1 thesis
> A service SME connects their WhatsApp to Rivon, spends 30 minutes entering their
> services, pricing rules, service area, inventory and crew capacity. From then
> on, inbound leads are qualified by conversation, checked against real business
> capacity, and turned into a priced draft quotation that the owner approves from
> his phone in under a minute.

If that sentence is true and demonstrable, v1 is done. If any clause is missing,
it isn't.

### What v1 deliberately is NOT
The post-sale lifecycle half — jobs, rating loop, tickets, retention, referrals
— is **v2**. It is the strategic reason the two systems merged, and it is still
the plan. But shipping the full lifecycle in v1 doubles the scope and delays the
only part that generates revenue. Build the funnel, then close the loop.

---

## 1. In scope for v1

### 1.1 Tenant & platform foundation
- [ ] Tenant provisioning — **decide: self-serve signup, or manual/invite-only?**
      Invite-only is strongly recommended for v1. It removes signup abuse,
      payment automation, and onboarding-at-scale from the critical path.
- [ ] Owner account: email + password, JWT with tenant claim, refresh tokens
- [ ] RBAC: owner / manager / agent (agent role can be stubbed if unused)
- [ ] Tenant-level `region` attribute set at provisioning (EU vs non-EU) — §15.6
      of the spec. Cheap now, a data migration later.
- [ ] Plan tiers as data + feature flags per tenant
- [ ] **Usage metering (`usage_events`)** — every LLM call, every message, per
      tenant. Non-negotiable in v1: you cannot price what you cannot measure.
- [ ] Quota enforcement with a soft warning before a hard stop
- [ ] Audit log for owner actions (approvals, edits, config changes)

### 1.2 Business profile & onboarding
- [ ] Services offered
- [ ] Pricing rules: rate cards, per-unit costs, labour, transport, margin targets
- [ ] Discount rules
- [ ] Service areas (start with named regions/cities, not polygons)
- [ ] Inventory items with quantities
- [ ] Workforce / crews with availability
- [ ] Min / max project size
- [ ] Business hours
- [ ] **Guided onboarding wizard, not a wall of forms.** Setup abandonment is the
      single biggest killer of SME SaaS adoption. Show progress, allow partial
      save, allow "skip for now" with a clear indicator of what's incomplete.
- [ ] **Sandbox / test mode** — the owner chats with their own bot before going
      live. Builds trust, catches bad pricing rules, and costs almost nothing to
      build.

### 1.3 Channel connection
- [ ] **WhatsApp Cloud API — primary and only required channel for v1**
- [ ] `channels` table: `provider_phone_number_id → tenant_id` routing
- [ ] Channel tokens encrypted at rest, refresh handled in the adapter
- [ ] Per-channel health check that alerts on auth failure. A silently dead token
      means a tenant stops receiving leads and nobody notices.
- [ ] Web widget (embeddable) — cheap, no platform approval, useful for tenants
      who have a site
- [ ] **Telegram (owner-side only)** — bot token, no OAuth, trivial to add.
      Worth it as the approval-notification fallback if WhatsApp template
      approval is slow.

**On Instagram:** see §4. Recommend deferring.

### 1.4 Business knowledge documents
Framed as an **onboarding accelerator first**, question-answering second.

- [ ] Document upload in the dashboard (PDF, DOCX, TXT) — brochures, FAQs, spec
      sheets, warranty and policy terms
- [ ] Text extraction + per-tenant corpus store
- [ ] **Draft profile extraction at onboarding** — parse uploads to pre-fill
      services, products, and policy answers; owner confirms before it is saved.
      Turns 30 minutes of typing into 5 minutes of correcting, which directly
      attacks the biggest adoption risk in §1.2.
- [ ] Full-context injection with prompt caching (see strategy note below)
- [ ] Per-tenant document token budget with a warning before the limit
- [ ] Document age surfaced in the dashboard + review prompt after a configurable
      period — a bot quoting last year's warranty terms is a real liability
- [ ] Contradiction flag at upload ("your brochure says 5-year warranty, your FAQ
      says 3")
- [ ] Document-level delete (removes text and any embeddings together)

**Strategy: do NOT build vector RAG in v1.** A typical SME tenant will upload
3–8 documents, roughly 15–40k tokens. At that size, injecting the whole corpus
with prompt caching beats retrieval on accuracy (retrieval can miss the relevant
chunk; full context cannot) and costs little because the corpus is static per
tenant. Build retrieval as a **fallback strategy behind the same interface**,
triggered only when a tenant exceeds the token budget. Use **`pgvector` in the
existing Postgres** when that day comes — do not add a separate vector database.

#### HARD BOUNDARY — documents inform answers, never decisions
Retrieved or injected document text is non-deterministic, unversioned, and
unauditable. Prices and feasibility cannot depend on it (spec §2.2).

- Pricing and feasibility read **only** from Postgres: `pricing_rules`,
  `inventory_items`, `workforce`, `service_areas`
- Document context is available **only** to conversational handlers (answering
  questions, assisting requirement extraction)
- **Enforce structurally**: the document-context service is not injected into
  `quotations` or `feasibility` at all. Do not rely on a prompt instruction.
- **Price lists are the most dangerous document type.** Use them only to
  pre-fill the rate card at onboarding (owner confirms → lands in Postgres),
  then exclude them from the answering corpus.
- Ground policy answers in the document text; default to "let me get someone
  from the team" rather than a confident guess. Ties into failure surfacing
  (§1.5).

#### Compliance notes for documents
- Uploaded documents **will** contain personal data — old quotations, crew
  lists, contracts. **Embeddings of personal data are personal data.**
- Warn at the point of upload (in the UI, not buried in the ToS) not to include
  customer or employee personal data
- Scan on upload for phone/email patterns and warn before accepting
- **Deletion granularity is document-level**, not person-level. You cannot
  surgically remove one individual from mid-PDF. State this limitation in the
  DPA rather than implying otherwise.
- Documents inherit the tenant's `region` (§15.6) — an EU tenant's documents and
  embeddings stay in the EU, including whatever the embedding API sees
- Add documents to the Art 30 records of processing and the DPIA

**Deferred to v2:** customer-side uploads (electricity bill, roof photo, floor
plan). For solar, an electricity bill is the single most valuable requirement
input available — but customer uploads are untrusted input and prompt injection
becomes a live concern, so it needs its own threat model.

### 1.5 Lead capture & conversation
- [ ] Unified inbound message normalization (all channels → one model)
- [ ] `contacts` table with `lifecycle_stage` — the unified lead/customer record
- [ ] Conversation + message persistence, append-only messages
- [ ] Turn router: intent classification → handler dispatch
- [ ] Qualification dialogue — asks only for fields still missing
- [ ] Requirement extraction into a per-vertical JSON schema (solar first)
- [ ] Sentiment classification for routing/escalation only (see spec §15.2)
- [ ] **Bot handoff to human.** The owner or agent can take over a live
      conversation, and hand it back. Essential for trust; often forgotten.
- [ ] **Failure surfacing.** When the bot can't handle something, it says so and
      flags the conversation for the owner rather than guessing.
- [ ] Idempotency: unique `(tenant_id, provider_message_id)`

### 1.6 Decision layer — THE DIFFERENTIATOR
- [ ] Lead scoring (scikit-learn), 0–100, with model version + input features
      recorded per score
- [ ] Feasibility rules engine: service match · area match · inventory
      sufficiency · crew availability · project size bounds
- [ ] **Feasibility returns structured reasons, not just pass/fail**
- [ ] Deterministic pricing engine against the rate card, with margin logic
- [ ] LLM writes the covering narrative only — never the numbers

### 1.7 Quotation & approval
- [ ] Draft quotation with line items
- [ ] Optional Good–Better–Best tiers (can slip to v1.1 if time-pressed)
- [ ] **Phone-first approval**: WhatsApp/Telegram card with customer name,
      amount, lead score, feasibility verdict + Approve / Reject quick replies +
      URL button to a single-screen mobile edit view
- [ ] Dashboard approval as the secondary path
- [ ] Edit before approve, with edits synced back
- [ ] **Quotation PDF generation** — B2B buyers expect a document, not a chat
      message
- [ ] Delivery to the customer on their original channel
- [ ] **Email delivery of the PDF** as an option — expected in B2B and needed
      when the quotation is too long for a chat message
- [ ] Quotation status tracking: draft / pending / approved / rejected / sent /
      accepted / declined
- [ ] Nothing reaches a customer unapproved in v1

### 1.8 Owner dashboard
Distinct from the marketing landing page — see §3.

- [ ] Lead list with score, status, and source
- [ ] **Conversation viewer** — the owner reads exactly what the bot said. This
      is the single most important trust feature in the product. Without it, no
      contractor will let a bot talk to their customers.
- [ ] Quotation queue (pending approval) + history
- [ ] Business profile editing (same forms as onboarding)
- [ ] Basic analytics off precomputed rollups: lead volume, qualification rate,
      quotation conversion rate, average quote value, response time
- [ ] Usage / quota display against plan
- [ ] **New-lead notification to the owner** — not just quotation approvals.
      A high-scoring lead arriving should ping him.

### 1.9 Operations
- [ ] Outbound dispatcher: single queue, dedupe key, backoff, per-tenant rate
      limits, DLQ
- [ ] Celery queue split: `inbound` / `ai` / `outbound` / `scheduled`
- [ ] Transactional outbox for domain events
- [ ] Structured JSON logging with request ID threaded through every layer
- [ ] Sentry
- [ ] Tiered model routing + prompt caching (cost control, spec §9.1)
- [ ] Nightly rollup job
- [ ] Backups + a tested restore
- [ ] Signed outbound event webhooks for n8n (retries, DLQ, replay) + scoped
      service tokens for n8n calling the API
- [ ] Self-hosted n8n in the EU, team access only, workflows versioned in the
      repo (spec §7.4)

### 1.10 Compliance in v1
The six engineering items from spec §15.10, plus the documents no real tenant
can be onboarded without.

**Engineering:**
- [ ] AI disclosure at the start of every conversation, per-tenant configurable,
      **not disableable**, logged as an event. Repeat on resume after a gap and
      on bot↔human handoff. (AI Act Art 50 — already applicable since 2 Aug 2026)
- [ ] **No terminal auto-rejection.** The `not feasible → lead closed` path must
      route to the owner, or produce a non-final outcome with a route to a human.
      (GDPR Art 22 / SCHUFA — this is a required change to the current activity
      diagram)
- [ ] Documented path to request human review of any automated outcome
- [ ] Consent records with timestamp, source, and `consent_text_version`
- [ ] Opt-out keyword/link handling — build it in v1 even though the marketing
      module is v2, because the plumbing belongs in `channels`
- [ ] Data subject rights as working endpoints: export (machine-readable),
      erase, rectify, object-to-profiling flag
- [ ] Decide and document erasure strategy vs. append-only messages —
      crypto-shredding or field redaction, not row deletion

**Documents (needed before the first real tenant, not for the FYP demo):**
- [ ] Privacy notice
- [ ] Terms of service
- [ ] Data Processing Agreement template (GDPR Art 28)
- [ ] Sub-processor list (OpenAI/Google, AWS, Meta) published
- [ ] AI Act risk-classification assessment, written down
- [ ] Cookie/consent banner on the landing page and web widget

---

## 2. Out of scope for v1

Deferred deliberately, with the reason. Each of these is a "no" that protects
the v1 timeline, not a "never."

| Item | Why deferred |
|---|---|
| **Jobs, rating loop, tickets** | The v2 core. Needs completed jobs to exist first. |
| **Retention / win-back / referral campaigns** | v2. Also the highest ePrivacy risk surface. |
| **Ad generation** | Lowest-value module and the least defensible. Owners can write their own ad. *Note: it is M1 in the approved FYP proposal, so implement a thin version for the report even if it's not a commercial priority.* |
| **Instagram / Messenger** | §4 |
| **Multiple verticals** | Solar only. HVAC/plumbing/construction are config, added once the config model is proven. |
| **Scheduling / dispatch / calendars** | Explicitly out per positioning. Don't compete with Jobber on its core. |
| **Payments / invoicing** | Out per positioning. |
| **Native mobile app** | Spec §8. WhatsApp + desktop covers both jobs. |
| **Jobber / Housecall Pro API sync** | The mid-term expansion play, after product-market fit. |
| **Mapping / property measurement** | QuoteIQ's strength, not ours. |
| **Any language other than English** | **English only** (decided Sep 2026). A second language is a post-v1 decision against real EU tenants. |
| **Tenant-facing workflow builder** | n8n is team-managed only (spec §7.4). Giving tenants workflow access needs a commercial n8n licence and its own support model. |
| **Self-serve billing** | §5 |
| **Embedded Signup / Tech Provider status** | Manual number registration for v1. Design documented, not built. |

---

## 3. The landing page — two things, not one

"Landing page" and "dashboard" are separate products and it's worth naming that
explicitly.

**Marketing site (public):**
- [ ] What it does, who it's for, the feasibility-before-quotation pitch
- [ ] Demo video or interactive demo — **more persuasive than any copy** for a
      product this hard to describe
- [ ] Pricing page (even if "contact us" for v1)
- [ ] Waitlist / demo-request form
- [ ] Privacy notice, ToS, DPA, sub-processor list (linked, per §1.10)
- [ ] Cookie consent banner
- [ ] Next.js static, on Vercel. A day or two of work.

**Product dashboard (authenticated):** §1.8. Weeks of work.

Don't let the marketing site consume time that belongs to the dashboard. It is
the cheapest artifact in v1 and the easiest to over-polish.

---

## 4. On Instagram and the other channels

Recommendation: **WhatsApp only for v1.** Reasons:

1. In Pakistan and the GCC, WhatsApp *is* the channel for local commerce. It is
   where the leads actually are.
2. Instagram DM API requires a Professional account linked to a Facebook Page,
   with its own permissions and review process — real onboarding friction for
   each tenant, for a fraction of the lead volume.
3. Every additional channel is the same adapter interface written again:
   near-zero academic value, real calendar cost. Breadth before depth is the
   classic FYP failure.
4. The adapter pattern (spec §2.1) means adding Instagram later is a contained
   piece of work, not a refactor. **That is the point of building it this way.**

**Exception worth checking:** if a specific target tenant runs Instagram-first
(common for some consumer-facing trades), that changes the calculus. Decide
against a real prospect, not in the abstract.

Keep the web widget — it's cheap and needs no platform approval. Keep Telegram
owner-side — bot token, no OAuth, hours of work.

---

## 5. OAuth — what actually applies

| Platform | Mechanism | OAuth? |
|---|---|---|
| WhatsApp Cloud API | Embedded Signup (Facebook Login for Business) → exchange for WABA + phone number IDs | Yes, OAuth-like |
| Instagram DM / Messenger | Facebook Login for Business, scoped page permissions | Yes |
| **Telegram** | Tenant creates a bot via BotFather, pastes the token | **No — just a token** |
| Web widget | Tenant-scoped embed key issued by us | No |

**Two separate auth systems — do not conflate them:**
- **Tenant → platform:** our own JWT with tenant claim. Dashboard login.
- **Platform → tenant's channel accounts:** OAuth tokens (Meta) or bot tokens
  (Telegram), stored encrypted per tenant in `channels`, refreshed on schedule.
  This is credential storage, not user login.

**For v1:** manual number registration, credentials in env vars or encrypted
config. Embedded Signup is the *production onboarding* path — investigate the
Tech Provider requirements now, build it when tenant count justifies it. Without
it, every onboarding is you walking someone through Meta Business Manager, which
is the custom-build economics the positioning rejects.

---

## 6. Billing — an unsolved practical problem

Flagging early because it has a long lead time and no clean answer.

- **All pricing and invoicing in EUR.** Tenants are EU businesses; expect
  SEPA transfer and card as the norm, and EU VAT rules (reverse charge for B2B
  cross-border) to apply to invoices.
- Processor availability depends on **the billing entity's country**, not the
  tenants'. Stripe has historically not onboarded Pakistani businesses; an
  EU-established entity (or equivalent) may be needed. **Verify before assuming
  self-serve billing is possible.**
- **Realistic v1:** EUR invoice + SEPA bank transfer, manual plan activation by us.
  Ugly, entirely viable at single-digit tenant counts, and removes payment
  integration from the critical path.
- This is another argument for **invite-only provisioning** in v1.

---

## 7. Definition of done

V1 ships when a person who is not on the team can:

1. Be provisioned as a tenant
2. Complete onboarding: services, pricing, area, inventory, crew
3. Connect a WhatsApp number
4. Test the bot in sandbox mode
5. Go live
6. Receive a real inbound lead, qualified by conversation, with AI disclosure
   given at the start
7. See the extracted requirements, lead score, and feasibility verdict with
   reasons
8. Get an approval card on their phone and approve in under a minute
9. Have the customer receive the quotation on WhatsApp with a PDF
10. Read the whole conversation back in the dashboard
11. See it counted in their analytics and against their quota
12. Export or erase that contact's data on request

If step 7 or 8 is missing, it's a chatbot. If step 10 is missing, nobody will
trust it. If step 12 is missing, no EU tenant can be onboarded.

---

## 8. Open questions

- [ ] **Is v1 the FYP deliverable, a commercial launch, or both?** They differ:
      the FYP needs the full loop demonstrable; a commercial v1 needs onboarding,
      billing, and support. If both, the FYP demo is a subset of v1.
- [ ] Self-serve or invite-only provisioning? (recommend invite-only)
- [ ] First vertical confirmed as solar?
- [x] ~~Second language~~ — **English only**
- [x] ~~EU a launch market, or EU-readiness a design property?~~ — **EU is the
      launch market** (spec §15.11)
- [ ] **Which EU market first?** Decides the primary channel (spec §15.12)
- [ ] EU pricing tiers in EUR
- [ ] Do we have a real pilot tenant lined up? Everything above is better
      decided against one real business than in the abstract.
- [ ] Verify Stripe/processor availability for the billing entity's country
- [ ] Is Good–Better–Best in v1 or v1.1?
