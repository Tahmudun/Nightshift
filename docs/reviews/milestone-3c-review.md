# Milestone 3c review — the score, its evidence, and its explanation

**Date:** 2026-08-10
**Branch:** `m3c-the-score`
**Scope:** twelve tasks — the weights file and its loader, the tables and their guards, six
components, two penalties, the golden file, mutation testing on every tunable number, the
recompute sweep and its triggers, the API, the explanation panel and the ranked list, the
embedding measurement that shipped nothing, and this session: the browser walk,
`check_match_results`, ADR 0019, and a demo profile the milestone turned out to need.

---

## 1. The shape of what went wrong this time

M3a's finding was that **a check could be blind to the thing it was named for.** M3b's was
that **a check can measure the right thing at the wrong altitude.** M3c's is different
again, and it is the least comfortable of the three:

> **Every false statement this milestone shipped was true of a database, and false about a
> person.**

Three defects, all found by looking at the page rather than by any test:

| What the page said | Why it was wrong |
|---|---|
| *What it asks for that you have nothing on file for:* **2** | The "2" was a `years_experience` requirement. The profile states its years; the eligibility gate directly above reads them. |
| *Nice-to-haves you have nothing on file for:* React, TypeScript, Python | All three were confirmed skills, quoted by name three sections higher **on the same screen**. |
| *0 · matched by a vocabulary rule*, under a confirmed skill | True — a preferred technology is worth nothing (§4.1) — and it reads as a judgement of the reader. |

Each was produced by code doing exactly what it said. `unmet_requirements` differences the
posting's asks against the evidence graph, correctly; the evidence graph simply cannot
contain a degree, a years figure, or a nice-to-have, so the difference returned things
nobody had failed to answer. **The defect is in what the sentence above the list claims,
and no unit test can see a sentence.**

The generalisation to carry into M3d: this milestone's output is a *claim about a reader*,
and the thing a claim can be wrong about is not in the schema. Three of the four M3b
review findings were of this kind too. The instrument that finds them is a person reading
the page with a realistic profile loaded — which is why half of this session was spent
making such a profile exist.

---

## 2. Findings from Task 12, in full

Tasks 1–11's findings are recorded in `docs/PROGRESS.md` and in their commit messages.
These are this session's.

### 2.1 The milestone had no reader to be about — FIXED

`make seed` created a dev user with an email, a display name and nothing else. Against
that profile, over the 31 seeded postings:

```
                            before          after
evidence rows                   13             102
  with a quote from a posting    0              27
  with a quote from the reader   0              27
components ever assessable   2 of 6           6 of 6
distinct fractions               8              11
postings in a dimmed band        0               7
```

**Zero evidence rows quoted anything.** All thirteen came from freshness and priority,
which are §2.1's exempt components and quote nobody by design. So the milestone's headline
claim — every point traces to two literal spans — was demonstrated by `make demo` rendering
its empty state, and the browser walk had nothing to check §7.2 against.

`make seed` now gives the dev user the profile that
`tests/fixtures/resumes/nadia_okonkwo.txt` describes: a Hunter College CS student
graduating May 2027, six confirmed skills, two projects with their bullets, stated role and
location preferences. Written through `update_profile`, `add_skill` and `add_project` —
the same functions the profile form calls, and the only writers `test_nothing_infers.py`
permits (I2). It refuses to overwrite a profile anybody has touched, and it names what it
did in the seed output.

Two consequences worth stating. `years_experience: 0` is what puts seven postings into
`likely_ineligible`, so the dimmed bands PROGRESS listed under "Not real yet" are now
exercised by something a person can look at. And four of the resume's skills are
deliberately **not** confirmed, because two existing checks need a proposal nobody has
accepted yet.

### 2.2 A gap list that named things no component could ever answer — FIXED

The bare **"2"**. `matching.unmet_requirements` now filters to
`scoring.EVIDENCE_BEARING_REQUIREMENT_KINDS`, which is `{technology}` and is named in one
place so a component that starts answering a new kind has somewhere to say so.

The fixture posting in `test_match_routes.py` stated only technologies, which is precisely
why nothing caught this: the test file could not construct the failing case. It now states
a years minimum, and the new test asserts it does — a guard against the guard going
vacuous, which is M3a's lesson written into a fixture.

