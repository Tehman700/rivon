# What is remaining

Everything still to build or do, in the order it should happen. Feature IDs are
from `docs/FEATURE_LIST_V1.md`; **FYP** marks what the defence needs (per the
"FYP subset" section of that file), **Before real tenant** marks what the law
needs before real customer data flows.

The critical path is **conversation → feasibility → quotation**. Almost
everything else hangs off it.

---

## 1. Finish the channel layer — small, do first

| Item | What is left | Size | Needs |
|---|---|---|---|
| Instagram | Link an Instagram professional account to *Tehman's Market* in Meta Business Suite, allow message access in the Instagram app, then press Connect | — | **You**, not code |
| WhatsApp button | Load Facebook's JS SDK on the Channels page, call `FB.login` with the WhatsApp configuration, listen for the `WA_EMBEDDED_SIGNUP` browser event, post the code + ids to `/channels/whatsapp/complete`, show the PIN once. The backend is done and tested. | ~1 day | — |
| Meta callbacks | Automated **deauthorize** and **data-deletion** callbacks (signed requests). Today we have the instructions page, which is enough for development mode. | ~1 day | Before going Live |
| CHN-06 | WhatsApp templates — needed to message a customer outside the 24-hour window, e.g. to send a quotation days later. Templates take Meta days to approve, so submit early. | M | QUOT-05 |
| CHN-08 | Per-channel health check and auth-failure alerting | M | Not FYP |
| CHN-09 | Web widget | L | **Promoted if a Nordic/DACH market is chosen first** |
| CHN-10 | Telegram (owner side) | M | Not FYP |
| CHN-11 | Versioned consent records | S | **FYP · legally required** |
| CHN-12 | Opt-out handling | S | Before real tenant |

---

## 2. Phase 2 — the conversation engine (the next big piece)

This is what replaces the echo. Nothing downstream can be built until
requirements are being extracted from real conversations.

| ID | What | FYP | Notes |
|---|---|---|---|
| CNV-01 | Conversation and message persistence, append-only, state in Postgres | ✅ | Decide first where messages live — see [`05-design-deviations.md`](05-design-deviations.md) §8 |
| CNV-02 | Turn router: intent → handler (qualification / service / general) | ✅ | |
| CNV-03 | Tiered model routing + prompt caching | ✅ | **Required** — it is the LLM cost control, and DOC-03 depends on it |
| CNV-04 | Qualification dialogue — asks only for what is missing | ✅ | Uses `SOLAR.missing_for_quote()`, already built |
| CNV-05 | Requirement extraction to the solar schema, Pydantic-enforced structured output | ✅ | |
| **CNV-09** | **AI disclosure at conversation start — not disableable, logged, repeated on resume and handoff** | ✅ | **Legally required (AI Act Art 50).** Ship it *with* CNV-01, not after |
| CNV-06 | Sentiment, for routing only | — | Not FYP |
| CNV-07 | Human handoff | — | Not FYP |
| CNV-08 | Failure surfacing | — | Not FYP |

**Before starting:** rotate the OpenAI key that was exposed in chat.

---

## 3. Phase 3 — feasibility, then quotations

Feasibility first: it is pure logic, needs no training data, and it is the
differentiator.

| ID | What | FYP |
|---|---|---|
| FEAS-01 | Rules framework, per-vertical rule sets | ✅ |
| FEAS-02..06 | Service, service-area, inventory, crew and project-size checks — all against configuration that already exists | ✅ |
| FEAS-07 | Reasons, not just pass/fail | ✅ |
| **FEAS-08** | **No terminal auto-rejection** — owner confirms, or the outcome stays provisional | ✅ **Legally required** |
| **FEAS-09** | **Human-review route** | ✅ **Legally required** |
| QUOT-01 | Deterministic pricing against the rate card (BIZ-03 already models it) | ✅ |
| QUOT-02 | Quotation + line items, status lifecycle | ✅ |
| QUOT-03 | LLM covering note — **wording only, never numbers** | ✅ |
| QUOT-05 | Phone-first approval card | ✅ |
| QUOT-09 | PDF | ✅ |
| QUOT-10 | Delivery on the original channel | ✅ |
| QUOT-12 | Status tracking | ✅ |
| QUOT-04, 06, 07, 08, 11 | Tiers, mobile edit, dashboard approval, edit-before-approve, email | Not FYP |

---

## 4. Phase 4 — leads and scoring

