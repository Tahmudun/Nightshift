# Milestone 2c review — profile and resume

**Date:** 2026-08-03
**Branch:** `m2c-profile-and-resume`
**Scope:** Tasks 1–11 of `docs/plans/2026-08-03-m2c-profile-and-resume.md`

M2c is the slice `command-center.md` §1 called the one with the most invariant
risk, which is why it was scheduled third rather than first. Everything a resume
says is a claim about a person, and I2 forbids storing any of it as fact without
an explicit click.

This review does what CLAUDE.md §5 asks: it looks for hallucinated certainty,
silent data loss, and tests that assert nothing. Every claim below was checked by
running something, not by reading.

---

## 1. The criterion, and how it is evidenced

> *No parsed resume fact is stored as confirmed without a user action.*

Four independent things would each have to fail for a resume fact to reach a
profile unasked, and each has been shown able to fail:

| Guard | Where | Shown able to fail by |
|---|---|---|
| Two tables, one writer | `domain/profile.py` is the only module that may write `users` / `user_skills` / `user_projects` | `test_nothing_infers.py` — three greps: assignment, constructor, `setattr` |
| The extractor cannot reach the confirmed tables | It does not import the ORM | `test_the_extractor_does_not_call_back_into_the_writer` |
| Every proposal quotes its span | Trigger `resume_extractions_span_must_quote` | Task 4's tests; and the same promise re-asserted in the API response and in Zod |
| The browser confirms nothing on its own | `ExtractionReview` opens with every row undecided | `confirms nothing until somebody says so`, and the seeded browser walk |

**The browser test is the criterion, not a proxy for it.** `profile.spec.ts`
pastes the fixture resume, asserts sixteen proposals are listed with the
characters each came from, then *navigates to the profile and finds it
unchanged*. Only then does it confirm two and reject one, and assert exactly
those outcomes.

`check_profile_confirmation` asserts the same thing over HTTP, and it compares
the profile **before and after** rather than asserting "no skills" — which would
pass vacuously on a fresh database and fail on a developer's own.

---

## 2. What this review found

### 2.1 A skill's provenance linked to a resume that may not exist — found by this review

`SkillList` rendered `source_reference` as a link to `/operate/resumes/<uuid>`.
Deleting a resume deliberately **keeps** the skills it produced — a confirmed
fact belongs to the person, not the file — so that link outlives its target and
returns a 404.

The damage is small and the shape is not: a 404 dressed up as evidence is worse
than no link, because a provenance that cannot be followed reads as one that
can. Fixed by passing the live resume ids into the component; the provenance is
still stated, only the link is withheld, and the row says *"in a resume you have
since deleted"*. Two tests, one for each branch.

### 2.2 Two enum vocabularies were transcribed wrong, and nothing local could see it

Nine Python enums were copied into `schemas.ts` by hand. Two were wrong:
`WorkAuthorization` gained a `requires_sponsorship` that does not exist (the real
member is `needs_sponsorship`), and `SkillSourceType` lost `assessment` and
`github`.

Neither is visible to any test on either side of the boundary. The Python suite
never reads TypeScript; the web suite parses fixtures somebody wrote to match the
schema. **The failure would have been a real response arriving in a real browser
and Zod refusing to parse the page** — the fifth time in this project that a
defect lived somewhere no local command looks.

Found by printing the enums rather than reading them. `tests/test_enum_parity.py`
is the guard, and it is the only test in the repo that reads both sides at once.
Mutation-checked: restoring the wrong member turns exactly that one parametrised
case red.

### 2.3 A test that could not fail, found by mutating what it guarded

`HighlightedText` drops a span whose bounds fall outside the text rather than
clamping it, because clamping moves a claim onto whatever words happen to be in
range. The test asserted that the rendered text was unchanged — and it is
unchanged either way, because an out-of-range slice is the empty string whichever
branch runs.

Mutating the range check killed nothing. The assertion is on the marks now
(`querySelectorAll('mark')` is empty), and the same mutation kills it.

This is the second such test found in M2c — the first was Task 2's
`test_the_longest_term_wins_when_two_overlap`, which used a term that overlapped
nothing.

### 2.4 A component test was fed data the API cannot produce

