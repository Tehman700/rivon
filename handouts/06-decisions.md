# Decisions

Every significant decision, with the date, the options, the choice and the
reason. Before re-opening one, read why it was made — and if the reason no
longer holds, change it and add a new entry that supersedes it. Never edit an
old entry's reasoning after the fact.

Format: **D-number · date · decision** — then context, options, choice, and
what would make us revisit it.

---

## Product and market

### D-01 · 19 Sep 2026 · The EU is the launch market; English only; prices in EUR
- **Context:** The original research leaned on Pakistan and the GCC. The team confirmed the EU.
- **Consequence:** GDPR and the EU AI Act are live requirements, not future work. Everything is hosted in the EU.
- **Revisit if:** never lightly — it drives hosting, legal and channel choices.

### D-02 · 19 Sep 2026 · Solar installers first
- **Context:** The platform targets service businesses that quote from a rate card.
- **Choice:** One vertical configuration in v1 (solar). Adding a vertical means adding configuration, not code paths.

### D-03 · 19 Sep 2026 · Both FYP and commercial v1
- **Choice:** Build for both. `V1_SCOPE.md` decides what ships to customers; spec §11.2 decides what is built for the defence.

### D-04 · 20 Sep 2026 · Invitation only
- **Choice:** No public sign-up. Businesses request access by email; the team provisions them with the CLI.
- **Why:** Each business is set up with us, so its prices and areas are right before a customer talks to it.
- **Revisit if:** onboarding becomes the bottleneck — then a guided wizard (BIZ-09) with channel connection built into sign-up, as ManyChat does.

---

## Infrastructure and accounts

### D-05 · 19 Sep 2026 · Code on a personal GitHub; services on a separate Rivon account
- **Choice:** The repository is public at `Tehman700/rivon`. Vercel, Neon, Meta and other services are on a separate Rivon-only Google account (`rivonna.ai@gmail.com`).
- **Consequence:** Anything committed is public. Secrets are never committed.

### D-06 · 20 Sep 2026 · Neon + EC2 + Vercel, all in Frankfurt
- **Options:** Managed platforms end to end; one VM; Kubernetes (ruled out by `CLAUDE.md`).
- **Choice:** Neon Postgres (Frankfurt), one EC2 instance in `eu-central-1` running Docker Compose with Caddy for TLS, and Vercel in `fra1` for the dashboard.
- **Why:** EU residency, low cost, and nothing to operate that a team of three cannot.

### D-07 · 20 Sep 2026 · Domain `tideover.site`
- **Choice:** `app.tideover.site` for the dashboard, `api.tideover.site` for the API.
- **Revisit when:** a Rivon domain is acquired (spec §16 open item).

### D-08 · 19 Sep 2026 · n8n at the edge, team-managed
- **Context:** The team wants to manage integrations and ops workflows without code changes.
- **Choice:** n8n receives signed event webhooks and calls the public API with a scoped token. No database access, never computes prices or scores, never messages a customer except through the Rivon API. Tenants never get access. Became hard rule 11.
- **Status:** Not built yet (OPS-10, OPS-11).

---

## Channels

### D-09 · 22 Sep 2026 · Pause the conversation engine; build the channel layer first
- **Choice:** Build all three Meta channels end to end with a placeholder reply, then put the agent inside.
- **Why:** Prove the part that depends on Meta first, and make the product visibly work.
- **Cost:** The critical path is delayed. See deviation §1.

### D-10 · 22 Sep 2026 · Self-serve connection, the ManyChat model
- **Options:** We configure each business in the Meta dashboard by hand; customers connect their own accounts.
- **Choice:** Self-serve. New feature ID CHN-13.
- **Why:** Manual setup does not scale past one customer, and means holding other people's credentials by hand.

### D-11 · 22 Sep 2026 · Facebook Login for Business, with configuration ids
- **Choice:** Two login configurations — one for Pages + Instagram, one for WhatsApp Embedded Signup.
- **Why:** Required for new business apps; tokens are scoped to the assets the customer picked.

### D-12 · 22 Sep 2026 · Instagram through the Page
- **Options:** Instagram's own login (no Page needed, 60-day tokens); through the linked Facebook Page.
- **Choice:** Through the Page.
- **Why:** One code path with Messenger, one consent screen, no refresh treadmill.
- **Trade-off:** The Instagram account must be professional and linked to a Page.

### D-13 · 22 Sep 2026 · Tech Provider, not Solution Partner, for WhatsApp
- **Why:** As a Tech Provider each customer attaches their own payment method. A Solution Partner fronts a line of credit for customers' message costs.

