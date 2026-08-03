# ADR 0012 — One stage change, one representation

- **Status:** accepted
- **Date:** 2026-08-03
- **Milestone:** M2b
- **Overrides:** `PRODUCT-SPEC.md` §6.12's example list of event types

## Context

PRODUCT-SPEC §6.12 sketches `application_events` with an illustrative list of
event types. Most of them are stage names: `applied`, `rejected`,
`offer_received`, `withdrawn`, and so on.

Meanwhile the M2 design (`command-center.md` §3) requires every stage change to
record where it came from, where it went, and how the two relate — `advance`,
`correction` or `reopen`. That classification is the whole point of a machine
that does not block: history stays honest without the product telling its user
they are wrong about their own job search.

Put those two together and a single stage change has **two** representations.
Moving to `rejected` would write an event of type `rejected`, *and* an event
carrying `to_stage = rejected`. Nothing keeps them consistent. A bug that
writes one and not the other produces a history that contradicts itself, and
the contradiction is invisible until somebody reads both columns.

## Decision

**Eight event types. One of them is `stage_changed`, and no event type mirrors
a stage.**

```
saved                 stage_changed         note_added
detail_updated        interview_scheduled   archived
restored              listing_closed
```

A stage change is `stage_changed` with `from_stage`, `to_stage` and
`transition_class`. The stage vocabulary lives in exactly one place — the
`application_stage` enum — and the event type says what *kind of thing
happened*, not which stage it happened to.

Two database check constraints hold the shape:

- `to_stage IS NULL OR actor = 'user'` — invariant I5, so ingestion may record
  that a listing closed and may never move anybody's application.
- `to_stage` and `transition_class` are both null or both set — a destination
  with no classification is half a transition.

Nothing is listed that M2b does not write. `discovered` exists as a *stage*
because M3 will put roles there, but there is no `discovered` event type,
because no code writes one.

## Consequences

**One fact, one row, no way for two columns to disagree.** The client restates
both constraints in `applicationEventSchema`, so a bug in the API cannot render
a stage badge with no classification behind it.

**A §6.12-shaped query changes shape.** "Every rejection" is not
`event_type = 'rejected'`; it is `to_stage = 'rejected'`. That is one index away
and it is the query that stays correct when a stage is renamed.

**M7's Gmail classifications add their values with a migration**, when there is
code that writes them. Adding an enum value is a migration either way; adding
seventeen speculative ones up front is a migration *plus* a list of values that
nothing produces, which reads as functionality that exists.

**The cost is a small indirection when reading raw rows.** `SELECT event_type`
on a stage change says `stage_changed` rather than naming the outcome. The
outcome is in the next column.
