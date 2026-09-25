# Rivon — handouts

The living record of what Rivon is, where it stands, and why it is the way it is.

The documents in `/docs` are the **plan** — the spec, the scope and the feature
list as they were written before building started. These handouts are the
**record** — what was actually built, what changed on the way, and what is left.
When the two disagree, these are the more recent truth, and
[`05-design-deviations.md`](05-design-deviations.md) says exactly where and why.

Last updated: **25 September 2026**, at commit `cf98ef1`.

---

## Read in this order

| # | File | What it answers | Read it when |
|---|---|---|---|
| 1 | [`01-project-handout.md`](01-project-handout.md) | What is Rivon, who is it for, how is it built | You are new, or explaining it to someone |
| 2 | [`02-project-status.md`](02-project-status.md) | Where exactly are we today | Every time you pick the work up |
| 3 | [`03-done.md`](03-done.md) | Everything built, by feature ID, with the commit | You need to know if something exists |
| 4 | [`04-remaining.md`](04-remaining.md) | Everything left, in the order it should happen | Planning the next piece of work |
| 5 | [`05-design-deviations.md`](05-design-deviations.md) | Where we departed from the spec, and why | Before assuming `/docs` is still accurate |
| 6 | [`06-decisions.md`](06-decisions.md) | Every significant decision, dated, with its reason | Before re-opening a decision |
| 7 | [`07-memory.md`](07-memory.md) | Facts, gotchas and lessons that are easy to lose | Before touching deploys, Meta, or secrets |
| 8 | [`08-updates-log.md`](08-updates-log.md) | What happened, day by day | Writing a progress report |
| 9 | [`09-channels-meta.md`](09-channels-meta.md) | How WhatsApp, Messenger and Instagram work in Rivon | Working on channels or Meta setup |
| 10 | [`10-operations.md`](10-operations.md) | Environments, deploy, verify, troubleshoot | Deploying, or something is broken |
| 11 | [`11-testing.md`](11-testing.md) | How we test, and why the tests look the way they do | Writing or reviewing code |

---

## The one principle these files are built on

**The design is a plan, not a contract.** Rivon has already changed shape
several times as we learned things the spec could not have known: which Meta
login flow new apps are allowed to use, what Postgres does to a table owner
under forced row-level security, what a real customer needs to see when a
connection half-works. Each change is recorded, reasoned, and tested.

What is **not** flexible — and these files are explicit about it everywhere it
matters:

- the **eleven hard rules** in `CLAUDE.md` — an exception is possible, but only
  as a named, reviewed, tested exception (see the one we have taken, in
  [`05-design-deviations.md`](05-design-deviations.md) §3), never a quiet drift;
- the **legally required features** — AI disclosure, human review of rejections,
  explainable scoring, export and erasure, consent records, EU data residency.
  These can change *how*, never *whether*.

Everything else is a decision we are allowed to revisit, and expected to when
the evidence says so.

---

## Keeping these current

These go stale the moment they stop being updated, and a stale status document
is worse than none. So:

- **After every feature:** update `02-project-status.md`, tick it off in
  `03-done.md` / `04-remaining.md`, add a line to `08-updates-log.md`.
- **When you change the design:** add an entry to `06-decisions.md` and, if it
  departs from `/docs`, to `05-design-deviations.md`.
- **When something bites you:** add it to `07-memory.md` so it bites nobody else.
- **Never put a secret in any of these files.** They are in a public repository.
  Names of settings are fine; values are not.
