# M3b — the deterministic eligibility gate

> Plan. Branch `m3b-eligibility-gate`, off `main` at `452ec90` (PR #9 merged) plus
> `ci-pin-and-canary` once that lands.
>
> Required reading first: `docs/architecture/matching.md` §3 and §8, AMENDMENTS
> A13, `CLAUDE.md` §1 (I2, I4), PROGRESS's M3a and M3a.1 sections.

## What M3b is

The milestone where this system first says something about **a person**. Every
milestone before it made claims about the world; M3a read what a posting asks
for. M3b compares the two and returns a verdict.

`matching.md` §1 scopes it: the deterministic eligibility gate, the role-family
and seniority classifier, `jobs.role_family` and `jobs.seniority` stop being
null, blockers named on the job page, the internship-season filter becomes real.
**No score.** The number, the weights, and the evidence graph are M3c and
nothing here anticipates them.

### The one sentence that governs every decision below

A13, restated in `matching.md` §3.3: **a wrong `ineligible` is the worst output
this engine can produce.** Every other error is visible next to its own
explanation. A wrong `ineligible` deletes an opportunity from the user's world
and reports nothing; they never learn it existed.

Three consequences are load-bearing rather than decorative:

1. When a rule cannot decide it returns `uncertain`. Never a default, never a
   fallback, never "probably fine".
2. Ineligible postings are **shown, dimmed, with the blocker named**. Never
   hidden. A hidden row is a parsing bug that nobody can see.
3. The one number M3b must drive to zero is not accuracy. It is **wrong
   ineligibles**, and it is checked as an equality rather than a rate.

---

## 1. Decisions taken before planning

Following M2c and M2d, where the product calls were made before the plan rather
than inside it.

### 1.1 The human's two, taken 2026-08-05

**Role families: the tech families, plus an explicit `not_tech`.**

```
software_engineering   data_engineering   ml_ai        infrastructure
security               quant_trading      product      design
not_tech    <- read, and deliberately outside this product's scope
unclear     <- could not decide. Never a default.
```

The two non-family values are the point. Nightshift is a NYC **tech** product
and `board-discovery.md` already decided the scope is *tech roles at any
employer* — so Point72's compliance analyst is a real posting that is genuinely
not this product's business. Filing it under `other` would claim we tried and
gave up. `not_tech` says we read it and it is outside scope.

Collapsing the two would make `unclear` mean two different things at once and
make the classifier's grade uninterpretable: a rise in `unclear` could be more
non-tech postings in the corpus or a worse classifier, with no way to tell.

**The `skill` filter is turned on, with what it is based on stated next to it.**

It has been deferred since M2 for a reason that has now moved twice. The
original reason ("requires the skill taxonomy") went stale at M2c and nobody
noticed for a milestone. The replacement reason (recall 0.459 — a filter would
hide more than half the matching roles) went stale at M3a.1, and PROGRESS caught
it in the same session for the first time.

At 0.861 it hides roughly one matching role in seven. That is a usable filter
and not a complete one, so the page says so, and the result panel reports how
many postings had no requirements extracted at all. Turning it on with no
caveat was rejected: it would be the first filter in this product that quietly
returns an incomplete result.

### 1.2 The ones taken here, as engineering calls

**The gate stores nothing.** `match_results` is M3c's table (`matching.md`
§4.2). M3b computes a verdict on read, from `job_requirements` × the user's
confirmed profile. Two reasons: a stored verdict goes stale the moment a person
edits their graduation year, and the gate stays a **pure function**, which is
what lets it be graded against the answer key without a database anywhere near
the grader — the property `eligibility_labels.py` already protects for the
labels.

**The gate never reads `jobs.description_text` itself.** It reads
`job_requirements` rows, which already carry their spans. That keeps exactly one
component doing the reading, and it means every blocker the gate names can quote
the posting because the span was stored at extraction time.

**Seniority is not a gate input.** `matching.md` §5.1 makes seniority mismatch a
*penalty*, which is M3c. A senior title is not a legal barrier and treating it
as one is precisely the wrong-`ineligible` failure. M3b classifies seniority and
the gate ignores it.

---

## 2. The grading design, which is the crux of the milestone

Three different things get measured and **they must not be reported as one
number**. M3a.1's central finding was a metric that disagreed with itself.

### 2.1 Reading accuracy — graded against the answer key, in CI

M3a graded exactly one of the answer key's nine fields: `required_tech`, plus
necessity. **The extractor already produces `degree`, `graduation_window`,
`years_experience`, `enrollment` and `authorization` proposals and no test has
ever compared any of them to a label.** Five fields of an answer key that was
committed before the rules existed, sitting ungraded for a milestone.

That is Task 1, and it is first because the numbers will be bad. M3a's first
measurement of required technologies was 0.156 recall. There is no reason to
expect these to open better, and every reason to find out before a gate is built
on top of them.

Per field, over the 60 labeled postings:

| Label field | Metric | Notes |
|---|---|---|
| `is_internship` | 3-way accuracy | yes / no / unclear |
| `graduation_window` | accuracy | a window, or `not stated` |
| `enrollment_required` | 3-way accuracy | |
| `degree` | 8-way accuracy | the four levels × `+equivalent` |
| `min_years_experience` | accuracy, `None`-aware | `not stated` ≠ 0 and the difference matters |
| `sponsorship` | 3-way accuracy | offered / not offered / not stated |
| `role_family` | accuracy | new label, Task 2 |
| `seniority` | accuracy | new label, Task 2 |

Floors go into CI **after** measuring, just under what is achieved — the rule
M3a set and the reason for it: a floor picked before measuring is either
unreachable or vacuous and there is no way to tell which from outside.

### 2.2 Gate correctness — fixtures, not a metric

