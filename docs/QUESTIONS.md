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
