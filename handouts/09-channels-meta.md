# Channels — WhatsApp, Messenger and Instagram

How messaging works in Rivon, how the Meta side is set up, and what is left.
Operational steps for deploying live in [`10-operations.md`](10-operations.md);
the traps are collected in [`07-memory.md`](07-memory.md) §5.

---

## 1. The idea

A business connects its own accounts from the Rivon dashboard, the way ManyChat
does it: press *Connect*, approve Rivon on Meta, and the account starts
answering. Nobody on our side touches a per-customer setting.

That splits the work in two:

| | Done how often | By whom |
|---|---|---|
| The Rivon Meta app — permissions, login configurations, webhook URLs | **Once, ever** | The team |
| Each business's Page / Instagram account / WhatsApp number | **Every business, self-serve** | The business, in about a minute |

One consequence shapes everything: **webhooks are app-level, not
business-level.** Every message for every customer on a platform arrives at one
URL. The first real job of the webhook is working out which tenant it belongs to.

---

## 2. The path a message takes

```
Customer ──► Meta ──► POST /webhooks/messenger
                          │
                          ├─ 1. Verify X-Hub-Signature-256 over the raw bytes   (403 if wrong)
                          ├─ 2. Parse with the adapter                          (pure, no I/O)
                          ├─ 3. channel_route(provider, account_id) → tenant    (one UUID)
                          ├─ 4. INSERT inbound_messages … ON CONFLICT DO NOTHING
                          ├─ 5. publish("message.received") in the same transaction
                          └─ 6. 200                                             (always, once signed)
                                    │
                         relay ─────┘──► Celery "rivon.outbound"
                                                │
                                   echo_reply (placeholder for the conversation engine)
                                                │
                              outbound.queue()  — claim the dedupe key, or stop
                              outbound.deliver() — send with the Page's token
                                                │
                                              Meta ──► Customer
```

Why each step is where it is:

- **Signature first, over raw bytes.** Re-serialising the JSON changes whitespace
  and key order, and the signature stops matching. There is a test for that exact mistake.
- **Always 200 once signed.** Meta retries anything else, and it keeps delivering
  for a while after a customer disconnects. A retry of something we already
  stored risks a second reply to a real person.
- **Store before anything else** (hard rule 3), so nothing is lost to a crash.
- **Dedupe twice** — on the way in by provider message id, on the way out by a
  key derived from the message being answered.

---

## 3. Connecting an account

### Messenger and Instagram — Facebook Login for Business

1. The customer presses **Connect** on the Channels page.
2. The API mints a single-use `state` and returns Meta's dialog URL with the
   *Pages + Instagram* configuration.
3. The customer chooses their business portfolio, Page, and Instagram account.
4. Meta sends them back to `/connect/meta/callback` with a code.
5. The API redeems the state (once), exchanges the code for a long-lived
   business token, checks which permissions were actually granted, reads the
   granted Pages, **subscribes each Page** to our webhooks, and stores one
   connection per Page and per linked Instagram account.
6. The return screen lists what was connected **and what was left out, and why**.

It refuses outright if `pages_messaging` or `pages_manage_metadata` is missing —
without the second, a Page can never be subscribed and would silently receive
nothing.

### WhatsApp — Embedded Signup (backend done, button not yet)

Meta *creates* the customer's WhatsApp Business Account during the dialog, so
the shape is different:

1. The page calls `FB.login` through Facebook's JavaScript SDK with the WhatsApp configuration.
2. The page listens for the browser `WA_EMBEDDED_SIGNUP` event, which carries
   `waba_id` and `phone_number_id` — they are **not** in the redirect.
3. The code lives **30 seconds**; it goes straight to `/channels/whatsapp/complete`.
4. The API exchanges it, checks permissions, subscribes the WhatsApp account,
   registers the number with a PIN, and stores the connection.

The PIN belongs to the customer: for a new number we generate one and show it
once, never storing it; for a number that already has one, we ask for it.

### Disconnecting

Disconnect marks the connection revoked, **destroys the stored token**, and
unsubscribes the account at Meta — but only once nothing else needs it, because
a Page and its Instagram account, or two numbers on one WhatsApp account, share
a subscription.

If a customer removes Rivon from Meta's side instead, the next send fails with
Meta's code 190, the connection moves to **needs reauth**, and the dashboard
says so.

---

## 4. Where it lives in the code

