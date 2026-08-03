# M1d review — conditional polling

**Date:** 2026-08-03
**Branch:** `m1d-conditional-polling`, eleven tasks, commits `6e516cf`…`d3738b6`
**Scope:** `PoliteClient.get_json_conditional`, `FetchOutcome`, all three
adapters, `domain/ingestion.py`, `domain/polling.py`, `domain/tiers.py`,
`board_poll_state`, two migrations, `GET /boards`, `/operate`, the registry.

At close: **804 Python tests** (from 607 at branch start), 42 web unit, **20
seeded browser tests** (from 16). `make check` green, `make acceptance` green,
migrations round-tripped in both directions against a live cluster.

This review looks for what the design named — a `304` that writes something, a
board enqueued twice, a tier that can only be entered, retry storms from the
scheduler, a stored ETag outliving a parser change, lock ordering — plus what
actually went wrong.

---

## 1. What the milestone claims, and the evidence

| M1 criterion | Status | Evidence |
|---|---|---|
| 13 — A `304 Not Modified` produces zero writes and closes zero jobs | **Verified** | Two consecutive live polls of `datadog`. Poll 1: `200`, 429 created, ~16 min. Poll 2: `304`, 0 created, 0.009 s. Job state byte-identical across all eight measures — 460 records, 446 jobs, 676 locations, 460 links, 0 status events, 446 embeddings, 0 misses, 0 closed. Plus `test_a_304_writes_no_job_state` at pipeline and poll-cycle level, mutation-checked |

**M1 is complete.** Fifteen of fifteen criteria verified.

### How criterion 13 is claimed, precisely

"Zero writes" is imprecise and was worth pinning down. A `304` *does* write one
row: the board's own `board_poll_state` bookkeeping, which is the point of
polling and not a claim about any job.

What is asserted is **zero writes to job state** — no insert or update against
`source_job_records`, `jobs`, `job_locations`, `job_source_links`,
`job_status_events` or `job_embeddings`; no miss-counter movement; no closure.
`_job_state_snapshot` is that assertion, and it includes the miss sum and the
closed count deliberately: a regression that increments every miss counter
changes no row count at all, and the damage lands three polls later.

---

## 2. The named risks

**A `304` that writes something.** Closed at four levels: the adapter returns
`not_modified` with no postings, a model validator refuses a `not_modified`
outcome carrying any, `ingest_boards` keeps such a board out of `boards_listed`
so freshness cannot age it, and `poll_one_board` skips the tier recompute. The
live evidence above is the fifth.

**A board enqueued twice.** `next_poll_at` is pushed forward *before* the jobs
run. A poll slower than the five-minute tick would otherwise be re-enqueued by
the following tick and the one after, stacking jobs against one provider. The
cost — a *lost* poll waits a full interval — is the deliberate trade, recorded
in the docstring and in ADR 0011.

**A tier that can only be entered.** Both directions tested. A board whose only
NYC posting closed more than 30 days ago demotes; one that closed last week does
not, because an employer who hired in New York last week will very likely hire
there again.

**Retry storms from the scheduler.** Three guards: the batch cap (500) for the
recovery case where every board is overdue at once, longest-overdue-first
ordering so nothing starves under that cap, and per-board backoff so a dead
board stops costing requests. `PoliteClient`'s per-host limiter is unchanged and
still the thing that bounds request rate.

**A stored ETag outliving a parser change.** `parser_version` is stored beside
the ETag and compared before it is sent; a mismatch discards it and polls
unconditionally. This is the failure that would otherwise be *invisible* — the
provider keeps answering `304`, the board looks perfectly healthy, and the new
parser never sees the payload it was written for. Two tests, one asserting the
stale ETag is not sent and one asserting a current one is, both checking what
reached the client rather than only what was stored.

**Lock ordering in `merge_jobs`.** See §3.4 — reproduced before fixing.

---

## 3. What actually went wrong

**Fourteen defects. Ten were in code that reported success.** That is the same
pattern M1a, M1b and M1c each recorded — now four milestones running, and this
time the sharpest instance was self-inflicted.

### 3.1 The pipeline had never been tested against Greenhouse

After Task 4 made Greenhouse two-phase, `ingest_boards` still read only
`outcome.jobs` — which phase 1 deliberately no longer populates. **Live
Greenhouse ingestion produced zero jobs and the suite stayed green.**

