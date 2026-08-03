# ADR 0011 — Boards carry their own due time, drained by a short cron

- **Status:** accepted
- **Date:** 2026-08-03
- **Milestone:** M1d
- **Refines:** ADR 0007, which decided polling is queue-driven but not how work
  reaches the queue

## Context

ADR 0007 decided that each board poll is an individual ARQ job rather than an
iteration inside one long task, and gave the two tiers their intervals: hot
hourly, warm daily. It did not say what puts those jobs on the queue.

That gap is not a detail. The mechanism decides whether per-board backoff is
expressible at all, what happens when the worker restarts, and whether 2,605
boards arrive at a provider evenly or all at once.

## Decision

**Each board row carries a `next_poll_at`. A cron every five minutes selects the
boards whose time has passed and enqueues one job for each.**

```
every 5 minutes:
    SELECT ... FROM board_poll_state
     WHERE next_poll_at <= now()
     ORDER BY next_poll_at          -- longest overdue first
     LIMIT 500
    -> enqueue poll_board(ats, token) for each
    -> push each next_poll_at forward *before* the jobs run

poll_board(ats, token):
    on 200 or 304:  next_poll_at = now + (1h if hot else 24h)
    on failure:     next_poll_at = now + backoff(consecutive_failures)
```

### Rejected: a cron per tier

An hourly cron enqueueing every hot board, a daily cron enqueueing every warm
one. This is what ADR 0007 literally describes and it is the least machinery.

Rejected because every board in a tier fires in the same instant — a thundering
herd against a handful of provider hosts, growing linearly with the registry —
and because per-board backoff has nowhere to live. A board that has been dead
for a month would be polled exactly as often as a healthy one, forever, with no
way to express otherwise short of editing the registry by hand.

### Rejected: each poll enqueues its own successor

Elegant, and needs no scheduler at all. Rejected because a single lost job stops
that board being polled *forever*, silently. There is no periodic sweep to
notice, no query that shows it, and nothing anywhere that says a board fell out
of the system. The failure mode is indistinguishable from a board that is simply
quiet, which is the failure mode this whole project is built to avoid.

## Constants, and why these values

**Batch limit 500.** At 22 boards it never binds. It exists for the recovery
case: a scheduler waking after an outage finds every board overdue, and without
a cap it queues the entire registry in one tick — reintroducing the exact
stampede this design was chosen to avoid, through the recovery path. Longest
overdue first, so nothing starves under the cap.

**Board backoff: 15 minutes, doubling, ceiling 24 hours.** Distinct from
`http_backoff_base_seconds`, which handles one flaky response and is measured in
seconds; this handles a board that is gone. The ceiling matches the warm tier
deliberately — a dead board stops costing requests without falling out of the
system, so if it comes back it is noticed within a day. The exponent is capped
as well as the result, because `2 ** 500` is a fine Python integer and a useless
`timedelta`.

**Tick every five minutes.** The tick does not poll anything; it asks which
boards are due. A short tick is what turns "hourly" into "within five minutes of
hourly" while letting boards drift apart rather than synchronise, and it is what
makes per-board backoff expressible at a useful granularity.

## Consequences

**`next_poll_at` moves forward before the jobs run, not after.** A poll slower
than the tick would otherwise be enqueued again by the following tick, and again
by the one after — stacking jobs against a single provider, which is the retry
storm §7.3 forbids, self-inflicted.

The cost is that a *lost* poll waits one full interval rather than being retried
immediately. That is the right trade: a missed poll costs freshness on one
board, while a stacking loop costs the project its data supply.

**State lives in Postgres, not in the queue.** A worker restart loses queued
jobs and loses nothing else; the next tick re-derives what is due. This is also
what makes "which boards are overdue" a SQL query, which the coverage page
(`board-discovery.md` §11) needs anyway.

**Backoff is free rather than built.** A failing board pushes its own
`next_poll_at` out. Nobody disables it, it keeps its registry entry (A1 deletes
nothing), and it surfaces on the source health page ordered by how long it has
been silent.

**`max_jobs` stays at 1, and raising it is not free.** ADR 0007's point was to
make raising it a configuration change rather than a rewrite, and that holds.
But `PoliteClient`'s rate limiter is per process: two concurrent jobs against
one provider halve the spacing it enforces. The day this goes above 1, the
limiter has to become per-host and shared. That constraint is recorded as a
comment on the line somebody would actually change.

**A board with no state row is an error, not a no-op.** If a queued job names a
board that has no row, the queue and the registry disagree. Returning quietly
would drop that poll and every future one for that board, with nothing to show
for it.