### 2.3 A docstring that described a feature nobody had written — FIXED

`score_skill_overlap`'s own docstring, since Task 3:

> *A matched preferred technology still produces an evidence row worth zero points, because
> the explanation panel needs it to say "you also have this" without claiming it earned
> anything.*

The code iterated the required list and nothing else. Every nice-to-have therefore had no
evidence row, and the gap list reported all of them — including the confirmed ones.

Both `score_skill_overlap` and `score_project_evidence` now emit zero-point rows for
confirmed nice-to-haves. No total moved. **The golden test refused to regenerate anyway**,
because the evidence graph changed while `ruleset_version` stayed put, which is exactly
the failure it was written to prevent — so `RULESET_LOGIC_VERSION` went to `2`. That guard
working unprompted is the single most reassuring thing that happened this session.

### 2.4 The two halves of §7.2 have very different teeth — RECORDED

Probed directly against the database rather than reasoned about:

| Attack | Result |
|---|---|
| Scorer emits a span that does not match its offsets | **Refused** by a trigger, on INSERT |
| `UPDATE match_evidence SET job_span_text = 'FABRICATED'` | **Refused**, on UPDATE too |
| `UPDATE` the offsets to point somewhere else | **Refused** |
| `INSERT` a row with `proposed_by = 'embedding'` | **Accepted** |

So the job-span half of §7.2 is enforced in DDL and `check_match_results` re-asserts it as
a second opinion; the `proposed_by` half is enforced by nothing but the scorer and this
check. And the check's reach is smaller than its first docstring claimed: every check
above it in `verify.py` edits a profile column or a confirmed skill, each of which deletes
every score, so it only ever reads rows it rescored itself moments earlier. It asserts
*the scorer stores no such row over 31 real postings* — which is worth having — and it
cannot catch one somebody inserted by hand. The hand-inserted row was tried; it was gone
before the check ran. The docstring now says so.

No constraint was added. ADR 0018 declined to ship the path and three unit tests keep that
from reversing silently; a DDL refusal would make a future migration the price of a
decision that is meant to be revisitable.

### 2.5 A browser test that could not fail — FIXED, and it was mine

The load-bearing test in `matching.spec.ts` — *every quoted word on the panel is text
printed on the same page* — **survived a mutation that lower-cased every quote the panel
printed.**

It took the span from the API, then asked whether some `<mark>` on the page matched it via
Playwright's `hasText`, which is case-insensitive and substring-based. Then it checked the
API's span against the API's description. So it asserted something the API guarantees and
the page cannot break, and a panel rendering "Python programming" for a span reading
"Python" would have passed it too.

Both marks now carry their side (`quoted-job-span`, `quoted-user-span`) and the comparison
is rendered-to-rendered: the text on screen against the description and title on screen,
and the reader's quotes against `/profile`. Re-run, the same mutation kills it.

**This is the file whose docstring says a paraphrasing panel would pass every other
assertion in it.** It was right, and it was describing itself.

### 2.6 The seeded browser suite raced itself — FIXED

`playwright.seeded.config.ts` ran `fullyParallel` against one database and one dev user.
Three specs write that user; two of them delete every `match_result` as a side effect of
doing so. `workers: 1`, with the reason in the config. The race predates M3c — two specs
already wrote the same six profile columns while a third read verdicts computed from them
— but M3c is where it stops being survivable.

`matching.spec.ts` still normalises on entry rather than trusting suite order: it runs the
sweep (`nightshift.cli score`, new this task) before it asserts, because the specs before
it legitimately leave the table empty.

### 2.7 An assertion that had been stale for three tasks — FIXED

`search-and-detail.spec.ts` asserted the job page lists "match score" under *Not yet
computed*. True when M2a wrote it; false since Task 10 built the score and took it off that
list. It went on passing because the seeded suite had not been run since — Task 9 and Task
10 both recorded "not run this session" in PROGRESS, honestly, and this is what that
honesty costs when it accumulates over three tasks.

### 2.8 A hand-copied vocabulary, for the third milestone running — FIXED