`ExtractionReview`'s fixture put `Python` at characters 34–40, which is
`"\nPytho"` — the right length, the wrong words. Exactly the row
`resumeDetailSchema` exists to refuse, and exactly the class of bug the whole
span mechanism is built against, sitting inside the test for it.

It surfaced because the component rendered the highlight faithfully and the
assertion did not match. The fixture is now parsed through `resumeDetailSchema`
in its own test, so a component test can no longer be run against impossible
data.

### 2.5 A stale deferred entry is the same lie as a hidden feature

`"Selected resume — blocked on M2c"` was in the applications deferred list.
M2c shipped it, so leaving the entry would have had the product claiming a
working feature was missing. Three tests asserted the old text — one Python, one
component, one browser — and all three had to be inverted rather than deleted:
each now asserts the entry is *gone*.

### 2.6 The browser walk exceeded the test budget under parallel load

`profile.spec.ts`'s main test passed alone and timed out at 30 s in the full
suite. Measured rather than guessed: the failure was `page.reload()` running out
the *test* clock, not an assertion going red. Five navigations across three
routes, two of which `next dev` compiles on demand, against three other workers
doing the same.

Marked `test.slow()` rather than trimmed — cutting the walk to fit a clock would
remove coverage. The seeded suite then passed three times back to back, and
`make acceptance` three times after that.

### 2.7 `pypdf` is BSD-3-Clause, not MIT

The plan's Global Constraints say "MIT/Apache". The implementation recorded
BSD-3-Clause in `costs.md`, which is correct — checked against the installed
package metadata. Noted because the plan is a document people will read.

---

## 3. Checks this review ran and what they showed

### 3.1 "Would any test still pass with the extractor returning `[]`?"

The plan asks this directly. Answer, measured by inserting `return []` at the top
of `extract_proposals`:

```
19 failed, 1073 passed
```

Nine in `test_profile.py`, four in `test_profile_routes.py`, six in
`test_resume_extraction.py`. The extraction path is not decorative in any of
them, and the golden-file test is among the dead.

### 3.2 "Does the upload path log the resume text?"

No. `grep` across `services/api/nightshift/` finds no logging statement carrying
`parsed_text` or a resume body, and `logging.py` has no request-body middleware.
The bytes are read in memory and discarded; the row keeps the filename, a hash of
the *text*, and the text. This is the most personal data the project holds
(PRODUCT-SPEC §13).

### 3.3 "Can a proposal survive a resume edit and quote the wrong words?"

Not today, and now not by accident either. Nothing in the codebase assigns
`resumes.parsed_text` after creation — `create_resume` passes it to the
constructor and no route touches it. **The trigger cannot catch this**: it fires
on `resume_extractions`, so an UPDATE to the parent passes unexamined while every
child row silently starts quoting different words.

`test_nothing_rewrites_the_text_a_proposal_quotes` is the guard, in the same file
and the same style as the I2 guards it sits beside.

### 3.4 "Does `make acceptance` leave rows behind?"

`check_profile_confirmation` leaves nothing. It deletes the resume it created and
the skill it confirmed — but only if that skill was not already on the profile,
because deleting a skill somebody added by hand would be the verification script
damaging the database it verifies.

`profile.spec.ts` leaves nothing either, and normalises on entry as well as exit:
every resume it creates carries a name only that file uses, and it deletes them
on the way in. M2b's pipeline test could not run twice for the opposite reason.

`check_application_tracking` still leaves one archived application, by design and
stated in its docstring.

### 3.5 Mutation testing

Ten mutations were run across Tasks 6–11 and **nine killed their intended test**.
The tenth (§2.3) found a test that could not fail rather than a rule that was
wrong, which is the same outcome Task 2 recorded.

| Mutation | Killed |
|---|---|
| `nothing_proven` always `False` | `test_a_resume_that_proves_nothing_says_so` |
| `parsed_text` shifted one character in the response | `test_every_proposal_in_the_response_quotes_the_parsed_text` |
| A3 resume-ownership check removed | `test_another_users_resume_cannot_be_selected` |
| `confirm_extractions` swallows the unknown-id error | `test_confirming_an_unknown_extraction_is_404` |
| TS enum member restored to the wrong value | `test_enum_parity[workAuthorizationSchema]` |
| Segment coverage computed by `start` only | `marks every segment covered by the active span` |
| Span ends are not boundaries | `gives the active span a treatment…` |
| Out-of-range spans clamped, not dropped | **nothing** → test rewritten, then killed |
| Extractor returns `[]` | 19 tests |

