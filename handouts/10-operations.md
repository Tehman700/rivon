# Operations

Environments, deploying, checking a deploy, and what to do when something
breaks. The first-time server setup is in `docs/DEPLOY.md`; this is the
day-to-day.

---

## 1. Environments

| | Local | Production |
|---|---|---|
| API | `http://localhost:8000` (Docker Compose) | `https://api.tideover.site` (EC2, Frankfurt) |
| Dashboard | `http://localhost:3000` (`npm run dev`) | `https://app.tideover.site` (Vercel `fra1`) |
| Database | Postgres in Docker; tests use a separate `rivon_test` database | Neon, Frankfurt |
| Settings | `.env` in the repo root | `/opt/rivon/.env` on the server |
| Compose file | `docker-compose.yml` | `docker-compose.prod.yml` |
| API docs | `/docs` visible | Hidden (404) |
| Password-reset emails | Printed to the console | Printed to the console — **no email provider yet** |

### Services in both compose files

| Service | Does |
|---|---|
| `migrate` | Runs Alembic to head, then exits. Nothing else starts if it fails. |
| `api` | FastAPI |
| `worker` | Celery, consuming the four queues |
| `relay` | Moves outbox events onto the queues |
| `redis` | Queues and cache |
| `caddy` | TLS (production only) |
| `postgres` | Local only; production uses Neon |

### Database roles

| Role | Used by | Can |
|---|---|---|
| `rivon_owner` | Migrations only | Owns the schema. Still subject to forced RLS. |
| `rivon_app` | API and worker | Normal access, always under RLS |
| `rivon_relay` | The relay | Read and mark outbox events across tenants — nothing else |

---

## 2. Settings

Every setting is in `.env.example` with a comment. The ones that must be set in
production, by name only:

```
RIVON_DATABASE_URL           RIVON_MIGRATION_DATABASE_URL    RIVON_RELAY_DATABASE_URL
RIVON_JWT_SECRET             RIVON_PUBLIC_APP_URL            RIVON_API_DOMAIN
RIVON_CHANNEL_TOKEN_KEY      RIVON_META_APP_ID               RIVON_META_APP_SECRET
RIVON_META_VERIFY_TOKEN      RIVON_META_LOGIN_CONFIG_PAGES   RIVON_META_REDIRECT_URI
RIVON_META_LOGIN_CONFIG_WHATSAPP   (the API starts without it; WhatsApp answers 503)
```

`docker-compose.prod.yml` marks these **required**: a missing one fails the
deploy immediately rather than failing on the first customer's click.

Generate a token-encryption key on the server:

```bash
docker run --rm python:3.12-slim sh -c \
  "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

Keep a copy somewhere safe. **Losing it means every connected customer has to
reconnect.** Never reuse the local key in production.

---

## 3. Deploying

### Before anything else: push

The server deploys from GitHub. **Check nothing is unpushed:**

```bash
git log --oneline origin/main..HEAD      # must print nothing
```

### The API

```bash
ssh -i rivon-eu.pem ec2-user@<server>
cd /opt/rivon
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs migrate | tail -5
```

`migrate` should show `Exited (0)`, and the log should name any new migrations.

### The dashboard

From the repo on a laptop:

```bash
cd web && npx vercel --prod --yes --scope rivon2
```

Only needed when something under `web/` changed. A backend-only change needs
only the server steps.

### Migrations

- Every schema change is a new numbered migration. **Never edit one that has run.**
- Every migration must downgrade cleanly — the test suite runs up, down, up on every run.
- Migrations must not import application code, so they keep meaning what they meant.
- Current head: **0012**.

---

## 4. Checking a deploy

Run from any machine:

```bash
curl -s https://api.tideover.site/health
curl -s -o /dev/null -w '%{http_code}\n' https://api.tideover.site/channels
curl -s -o /dev/null -w '%{http_code}\n' https://api.tideover.site/docs
curl -s "https://api.tideover.site/webhooks/messenger?hub.mode=subscribe&hub.verify_token=<VERIFY_TOKEN>&hub.challenge=hello"
```

| Check | Expect | If not |
|---|---|---|
| `/health` | `{"status":"ok","database":true,"redis":true}` | Database or Redis down |
| `/channels` | **401** | **404 means the old image** — the code was not pulled or not rebuilt |
| `/docs` | 404 | Docs are exposed — `RIVON_ENV` is not `production` |
| Webhook handshake | prints `hello` | 404: old image. 503: verify token missing. 403: wrong token |

Also worth confirming after a channel change: a wrong verify token gives **403**,
and an unsigned POST to a webhook gives **403**. Those two are the webhook's
whole defence.

---

## 5. When something is wrong

### Reading the logs

```bash
docker compose -f docker-compose.prod.yml logs api    | tail -50
docker compose -f docker-compose.prod.yml logs worker | tail -50
docker compose -f docker-compose.prod.yml logs relay  | tail -50
```

The **API** log shows whether a webhook arrived, was signed correctly, and was
routed. The **worker** log shows what happened to the reply. They are separate
containers and separate logs.

### Symptom → cause

| What you see | What it usually means |
|---|---|
| Any new endpoint returns 404 | Old image. `git log --oneline -1` on the server; pull and rebuild |
| A 500 on something that works locally | A package missing from the production image. `tests/test_dependencies.py` should have caught it |
| "Expected JSON" in the dashboard | A write reached the proxy without a JSON content type |
| Connect gives 503 | A `RIVON_META_*` setting is missing |
| Blank Facebook error page | Redirect URI does not match the App Dashboard exactly |
| Connected, but no messages arrive | App-level webhook not saved in the Meta dashboard, or `pages_manage_metadata` not granted |
| Message sent, nothing in the API log | The sender has no role on the Meta app (development mode) |
| `rejected an unsigned or mis-signed webhook` | `RIVON_META_APP_SECRET` does not match the app |
| `no active connection for …` | The message was for an account we do not have connected |
| Stored, but the worker is silent | The relay is not running — check its log |
| `giving up on reply` in the worker | Meta refused the send; the line says why |
| Channels page says *Needs reconnecting* | The customer revoked access at Meta, or the token died |
| Instagram "connects" but is not listed | The Page has no Instagram professional account linked |
| WhatsApp dialog: "Not Found" | The API is older than `cf98ef1` — pull and rebuild |
| WhatsApp dialog: "not configured" | `RIVON_META_LOGIN_CONFIG_WHATSAPP` missing from `.env` |
| WhatsApp dialog: "Facebook could not be reached" | An ad blocker stopped Facebook's SDK |
| WhatsApp popup does not open, or errors at once | *Login with the JavaScript SDK* is off, or `app.tideover.site` is not an allowed domain |
| WhatsApp dialog: "no phone number was added" | The account was created without a number — connect again and add one |
| WhatsApp dialog asks for the existing PIN | The number already has two-step verification; enter its PIN before connecting |
| `migrate` exits non-zero | The log names the failing step. Nothing else starts — on purpose |

---

## 6. Not yet in place

| | Why it matters |
|---|---|
| Structured JSON logs with a request id (OPS-04) | Tracing one message across API, relay and worker by hand is slow |
| Sentry (OPS-05) | Errors are found by reading logs, not by being told |
| **Tested restore** (OPS-07) | Neon has point-in-time recovery; nobody has tried restoring from it |
| Email provider | Password resets print to the server console |
| Login rate limiting | Before any real tenant |
| Alerting on a dead channel (CHN-08) | Today the dashboard shows it; nobody is told |