`eligibility.spec.ts` matched the save control by
`/saved|applied|interview|offer|rejected/i` — five of `STAGE_LABELS`' ten stages. Under
`make acceptance`, `verify.py` runs first and leaves an archived application on exactly the
posting that spec picks, at stage **Preparing**. The control was on screen and the test
reported that an ineligible posting had had its apply path taken away.

M3b's review found the same defect in `ASKS`. M1d found it in an enum copy. The rule that
keeps failing is: *if a vocabulary lives in a `Record<Enum, string>`, nothing may keep a
subset of it.* The spec now uses a test id.

### 2.9 `git checkout --` destroyed unstaged work mid-run — RECORDED

The first mutation script restored each mutated file with `git checkout -- <file>`. That
restores from the **index**, and two of the files had unstaged Task 12 work in them. Both
were reverted in the middle of the run, silently, and the next three mutations then ran
against a tree missing the change they were meant to be testing — which is why case 3
reported "the API did not start" instead of a result.

The work was reconstructable and was reconstructed; the golden file (which was staged)
then matched byte-for-byte, which is a decent independent check that the reconstruction
was faithful. The script now saves copies. The general rule, and it is not a git rule:
**a script that restores state must not restore it from somewhere the session is also
writing to.**

### 2.10 A ranked order that is honest and still misleading — NOT FIXED, and named

On the seeded corpus a Partner Development Representative at **19 of 40** (48%) outranks a
Software Engineer Internship at **30 of 100** (30%), for a CS student who typed "Software
Engineer" as a preferred role.

Every number there is correct. The fraction means "of what could be assessed", the two
denominators are not comparable quantities, and sorting on the ratio of incomparable
quantities is not a total order anybody should read as "best first". A posting that could
barely be assessed can beat one that was assessed thoroughly.

Not fixed here, deliberately: the fix is a confidence-weighted ordering, that is a design
decision with no obvious right answer, and §7.3 already says ranking *quality* is
unmeasured in M3 and names the relevance-rating pass as M3d's. **This is what "unmeasured"
looks like on screen, and it should be the first thing that pass examines.** Both numbers
are printed on every row, which is the mitigation available today and not a solution.

---

## 3. What Task 12 added

**`check_match_results` in `scripts/verify.py`** — 18 checks. §7.2 as an equality over
every stored evidence row, on both sides; I4 over all 31 scores; the ranked order; the two
surfaces agreeing; ADR 0019's withdraw-and-rebuild cycle; and §7.1's stability, measured
by deleting the corpus twice and landing on identical numbers.

**`apps/web/e2e-seeded/matching.spec.ts`** — 7 tests. The panel, the bands, the ordering,
and the two false claims §1 lists, each of which it would now catch.

**`make score` / `nightshift.cli score`** — the sweep on demand. Wanted by a developer who
has just edited their profile, and by a browser suite with no worker behind it.

**ADR 0019** — why a score is stored when the verdict beside it is not, and why a moved
input deletes it rather than refreshing it.

### Mutations, each measured going red

| Mutation | What went red |
|---|---|
| A user span invented (`"Python (expert)"`) | §7.2's user-side equality in `verify` |
| Profile invalidation disabled | six checks, including "editing a scoring input withdraws every score" |
| Ranking sorted on the raw total | "each band is ordered on the fraction" |
| A job span that does not match its offsets | **the database**, before `verify` could see it |
| The panel lower-cases its quotes | the browser walk — *after* §2.5's fix, and not before |
| The total printed without its denominator | two browser tests |
| An unassessable component printing `0 of 30` | one browser test |
| A dimmed band hidden instead of listed | two browser tests |
| The gap-kind filter removed | `test_a_gap_is_only_ever_something_the_evidence_graph_could_have_answered` |

---

## 4. What this milestone still cannot tell you

- **Whether a high score means a good role.** §7.3, unchanged. Stability is measured;
  quality is not. §2.10 is the concrete face of it.
- **Whether the rules read a posting correctly** beyond the 60 labeled ones. The corpus is
  nine employers, all quant trading firms or AI labs, plus three fixture boards.
- **Whether the ordering holds up for anyone but this fixture person.** One profile, one
  corpus. Four fixture profiles exist in the unit suite; the seeded stack has one.
- **Whether a hand-inserted evidence row would ever be noticed** (§2.4). It would not be,
  by anything running today.