---

## 4. Corrections made to the plan

- **Task 6 needed a domain function the plan did not list.** `PATCH /resumes/{id}`
  is in the plan's route list, and Task 5 built no writer for it. `update_resume`
  was added to `domain/profile.py` rather than putting the "one default per user"
  rule in a route handler (CLAUDE.md §3).
- **`selected_resume_id` needed an ownership check the foreign key cannot make.**
  The plan says only "accept it in `ApplicationPatchIn`". The FK accepts any
  user's resume id, and every later read of that application would then leak it
  (A3). Checked in the route, 404 rather than 403, mutation-verified.
- **The plan's `DEFERRED_PROFILE_FIELDS` snippet was used verbatim**, and the
  `UPDATABLE_FIELDS` frozenset in `domain/applications.py` had to be widened —
  which the plan's file list did not mention.
- **The plan asked the skill list to show "the quoted words".** The schema stores
  a pointer (`resume:<uuid>#238-244`), not the words, and the vocabulary's
  canonical name can differ from the literal text anyway ("data structures" →
  "Data Structures"). A followable pointer is stronger than a duplicated string —
  see §2.1 for the part of that which was wrong.
- **A name field was added to the paste box.** The browser test needs to identify
  rows it created, and somebody with a backend resume and a data resume needs the
  same thing.
- **`HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in the installed Starlette** and
  emits a warning on every 422. `pyproject.toml` turns `DeprecationWarning` from
  `nightshift.*` into an error, so the plan's snippet would have failed CI.
  `HTTP_422_UNPROCESSABLE_CONTENT` throughout.

---

## 5. What M2c deliberately did not build

| Not built | Why | Where it lands |
|---|---|---|
| `.docx` upload | A second parser in the slice with the most invariant risk. The upload control names it, with paste offered as the route around it | Unscheduled |
| Storing the uploaded file | We need the text, not the bytes (§13) | Never, unless a feature needs the original |
| `user_skills.confidence` | A confirmed skill has no confidence score. I4 forbids a number with no breakdown | M3 |
| `skill_id` FK to a taxonomy | The taxonomy is M3's | M3 |
| `resumes.structured_profile` | The proposals *are* the structure, and they carry spans | Never |
| Proficiency inference | A page cannot show how well somebody knows a thing | Never inferred |
| Work-authorization extraction | A claim about legal status is confirmed in a form. `ExtractionKind` has no member for it | Never |
| An LLM anywhere in this path | `command-center.md` §6.1, decided by the human | Would need an ADR naming the cost |
| §12.1's guided first-run wizard | Its steps 9–10 refer to the daily queue and the match list, neither of which exists | M2d, and named here rather than left unstated |

The first four are named on the profile page itself, from the API's own
`deferred_fields`.

---

## 6. Carried into M2d and beyond

1. **A resume's text is immutable by guard, not by schema.** §3.3's test greps the
   source. A trigger on `resumes` refusing an UPDATE to `parsed_text` would make
   it structural, the way the append-only trigger did for events. Cheap, and not
   done here.
2. **`source_reference` is a string, not a foreign key.** It is deliberately a
   pointer that may dangle (§2.1), because the fact outlives the file. But
   nothing validates its format on write — a malformed one renders as "added by
   you" rather than failing.
3. **The confirmation screen has no keyboard shortcut for bulk confirm.** Sixteen
   proposals is sixteen clicks. Not a correctness problem; it will become an
   ergonomics one on a long resume.
4. **The seeded suite is at four workers and near its budget.** One test —
   `profile.spec.ts`'s main walk, the only `test.slow()` in the repo — needed
   more than the 30 s default, and M2b's whole-loop test runs at 20–29 s without
   one. Adding a comparably heavy spec should come with a look at the worker
   count rather than another `slow()`.
