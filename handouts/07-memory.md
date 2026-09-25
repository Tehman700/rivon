# Memory — things that are easy to lose

The facts, identifiers, traps and lessons that are not obvious from the code.
Most of these cost someone an hour or a day to learn. Read this before touching
deploys, secrets, or Meta.

> **No secrets in this file.** It is in a public repository. It says *where*
> secrets live and *what they are called*, never what they are.

---

## 1. Accounts and where things live

| What | Where |
|---|---|
| Code | `github.com/Tehman700/rivon` — **public** |
| Vercel, Neon, Meta, other services | A separate Rivon-only Google account, `rivonna.ai@gmail.com` |
| Vercel team scope | `rivon2` — deploys need `--scope rivon2`, or the CLI says "Not authorized" |
| Vercel project | `rivon` |
| Dashboard | `https://app.tideover.site` |
| API | `https://api.tideover.site` |
| Server | EC2 in `eu-central-1`, repo at `/opt/rivon`, settings in `/opt/rivon/.env` |
| Database | Neon, Frankfurt |
| Public contact address | `rivonna.ai@gmail.com` |

### Where secrets live — never anywhere else

| Secret | Location |
|---|---|
| Local development settings | `.env` in the repo root — gitignored |
| Meta app credentials, verify token | `local_secret_ids.txt` in the repo root — gitignored, never committed |
| Production settings | `/opt/rivon/.env` on the server |
| Production token-encryption key | `/opt/rivon/.env`, **and written down somewhere safe** — losing it means every customer reconnects |

---

## 2. The Meta app

These identifiers are not secret — they appear in every login URL.