| File | Responsibility |
|---|---|
| `rivon/channels/messages.py` | The internal message model: one shape for every platform |
| `rivon/channels/adapters.py` | The adapter contract and registry |
| `rivon/channels/providers.py` | The WhatsApp, Messenger and Instagram adapters — translation only |
| `rivon/channels/fake.py` | The fake channel and a fake platform, for tests and offline demos |
| `rivon/channels/meta.py` | Talking to the Graph API; the HTTP call is injected |
| `rivon/channels/oauth.py` | The connect and disconnect flows |
| `rivon/channels/service.py` | Connections, the OAuth state, and the routing lookup |
| `rivon/channels/crypto.py` | Sealing and opening customers' tokens |
| `rivon/channels/webhooks.py` | The three endpoints Meta calls |
| `rivon/channels/inbound.py` | Signature, routing, storing and enqueueing |
| `rivon/channels/outbound.py` | The dispatcher |
| `rivon/channels/echo.py` | The placeholder reply — replaced by the conversation engine |
| `rivon/channels/api.py` | The dashboard's endpoints |
| `web/src/app/(app)/channels/` | The Channels page |
| `web/src/app/connect/meta/callback/` | Where Meta returns the customer |

### Tables (migrations 0010–0012)

| Table | Holds |
|---|---|
| `channel_connections` | One row per connected account; token encrypted; status |
| `channel_oauth_states` | Single-use `state` values for the connect flow |
| `inbound_messages` | What customers sent, exactly as it arrived; unique per provider message id |
| `outbound_messages` | What we intend to say, claimed before sending; unique per dedupe key |

---

## 5. Where each channel stands

| Channel | Connect | Receive | Reply | Blocking |
|---|---|---|---|---|
| **Messenger** | ✅ | ✅ | ✅ | Nothing — working in production |
| **Instagram** | ✅ code | ✅ code | ✅ code | An Instagram professional account must be linked to *Tehman's Market* |
| **WhatsApp** | 🟡 backend only | ✅ code | ✅ code | The dashboard button (JS SDK + browser event) |

### To connect Instagram

1. Meta Business Suite → *Tehman's Market* → Settings → Accounts → **Instagram accounts** → Add.
2. The account must be **Business or Creator**, not personal.
3. In the Instagram app: Settings → Messages and story replies → Message controls → **allow access to messages**.
4. Press **Connect** on the Instagram card again.

---

## 6. Development mode and going live

We are in **Development mode** with **Standard Access**, which is automatic for a
Business-type app and needs no documents. Everything works — for people who
hold a role on the app.

| | Development (now) | Live, after App Review |
|---|---|---|
| Who can connect or message | App Administrators, Developers, Testers | Anyone |
| WhatsApp onboardings | 10 per rolling 7 days | 200 per rolling 7 days |
| Customer's WhatsApp display name | Not approved — shows the number | Shows the business name |

To go live, in this order — never out of it:

1. Register a legal entity; open a business bank account (documents must show the business name).
2. Meta business verification, domain verification, two-step verification.
3. App Review for Advanced Access: `pages_messaging`, `pages_manage_metadata`,
   `instagram_basic`, `instagram_manage_messages`,
   `whatsapp_business_messaging`, `whatsapp_business_management`.
4. Tech Provider registration for WhatsApp.
5. Automated deauthorize and data-deletion callbacks live.
6. **Then** switch the app to Live.

Switching to Live before App Review removes the messaging permissions from the
consent screen and breaks the flow for everyone.

---

## 7. Configuration

| Setting | Secret | Purpose |
|---|---|---|
| `RIVON_META_APP_ID` | No | The Meta app |
| `RIVON_META_APP_SECRET` | **Yes** | Verifies every webhook; signs token exchanges |
| `RIVON_META_VERIFY_TOKEN` | **Yes** | Echoed once when a webhook URL is saved |
| `RIVON_META_GRAPH_VERSION` | No | Pinned, `v25.0` |
| `RIVON_META_LOGIN_CONFIG_PAGES` | No | Configuration id for Pages + Instagram |
| `RIVON_META_LOGIN_CONFIG_WHATSAPP` | No | Configuration id for Embedded Signup |
| `RIVON_META_REDIRECT_URI` | No | Must match the App Dashboard exactly |
| `RIVON_CHANNEL_TOKEN_KEY` | **Yes** | Encrypts customers' tokens; different in every environment |

Note what is absent: no Page id, no phone number, no customer token. Those are
per customer and live encrypted in the database. **Adding a customer never
touches a config file or a deploy.**
