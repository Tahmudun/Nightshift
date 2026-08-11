# M3d — the evaluation suite, the four queue rows, and an order nobody can defend

> Plan. Branch `m3d-evaluation`, off `main` at `03fa035` (PR #12 merged, CI green,
> no findings).
>
> Required reading first: `docs/architecture/matching.md` §7 and §8; ADR 0018;
> `docs/reviews/milestone-3c-review.md` §2.10 and §4; QUESTIONS Q5's second-pass
> section; `CLAUDE.md` §6's M3 acceptance criteria.

## What M3d is

M3a built the answer key. M3b built the gate. M3c built the score. **M3d is the
milestone that finds out whether any of them work**, and it is the last slice of
M3, so it also carries the milestone's acceptance walk.

The failure mode here is different from every slice before it and is worth
naming before any task: **an evaluation suite is the one component whose bugs
make everything else look better.** A metric that measures the wrong thing, a
floor set above what it grades, a hallucination check that runs after the table
it inspects has been emptied — each reports a green number and hides the defect
it was built to expose. This project has recorded three tests that could not
fail. Two of them were mine and one was in the review of the milestone that
found the other two.

### The one sentence that governs every decision below

**A number this milestone publishes must name what it was computed over.**

Not "eligibility recall is 0.91" but "eligibility recall is 0.91 over 60 labeled
postings from nine employers, all quant trading firms or AI labs, against four
fixture profiles, comparing the gate's reading of an extracted requirement set
against its reading of the labeled one." The second sentence is checkable and the
first is a claim about the world that this repository has no basis for.

---

## 1. What already exists, measured before planning rather than assumed

`matching.md` §7.1 lists six metrics. **Three are already built and gated in
CI**, which the milestone brief does not say and which changes what M3d owes.

| §7.1 metric | State today |
|---|---|
| Skill-extraction precision and recall | **Built.** `test_requirement_extraction_against_the_answer_key.py`, floors 0.84 / 0.86, re-baselined at M3a.1 |
| `required` vs `preferred` accuracy | **Built.** Same file, `NECESSITY_ACCURACY_FLOOR = 0.91` |
| Ranking stability | **Built.** `test_matching_golden.py`, two full runs that rebuild the corpus and re-extract rather than comparing a cached string to itself |
| Eligibility precision **and recall**, per state | **Missing entirely.** See §2 |
| Hallucination rate = 0 | **Half-built.** The job-span half is a trigger (INSERT and UPDATE, both probed). The user-span half exists only in `verify.py` and the unit suite, and `verify.py` runs against a corpus it rescored itself. §7.2's table |
| Embedding-proposed share | **Missing as a published number.** ADR 0018 makes the true value 0 and three tests assert no such row; nothing reports it |

Two further inherited items that §7.1 does not list:

- **Five reading accuracies are measured and ungated.**
  `test_eligibility_reading_against_the_answer_key.py` carries exactly one floor
  (enrollment, 0.90) and reports `degree`, `graduation_window`,
  `years_experience`, `authorization` and `is_internship` without gating them.
  Its docstring says why: *"reported and ungated until Task 5's remaining repairs
  are done, because a floor set mid-repair is a floor that has to be edited again
  next week."* **M3b Task 5 shipped and merged.** The condition it was waiting on
  is met and nothing has gone back to close it.
- **Nothing reads `ratings.yaml`.** Q5 was answered on 2026-08-10 — thirty
  postings, filled profile, 12 / 11 / 7 — and the file is graded by no test. It
  is a fixture with a passing schema check and no measurement behind it.

---

## 2. Decisions taken here, as engineering calls

### 2.1 Eligibility precision and recall grade the extractor, not the rules — and the plan says so out loud

§7.1 asks for eligibility precision and recall per state. §3.1 says the verdict
is **computed** from (labeled requirements × profile). Put together, those two
sentences describe a measurement whose ground truth is a computation, and it is
worth being exact about what that can and cannot establish.

Two different quantities are available and only one of them is free:

- **(a) Extraction-induced verdict error.** Ground truth is
  `gate(labeled requirements, profile)`; the prediction is
  `gate(extracted requirements, profile)`. The rules are identical on both sides,
  so what this isolates is **how often mis-reading a posting changes the
  verdict** — which is precisely the path by which a wrong `ineligible` reaches a
  person, and A13 makes that the worst output this engine can produce. No human
  input needed. **This is what M3d builds.**
