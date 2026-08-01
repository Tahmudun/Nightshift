# The canonical spine — dedupe, freshness, closure

> Design for M1b. Read before touching `domain/dedupe.py`, `domain/freshness.py`,
> or any code that writes `jobs.status`.
>
> Companion documents: `docs/architecture/board-discovery.md` (M1c/M1d — where
> the jobs come from), ADR 0009 (closure thresholds), ADR 0010 (dedupe layers
> and the similarity threshold).

---

## 1. What this subsystem is for

M1a made three providers deliver raw postings through one interface. Every raw
posting still becomes exactly one canonical job, linked with
`match_confidence=1.0` and `link_reason='sole_source_record'` — a claim about
provenance, not about identity. Nothing can close a listing; `jobs.status` only
ever holds `open`.

M1b closes both gaps:

- **Identity.** One real-world opening is one `job` row, however many boards
  describe it.
- **Life cycle.** A job that goes away stops being presented as available,
  without an outage ever being mistaken for a closure.

The two are entangled, which is why they are one milestone: a job with two
source records is only gone when *both* of them stop listing it, so closure
cannot be specified until identity is.

## 2. The shape of the data, and why it already fits

The M0 schema anticipated this milestone. Nothing here required inventing a
new place to put state:

| Existing column | Role in M1b |
|---|---|
| `source_job_records.consecutive_misses` | Miss counter, per raw record |
| `source_job_records.last_seen_at` | Last time the board listed it |
| `source_job_records.last_verified_at` | Last time *the posting's own endpoint* confirmed it (M1d fills this; null now) |
| `source_job_records.source_status` | What the source last said about this record |
| `jobs.status` | The four-state machine below |
| `jobs.closed_at` | Paired with `status` by a check constraint |
| `jobs.last_seen_at` | Derived: the max over the job's live source records |
| `job_source_links` | Unique per (job, record); a merge adds an edge |

Three tables are new. They exist because the invariants require an audit trail
that the columns above cannot carry:

- `job_status_events` — append-only, one row per transition.
- `job_embeddings` — one vector per canonical job, with model name and
  dimension (AMENDMENTS A5).
- `job_merge_events` — one row per merge, with enough detail to undo it.

## 3. Closure

### 3.1 The states

```
                    board answered, job absent x3
        open ──────────────────────────────────────► possibly_stale
          ▲                                                │
          │                                                │ and 7+ days
          │ job reappears on any of its sources            │ since last seen
          │                                                ▼
          ├──────────────────────────────────────────── closed
          │
          │ board answered again
          │
      unverified ◄──── no successful poll of this board for 14 days
```

`possibly_stale` and `unverified` are not two words for the same doubt:

- **`possibly_stale`** — the board answered, and this job was not in the
  answer. That is real evidence about the job.
- **`unverified`** — the board has not answered at all. That is evidence about
  *the source*, and none whatever about the job.

Keeping them apart is what makes I3 checkable rather than aspirational. A
source outage moves jobs to `unverified`, which the UI presents as "we cannot
currently check this", and no amount of time in that state ever leads to
`closed`. Only the `possibly_stale` path reaches closure.

### 3.2 Thresholds, and why they are a pair

Closure requires **3 consecutive misses AND 7+ days since `last_seen_at`**. Both,
not either. See ADR 0009 for the full argument; the short version is that a
miss count alone means nothing once the poll rate varies. M1d introduces an
hourly `hot` tier and a daily `warm` tier, so "3 misses" is three hours on one
board and three days on another. The elapsed-time condition is what makes the
rule mean the same thing regardless of cadence, and the miss count is what
stops a single successful-but-anomalous poll from starting the clock.

### 3.3 The three rules that carry I3

1. **A failed fetch changes nothing.** Not `status`, not `consecutive_misses`,
   not `last_seen_at`. `FetchOutcome(ok=False)` is already the type-level
   distinction (ADR 0003); freshness simply never runs on one.
2. **An authoritative empty board is evidence.** A live board returning `[]`
   really does say its postings are gone. M1a recorded the `plaid` empty board
   as a separate fixture from the `ramp` 404 precisely so this branch has a
   test.
3. **A job is missing only when every one of its source records is missing.**
   After dedupe a job may be described by a Greenhouse posting and a Lever
   posting. One board dropping it is not the job closing.

### 3.4 Reopening

A closed job that reappears goes back to `open` and `closed_at` returns to
null. Reposts are ordinary — companies pause and re-publish listings — and
refusing to reopen would leave the system permanently wrong about a job that is
demonstrably available.