| ID | What | FYP |
|---|---|---|
| LEAD-01 | Unified contacts with a lifecycle stage | ✅ |
| LEAD-03 | Feature engineering | ✅ |
| LEAD-04 | Synthetic training data | ✅ |
| LEAD-05 | scikit-learn model | ✅ |
| **LEAD-06** | **Scoring service, storing model version and inputs per score** | ✅ **Legally required** |
| LEAD-02 | Contact de-duplication | Not FYP |
| LEAD-07 | Objection-to-profiling flag | Before real tenant |

Scoring must never use ability to pay or financial standing (hard rule 9).

---

## 5. Knowledge documents

| ID | What | FYP |
|---|---|---|
| DOC-01 | Upload to S3, per-tenant corpus | ✅ |
| DOC-02 | Text extraction | ✅ |
| DOC-03 | Full-context injection with prompt caching and a per-tenant token budget | ✅ |
| DOC-04..07 | Draft profile from documents, library view, PII scan, contradiction flag | Not FYP |

Documents must never reach pricing or feasibility — enforced structurally
(hard rule 5).

---

## 6. Phase 6 — the thin jobs + feedback slice (FYP only)

Accepted quotation → job → owner marks complete → delayed rating request →
1–5 captured → a low score opens a ticket. No inventory reservation, crew
allocation, SLA tracking or timeline UI. ~15–20 days. **Required for the FYP:
the closed loop is the novelty claim.**

---

## 7. Dashboard, analytics, and the rest of the product

| ID | What | FYP |
|---|---|---|
| DASH-02 | Lead list | ✅ |
| DASH-03 | **Conversation viewer** — the owner reads exactly what the bot said | ✅ |
| DASH-07 | Analytics (basic) | ✅ |
| ANL-01..03 | Event capture, nightly rollups, read API — never live tables | ✅ |
| BIZ-04 | Discount rules | Not FYP |
| BIZ-09 | Guided onboarding wizard | Not FYP — ManyChat puts channel connection *inside* sign-up; worth copying |
| BIZ-10 | Sandbox: owner chats with their own bot | Not FYP |
| PLT-07 | Usage metering per LLM call and per message | ✅ |
| PLT-06, 08, 09 | Plans, quotas, audit log | Not FYP |
| SITE-02 | Demo video | After the loop works |
| SITE-03 | Terms of service | Before real tenant |

---

## 8. Compliance

| ID | What | When |
|---|---|---|
| **GDPR-01** | Data export | **FYP** |
| **GDPR-02** | Erasure, including a documented strategy for append-only messages | **FYP** |
| GDPR-03 | Rectification | Before real tenant |
| GDPR-04 | Per-jurisdiction consent | Before real tenant |
| GDPR-05 | Records of processing | Before real tenant |

The Meta data-deletion callback is GDPR-02 arriving through a different door;
build both against the same service.

---

## 9. Operations

| ID | What | When |
|---|---|---|
| OPS-04 | Structured JSON logging with a request id through every layer | FYP |
| OPS-05 | Sentry | Before real tenant |
| OPS-06 | Redis caching and rate-limit buckets | When needed |
| **OPS-07** | **Backups with a tested restore** | Before real tenant — Neon has point-in-time recovery, but nobody has tried restoring |
| OPS-10 | Signed outbound event webhooks for n8n | FYP |
| OPS-11 | n8n, self-hosted in the EU, team-only | FYP |
| — | Login rate limiting | Before real tenant |
| — | Email provider for password resets | Before real tenant — resets currently log to the console |

---

## 10. Business and account tasks (not code)

| Task | When | Notes |
|---|---|---|
| Rotate the OpenAI API key | **Now** | Exposed in chat |
| Replace root AWS keys with the `rivon-deployer` IAM user | **Now** | |
| Name the first EU market | Before CHN-09 decisions | Spec §15.12 |
| Register a legal entity + business bank account | A month before the first paying customer | Meta verification needs documents in the business's name, not a personal one |
| Meta business verification | After the entity | 2–5 business days |
| Meta App Review for Advanced Access | After verification | Weeks. Six permissions; screen recordings required |
| Meta Tech Provider registration | After verification | Lifts WhatsApp onboarding from 10 to 200 per week |
| **Then** switch the Meta app to Live | Last | Never before App Review — the permissions disappear from the consent screen |
| Delete the production test tenant | Before showing anyone real | Test content becomes visible when the app goes Live |
| Terms of service | Before real tenant | |
| Lawyer review of the privacy notice | Before real data | It names no legal entity yet, because there isn't one |
