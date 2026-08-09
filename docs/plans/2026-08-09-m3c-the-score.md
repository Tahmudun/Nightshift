# M3c — the score, the evidence graph, and the explanation

> Plan. Branch `m3c-the-score`, off `main` at `d2273e7` (PR #11 merged, CI green).
>
> Required reading first: `docs/architecture/matching.md` §2, §4, §5, §6 and §8;
> AMENDMENTS A5, A10, A13; `CLAUDE.md` §1 (I2, I4, I5); PROGRESS's M3b section,
> in particular "the three-day-old server".

## What M3c is

M3b answered *is this posting open to you*. M3c answers *how well does it fit*,
and those are different questions with different failure modes. The gate's worst
output is a wrong `ineligible`, which deletes an opportunity silently. The
score's worst output is **a number with nothing behind it** — because a number
is believed, is sortable, and looks like a measurement whether or not it is one.

`matching.md` §1 scopes the slice: the score, the versioned weights, the evidence
graph, the explanation panel, and `match_results` precomputed so a ranked query
is possible. **No evaluation suite** — the metrics, the ranking checks and the
hallucination equality in CI are M3d's.

### The one sentence that governs every decision below

I4, taken literally: **every score decomposes, and a component with no evidence
row is not a component — it is a database error.**

Three consequences that are load-bearing rather than decorative:

1. **A score with no evidence cannot be committed.** Not "is caught in review",
   not "is asserted by a test". `matching.md` §4.3 puts it in a trigger, and the
   reason it is a trigger is that the code which breaks this invariant is code
   doing its job correctly — the same argument that made
   `jobs_description_change_clears_requirements` a trigger at M3a.
2. **An embedding may propose; it may never score.** §2. A proposal earns points
   only by resolving to a character span on *both* sides. If either span cannot
   be produced, the proposal produces nothing — no points, no explanation line,
   no mention.
3. **Eligibility is never converted into points.** §5.2. A job can score 82 and
   be `uncertain`, and the page shows both without reconciling them. The moment
   uncertainty is worth a number it stops being uncertainty.

---

## 1. Decisions taken here, as engineering calls

`matching.md` already settled the weights, the two deferred components, the
table shapes and the span rule. These are the calls it leaves open.

### 1.1 The embedding proposal path lands late, and may not land at all

**Tasks 1–10 are rules-only.** Vocabulary hits from `data/skills.yaml`, the
requirement rows M3a extracts, and the confirmed user records M2c stores. The
embedding proposal path is **Task 11**, after the whole score is measurable
without it.

Two reasons, and the second is the real one.

The scheduling reason: `matching.md` §2.3 says the cost of the span rule is
recall, "measured rather than assumed" — but that measurement is only meaningful
against a rules-only baseline. Shipping both together produces one number and no
way to attribute it, which is M3a.1's lesson (four repairs, each measured on its
own) applied before the fact rather than after.

The structural reason: **the span rule means an embedding proposal can only ever
re-rank things that already have spans.** It cannot invent evidence — that is the
whole design. So the honest question is how many *additional* (job span, user
span) pairs a proposal finds that the vocabulary missed, and that question has no
answer until the vocabulary's own yield is on the table. If Task 11 measures a
small number, **it is correct to not ship it** and record the figure, and that
outcome has to be reachable from the plan rather than embarrassing.

The infrastructure is already real and this is not a new dependency: `bge-small`
via fastembed backs M1b's dedupe, and `job_embeddings` already stores one vector
per job description keyed by its content hash.

### 1.2 The score is computed by a pure module, exactly as the gate is

`domain/scoring.py`, importing no ORM, taking a posting reading, a seeker
profile, and the loaded weights, and returning a result plus its evidence rows.
The ARQ task and the API are the only things that touch the database.

Not a stylistic preference. It is what let M3b grade the gate against 60 postings
in a test with no database, and what let `test_every_gate_rule_is_load_bearing`
neuter a rule and re-run. A scoring function that reads a session cannot be
mutation-tested the same way, and §8 asks for exactly that.

### 1.3 `data/matching.yaml` is a data file with a version, and the logic
constant lives in Python

§4.2's composition, `"<logic>+<data>"`. Two things this plan commits to that the
architecture doc implies without stating:

- **The weights file is validated on load and fails loudly.** A typo'd weight
  that silently reads as zero removes a component from every score in the corpus
  and every test still passes. The loader asserts the six components sum to 100
  and that both penalty ceilings are negative.
- **The golden test is written before the weights are tuned**, not after. §4.2
  says a golden test pins the full output so that changing a rule without
  bumping `RULESET_LOGIC_VERSION` goes red with a diff. Written afterwards it
  pins whatever the code then does, which is a test that cannot fail on the
  thing it exists to catch.

### 1.4 Recompute is triggered by three events and one of them is a trap

§4.2: a new or changed job, any profile change, and a ruleset version bump.

