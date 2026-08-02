# Conditional polling — the M1d design

- **Status:** accepted
- **Date:** 2026-08-02
- **Milestone:** M1d (closes M1)
- **Implements:** ADR 0007, `board-discovery.md` §7
- **Corrects:** ADR 0007 in three places, recorded in §3

This document sequences ADR 0007 rather than re-deciding it. Where it departs
from that ADR it says so and says why, because two of the departures come from
measurements ADR 0007 explicitly asked for and never got.

Read `docs/architecture/board-discovery.md` §7 first for the decisions; this
file is what the implementation has to be true to.

---

## 1. What M1d delivers

M1 criterion 13 — *a `304 Not Modified` produces zero writes and closes zero
jobs* — is the only unclaimed criterion in the milestone. Everything here exists
to earn it honestly and to make the polling underneath it something that scales
past 22 boards.

1. Conditional requests (`If-None-Match`) on all three providers.
2. Greenhouse's two-phase poll: cheap listing, then per-posting content for
   what changed.
3. Per-board poll state in the database, including the stored ETag.
4. Queue-driven scheduling: one ARQ job per board, paced by `next_poll_at`.
5. Hot/warm tiers derived from ingested postings.
6. Lever and Ashby actually polled, which they are not today.
7. The `merge_jobs` row lock, which M1d is what makes reachable.
8. The 19 discovered boards promoted into the registry, by a `promote` that
   stops destroying the file's comments.

---

## 2. Measurements

Taken 2026-08-02 against live boards, because ADR 0007 was written from one
provider and this design turns on the other two behaving the same way.

### Conditional requests

Each board's own ETag was sent back to it in an `If-None-Match` header:

| Provider | Board | ETag served | Response to `If-None-Match` |
|---|---|---|---|
| Greenhouse | `datadog` | `W/"96ced7ed899bb76f1b2f37c3507e1e87"` | **304**, empty body |
| Lever | `alloy` | `W/"38d97-QpFUTsXivlu57d+bMruLaekfNgs"` | **304**, empty body |
| Ashby | `ramp` | `W/"job-board:291499f30d9689e05315b8db4c897f97e519651376402ebc7db8ddd8ec2a81cb"` | **304**, empty body |

**All three revalidate.** ADR 0007 said "Verified on Greenhouse. Ashby and Lever
must be checked when their adapters are built," and provided for a provider that
could not. No such fallback is needed.

### Response sizes and shapes

| Request | Bytes | Compressed | Carries descriptions? |
|---|---:|---|---|
| Greenhouse `/jobs` (listing) | 33,442 | gzip | **No** |
| Greenhouse `/jobs?content=true` | 498,760 | gzip | Yes |
| Greenhouse `/jobs/{id}` | 4,852 | gzip | Yes |
| Lever `/v0/postings/{token}?mode=json` | 232,855 | **none** | Yes |
| Ashby `/posting-api/job-board/{token}` | 220,891 | gzip | Yes |

Three things follow.