- **(b) Rule correctness.** Whether `gate(labeled, profile)` is itself the right
  answer. There is no ground truth for this in the repository and getting one
  means a human reading 60 postings and writing down a verdict per profile —
  which §3.1 refuses on purpose, because a verdict bakes the labeler's own
  graduation date into a fixture that then silently rots. **M3d does not measure
  this and PROGRESS says so.**

Publishing (a) as "eligibility precision and recall" without that paragraph would
be the flattering reading of a real number, which is the specific thing §1's
governing sentence forbids.

**Recall is reported per state and separately from precision**, per §3.3: a gate
that answers `uncertain` to everything has perfect precision on every other state
and is worthless.

### 2.2 `demonstrated_by:` lands first, because it moves scores

ADR 0018's constructive successor: 33 occurrences across the corpus of concept
terms — `Machine Learning` (26), `Distributed Systems` (4), `Data Structures` (3)
— that a concrete tool demonstrates and the scorer misses entirely.

It is Task 1 rather than Task 7, and the reason is ordering rather than
importance. It moves scores across the corpus, so it needs a
`RULESET_LOGIC_VERSION` bump and a golden regeneration. Any ranking metric
measured before it would be measuring a scorer that no longer exists, and the
floors set from those numbers would need editing the same week — which is the
mistake `test_eligibility_reading_against_the_answer_key.py`'s docstring already
names one milestone up.

**It is also the one change in M3d that a person can feel.** The rater's own
confirmed skills include all three of those concept terms.

### 2.3 The ordering decision comes after the ranking metric, not before

Review §2.10: a Partner Development Representative at 19 of 40 outranks a
Software Engineer Internship at 30 of 100, because sorting on a ratio of
incomparable denominators is not a total order. The review declined to fix it and
said the fix is a confidence-weighted ordering with no obvious right answer.

**A design decision with no obvious right answer is exactly what a measurement is
for.** Task 5 builds the ranking metric against `ratings.yaml`; Task 6 tries
candidate orderings and picks the one the metric prefers. Doing it the other way
round means choosing an ordering on taste and then building the instrument that
grades it, which is A13's collect-first rule pointed at ranking instead of
labels.

If no candidate beats the current one on the metric, **the current one stays and
the finding is that §2.10 is not fixable on this corpus** — that outcome has to
be reachable from the plan rather than embarrassing.

### 2.4 Three of the four queue rows can now be built honestly, and one still cannot

`routes/queue.py`'s `DEFERRED_ROWS`, all four blocked on "milestone 3":

| Row | M3d |
|---|---|
| **Best new internships** | **Build.** A score exists and the ranked query exists. **There is no `jobs.is_internship` column** — checked, not assumed: M3b shipped `role_family`, `seniority`, `internship_season` and `internship_year`, and internship-ness is carried by `seniority = 'internship'` with the two season columns gated on it. The row filters on `seniority`, and a posting whose seniority is `unclear` is not silently excluded — it is absent, and the row says how many it could not classify |
| **High-match roles closing soon** | **Stays deferred, and its reason gets corrected.** Its text blames the missing score; the score now exists and the row is still impossible, because A10 records `application_deadline` as rarely present and Datadog's registry note says that board publishes none at all. The honest `blocked_on` is *the sources*, not *milestone 3*, and leaving it saying "milestone 3" after M3 closes is a false statement with a date on it |
| **Resume mismatch warnings** | **Build, renamed.** `matching.unmet_requirements` is exactly this list. It must **not** be called a resume warning: it is computed from `user_skills` (confirmed, belongs to the person) and never from `resume_extractions` (proposals, and §7.2 forbids a user span quoting one). Shipping it under the old name would be ADR 0019's defect returning by the front door — a true statement about a database rendered as a false one about a document |
| **The one thing to do today** | **Build.** Its own deferral text says it is *"ranking across every row above… the most useful line on this page and the least honest to fake, so it waits."* The ranking now exists. It is one row, it links to something, and it never invents an action — I5 |

### 2.5 What is deliberately *not* in this slice

- **No top-k relevance beyond the 30 rated postings.** §7.3. The corpus is nine
  employers and the number generalises to that slice only.
