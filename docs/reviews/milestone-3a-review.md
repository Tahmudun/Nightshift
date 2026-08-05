# Milestone 3a review — the corpus, the answer key, and requirement extraction

**Date:** 2026-08-04
**Branch:** `m3a-answer-key`
**Scope:** twelve tasks — nine recorded boards, a 60-posting human answer key, the
`job_requirements` table and its two triggers, the extractor and its grading, ingestion,
the API, the job page, and the fifth coverage blind spot.

---

## 1. The number this project tracks

**Tasks 8–12 produced eleven findings and eight were in code or tests that reported
success** (§2). Tasks 1–7 ran across a previous session and their findings are recorded
individually in the commit messages; counting them into a single total here would mean
inventing a number, so this review counts what it can and points at the log for the rest.
Either way it is the ninth consecutive milestone where the majority of what was found was
found in something green.

The shape of it changed this time, and the change is worth naming. In M1 and M2 the
typical finding was a rule that was wrong. Here the typical finding is **a check that
could not see the thing it was named for**. Eight separate times on this branch, a test
suite was fully green while the artefact it guarded was broken:

| What passed | What was actually true |
|---|---|
| Every worksheet test | 30 of 60 excerpts started mid-sentence; ~17 of 60 were labelable |
| Every worksheet test, round 2 | 3 postings had a known heading sitting undetected |
| Every worksheet test, round 5 | 12 of 60 silently dropped a degree or sponsorship statement |
| `unlabeled()` returning `[]` | Four malformed keys read as fully labeled |
| `unlabeled()` returning `[]`, round 2 | A nested field value read as fully labeled |
| The span trigger | Its parent could be rewritten underneath it |
| `test_a_span_running_past_the_description_is_refused` and friends | An inverted span raised `SubstringError`, not `IntegrityError` |
| `JobDetail.test.tsx` | Its fixture was a cast, so it went stale silently |

The generalisation: **a guard that asks "does the output look right" cannot see a
guard-shaped hole.** Every worksheet check asked whether an excerpt began at a heading,
was short enough, and was marked when cut. All of them passed while twelve postings
dropped the answer to a question the worksheet asks. The check that found it —
`test_no_excerpt_silently_drops_eligibility_content` — asks a different question: *did we
lose anything*. That question has to be asked separately and it is the one nobody writes
by default.

---

## 2. Findings from Tasks 8–12, in full

Tasks 1–7's findings are recorded in their commit messages and summarised in §1. These
are the ones from this session, which are not written down elsewhere.

### 2.1 The plan credited the wrong guard, and measuring said so — CORRECTED

The plan's `sync_requirements` docstring said delete-then-insert is what keeps a span
honest when the description changes. It is not. Task 5's
`jobs_description_change_clears_requirements` trigger already does that, and **removing
the delete leaves every description-change test green** — measured, not reasoned about.

What the delete is actually for is the *unchanged* case: re-extracting over text that did
not move re-emits the same `(kind, value, char_start)` tuples and
`uq_job_requirements_span` rejects the second insert. Two tests fail without it.

This matters beyond a docstring. A reader who believes the delete is the integrity
guarantee will happily delete the trigger, because the trigger looks redundant. It is the
other way round.

### 2.2 An unconditional re-extract on the update path — CORRECTED

The plan called for `sync_requirements` on every re-poll that touched a job. That is
churn no count can see: identical row totals, every row replaced, `created_at` reset
across the whole corpus each time any board answers. A salary edit changes fields and
moves no character.

Gated on the description hash, read *before* `_apply_normalized_fields` overwrites it.
`test_repolling_unchanged_postings_does_not_churn_requirements` compares row **ids**
rather than counts, because counts are exactly what this failure preserves. Mutating the
gate to `if True:` turns it red.

### 2.3 An ordering hazard the delete fixes by accident — DOCUMENTED

