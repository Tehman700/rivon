# How we differ from the design

`docs/PROJECT_SPEC.md`, `docs/V1_SCOPE.md` and `docs/FEATURE_LIST_V1.md` were
written before a line of code existed. This file lists every place where what we
built departs from them, and why. If you are about to rely on something in
`/docs`, check here first.

---

## Our position on design changes

**We are not bound to one design.** The spec was the best plan available before
building, and building taught us things it could not have known — which Meta
login flow new apps are allowed to use, what forced row-level security does to
a table owner, what a customer needs to be told when a connection half-works.
Where evidence says the design is wrong, we change the design, and say so here.

But flexibility has edges, and they are firm:

| Can change freely | Can change only as a named, tested exception | Can never be weakened |
|---|---|---|
| Build order, module boundaries, table layout, UI, library choices, which features ship first | The eleven hard rules in `CLAUDE.md` | The legally required features — AI disclosure, no terminal auto-rejection, explainable scoring, export and erasure, consent records, EU data residency |
| *Record it in `06-decisions.md`* | *Record it here, register it in the schema review gates, and test the reason it is safe* | *These change how, never whether* |

A good design change has three things: a reason grounded in something we
learned, a record of it, and a test that would fail if the reason stopped being
true. Everything below has all three.

---

## 1. We built the channels before the conversation engine

| | |
|---|---|
| **Design said** | Spec §11.3: Phase 2 is the fake channel + conversation core; the WhatsApp adapter is Phase 5, "because the pipeline already works, so this phase is plumbing". |
| **We did** | Built the fake channel, then the **entire** transport layer — all three Meta channels, OAuth onboarding, webhooks, routing, deduplication, outbound dispatch — and paused the conversation engine. |
| **Why** | A deliberate product decision: prove that customers can connect their accounts and that messages flow both ways ("hi" → "hello") before putting intelligence inside it. It de-risked the part that depends on an outside company (Meta), and it gave something visible to show. |
| **Why it is safe** | Hard rule 4. Adapters only translate; the conversation engine will read the same internal message model whether it arrives from Meta or the fake channel. Nothing built has to move when Phase 2 lands — the echo reply is the one handler it replaces. |
| **Cost** | The critical path (conversation → feasibility → quotation) has not started. It is next. |

## 2. We started channel work before the first EU market was named

| | |
|---|---|
| **Design said** | Spec §15.12, in bold: *"Do not start CHN work until the first EU market is named"* — because Southern Europe keeps WhatsApp first, while the Nordics and DACH would make a web widget and email primary. |
| **We did** | Built all three Meta channels without naming the market. |
| **Why** | Building all three Meta channels made the WhatsApp-versus-others question much less decisive for the channel layer: whichever market comes first, Messenger and Instagram are there too. It was an explicit override, noted in the plan at the time. |
| **Still open** | The market question is **not** answered, and it still matters: if a Nordic or DACH market comes first, the **web widget (CHN-09)** and **email** become primary channels. The adapter pattern means adding them does not touch the pipeline. |

## 3. One exception to hard rule 2 — the routing lookup

| | |
|---|---|
| **Rule** | Every index on a tenant table leads with `tenant_id`. |
| **Exception** | `channel_connections` has a **globally unique** index on `(provider, external_id)`. |
| **Why** | When a webhook arrives, Meta tells us which Page or phone number it is for — not which tenant. Finding the tenant *is* the query, so it cannot lead with the tenant. Global uniqueness is also a **safeguard**: without it, two businesses could both connect the same Page and one would start receiving the other's customers. |
| **How it is contained** | The lookup goes through one SQL function, `channel_route()`, the **only cross-tenant read in the system**. It returns a single UUID — never a row, never a token — and only for an active connection. Every other query on the table still leads with `tenant_id`, and RLS stays on. |
| **Subtlety we hit** | `FORCE ROW LEVEL SECURITY` binds the table's *owner* too, so a `SECURITY DEFINER` function alone returned nothing. Instead of letting the owner read every row, the function raises a transaction-local flag around its one query, and a policy scoped to `rivon_owner` opens only while that flag is set. The application role is not covered by that policy, so setting the flag itself gains it nothing — there is a test that tries exactly that. |
| **Registered** | In `tests/test_schema_conventions.py` (`INDEX_EXCEPTIONS`, `EXTRA_POLICIES`), each with its reason. Changing either without a reason fails the build. |

## 4. Three channels, not WhatsApp first

| | |
|---|---|
| **Design said** | CHN-02 is "WhatsApp Cloud API inbound"; CHN-03 routes `provider_phone_number_id → tenant_id`. Messenger and Instagram were mentioned in the pipeline but not specified. |
| **We did** | WhatsApp, Messenger and Instagram as equals. Routing generalised to an `external_id` per provider: Page id, Instagram account id, or WhatsApp **phone number** id. |
| **Why** | The customer asked for all three, the way ManyChat offers them. |
| **Worth knowing** | WhatsApp routes by phone number id, **not** the WhatsApp Business Account id. One account can hold several numbers, and they need not belong to the same business. A test fails if that is ever reversed. |

## 5. A new feature: self-serve channel connection (CHN-13)

| | |
|---|---|
| **Design said** | Onboarding was assumed manual (spec §10). Embedded Signup was an open item: "investigate". |
| **We did** | Customers connect their own accounts from the dashboard, ManyChat-style: Facebook Login for Business for Pages and Instagram, WhatsApp Embedded Signup for WhatsApp. |
| **Why** | Manual per-tenant setup does not scale past the first customer, and means holding other people's credentials by hand. |
| **ID** | `CHN-13` — added rather than stretching CHN-07 to cover it. |

## 6. Facebook Login for Business, not classic Facebook Login