**Greenhouse's listing is 14.9× cheaper than its content fetch** on this board
(ADR 0007 measured 31× on `6sense`; both are large, and the ratio varies with how
long a board's descriptions are). Every figure in the table above was measured
on `datadog` for this design — ADR 0007's numbers are a different board and are
not mixed in. The listing carries `id`, `updated_at`,
`first_published`, `location`, `title` and `absolute_url` — everything the
freshness pass needs and nothing it does not.

**Lever and Ashby return the complete posting in the board request.** Lever's
first `alloy` posting carries 6,373 characters of `description`; Ashby's first
`ramp` posting carries 7,332 of `descriptionHtml`. There is no cheaper listing
endpoint and no per-posting endpoint to escalate to.

**Lever does not compress.** It sent 232,855 bytes with no `Content-Encoding`
despite being offered gzip. A Lever `200` is the most expensive response this
system takes, which makes its `304`s the most valuable.

### Greenhouse's per-posting payload

`GET /v1/boards/datadog/jobs/7194969` was compared key-by-key and value-by-value
against the same posting inside `?content=true`:

```
only in single   : []
only in list     : []
differing values : []
```

**Identical.** Phase 2 therefore reuses `GreenhouseAdapter.normalize` unchanged.
This matters more than it looks: a second normalization path is a second place
for the location parser to drift, and I1 failures have come from exactly that
kind of divergence three times in this project already.

---

## 3. Where this corrects ADR 0007

**Two-phase polling is a Greenhouse mechanism, not a general one.** ADR 0007
describes phase 2 — "fetch `/jobs/{id}` for new or changed postings only" — as
the shape of every poll. For Lever and Ashby a `200` already contains
everything, so there is nothing to escalate to and phase 2 does not exist. Their
poll is: `304`, or a `200` that is complete.

**The "no `updated_at` on Lever and Ashby" problem dissolves.** `docs/PROGRESS.md`
records this three times, most recently as *"the most consequential"* finding
carried into M1d: ADR 0007's phase-2 diff needs a timestamp to compare and
neither provider publishes one. True, and irrelevant — the diff exists to decide
what to fetch, and for those providers there is nothing left to fetch. No
description-hash fallback is needed for change *detection at fetch time*. The
existing `description_hash` comparison inside `persist_source_job` continues to
decide `updated` versus `unchanged` after the fact, exactly as it does today.

**No provider needs an ETag fallback.** ADR 0007 provided for a provider without
ETags falling back to fetching the listing. Unused; all three revalidate.

Nothing else in ADR 0007 changes. Tiers, intervals, the rejection of a weekly
tier, queue-driven polling, and the ban on `content=true` for routine polls all
stand.

---

## 4. Listed is not fetched

**This is the defect the design exists to prevent, and it is created by ADR 0007
itself.**

`apply_freshness` decides a posting is absent by `last_seen_at < now`: a record
the current run did not write was not in the response. Persisting a posting sets
`last_seen_at = now`, so anything older is missing. Three misses and seven
elapsed days close it (ADR 0009).

Phase 2 fetches only postings that changed. So an unchanged posting is never
persisted, its `last_seen_at` stays old, and `apply_freshness` counts it as
missing. **Every unchanged posting on every Greenhouse board would take a miss
on every poll, and close on the third.** Nothing raises an error. The damage
appears three polls after the change that caused it — the same delayed shape the
M1b review named when it moved a closure assertion from the job's status onto
the miss counter.

The model must therefore separate two facts a single `jobs` tuple currently
conflates:

| | Meaning | Source | Used for |
|---|---|---|---|
| **listed** | the posting appeared in the board listing | phase 1, always complete | freshness — this is what "still open" means |
| **fetched** | we pulled its full content because it changed | phase 2, deliberately partial | normalization and persistence |

`FetchOutcome` gains `listed_source_job_ids: tuple[str, ...]`. `apply_freshness`
ages records against that set rather than against "what this run wrote".
`persist_source_job` continues to run over `jobs`.

For Lever and Ashby the two sets are equal, and a test asserts that equality
rather than leaving it to coincidence.

A `304` sets `listed_source_job_ids = ()` **and** `not_modified = True`, which
§5 explains is not the same as an empty board.

---

## 5. What a `304` means

A `304` says the listing is byte-identical to the one we already parsed. The
tempting conclusion — "so every posting is still open, refresh them all" — would
write thousands of rows to save one request and defeat the entire mechanism.

**A `304` touches no job-state row.** No records aged, no misses incremented, no
closure decided, no embeddings computed, no locations rewritten. Closure requires
misses; misses require a `200` listing that omits the posting. A board that sits
unchanged for a year closes nothing, which is I3 holding at the level ADR 0007
introduced.

### The criterion, stated precisely

Criterion 13 says "zero writes". A `304` does write one row — the board's own
`board_poll_state` (`last_polled_at`, `next_poll_at`, `consecutive_failures`
reset). That is the bookkeeping that makes polling work, not a claim about any
job.

So the criterion is claimed as **zero writes to job state**, and tested as: no
`INSERT` or `UPDATE` against `source_job_records`, `jobs`, `job_locations`,
`job_source_links`, `job_status_events`, or `job_embeddings`; no
`consecutive_misses` movement anywhere; no `job_status` transition. Stating it
this way rather than as a bare "zero writes" is the difference between a
criterion that can be verified and one that quietly cannot.

### A live bug this exposes

`FetchOutcome.is_authoritative_empty` is currently `self.ok and not self.jobs`.
A `304` is a success carrying no jobs. Under that definition it reads as *"this
board authoritatively has no postings"* — which is the single most destructive
sentence in this system, and ADR 0007 warned about it in the abstract before the
code existed to make it concrete.

Two changes, belt and braces:

1. `is_authoritative_empty` becomes `ok and not not_modified and not jobs`.
2. A model validator refuses to construct a `FetchOutcome` with
   `not_modified=True` alongside a non-empty `jobs` or `listed_source_job_ids`.

The first is the fix; the second means a future adapter cannot express the
confusion at all.

---

## 6. `board_poll_state`

One row per board, keyed `(ats, token)`. The registry YAML stays the declarative
source of what boards exist; this table is what polling *knows* about them, and
the name is chosen so the two cannot be confused.

| Column | Type | Why |
|---|---|---|
| `ats`, `token` | text, unique together | The board identity used everywhere else |
| `source_id` | FK → `sources` | Which provider row this polls under |
| `etag` | text, null | The last ETag the provider served |
| `parser_version` | text | ADR 0007: a stored ETag is only valid for the parser that earned it |
| `tier` | PG enum `hot \| warm` | §8 |
| `next_poll_at` | timestamptz, indexed | The scheduler's only query |
| `last_polled_at` | timestamptz, null | Includes `304`s |
| `last_success_at` | timestamptz, null | `200` or `304`; a failure does not move it |
| `last_status` | int, null | HTTP status, for the health page |
| `last_error` | text, null | Cleared on success |
| `consecutive_failures` | int, default 0 | Drives backoff (§7) |

`parser_version` is a constant in the adapter module, bumped by hand when
normalization changes. On read, an ETag whose `parser_version` differs from the
adapter's current value is discarded and the poll proceeds unconditionally. This
is the guard against the failure ADR 0007 names: a changed parser plus a stale
ETag means the new parser never sees the payload it was written for.

**Freshness display reads from here, not from each posting.** A board that `304`s
for sixty days leaves its postings' `last_seen_at` sixty days old. Those postings
are open and correctly so — no misses were taken — but any UI computing "how
fresh is this?" from `last_seen_at` alone would call them stale. "When did we
last successfully hear from this board" is `last_success_at` on this row.

---

## 7. Scheduling

Considered and rejected: two crons, one per tier, each enqueueing its whole tier.
It is what ADR 0007 literally describes and the least machinery, but every board
in a tier fires in the same instant and per-board backoff has nowhere to live.
Also rejected: each poll enqueueing its own successor — elegant, and one lost
job silently stops polling a board forever with nothing to notice.

**Chosen: `next_poll_at` on the board row, drained by a small cron.**

```
every 5 minutes:
    SELECT ... FROM board_poll_state
     WHERE next_poll_at <= now()
     ORDER BY next_poll_at
     LIMIT 500
    -> enqueue poll_board(ats, token) for each

poll_board(ats, token):
    poll (§4, §5)
    on 200 or 304:  next_poll_at = now() + (1h if hot else 24h)
                    consecutive_failures = 0
    on failure:     next_poll_at = now() + min(15min * 2**failures, 24h)
                    consecutive_failures += 1
```

The two constants above are chosen rather than inherited, so they are stated
here rather than left to the implementation:

- **`LIMIT 500`** caps how many boards one tick may enqueue. At 22 boards it
  never binds. It exists so that a scheduler waking after an outage, with every
  board overdue, drains in several ticks instead of queueing the entire registry
  at once — the thundering herd this design chose `next_poll_at` to avoid,
  reintroduced by the recovery path if nobody caps it.
- **Board backoff is 15 minutes doubling to a 24-hour ceiling**, separate from
  `PoliteClient`'s per-request retry backoff, which handles a single flaky
  response and is measured in seconds. This one handles a board that is simply
  gone. The ceiling is 24 hours so a board that comes back is noticed within a
  day, matching the warm tier — a dead board and a slow board converge on the
  same rate rather than the dead one falling out of the system.

Four properties this buys:

1. **Load spreads.** Boards drift apart naturally instead of stampeding at `:00`.
2. **Backoff is free.** A dead board pushes itself out without anyone disabling
   it, and stops costing requests. It keeps its registry entry (A1 deletes
   nothing) and surfaces on the health page.
3. **"What is overdue" is a query.** The coverage page (`board-discovery.md`
   §11) already needs "how many boards were polled in the last hour"; this is
   the same row.
4. **It survives a restart.** State is in Postgres, not in the queue.

The cost is that "hourly" becomes "within five minutes of hourly", which is well
inside a product promise measured in days.

Rate limiting stays where it is — per-provider-host in `PoliteClient`. Adding
boards never raises the rate against any one provider, which is the property that
makes §10 of `board-discovery.md` a worker-count question.

---

## 8. Tiers

| Tier | Membership | Interval |
|---|---|---|
| `hot` | the board has an open NYC posting, or had one seen in the last 30 days | 1 hour |
| `warm` | every other pollable board | 24 hours |

Derived from ingested postings via `job_locations`, never from `nyc_presence` in
the registry YAML. A board is hot because of what its postings said.

Recomputed at the end of that board's own poll. That is also what demotes: a
board whose last NYC role closes drops to `warm` on its next poll, thirty days
later. Both directions get a fixture, because a tier that can only be entered is
a tier that eventually contains everything.

`nyc_presence` in the registry is now decorative for polling purposes.
`board-discovery.md` §16 anticipated its deletion once tiers are computed; M1d
leaves the field in place but adds a test asserting nothing in the polling path
reads it, so the deletion is a later cleanup rather than a behaviour change.

---

## 9. Carried debt fixed here

**The `merge_jobs` row lock.** Named in the M1b review as the one thing M1d must
not inherit unnoticed, and M1d is precisely what makes it reachable: with
per-board jobs running concurrently, two workers can each decide postings A and B
are duplicates and each delete the other's survivor. `SELECT ... FOR UPDATE` on
both job rows in a deterministic order (by primary key, so two workers acquiring
the same pair cannot deadlock), with the losing worker re-reading and finding the
merge already done.

**`promote` destroys the registry's comments.** Its docstring says "Additive,
never destructive." In the data sense that is true — verified semantically:
promoting 19 boards left all four existing entries identical, re-enabled nothing.
But it rebuilds the file with `yaml.safe_dump`, preserving only the leading
comment block, and the first real `--write` in this project's history deleted ten
lines of human-written rationale from between the entries — including the note on
the `Stripe` entry reading *"enable once the freshness and closure state machine
lands"*, which is a message to M1d, deleted by approving unrelated boards.

M1c could not have caught this: it deliberately never wrote to the registry and
cited byte-identity as evidence of restraint. Fixed by appending rendered entries
to the existing text rather than re-serializing the document, which also ends the
`added: '2026-08-02'` versus `added: 2026-07-29` quoting split the round-trip
introduced. The diff a human reviews becomes purely additions, which is what
ADR 0005's batch approval assumes it is reviewing.

**The registry closed-set guard.** `test_the_pollable_set_is_exactly_these_three_boards`
enumerates every pollable board so nothing goes live without a deliberate edit.
It fired correctly on all 19 new boards. Enumeration does not survive a registry
meant to grow into the thousands, and deleting the guard would remove the only
thing standing between a hand-disabled board and live polling. Replaced by:

- the four hand-curated boards keep an exact expected set, so `Stripe` flipping
  to `active` still fails loudly;
- every *other* pollable board must carry provenance in `notes` naming ADR 0005,
  so a board hand-added with no approval trail fails.

**Not fixed, and still recorded as debt:** the mass-failure signal for a
discovery sweep, and `cmd_validate`'s per-board rewrite of the candidate file.
Both were considered for this milestone and deliberately left out.

---

## 10. The registry, filled

The 19 boards M1c validated and withheld are promoted here, by the fixed
`promote`. That takes the pollable set from 3 to 22 and gives the scheduler,
the tiers and the rate limiter real traffic rather than fixtures alone.

The two `Abridge` candidates stay withheld — one employer, two live Ashby
tokens, and which to poll is a human's call under ADR 0005. The two `empty`
boards stay held.

Lever and Ashby become genuinely polled. `workers/tasks.py` and `cli.py` both
hard-filter `pollable(ats="greenhouse")` today, so the registry's `active` on
those boards has meant "eligible once M1d ships a poller". That gap is listed in
PROGRESS under "Not real yet" and M1d is where it closes.

---

## 11. Testing

Fixtures, committed, recorded from real responses — no hand-written HTTP.

**The two that carry the criterion:**

- A `304` produces zero writes to job state. Asserted by counting rows and
  reading `consecutive_misses` before and after, not by inspecting a log line.
  Mutation check: making `not_modified` fall through to the normal empty-listing
  path must fail it.
- A `304` is not an authoritative empty board. Mutation check: reverting
  `is_authoritative_empty` to `ok and not jobs` must fail it.

**The one that carries §4:**

- A Greenhouse board where one posting changed and nine did not: the nine take
  no miss, are not re-persisted, and are not re-embedded; the one is updated.
  Mutation check: aging against the fetched set instead of the listed set must
  close the nine. This is the test the whole design turns on.

**The rest:**

- Lever and Ashby: `listed_source_job_ids` equals the ids in `jobs`.
- A stored ETag under a stale `parser_version` is discarded and the poll proceeds
  unconditionally.
- Tier promotion and demotion, both directions.
- Backoff: a failing board's `next_poll_at` moves out and its jobs are untouched
  (I3, again, now at board level).
- The scheduler enqueues only due boards, and enqueues a board at most once.
- `merge_jobs` under two concurrent transactions leaves one survivor with both
  source links.
- `promote` preserves every comment in the registry file, asserted against a
  fixture registry that has comments between entries.

---

## 12. Deliberately not built

- **A mass-failure signal for discovery sweeps.** M1c's top carried weakness.
  Decided out of scope for M1d; still recorded.
- **Batched candidate-file writes.** Only bites above a few hundred candidates.
- **Webhooks.** No provider offers them.
- **A weekly tier.** ADR 0007 rejected it and this design does not revisit it:
  daily on the long tail is what keeps "the day of" true for a company posting
  its first NYC role.
- **Distributed workers, sharding, multi-region.** `board-discovery.md` §10 lists
  the complete set of things being done for a future that may not arrive, and
  this is not on it.