### D-14 · 22 Sep 2026 · Stay in Meta development mode until App Review
- **Context:** No legal entity yet, so no business verification, so no Advanced Access.
- **Choice:** Develop and demonstrate on Standard Access, with the team and pilot installers as app testers.
- **Rule:** Do **not** switch the app to Live before App Review — the messaging permissions disappear from the consent screen and the flow breaks for everyone.

### D-15 · 22 Sep 2026 · Encrypt customers' tokens with `cryptography` (Fernet)
- **Options:** Fernet in the application; Postgres `pgcrypto`; rely on disk encryption.
- **Choice:** Fernet, key in `RIVON_CHANNEL_TOKEN_KEY`, never in the database.
- **Why:** pgcrypto puts the key into SQL statements, where it can surface in logs. Disk encryption does nothing against a read-only connection or a leaked backup.
- **Consequence:** Losing the key means every customer reconnects. Rotation is deliberately not automated.

### D-16 · 22 Sep 2026 · Route through a `SECURITY DEFINER` function
- **Options:** A definer function; a fourth database role with its own connection string; an unprotected lookup table.
- **Choice:** The function, plus a flag-scoped owner policy (see deviation §3).
- **Why:** No new role or connection string to provision everywhere, and the only thing that crosses a tenant boundary is one UUID.

### D-17 · 22 Sep 2026 · External account ids are globally unique
- **Why:** Two tenants must never be able to claim the same Page or number.
- **Side effect:** Tests that share a committed database must use distinct account ids.

### D-18 · 22 Sep 2026 · The WhatsApp PIN is the customer's
- **Choice:** For a new number, generate a PIN and show it once; never store it. For a number that already has one, ask for it.

### D-19 · 22 Sep 2026 · Tell a dead credential apart from an undeliverable message
- **Choice:** A token Meta rejects (code 190) marks the connection *needs reauth* and the dashboard says so. A closed 24-hour window (131047) fails immediately. Anything else is retried up to five times, then given up on with the reason kept.

### D-20 · 22 Sep 2026 · The placeholder reply identifies itself
- **Text:** "Hello 👋 This is Rivon's automated assistant. We're still being set up."
- **Why:** These are real accounts even in testing. Nobody who finds one should think a person is typing. The full AI disclosure (CNV-09) arrives with the conversation engine.

### D-21 · 25 Sep 2026 · Explain what was left out, based on the button pressed
- **Choice:** If a customer pressed *Connect Instagram* and no Instagram account came back, say so and say how to fix it. If they pressed *Connect Facebook*, stay quiet about Instagram.

### D-26 · 25 Sep 2026 · The server tells the browser which WhatsApp configuration to open
- **Options:** Build the App ID and configuration id into the frontend; ask the API.
- **Choice:** `POST /channels/whatsapp/start`, owner only. One place says which app and configuration a deployment uses, and changing it needs no frontend redeploy.

### D-27 · 25 Sep 2026 · Build the ManyChat-style connect as a separate beta, not a change
- **Choice:** New endpoints and pages beside the current flow; nothing in the current flow changes.
- **Why:** The current flow works in production. The new one can be judged with real accounts first, then merged in, swapped in, or dropped.
- **Revisit:** After the live try — this entry will be superseded by the outcome.

### D-28 · 25 Sep 2026 · The beta logs in with a user token
- **Options:** Business integration token (current); user token.
- **Choice:** User token, traded for a long-lived one, sealed, held 30 minutes at most, destroyed when the session closes.
- **Why:** It can list every Page the person manages, including ones created after sign-in, and needs no business portfolio. Page tokens read with a long-lived user token do not expire, so what is stored afterwards is no weaker than today.

---

## Engineering practice

### D-22 · 19 Sep 2026 · Tests run against a real Postgres, as the application role
- **Why:** Row-level security only means anything if the tests are subject to it.

### D-23 · 21 Sep 2026 · Mutation testing on every feature
- **Choice:** After tests pass, break the code on purpose, one change at a time, and confirm a test fails. Survivors are either fixed with a new test or explained.
- **Why:** It has found real gaps every time — including an untested tenant filter whose absence would let one business silently overwrite another's credential.

### D-24 · 22 Sep 2026 · Push before any server deploy
- **Why:** The server deploys from GitHub. Ten commits once sat unpushed while a deploy rebuilt the old code.

### D-25 · 20 Sep 2026 · Primary colour is provisional
- **Choice:** Keep the design files' primary colour for now; decide the final brand colour later.

---

## Superseded

None yet.
