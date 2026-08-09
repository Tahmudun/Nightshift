# Milestone 3b review — the deterministic eligibility gate

**Date:** 2026-08-09
**Branch:** `m3b-eligibility-gate`
**Scope:** twelve tasks — five ungraded label fields graded, two new label fields, three
enums and their migration, the classifier, a four-step repair pass, the gate itself, the
wrong-ineligible equality, mutation testing on every rule, the API field, the job page,
two deferred filters switched on, and the browser walk.

---

## 1. The shape of what went wrong this time

M3a's finding was that **a check could not see the thing it was named for** — eight
suites green while the artefact they guarded was broken. M3b's is one step further in and
it is worth naming precisely, because it is a harder failure to write a guard for:

> **A check that measures the right thing can still be measuring it at the wrong
> altitude.**

Three of this milestone's most valuable corrections were invisible to a metric that was
working exactly as designed:

| The metric said | What was true |
|---|---|
| `degree` accuracy 0.850 → 0.867, barely moved | "MS Office" had been read as a master's degree, hard-blocking a bachelor's graduate from an administrative posting |
| `graduation_window` 0.917, a five-label accuracy gap deferred to a later task | Those five labels were the gate telling a 2024 graduate they could not apply to a posting whose own words say "August 2027 **or prior**" |
| Every unit and component test green, twice | The page offered "Add your degree" to a reader whose degree was already on file |

Each of those was found by a *different kind* of check than the one that missed it: the
wrong-ineligible equality, running the gate over the corpus, and driving a browser. None
was found by improving the metric.

**The generalisation, and it is the one to carry into M3c:** accuracy cannot distinguish a
false positive that costs precision from one that costs somebody a job. It has no term for
that. Both are one wrong cell. The equality beside the floors is not redundancy — it is
the only instrument in this milestone that can see the difference, and it is the reason
`test_no_posting_is_wrongly_reported_ineligible.py` never calls the gate. A checker that
called the gate would agree with it by construction, which is exactly how M3a's
`test_no_nice_to_have_is_ever_reported_as_required` sat at zero for a whole milestone.

---

## 2. Findings from Task 12, in full

Tasks 1–11's findings are recorded in `docs/PROGRESS.md` and in their commit messages, at
the point they were found. These are this session's, and they are not written down
elsewhere.

### 2.1 An unknown that offered an action which could not work — FIXED

The gate's degree rule demotes `bachelors+equivalent` to an uncertain outcome, per A13,
and the hatch is checked **before `profile.degree` is read** — that ordering is what makes
it always win. Filed as `cannot_tell`, `evaluate` then attached
`profile_field="degree"` from `_ASKS_FOR`, and the page rendered:

```
the posting accepts equivalent experience in place of the degree,
which is not something this system can assess.  [Add your degree]
```

beside a profile that already had a degree in it. The reader follows the link, fills a
field that is already filled, comes back, and the verdict has not moved.

**This is the milestone's own principle failing one layer up.** The gate refuses to invent
a blocker; the page invented an action. Both are claims the system cannot support, and the
second one is harder to notice because it looks helpful.

`Outcome` gained `cannot_assess`. Both reach `uncertain`; the only thing that differs is
whether there is a field to name, and `Unknown.profile_field` is now nullable to carry it.
The page renders two headings — "What would let this answer", with a link, and "What
nothing in your profile can settle", without one.

**Found by driving a browser, and it could not have been found any other way available.**
Every unit test passed the whole time, because a `why` sentence reading "not something
this system can assess" is perfectly correct in a fixture and is a broken promise
underneath a link. The distinction is only visible when the sentence and the link are
rendered together, which is what the walk does and what no component test asserting on the
same fixture would ever have questioned.

### 2.2 The headline kept making the promise the sections had stopped making — FIXED

Found reviewing 2.1's fix rather than 2.1's bug, which is why it is recorded separately.

`uncertain` has one headline and one caveat, and both describe only the `cannot_tell`
cause:

```
Not enough in your profile to tell
Nothing here is a no. Fill in what is missing and this can answer.
```

For a posting whose every open question is `cannot_assess`, both sentences are false. It
is not the profile that is lacking, and filling in what is missing cannot make this
answer. **Splitting the sections below fixed the link and left the promise standing two
paragraphs above it** — and the promise is the part a reader acts on, because it is the
part they read first.

The headline and caveat are now conditional on whether any unknown is askable. Both new
tests were shown able to fail, in both directions: neutering the condition fails the
first, over-applying it (any unassessable unknown rather than no askable one) fails the
second. The reassurance — "Nothing here is a no" — is kept in both branches deliberately;
correcting a false promise is not a reason to withdraw a true comfort.

