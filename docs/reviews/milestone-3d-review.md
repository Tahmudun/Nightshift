# Milestone 3d review — the evaluation suite, and what it was grading

**Date:** 2026-08-11
**Branch:** `m3d-evaluation`
**Scope:** eight tasks — the ontology edge, floors on four reading accuracies, eligibility
precision and recall per state, §7.2's second equality in CI, the ranking-quality metric,
the ordering decision, three queue rows off the deferred list, and this session: two ADRs,
this review, and M3's acceptance walk.

---

## 1. The shape of what went wrong this time

The plan named the failure mode before any task started, and it is worth quoting
because the milestone then produced a textbook instance of it:

> **An evaluation suite is the one component whose bugs make everything else look
> better.** A metric that measures the wrong thing, a floor set above what it grades, a
> hallucination check that runs after the table it inspects has been emptied — each
> reports a green number and hides the defect it was built to expose.

Three milestones have each found a different version of a check that cannot see what it
is named for. M3a: **a check can be blind to the thing it is named for.** M3b: **a check
can measure the right thing at the wrong altitude.** M3c: **a true statement about a
database can be a false one about a person.** M3d's is the one that only an evaluation
milestone can produce:

> **A measurement keeps reporting after the thing it measures has been replaced, and
> nothing goes red, because a number that gates nothing has nothing to be red about.**

Four of this milestone's findings are that sentence with different nouns. The
ranking-quality grader graded an ordering the product had stopped serving. Five reading
accuracies stayed ungated on a condition that had been met a milestone earlier. Three
brand-new `verify.py` checks were asserted against a table that had been emptied on the
way past. And a check added by the commit that fixed those three could itself not fail.

The generalisation to carry into M4: **this project's tests are now good enough that its
weakest link is the tests nobody made gate anything.** §7.1 lists three metrics that are
reported and not gated by deliberate decision, and that decision is still right — a floor
set before a number is measured is either unreachable or vacuous. What is not right is
that a reported number and a gated one look identical in a green run, and the only thing
standing between them is somebody remembering to look.

---

## 2. Findings

### 2.1 The ranking grader measured an ordering the product had stopped serving — FIXED, and it is the milestone's own headline metric

Task 5 built `test_ranking_quality_against_the_ratings.py`, which sorts the rated corpus
the way the product sorts it and reports NDCG and precision. Its sort key carried this
docstring:

> *The product's own ordering (§5.3), not a second opinion about it.*

Task 6, one commit later, replaced the product's ordering with
`fraction × √(assessed/100)` and did not touch the grader. So for the rest of the
milestone the sentence above was false, and CI reported this:

```
NDCG@10      0.811        <- the ordering M3c shipped
NDCG@30      0.926
precision@5  0.600
```

against a product serving this:

```
NDCG@10      0.817        <- the ordering Task 6 shipped
NDCG@30      0.931
precision@5  0.800
```

The receptionist tells the story on its own. Task 6 exists because an Employee Experience
Specialist rated `poor` ranked **fifth**, above four postings rated `good`; `matching.md`
§5.3 records that it now ranks sixth. Run the committed grader before this repair and it
prints the receptionist at rank five — the milestone's own metric still showing the defect
the milestone had fixed.

**Why nothing caught it.** Task 7 found the same drift in two other places and repaired
both: `verify.py` and `matching.spec.ts` had also asserted the plain fraction, and both
went red. The grader did not go red because it gates nothing. A reported metric cannot
fail; it can only be wrong, and only to a reader who happens to run it with `-s` and
compare the number to a document.

**Why it is the worst of the four.** The other three drifts made a correct system look
broken, which is loud. This one made a superseded ordering look like the current one, in
the flattering direction, in the exact file whose purpose is to tell the truth about
quality. Had the change gone the other way — had coverage weighting made ranking worse —
this file would have gone on reporting the better number, and the milestone would have
shipped a regression with a metric certifying it.

**Fixed** by giving the arithmetic one definition,
`scoring.coverage_weighted_fraction`, called by the grader and by `verify.py`;
`coverage_weighted_rank` is its SQL translation and
`test_the_sql_ordering_is_the_documented_key` holds the two together over stored rows
chosen so the plain fraction and the raw total each give a *different* permutation. The
grader now reproduces §5.3's chosen row from committed fixtures, which is also the first
independent confirmation Task 6's table ever had — it was measured by a harness that never
entered the repository. ADR 0021 records all of it.

**And a guard for the same class**: `test_this_corpus_can_tell_the_two_orderings_apart`
asserts the rated corpus distinguishes the shipped key from the plain fraction. Where it
could not, the metric would be unable to report the drift a second time.

