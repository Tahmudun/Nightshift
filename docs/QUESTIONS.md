# QUESTIONS

Things that need a human. Batched, not blocking — work continues around them.

Format: newest first. Answered questions move to the bottom with the answer and
the date, because the reasoning is usually worth more than the decision.

---

## Q2 — Deployment target for the M4 ship

**Raised:** 2026-07-29 (M0) · **Type:** cost · **Blocking:** no

A15 says M0–M4 is the portfolio project and M4 should be a real ship — deployed,
case study written, on the resume. That is the first point where this project can
cost money, so it is worth deciding before it arrives rather than under deadline.

The shape needed: one Next.js app, one Python service (API + worker in one
process), Postgres with PostGIS and pgvector, Redis.

The PostGIS + pgvector requirement is the constraint that matters — several
managed Postgres free tiers do not offer both. Rough options:

- **Fly.io** — one machine + a Postgres app, both extensions installable. Around
  $5–10/month at this size, scale-to-zero possible.
- **Railway / Render** — simpler, similar money, extension support needs checking
  per provider.
- **A single small VPS with docker compose** — cheapest and closest to the
  committed compose file, but you own the backups.
- **Local-only, demo by video** — $0, and A9's target is $0 for M0–M4. Loses the
  live link, which is a real part of what makes the project persuasive.

What I need: a monthly figure you are comfortable with, or "local only". I will
write the ADR with the number and the degradation behaviour either way.

**Not blocking:** nothing before M4 needs it, and `docs/architecture/costs.md`
tracks the answer when it exists.

---

## Q1 — Gmail OAuth client, and confirmation you accept the A8 constraint

**Raised:** 2026-07-29 (M0) · **Type:** credential + legal · **Blocking:** no, until M7

M7 needs a Google Cloud OAuth client that only you can create. Before then,
please confirm you accept what A8 establishes, because it is a real product
limitation and not a technical detail:

- `gmail.readonly` is a Google **restricted scope**. An unverified app is capped
  at a small number of test users and shows an unverified-app warning screen.
  Full verification requires a security assessment that is not realistic for this
  project.
- Therefore **public demo mode and Gmail are mutually exclusive.** The public
  demo uses synthetic classified-message fixtures only. Never a real inbox. If
  you want a shareable demo *and* Gmail on your own account, those are two
  deployments.
- Storage is minimal by design: message id, thread id, sender, subject,
  timestamp, classification, extracted dates, confidence, associations. **Never
  bodies.** A classifier that needs body text processes in memory and stores only
  its output.
- Disconnect must revoke the token *and* delete every derived row, with a test
  proving it.

Nothing to do now. Flagging at M0 so M7 does not end in a surprise.

---

## Answered

## Q4 — Should CI pin its Python dependencies?

**Raised:** 2026-08-05 (M3a.1) · **Answered:** 2026-08-05

> **Numbering correction.** This was raised as "Q3" and Q3 was already taken by
> the registry question below. Renumbered on answering rather than left to
> collide, since these are referred to by number from PROGRESS and the ADRs.

**Both. Pin the jobs that gate a merge; keep one unpinned job that gates
nothing.** The human's decision on 2026-08-05, taken on the recommendation in
the question. Full reasoning and what was rejected: **ADR 0016**.

What the question got right, and it is the part worth keeping: reproducibility
and early warning only conflict if there is one place to install. There are now
two.

- `ci.yml` installs from `services/api/constraints-ci.txt` — 72 distributions at
  exact versions, wired in through one workflow-level `PIP_CONSTRAINT` so all
  three install steps read the same file and cannot drift apart. The `python`
  job then diffs `pip freeze` against that file, so "CI is pinned" is checked
  rather than assumed — a dependency added to `pyproject.toml` and never
  regenerated would otherwise install unpinned with nothing saying so.
- `dependency-canary.yml` installs unpinned, weekly, and runs the checks a
  release can break — including the drift probe that started all this. It runs
  on `schedule` and `workflow_dispatch` only, so it cannot gate a merge. Every
  run writes a diff of unpinned-versus-pinned to the job summary, green or red.

**Who reads it**, which was the open half of the question: GitHub emails the
repository owner when a scheduled workflow fails on the default branch. No bot,
no auto-filed issue — one reader does not need a queue.

**What this gives up, stated plainly:** the alembic finding arrived for free the
day it shipped. The same finding would now arrive up to seven days later. That
is the price of an unrelated pull request never going red at a moment nobody
chose, and it is paid deliberately.

Two things generated the answer that were not in the question:

1. **The constraints file cannot be generated on the developer's machine.**
   `make constraints` resolves inside a `linux/amd64` container because the two
   platforms disagree about eleven distributions and one of them irreconcilably:
   onnxruntime resolves to 1.28.0 on linux and 1.23.2 is the newest release with
   a macOS x86_64 wheel. So **the pin covers CI and not a developer's machine**,
   which is a smaller version of the original problem left standing on purpose.
2. **The related gap is now closed.** `make drift` runs the drift probe against
   your own stack and is part of `make acceptance`. It is not in `make check`,
   which must keep working without a database.

## Q3 — Which boards go in the registry, and who vets them?

**Raised:** 2026-07-29 (M0) · **Answered:** 2026-07-30

**The question was wrong, and the answer changed the milestone.**

It asked how many companies to curate — 50, 100 — and assumed a hand-built list.
Asked directly, the human's goal turned out to be: *if any tech job or internship
opens in NYC, the system knows the day of, from any employer.* Curation cannot
reach that at any list length, so the registry stops being curated and becomes
the output of a discovery pipeline.

Answers to what was actually asked:

- **How many companies:** as many as can be discovered. **2,605** board tokens
  were available immediately from one Common Crawl index, measured 2026-07-30.
  Not a target — a floor.
- **Which companies:** not decided in advance at all. Whole boards are polled and
  NYC-ness is read off the postings, so no list needs to declare a city. This
  also means expanding beyond NYC costs nothing at ingestion.
- **Who vets them:** the human, in batches rather than per entry. Candidates
  whose employer name came from the provider are approved as a batch and
  committed from a git diff; unnameable and colliding ones are held for
  individual review. This departs from A1 and is recorded in **ADR 0005**.
- **How often it runs:** a command the human runs, not a schedule. New crawl data
  appears monthly. This only affects finding *new companies* — checking known
  boards for new jobs is hourly or daily and unaffected.

Scope decisions taken at the same time:

- **Employer breadth:** tech roles at *any* employer, not only at tech companies.
  Banks, hospitals, media and universities are in scope eventually — they are on
  Workday/iCIMS/Taleo, which is the milestone after this one and until then a
  stated blind spot.
- **LinkedIn and Indeed: no.** LinkedIn's robots.txt is a blanket `Disallow: /`
  for all agents with an address to email for permission; Indeed's public API is
  partner-only and its inventory is largely resold from the same ATS boards read
  here first-hand. `docs/architecture/board-discovery.md` §9.
- **Long-term ambition** — other cities, then every state, then every job type —
  is answered in §10 of the same document, including where it stops being
  honestly possible.

Full design: `docs/architecture/board-discovery.md`. Decisions: ADRs 0005, 0006,
0007.
