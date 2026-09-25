# Updates log

What happened, day by day. Newest first. Each entry names the commits, so
`git show <hash>` gives the full reasoning.

---

## 25 September 2026

**Beta connect flow built** — the ManyChat round trip, beside the current flow: sign in, see your Pages on a Rivon screen, create one on Facebook if there is none, come back, Connect. Uses a user token so it needs no business portfolio and sees Pages created later. Found on the way: the global unique index also covers revoked connections, so a Page one business disconnected cannot be taken up by another — logged in `04-remaining.md`. (`cf08ca1`)

**Messenger works end to end in production.** A real message sent to the
*Tehman's Market* Page received the automated reply through the full path:
signed webhook → tenant routing → stored → outbox → worker → outbound dispatcher
→ Meta → customer.

**Instagram investigated.** It appeared to connect but did not show up. Reading
the stored connection showed the Instagram permissions *had* been granted, but
Meta returned the Page with no Instagram account attached — it is not yet a
professional account linked to the Page. The return screen now explains this
when someone pressed *Connect Instagram*, and stays quiet when they pressed
*Connect Facebook*. (`946b757`)

**Handouts written** — this folder. (`893025d`)

**Instagram connected** — `rivonna.ai`, once linked to the Page as a professional account.

**WhatsApp button built** — Embedded Signup in Facebook's popup, pairing the code with the account ids from the browser event, PIN shown once. Found that SDK codes must be exchanged with no `redirect_uri` at all. (`cf98ef1`)

---

## 22 September 2026 — the channel layer

The biggest day so far: the whole messaging transport, built, tested and deployed.

- **Data deletion page** at its own URL, because Meta rejects a fragment link. (`2155071`)
- **Credential notes gitignored** after `local_secret_ids.txt` was found un-ignored in the repo root. (`9d916bc`)
- **CHN-07** — connected accounts with encrypted tokens and the routing function; found that forced RLS binds the table owner and solved it with a flag-scoped policy. Two real bugs found by testing: a savepoint opened in the wrong order, and an untested tenant filter. (`067d058`)
- **CHN-13** — self-serve connect for Pages and Instagram through Facebook Login for Business. (`f930aa4`)
- **CHN-02/03/04** — webhooks, the three real adapters, routing, deduplication. (`b5c28db`)
- **CHN-05** — the outbound dispatcher and the placeholder echo. Found that a revoked credential was failing silently instead of marking the connection for reconnection. (`21502c9`)
- **Channels page** in the dashboard, ManyChat-style. (`aac3a81`)
- **CHN-13** — WhatsApp Embedded Signup, backend. Mutation testing found a duplicated disconnect path, which was merged. (`ab865b4`)
- **Deployed.** The first attempt rebuilt old code: ten commits had never been pushed. Pushed, redeployed, all checks passed.
- **Two production bugs fixed** after the first real clicks: body-less POSTs rejected as "Expected JSON" (`5a89ec3`), and `httpx` missing from the production image, causing a 500 on connect. A dependency guard test now prevents that class of bug. (`7640d2f`)
- **Meta app set up** by hand: renamed to Rivon, icon, privacy and deletion URLs, roles, two login configurations, three webhooks.

---

## 21 September 2026

- **Privacy notice** published at `/privacy`: the controller/processor split, automated decisions, EU storage, retention, rights, cookies. (`de5d58b`)
- **CHN-01** — the internal message model, adapter contract and fake channel. Mutation testing introduced as standard practice. (`9fdbc0e`)
- **Channel plan changed twice** after research: from manual per-business Meta setup to self-serve connection (the ManyChat model), and from "verify the business first" to "build and demonstrate in development mode; verify when a paying customer needs it".

---

## 20 September 2026 — the dashboard and production

- **Dashboard** in Next.js 16, Tailwind v4 and shadcn/ui, with a BFF proxy so the browser never holds a token. (`9ef4cb8`)
- **Logo** replaced with the supplied design, traced to SVG. (`55b5c03`)
- **Production deployment**: compose file, Caddy TLS, managed-database roles, a console guide, then fixes found on the first real deploy — `buildx` missing on Amazon Linux, `.env` handling. (`137dc9a`, `032e9b1`, `4fc7493`, `a334c5f`)
- **API docs hidden** in production. (`71400df`)
- **Landing page** with GSAP animations; contact address. (`eb21a8b`, `cab332a`)
- **BIZ-05/06/07** — service areas, inventory, crews, and their screens. (`1479094`, `2b9ab8c`)
- **BIZ-08** — the solar question set and deterministic sizing, and its screen. (`1850809`, `a4b99b9`)
- **A secrets leak handled**: a production secrets file was committed to the public repo, removed, and every secret in it rotated.

---

## 19 September 2026 — foundations

- **Bootstrap**: repository, `CLAUDE.md` at the root, docs into `docs/`, PLT-01 multi-tenant foundation. (`913e310`)
- **OPS-09** migration conventions enforced by tests; **OPS-01** CI. (`8b1e88a`, `f74ac6f`)
- **PLT-02** owner authentication, and later a grace window for concurrent refresh. (`e7b4bb0`, `37eda8a`)
- **PLT-05** tenant region, fixed at provisioning. (`53b32cf`)
- **OPS-02/03** outbox, relay and Celery queues. (`174733a`, `9d29cec`)
- **BIZ-01/02/03** profile, services, pricing rules. (`57e0db0`, `d4da9fc`)
- **Decisions**: EU launch market, English only, EUR; n8n at the edge, team-managed; code public on personal GitHub, services on a separate Rivon account.
