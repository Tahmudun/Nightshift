# QUESTIONS

Things that need a human. Batched, not blocking — work continues around them.

Format: newest first. Answered questions move to the bottom with the answer and
the date, because the reasoning is usually worth more than the decision.

---

## Q3 — Which boards go in the registry, and who vets them?

**Raised:** 2026-07-29 (M0) · **Type:** product / effort · **Blocking:** no

A1 is right that the board registry is the most interesting infrastructure
problem here, and it is also the one that needs a judgement call I should not
make alone.

The registry has two entries today: Datadog (active, polled) and Stripe
(verified, disabled until M1). Scaling it means deciding how the list is built:

1. **Curated NYC tech list, ~50–100 companies, hand-verified once.** Highest
   signal, a few hours of one-time work, and the resulting registry is a genuine
   asset. My recommendation.
2. **Resolve from a community internship aggregator's company list.** A1 permits
   this explicitly — as a source of *company names to resolve into board tokens*,
   never as a source of listings. Faster and broader, noisier, and biased toward
   internships.
3. **Both**, curated first.

What I need from you: roughly how many companies, and are you willing to be the
human in the human-in-the-loop for the candidate entries the resolution pipeline
emits? A1 says never auto-commit, so someone has to review them.

**Not blocking:** M1 builds the resolution pipeline against however many entries
exist. The pipeline is the deliverable; the list length is a dial.

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

*(none yet)*