### 2.3 A hand-transcribed map across the language boundary, with no guard — FIXED

`ASKS` in `JobEligibility.tsx` turns a column name into words. It is a copy of the gate's
`_ASKS_FOR` values, written by hand, and **nothing compared the two.**

It is not a `z.enum`, so `test_enum_parity.py`'s parametrised test could not reach it, and
it fails more quietly than any enum in that file does. `ASKS[field] ?? field` falls back to
the raw column name — so a rule added without its phrase does not throw and does not blank
the page. It prints **"Add years_experience"** at a person, inside a sentence that is
otherwise asking them politely for help.

Two of the last four milestones found a hand-transcription defect at this boundary. The
new test is one-directional on purpose: every field a rule can ask for must have words; a
spare phrase for a field no rule asks for is dead and harmless. Shown able to fail by
deleting `is_enrolled` and watching it name the column.

### 2.4 A non-null assertion standing in for a check — FIXED

`ASKS[row.profile_field!]`. `Array.filter` does not narrow the element type, so the `!` was
load-bearing: it compiled by asserting something the compiler had not verified, and the
thing being asserted was **precisely the distinction 2.1 had just been fixed to respect.**

A type predicate (`row is AskableUnknown`) does the narrowing honestly. Small, and recorded
because the alternative reading — "it is safe, the filter guarantees it" — is true today
and is exactly the reasoning that makes the next such assertion survive a refactor that
breaks it.

### 2.5 The git-tracking guard fired for the second time in two tasks — CAUGHT

`test_every_source_file_is_tracked_by_git` failed on `apps/web/e2e-seeded/eligibility.spec.ts`:
written, passing, never added. Task 11 hit the same guard on `SearchCaveats.tsx` and its
test.

Twice in two tasks is a pattern rather than a slip, and the pattern is that a new *file*
is the thing this workflow loses — not an edit, which shows up in `git status` as a
modification nobody has to notice. The guard is the reason neither reached a commit. Noted
here rather than fixed, because the guard is the fix.

### 2.6 `verify.py` had no eligibility check — CLOSED, and the check failed on its first run

The gap Task 12 existed to close. `check_eligibility_gate` clears the six gate columns,
walks every seeded posting, and asserts the day-one user is blocked from nothing; that no
verdict appears without its breakdown; that every unknown names a profile field that
exists or names none; that every blocker's quote is the text its span points at; and that
the verdict is computed on read, by changing a column, re-requesting the same URL, and
putting the column back.

**Its first execution raised `KeyError: 'posting_span'`.** The domain object carries a
`posting_span` tuple; `EligibilityBlockerOut` flattens it to `char_start`/`char_end` on the
wire, the same shape `job_requirements` already uses. The check had been written against
the dataclass and run against the API.

Recorded rather than quietly fixed, because it is the cheapest possible demonstration of
why this file exists beside a fully green unit suite: **1383 Python tests knew the correct
shape and none of them was looking at this script.** The crash also proved the `finally`
block does what it claims — "the profile is left as it was found" ran and passed while the
function was unwinding.

### 2.7 A three-day-old server answered 73 checks, and nothing could tell — FIXED

The most consequential finding of the session, and it was found by disbelieving a skip.

The first full run of `make verify` printed `all checks passed` — 73 of them, sixteen of
them written that morning. It was answered by a `uvicorn` **started by hand on 2026-08-05
and still holding port 8000 three days and eight hours later.** `verify.py` starts its own
API, that one died instantly with "address already in use" into `DEVNULL`, and
`wait_for_api` got a perfectly healthy `/health` from the squatter.

`CLAUDE.md` §4 already states the rule, in the imperative, from the M0 review:

> Verify from a clean shell, not the one you were working in. A server you started by
> hand an hour ago will make a broken target look like a passing one.

**A habit written down is not a guard, and this is the second time this project has paid
for the difference.** Two now exist:

| Guard | Catches |
|---|---|
| `port_is_taken()`, refusing to run at all | a squatter already there — exactly this case |
| `wait_for_api(process)` polling `process.poll()` | our own server dying for any reason while something else answers |

Both were demonstrated: the port guard was run against the live stale process and refused,
with the `lsof` line in its output, **before** that process was killed.

**The scariest part is that the output was identical.** The stale run and the honest run
print the same 73 lines and the same counts. Nothing in the transcript distinguishes them.
The only thing that surfaced it was a *sixth* signal — a Playwright test skipping with
"no seeded posting is unassessable on any dimension", which is a claim about a committed,
deterministic fixture corpus and therefore could not be true.