A caller assigns `job.description_text` and calls straight in. Executing SQL inside
`sync_requirements` autoflushes that pending UPDATE first, so the trigger it fires clears
the old rows *before* any new one is inserted. Without a statement forcing that order, the
unit of work is free to order the inserts ahead of the UPDATE — and the trigger would then
delete the rows the function had just written.

It is covered by `test_changing_the_description_replaces_the_requirements`, which asserts
the *new* values survive. Written down in the code because nothing about the line says so.

### 2.4 The extractor version was nearly read from the module constant — CORRECTED

The obvious implementation of `requirements_extractor_version` is `EXTRACTOR_VERSION`.
That answers "what would the extractor produce today", which is not the question. A job
whose rows predate a version bump must report the rules that actually produced them, and a
job nobody has read must report nothing at all. Read off the rows instead. Substituting the
constant turns `test_nothing_extracted_is_not_reported_as_nothing_required` red.

This is the field that lets the page distinguish "we read it and found nothing" from "we
have not read it". An empty list alone cannot.

### 2.5 A component-test fixture was a cast, not a check — FIXED

`JobDetail.test.tsx` declared `const BASE: JobDetail = {...}`. A cast asserts a shape; it
does not verify one. The fixture went stale the instant this milestone added two fields
and **said nothing** — the render crashed with `Cannot read properties of undefined`
instead. Now parsed through `jobDetailSchema`, which is the same lesson M2c recorded about
`ExtractionReview` and the second time this project has shipped it.

### 2.6 A "not built yet" reason had gone stale — FIXED

The `skill` deferred filter said *"Requires the skill taxonomy and its aliases."*
`data/skills.yaml` shipped at M2c and M3a indexed every posting's technologies, so the
stated blocker had been false for a milestone and a half. **This is the third consecutive
milestone to find a stale absence** — M2c and M2d each found one — and it is always the
same direction: nobody re-reads the "not built" list when the thing it waits on lands.

The filter stays deferred, for a reason that is now measured: required-technology recall
grades at 0.459, so filtering on a skill would hide more than half the postings that ask
for it and return them as an empty result, which reads as "no such job".
`test_no_deferred_filter_blames_something_that_now_exists` is the new guard. It can only
check named artefacts — a test cannot read English — but it covers the three that have
actually gone stale.

### 2.7 A verify check that passed with nothing on either side — FIXED

`check_job_requirements` picked the first posting with any requirements. That posting's
three rows were all `mentioned`, so the necessity assertion printed **"0 required, 0
preferred"** and a green tick for a comparison with nothing in it. Now it prefers a
posting that can actually fail the check, and prints the necessity mix either way so a
vacuous case is visible in the output rather than hidden behind a passing line. This is
M2a's lesson — *any measurement must print what it measured against* — in a new place.

### 2.8 A browser test that would skip itself green — FIXED

`requirements.spec.ts` picks its job from the API at run time rather than naming a UUID,
and skips with a reason when no posting has the shape it needs. Written naively, all four
tests skip green against an unseeded stack and the file reports success having checked
nothing — which happened on its first run. `findJob` now throws when the corpus is
*empty*, which is a different thing from a shape being absent.

### 2.9 The section was rendered where nobody would read it — FIXED

The plan said "below the description", which put it after "Not yet computed", after
"Sources", and below the entire posting text. Found by opening the page, not by reading
the code. Every row quotes a sentence from the description, so a reader who has scrolled
the whole posting is being shown those sentences twice; the other way round, the section
tells them what to look for.

### 2.10 A new text surface with no contrast assertion — FIXED

`ink-700` had been a border shade everywhere until the "or equivalent" badge used it as a
fill with text on it. Added to `SURFACES` in `colour-contrast.test.ts` rather than given a
one-off assertion, so all three text weights are held to it. It is now the lightest
surface there and therefore the binding one: `paper-faint` clears it at **4.63:1**, with
less than a shade to spare.

### 2.11 Two items a previous commit deferred to this review — BOTH NOW VERIFIED

`aa0235b` states plainly that it did not verify the trigger-drop proof or a fresh
migration cycle. Both done here:

