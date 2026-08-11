# ADR 0021 — The ranked list is ordered by a key it does not print

- **Status:** accepted
- **Date:** 2026-08-11
- **Milestone:** M3d (Tasks 5, 6, and a repair at Task 8)
- **Relates to:** ADR 0019 (a score is stored and withdrawn), `matching.md` §5.1.1, §5.3, §7.1, §7.3, `docs/reviews/milestone-3c-review.md` §2.10, QUESTIONS Q5, invariant I4

## Context

ADR 0019 decided that a score is stored out of `assessed_out_of` rather than out
of 100, because 26 of 60 labeled postings name no required technology at all and
scoring those out of 100 removes 50 points for how an employer writes. The ranked
list therefore sorted on `overall_score / assessed_out_of`.

That ADR's own consequences section named what it had not fixed: *"the fraction
is not a total order anyone should read as best first — 19 of 40 outranks 30 of
100, and the two denominators are not comparable quantities."* The M3c review
recorded the same thing at §2.10 and **declined to fix it**, for a reason worth
preserving: there was no way to tell a better ordering from a worse one. Every
candidate was an argument, and this project has a rule against choosing between
arguments when a measurement is available.

QUESTIONS Q5 made one available. Thirty postings rated `good` / `acceptable` /
`poor` by the human on 2026-08-10, with the profile they were rated against
committed in the same file.

The concrete failure, on that corpus: an Employee Experience Specialist
(Receptionist) rated `poor` ranked **fifth**, above four postings rated `good`.
Every number on the page was true and the order was misleading.

## Decision

### 1. The ordering key is `fraction × √(assessed_out_of / 100)`

A fraction of 20 assessable points is not comparable to a fraction of 80, for the
same reason ADR 0019 gave about raw totals. A posting assessed on a fifth of the
score carries a fifth of the evidence, and discounting by coverage is what "these
denominators are not comparable" means arithmetically.

| Ordering | NDCG@10 | NDCG@30 | P@5 |
|---|---|---|---|
| fraction (as shipped in M3c) | 0.811 | 0.926 | 0.600 |
| raw `overall_score` | 0.777 | 0.902 | 0.800 |
| fraction × shrink to corpus mean | 0.811 | 0.924 | 0.600 |
| **fraction × √(assessed/100)** | **0.817** | **0.931** | **0.800** |
| fraction, ≥50 assessed first | 0.822 | 0.934 | 0.800 |

**The +0.006 is not the evidence and must not be read as it.** Over 30 items that
is what one swap moves. Three things decided it:

1. **Never worse.** Leave-one-out across all 30 folds: better in 28, tied in 2,
   worse in none.
2. **Both endpoints lose to the middle.** Sweeping the exponent, `p=0` (the plain
   fraction) gives 0.811 and `p=1` (algebraically the raw score) gives 0.777,
   while `p=0.5` and `p=0.75` both give 0.817. No weighting under-corrects; full
   weighting over-corrects.
3. **The mechanism is the one §2.10 described in advance**, so this is not fitted
   to the corpus.

The bucketed variant scores marginally higher and was **not** taken: its
threshold of 50 is a magic number with no support in this data, and it would need
its own entry in `matching.yaml` and its own mutation test to be defensible. √
has no free parameter. The exponent is deliberately not pinned harder than the
data supports — 0.5 and 0.75 are indistinguishable here.

### 2. The printed number does not change, and the response says what it sorted by

Every row still prints `fraction`, the honest *of what could be assessed* figure.
So a reader can see 17% ranked above 30%.

That is a real cost and it is **disclosed rather than absorbed**:
`MatchRankingOut.ordering` carries `"coverage_weighted_fraction"` on the wire, in
the shape `unassessed_sort_last` already uses. Without it, a reader's only
available conclusion is that the list is broken.

The alternative — printing the weighted key — was rejected because the weighted
key is not a statement about the pair. `fraction` answers "how much of what could
be assessed did this posting score", which is checkable against the breakdown
below it. The weighted key answers "where should this sit relative to postings
with different denominators", which is a fact about a list and belongs to the
list rather than to the row.

### 3. No `ruleset_version` bump: this is a query concern

No score moved, no evidence row changed, the golden file is untouched. Ordering
is not part of what I4 requires to be reproducible from a stored row — it is a
property of how rows are read back. Bumping the version would invalidate every
stored score to change a `SORT BY`.

### 4. One Python definition, and the SQL is held against it — added at Task 8

By the end of Task 6 the arithmetic in §5.3 had four implementations:
`coverage_weighted_rank`'s SQL, `verify.py` recomputing it from the wire,
`matching.spec.ts` doing the same in the browser suite, and the ranking-quality
grader's sort key. **Task 6 updated one of them.**

Two of the other three went red and were repaired at Task 7 — `make acceptance`
had been failing for a week on a correct list. The fourth did not go red, because
a reported-and-ungated metric has nothing to be red about: the grader went on
sorting by the plain fraction and reporting 0.811 as the ranking's quality, which
is the first row of the table above — the ordering this system had stopped
serving.

So:

- `scoring.coverage_weighted_fraction` is the definition. `verify.py` and the
  grader call it; neither restates it.
- `coverage_weighted_rank` is its translation into SQL, because Postgres cannot
  call it, and `test_the_sql_ordering_is_the_documented_key` asserts the served
  order equals the Python order over rows chosen so that the plain fraction and
  the raw total each give a *different* permutation.
- `matching.spec.ts` keeps its own copy — nothing crosses that boundary — and
  reads `ordering` off the response before asserting, so a future change to the
  key is a loud refusal rather than a wrong assertion about a right answer.

## Consequences

**What this buys.** The one ordering defect the rated corpus could see is fixed,
by the mechanism the review predicted, with the measurement that chose it
committed rather than performed once and discarded. CI now reports the quality of
the ordering the product actually serves — and reproducing 0.817 / 0.931 / 0.800
from committed fixtures is the first independent confirmation Task 6's figures
ever had.

**What it costs.**

- **A reader can see a smaller percentage above a larger one.** `ordering` on the
  wire is the mitigation and it is not a complete one: the page names the key, it
  does not show each row's value for it.
- **The evidence is thirty postings from nine employers**, all quant trading
  firms or AI labs, rated by one person. §7.3 says this in full. The choice is
  better supported than the alternative it replaced and it is not broadly
  validated, and those are different claims.
- **A second surface now imports the ordering.** The daily queue's internship row
  ranks stored scores through `band_rank` and `coverage_weighted_rank` rather
  than writing its own clause, which is right — and it means a change to §5.3
  moves two pages at once.

## Alternatives considered

**Leave it, as the M3c review chose.** Correct until Q5 existed and wrong after:
the objection was the absence of a way to choose, and thirty ratings are one.

**Bucket by coverage — everything with ≥50 assessed first.** Scores marginally
higher and was rejected in §1 above: a threshold with no support in the data,
needing a config entry and a mutation test to be defensible, in exchange for a
difference this corpus cannot resolve.

**Print the weighted key instead of the fraction.** Rejected in §2: it is a
property of the list, not of the pair, and it is not checkable against the
breakdown the row carries — which under I4 is the whole point of printing a
number at all.

**Score everything out of 100 so the denominators are comparable.** Rejected in
ADR 0019 and §5.1.1: it ranks terse postings below verbose ones, which measures
an employer's prose.
