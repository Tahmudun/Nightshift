# ADR 0009 — Closure requires both a miss count and elapsed time

- **Status:** accepted
- **Date:** 2026-08-01
- **Milestone:** M1 (M1b)

## Context

PRODUCT-SPEC §7.4 specifies a four-state closure machine and says a listing
moves toward stale after "missing repeatedly across a configured window". It
does not configure the window. Invariant I3 says a source returning an error,
a timeout or an empty array is not evidence a job closed, and that source
unavailable leaves listing state unchanged, full stop.

That leaves one genuine product decision: **how much absence is enough?**

The two failure directions are not symmetric.

- **Closing a job that is still open** hides an opening the user would have
  applied to. They never learn it existed. The product's entire premise —
  same-day knowledge of any NYC tech opening — is defeated silently.
- **Keeping a closed job open** wastes a user's time on an application that
  goes nowhere, and they find out within minutes of clicking through.

The first error is invisible and permanent. The second is visible and cheap.

A second constraint arrives with ADR 0007: polling cadence is about to stop
being uniform. The `hot` tier polls hourly and the `warm` tier daily. Any rule
phrased purely in polls therefore means different things on different boards —
"three misses" is three hours on one and three days on another.

## Decision

A job moves to `closed` only when **both** conditions hold:

1. `consecutive_misses >= 3` on every one of its source records, and
2. `now - last_seen_at >= 7 days`.

Intermediate states:

- **3 consecutive misses** → `possibly_stale`. Still shown to the user, marked.
- **No successful poll of the board for 14 days** → `unverified`.

`unverified` never leads to `closed`, no matter how long it persists. It is a
statement about the source, not about the job.

Reopening is permitted: a job seen again returns to `open` with `closed_at`
nulled. Every transition is appended to `job_status_events`.

## Why both conditions

Each one alone fails in a way the other covers.

**Misses alone** are cadence-dependent, per the ADR 0007 problem above. Worse,
they get *more* aggressive exactly where the product cares most: an NYC-active
board is in the `hot` tier, so its jobs would close after three hours of
absence while a quieter board's jobs get three days.

**Elapsed time alone** would close a job on a board that has been polled once
in seven days and simply never re-checked. Seven days of not looking is not
seven days of absence.

Together they read as: *we looked at least three times, spread over at least a
week, and it was gone every time.*

## Why the cautious end of the range

The human was offered three settings — cautious (3 misses / 7 days), balanced
(2 / 3 days), and never-infer (close only on direct confirmation) — and chose
cautious.

It matches the asymmetry above and it matches what boards actually do:
employers pause and re-publish listings, and a posting can vanish from a board
for a day for reasons that have nothing to do with the role being filled.

Never-infer is the strictest reading of I3 and was rejected on cost, not on
principle: confirming closure directly means fetching each posting's own
endpoint, which is exactly the per-job request volume ADR 0007's two-phase
design exists to avoid. It stays available as an upgrade — `last_verified_at`
already exists on the schema for it — and when M1d can afford targeted
verification, a direct confirmation should close a job immediately rather than
waiting out this window.

## Consequences

- Jobs remain visible for up to a week after they actually close. This is the
  chosen trade and the UI must not pretend otherwise: `possibly_stale` is a
  presented state with an explanation, not a hidden one.
- A board that disappears for two weeks moves all of its jobs to `unverified`
  and closes none of them. The coverage surface has to say so, or the user sees
  stale jobs with no account of why.
- The thresholds are constants in one module, named and versioned. Changing
  them is a code review with a fixture, not a config tweak — because a change
  here changes what the product claims about every job at once.
- `job_status_events` is append-only and enforced by trigger. Without it,
  reopening a job erases the evidence that it ever closed, and I6's "record the
  evidence" has nothing to point at.

## Alternatives rejected

**Balanced (2 misses / 3 days).** Tidier lists, and it would hide real openings
during ordinary re-publication churn. The failure it trades into is the
invisible one.

**A per-source threshold.** Superficially attractive — Greenhouse and Lever do
behave differently — but there is no evidence yet about how they differ on
delisting, and inventing per-provider constants without measurements is exactly
the guessing this project forbids elsewhere. Revisit with data from M1d.

**Closing on the first `authoritative_empty` board.** A board going from 40
postings to zero in one poll is far more likely to be a provider fault than 40
simultaneous closures. It gets no special case; the empty board increments
misses like any other absence.
