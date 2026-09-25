# Project status

**As of 25 September 2026 — commit `cf08ca1` — 433 tests passing.**

Update this file every time a feature lands. If the date above is more than a
week old, treat everything below as suspect until checked.

---

## In one paragraph

The foundations, the business configuration, and the **entire messaging
transport layer** are built, tested and live in production in Frankfurt. A
business can connect its Facebook Page, Instagram account and WhatsApp number
from the dashboard, and a customer who messages them receives an automated
reply, end to end, through signed webhooks, tenant routing, deduplication and
an outbound dispatcher. Messenger is proven with real messages; Instagram is
connected; WhatsApp is built and waiting for its first live signup. What that reply *says* is still a placeholder: the
conversation engine — the part that qualifies leads — is the next major piece
and has not been started. Feasibility, quotations, lead scoring and analytics
come after it.

---

## What works in production today

Verified against the live system, not just in tests.

| | Status | Verified how |
|---|---|---|
| Owner sign-in, sessions, password reset | ✅ Live | End-to-end script against `app.tideover.site` |
| Business profile, services, rate cards, pricing | ✅ Live | Same |
| Service areas, inventory, crews | ✅ Live | Same |
| Solar question set and system sizing | ✅ Live | Same |
| Landing page, privacy notice, data-deletion page | ✅ Live | HTTP checks |
| Channels page (connect / disconnect) | ✅ Live | Used by hand |
| **Facebook Messenger: connect → receive → reply** | ✅ **Working** | A real message to *Tehman's Market* got the automated reply, 25 Sep |
| Webhook security | ✅ Live | Handshake echoes on all three channels; unsigned, mis-signed and tampered posts refused |
| Instagram: connect | ✅ Connected | `rivonna.ai` linked to *Tehman's Market*, 25 Sep |
| Instagram: receive → reply | 🟡 Awaiting a live DM | Same code path as Messenger; needs a message from an account with a role on the app |
| WhatsApp | 🟡 **Built, awaiting first live signup** | Button and backend deployed; needs the server pulled to `cf98ef1` and a spare number |
| **Beta: connect by choosing a Page** (`/channels/beta`) | 🟡 **Live, awaiting its first real try** | The ManyChat round trip — see [`09-channels-meta.md`](09-channels-meta.md) §6a |
| Lead qualification, feasibility, quotes | ❌ Not built | Phase 2 onwards |

---

## Where we are against the build phases

The phases from spec §11.3, and where each stands. We have deliberately taken
them out of order — see [`05-design-deviations.md`](05-design-deviations.md) §1.

| Phase | Focus | Status |
|---|---|---|
| 0 | Foundations: tenancy, auth, outbox, CI, migrations | ✅ Done |
| 1 | Business configuration, solar vertical | ✅ Done |
| 2 | Fake channel + **conversation core** | 🟡 Fake channel done; conversation core **not started** |
| 3 | Feasibility, then quotations | ❌ Not started |
| 4 | Lead scoring | ❌ Not started |
| 5 | Channel adapters | ✅ **Done early** — all three Meta channels, connect flows and dashboard, not just WhatsApp |
| 6 | Thin jobs + feedback (FYP only) | ❌ Not started |
| 7 | Dashboard | 🟡 Built alongside each feature rather than at the end |
| 8 | Polish, observability, demo | ❌ Not started |

---

## Production at a glance

| | |
|---|---|
| Dashboard | `https://app.tideover.site` — Vercel `fra1` |
| API | `https://api.tideover.site` — EC2 `eu-central-1`, Docker Compose, Caddy |
| Database | Neon Postgres, Frankfurt — migrations at **0012** |
| Code on the server | Must be `cf08ca1` or later for WhatsApp and the beta flow; migrations to **0013** |
| Meta app | **Rivon**, App ID `1027179017015673`, Business type, **Development mode** |
| Connected accounts | 2 — Messenger (*Tehman's Market*) and Instagram (`rivonna.ai`), under the test tenant |

---

## Open items that need someone

### Waiting on you (not code)

| Item | Why it matters |
|---|---|
| Pull `cf08ca1` on the server and rebuild | WhatsApp and the beta flow need it; runs migration 0013 |
| Try the beta, then decide: merge it, replace the old flow, or drop it | It was built to be judged side by side |
| A spare phone number for WhatsApp | Embedded Signup registers a real number |
| **Rotate the OpenAI API key** | It was pasted into a chat; treat it as exposed before Phase 2 uses it |
| **Replace the root AWS access keys** with the `rivon-deployer` IAM user | Root keys should not be on a laptop |
| Decide which EU country launches first | Spec §15.12: decides whether web widget + email outrank WhatsApp |
| Delete the production test tenant before showing anyone real | It holds test data and a real Page connection |

### Waiting on code

| Item | Size |
|---|---|
| **Conversation engine (CNV-01..05, 09)** — the next major phase | Large |
| Automated deauthorize and data-deletion callbacks from Meta | ~1 day |

### Not yet, but on the calendar

| Item | When |
|---|---|
| Legal entity, Meta business verification, App Review, Tech Provider | Before the first paying customer who is not a friend |
| Flipping the Meta app to **Live** | Only after App Review — never before; see [`07-memory.md`](07-memory.md) |

---

## Risks worth watching

| Risk | Why | Mitigation |
|---|---|---|
| Phase 2 is the critical path and has not started | Everything after it — feasibility, quotes, scoring — depends on extracted requirements | Start it next |
| Legal features all land with Phase 2+ | AI disclosure, consent, export/erasure are required before real data | Build CNV-09 and CHN-11 *with* the conversation engine, not after |
| Meta approval timelines | Business verification + App Review take weeks, and need a legal entity | Development mode + testers covers the FYP; start the entity early |
| Channel choice unsettled | If Nordics/DACH launch first, web widget and email become primary | The adapter pattern means adding them does not touch the pipeline |