The history is not lost, because it never lived in the `status` column. Every
transition is a row in `job_status_events`, so "this job closed on the 3rd and
reopened on the 11th" remains answerable after the fact. Without that table,
reopening would silently erase the evidence that a closure ever happened, and
I6's standard of evidence would have nothing to point at.

### 3.5 When it runs

At the end of each ingestion run, inside the same transaction. Freshness is a
function of what a poll observed, so it belongs where the observation is —
not on a separate schedule that could run while a poll is half-finished.

## 4. Dedupe

### 4.1 Blocking: comparisons happen within one company

Candidate pairs are drawn only from the same `company_id`. This is a
correctness rule before it is a performance one — merging across employers is
never right — and it also keeps the comparison count trivial at this volume.

### 4.2 The layers

Evaluated strongest-first; the first that fires decides, and records its reason
and confidence on the `job_source_links` row.

| # | Rule | Confidence | `link_reason` |
|---|---|---|---|
| 1 | Same canonical URL, after normalisation | 1.0 | `same_canonical_url` |
| 2 | Same company + same normalized title + shared location + identical `description_hash` | 0.99 | `identical_content` |
| 3 | Same company + same normalized title + shared location + description similarity ≥ threshold | scaled from similarity | `similar_description` |
| — | otherwise | — | distinct jobs |

URL normalisation strips tracking parameters (`utm_*`, `gh_src`, `ref`),
lowercases the host, and drops a trailing slash. It does **not** strip the
path or any parameter that identifies the posting.

### 4.3 The blocking rules, which override any positive match

A merge is refused, whatever the layers say, when:

- **Employment types differ.** An internship and a full-time role sharing a
  title are different jobs. The spec's own fixture list names seasonal
  internship variants as a case that must stay separate.
- **The two postings share no location.** M0's dedupe note is explicit: keep
  multi-location roles distinct.
- **The companies differ.** Structurally impossible given the blocking in §4.1,
  asserted anyway, because a future change to candidate generation must not be
  able to quietly enable it.

### 4.4 Similarity, and what it is not allowed to do

Layer 3 uses embeddings — the local `bge-small-en-v1.5` via fastembed that
AMENDMENTS A5 mandates. Free, offline, deterministic, no key. The model is
fetched once during `make setup` so `make demo` stays offline.

**Similarity is never sufficient on its own.** It only breaks the tie after
company, normalized title and location already agree. A high cosine score
between two postings with different titles, or no shared location, produces
nothing. This is deliberate: a merge destroys a distinct listing from the
user's view, and a number is not a reason.

**The threshold is not chosen by taste.** It is derived from the labelled
fixture set in §4.6 and pinned as `DEDUPE_RULESET_VERSION`, so changing it is a
visible, reviewable event rather than a tuning session nobody records.

### 4.5 Merges are reversible because the raw truth is preserved

Merging job B into job A moves B's `job_source_links` onto A and writes a
`job_merge_events` row: winner, loser, reason, confidence, ruleset version, and
a snapshot of the loser.

Reversibility does not depend on that snapshot being complete, because
canonical jobs are *derived*. `source_job_records.raw_payload` holds every
source payload verbatim, so any canonical job can be rebuilt from raw records
at any time. The merge event exists to make an un-merge cheap and to make the
decision auditable — not because the underlying data could otherwise be lost.

### 4.6 The evaluation fixture set

PRODUCT-SPEC §7.5 names seven categories, and all seven get fixtures before the
matcher is written:

1. True duplicates
2. Near duplicates
3. Distinct roles with similar titles
4. Reposts
5. Seasonal internship variations
6. Jobs in multiple locations
7. Jobs with modified descriptions

Each fixture is a labelled pair with an expected verdict. The suite is what
sets the threshold in §4.4, and it fails if a change to the rules starts
merging a pair labelled distinct — which is the failure that costs a user a job
they would have applied to.

## 5. UI

### 5.1 Admin job table

Under Operate. Every canonical job with status, `last_seen_at`, source count,
locations, and merge provenance; filterable by status, source and company.
This is where "ingestion failures are visible in the UI, not just logs" is
satisfied for the job side.

### 5.2 Source health

The existing table grows: per board, the last successful poll, consecutive
failures, the last error text, and job counts by status. It states the
outage-versus-empty distinction in words, because that distinction is the whole
of I3 and a reader should not have to infer it from a zero.

## 6. Deliberately not in M1b

| Thing | Where it belongs |
|---|---|
| Board discovery, the coverage page | M1c |
| Polling tiers, conditional requests, `304` handling | M1d |
| Geocoding, and therefore `last_verified_at` being populated | M1's geocoding stage |
| Role-family and seniority normalisation | M3 |

M1b needs no new scheduling: closure evaluation runs at the end of each
ingestion run, and the hourly ARQ cron from M0 already triggers those.