The reason: every ingestion, closure, merge and route test drove a
`_StubAdapter` wrapping *Lever*, handed a `FetchOutcome` the test built itself.
The pipeline had never once seen a Greenhouse-shaped response, and outcomes
constructed by tests cannot disagree with what adapters actually return.

I predicted the suite would fail and it did not. The green run was the finding.

### 3.2 The same footgun three times, so the type was changed

A `FetchOutcome` carrying postings but no `listed` set reads to freshness as a
board that listed nothing — which ages every record and closes the board three
polls later, silently. That mistake was made in the fixture adapters, and in two
pipeline test stubs.

Fixed at the type rather than the call sites: `listed` now derives from `jobs`
when none is given. A posting we hold the content of was self-evidently on the
board. Two-phase providers pass `listed` explicitly and are unaffected.

### 3.3 `make seed` would have crashed

`FixtureGreenhouseAdapter` subclasses the real adapter and inherited
`is_two_phase = True`, along with a `fetch_full_board` that reaches for an HTTP
client the fixture adapter deliberately does not have. **The offline demo path,
broken by inheritance.**

The fixture adapters had **no tests at all** — the thing that makes `make demo`
work was untested. There are now 24, and the real path was verified rather than
inferred: two consecutive `make seed` runs leave 31 jobs open, zero misses.

### 3.4 A real deadlock, reproduced before fixing

The M1b review named the missing `merge_jobs` row lock as the one thing M1d must
not inherit unnoticed. Reproduced:

```
DeadlockDetectedError: deadlock detected
Process 3614 waits for ShareLock on transaction 1931; blocked by process 3615.
Process 3615 waits for ShareLock on transaction 1930; blocked by process 3614.
```

Fixed by locking both rows in primary-key order. **The ordering prevents the
deadlock rather than detecting it** — locking in the caller's order lets each
worker hold the row the other wants. Acquired as two statements rather than one
`IN` clause with `ORDER BY`, because a single statement's lock acquisition
follows the query plan and is not guaranteed to follow the sort.

Mutation-checked as a race must be: the caller's order reproduces the deadlock
on 3 of 3 runs; the fix passed 8 consecutive runs. One green run proves nothing
about a race.

### 3.5 `promote` was destructive in everything a human had written

Found by running `--write` for the first time in the project's history. It was
additive in the *data* and deleted ten lines of rationale between the entries —
including the note on `Stripe` reading *"enable once the freshness and closure
state machine lands"*, a message to this milestone, deleted by approving
nineteen unrelated boards. `_leading_comment` had saved the header, so the
limitation was known; only the consequence was not.

M1c could not have caught it: that milestone deliberately never wrote and cited
byte-identity as evidence of restraint.

Now literally appended, asserted as `after.startswith(before)`.

### 3.6 Structural typing did the wrong thing quietly

`isinstance(adapter, TwoPhaseJobSourceAdapter)` matches on method *names* only,
so a single-phase Lever stub that implemented them for convenience was dragged
into a phase Lever has no endpoint for. The pipeline now gates on the
`is_two_phase` flag and *then* narrows; an adapter claiming two phases without
implementing them raises rather than silently ingesting nothing.

### 3.7 The rest

- **A `304` is not an authoritative empty board.** `is_authoritative_empty` was
  `ok and not jobs`, which a `304` satisfies — "every posting on this board is
  gone", from a provider behaving perfectly.
- **httpx counts only 2xx as success and `304` is not retryable**, so a naive
  conditional client falls through to the terminal-failure branch and records an
  outage.
- **Autogenerate emitted `nightshift.db.types.UTCDateTime` with no import** —
  a `NameError` at upgrade time. Second migration running that the note at the
  head of `0002` has caught, which is why `0004` was written by hand.
- **`jobs.source_updated_at` already existed and reusing it would have been
  wrong.** After a merge one job carries records from several boards and its
  timestamp reflects whichever wrote last, so the phase-2 diff would refetch
  what had not changed and skip what had.
- **Eleven route tests were *errors*, not failures**, on a fourth `_StubAdapter`
  copy. Errors read as noise; failures read as signal.