### 2.2 `make acceptance` was red for a week and nobody noticed — FIXED at Task 7

`verify.py` and `matching.spec.ts` both asserted the ranked list descends by printed
`fraction`. Task 6 replaced the key and updated neither. Both now recompute the documented
key and **read `ordering` off the response first**, so the next change to the sort is a
loud refusal rather than a wrong assertion about a right answer.

### 2.3 A seven-task branch ran no CI at all — RECORDED, and it is the cause of 2.1 and 2.2

`.github/workflows/ci.yml` triggers on `push: branches: [main]` and on `pull_request`.
`m3d-evaluation` is pushed to the remote and has **no PR**, so `gh run list --branch
m3d-evaluation` returns an empty array: not one CI run across eight tasks and five days.

This reframes Task 7's conclusion. That task recorded the cause as *"nothing in CI covers
`make acceptance`"*, which is true — the `e2e` job runs the seeded Playwright suite but
never `scripts/verify.py`. It is not the whole cause. `matching.spec.ts` **does** run in
CI, and its ordering assertion was red from Task 6 onward. CI would have caught the drift
within minutes of the push. CI did not run.

Two candidate fixes, and the cheap one is the right one:

| | |
|---|---|
| Widen the trigger to `push: branches: ['**']` | Every work-in-progress push burns a full matrix, including the ones that are known-broken. ADR 0016's five-minute target is about a CI people do not start skipping |
| **Open the PR as a draft at task 1** | Costs nothing, gates nothing, and every push from then on is checked |

Recorded rather than changed, because it is a working-practice decision rather than a code
one, and because this milestone is the evidence for it: **the rule "commit small and run
`make check`" has been followed exactly, and it was not enough, because `make check` does
not run the browser suite.**

### 2.4 Three brand-new `verify.py` checks were vacuous the moment they were written — FIXED at Task 7

`check_daily_queue` runs after `check_profile_confirmation`, which edits a scoring-relevant
profile column and therefore deletes every stored score on its way past (ADR 0019 §2). All
three of Task 7's score-backed rows were asserted against an empty table and passed. It
rescores first now, and the gap row's assertions moved below the point where the script has
a tracked role for them to be about. With that fixed the checks see 1 internship offered
and 3 gap rows naming JavaScript, Kotlin and Swift.

### 2.5 The repair for 2.4 contained a check that could not fail — FIXED here

```python
check(scored >= 0, "the corpus is scored before the score-backed rows are read", str(scored))
```

`recompute_pending` returns a count. `>= 0` is true of every possible return value,
including the zero that means the rescore did nothing and the three rows below are once
again being asserted against an empty table. `check_match_results` does the same rescore
twenty lines further down and asserts `restored > 0`.

So the commit whose subject was *three checks that could not fail* shipped a fourth. It is
recorded rather than quietly corrected because of what it says about the class: this is not
a lapse of attention that more care would have prevented — it is the default outcome of
writing an assertion about a value you have just computed and know to be fine. The habit
that catches it is the one M3a wrote down and this project keeps having to relearn: **write
the assertion, then make it fail on purpose before believing it.**

Now `scored > 0`.

### 2.6 The golden file was not scoring what production scores — FIXED at Task 1

`demonstrates` began as an optional parameter of `score_match` defaulting to no edges. The
golden test, the mutation harness and the embedding measurement all call `score_match`
directly, so all three pinned a scorer that was not shipping — **and the golden test passed
with the feature complete and wired into production.**

It is now a required keyword-only argument: a call site has to say which rules it means,
and one that forgets fails to run rather than measuring the wrong thing quietly. ADR 0020
§5. The comment predicting this defect was three lines above the code that had it.

Note the family resemblance to 2.1. Both are *a grader silently bound to a version of the
system that is not the one running*, once through a default argument and once through a
duplicated sort key.

### 2.7 `SCORING_VERSION = "m3c.1"` was dead, and its comment said otherwise — FIXED at Task 1

The comment claimed it was "composed onto every stored score by
`matching_weights.ruleset_version()`". Nothing imported it, no stored row ever carried it,
and it survived twelve tasks of M3c. Deleted, with the account left in its place.

### 2.8 A deferral with no owner and no expiry — FIXED at Task 2

`test_eligibility_reading_against_the_answer_key.py` reported five accuracies and gated
one, on a stated condition: *"until Task 5's remaining repairs are done."* M3b Task 5
shipped and merged on 2026-08-05. Nobody came back.

Four are now gated at 0.86 / 0.98 / 0.88 / 0.91, measured and set just under.
`enrollment_required` is deliberately ungated and now says so in `REPORTED_NOT_GATED` with
its reason — 30 of its 31 errors are `not_stated` where the key says `no`, and both mean
*you need not be a student* to the gate. A test partitions the graded fields so a future
field cannot become ungated by nobody noticing.