| | |
|---|---|
| App name | **Rivon** (renamed from `rivon_test`; the name is shown on customers' consent screens) |
| App ID | `1027179017015673` |
| App type | Business |
| App mode | **Development** — see §5 before changing it |
| Business portfolio | *Tehman's Market* |
| Login configuration — Pages + Instagram | `1615515353401241` |
| Login configuration — WhatsApp Embedded Signup | `1050395724554089` |
| Products added | Messenger, Instagram, WhatsApp, Webhooks, Facebook Login for Business |
| Redirect URI | `https://app.tideover.site/connect/meta/callback` — exact, no trailing slash |
| Privacy policy URL | `https://app.tideover.site/privacy` |
| Data deletion URL | `https://app.tideover.site/data-deletion` |
| Graph API version | `v25.0`, pinned |
| Connected in production | Messenger → *Tehman's Market*, Page id `1393807600471063`; Instagram → `rivonna.ai`, linked to that Page. Both under the test tenant |

The credentials file also holds an **Instagram App ID and secret**. We do not use
them — they belong to Instagram's own login, and we connect Instagram through
the Page.

---

## 3. The production test tenant

A tenant called *Rivon Test Solar* with owner `test@tideover.site` exists in
production for end-to-end checks. It has a real Page and a real Instagram account connected.

**Delete it before showing the product to anyone real.** When the Meta app goes
Live, content created in development mode becomes visible to everyone.

---

## 4. Lessons learned the hard way

Each of these happened. The fix is in place; the lesson is so it does not happen
in a new form.

### A secrets file was committed to the public repo (19 Sep)
`git add -A` swept a new `scripts/.prod_secrets` into a commit. It was removed
and force-pushed, **and every secret in it was rotated** — the orphaned commit
is still reachable by its hash, so rotation was the real fix.
**Never `git add -A`. Add files by name. Check `git status` first.**

### A second secrets file nearly went the same way (22 Sep)
`local_secret_ids.txt` sat untracked and un-ignored in the repo root. It is now
ignored (`local_secret*`, `*secret*.txt`).
**Whenever a new file holds a credential, check `git check-ignore <file>`.**

### An OpenAI key was pasted into a chat
Treat it as exposed. **Rotate it before Phase 2 uses it.**

### Root AWS keys on a laptop
Replace them with the `rivon-deployer` IAM user and delete the root key.

### Ten commits never reached GitHub (22 Sep)
The server deploys with `git pull`. Nothing had been pushed, so the "deploy"
rebuilt the old code and every new endpoint returned 404.
**Push before asking anyone to deploy. Check `git log origin/main..HEAD` is empty.**

### A test-only package broke production (22 Sep)
`httpx` was a dev dependency. The production image is built with
`uv sync --no-dev`, and the import sat *inside* a function — so the app started
healthy, every test passed, and the first real Connect returned a 500.
**`tests/test_dependencies.py` now fails if anything `rivon/` imports is not a
runtime dependency.**

### A body-less POST was turned away as "Expected JSON" (22 Sep)
The dashboard's API proxy refuses anything that could carry a body unless it
says `application/json` — that is what stops a cross-site form posting through
it. A POST with no body still has to send the header. The client now does.

### Instagram "connected" but nothing appeared (25 Sep)
The permissions were granted, but Meta returned the Page with **no Instagram
account attached**: the account was not a professional account linked to the
Page. The dialog had warned: *"Instagram Pro account required"*. The return
screen now says so plainly.

**What was actually wrong:** `rivonna.ai` was linked to the *Rivona Ai* personal
profile in **Accounts Center** — and that link means nothing to the messaging
API. Meta only reports an Instagram account (`instagram_business_account`) when
it is linked to the **Page**. Fixed by linking it from the Instagram phone app
(Edit profile → Page → Connect → *Tehman's Market*), then connecting again in
Rivon and ticking the Instagram account in the dialog. A real DM got the reply
the same evening.
**If Instagram will not connect, check the Page's Linked accounts, not Accounts
Center.**

### A Graph API Explorer token was pasted into a chat (25 Sep)
Short-lived, read-only, and expired within the hour, so no action was needed.
Still: **never paste a token into a chat** — describe the result or a
screenshot with the token cropped out.

---

## 5. Meta traps

| Trap | What happens | What to do |
|---|---|---|
| **Switching the app to Live too early** | Only permissions approved in App Review appear in a Live app's consent screen. Ours are not approved, so the connect flow would break for everyone. | Stay in Development until App Review is done. The toggle is the front door; App Review is the keys. |
| **Development mode is invisible** | Only people with a role on the app (Administrator, Developer, Tester) can connect an account *or* message one. Everyone else is silently dropped. | Add every tester under *App roles* first, then debug. |
| **Development mode is not a sandbox** | WhatsApp Embedded Signup creates a real account on a real number. | Use a spare number. |
| **Fragment URLs are rejected** | `…/privacy#data-deletion` is not accepted as a data-deletion URL. | It must be its own page — hence `/data-deletion`. |
| **Redirect URI must match exactly** | Strict mode is on. A mismatch shows a blank Facebook error page. | `https://app.tideover.site/connect/meta/callback`, no trailing slash. |
| **Two webhook settings, not one** | Connecting subscribes the *Page* to the app; the *app* also needs its callback URL and fields set in the dashboard. | Both, or nothing arrives. |
| **`pages_manage_metadata` unticked** | The connect looks fine and the Page never receives anything, because it cannot be subscribed. | We refuse the connect if it is missing. |
| **Our own replies come back** | Meta echoes outbound messages to the webhook with `is_echo`. | Ignored by the adapter — otherwise the bot answers itself forever. |
| **The Embedded Signup code lives 30 seconds** | Anything between the callback and the exchange risks losing it. | Exchange first, always. |
| **WhatsApp ids arrive by browser event** | `waba_id` and `phone_number_id` are not in the redirect. | The page must listen for `WA_EMBEDDED_SIGNUP`. |
| **The 24-hour window** | Free-form replies only within 24 hours of the customer's last message. | Later messages (quotations) need an approved WhatsApp template or a Messenger tag. |
| **Embedded Signup v2 is deprecated 15 Oct 2026** | | We build against v4. |
| **ManyChat's dialog looks different** | They use the old consumer login, grandfathered. | New business apps must use Facebook Login for Business. |
| **Accounts Center is not a Page link** | Linking Instagram to your *personal profile* in Accounts Center does not attach it to the Page, so Meta returns the Page with no Instagram and nothing connects. | Link it to the **Page**: Instagram app → Edit profile → **Page** → Connect, or Facebook as the Page → Settings → Linked accounts. |
| **Instagram's website has no Page option** | Edit profile on instagram.com has no "Page" row. | Use the Instagram phone app, or Facebook's Linked accounts. |
| **The login dialog remembers the last selection** | Facebook Login for Business reuses the Pages and Instagram accounts ticked last time — including a time when the Instagram account did not exist to tick. | Choose **Edit previous settings** in the dialog and tick the new asset. |
| **Graph API Explorer tokens are per asset** | A token with `pages_read_engagement` still returns `"data": []` from `me/accounts`, or error `#10` on the Page, if the Page was not ticked when it was generated. | Regenerate, *Edit previous settings*, tick the Page. Or skip the Explorer and look at the Page's Linked accounts screen. |
| **Instagram testers in development mode** | A DM is only delivered if the sender's Instagram is linked (Accounts Center) to a Facebook account with a role on the app. You cannot test by DMing the business account from itself. | Test from a second Instagram account belonging to an app Tester. The DM may land in the business's **Requests** folder; the reply still goes out. |

---

## 6. Engineering traps

| Trap | Detail |
|---|---|
| **`FORCE ROW LEVEL SECURITY` binds the owner too** | A `SECURITY DEFINER` function owned by the table owner is still filtered. See deviation §3 for how routing gets round it safely. |
| **`begin_nested()` autoflushes first** | Add an object *after* opening the savepoint, or a failing insert kills the whole transaction instead of the savepoint. |
| **Unique external ids across tenants** | API tests share a committed database, so each test needs its own Page and number ids. |
| **Stale Docker image** | A new endpoint returning 404 is usually an old image. `docker compose up -d --build`. |
| **Next.js 16 renamed middleware** | It is `web/src/proxy.ts`. |
| **React runs effects twice in development** | The Meta callback page guards against it — the OAuth state is single use, so a second exchange would fail on a connection that worked. |
| **`lucide-react` dropped brand icons** | Channel icons are drawn inline in `web/src/components/brand/channel-icons.tsx`. |
| **Git Bash rewrites paths** | Arguments like `/dashboard` get mangled on Windows. Prefix with `MSYS_NO_PATHCONV=1`. |
| **Heredocs with backslashes** | Escaping breaks easily in Git Bash. Write a small Python script to a file and run it instead. |
| **The credentials file mixes separators** | Some lines use `:`, some use `=`. Parse with `[:=]`. |
| **Amazon Linux has no `buildx`** | Installed in the server's user-data; see `docs/DEPLOY.md`. |

---

## 7. Conventions (short form — `CLAUDE.md` is authoritative)

- Package root `rivon`; modules `rivon.channels`, `rivon.business`, …
- Settings prefix `RIVON_`; database `rivon`; images `rivon-api`, `rivon-worker`, `rivon-web`.
- Every table: `id` (UUID), `tenant_id`, `created_at`, `updated_at`; timestamps UTC and timezone-aware.
- An Alembic migration for every schema change. Never edit a migration that has run.
- Tests beside the feature, written with it.
- One feature ID per session; ask which if unclear.
- Do not add dependencies without asking.
- Commit messages explain *why*. They are written to be read later.

---

## 8. Commands worth having

```bash
# Local
docker compose up -d
uv run pytest -q
cd web && npm run dev

# Is anything unpushed?
git log --oneline origin/main..HEAD

# Is a file safely ignored?
git check-ignore -v local_secret_ids.txt

# Deploy the dashboard
cd web && npx vercel --prod --yes --scope rivon2

# Deploy the API (on the server)
cd /opt/rivon && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs migrate | tail -5
docker compose -f docker-compose.prod.yml logs api    | tail -30
docker compose -f docker-compose.prod.yml logs worker | tail -30

# Create a tenant
uv run python -m rivon.platform.cli provision-tenant \
  --name "…" --slug … --owner-email …
```