| | |
|---|---|
| **What people expect** | ManyChat's dialog: "Continue as …?", one screen, a list of scopes. |
| **What ours does** | An asset picker: choose the business portfolio, the Page, the Instagram account. |
| **Why** | ManyChat's app uses the old consumer login and predates the change. **New business apps are required to use Facebook Login for Business** with a configuration id. It is also better: the token we receive reaches only the assets the customer ticked. |

## 7. Instagram through the Page, and no token refresh job

| | |
|---|---|
| **Design said** | CHN-07: "channel credential storage (encrypted) + **token refresh**". |
| **We did** | Instagram connects through its linked Facebook Page, on the Page's own long-lived business token. There is no refresh job. Instead, a connection whose token stops working moves to **needs reauth**, the dashboard says so, and the customer reconnects in one click. |
| **Why** | Instagram's own login returns tokens that expire in 60 days and die permanently if unused for 60 days; the Page route avoids that treadmill entirely, and shares one code path with Messenger. |
| **Trade-off** | The Instagram account must be a professional account linked to a Page. That is exactly what stopped the first Instagram connect — see [`07-memory.md`](07-memory.md). |

## 8. Messages are stored in the channels module, for now

| | |
|---|---|
| **Design said** | CNV-01: the `conversations` module persists conversations and append-only messages. |
| **We did** | `inbound_messages` and `outbound_messages` live in the `channels` module, because the transport layer was built first and had to store what it received (hard rule 3: persist before anything else) and what it sent (hard rule 7: claim before sending). |
| **Open question for Phase 2** | Either `conversations` reads these tables through the channels service interface, or conversation-level messages become their own table that references them. It must **not** read the channels tables directly (hard rule 8). Decide at the start of CNV-01. |

## 9. The dashboard was built alongside each feature, not last

| | |
|---|---|
| **Design said** | Spec §11.3, Phase 7: "Dashboard last — API contracts are stable, so each screen is built once." |
| **We did** | A screen for each business feature as it landed, and the Channels page with the channel layer. |
| **Why** | Seeing the work was a stated priority, and configuration screens change little. The risk the spec was avoiding — rebuilding screens as APIs change — has been small so far. |

## 10. Deployed early

| | |
|---|---|
| **Design said** | Deployment effectively at the end (Phase 8). |
| **We did** | Production in the EU from the first week: Neon, EC2 and Vercel, all Frankfurt. |
| **Why** | Real deployment finds real problems. It already found four that no test could: missing `buildx` on the server, dev-only dependencies absent from the image, code that was never pushed, and a proxy rule that turned away body-less requests. |

## 11. Meta business verification deferred

| | |
|---|---|
| **Design said** | Feature list: "start Meta Business verification … in week one". |
| **We did** | Deferred it. There is no legal entity yet, and verification needs documents in the business's name. |
| **Why it is fine for now** | Business apps get Standard Access automatically. In development mode every flow works for people holding a role on the app — including real Embedded Signup, up to 10 new WhatsApp businesses a week. That covers the FYP and a pilot installer added as a tester. |
| **When it stops being fine** | The first customer who is not on our tester list. See [`04-remaining.md`](04-remaining.md) §10. |

## 12. Invite-only, no registration

| | |
|---|---|
| **Design said** | PLT-02: "Owner auth: **registration**, login, JWT + refresh, password reset". |
| **We did** | No public registration. Access is requested by email and provisioned with the CLI. |
| **Why** | Consistent with PLT-04 (invite-only provisioning) and with how the first installers will be onboarded: by us, on a call, so prices and service areas are right before any customer talks to the bot. |

## 13. Dependencies added

The stack list in `CLAUDE.md` did not include these. None is on the forbidden list.

| Package | Why | Asked? |
|---|---|---|
| `cryptography` | Encrypting customers' access tokens (Fernet). Python's standard library has no AES. | Yes — chosen over pgcrypto (key would appear in SQL logs) and over no encryption |
| `httpx` | Calling Meta's Graph API. Was a test-only dependency; is now a runtime one. | Promoted after it broke production — see [`07-memory.md`](07-memory.md) |
| `kombu` | Already installed through Celery; now declared because the worker imports it directly | Declared, not new |
| `lucide-react` icons only | Brand icons (Facebook, Instagram, WhatsApp) were removed upstream, so we draw them inline | — |

## 14a. A second connect flow, in beta, beside the first

| | |
|---|---|
| **Current flow** | Facebook Login for Business with a **business** token. Meta's dialog picks the assets; everything ticked is connected. |
| **The gap** | It needs a Meta business portfolio, and a Page created after the dialog is invisible. A brand-new installer usually has neither a portfolio nor a Page — the two walls where people give up. ManyChat avoids both. |
| **Beta flow** | A **user** token and Rivon's own Page picker: every Page the person manages, an empty state that sends them to Facebook to create one, a list that refreshes when they come back, and Connect per Page. |
| **Why run both** | So the new flow can be tried with real accounts in production without risking the one that already works. Separate endpoints (`/channels/v2`), separate pages (`/channels/beta`), a separate login configuration and redirect URI. Only the storage they end in is shared. |
| **What cannot be done by anyone** | Creating the Page. Meta has no API for it — ManyChat's "Create new Page" is a link to Facebook. |
| **Decision pending** | After a live try: merge, replace the old flow, or drop. Recorded in `06-decisions.md` when made. |

## 14. Visual design

| | |
|---|---|
| **Design files** | A local `design-files` reference folder (not committed, by request). |
| **We did** | Followed its structure and kept its primary colour **provisionally** — the final brand colour is still to be decided. The logo is traced from the supplied PNG into an SVG that works on light and dark backgrounds. The Channels page follows the ManyChat layout the customer pointed at, in Rivon's own design language. |