**The finding is the deferral mechanism, not the four floors.** A condition written into a
docstring has no owner and no expiry date, and it reads as a decision when it is a
reminder. `test_no_deferred_row_blames_something_that_now_exists` — added at Task 7 for the
queue, mirroring `test_search.py`'s guard of the same name — is the shape of the answer,
and it went red immediately on the one surviving deferral's reworded reason, which is the
guard working on the day it was written.

### 2.9 My own new test's third assertion passed while proving nothing — FIXED before commit

`test_the_sql_ordering_is_the_documented_key` (2.1's repair) asserts the served order
differs from what the plain fraction gives *and* from what the raw total gives, so that the
main assertion is not satisfied by an accident of the fixture. The first draft used round
numbers on which two rows tied at a raw total of 20; Python's stable sort then produced the
same permutation as the right key, and the third assertion failed loudly — which is the
only reason it is a footnote here instead of a finding in M4's review.

Recorded because it happened **while writing the review that names this exact class**, in
the test built to close it. The four rows now have deliberately unround totals and each
wrong key gives a visibly different permutation.

---

## 3. What Task 8 added

| | |
|---|---|
| `scoring.coverage_weighted_fraction` | One definition of §5.3's key; `verify.py` and the grader call it |
| `test_the_sql_ordering_is_the_documented_key` | The SQL clause held against the Python definition, over stored rows, with two wrong keys shown wrong |
| `test_this_corpus_can_tell_the_two_orderings_apart` | The rated corpus can see the difference, so the metric can report the drift |
| `_sort_key` in the ranking grader | Reads the shared function; CI now reports the ordering the product serves |
| `check(scored > 0, ...)` | 2.5 |
| ADR 0020 | The ontology edge: one hop, one direction, written by a person |
| ADR 0021 | The ordering key, why it is not the printed number, and the four copies of its arithmetic |
| `matching.md` §5.3, §7.1, §7.3 | §7.1's table brought level with what exists and split by *gated* vs *reported*; §7.3's "ranking quality is unmeasured" retired |
| This file, and M3's acceptance walk in PROGRESS | |

### Mutations, each measured going red

| Mutation | Killed by |
|---|---|
| `coverage_weighted_rank` reverted to the plain fraction | `test_the_sql_ordering_is_the_documented_key` **and** `test_a_barely_assessed_posting_does_not_outrank_a_thoroughly_assessed_one` |
| The grader's `_sort_key` on the plain fraction (i.e. the state this branch was in) | Nothing — which is finding 2.1. It moves the reported numbers from 0.817/0.931/0.800 to 0.811/0.926/0.600, and `test_this_corpus_can_tell_the_two_orderings_apart` is now what stands between that and a silent repeat |

The second row is the honest entry and it is not a passing grade. The repair makes the
drift *observable* — one definition, a corpus that can see the difference, and a SQL/Python
agreement test — and it does not make a future revert of the grader's sort key **red**,
because a reported metric has nothing to be red about. Gating NDCG is §2.5 of the plan's
third step, and the baseline for it is exactly one measurement old.

---

## 4. What this milestone still cannot tell you

- **Whether the ranking is good.** It can tell you that it is 0.817 NDCG@10 over thirty
  postings from nine employers, all quant trading firms or AI labs, rated by one person on
  one day against one profile. §7.3 says this at length and it should be read every time
  the number is quoted.
- **Whether the eligibility rules are right.** Task 3 measures *extraction-induced verdict
  error* — `gate(extracted)` against `gate(labeled)` — with the identical rules on both
  sides. A rule that is wrong is wrong in both and scores 1.000. §2.1 of the plan says so;
  it bears repeating next to the 202/240 agreement figure.
- **Whether the ARQ cron works.** `recompute_pending` is exercised by `make seed`, `make
  score`, `verify.py` and the unit suite. The cron that calls it has been run by `make dev`
  and by nothing that asserts anything. Unchanged since M3c and still true.
- **Whether the queue's summed blind spot means anything.** `todays_one_thing` adds counts
  of different kinds — unscored pairs, unscored applications, unreadable seniority — into
  one number. The sentence tells the reader to read the individual headings, which is a
  disclosure rather than a fix. It is the right disclosure at one user and 31 postings and
  it will not survive a corpus where the counts are large.
- **Whether any of this holds outside the recorded corpus.** Every number in M3 is measured
  against 60 labeled postings and 153 scored ones from nine employers, chosen for
  eligibility-rule coverage. M1's discovery pipeline exists to make that corpus wider, and
  until it runs, "the matching engine performs at X" means "on these nine boards".
