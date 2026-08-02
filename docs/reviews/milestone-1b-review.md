# M1b review — canonical spine

**Date:** 2026-08-02
**Scope:** dedupe, freshness, the closure state machine, the admin job table,
the source health page. Branch `m1b-canonical-spine`, PR #2.

Written per CLAUDE.md §5, which says to actively look for hallucinated
certainty, silent data loss, wrong merges, race conditions, retry storms, GPU
leaks, unbounded render work, mobile gesture conflicts, accessibility gaps,
privacy overreach, and tests that assert nothing. Four of those are not
reachable yet and are marked as such rather than quietly dropped.

---

## 1. Defects found, and how

Two real bugs. **Neither was found by reading the code**, and that is the most
useful thing in this document.

### 1.1 A merge silently dropped locations only the loser named

**Severity: the highest in this milestone.** Fixed in `eda0297`.

Two cross-posted listings of one role can name different sets of offices. Board
A says `"Washington, DC"`. Board B says `"Washington, DC"` and `"Austin, TX"`.
They share a location, so they merge; the loser was then deleted and its
`job_locations` rows cascaded away with it. The canonical job was left claiming
the role is only in DC.

The raw payload survives, so nothing was unrecoverable. But a user filtering
for Austin would never have seen the role — at the exact moment two independent
sources agreed it exists there. That defeats AMENDMENTS A2 ("one row per
location the posting names") precisely where A2 matters most.

**How it was found:** by writing a throwaway script that ingested a
deliberately-asymmetric pair and printed the resulting location rows. Every
existing merge test used pairs whose location sets were identical, so the whole
suite was green and blind. The lesson is narrow and worth keeping: *a fixture
pair that varies only in the dimension under test will not catch a bug in a
dimension held constant.*

Now deduplicated on the parsed `(city, state, country)` key rather than on
`raw_text`, because `"New York, NY"` and `"New York, NY (HQ)"` are one office
written twice and keeping both would turn one place into two.

### 1.2 Two descriptionless postings merged on their emptiness

Fixed in `4058a16`, found while wiring the matcher into the pipeline.

`content_hash(None)` returns the sha256 of the empty string — a genuine
64-character digest, identical on both sides. So layer 2 compared two postings
with no description at all, found their hashes equal, and merged them on
"identical content".

Same shape as two null URLs matching each other, which `normalize_url` had
already guarded against. One guard existed and its twin did not, which is the
ordinary way this class of bug survives.

---

## 2. Risks examined and found acceptable

### 2.1 The handover between merging and closure

**Checked, correct, and now covered by a test.**

A company closes a listing and re-publishes it weeks later under a new id. The
new posting merges into the *closed* original — correct, it is the same
opening — and `apply_freshness` then re-decides on the merged job's records and
reopens it, because one of them was listed at this poll.

These two subsystems could plausibly have fought: a merge that inherited the
winner's `closed` state without freshness re-running would leave a live job
invisible. It does not, but nothing in the suite covered the handover, so
`test_a_repost_merging_into_a_closed_job_reopens_it` now does.

### 2.2 Merge asymmetry through the inputs

An early draft of `_candidate_for` took one side's URL from the incoming
payload and the other's from storage. `compare` is symmetric, but its *inputs*
were not, so merges would have depended on ingestion order and the same board
polled twice could have produced different canonical jobs.

Caught during implementation. Both sides are now built by one function from the
database, and `test_comparison_is_symmetric` runs over every labelled pair.

### 2.3 Unbounded work

`find_duplicate` is linear in a company's job count, and runs once per created
job — so a first ingest of a large board is quadratic in that board's size.
Measured in practice: the recorded 9-posting board is imperceptible, and the
whole Python suite runs in ~135s including model loads.

This will not hold at M1c's 2,605 boards. The fix then is a blocking index on
`(company_id, normalized_title)`, which turns the scan into a lookup. Not done
now, deliberately: CLAUDE.md §8 forbids building for scale nobody has measured,
and the shape of the fix is known and cheap.

### 2.4 Retry storms

Unchanged from M0. Nothing in M1b issues an HTTP request; `PoliteClient` remains
the only module that touches the network, and the closure machine is driven
entirely by outcomes the ingestion loop already has in hand.

### 2.5 Privacy overreach

None. M1b touches no user data — there is no user data yet. `job_status_events`
and `job_merge_events` record decisions about public job postings.

---

## 3. Open risks, carried forward

### 3.1 The similarity threshold is calibrated on three labelled pairs

`SIMILARITY_THRESHOLD = 0.85` was derived, not chosen, and the separation is
wide (0.7640 distinct / 0.9370 merge, margin 0.173). But only three labelled
pairs carry descriptions, so three points define it.

That is thin, and it is the number most likely to be wrong in a way no current
test can see. It should be re-derived as the fixture set grows;
`scripts/derive_dedupe_threshold.py` exists precisely so that re-deriving is a
one-command job rather than an archaeology project.

**Recorded in PROGRESS under "Not real yet" rather than left in this file.**

### 3.2 Two workers merging concurrently

Not reachable today at `max_jobs=1`. ADR 0007 makes polling queue-driven, at
which point two workers can each decide job A and job B are duplicates and each
try to delete the other's winner.

`get_or_create_company` and `get_or_create_source` were made atomic upserts in
M1a for exactly this reason; merging has no equivalent protection. The likely
answer is a row lock on the winner (`SELECT ... FOR UPDATE`) inside
`merge_jobs`, but it should be designed against M1d's actual concurrency model
rather than guessed at now.

**This is the single most important thing M1d must not inherit unnoticed.**

### 3.3 Dedupe runs only on creation

Deliberate — re-running the matcher every poll is how a settled merge starts
oscillating — but it has a consequence: two jobs that become duplicates *later*
(a title corrected on one board to match the other) never merge.

No mechanism exists to reconcile that, and none is planned. Acceptable while
the corpus is small; worth revisiting if users start reporting visible
duplicates.

### 3.4 A merged job can end up with no primary location

If two postings merge on identical URL while having disjoint location sets, and
the winner happened to have no locations, every absorbed row is marked
non-primary and `primary_location_id` stays null. The column is nullable and
the UI handles it, so this is cosmetic — but it is a state no posting asserted.

---

## 4. Accessibility

Partial, and honestly so.

**Done:** every job status renders as a word alongside its colour, asserted by
a browser test — §12.4 forbids essential information carried by a visual
channel alone, and "is this job still open" is as essential as it gets on that
screen. The status legend is a permanent `<section>` with an accessible name,
not a tooltip. Tables use `<caption>`, `scope="col"` and `scope="row"`. Filter
buttons carry `aria-pressed`.

**Not done, and unchanged from M0's deferral:** no test asserts focus-visible
styling, and none of this has been checked with a real screen reader. Still
deferred to M4's accessibility pass. It has now been deferred twice, which is
worth saying out loud.

---

## 5. Tests that assert nothing

Every guard added in this milestone was mutation-checked, and the results are
recorded in the commit messages rather than only here. The three most
informative:

| Mutation | Caught by |
|---|---|
| A failed board counted as answered | 2 closure tests — and **not** the pre-existing `test_a_failed_board_closes_nothing`, because one failed poll never reaches a threshold |
| The title guard removed | `test_the_recorded_board_does_not_self_merge` — the 9 real postings on the recorded board collapse |
| The append-only triggers dropped | Exactly the 3 tests written for them, and nothing else |

The first is the one worth remembering. The existing I3 test was satisfied by
code that incremented a miss counter during an outage, because the damage only
becomes visible three polls later. The new assertion is on the counter, not the
status, for that reason.

`TestSimilarityIsConfined` includes a deliberate control case
(`test_identical_text_still_merges_when_everything_agrees`) so its three
negative tests cannot pass by the similarity layer simply being broken.

---

## 6. Not applicable at this milestone

Named rather than dropped, so a later reader knows they were considered:

- **GPU leaks, unbounded render work, mobile gesture conflicts** — no 3D, no
  map, no canvas. M4.
- **Hallucinated certainty in the UI** — no score is displayed anywhere yet;
  I4's subsystem is M3. The nearest thing is `match_confidence` on a merge, and
  it is stored with its reason and ruleset version rather than shown as a bare
  number.

---

## 7. Verification

At `eda0297`, from a clean shell:

```
make check        480 Python tests (0 skipped), 42 web, ruff + mypy clean (34 files)
make acceptance   18 verify checks, 11 seeded browser tests
migration         down and up on a live cluster: both triggers, the trigger
                  function and all three tables drop and are restored
CI                run #10 green, five jobs, 467 passed read directly from the log
```

CI has not yet run the location-absorption fix or the UI. That is the one gap
in this document and it closes on the next push.