```
DROP TRIGGER jobs_description_change_clears_requirements   -> 1 test red, 12 green
alembic downgrade -1 && upgrade head                       -> both triggers present again
alembic check                                              -> no new upgrade operations
```

**The trigger is guarded by exactly one test**, `test_rewriting_the_description_clears_
its_requirements`. My own Task 8 tests pass without it, because `sync_requirements`'
delete covers the paths they walk. That is thin for a structural guarantee, and it is
recorded rather than padded: the trigger's whole purpose is the writer that *doesn't* call
`sync_requirements`, and there is exactly one test standing in that position.

---

## 3. What was actively looked for

| Risk | Finding |
|---|---|
| **Hallucinated certainty** | The coverage row's probe claims were checked against `matching.md` §3.6 before being committed, not copied from the plan on trust. The ADR's worked example was changed from the plan's Ramp to Akuna, because the corpus says Akuna |
| **Silent data loss** | The dominant failure mode of this milestone — see §1. Six of the eight green-while-broken cases are data loss |
| **Spans that can drift** | Two triggers, both proven able to fail. Re-asserted at the API boundary (`test_every_returned_span_quotes_the_returned_description`), again in Zod (`jobDetailSchema.superRefine`), and again in the browser against the rendered description |
| **Tests that assert nothing** | §2.7 and §2.8. Both were mine and both were found by reading the output rather than the code |
| **A stale "not built" list** | §2.6. Third milestone running |
| **Privacy** | `job_requirements` holds no personal data. A posting is public and its payload is committed |
| **Irreversible actions (I5)** | Nothing in M3a writes on a user's behalf. `check_job_requirements` edits a description and restores it, comparing `(kind, value, span)` sets before and after |

---

## 4. What this milestone does not claim

**Recall is 0.459 and that is the headline weakness.** Sixty of the 103 original misses
are terms `data/skills.yaml` does not carry — no rule can reach them. It is recorded in
PROGRESS under "Not real yet" rather than absorbed into a floor.

**Necessity accuracy is 0.668, and the job page makes that visible rather than hiding
it.** Measured on the seeded corpus: **2 of 32 rows shown as `required` sit beside a
quoted sentence that itself says "preferred" or "a plus"**. A reader can see the
disagreement because the sentence is printed next to the claim. That is the argument for
showing the quote, and it is also the honest statement of where this extractor is. A first
attempt at this measurement used a cruder sentence rule than the component's and reported
12 of 32 — the number was re-derived using the component's actual boundary rule, because a
measurement of what a reader sees has to use the rule the reader sees.

**The answer key is model-labeled, not human-verified.** Recorded as such. Two
`+equivalent` calls read an escape hatch worded without the word "equivalent" and are
named in PROGRESS as the entries most likely to be wrong.

**Nothing is compared against a person yet.** No eligibility gate, no score, no
`uncertain` resolution of `+equivalent`. `has_equivalence` is stored and read by nothing
but the tests and a badge.

---

## 5. Evidence

```
make check        1280 Python, 159 web, ruff/mypy/eslint/tsc clean
make acceptance   57 verify checks + 41 seeded browser tests, 1 skip
                  run three times back to back, all three passed
make test-e2e     5 degraded-path tests            <- the third command, run separately
alembic           down, up, no drift; both triggers present after the cycle
```

Mutation checks performed this session, each reverted:

| Mutation | Result |
|---|---|
| Delete moved after the empty-text guard | **0 tests fail** — the trigger covers it (§2.1) |
| Delete removed entirely | 2 fail — the idempotency pair |
| `if description_changed:` → `if True:` | 1 fails — the churn test |
| Requirement sort key reversed | 1 fails — document order |
| Version read from the constant | 1 fails — the unread/empty distinction |
| Quote is not a literal slice | 1 fails — the browser criterion |
| `DROP TRIGGER jobs_description_change_clears_requirements` | 1 fails |

The first row is the most useful one in the table: it is the mutation that *should* have
failed something and did not, and chasing why is what produced §2.1.