### 2.8 The skip that hid it, and the config comment that licensed it — BOTH FIXED

Two artefacts made §2.7 survivable, and both asserted something false.

`eligibility.spec.ts` guarded its unassessable case with
`test.skip(job === null, 'no seeded posting is unassessable on any dimension')`. The seeded
corpus is committed fixtures and deterministically contains Datadog's *AI Research
Scientist*, whose degree requirement extracts as `phd` with `has_equivalence` — so that
sentence is never true of this repository. **The test covering this milestone's headline
fix reported itself as legitimately inapplicable.** It now throws, and the message names
both causes and the `lsof` command. The other four tests in the file keep their skips,
because a corpus with no `ineligible` case genuinely is a possible state; this one is not.

That is M3a review §2.8 — "a browser test that would skip itself green" — recurring in the
next milestone, on a different test, for a different reason.

`playwright.seeded.config.ts` set `reuseExistingServer: true` for the API under a comment
reading *"an API already running for `make dev` is the same API"*. It is not, and the
comment is why nobody questioned the reuse. Still reused — refusing would break the
ordinary `make dev` loop and re-binding 8000 would fail anyway — but the comment now says
what it cannot guarantee, and points at the two places that guard their own halves.

### 2.9 The plan's composition had five branches and the gate has four — CORRECTED IN ADR 0017

The plan (§3) wrote:

```
else all pass, some on an unstated input  -> likely_eligible
```

No rule can reach it. Every rule that would "pass on an unstated input" returns
`cannot_tell` instead, which is `uncertain` — and that is the safer of the two, so the
branch is not merely unreachable but would be wrong if it were reachable. The enum keeps
the member because PRODUCT-SPEC §8.3 names it and M3c's score components may earn it.

Recorded in the ADR rather than silently not implemented, which is the difference between
a decision and an omission.

---

## 3. What was actively looked for

| Risk | Finding |
|---|---|
| **Hallucinated certainty** | The whole milestone's subject. Found: an unknown asserting an action existed (§2.1), a headline asserting a cause (§2.2), a `!` asserting a narrowing (§2.4). Earlier: a docstring asserting autogenerate worked, corrected by running it |
| **Silent data loss** | `enrollment_required` was redefined rather than relabeled, and the three-way figure is still printed beside the two-way one so the change is visible. **No label was edited in this milestone** |
| **Wrong merges** | `null` `role_family` (unclassified) is kept distinct from `unclear` (read and declined). Merged, an unrun classifier and a corpus of ambiguous titles look identical |
| **Tests that assert nothing** | Every gate rule is mutation-tested *in the suite* rather than by hand, plus two guards on the harness itself — one of which exists because `_RULES` captures function references at import and `monkeypatch.setattr` left the tuple pointing at the originals, measured rather than supposed |
| **A stale "not built yet" list** | Two deferral reasons for the `skill` filter had gone stale; the first went unnoticed for a milestone, the second was caught the same session |
| **Privacy** | The gate reads six `users` columns and stores nothing. No verdict is persisted, so there is no row recording what any posting concluded about anybody |
| **Irreversible actions (I5)** | Nothing here writes on a user's behalf. Both the browser walk and `check_eligibility_gate` write to the developer's own profile and restore it, and both state in their own docstrings that a kill mid-run leaves the six columns holding test values with nothing on disk remembering what preceded them |
| **Accessibility** | The verdict is a sentence, never a colour and never a bare enum value. `TONE` dims and does not encode. No new colour token was added, so no new contrast assertion was owed |

---

## 4. What this milestone does not claim

**The gate is graded on the same 60 postings the classifier's thresholds were chosen
against.** The seniority precedence and its two thresholds were picked with those titles
visible — weaker independence than M3a had, where the key was labeled from descriptions and
the rules were about headings. **Every number here is an upper bound, not an estimate of
behaviour on an unseen posting.** The corpus carries 93 recorded-but-unlabeled postings
that are exactly the held-out check this wants, and they are not labeled.

**No eligibility precision or recall, in CI or anywhere.** `matching.md` §7 puts those at
M3d. M3b publishes reading accuracy per label field, classifier accuracy per field, and the
wrong-ineligible equality — which is what a 60-posting key with no eligibility ground truth
in it can honestly support.

**`role_family: unclear` is labeled on zero postings**, so the corpus holds no example of
the case the classifier most needs to get right: a posting it should refuse to guess at. A
classifier that never answers `unclear` scores perfectly here. Asserted as a gap by a test
that goes red the day a posting is labeled `unclear`.