The gate is a pure function of (facts × profile). Grading it against the corpus
would measure the extractor and the rules at once and attribute nothing.

So it is fixture-tested: hand-written `(label, profile) → expected verdict`
cases, one per rule and one per hard case A13 names. All six of A13's, by name,
because a rule with no posting exercising it is a rule with no test:

- an "Intern" title carrying "3+ years of experience required"
- a new-grad role whose window is stated only in prose
- a years requirement sitting under *preferred*, not *required*
- "Bachelor's degree **or equivalent experience**" — never a hard blocker
- "Software Engineer I/II" spanning an eligibility boundary
- a return-offer internship with its own eligibility

**The fifth is the one the corpus cannot support.** `matching.md` §3.6 measured
it: a posting spanning an eligibility boundary is absent from **eight of the
nine boards**. Its fixture is therefore hand-written and labelled as
constructed, not drawn from a recorded payload — and M3b must not read its
answer-key grade as evidence about that case. Stated here so it is not
discovered as a surprise in the review.

### 2.3 The wrong-ineligible check — an equality, not a rate

Run description → extraction → gate over all 60 labeled postings × a set of
profiles. For every `ineligible`, check the **labels** independently support a
hard block. Any posting where they do not is a wrong ineligible.

**Target zero, asserted as an equality.** Not a floor, not a rate.

And it must be shown able to fail, because M3a shipped exactly this shape of
test and it was vacuous: `test_no_nice_to_have_is_ever_reported_as_required`
reported 0 violations for a whole milestone because it compared raw strings and
could not see that `Apache Spark` and `Spark` are the same technology. It was at
zero the way a test that cannot fail is at zero. This one gets a deliberately
broken rule pushed through it before it is trusted.

---

## 3. The gate's shape

`services/api/nightshift/domain/eligibility.py`. No ORM import, per the rule
`eligibility_labels.py` already follows.

Each dimension returns one of five outcomes — `passes`, `blocks`, `soft_blocks`,
`cannot_tell`, `not_applicable` — and the five compose in one direction only:

```
any blocks        -> ineligible
else any soft     -> likely_ineligible
else any cannot   -> uncertain
else all pass, some on an unstated input  -> likely_eligible
else                                       -> eligible
```

`blocks` requires two things at once: the posting states it under a **required**
heading, *and* the user's **confirmed** profile contradicts it. Either half
missing is `cannot_tell`. That is I2 doing the work — an inferred fact never
blocks anybody, because an inferred fact is not a fact.

Three rules that follow directly from A13:

- **`+equivalent` demotes `blocks` to `cannot_tell`.** Always. `has_equivalence`
  has been stored since M3a for exactly this and is currently read by nothing.
- **An internship stating years of experience contradicts itself**, so that
  dimension is `cannot_tell` and the verdict names the contradiction rather than
  resolving it.
- **A requirement under a *preferred* heading can never do more than
  `soft_blocks`.** M3a's necessity column is what makes this mechanical.

Every blocker carries what it needs to be inspectable (I4): the dimension, the
quoted span from the posting, what the profile says, and one sentence a human
reads. Unknowns are separate from blockers and name the profile field whose
absence prevented a decision — that is what turns "we cannot tell" into
something a person can act on.

---

## 4. Tasks

| # | What | Ends in |
|---|---|---|
| 1 | Grade the five ungraded label fields. Publish the numbers before changing a rule | Measured baseline, no floors yet |
| 2 | `role_family` + `seniority` labels added to the answer key, **before** any classifier exists | The gate test goes red until they are filled |
| 3 | `RoleFamily`, `Seniority`, `EligibilityState` enums; migration converting the two `String` columns to PG enums | Migration up, down, up |
| 4 | The classifier, graded against Task 2 | Accuracy per field |
| 5 | Whatever Task 1 says is broken — the M3a.1-shaped repair loop, each step measured on its own | Attributable movement |
| 6 | `domain/eligibility.py`: the gate, pure, no ORM | The fixture suite of §2.2 |
| 7 | The wrong-ineligible equality, shown able to fail | 0, provably |
| 8 | Mutation testing on every gate rule (`matching.md` §8) | Each rule kills a named test |
| 9 | `GET /jobs/{id}` returns the verdict, its blockers and its unknowns; the three new enums transcribed into `schemas.ts` and added to `test_enum_parity.py` | Zod schemas, parity guard |
| 10 | The job page: blockers named, dimmed not hidden, unknowns linking to the profile | Component tests |
| 11 | `internship_season` — the column, its shape, and the filter; `skill` filter on with its caveat and its not-extracted count | Both deferral reasons deleted from the list |
| 12 | Browser walk, `check_eligibility_gate` in `verify.py`, ADR 0017, review, PROGRESS | `make acceptance` |

Task 5 is deliberately sized as unknown. M3a.1 was an entire unplanned slice
that existed because a number came in at 0.459, and pretending the same cannot
happen here would be planning for the happy path.

---

## 5. What M3b does not do

- **No score, no weights, no `match_results`, no evidence graph.** M3c.
- **No seniority-based blocking.** §1.2.
- **No `ineligible` that hides a row.** Ever.
- **No eligibility state converted into points.** `matching.md` §5.2 — a job can
  be `uncertain` and still be worth looking at, and the moment uncertainty is
  worth a number it stops being uncertainty.
- **No eligibility precision/recall in CI.** `matching.md` §7 puts the ranking
  and eligibility metrics in M3d. M3b reports reading accuracy and the
  wrong-ineligible equality; that is what it can honestly measure.
- **No label edited.** The answer key was committed before any rule existed and
  that ordering is the only reason its numbers mean anything. Two fields are
  **added** in Task 2, labeled before the classifier they grade. If an existing
  label looks wrong it is fixed in the review with a recorded reason, never
  quietly.
