# Testing

How Rivon is tested, and why the tests look the way they do.

**433 tests** at `cf08ca1`. All run against a real Postgres, as the real
application role, with row-level security in force.

---

## 1. Running them

```bash
docker compose up -d postgres redis      # the tests need both
uv run pytest -q                         # everything, ~1 minute
uv run pytest tests/test_webhooks.py -q  # one file
```

If every test errors with `ConnectionRefused`, Docker is not running.

---

## 2. What makes these tests different

### They run as the application, against the real schema

`tests/conftest.py` builds the schema by running the **actual Alembic
migrations** — up, down, and up again, so every downgrade is exercised on every
run. The tests then connect as `rivon_app`, not as a superuser, so row-level
security applies exactly as in production. A test that passes here has passed
through the same isolation a real request does.

### They name the failure, not the function

Test names describe the thing that must not happen:

```
test_a_retried_delivery_is_stored_and_enqueued_once
test_two_businesses_cannot_claim_the_same_page
test_our_own_reply_coming_back_is_not_treated_as_a_customer_message
test_connecting_never_overwrites_a_row_rls_happens_to_expose
```

The priority is the failures that would reach a real person — a second reply, a
message for the wrong business, a credential readable from a database dump —
over whether a function returns what it returns.

### They are proved to bite — mutation testing

After a feature's tests pass, the code is broken on purpose, one change at a
time, and each change must make a test fail. A change that survives means a
test is missing, or the code it removed was doing nothing.

It has found real problems every time:

| Feature | Mutation that survived | What it revealed |
|---|---|---|
| CHN-07 | Remove the tenant filter from the connection lookup | Masked by RLS in every test. Without it, a call for one tenant could **silently overwrite another's credential** whenever RLS exposed the row. New test added. |
| CHN-07 | Let any tenant redeem any OAuth state | Also masked by RLS. New test added. |
| CHN-02 | Treat account-update notifications as messages | The test payload had no messages to leak. New test added. |
| CHN-05 | Reply on a connection waiting for reconnection | Masked by disconnect destroying the token. New test for the needs-reauth case. |
| CHN-13 | Disconnect WhatsApp as though it were a Page | **The two paths were identical.** Merged into one — less code, same behaviour. |
| CHN-13 | Ignore a plain `{"success": false}` from Meta | The fake only ever returned error objects. New case added. |

Some survivors are **equivalent mutants** — changes that alter no behaviour.
Removing the `sha256=` prefix check is one: the digest comparison still fails.
Those are left in place as defence in depth and recorded rather than chased
with a contrived test.

The mutation scripts are kept in the session scratchpad rather than the repo;
the pattern is: a list of `(file, original text, replacement, label)`, apply
one, run that feature's test file with `-x`, restore, report *caught* or
*SURVIVED*.

### Nothing needs Meta

Every channel test runs against fakes: a fake channel for the message path, a
fake Graph API for the connect flows, a fake send endpoint for outbound. That is
hard rule 4, and it means the whole channel layer was finished and demonstrated
before Meta approved anything.

---

## 3. The guards

Some tests exist to stop a whole class of mistake rather than test a feature.

| Test | Stops |
|---|---|
| `test_schema_conventions.py` | A table without forced RLS or a tenant policy; an index not led by `tenant_id`; an extra RLS policy — unless each exception is listed **with a reason**. Also enforces a single numbered migration chain, and migrations that do not import application code. |
| `test_dependencies.py` | Anything `rivon/` imports — including inside functions — that is not a runtime dependency. Would have caught the `httpx` production failure. |
| `test_tenant_isolation.py` | One tenant seeing, changing or deleting another's data — at the database level, through pooled connections, and in the request dependency. Each feature's own test file then repeats the check through its API. |
| `test_app_surface.py` | API docs and schema exposed in production. |

The two review lists in `test_schema_conventions.py` are where deliberate
exceptions to hard rule 2 live. Today they hold the login-by-email lookup, the
outbox relay, and the channel routing function — each with its reason.

---

## 4. Where the tests are

| File | Tests | Covers |
|---|---|---|
| `test_webhooks.py` | 43 | Signatures, handshake, the three adapters, routing, dedupe, end to end over HTTP |
| `test_business.py` | 39 | Profile and services |
| `test_capacity.py` | 39 | Service areas, inventory, crews |
| `test_pricing_rules.py` | 36 | Rate cards and pricing settings |
| `test_channels.py` | 36 | The message model, adapter contract, fake channel |
| `test_verticals.py` | 34 | The solar question set and sizing |
| `test_channel_connections.py` | 33 | Connections, encryption, routing, OAuth state |
| `test_channel_connect.py` | 30 | The Messenger and Instagram connect flow |
| `test_whatsapp_signup.py` | 30 | Embedded Signup |
| `test_channel_picker.py` | 24 | Beta: the Page picker — including a Page created after sign-in appearing on refresh |
| `test_auth.py` | 21 | Sign-in, refresh rotation, password reset |
| `test_outbound.py` | 20 | The dispatcher and the echo |
| `test_tenant_isolation.py` | 13 | Cross-tenant access |
| `test_events.py` | 12 | Outbox, relay, exactly-once delivery |
| `test_schema_conventions.py` | 9 | The schema guards |
| `test_regions.py` | 5 | Tenant regions |
| `test_dependencies.py` | 4 | The dependency guard |
| `test_app_surface.py` | 3 | Production surface |
| `test_health.py` | 2 | Health endpoint |

---

## 5. Beyond the test suite

| Check | How |
|---|---|
| **Production end to end** | A script signs in as the test tenant on `app.tideover.site` and exercises every screen's API: 47 checks when last run for the business features |
| **Webhook security in production** | Handshake on all three channels, wrong token 403, unsigned 403, correctly signed 200, tampered 403 |
| **The real thing** | A message to the connected Page, and the reply arriving on a phone |
| **CI** | GitHub Actions on every push, including a check that the worker and relay start |

---

## 6. What is not tested yet

| | |
|---|---|
| The dashboard's own code | There is no frontend test runner. The dashboard is verified through its API and by hand. |
| The WhatsApp button | Built, but only its API is tested. The browser half — SDK loading, pairing the code with the session event, the 30-second window — is verified by hand. This is where a browser test would earn its place. |
| A restore from backup | Never attempted. |
| Load | Not attempted. The webhook path is built to be fast, but nobody has measured it. |