The trap is "any profile change". M2c's profile PATCH is a single endpoint that
writes fifteen columns, most of which no component reads. Enqueuing a full
corpus rescore because somebody changed their display name is a retry storm
waiting for a demo. **The task is enqueued from a named set of scoring-relevant
columns**, listed beside `PROFILE_COLUMNS` in `test_nothing_infers.py` and
checked against `User.__table__` the same way — because that hand-maintained
list is the thing that quietly stopped describing what it named at M3b, and it
will do it again if nothing watches.

### 1.5 What is deliberately *not* in this slice

- **No evaluation suite, no metrics in CI.** M3d. M3c may print numbers; it may
  not gate on them, for M3a's reason: a floor set before measuring is either
  unreachable or vacuous and there is no way to tell which from outside.
- **No top-k relevance.** §7.3, and it needs ~20 minutes of the human's time.
  Raised in QUESTIONS now rather than at M3d, so it can be scheduled.
- **No queue rows.** The four named-but-empty rows from M2d are M3d's.
- **No `likely_eligible`.** Still unreachable. M3b's ADR 0017 said M3c's score
  components "may earn it"; this plan does not spend one.

---

## 2. The grading design, which is thinner here than at M3b — deliberately

M3b could grade against an answer key because "does this posting require a
bachelor's degree" has a right answer a human can write down. **"Is this job an
82 for you" does not.** Relevance is irreducibly personal (§7.3), so there is no
key in this repository against which a score can be scored.

So M3c's checks are of a different kind, and pretending otherwise would produce
exactly the vacuous metric §1.1 of `matching.md` warns about:

| Check | Shape | Where |
|---|---|---|
| Every positive component has an evidence row | Deferrable constraint trigger | Database |
| Every `role`/`skill`/`project` row has both spans | Check constraint | Database |
| Every stored span is a literal substring at its offsets | Equality, must be zero | Test + `verify.py` |
| Identical inputs + identical `ruleset_version` → byte-identical output | Two full runs compared | Test |
| Every component is load-bearing | Mutation: zero the weight, a named test goes red | Test |
| The corpus reaches more than one band and more than one score | Anti-vacuity | Test + `verify.py` |

**The last row is the one this project has learned to write.** A scorer returning
50 for everything satisfies every other line above. M3b's
`test_the_corpus_actually_exercises_the_gate` is the same guard one milestone
down, and it exists because a gate answering `uncertain` to everything has
perfect precision and is worthless.

---

## 3. Tasks

| # | What | Ends in |
|---|---|---|
| 1 | `data/matching.yaml` — weights, thresholds, `version`; the loader and its validation | Sum-to-100 assertion, shown able to fail |
| 2 | Migration: `match_results`, `match_evidence`, `user_skills.skill_id`; both evidence guards | Up, down, up; each guard proven able to fail |
| 3 | `domain/scoring.py` — the three span-bound components (role, skill, project), rules only | Fixture tests, no database |
| 4 | The three exempt components (location, freshness, priority) and their recorded comparisons | §2.1's distinction visible in the rows |
| 5 | The two penalties, and the seniority penalty that M3b refused to make a blocker | A senior title costs points and never blocks |
| 6 | The golden test, **before any weight is tuned** | Byte-identical output, twice |
| 7 | Mutation: zero each weight, a named test goes red | Six kills, plus the harness guards |
| 8 | The ARQ recompute task and its three triggers; the scoring-relevant column list and its parity guard | A profile change rescores; a display-name change does not |
| 9 | The API: `match_result` on the job detail, refusing a stale `ruleset_version` | A stale row reads as not-yet-computed, never as a score |
| 10 | The explanation panel and the banded ranked list (§5.3, §6); seven elements, two named as not built | Component tests; bands are headers, never points |
| 11 | The embedding proposal path, measured against Task 3–5's baseline | A number, and the option of not shipping it |
| 12 | Browser walk, `check_match_results` in `verify.py`, ADR 0018, review, PROGRESS | `make acceptance` |

Task 11 is deliberately sized as unknown and deliberately allowed to end in a
deletion. Task 5 is the one most likely to grow: `matching.md` §5.1 gives the
penalty ceilings and nothing about their curves.

---

## 4. What would make this plan wrong

Written down now, so that finding one of these later is a correction rather than
a surprise.

- **If the seeded corpus cannot produce a spread of scores.** 31 postings, most
  of them customer-success roles from the Alloy board, against a developer
  profile that is nearly empty. M3b measured 12 of 31 postings with no technology
  extracted at all. If Task 3 finds skill overlap is zero on most of the corpus,
  the honest response is to say so and score against the 93 unlabeled recorded
  postings, not to widen the matching until the number moves.
- **If the evidence trigger cannot be written deferrably.** §4.3 wants "any
  positive component score has at least one evidence row", which is a
  cross-table assertion checked at commit. If Postgres makes that unworkable in
  the shape assumed, it becomes an explicit `SET CONSTRAINTS` transaction
  discipline plus a test — and that is a weaker guarantee that must be recorded
  as one rather than described as equivalent.
- **If precomputation makes the developer loop unusable.** A full rescore on
  every profile change, run synchronously in tests, is how a fast suite becomes
  a slow one. If it does, the fix is a smaller trigger set, not a mock.