- **`2 ** 500` is a fine integer and a useless `timedelta`.** Backoff caps the
  exponent, not just the result.
- **Two of my own tests grepped module source** for `nyc_presence` and borough
  names, and failed on the docstrings explaining why neither belongs in the
  code. A test that greps prose punishes documenting the rule. They now parse
  the module and strip docstrings.
- **Two browser tests read `innerText` without waiting** for an async query,
  so they passed or failed on timing rather than content.

### 3.8 What the existing guards caught

Worth recording separately, because these are controls earning their keep:

- `test_repo_integrity` — added in M1c after `.gitignore` swallowed a route —
  caught `polling.py` and `tiers.py` before they were staged. A stricter
  guarantee than it was written for.
- `conftest`'s no-CASCADE truncate refused `board_poll_state` until it was
  listed. Third milestone running.
- The `job_merge_events` append-only trigger refused a test's cleanup `DELETE`.
  The right answer was to stop deleting, not to weaken the trigger.
- The `jobs` check constraint refused a `closed` job with no `closed_at`.
- The registry closed-set test refused all 19 new boards until deliberately
  reshaped.

---

## 4. Weaknesses carried forward

Ranked.

1. **`max_jobs` is still 1, and raising it is not free.** `PoliteClient`'s rate
   limiter is per process, so two concurrent jobs against one provider halve the
   spacing it enforces. The queue-driven design makes raising it a config change
   rather than a rewrite, but the limiter must become per-host and shared first.
   Recorded as a comment on the line somebody would change.
2. ~~**The scheduler has never run for real.**~~ **Verified after this review
   was first drafted.** `enqueue_due_boards` was run against the live Redis:
   22 boards synced, 22 `poll_board` jobs on the queue with correct arguments,
   and a second tick immediately afterwards enqueued **zero** — which is the
   double-enqueue guard working, since `next_poll_at` moves forward before the
   jobs run. What remains unexercised is an ARQ *worker* consuming those jobs;
   the poll cycle they invoke has run live twice through the CLI.
3. **No mass-failure signal**, deliberately out of scope. A provider changing its
   envelope classifies every board `unreachable` and nothing shouts. Carried from
   M1c.
4. **`cmd_validate` still rewrites the candidate file per board.** O(n²) at
   scale. Carried from M1c.
5. **Only `datadog` has been polled conditionally against a live provider.** The
   `304` path is proven on Greenhouse; Lever and Ashby were verified to *serve*
   `304` during design, but their adapters' conditional path has been exercised
   only against fixtures.
6. **`nyc_presence` still exists in the registry.** Nothing in the polling path
   reads it — asserted by a test that inspects code with docstrings stripped —
   so deleting it is now a cleanup rather than a behaviour change.
7. **The dedupe threshold got its first real-world data point and nobody acted
   on it.** The live Datadog poll merged two postings on `similar_description` at
   0.864, against a 0.85 threshold derived from three labelled pairs. One
   observation is not a calibration, but it is the first evidence from outside
   the labelled set and it landed close to the line.

---

## 5. What was deliberately not built

- **The mass-failure signal** and **candidate-file batching**, both by explicit
  decision when M1d's scope was set.
- **A weekly tier.** ADR 0007 rejected it and the `BoardTier` closed-set test is
  where that decision now lives.
- **Concurrency above one worker.** See §4.1.
- **Any change to `PoliteClient`'s rate limiter.** It is correct for one worker
  and the milestone did not need it to be more.

---

## 6. Verdict

Criterion 13 is met with live evidence rather than fixture evidence: two polls
of a real board, one `200` and one `304`, with job state byte-identical across
eight measures either side of the `304`.

The honest summary is that **the milestone's own optimisation was its biggest
risk, and the tests that should have caught it were all pointed at the wrong
provider.** ADR 0007's phase 2 creates a silent mass-closure bug by design, and
the pipeline's entire test suite drove one provider's shape through a stub. Both
are now fixed, and the second was only visible because a green run contradicted
a prediction.

Two things written down turned out to be wrong and are corrected in place: phase
2 is Greenhouse-only, and the "no `updated_at` on Lever and Ashby" problem this
project recorded three times as M1d's most consequential inheritance dissolved
once someone measured the payloads.

M1d is complete. **M1 is complete.**