- **No new floors on anything M3d measures for the first time.** Report first,
  baseline second, gate third — M3a's rule. A floor set before measuring is
  either unreachable or vacuous and there is no way to tell which from outside.
  The exception is §1's five reading accuracies, which have been measured for a
  milestone already.
- **No rule correctness measurement** — §2.1(b).
- **No fix for the corpus being nine quant firms and AI labs.** Recording a
  different slice is M6-or-later and needs its own ADR (`matching.md` §3.6).

---

## 3. Tasks

| # | What | Ends in |
|---|---|---|
| 1 | `demonstrated_by:` edges in `data/skills.yaml`; `RULESET_LOGIC_VERSION` → 3; golden regenerated | The 33 concept-term occurrences earn evidence rows; the regeneration guard is made to refuse first, then satisfied |
| 2 | Floors on the five reading accuracies `test_eligibility_reading_against_the_answer_key.py` has reported and ungated since M3b | Each floor measured, set just under, and shown able to fail |
| 3 | Eligibility precision and recall **per state**, `gate(extracted)` against `gate(labeled)`, four fixture profiles × 60 postings | Reported per state, precision and recall separately; the grader shown able to fail |
| 4 | §7.2's equality over the whole corpus in the unit suite, **both halves**; the embedding-proposed share published | A fabricated user span goes red in CI, not only in `verify.py` |
| 5 | Ranking quality against `ratings.yaml` — NDCG@10 and precision@5, a pure function over a committed file | A number, reported and ungated, with the corpus named beside it |
| 6 | The ordering decision (§2.10), candidates graded by Task 5's metric | Either a new ordering with the measurement that chose it, or the finding that none beats the current one |
| 7 | The three buildable queue rows; the fourth's reason corrected to name the sources | Four rows again, three real, one deferred honestly |
| 8 | ADRs, the M3d review, the **M3 acceptance walk**, PROGRESS | `make acceptance`, and M3's six criteria each with evidence |

Task 6 is deliberately sized as unknown and deliberately allowed to end in a
finding rather than a change. Task 3 is the one most likely to grow: **nothing in
the repository currently runs the gate over the *labeled* requirement set**, so
that path is new even though both of its ends already exist.

The four scoring profiles Task 3 needs are already shared and already committed —
`tests/fixtures/matching/profiles.yaml`, in `ScoringProfile`'s shape. **Its header
comment says "Three of them" and the file holds four**, `early_career_no_experience`
having been added by M3c Task 7 without the comment moving. Found while checking
this plan's claims rather than by a test, which is the point: a stale comment
beside the thing it describes is how the last three milestones each lost an hour.
Task 3 fixes it in passing.

---

## 4. What would make this plan wrong

Written down now, so that finding one of these later is a correction rather than
a surprise.

- **If `demonstrated_by:` moves scores by more than a rounding error on the
  ranked order.** Task 1 changes what the corpus scores, and the four fixture
  profiles were built against the old behaviour. If the golden diff is large, the
  right response is to read it posting by posting before regenerating — the guard
  exists precisely because regenerating is the reflex — not to accept it because
  the direction is favourable.
- **If Task 3's ground truth turns out to be nearly always the same verdict.**
  The gate can answer `uncertain` a great deal, and if `gate(labeled, profile)`
  is `uncertain` on 55 of 60 postings then per-state recall is computed over
  single-digit denominators and means very little. That is a corpus finding, it
  must be reported as one, and the numbers must not be published without their
  denominators beside them.
- **If the ranking metric cannot discriminate on 30 postings.** NDCG over 30
  items with three relevance levels is a coarse instrument. If every candidate
  ordering in Task 6 scores within noise of every other, the honest output is
  that the instrument is too blunt to choose, and §2.10 stays open with that
  recorded — not a winner declared on a third decimal place.
- **If the queue rows need a score the sweep has not computed.** `not_yet_scored`
  is real: the ranked list already reports it because a corpus can be partially
  scored. A queue row that silently shows fewer items because the worker is
  behind is the M2d closure-state failure wearing new clothes, and each built row
  must say what it could not see.
- **If gating the five reading accuracies turns CI red on a corpus change.** A
  floor is a promise about a fixed corpus. Task 8 of M3a added postings; if
  anything in M3d adds one, the floors move and the reason must be recorded in
  the same commit rather than discovered by the next person.