**`fall`, `winter` and `spring` are reachable by the internship-season rule and stated by
no posting in the corpus.** A measured gap in the corpus, not in the rule, and a test says
so by name.

**Three of five reading accuracies are still below 0.95** — `degree` 0.867, `min_years`
0.883, `sponsorship` 0.917 — and two of `sponsorship`'s five errors are the deliberate
`offered` tie-break, kept because A13 ranks sending somebody into a conversation above
telling them not to apply.

---

## 5. Evidence

Docker was down for the first half of this session and came back. Everything below ran
against a clean stack afterwards, **and against a verified-fresh API** — which, per §2.7,
is a sentence this review has earned the right to be specific about.

```
make check         1383 python passed; 182 web across 20 files
                   ruff, mypy (64 files), eslint, tsc, prettier all clean
make acceptance    73 verify.py assertions + 48 seeded browser tests, 1 skipped
                   exit 0
make verify        73 checks, run separately three times
make drift         no model/migration drift
migrations         0015 down and up again against a real database, then drift clean
```

`check_eligibility_gate` contributes 16 of the 73, and this is its first working run. What
it reports, against the live seeded corpus:

```
22 of 31 postings judged, 9 unread (nothing extracted, verdict null)

empty profile        eligible 13   uncertain 9                        ineligible 0
blocked profile      eligible 13   uncertain 1   likely_ineligible 7  ineligible 1
```

**`ineligible 0` on the empty profile is the milestone's headline assertion**, now measured
against live data rather than only against the answer key. The second row is what keeps the
first from being vacuous: the same corpus does reach `ineligible` when a profile genuinely
contradicts a stated bar.

The browser walk: all five eligibility tests run and pass. The fifth —
"no unknown offers an action that could not resolve it" — **skipped on its first attempt
and passes now**, which is §2.7 and §2.8 in one line.

Mutation and failure checks performed this session, each reverted:

| Mutation | Result |
|---|---|
| `nothingToFillIn` forced to `false` | 1 test fails — §2.2's first (the pre-fix shape) |
| `nothingToFillIn` widened to "any unassessable unknown" | 1 test fails — §2.2's second (the over-applied shape) |
| `is_enrolled` deleted from `ASKS` | 1 test fails, naming the column — §2.3 |
| `verify.py` run with the stale server still listening | refuses, exit 1, prints the `lsof` line — §2.7, run against the real stale process before killing it |

Every one was run and watched to go red before the fix was trusted, which is the discipline
`matching.md` §8 asks for and the reason the gate's own mutation harness lives in the suite
rather than in this document.

**CI: green on all five jobs at `6656eab`, first attempt** — run
[31310986928](https://github.com/Tahmudun/Nightshift/actions/runs/31310986928). Counts read
from the job logs:

```
python       1383 passed; 72 distributions, all pinned
e2e          5 degraded + 48 seeded passed, 1 skipped
web          20 files, 182 tests
migrations   up, down, up, and no drift
secret scan
```

**The e2e arithmetic is the assertion this review most wanted.** The previous run at
`b403a8e` was 43 seeded and 1 skipped; this one is 48 seeded and **still 1 skipped**. The
five eligibility tests ran rather than skipping — including, on a machine that has never
had a stale server on port 8000, the one that skipped itself green here (§2.7, §2.8).

`make acceptance` and `verify.py` remain the two things CI does not run, so the 73
assertions are local-only evidence. Unchanged from every previous milestone.

---

## 6. What is left

1. **Merge PR #11.** CI is green on all five jobs, first attempt — the sixth first-try pass
   in this project, recorded because seven runs here have failed and every one found
   something no local command had executed.
2. **A stale server can still fool the browser suite.** `verify.py` refuses to run against
   a port it does not own; Playwright cannot, because `reuseExistingServer: true` is load-
   bearing for the ordinary `make dev` loop. What replaces the guard there is the throwing
   assertion in `eligibility.spec.ts` (§2.8) — narrow, real, and only covering the one case
   that happened. **A general freshness check would need the API to report its build**, and
   `/health` reports database and Redis and not what code is answering. That is the honest
   size of the remaining hole and it is worth an ADR at M3c rather than a rushed field now.
3. **A three-day-old `uvicorn` was killed** to get an honest run. It was a `make dev` server
   from the 2026-08-05 session, holding port 8000.

The PRODUCT-SPEC rename to "CitySignal" that was in the working tree at the start of this
session was a VS Code artefact, confirmed by the human on 2026-08-09 and reverted. The
product is Nightshift.
