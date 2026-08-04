# ADR 0014 — Queue membership comes from current state; only activity comes from history

- **Status:** accepted
- **Date:** 2026-08-04
- **Milestone:** M2d
- **Relates to:** ADR 0012 (event types are not stage names), `command-center.md` §7.2

## Context

The daily queue answers four questions by reading data two other milestones
wrote. Two of those questions are about *state* — is this listing closed, is
this application still at `saved` — and two are about *time since something
happened*.

`application_events` is append-only, complete, and indexed. That makes it the
obvious source for all four, and for two of them it is the wrong one.

The specific temptation: "closed while you were tracking it" has an event that
means exactly that. `record_listing_closed` writes a `listing_closed` row when
the poller stops seeing a posting, so the section is one join and no ambiguity —
`EXISTS (SELECT 1 FROM application_events WHERE event_type = 'listing_closed')`.

It is wrong because **a listing can close and reopen**. §7.4's closure state
machine allows it, `job_status_events` records both directions, and a reopened
role's `listing_closed` event never stops being true — it *was* true when it was
written, and an append-only log is not permitted to unsay it. So the section
would accumulate roles forever and tell the user to act on something that had
stopped being the case. Nothing would error. The row would look exactly like a
correct one.

The same reasoning runs the other way for the two time questions. "When did this
person last touch this application?" has no column anywhere; the events *are*
the answer, and there is no alternative source to prefer.

## Decision

**Membership in a queue section is computed from current state. History is read
only to answer questions that are about history.**

Concretely, in `domain/queue.py`:

| Section | Source | Why that one |
|---|---|---|
| Closed while saved | `jobs.status = 'closed'` | A reopened listing leaves the section by itself |
| Stale saved | `applications.current_stage = 'saved'` for membership, events for the date | The stage is the state; "how long" is history |
| Follow up | `applications.next_action_at` and `current_stage`, events for silence | Same split |
| Interviews approaching | `application_events.occurred_at` | An appointment *is* an event; there is no state column for it, and M2b's model docstring already recorded that `occurred_at` may be in the future for exactly this |

And the corollary that makes the history half honest:

**Only `actor = 'user'` counts as activity.** `application_events` holds system
rows, and `record_listing_closed` writes one. If a system event counted as the
person touching their application, a listing going closed would make that
application look freshly handled and drop it out of the queue that exists to
surface it. The queue would go quiet at precisely the moment it had something to
say. `_last_user_activity()` carries that filter and
`test_a_system_event_does_not_count_as_activity` fails when it is removed.

## Consequences

**A section empties itself when the world changes back.** That is the point, and
it is asserted by `test_a_reopened_listing_leaves_the_queue`, which writes the
`listing_closed` event, flips the job back to `open`, and requires the row to be
gone.

**Two partial indexes**, both on `application_events` (migration `0010`). The
existing `(application_id, occurred_at)` index serves neither queue question:
`actor` is not in it, and the interview scan has the wrong leading column.

**This is a general rule and M3 will meet it immediately.** A `match_result` row
is a fact about a scoring run, not a fact about the job — when the ruleset
version changes, old results stay true about the run that produced them and stop
being true about the role. Anything that asks "should this be in front of the
user right now" reads current state; the history explains *why*, and is not the
membership test.

## Alternatives considered

**Read the closure event and check for a later reopen event.** Correct, and it
requires knowing every event type that could undo every other one — a rule set
that grows with the enum and is wrong silently when somebody adds a member. The
job's status column already is that computation, maintained by the closure state
machine, which is the thing that owns it.

**Materialise a `queue_state` table, refreshed by the worker.** Faster to read
and a second copy of the truth. With one user and a few thousand jobs it is
solving a problem this project does not have (`CLAUDE.md` §8), and a stale
refresh is the same class of lie this ADR exists to prevent.

**Count every event as activity, system rows included.** Simpler by one line and
wrong in the direction that hides work from the user. Rejected, with a test that
fails if somebody simplifies it back.
