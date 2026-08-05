# PROGRESS

> Read this first, every session. If the repo state does not match what this
> file claims, fix this file before writing code.

**M0: COMPLETE — 6 of 6 acceptance criteria verified at commit `4c1643f`.**
**M1: COMPLETE — all four parts, 15 of 15 criteria verified.**
**M1a: COMPLETE, CI-green at `430347a`, merged to `main` as PR #1 (`54ef35a`).**
**M1b: COMPLETE and reviewed. Merged to `main` as PR #2 (`cf48719`).**
**M1c: COMPLETE, reviewed, CI-green at `19236f5`, merged to `main` as PR #3 (`f377303`).**
**M1d: COMPLETE, reviewed, CI-green at `75d9ab7`, merged to `main` as PR #4 (`044189e`).**
**M2a: COMPLETE, reviewed, CI-green at `76190c8`, merged to `main` as PR #5 (`910027a`).**
**M2b: COMPLETE, reviewed, CI-green at `6a10bb6`, merged to `main` as PR #6 (`2f984f3`).**
**M2c: COMPLETE, reviewed, CI-green at `e63ec2f`, merged to `main` as PR #7 (`e42d612`).**
**M2d: COMPLETE, reviewed, CI-green at `c6e5a97`, merged to `main` as PR #8 (`77e52ea`).**
**M2: CLOSED. All four acceptance criteria verified, all four PRs merged.**
**M3a: COMPLETE, reviewed, CI-green at `3fbffd6`, merged to `main` as PR #9 (`452ec90`).**
**M3a.1: COMPLETE. Recall 0.459 → 0.861, precision 0.659 → 0.847, necessity 0.668 → 0.915.**
**Current milestone: M3 — explainable matching. M3b (the eligibility gate) is in progress.**
**Last updated: 2026-08-05**

---

## Next exact action

### M3b is underway on `m3b-eligibility-gate`. Tasks 1–8 are done. Next: Task 9 — `GET /jobs/{id}` returns the verdict, and the three enums cross into `schemas.ts`.

**[PR #11](https://github.com/Tahmudun/Nightshift/pull/11) is open as a draft,
and that is deliberate.** Seven CI runs in this project have failed and every
one found something no local command had executed; waiting until the end of a
twelve-task milestone to learn that is the expensive version. CI now runs on
every push, and it has been **green on all five jobs twice** —
[31052329000](https://github.com/Tahmudun/Nightshift/actions/runs/31052329000)
at `bcf5f58` (Tasks 1–4), and
[31053249925](https://github.com/Tahmudun/Nightshift/actions/runs/31053249925)
at `1da91ce` (through Task 5). Counts read from the job logs:

```
python       1308 passed; 72 distributions, all pinned
e2e          5 degraded + 41 seeded passed, 1 skipped
migrations   up, down, up, and no drift — including 0013
web          18 files, 159 tests
secret scan
```

`1da91ce` is the branch head, so the recorded result covers every line on the
branch by inspection rather than by a diff. **Migration `0013` has now run
up, down and up on a machine that is not this one**, which is the assertion
this project has twice had to learn to make.

The plan is `docs/plans/2026-08-05-m3b-eligibility-gate.md`. Two decisions the
human took on 2026-08-05 before planning: role families are the eight tech
families plus an explicit `not_tech` and `unclear`, and the `skill` filter comes
on with what it is based on stated beside it.

**Task 1 is done and its result is a baseline, not an achievement.**

---

## M3b Task 1 — the five answer-key fields nobody had ever graded

**M3a graded one of the answer key's nine label fields.** The extractor has been
emitting `degree`, `graduation_window`, `years_experience`, `enrollment` and
`authorization` proposals since commit `3722026`, against a key committed before
any of those rules existed, and **no test had ever compared one of them to a
label.** It read as finished because nothing counted.

Measured 2026-08-05, over the 60 labeled postings, before any rule was changed:

```
degree                 0.567     34 right, 26 wrong
graduation_window      0.917     55 right,  5 wrong
min_years_experience   0.883     53 right,  7 wrong
enrollment_required    0.317     19 right, 41 wrong
sponsorship            0.917     55 right,  5 wrong
```

**No floors are in CI yet, deliberately.** They go in after Task 5 repairs what
this found, set just under what the rules then achieve — M3a's rule, for M3a's
reason: a floor picked before measuring is either unreachable or vacuous and
there is no way to tell which from outside.

### The confusions say what is wrong, which is why the report prints them

```
degree               read 'none' for 'bachelors+equivalent' x14, for 'bachelors' x5,
                     'phd' for 'bachelors' x2, 'none' for 'masters+equivalent' x2
enrollment_required  read 'not_stated' for 'no' x30, for 'yes' x11
graduation_window    read '2027-2027' for 'through-2027' x2, and 3 more of that shape
min_years_experience read None for 10, 14, 1; and read 5 where 3 was labeled
sponsorship          read 'offered' for 'not_offered' x2, 'not_stated' for 'not_offered' x2
```

**`enrollment_required` at 0.317 is mostly a vocabulary gap, not 41 defects.**
30 of the 41 are `not_stated` where the human wrote `no` — the reading has no
rule that can ever output `no`, which is stated in the function's own docstring
rather than discovered from the grade. Producing `no` needs to know the posting
is not an internship, and **`is_internship` is the classifier's, so this one is
blocked on Task 4.** The other 11 are real misses: the rule matches only
"currently pursuing / enrolled / studying" and postings say "rising senior",
"returning to school", "must be enrolled in".

**`degree` at 0.567 is the one to chase.** 21 of the 26 errors read `none` where
a degree was labeled, which means the degree was found and filed under a heading
the extractor does not read as required — the same class of defect M3a.1 fixed
for technologies, in a dimension nobody had looked at. The 2 postings read `phd`
against a labeled `bachelors` are the opposite error and the more dangerous one:
that is a wrong blocker waiting for the gate to exist.

### A rule that could not fire, found by measuring within the hour

`_resolve_graduation_window` shipped a branch producing the answer key's
`through-YYYY` form when the words `through|by|before` appeared in a proposal's
`raw_text`. **`raw_text` for these proposals is the matched year and nothing
else** — `"2027"`, or `"2027-2028"`. The branch could never fire.

Deleted rather than left in, and **the numbers were identical before and
after**, which is what makes "it was dead" a measurement rather than a claim.
Producing that distinction needs the words around the year, which only the
extractor has; it is Task 5's. Until then those 5 postings read as a narrower
window than the posting states — the direction that invents blockers.

### One tie-break is deliberately wrong on this corpus

`_resolve_sponsorship` prefers `offered` when a posting somehow says both, and
that costs 2 of its 5 errors. Kept: "we do not sponsor H-1B for this role, but
we do sponsor OPT extensions" is one real sentence containing both, and reading
it as `not_offered` tells a person they cannot apply for a role that says it
will help them. The other error sends them into a conversation. A13 ranks those
two, and this is the ranking applied rather than accuracy maximised.

### The grader is guarded against being the thing that is broken

Two of its four tests are about the machinery rather than the corpus, because
M3a shipped a violation count stuck at zero for a whole milestone:

- `test_the_grader_can_fail` runs a constructed disagreement through the tally
  and asserts it is recorded — a tally that cannot count a miss reads 1.000.
- `test_every_label_field_is_graded_or_named` fails if a label field is in
  neither the graded list nor the named-and-excluded list. **That is the guard
  that would have caught M3a's gap a milestone earlier**: five fields were
  unmeasured and nothing anywhere said so.
- `test_none_years_never_compares_equal_to_zero` — `not_stated` and "no
  experience required" are different postings, and the gate treats them
  differently, so the grader must not merge them.

---

## M3b Task 2 — `role_family` and `seniority` labeled, before a classifier exists

60 postings × 2 fields, added to `labels.yaml`. **120 insertions, zero
deletions** — checked with `git diff --stat`, and the patch script refuses to
write at all if the rewrite removes a line, because the one thing it may not do
is reformat a committed label.

The ordering is the whole point (`matching.md` §1.1). Rules written first make
the corpus get chosen — in good faith — to hold the cases the rules already
handle, and the grade then measures nothing. Both fields are **required with no
default**: a posting arriving unlabeled must fail to parse rather than quietly
acquire an answer nobody chose. `test_neither_new_field_has_a_default` is that
guard, and `unclear` and `not_tech` are both real answers a human picked, so
neither may become what happens when nobody picks.

### The taxonomy gained a value the human's list did not have

`hardware`. Akuna's *Hardware Engineer Intern* and IMC's *Graduate Hardware
Engineer* are both FPGA and low-latency hardware design — read, not guessed
from the titles. `not_tech` would be false and `infrastructure` would make that
family mean two unrelated things. Two of sixty. **Recorded as a departure from
the decision rather than absorbed into it**, and it is one line to revert.

The rule applied consistently for the harder calls, written down because a
labeler's rule that lives only in their head is a rule the next pass will
contradict: **`role_family` describes the work's primary output.** Software,
systems or models earn a tech family; a deal, a hire, a policy, a report or a
financing is `not_tech`. That is what puts Anthropic's *Applied AI Architect*
in `not_tech` — its own first sentence says "you will be a Pre-Sales
architect" — and OpenAI's TPM roles in `product`.

`seniority` was harvested from the 60 titles rather than invented, the lesson
M3a's Task 7 paid for. `staff` covers the Lead / Staff / Principal band because
the corpus writes "Lead" and never "Staff".

### What the distributions say, including the part that is a gap

```
role_family   not_tech 19   quant_trading 13   ml_ai 9   software_engineering 4
              security 4    product 4          infrastructure 3
              hardware 2    design 1           data_engineering 1   unclear 0

seniority     unclear 14    mid 13   new_grad 8   director 6
              internship 5  senior 5  staff 5     junior 4
```

**`role_family: unclear` is labeled on zero postings, and that is a coverage
gap rather than a success.** All sixty could be classified, so the corpus holds
no example of the case the classifier most needs to get right: a posting it
should refuse to guess at. A classifier that never answers `unclear` scores
perfectly here and is wrong the first time it meets a genuinely ambiguous
posting.

`test_the_corpus_cannot_grade_an_unclear_family_and_says_so` **asserts the
gap** — it fails the day a posting is labeled `unclear`, and its message says to
delete it. That is deliberate: this project has now four times shipped a blind
spot recorded in a comment that nobody re-read once the thing it waited on
landed. A comment goes stale silently; a test goes red.

`design` and `data_engineering` carry one posting each and `hardware` two, so
per-family accuracy on those is not a measurement. Asserted by name in
`test_two_families_are_too_thin_to_grade_on_their_own`, so a future table
printing `design 1.000` cannot be read as a result.

**14 of 60 seniority labels are `unclear`**, which means roughly a quarter of
the classifier's job is knowing when not to answer. That is the right shape for
this milestone and it also means a classifier that always says `unclear` scores
0.23 — visible, rather than hidden behind an average.

### The guard that worked on its first day

Adding two label fields turned `test_every_label_field_is_graded_or_named` red
immediately: both were in neither the graded list nor the named-and-excluded
one. That test was written four hours earlier, in Task 1, precisely because M3a
had five unmeasured fields and nothing anywhere said so. **This is the first
time in this project a new label field has been unable to arrive unmeasured.**

---

## M3b Task 3 — two `String` placeholders become real types, and a seed that lied

Migration `0013_role_family_and_seniority`. `RoleFamily` (11 values),
`Seniority` (8), and `EligibilityState` (5).

**`EligibilityState` is deliberately not a PostgreSQL enum**, unlike everything
else in `db/base.py`. M3b computes a verdict on read and stores none, so there
is no column to attach a type to until `match_results` arrives at M3c. Creating
a database type with no column is shape with no use — the same reasoning that
left `user_skills.confidence` out at M2c.

**Both columns were empty, and that was checked rather than assumed**: no writer
anywhere in `nightshift/`, `scripts/` or the web app, and `count(role_family),
count(seniority)` returned `0, 0` against a freshly seeded database holding 31
jobs. So the conversion could not lose a value.

`null` still means "not yet classified" and stays distinct from `unclear`, which
is the classifier having read a posting and declined to guess. Merged, an unrun
classifier and a corpus of ambiguous titles would look identical.

### Autogenerate got three things wrong, and this project had recorded all three

```
alter_column does not create the enum type   -> `type "role_family" does not exist`
VARCHAR to enum needs an explicit USING       -> postgres will not cast implicitly
the downgrade emitted no DROP TYPE            -> next upgrade: "type already exists"
```

The first and third are M2c's review findings 2 and 3, about `add_column` rather
than `alter_column`. **Knowing the pattern did not prevent it** — autogenerate
produced the same shape again and it was caught by running the migration, not by
remembering.

A fourth, new: `alembic_version.version_num` is `varchar(32)` and the generated
revision id was 36 characters. The migration applied and then failed writing
down that it had.

Verified: up, down one, up; and a full down-to-base and back. `make drift`
reports no drift. `make acceptance` passes with the drift step in it.

### The vocabulary now exists in three places, so it is asserted equal in all three

The enums in `db/base.py`, `ROLE_FAMILY_VALUES` / `SENIORITY_VALUES` beside the
labels, and the migration's own tuples. **The migration's copy is unavoidable**
— a migration that imports a model stops describing the schema as of its own
revision and starts describing today's — so an assertion is the only defence
available. Shown able to fail by misspelling `hardware` in the migration.

### The seed reported success over an empty database

The eighth time in this project something that reported success was wrong, and
the first where the reporter was `make seed` itself.

The model change landed before its migration. Every INSERT failed with `type
"role_family" does not exist`. `ingest_boards` counted all 31 postings into
`stats.failed` — **which is correct**, I3 says one bad posting may not kill a
board — and the command printed `seed complete` and exited `0`.

```
  greenhouse fixture ingest: 0 created, 0 updated, 0 unchanged, 10 failed (succeeded)
  lever fixture ingest:      0 created, 0 updated, 0 unchanged,  9 failed (succeeded)
  ashby fixture ingest:      0 created, 0 updated, 0 unchanged, 12 failed (succeeded)
    canonical jobs      0 (0 open)
seed complete. `make dev` then open http://localhost:3000     <- exit 0
```

**The counts were on screen the whole time, and that is not enough.** CI's "Seed
loads" step reads the exit code and nothing else, so a completely broken seed
was a green check. `make demo` would have handed a developer an empty city under
a success message. `make acceptance` *would* have caught it — `verify.py`
indexes `jobs["items"][0]` and would have raised — but the CI seed step has no
such backstop and it is the one that runs on every push.

The guard is "ended with zero jobs", not "any posting failed". The fixtures are
committed and deterministic so any failure is a defect, but failing the whole
seed over one bad posting would make the command brittle in exactly the way
`ingest_boards` refuses to be.

**Demonstrated failing twice, from two unrelated causes** — the missing enum
type, and orphaned `source_job_records` left by a careless `truncate`, which the
seed refuses on the M1 acceptance criterion. Both now exit 1; a healthy seed
still exits 0 with 31 jobs.

### Two plan corrections, recorded rather than absorbed

1. **`internship_season` moved from Task 3 to Task 11.** The plan put the column
   here. It does not belong here: nothing in the answer key labels a season, so
   populating it in Task 3 would add a field graded by nothing — the exact
   condition Task 1 built a guard against, four hours earlier. It lands with the
   filter that uses it, where the two can be checked together. Its shape is also
   undecided: one `summer_2027` string, or a term enum plus a year, and the
   corpus (4 of 5 internships state a season in the title) should decide.
2. **Enum parity moved from Task 3 to Task 9.** The parity test compares Python
   enums against `z.enum` copies in `schemas.ts`, and nothing serves these
   values to a browser yet. Writing the TypeScript now would be shape with no
   use, and the drift it guards happens at the moment of transcription — which
   is Task 9.

---

## M3b Task 4 — the classifier, and the number that matters more than accuracy

```
role_family      0.950     57 right,  3 wrong
seniority        0.967     58 right,  2 wrong
is_internship    0.933     56 right,  4 wrong
```

Floors in CI at **0.94 / 0.96 / 0.93**, set after measuring.

### One rule changed after the first measurement, and it is recorded on its own

```
role_family   0.933 -> 0.950   the role type beats the domain in a title
```

OpenAI's *Senior Technical Program Manager - Security* names a job and a subject
area. The job is program management; security is what it is *about*. Graded with
the domain families first it came out `security`, which describes the team
rather than the work — and it was **the only family error in the corpus that was
not a safe `unclear`**. Explicit management phrases now sit above every domain
rule.

### Three orderings are load-bearing and every one comes from a real posting

- **`not_tech` is tested first.** *AI Compliance Officer* contains AI, *Capital
  Markets - Infrastructure Financing* contains Infrastructure, *Cloud Partner
  Enablement Lead* contains Cloud, *People Research Scientist, Recruiting*
  contains Research Scientist. Four business roles wearing a technical word; a
  tech-first order files all four wrongly.
- **New-grad beats junior.** *Associate Product Manager, New Grad (2027 Start)*.
- **A years figure ≥ 6 beats an early-career title word.** Jane Street's *Campus
  Recruiter, Early Careers Partnerships & Initiatives* says early career three
  times and asks for six years. A title-only classifier ranks it into a new
  graduate's list.

**The description may only veto towards `not_tech`, never promote into a tech
family.** Every description in this corpus talks about technology, most at
length, so a promoting rule would promote nearly all of them. The one phrase
that decides on its own is Anthropic's own first sentence about the Applied AI
Architect role: *"you will be a Pre-Sales architect"*.

### The assertion that matters more than the floor

`test_every_role_family_error_is_a_refusal_rather_than_a_wrong_answer`. All
three remaining family errors say `unclear` — the classifier declining to make a
claim, which is the same instinct A13 demands of the gate.

**A floor cannot tell a confident error from a refusal, and those are not the
same mistake.** A future rule that buys accuracy by guessing fails this test
before it fails the floor.

### Two misses are inherited, and that was checked rather than assumed

*Data Center Architect, CSA* is labeled `senior` on 10 years and the classifier
says `unclear`, because the reading returns `None`. The posting writes:

```
Required 10+ years delivering mission-critical facility infrastructure
```

`_years_of_experience` needs the word "experience" within 40 characters of the
figure, and it is not there. **The classifier's error is the extractor's**, and
it is one of the two `read None for 10` confusions Task 1 already printed. Task
5's to fix.

### The methodological caveat, in the module rather than in a review

The seniority precedence and its two thresholds (3 and 6 years) were chosen with
these 60 titles visible. That is **weaker independence than M3a had** — there
the key was labeled by reading descriptions and the rules were about headings
and vocabulary, a different surface. Here labels and rules came off the same
titles, hours apart.

Some rules are not fitted in any meaningful sense: "Director in the title means
director" is what anybody would write. The thresholds and the ordering are.
**So these numbers are an upper bound, not an estimate of behaviour on an unseen
posting.** The corpus carries 93 recorded-but-unlabeled postings and they are
exactly the held-out check this wants. **Not done, and named here rather than
left to be noticed.**

---

## M3b Task 5 — four repairs, each measured on its own

```
Task 1 baseline                          degree 0.567   enrollment 0.317
+ curly apostrophe in the degree words   degree 0.700
+ "or an equivalent" broadened           degree 0.733
+ "minimum education" heading harvested  degree 0.850
+ enrollment stops requiring "currently"                enrollment 0.483
```

**The technology numbers are unchanged at 0.847 / 0.861 / 0.915**, checked
rather than assumed — adding a required heading is exactly the kind of change
that could have moved M3a.1's figures.

### The apostrophe: M3a.1's en-dash finding, in a different rule

Akuna, Anthropic and IMC type the **curly** apostrophe in "Bachelor's degree",
because that is what a rich-text editor produces. The pattern accepted only
ASCII `'` and matched none of it. **21 of the 26 degree errors were postings
whose degree sentence the extractor could not see at all.**

Two of those came out `phd` against a labeled `bachelors`:

```
Requirements for this role: Pursuing a bachelor's, master's, or Ph.D.
```

`Ph.D` is the one spelling in that list with no apostrophe in it, so it was the
only proposal and won by default. **A posting explicitly open to a bachelor's
graduate read as a doctorate requirement** — the direction A13 ranks worst, and
it was one migration away from being a wrong `ineligible`.

Normalising the text to ASCII first would also have worked and was rejected:
every proposal carries character offsets into `jobs.description_text`, and
rewriting the string those offsets point at is how a span comes to quote
something the posting never said. U+2019 happens to be one character wide so the
offsets would have survived — but the rule is not "when the replacement is the
same width", and the next such fix would not be.

### Both new phrasings were harvested, not invented

- **`minimum education`** occurs in exactly **15** postings — every Anthropic
  posting in the corpus, which appends a `Logistics / Minimum education: ... /
  Required field of study: ...` block to all of them. It is the last heading
  before the degree sentence, so without it a posting whose own words are
  *"Minimum education: Bachelor's degree"* was read as requiring **no degree**.
- **`or an equivalent`** — A13's escape hatch. `or\s+(?:an?\s+)?equivalent`
  matches 23 of 60 against the narrow form's 8. Missing one is the dangerous
  direction: it turns "or an equivalent combination of education, training,
  and/or experience" into a hard degree requirement.
- **The enrollment rule required the word "currently"**, and 10 of the 11
  postings labeled `enrollment_required: yes` do not use it. They write
  *"Pursuing a bachelor's, master's, or Ph.D."* and *"Current university
  student graduating between..."*. The replacement is anchored to a degree word,
  because "pursuing excellence" is ordinary prose — the same prove-itself
  discipline `_looks_like_a_heading` already applies to headings.

### One metric was redefined rather than one rule tuned, and no label was edited

**`enrollment_required`'s `no` and `not_stated` are not separable from the
postings.** Among the 47 non-internship postings, 30 are labeled `no` and 17
`not_stated`, and reading the descriptions the split is not driven by anything
they say — a few `no` labels carry a note pointing at real text, most do not. To
a person both mean the same thing: you do not have to be a student to apply.

So the three-way figure measures a distinction that does not exist, and it would
keep looking broken however good the rules got.

```
enrollment, as the gate asks it   0.983    59 right, 1 wrong
enrollment, three-way             0.483    still printed, not gated
```

**No label was edited.** Rewriting 30 labels to lift a metric is exactly the
move `matching.md` §1.1 forbids, and "with a recorded reason" would not make it
a different move. The metric is redefined on the distinction that changes a
verdict — the gate asks "must this person be enrolled", and a posting that is
silent and a posting that says no produce the identical answer — and the
three-way figure stays printed beside it so the change is visible rather than a
quiet improvement.

**This is the only floor in that file so far**, at 0.90. The other five stay
reported and ungated until the repair pass is finished, because a floor set
mid-repair is a floor that has to be edited again next week.

### What is still wrong, and what it is waiting on

```
degree 0.850            9 left: 2 read `none` for `bachelors+equivalent`,
                        2 read `bachelors+equivalent` for `none`
graduation_window 0.917 all 5 are the `through-YYYY` form, which needs the
                        words around the year and so needs the extractor
min_years 0.883         "Required 10+ years delivering ..." — the rule needs
                        the word "experience" within 40 characters and it is
                        not there
sponsorship 0.917       2 of the 5 are the deliberate `offered` tie-break
```

---

## M3b Tasks 6 and 7 — the gate, and the two blockers it was caught inventing

`domain/eligibility.py`. Pure, no ORM, reads no description. It takes a
`PostingReading` and a `SeekerProfile` and returns a state, its blockers, its
unknowns and its version. **Nothing is stored** — `match_results` is M3c's, and
a stored verdict goes stale the moment somebody edits their graduation year.

```
any blocks       -> ineligible
else any soft    -> likely_ineligible
else any cannot  -> uncertain
else                eligible
```

`blocks` needs **two explicit halves at once**: the posting states it under a
required heading, *and* the person's confirmed profile contradicts it. Either
half missing is `cannot_tell`. That is I2 doing the work — an inferred fact
never blocks anybody, because an inferred fact is not a fact.

**There is no branch producing `likely_eligible`, and that is stated rather than
left to be noticed.** It would mean "every rule passed, but one leaned on
something uncertain", and no rule here passes on an uncertain input — each
returns `cannot_tell` instead. A fifth state no rule can reach would be shape
with no use. The enum keeps the member because PRODUCT-SPEC §8.3 names it and
M3c's score components may earn it.

### Three rules whose reasons matter more than their code

- **A years shortfall may never hard-block.** "5+ years" is a wish far more
  often than a rule, and A13's first hard case is an employer writing "Intern"
  and "3+ years required" in the same document. It reaches `likely_ineligible`
  and stops. The person sees the role, sees the gap, and decides.
- **Enrollment may hard-block**, because it is categorical and checkable rather
  than a matter of degree.
- **Authorization blocks in exactly one configuration** — the posting says in
  writing that it does not sponsor **and** the person has said they need it.
  `unspecified` is the column default and most users' day-one value; reading it
  as "needs sponsorship" would silently block them out of every such posting
  before they had typed anything. `f1_student` is likewise not `needs_sponsorship`
  — an F-1 on OPT does not need sponsorship today, and inferring one from the
  other is the fabrication I2 forbids in the field where being wrong costs most.

**Blockers and unknowns are separate types** because they mean opposite things
to a person. A blocker says "this is probably not for you". An unknown says
"tell us one more thing and we can answer" — and names the profile field that
would settle it, because "complete your profile" is not an action and "tell us
your graduation year" is.

### The wrong-ineligible check found two real blockers on its first run

Zero, as an equality, over **60 postings × 5 profiles**. The checker is written
from the answer key and **never calls the gate** — a checker that called the
gate would agree with it by construction and assert nothing, which is precisely
how M3a's `test_no_nice_to_have_is_ever_reported_as_required` sat at zero for a
whole milestone.

**1. "Must be graduating August 2027 or prior"** was read as the single year
2027, so the gate blocked a 2024 graduate from a role whose own words say they
qualify. **Task 5 had recorded this exact form as a 5-label accuracy gap and
deferred it.** It was not an accuracy gap. The gate is what turned five labels
into a person being told they cannot apply. `_is_open_ended` now reads the words
on either side of the year; `graduation_window` went **0.917 → 1.000**.

**2. "MS Office" was read as a master's degree** on IMC's *Administrative
Assistant* posting, which the answer key labels `degree: none` — hard-blocking a
bachelor's graduate. Bare two-letter abbreviations now need two things at once:

- **case-sensitivity**, because `\bms\b` under `re.I` matches the milliseconds
  in "5 ms in latency" and these boards are trading firms. The same call
  `skills.yaml` already makes for `Go`, `Rust`, `React` and `Outlook`.
- **a following degree context** — a slash, "in", "or", "degree", or a comma
  *only when another abbreviation follows*. "BS, MS preferably in business" is
  IMC's; "MS, Word, Excel" is what the constraint keeps out.

**That second fix left accuracy at 0.850, then 0.867 — and that is the finding.**
It removed no error on paper and removed a hard block on a real person.
**Accuracy could not tell the difference between a false positive that costs
precision and one that costs somebody a job.** It is the clearest argument in
this milestone for why the wrong-ineligible equality exists beside the floors
rather than instead of them.

### The mutation test was wrong on its first write, and is recorded as such

It strips A13's equivalence hatch and re-runs. The first version used a
bachelor's holder — who clears a `bachelors+equivalent` bar whether the hatch is
honoured or not — so the break produced **zero** violations and the test failed
for its own reason rather than the gate's. The profile the hatch is addressed to
is the one with **no degree at all**, and that person is now in the profile set.

### The distribution, printed rather than assumed

```
a 2027 undergraduate, enrolled, needing sponsorship   eligible 27  ineligible 2   likely_inel 20  uncertain 11
a 2024 graduate with two years and a green card       eligible 22  ineligible 11  likely_inel 15  uncertain 12
a PhD with eight years, a citizen                     eligible 29  ineligible 11  likely_inel 5   uncertain 15
a self-taught engineer with no degree and four years  eligible 16  ineligible 21  likely_inel 9   uncertain 14
somebody who has filled in nothing                    eligible 13  ineligible 0                   uncertain 47
```

**The last row is the one to read.** A person who has filled in nothing gets
**zero** ineligibles and 47 uncertains — the state every user is in on day one.
`test_the_corpus_actually_exercises_the_gate` guards the opposite failure: a
gate answering `uncertain` to everything would satisfy every other assertion in
that file, has perfect precision, and is worthless (`matching.md` §3.3).

---

## M3b Task 8 — every gate rule shown able to fail, in the suite

**All five rules are load-bearing.** Replacing any one with an unconditional
`passes` changes the verdict of a case taken from `test_eligibility_gate.py`.

`matching.md` §8 asked for this on the gate specifically, and gave the reason:
three tests in this project have turned out unable to fail, and the gate is
where that would cost most.

**It runs as a test rather than as an exercise a human did once and wrote down.**
A mutation result in a review is true on the day it was written. A mutation
result in the suite is true every time the suite runs.

Two guards on the harness itself, because a mutation harness that mutates
nothing is the most confident kind of vacuous test:

- `test_every_rule_in_the_gate_has_a_case_here` fails when a rule is added
  without a mutation case — the same shape as
  `test_every_label_field_is_graded_or_named` one layer down, and the same
  failure mode it prevents: a check that looks complete because nothing counts
  what it is missing.
- `test_the_harness_itself_is_not_vacuous` neuters all five at once and asserts
  the all-passing outcome.

**That second risk is real and was measured rather than supposed.** `_RULES`
holds function references captured at import, so `monkeypatch.setattr(
eligibility, "_degree_rule", ...)` leaves the tuple pointing at the original.
Run directly: the verdict stayed `ineligible` under that patch. The harness
rebuilds the tuple instead, and the comment saying so was written after
checking rather than before.

---

### After M3b Task 8: the rest of the M3b plan.

**PR #9 is merged.** `main` is at `452ec90`, checked against the PR rather than
assumed. CI was green on all five jobs at `3fbffd6`, run
[31039059510](https://github.com/Tahmudun/Nightshift/actions/runs/31039059510) —
counts read from the job logs rather than inferred:

```
python       5m11s   1282 passed
e2e          2m50s   41 seeded passed, 1 skipped
migrations   1m17s   up, down, up, and no drift
web            59s   159 tests
secret scan      7s
```

The pre-merge invariant held: `git diff 3fbffd6..HEAD --stat` listed docs only.
**That branch took three CI runs, and only the first found anything** — the
check-constraint defect below. The second and third were green first time.

**All four stale merged branches are deleted, locally and on the remote.**
`m1a-provider-breadth`, `m2c-profile-and-resume`, `m2d-daily-queue` and
`m3a-answer-key` are gone; `git branch -a` now lists only `main`,
`ci-pin-and-canary` and `m3b-eligibility-gate`, checked after a `--prune` rather
than assumed. This had been carried as an open item since M2c, in four
consecutive PROGRESS entries, because the permission was not available.

**[PR #10](https://github.com/Tahmudun/Nightshift/pull/10) is open and CI is
green on all five jobs, first attempt**, run
[31045860049](https://github.com/Tahmudun/Nightshift/actions/runs/31045860049).
Counts read from the job logs rather than inferred:

```
python       299s   1282 passed; 72 distributions, all pinned
e2e          189s   5 degraded + 41 seeded passed, 1 skipped
migrations    74s   up, down, up, and no drift
web           69s   18 files, 159 tests
secret scan    5s
```

**The step that matters is `The pin covers everything that got installed`, and
it passed in the real runner** — the constraints file resolved to exactly the 72
lines it names, on a machine that is not this one. Seven CI runs across this
project have failed and every one found something no local command had executed;
this is the fifth first-try pass, recorded because it is not the usual outcome.

`headSha` is `cef574a`, which is also the branch head, so the pre-merge
invariant is satisfied by inspection rather than by a diff.

---

## Q4 answered: CI pins what gates a merge, and a canary watches what does not

**The human's decision on 2026-08-05, on the recommendation in the question:
both.** Full reasoning, and the four alternatives rejected, in **ADR 0016**.

Reproducibility and early warning only conflict if there is one place to
install. There are now two:

| | Installs | Runs on | Can block a merge |
|---|---|---|---|
| `ci.yml` | pinned, from `services/api/constraints-ci.txt` | `pull_request`, `push` to main | yes |
| `dependency-canary.yml` | unpinned | `schedule` weekly, `workflow_dispatch` | **no** |

72 distributions are pinned, wired in as **one** workflow-level `PIP_CONSTRAINT`
rather than a flag on three install steps that could drift apart.

**The pin is checked rather than assumed.** `-c` constrains only the
distributions the file names, so a dependency added to `pyproject.toml` and never
regenerated would install unpinned with nothing anywhere saying so — the pin
becomes partial while everything keeps calling it a pin, which is this project's
recurring failure class exactly. The `python` job diffs `pip freeze` against the
file and fails on a difference in either direction.

**The constraints file cannot be generated on this machine, and that was
measured rather than assumed.** `make constraints` resolves inside a
`linux/amd64` container. The two platforms disagree about eleven distributions
and one irreconcilably:

```
onnxruntime   1.28.0   resolved on linux/amd64, what CI installs
              1.23.2   the newest release with a macOS x86_64 wheel
```

So **the pin covers CI and does not cover a developer's machine**. That is a
smaller copy of the original problem, left standing on purpose and written into
the file's own header rather than discovered later.

**What this gives up:** the alembic finding arrived free, the day it shipped.
The same finding would now arrive up to seven days later, from the canary. That
is the price of an unrelated pull request never going red at a moment nobody
chose, and it is paid deliberately. The canary writes a diff of unpinned-versus-
pinned to its job summary on every run, green or red; notification is GitHub's
own email to the repo owner on a failed scheduled run.

### `make drift` — the gap this episode exposed, now closed

The drift probe existed only in CI, so "it passes locally" and "it passes in CI"
were never the same claim about the schema. That is how a defect eleven
migrations old sat unseen. `make drift` runs the probe against the developer's
own stack and is part of `make acceptance` — **not** of `make check`, which must
keep working without a database.

**Shown able to fail rather than assumed to work.** Adding a `mutation_probe`
column to the `Company` model makes it print both operations and exit 1:

```
==> the models have drifted from the migrations:
    op.add_column("companies", sa.Column("mutation_probe", sa.String(length=10), nullable=True))
    op.drop_column("companies", "mutation_probe")
```

The temporary revision file is cleaned up on the failure path too, checked with
`git status` after — a probe that leaves a migration behind when it fails is a
probe that gets committed by accident.

**What is still floating, named so nobody reads the pin as broader than it is:**
pip itself, the `ubuntu-latest` runner image, `setup-python`'s 3.12.x patch, and
the Postgres service tag. Node was already locked by `package-lock.json`, which
is why the canary is Python-only.

---

## CI's first run on this branch, and the defect it found

**The migrations job failed on the first run — the seventh CI failure in this
project, and the seventh to find something no local command had executed.**

The drift probe emitted forty operations. The cause was older than the branch:
`NAMING_CONVENTION` in `nightshift/db/base.py` renders
`ck_%(table_name)s_%(constraint_name)s`, five migrations wrote the *rendered*
name into `name=` rather than the bare one, and `op.create_table` applies the
convention to whatever it is given. **The database has carried
`ck_jobs_ck_jobs_closed_at_matches_status` since 2026-07-29** while the models
called it `ck_jobs_closed_at_matches_status`. Ten constraints, across `users`,
`jobs`, `job_locations`, `job_source_links` and `ingestion_runs`.

**The constraints were never wrong, only misnamed**, which is exactly why no
behavioural test noticed — each enforces what it was written to enforce. Two of
the ten were long enough that the doubled prefix pushed them past PostgreSQL's
63-character limit and SQLAlchemy truncated them with a hash suffix
(`ck_job_locations_ck_job_locations_confidence_matches_co_b8be`), so nobody
could predict those names at all.

**Why it surfaced on 2026-08-05 and not before, measured in both directions:**

```
alembic 1.18.5   0 autogenerate operations     <- the developer venv
alembic 1.19.0   40 autogenerate operations    <- what CI installed that day
```

Alembic did not compare check constraints during autogenerate until 1.19.0. CI
runs `pip install -e "services/api[dev]"` unpinned and picked the release up the
day it shipped. **No local command could have found this**, and that is the
finding worth keeping: `make check` never ran a drift probe at all, so local
evidence and CI evidence were never the same claim.

Fixed by migration `0012_check_constraint_names`, which renames all ten and
reverses cleanly. `tests/test_check_constraint_names.py` is the guard that does
**not** depend on an alembic version — it reads `pg_constraint` and
`Base.metadata` directly. Both its assertions fail before the migration and pass
after. The local venv is now on 1.19.0 so `make check` means what CI means.

**A third assertion was written and deleted rather than kept green.** It flagged
constraint names at the 63-character limit; the truncated names are 60, so it
could not have caught this defect and guarded nothing the first test does not.

### Both of the things this section left open are now done

It read: *"`pip install -e` stays unpinned"* and *"a `make` target that runs the
drift probe locally does not exist and should"*. Both were closed on
`ci-pin-and-canary` — see the Q4 section above and ADR 0016. Left here rather
than deleted, because the entry above is the reason the decision came out the
way it did: pinning is only defensible alongside something still unpinned.

---

## M3a.1 — COMPLETE. What moved, and what was measurement rather than progress

**Recall 0.459 → 0.861. Precision 0.659 → 0.847. Necessity 0.668 → 0.915.
Nice-to-haves reported as required: still 0, and now a stronger claim than it
was.**

Floors in CI are now **0.84 / 0.86 / 0.91**, set after measuring and just under
what the extractor achieves.

### The first change was not an improvement, and is recorded as such

**The grader compared raw strings.** A posting the human labeled `GCP` scored as
a miss *and* a false positive against an extractor that had correctly found it
and emitted the vocabulary's canonical `Google Cloud`. Same technology,
penalised twice. The same defect covered `python`/`Python`, `Pytorch`/`PyTorch`,
`Golang`/`Go`, `Microsoft Azure`/`Azure`.

That this was a defect rather than a decision is visible inside the one file:
the necessity-accuracy loop already casefolded both sides while `score_sets` did
not, so two metrics over the same labels disagreed about whether `python` and
`Python` are the same word.

Both sides now resolve through the same vocabulary, and **only a match spanning
the whole term counts**. A substring rule would have resolved the label
`Entra ID/Azure AD` to `Azure` — it contains the word — merging Microsoft's
identity product into its cloud platform. Measured: the substring rule collapses
two distinct labels into one on `akunacapital/8047104`; the whole-term rule
collapses none.

```
before, raw strings         precision 0.659  recall 0.459  necessity 0.668
after, both canonicalised   precision 0.706  recall 0.492  necessity 0.683
```

**No extraction rule changed between those two lines.** The human's decision on
2026-08-05 was to fix it, re-baseline, and keep the old numbers on record so
nobody reads the jump as the extractor improving.

### It also un-hid a real violation that had never been at zero

`test_no_nice_to_have_is_ever_reported_as_required` reported **0 violations**
before this change and **1** immediately after: Databricks 8290810002, where the
human labeled `Apache Spark` a nice-to-have and the extractor called canonical
`Spark` required. The raw-string comparison could not see it because the strings
differ. **The assertion with no floor had never actually been at zero** — it was
at zero the way a test that cannot fail is at zero.

Chasing it found the deeper defect. The "heading" governing that sentence was
the bare word *requirements* occurring in prose — "requirements, when we ingest
terabytes per second across 100…" — because `_REQUIRED_HEADINGS` matched
anywhere in the text.

### The rule that fixed it already existed, one directory away

`scripts/make_label_worksheet.py` has demanded since its first real run that an
ambiguous heading **prove itself** — a colon follows, it is capitalised, or it
opens a sentence — after *30 of 60* worksheet excerpts anchored inside ordinary
prose. **The extractor was graded against an answer key built with that rule
while using a looser one itself.** Now ported, with the same ambiguous list.

One correction the port needed, found by measuring rather than supposing:
Databricks writes `[Preferred] Experience using ... Apache Spark`, and with
brackets absent from the sentence-opener set that heading failed its own proof,
the preferred block never opened, and Apache Spark was reported required on two
*more* postings. `[` and `(` were added to both files, which stay identical on
purpose.

### Each step measured on its own, so the movement is attributable

```
canonicalised comparison (measurement)   0.706 / 0.492 / 0.683
+ headings must prove themselves         0.700 / 0.516 / 0.693
+ a bracketed heading is a heading       0.716 / 0.516 / 0.704
+ skills.yaml gains 33 terms             0.800 / 0.820 / 0.889
+ VPNs, firewalls, Entra ID aliases      0.805 / 0.844 / 0.905
+ "candidates must be" heading           0.784 / 0.861 / 0.915
+ React and Outlook case-sensitive       0.847 / 0.861 / 0.915
```

**The sixth line cost precision** and was kept anyway, because the two postings
behind it say "Candidates must be: Fluent in Python programming" — the extractor
was getting a plain statement wrong. The seventh line then returned the
precision and more, from a defect the sixth made visible.

### Two ordinary English words were required technologies

Found by grading, not by reading:

- **`react`** — "the ability to react quickly and accurately to rapidly changing
  market conditions" is a line in four Akuna trading postings, and bare `react`
  made the JavaScript library a **required** technology on eight postings that
  never mention it.
- **`outlook`** — "eager to solve challenging problems with a pragmatic outlook"
  made the mail client required on two Jump research postings. This one was
  self-inflicted, added earlier in the same session.

Both are now `case_sensitive: true`, which is the rule `skills.yaml` already
documented for `Go` and `Rust` and which nobody had applied to these.

### The heading was harvested, not invented

Per the lesson Task 7 paid for. A harvest of heading-shaped phrases across the
60 labeled postings found `candidates must be` in exactly the 2 postings whose
`Python` was missing. The same harvest is what kept the other candidates out —
`the impact you will have`, `your core responsibilities` and `visa sponsorship`
are heading-shaped and are not requirements headings.

### What is still missed, and why it is a decision rather than a gap

17 of 122 labeled required technologies. Every one is a term `data/skills.yaml`
deliberately does not carry:

```
ACI 318, ASCE 7, IBC, IFC, AISC, FM Global     structural engineering codes
Kyriba, GTreasury, Trovata, TMS, Quantum       treasury management systems
US GAAP, IFRS                                  accounting standards
MS Office, Word                                too ambiguous to match safely
Excel, Google Sheets (1 posting)               a necessity call, not a miss
```

**The vocabulary is what the product knows, and it is a NYC *tech* product.**
Building codes and accounting standards are real requirements of real postings
in the corpus and they are not software skills; adding them would raise recall
by teaching the product a domain it does not serve. `Word` and `MS Office` are
left out for the reason `skills.yaml` already leaves out bare `node` and bare
`rest` — the word is too ordinary to match without inventing requirements.

This is a cap on recall and it is stated rather than papered over.

### `skills.yaml` is shared with resume extraction, and that was checked

34 entries were added, so a resume can now propose `SIEM` or `CUDA` too — that is
intended. What was verified rather than assumed: the fixture resume produces
**16 proposals before and 16 after, identical but for the vocabulary version**.
The additions introduce zero spurious resume proposals.

### `EXTRACTOR_VERSION` moved to `m3a.2`, and stored rows lag

The rules changed, so the stamp changed. **Rows written by `m3a.1` keep that
value until their posting is re-seeded or its description moves** — the
description-change trigger cannot help, because the text is identical and only
the rules changed. `make seed` refreshes them, and `make acceptance` confirms
`m3a.2` on the seeded corpus.

`sync_requirements`'s docstring claimed "the backfill script calls it". **There
is no backfill script** — the ninth instance in this project of a claim that
went stale in the direction nobody re-reads. Corrected to say what is true.

### What must not happen

**Do not tune against the answer key by editing the answer key.** It was
committed before any extraction rule existed, and that ordering is the only
reason these numbers mean anything. If a label looks wrong, it is fixed with a
recorded reason in the review, never quietly. **No label was edited in M3a.1.**

**All twelve M3a tasks are done and committed.** The three commands were run
locally at the branch head and their counts are read from the output, not
inferred:

```
make check        1280 Python, 159 web, ruff/mypy/eslint/tsc clean
make acceptance   57 verify checks + 41 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
alembic           down, up, no drift; both triggers present after the cycle
```

**`make acceptance` was run three times back to back and passed all three**,
which is the idempotency evidence rather than a hope about it. The single e2e
skip is the pre-existing honest one: `an unchanged board is not presented as a
problem` needs a board that has answered `304`.

**CI has not run on this branch.** Every previous milestone's PROGRESS entry at
this point carried a CI result; this one cannot. Six CI runs across this project
have failed and every one found something no local command had executed, so the
three green commands above are evidence about this machine and not yet evidence
about the branch. Pushing alone does not change that — see the top of this
section.

Once CI has run, the invariant this project learned twice applies before
merging — name the last commit CI executed, and check nothing outside `docs/`
follows it:

```
git diff <that-sha>..HEAD --stat    # must list nothing outside docs/
```

### What M3a is

The reading half of matching, and nothing else. A posting's requirements are
extracted by rules, stored with the characters they came from, and shown on the
job page quoting the posting's own words. **Nothing is compared against a person
yet** — no eligibility gate, no score, no `uncertain`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `c577d56` | Fixture selectors by eligibility shape, not location |
| 2 | `6a9b7cf` | Nine boards recorded, 153 postings |
| 3 | `b297c36`¹ | The labeling worksheet — six fix rounds, each measured |
| 4 | `9929aa0` | The answer key's schema, loader, and the two gate tests |
| 4b | `0f10284` | The key filled: 60 postings × 9 fields, audited |
| 5 | `44a70e7`² | `job_requirements`, migration `0011`, both triggers |
| 6 | `3722026` | The extractor — every proposal carrying its span |
| 6b | `7eb3750` | `match_all`, which keeps repeated occurrences |
| 7 | `7134094` | Grading against the answer key, and the rules it demanded |
| 8 | `7c950d5` | `sync_requirements` — extraction follows the description |
| 9 | `7f52a8f` | `GET /jobs/{id}` returns requirements with their spans |
| 10 | `38d5e69` | The job page, the Zod refinement, the parity guard |
| 11 | `7cff577` | The fifth coverage blind spot |
| 12 | this | The browser walk, `verify.py`, ADR 0015, the review |

¹ Task 3 landed across five commits of fix rounds; `b297c36` is the last.
² Task 5's trigger fix landed separately in `aa0235b`.

### The measured numbers

**Extraction, graded against the 60-posting answer key.** The key was committed
*before* any extraction rule existed, so this measures the rules rather than the
choice of examples:

**These are M3a's numbers, kept as they were when M3a closed. M3a.1 superseded
them — see the section above for the current figures and for why part of the
movement was the meter being fixed rather than the extractor improving.**

```
required technology   precision 0.659   recall 0.459   (tp 56, fp 29, fn 66)
necessity accuracy    0.668             over 199 labeled technologies
nice-to-haves reported as required      0            <- see below; this was wrong
```

Floors in CI at M3a: 0.65 / 0.45 / 0.66. Set *after* measuring, just under what
the extractor achieves — a floor picked before measuring is either unreachable
or vacuous and there is no way to tell which from the outside.

**The last line of that block was not true**, and M3a.1 is what proved it. The
comparison was raw-string, so a nice-to-have labeled `Apache Spark` reported as
canonical `Spark` did not register as a violation. The honest M3a figure is 1,
not 0.

**The first measurement was 0.432 / 0.156 / 0.447**, with an imagined heading
list. Setting a floor under that would have enshrined a broken extractor. The
103 misses were split by cause first: 60 are terms `data/skills.yaml` does not
carry and no rule can reach; 43 the extractor found and filed under the wrong
necessity. Only the second kind is an extraction defect.

**The answer key holds 60 postings across seven boards:**

```
akunacapital 15   anthropic 15   databricks 10   imc 7
openai 8          jumptrading 3  janestreet 2
```

**What the corpus could not demonstrate**, from the union of the nine boards'
`coverage_not_available_on_this_board` lists — the number is how many of the
nine boards lack that shape:

```
multi-level posting spanning an eligibility boundary      8 of 9
sponsorship stated in writing                             4 of 9
new grad / university programme in the title              3 of 9
internship in the title                                   2 of 9
a preferred section whose contents are not gaps           2 of 9
senior or above in the title — the seniority mismatch     1 of 9
a graduation year stated numerically                      1 of 9
internship employmentType                                 1 of 9
```

The first line is the important one. **A posting spanning an eligibility
boundary is absent from eight of nine boards**, so the case A13 calls hardest —
a role open to both a new grad and a senior — is the one the answer key can say
least about. M3b must not read its grading as evidence there.

### The queue's own acceptance, measured

`check_job_requirements` in `make acceptance`, compared **before and after**
rather than against an absolute state:

```
✓ the job detail answers                          HTTP 200, 4 required, 5 preferred
✓ requirements carry an extractor version         m3a.1
✓ every span quotes the description it points at  9 spans
✓ no single span is both required and preferred   4 required, 5 preferred
✓ changing the description clears the old rows    9 -> 0
✓ a description change replaces the requirements  9 -> 1
✓ the job is left as it was found                 nothing is left behind
```

**Its first version passed with nothing on either side.** It picked the first
posting with any requirements; that posting's three rows were all `mentioned`,
so the necessity line read "0 required, 0 preferred" and ticked green. It now
prefers a posting that can fail the check and prints the mix either way, so a
vacuous case is visible in the output rather than hidden behind a passing line.

### What M3a found that the plan did not predict

Eleven in Tasks 8–12 and **eight were in code or tests that reported success** —
the ninth milestone running. Tasks 1–7's are in their commit messages. Full
detail in `docs/reviews/milestone-3a-review.md`; the four worth reading here:

1. **The plan credited the wrong guard, and measuring said so.** The plan said
   delete-then-insert is what keeps a span honest when a description changes.
   It is not — Task 5's `jobs_description_change_clears_requirements` trigger
   already does, and **removing the delete leaves every description-change test
   green**. The delete's real job is idempotency: a second sync over unchanged
   text re-emits the same `(kind, value, char_start)` tuples and the unique
   constraint rejects them. This matters beyond a docstring — a reader who
   believes the delete is the integrity guarantee will delete the trigger,
   because the trigger looks redundant. It is the other way round.
2. **An unconditional re-extract on the update path churns invisibly.**
   Identical row counts, every row replaced, `created_at` reset across the
   corpus each time any board answers. A salary edit changes fields and moves
   no character. Gated on the description hash; the guard compares row **ids**
   rather than counts, because counts are exactly what this failure preserves.
3. **A "not built" reason had gone stale, for the third milestone running.**
   The `skill` filter still blamed the absence of the skill taxonomy, which
   shipped at M2c. It is always the same direction: nobody re-reads that list
   when the thing it waits on lands. The filter stays deferred for a reason
   that is now measured — at 0.459 recall it would hide more than half the
   postings that ask for a skill and return them as an empty result, which
   reads as "no such job".

   **That reason is itself now stale, one milestone later, in the same
   direction.** M3a.1 took recall to 0.861, so "it would hide more than half"
   is no longer true. The `skill` filter's deferral needs re-deciding on the
   current number rather than inheriting this one — which is the fourth
   milestone running that this exact pattern has appeared, and the first time
   it has been caught in the same session that invalidated it.
4. **A component-test fixture was a cast, not a check.**
   `const BASE: JobDetail = {...}` asserts a shape without verifying one, so it
   went stale the instant this milestone added two fields and said nothing —
   the render crashed instead. Now parsed through `jobDetailSchema`. Second
   time this project has shipped that exact mistake.

### The mutation that should have failed and did not

Moving the delete after the empty-text guard in `sync_requirements` fails
**zero** tests. Chasing why is what produced finding 1 above. It is recorded
because a mutation that survives is the more useful result and the one easiest
to write off as "the mutation was not meaningful".

### Not real yet — M3a

- **Recall was 0.459 at M3a and is 0.861 after M3a.1.** The remaining 17 misses
  are all terms `data/skills.yaml` deliberately does not carry — building codes,
  treasury systems, accounting standards — and that cap is a decision recorded
  in the M3a.1 section above, not a gap waiting to be closed.
- **Necessity accuracy was 0.668 at M3a and is 0.915 after M3a.1.** It is not
  1.0, so some technologies are still filed under the wrong heading. **The job
  page makes this visible rather than hiding it**: measured on the seeded
  corpus at M3a, 2 of 32 rows shown as `required` sat beside a quoted sentence
  that itself says "preferred" or "a plus". A reader can see the disagreement
  because the sentence is printed next to the claim. That is the argument for
  showing the quote. **That 2-of-32 count was measured before M3a.1 and has not
  been re-measured since** — the numbers behind it moved and this line has not.
- **The answer key is model-labeled, not human-verified.** Two `+equivalent`
  calls read an escape hatch worded without the word "equivalent" — Akuna
  8035515's *"or evidence of mathematical and quantitative skill"* and OpenAI
  8fb1615c's *"or have a demonstrated track record"*. Both are kept, because
  `+equivalent` resolves to `uncertain` and the alternative tells a qualified
  person they are blocked. They are the two entries most likely to be wrong.
- **93 of the 153 recorded postings are committed and unlabeled.** Deliberate:
  the payloads are real and cheap to keep, and re-recording later costs a
  network round against nine live boards.
- **`has_equivalence` is stored and read by nothing** but the tests and a badge
  on the job page. A13 requires M3b's gate resolve it to `uncertain` rather
  than `ineligible`; storing it now is what makes that possible without
  re-extracting.
- **The `jobs_description_change_clears_requirements` trigger is guarded by
  exactly one test.** Dropping it turns exactly that one red. Thin for a
  structural guarantee, and recorded rather than padded — its whole purpose is
  the writer that does *not* call `sync_requirements`.
- **Everything in `matching.md` §9 is M3b or later**: the eligibility gate, the
  score and its components, role-family and seniority classification, the
  project evidence graph, and the `uncertain` resolution. None is stubbed.

### The M3a plan

`docs/plans/2026-08-04-m3a-answer-key.md`. Two merged remote branches are still
there — `origin/m2c-profile-and-resume` and `origin/m1a-provider-breadth` — both
fully merged into `main` with nothing ahead. Deleting them needs a permission
this session did not have; it is one `git push origin --delete`.

---

### The M2d record, kept below

All seven tasks are done, committed, pushed, and CI-green. The three commands
were run locally at the branch head and their counts are read from the output,
not inferred:

```
make check        1136 Python, 144 web, ruff/mypy/eslint/tsc clean
make acceptance   50 verify checks + 37 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
alembic check     no drift; 0010 up, down, up clean
```

**`make acceptance` was run three times back to back and passed all three**,
which is the idempotency evidence rather than a hope about it. The single e2e
skip is the pre-existing honest one: `an unchanged board is not presented as a
problem` needs a board that has answered `304`.

**CI is green, on the first attempt.** [PR #8](https://github.com/Tahmudun/Nightshift/pull/8),
run [30884388243](https://github.com/Tahmudun/Nightshift/actions/runs/30884388243)
— **all five jobs**, counts read from the job logs rather than inferred:

```
python       257s   1136 passed, zero skipped
e2e          187s   5 degraded + 37 seeded passed, 1 skipped
migrations    80s   up, down, up, and no drift
web           63s   17 files, 144 tests
secret scan   10s
```

`headSha` on the run is `c6e5a977225884c84cd69ea47adbbc24cf43108f`, checked
against the branch head rather than assumed. **1136 in CI matches 1136
locally**, so the database-backed tests really ran there too. No retries and no
flakes are recorded in the logs — worth checking explicitly, because the review
below marks a test `test.slow()` for parallel-load reasons and a silent retry
would have hidden whether that worked.

Six CI runs across this project have failed and every one found something no
local command had executed. This is the fourth first-try pass; it is recorded
precisely because it is not the usual outcome.

**`a6c4ead` is the last commit containing anything CI executes** — everything
after it touches `docs/` only, which is one command:

```
git diff a6c4ead..HEAD --stat    # must list nothing outside docs/
```

If that shows a file under `apps/`, `services/`, `infra/`, `data/` or the
Makefile, the recorded results do not cover the branch and the three commands
must run again.

**M2d earns none of M2's four acceptance criteria, and that is not a gap.** All
four were verified at M2a, M2b and M2c and are recorded below, unchanged. What
M2d completes is M2's *deliverable* list in `CLAUDE.md` §6, of which the daily
queue was the last item.

Seven tasks, branch `m2d-daily-queue`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `9bef08a` | `domain/queue.py` — four queries, three thresholds, the `actor = 'user'` filter |
| 2 | `4ed6390` | Migration `0010`, two partial indexes, the first query-plan assertion |
| 3 | `02eeb39`¹ | `GET /queue`, the schemas, the four named absences |
| 4 | `a3d6b11` | Zod schemas, `fetchQueue`, and five enums added to the parity guard |
| 5 | `1f39435` | `QueuePanel`, `/operate/queue`, the Operate link |
| 6 | `02eeb39` | The browser walk and `check_daily_queue` |
| 7 | `a6c4ead` | ADR 0014, the review, the reworked plan assertion |

¹ Task 3's route landed in its own commit; `02eeb39` is Task 6's.

### The queue's own acceptance, measured

`check_daily_queue` in `make acceptance`, compared **before and after** rather
than against an absolute state — asserting "the queue is empty" would pass
vacuously on a fresh database and fail on a developer's own:

```
✓ the queue answers                              HTTP 200
✓ four sections, always                          follow_up, interviews_approaching, stale_saved, closed_while_saved
✓ four deferred rows, each with a reason         4
✓ no deferred row carries a number
✓ the thresholds are coherent                    7 / 21 / 14
✓ a past next action adds exactly one follow-up  0 -> 1
✓ every row says why it is there                 1 rows
✓ the row names the reason it was added          you set a next action for 1 Jan
✓ clearing the next action removes the row again 1 -> 0
✓ the application is left as it was found        nothing is left behind
```

### What M2d found that the plan did not predict

Six, and **three were in code or tests that reported success** — the eighth
milestone running to record that pattern. Full detail in
`docs/reviews/milestone-2d-review.md`; the three worth reading here:

1. **The query-plan assertion was wrong twice, in opposite directions.** The
   plan's version could not fail: every queue statement joins `jobs` and
   `companies`, so `pk_jobs` and `pk_companies` appear in all four plans
   whatever the filter does — measured by dropping both new indexes and watching
   all four still report index nodes. The fix then over-corrected by naming the
   expected index, and **that broke within the hour**: `interviews_approaching`
   used one index against one corpus and another against a corpus a few
   applications larger, which is the planner switching from a time scan to a
   nested loop and doing its job. The property that holds is *no fall back to
   reading a whole table*; with `enable_seqscan = off` a sequential scan means no
   usable index exists. Dropping all three `application_events` indexes turns
   three of four red. **Between a vacuous assertion and a brittle one there was a
   correct one, and finding it took measuring the planner twice.**
2. **The plan's test helper could not insert a closed job.**
   `ck_jobs_closed_at_matches_status` is a biconditional, so setting `status`
   alone fails — six tests, every one about "closed while saved". The schema was
   right and the plan was wrong.
3. **Operate claimed tracking was not built, directly below a link to it.** The
   "Not built yet" list still said *"Saving, applying, and stage tracking —
   milestone 2"*, false since M2b. M2c's review made the same finding about a
   different list, which makes this the pattern rather than the incident: **a
   "not built" list goes stale in the one direction nobody checks**, because
   nobody re-reads it when a feature lands.

Also: the plan's browser walk would not have run twice — it gave both tests the
same job, and an `interview_scheduled` event cannot be deleted, so the
follow-up test's "the row is gone" assertion would fail on the second run of the
day. That is the exact bug M2b's pipeline test shipped.

### A prediction the plan made that did not come true

The plan added M2b's four enums to `test_enum_parity.py` and predicted **at
least one would disagree** with Python, reasoning that hand-transcribed and
never machine-checked is what produced M2c's defect. **All four were correct.**
Recorded rather than deleted — the prediction was sound and the outcome was
better than it. The guard now covers thirteen enums instead of nine, and
`QueueSectionKey` is the first entry in it that is not a database enum.

### Not real yet — M2d

The four rows PRODUCT-SPEC §10.4 asks for that need M3. **None are stubbed**;
each is named on the page with its reason, rendered from the API's own
`deferred_rows`:

- **Best new internships** — 'best' is a ranking and there is no match score.
- **High-match roles closing soon** — needs a score *and* a deadline most
  sources never publish (A10).
- **Resume mismatch warnings** — needs requirement extraction and the evidence
  graph.
- **The one thing to do today** — ranking across four heterogeneous row types.

Also deliberately absent: **dismiss and snooze** (§7.3 — new state, a new table,
and a decision about whether a dismissed row returns tomorrow), and
**`assessment_due_at`** (§7.1 — `next_action_at` already carries the date).

**`offer` is excluded from every queue section.** An offer is a decision rather
than a chase and the pipeline shows it prominently. That is a judgement a real
user might overturn, and it is one tuple — `TERMINAL_STAGES` — in one file.

**The browser walk leaves one archived application**, for the same reason
`check_application_tracking` does: an `interview_scheduled` event is append-only,
so archiving is the only way to take a role back out of the queue. Stated in the
test. `check_daily_queue` itself leaves nothing.

### The M2d plan, and the two branches still on the remote

`docs/plans/2026-08-04-m2d-daily-queue.md`. Two merged remote branches are still
there — `origin/m2c-profile-and-resume` and `origin/m1a-provider-breadth` — both
fully merged into `main` with nothing ahead. Deleting them needs a permission
this session did not have; it is one `git push origin --delete`.

**Next after M2d: merge, then M3 — explainable matching.**

---

### The M2c record, kept below

**PR #7 is merged.** `main` is at `e42d612`, merged 2026-08-04 by the human,
checked against the PR rather than assumed. The pre-merge invariant held: `git
diff 1fe34ef..HEAD --stat` listed one file, `docs/PROGRESS.md`, so the recorded
CI result covered every line of code on the branch. `m2c-profile-and-resume` is
deleted locally.

**Two remote branches are still there and both are fully merged into `main`
with nothing ahead** — `origin/m2c-profile-and-resume` and, from much longer
ago, `origin/m1a-provider-breadth`. The M1 record below claims every milestone
branch was deleted "both locally and on the remote", and for `m1a` that was
never true. Deleting them needs a permission this session did not have; it is a
human's `git push origin --delete` and costs nothing to defer.

**Branch `m2d-daily-queue` is open at `0465e63`** with two docs commits on it
and no code yet.

### What M2d is, and what it earns

Four rows the system can compute honestly — follow up, interviews approaching,
stale saved, closed while saved — plus the four PRODUCT-SPEC §10.4 asks for
that need M3, named on the page with their reason rather than rendered as
empty sections. An empty section claims "you have none of these"; a named
absence says "this does not exist yet". Only one of those is true.

**M2d earns none of M2's four acceptance criteria, and that is not a gap.** All
four were verified at M2a, M2b and M2c and are recorded below. What M2d
completes is M2's *deliverable* list in `CLAUDE.md` §6, of which the daily
queue is the last item.

### Three decisions taken on 2026-08-04, before planning

All three are recorded in `docs/architecture/command-center.md` §7, which was
amended rather than left to the plan:

| Decision | Where |
|---|---|
| Thresholds: 7 days of silence, 21 days stale, a 14-day interview horizon | §7 |
| "Assessments due" folds into Follow up rather than getting its own row | §7.1 |
| The queue writes nothing — no dismiss, no snooze, every row a link | §7.3 |

**The second one was a discrepancy, not a preference.** PRODUCT-SPEC §10.4
lists nine queue rows. `command-center.md` §7 named eight and had lost
"Assessments due" without saying so — the exact failure mode that document
exists to prevent. `applications` carries `next_action_at` and nothing else
date-shaped, so an assessment with a date already surfaces under Follow up;
the fold is now written down with its reason instead of being a silent drop.

### What the plan checked against the code rather than assuming

Three things, and all three would have been wrong in the executor's hands:

1. **The query-plan helper is `_plan`, not a new `EXPLAIN` call.** It compiles
   with `paramstyle="named"` and sets `enable_seqscan = off` inside the
   transaction; a second copy would not have matched how the existing
   assertions run.
2. **There is no shared `client` fixture.** Each route-test file defines its
   own, because it overrides `current_user_id` as well as the session so the
   suite does not depend on `make seed` having run. Reproduced in the task.
3. **M2b's four enums cross the Python/TypeScript boundary unguarded.**
   `test_enum_parity.py` covers nine, all of them M2c's. The queue's row schema
   parses `current_stage` through `applicationStageSchema`, so M2d depends on
   one of them being right. The plan adds all five — the four plus its own
   `QueueSectionKey` — and predicts at least one will fail on its first run,
   because hand-transcribed and never machine-checked is the exact condition
   that produced M2c's defect.

**M2b built for this milestone deliberately** and it shows: `next_action_at` is
already indexed with a comment naming M2d, and `ApplicationEvent`'s docstring
already records that `occurred_at` may be in the future because an
`interview_scheduled` event carries the interview's own time. Neither needed
changing.

### The M2c record, kept below

**All eleven tasks are done, committed, pushed, and CI-green.** The three
commands were run locally and their counts are read from the output, not
inferred:

```
make check        1093 Python, 129 web, ruff/mypy/eslint/tsc clean
make acceptance   73 verify checks + 34 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
```

**`make acceptance` was run three times back to back and passed all three**,
which is the idempotency evidence rather than a hope about it. The single e2e
skip is the pre-existing honest one: `an unchanged board is not presented as a
problem` needs a board that has answered `304`.

**CI is green, on the first attempt.** [PR #7](https://github.com/Tahmudun/Nightshift/pull/7),
run [30877140583](https://github.com/Tahmudun/Nightshift/actions/runs/30877140583)
— **all five jobs**, counts read from the job logs rather than inferred:

```
python       4m09s   1093 passed, zero skipped
e2e          2m39s   5 degraded + 34 seeded passed, 1 skipped
migrations   1m20s   up, down, up, and no drift
web            55s   16 files, 129 tests
secret scan     8s
```

`headSha` on the run is `e63ec2fe525738db7eb8791971a68a59566912fb`, checked
against the branch head rather than assumed. **1093 in CI matches 1093
locally**, so the database-backed tests really ran there too. The single e2e
skip is the pre-existing honest one.

Six CI runs across this project have failed and every one found something no
local command had executed. This is the third first-try pass; it is recorded
precisely because it is not the usual outcome.

**`1fe34ef` is the last commit containing anything CI executes** — and it is the
docs commit, because the review found two defects and fixing them is code
(§2.1's provenance link, §3.3's new guard). The three commands above were run
*after* those fixes and before that commit, so their counts cover it. Every
commit after `1fe34ef` must touch `docs/` only, which is one command:

```
git diff 1fe34ef..HEAD --stat    # must list nothing outside docs/
```

If that shows a file under `apps/`, `services/`, `infra/`, `data/` or the
Makefile, the recorded results do not cover the branch and the three commands
must run again. This is the invariant M1d wrote down after PROGRESS twice
carried a green claim beside a SHA that was no longer the head.

Eleven tasks, eleven commits, branch `m2c-profile-and-resume`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `09a4724` | Paste, `.txt` and PDF, failing whole; `pypdf` + `python-multipart` |
| 2 | `b82b652` | `data/skills.yaml` and the matcher |
| 3 | `72814c9` | The extractor — 16 proposals, every one carrying its span |
| 4 | `a87b280` | Migration `0009`, four tables, the span-quoting trigger |
| 5 | `74f1076` | `domain/profile.py` — the only writer of a confirmed fact |
| 6 | `e99e085` | Thirteen routes; a resume can be selected on an application |
| 7 | `61ff9c3` | Zod schemas and the client, and the enum-parity guard |
| 8 | `8390704` | The profile page, the skill list, the upload control |
| 9 | `e5f7fdc` | The confirmation screen and the overlapping-span highlighter |
| 10 | `f2d01f0` | The browser walk, and `check_profile_confirmation` |
| 11 | this | ADR 0013, the review, this entry |

### Criterion 4, earned: no parsed resume fact is stored as confirmed without a user action

Four independent guards, each shown able to fail:

| Guard | Where | Shown able to fail by |
|---|---|---|
| Two tables, one writer | `domain/profile.py` is the only module that may write `users` / `user_skills` / `user_projects` | `test_nothing_infers.py` — three greps: assignment, constructor, `setattr` |
| The extractor cannot reach the confirmed tables | It does not import the ORM | `test_the_extractor_does_not_call_back_into_the_writer` |
| Every proposal quotes its span | Trigger `resume_extractions_span_must_quote`, re-asserted in the API response and again in Zod | Task 4's tests; and a one-character shift in the response turns the API test red |
| The browser confirms nothing on its own | `ExtractionReview` opens with every row undecided | `confirms nothing until somebody says so` |

**The browser test is the criterion, not a proxy for it.**
`apps/web/e2e-seeded/profile.spec.ts` pastes the fixture resume, asserts sixteen
proposals with the characters each came from, then **navigates to the profile and
finds it unchanged** — that step is the criterion. Only then does it confirm two
and reject one, and assert exactly those outcomes, that the rejected skill is
absent, that it survives a reload, and that it survives deleting the resume.

`check_profile_confirmation` asserts the same over HTTP and compares the profile
**before and after** rather than asserting "no skills", which would pass
vacuously on a fresh database and fail on a developer's own. Measured:

```
✓ pasting a resume succeeds                              HTTP 201
✓ the resume produced proposals                          16
✓ every proposal quotes the text it points at
✓ invariant I2: every proposal is still pending
✓ invariant I2: reading a resume confirmed nothing
✓ exactly the confirmed skill was added, and nothing else   Python
✓ the confirmed skill points back at the words it came from resume:e445e1e0…#238-244
✓ a confirmed skill survives deleting the resume it came from
✓ the skill this check added is removed again            nothing is left behind
```

### What M2c found that the plan did not predict

**Eleven, and eight were in code or tests that reported success** — the seventh
milestone running to record that pattern. Full detail in
`docs/reviews/milestone-2c-review.md`; the seven worth reading here are below,
starting with the four from Tasks 1–5:

1. **A vocabulary test could not fail.** `test_the_longest_term_wins_when_two_
   overlap` used "Machine Learning", which contains no shorter vocabulary term,
   so the longest-first ordering it claimed to guard was never exercised. Found
   by mutating the sort and watching nothing go red. Rewritten over "Tailwind
   CSS", where three terms genuinely overlap.
2. **`op.add_column` does not create an enum type**, unlike `create_table`. The
   autogenerated migration failed with "type does not exist" on its first run.
   Restructured to the house pattern from `0001` and `0004`.
3. **Autogenerate emitted `nightshift.db.types.UTCDateTime` with no import** —
   the fourth migration in this project to do it — **and** omitted both `users`
   check constraints, because it does not emit table constraints for a table it
   is only adding columns to, **and** emitted no `DROP TYPE`, which would have
   left nine enums behind on downgrade.
4. **`parents[3]` is `services/`, not the repo root.** The vocabulary loader
   pointed at a path that does not exist. This is the same off-by-one M1c's
   plan made, and the reason `domain/registry.py` uses `parents[4]`.

And the three from Tasks 6–11:

5. **Two enum vocabularies were transcribed into TypeScript wrong, and nothing
   local could see it.** `WorkAuthorization` gained a `requires_sponsorship` that
   does not exist — the real member is `needs_sponsorship` — and
   `SkillSourceType` lost `assessment` and `github`. The Python suite never reads
   TypeScript; the web suite parses fixtures written to match the schema. **The
   failure would have been a real response reaching a real browser and Zod
   refusing to parse the page.** Found by printing the enums rather than reading
   them. `tests/test_enum_parity.py` is the guard and it is the only test in the
   repo that reads both sides of that boundary at once. This is the fifth time a
   defect has lived somewhere no local command looks.
6. **A skill's provenance linked to a resume that may have been deleted.**
   Deleting a resume deliberately keeps the skills it produced, so the pointer
   outlives its target and the link 404s. A 404 dressed up as evidence is worse
   than no link. The provenance is still stated; only the link is withheld, and
   the row says "in a resume you have since deleted".
7. **A component test was fed data the API cannot produce.** `ExtractionReview`'s
   fixture put `Python` at characters 34–40, which is `"\nPytho"` — the right
   length, the wrong words, and exactly the row `resumeDetailSchema` exists to
   refuse, sitting inside the test for it. The fixture is now parsed through that
   schema in its own test.

Also corrected against measurement rather than assumption: the fixture
generator's docstring claimed `encrypted.pdf` could not be byte-reproducible.
Two consecutive runs produce identical bytes on pypdf 6.14, so it now records
what was measured. And `pypdf` is BSD-3-Clause, not the plan's "MIT" —
`costs.md` had it right.

### Mutation testing: ten more, and nine killed their intended test

The tenth found a test that could not fail rather than a rule that was wrong,
which is the same outcome Task 2 recorded. `HighlightedText` drops a span whose
bounds fall outside the text rather than clamping it; the test asserted the
rendered text was unchanged, **and it is unchanged either way** — an
out-of-range slice is the empty string whichever branch runs. The assertion is
on the marks now, and the same mutation kills it.

The most valuable of the ten: inserting `return []` at the top of
`extract_proposals` fails **19 tests** across three files, so the extraction path
is decorative in none of them.

### Three things the review checked rather than assumed

- **Nothing logs the resume text.** No logging statement in
  `services/api/nightshift/` carries `parsed_text` or a resume body, and
  `logging.py` has no request-body middleware. This is the most personal data
  the project holds (§13).
- **No proposal can come to quote different words.** Nothing assigns
  `resumes.parsed_text` after creation. **The trigger cannot catch this** — it
  fires on `resume_extractions`, so an UPDATE to the parent passes unexamined
  while every child row silently starts lying.
  `test_nothing_rewrites_the_text_a_proposal_quotes` is the new guard.
- **`make acceptance` leaves nothing behind from M2c.** Both the verify check and
  the browser walk clean up after themselves, and the browser walk normalises on
  *entry* as well — M2b's pipeline test could not run twice for the opposite
  reason. `check_application_tracking` still leaves one archived application, by
  design and stated in its docstring.

### The plan being executed: `docs/plans/2026-08-03-m2c-profile-and-resume.md`

**M2b is merged and its branch is gone.** PR #6 merged at `2f984f3` with head
`40d7dd8`, checked against the PR rather than assumed; `m2b-the-loop` is deleted
locally and on the remote. The pre-merge invariant held — `git diff
6a10bb6..HEAD --stat` listed one file, `docs/PROGRESS.md`, so the recorded CI
result covered every line of code on the branch.

**M2c is the slice with the most invariant risk in M2**, which is why
`command-center.md` §1 put it third. Everything a resume says is a claim about a
person, and I2 forbids storing any of it as fact without an explicit click. The
enforcement is structural: proposals live in `resume_extractions`, confirmed
facts live in `users` / `user_skills` / `user_projects`, and one module may
write the second set.

**One decision the human made on 2026-08-03, before planning:** resume input is
**paste, PDF, and `.txt`**. PDF costs one dependency (`pypdf` — pure Python,
MIT, no native libraries, no key, so `make demo` stays offline). `.docx` is not
supported and the upload control says so by name. The confirmation screen shows
the text the extractor actually read, which is what makes PDF safe to accept: a
scrambled two-column extraction is visible rather than hidden behind a tidy
form.

### The M2b record, kept below

**M2b is complete and M2's headline criterion is earned.** All three commands
were run at the branch head and their counts are read from the output, not
inferred:

```
make check        992 Python, 84 web, ruff/mypy/eslint/tsc clean
make acceptance   28 verify checks + 31 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
alembic check     no drift, up/down/up clean on migration 0008
```

**`make acceptance` was run three times back to back and passed all three**,
which is the evidence for the idempotency claim rather than a hope about it.
The single e2e skip is the pre-existing honest one: `an unchanged board is not
presented as a problem` needs a board that has answered `304`.

**CI is green, on the first attempt.** Run
[30797523109](https://github.com/Tahmudun/Nightshift/actions/runs/30797523109)
at `6a10bb6` — **all five jobs**, counts read from the job logs rather than
inferred:

```
python       241s   992 passed, zero skipped
e2e          164s   5 degraded + 31 seeded passed, 1 skipped
migrations    79s   up, down, up, and no drift
web           63s   11 files, 84 tests
secret scan   47s
```

`headSha` on the run is `6a10bb67d5172ef615816d9e75a16f3f33bcfa6a`, checked
against the branch head rather than assumed. **992 in CI matches 992 locally**,
so the database-backed tests really ran there too. The single e2e skip is the
pre-existing honest one.

Five CI runs across this project have failed and every one found something no
local command had executed. This is the second first-try pass; it is recorded
precisely because it is not the usual outcome.

The invariant this project has learned twice still applies before merging —
`6a10bb6` is the last commit CI has seen:

```
git diff 6a10bb6..HEAD --stat    # must list nothing outside docs/
```

Eight tasks, eight commits, branch `m2b-the-loop`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `2c51a16` | The stage machine — 90 ordered pairs, classify never block |
| 2 | `d02cb08` | `applications`, `application_events`, migration `0008`, the trigger |
| 3 | `765b792` | The write layer — no change without an event |
| 4 | `bb09b53` | Nine routes, and the guard that nothing applies |
| 5 | `aca7957` | A closing listing writes an event, never a stage change |
| 6 | `00c5ee1` | Zod schemas and the eight client mutations |
| 7 | `f0a3eaf` | The save control, on the list and the job page |
| 8 | `e711a45` | The pipeline board and the application page |
| 9 | this | The browser loop test, `verify.py`, ADR 0012, the review, this entry |

### Acceptance criteria — M2

`CLAUDE.md` §6 gives M2 four. **All four are now earned and verified below** —
three by M2b, the fourth by M2c. The <200ms filter criterion was earned at M2a
and is unchanged.

**M2 is not closed.** M2d — the daily queue — is still to build, and CI has not
run on M2c.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Full discover→save→apply→track loop works with zero 3D | **VERIFIED** (M2b) | `apps/web/e2e-seeded/pipeline.spec.ts`, `discover, save, apply, track — the whole loop`. Walks a real browser: open a role, save it, assert the control reports a stage, open the application, assert **no control that applies**, record "I applied", write a note, move to `interview`, read the history back with its transition class, archive, restore, and correct the stage back. 15.2 s against the seeded stack. **That test is the criterion, not a proxy for it.** |
| 2 | Events are append-only, enforced at the DB level, not by convention | **VERIFIED** (M2b) | Trigger `application_events_append_only`, reusing `nightshift_refuse_mutation()` from `0002`. Three tests attempt the violation and catch the error: UPDATE, DELETE, and **deleting the parent application**, which cascades into the trigger. Mutation-checked: dropping the trigger turns exactly those 3 red. An application therefore cannot be deleted at all — archive is the only removal, and that is a property of the schema rather than a UI choice |
| 3 | No stage moves without a user (invariant I5) | **VERIFIED** (M2b) | Enforced in three places and each proven able to fail. Python: `SystemMayNotSetStageError`. Database: `ck_application_events_only_a_user_moves_a_stage` — neutering it to `true` fails 1 test, and a `system` actor carrying a stage fails 3. Client: `applicationEventSchema`'s `superRefine`. Plus `tests/test_nothing_applies.py`, which asserts `PoliteClient` exposes no write method and that `domain/applications.py` is the only module assigning `current_stage`. A closing listing writes a `listing_closed` event and the stage does not move — asserted end to end through `apply_freshness`, not through the helper |
| 4 | No parsed resume fact is stored as confirmed without a user action | **VERIFIED** (M2c) | `apps/web/e2e-seeded/profile.spec.ts`, `a resume proposes, and confirms nothing until it is told to`. Pastes the fixture resume, asserts 16 proposals each showing the characters it came from, then **navigates to the profile and finds it unchanged** — that step is the criterion. Then confirms two, rejects one, and asserts exactly those outcomes, that the rejected skill is absent, that it survives a reload, and that it survives deleting the resume. Four guards behind it, each shown able to fail — see the table above. Also asserted over HTTP by `check_profile_confirmation` in `make acceptance` |

The <200ms filter criterion was earned at M2a and is unchanged.

### What M2b found that the plan did not predict

Ten findings. **Six were in code or tests that reported success** — the sixth
milestone running to record that pattern. Full detail in
`docs/reviews/milestone-2b-review.md`; the four worth reading here:

1. **The event timeline could not be ordered, and every row looked present.**
   `created_at` defaulted to `now()`, copied from every other table. Postgres's
   `now()` is the *transaction* timestamp — measured: three inserts in one
   transaction give **1 distinct `now()` and 3 distinct `clock_timestamp()`**.
   With one value the sort falls through to a random UUID, so the history
   renders complete, plausible, and in the wrong order. Two of the plan's own
   tests failed on this before anything was changed. Fixed at the column;
   every other table keeps `now()`, which is right for them.
2. **A concurrent save returned HTTP 500, reproduced before being fixed.** Four
   simultaneous POSTs for one job: `[500, 500, 201, 500]`, one row. Data
   integrity never broke — that is the unique constraint working — but the
   loser of the race got a server error for a save that succeeded. Fixed with a
   savepoint and a re-read; re-measured across six rounds, **zero 500s**.
3. **A tracked job flashed an actionable Save button, and a browser test landed
   a click in that window.** `SaveJobButton` rendered the button whenever the
   query had not answered yet. The flake was the product telling the truth
   about itself: a person can click that. Fixed with a pending state — which
   then broke the test in a second way, because the test asked `isVisible()`
   before the control had settled. Both fixed.
4. **An archived application looked unsaved, and saving it did nothing.** The
   control queried without `archived`, so the route filtered the row out, the
   button said "Save", and the save returned 200 having changed nothing.

Three more, all in tests: a stage-change test asserted on the returned
in-memory object and could not detect a missing `session.add`; three Zod tests
passed before the schema existed, because `undefined.parse()` throws; and the
I5 source guard excluded the stage machine by basename, hiding a substring bug
where `.current_stage =` also matches `Application.current_stage == stage`.

### Three corrections M2b made to its own plan

- **The plan's browser test could not run twice.** It archived on the way out,
  and an archived application is excluded from the pipeline and refuses every
  mutation. Each test now normalises what it finds on entry rather than
  trusting its own tidy exit.
- **The posting link could not be built as specified.** The plan said
  `application_url ?? job.sources[0].canonical_url`; the application's `job` is
  a `JobSummaryOut` and carries no `sources`. An application with no recorded
  URL now says so, rather than a fabricated board link (I1).
- **The plan predicted the wrong test would catch a mutation.** It said that if
  `test_a_closing_listing_does_not_move_the_stage` did not fail, the test was
  wrong. It did not fail, and the test is right: the mutation writes a false
  *event* without touching `current_stage`. Recorded rather than "fixed".

### What M2b deliberately did not build

Profile and resume, with the confirmation step (M2c); the daily queue (M2d);
match score, eligibility, skill and internship-season filters (M3); boroughs
and any coordinate (M4). **Contacts** are unscheduled — a contact is a person
and needs its own table.

**None of these are stubbed.** The application page renders them by name with
the reason and the milestone, from the API's own `deferred_fields`.

### Not real yet

- **`make acceptance` leaves one archived application behind**, by design and
  stated in `check_application_tracking`'s docstring. `make reset-db` clears
  it. Deleting it is impossible — see acceptance criterion 2.
- **The seeded browser suite leaves two saved applications** in the developer's
  corpus, for the same reason: it tests the loop against a real stack.
- **`discovered` is an unreachable stage.** The enum value exists because M3
  will use it; nothing writes it today.


**M2a is complete. The first CI run failed and it caught a real defect no local
command had run** — see item 4 below. Fixed, and the second run is what the
merge decision should rest on.

```
make check        856 Python, 63 web, ruff/mypy/eslint/tsc clean   (read, not inferred)
make acceptance   18 verify checks + 27 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests          <- the suite CI caught, run separately
alembic check     no drift, all three migrations applied
```

**CI is green.** Run
[30788730379](https://github.com/Tahmudun/Nightshift/actions/runs/30788730379)
at `76190c8` — **all five jobs**, counts read from the job logs rather than
inferred:

```
python       232s   856 passed, zero skipped
e2e          164s   5 degraded + 27 seeded passed, 1 skipped
migrations    77s   up, down, up, and no drift
web           55s
secret scan    8s
```

`headSha` on the run is `76190c88657f8a6a1d4883ef3a469a0501a41bac`, checked
against the branch head rather than assumed. **856 in CI matches 856 locally**,
so the database-backed tests really ran there too. The single e2e skip is the
pre-existing honest one: `an unchanged board is not presented as a problem`
needs a board that has answered `304`, and the seeded stack has polled nothing.

**The first run failed, and it earned its keep.** Run
[30788290888](https://github.com/Tahmudun/Nightshift/actions/runs/30788290888)
at `1aabc58`: four of five green, `e2e` red — item 4 below. Four CI runs across
this project have now failed, and every one found something no local command
had executed.

The M1d invariant still applies and is still cheap to check before merging:

```
git diff 76190c8..HEAD --stat    # must list nothing outside docs/
```

Ten tasks, ten commits, branch `m2a-search-and-detail`.

| Task | Commit | What it did |
|---|---|---|
| 1–2 | `4120415` | `search_vector`, the filter indexes, `domain/search.py` |
| 3 | `0eed338` | `/jobs` filters on text, city, type, source, date, salary |
| 4 | `0c30d2c` | The query-plan guard — and the defect it immediately found |
| 5 | `69fdd89` | `/companies` and `/companies/{id}` |
| 6 | `3920b9d` | Zod schemas and the API client |
| 7 | `7d42ceb` | The filter panel, state in the URL |
| 8–9 | `1df5156` | Job and company detail pages |
| 10 | this | Seeded browser tests, review, this entry |

### Criterion: filters return in <200ms on seeded data

Measured against the 31-job seeded corpus, worst of five requests each:

```
q=engineer&status=open                        9 hits    31.6 ms
q=engineer&include_description=true          21 hits    40.1 ms
city=New York&employment_type=full_time      15 hits    36.1 ms
salary_at_least=90000                        27 hits    42.7 ms
(no filter)                                  31 hits    53.4 ms
```

**The first attempt at this measurement was wrong and looked right.** Run
straight after `make check`, it produced five plausible figures of 12–23 ms —
against a corpus of **zero jobs**, because the Python test fixtures truncate
the dev database. It was caught only because the corpus size was printed
beside the timings. Any future measurement must print what it measured against.

The number is not the guard. `tests/test_query_plans.py` is: it asserts every
filter is servable by an index, which is what stays true as the corpus grows.

### What M2a found that the plan did not predict

Nine defects, **seven in code that reported success** — the same pattern M1a,
M1b, M1c and M1d each recorded, now five milestones running. Full detail in
`docs/reviews/milestone-2a-review.md`; the four worth reading here:

1. **Searching descriptions by default made the search box useless.**
   `q=developer` matched all nine recorded Alloy postings, because it stems to
   `develop` and every description says "business development" somewhere. Not
   an index bug — it is what full-text search over long documents does with no
   relevance ranking to sort the noise down, and ranking is M3. The tempting
   fix was to change the test, which would have shipped a search box where
   typing a job title returns the corpus. Fixed with a title-only vector
   (migration `0006`) and `include_description` as an opt-in.
2. **The salary floor could not be served by an index**, found by the
   query-plan test on its first run. The floor is an `OR` across both bounds
   and Postgres needs an index on each side to build a BitmapOr; only
   `salary_max` had one. **The wrong plan returns exactly the right rows**, so
   this is invisible in the code, in the response, and in every correctness
   test. Migration `0007`.
3. **Two defaults governed one behaviour and only one was guarded.** Flipping
   `JobSearchQuery.include_description` failed nothing, because the FastAPI
   route re-declares its own default and that is what governs. Found by
   mutation testing — the guard looked present and was not.
4. **`make check` and `make acceptance` both miss the degraded e2e suite, and
   CI caught what they missed.** The new remote-policy filter added a second
   "Remote" to `/explore`, breaking a page-wide text assertion in
   `make test-e2e`. Neither aggregate target runs that suite and neither can —
   it needs the API *down*, which is the opposite stack state from acceptance.
   **`make test-e2e` is a third command and must be run before pushing.** This
   is the fifth time in this project that a defect lived somewhere no local
   command looks.

### Two corrections M2a made to its own plan

- **`ix_job_locations_city_lower` must be declared on the model.** The plan
  said the opposite. Measured: with the index in the database and absent from
  the model, `alembic check` reports `remove_index` and fails.
- **Two Playwright failures were harness, not product.** `.check()` on a
  URL-controlled checkbox catches the input mid-revert, and the first
  navigation into a dynamic route pays `next dev`'s on-demand compile. Both
  diagnosed by probing the browser rather than by assuming the link was broken.

### What M2a deliberately did not build

Save, apply, tracking, notes, stage history (M2b); profile and resume (M2c);
the daily queue (M2d); match score, eligibility, skill and internship-season
filters (M3); boroughs and any coordinate (M4).

**None of these are stubbed.** Where the spec asks for them, the UI names them
and says what they are waiting for — the filter panel renders five disabled
filters with their reasons, and the job page lists seven uncomputed fields.

---

### The M1 record, kept below

**M1 is closed. All four PRs are merged, `main` is at `044189e`, and every
milestone branch is deleted both locally and on the remote.** The `git diff
75d9ab7..HEAD` check below was performed before merging and listed nothing
outside `docs/`, so the recorded CI result covered the branch.

**M2 is scoped and its design is written: `docs/architecture/command-center.md`.**
Read it before any M2 work; `CLAUDE.md`'s read-order table now requires it.

Three decisions the human made on 2026-08-03, all recorded in that document:

| Decision | Where |
|---|---|
| Slice order: search → track → resume → queue, so the loop criterion is earned at M2b | §1 |
| Resume extraction is rules-based with a character span per proposal — not an LLM, not a bare form | §6.1 |
| The daily queue ships its four honest rows and names the four that need M3 | §7 |

**Two things the design corrected against the code rather than the spec**, both
found by reading the schema instead of trusting the plan:

1. **A borough or neighborhood filter cannot be built in M2, and it is an I1
   problem rather than a scheduling one.** `job_locations` has `city`, `state`
   and `country` and no borough column, because a posting saying `"New York,
   NY"` does not say which borough it is in. Deriving one is interpolation. A
   **city** filter is honest today because it matches what the source wrote;
   boroughs arrive with the geocoder at M4.
2. **A stage machine must not block a stage change.** §10.2 requires the user
   can always correct a stage, and `saved → offer` is real — referrals happen.
   The machine classifies each transition (`advance` / `correction` / `reopen`)
   and records it, instead of refusing it. What it *does* enforce is I5: a
   stage change requires an actor of `user`, so a closing listing writes a
   `listing_closed` event and a prompt, and never moves the stage itself.

M2's acceptance criteria are not yet claimed. Nothing below this line describes
M2 work — the tables in this file are still M1's and M0's.

**M1d is complete, M1 with it, and CI was green.**
[PR #4](https://github.com/Tahmudun/Nightshift/pull/4), run
[30783504694](https://github.com/Tahmudun/Nightshift/actions/runs/30783504694)
at `75d9ab7` — **all five jobs green**:

```
python       3m18s   804 passed, zero skipped   (read from the log, not inferred)
e2e          2m33s   20 passed, 1 skipped
migrations   1m17s   up, down, up, and no drift
web            54s
secret scan    11s
```

`headSha` on the run is `75d9ab798a46b1a49602adacffe3575fbe862b87`, checked
against the PR head rather than assumed.

**That check found something worth keeping, and then a regress worth naming.**
The first green run was at `4106072`; two docs commits landed after it, so this
file briefly claimed "CI-green" beside a SHA that was no longer the branch head.
Re-running fixed that — and the commit recording the re-run moved the head past
the SHA *it* recorded. Chasing this converges on nothing: **any commit that
writes down a CI result invalidates its own claim.**

So the invariant is stated rather than chased. `75d9ab7` is **the last commit
containing anything CI executes.** Every commit after it on this branch touches
`docs/` only, which is verifiable in one command:

```
git diff --stat 75d9ab7..HEAD    # must list nothing outside docs/
```

If that shows a file under `apps/`, `services/`, `infra/`, `data/` or the
Makefile, the recorded result does not cover the branch and CI must run again.
That is the check to perform before merging, and it is cheap.

The stronger form of this mistake has bitten this project before: PROGRESS once
carried a CI-green line that predated twenty-one commits of real work. The rule
that prevents it is **name the commit, and say what may follow it.**

**804 in CI matches 804 locally**, so the database-backed tests really ran there
too. The single e2e skip is honest: `an unchanged board is not presented as a
problem` needs a board that has answered `304`, and the seeded stack has polled
nothing.

M0's acceptance row 2 was the reason to insist on this. Three CI runs were
needed at M0 and the two failures found five defects that every local command
had passed over. This time the first attempt was green — which is worth
recording precisely because it is not the usual outcome.

| Task | Commit | What it did |
|---|---|---|
| 1 | `6e516cf` | `PoliteClient.get_json_conditional`; `304` returned as data |
| 2 | `8d5f5c5` | `FetchOutcome` separates *listed* from *fetched* |
| 3 | `4106ed0` | All three adapters revalidate |
| 4 | `6a5757b` | Greenhouse two-phase, plus `fetch_full_board` for first ingestion |
| 5 | `dd9e62a` | **Freshness ages against the listed set** — the central guard |
| 6 | `f356a0e` | `board_poll_state`, `board_tier`, migration `0004` |
| 7 | `6230bd8` | Poll cycle and `next_poll_at` scheduler |
| 8 | `51c7627` | Hot/warm tiers derived from postings |
| 9 | `408c768` | Row lock in `merge_jobs`, in primary-key order |
| 10 | `d3738b6` | `promote` appends; **the 19 boards are in the registry** |
| 11 | this | `GET /boards`, the Operate table, ADR 0011, review |

### Criterion 13, verified against a live provider

Two consecutive polls of `datadog` through `nightshift poll`, 2026-08-03:

```
poll 1   HTTP 200   created=429   ~16 min   (first ingestion, one request)
poll 2   HTTP 304   created=0     0.009 s
```

Job state either side of the `304`, byte-identical:

```
before   460 records | 446 jobs | 676 locations | 460 links | 0 events | 446 embeddings | 0 misses | 0 closed
after    460 records | 446 jobs | 676 locations | 460 links | 0 events | 446 embeddings | 0 misses | 0 closed
```

The ETag stored on poll 1 is the one sent on poll 2, and the same one Greenhouse
served when the design was being measured. The dev database was reset to its
documented 31-job corpus afterwards.

**"Zero writes" is claimed precisely.** A `304` *does* write one row — the
board's own `board_poll_state` bookkeeping, which is the point of polling and
not a claim about any job. What is asserted is zero writes to **job state**: no
insert or update against `source_job_records`, `jobs`, `job_locations`,
`job_source_links`, `job_status_events` or `job_embeddings`; no miss-counter
movement; no closure. `_job_state_snapshot` is that assertion, and it includes
the miss sum and the closed count because a regression that increments every
miss counter changes no row count at all.

### The 19 boards are in the registry

`make registry-approve-write` with the fixed `promote`: **4 boards → 23**, git
reports **171 insertions and 0 deletions**, no existing board lost or modified,
and `after.startswith(before)` is true — the old file is a strict byte prefix of
the new one. The note on the `Stripe` entry reading *"enable once the freshness
and closure state machine lands"* survived; under the old `promote` it would
have been deleted by the act of approving nineteen unrelated boards.

Two `Abridge` candidates stay withheld — one employer, two live Ashby tokens —
and the two `empty` boards stay held. Both are a human's call under ADR 0005.

**Stripe is still `disabled`.** M1d is the milestone its note was waiting for,
and enabling it is a decision for the human rather than a side effect of the
work finishing. A test now asserts it by name.

### What Tasks 1–5 found that the plan did not predict

Nine defects. **Seven were in code that reported success**, which is the same
pattern M1a, M1b and M1c each recorded — now four milestones running.

1. **A `304` currently reads as an authoritative empty board.** `FetchOutcome.
   is_authoritative_empty` was `ok and not jobs`, and a `304` satisfies it. That
   is "every posting on this board is gone" for a provider behaving perfectly.
   Fixed in Task 2, mutation-checked.
2. **httpx counts only 2xx as success and `304` is not retryable**, so a naive
   conditional client falls through to the terminal-failure branch and records
   an outage. The `304` check has to precede both branches.
3. **The same "jobs without listed" footgun appeared three times** — the fixture
   adapters, and two pipeline test stubs. Each instance silently means "the
   board listed nothing", which ages every record. Fixed at the type: a
   `FetchOutcome` carrying jobs with no listing now derives one.
4. **`isinstance` against a runtime-checkable Protocol matches method names
   only.** A single-phase Lever stub that implemented `fetch_postings` for
   convenience got pulled into a phase Lever has no endpoint for. The pipeline
   gates on the `is_two_phase` flag and *then* narrows.
5. **`make seed` would have crashed.** `FixtureGreenhouseAdapter` subclasses the
   real adapter and inherited `is_two_phase = True`, along with a
   `fetch_full_board` that needs the HTTP client the fixture adapter
   deliberately lacks. **The fixture adapters had no tests at all** — the
   offline demo path, untested. 24 now, plus a real two-seed run.
6. **Eleven route tests were *errors*, not failures**, on a fourth
   `_StubAdapter` copy. Errors read as noise; failures read as signal.
7. **Migration autogenerate emitted `nightshift.db.types.UTCDateTime` with no
   import** — a `NameError` at upgrade time. Second migration running that the
   note at the head of `0002` has caught.
8. **`jobs.source_updated_at` already existed and reusing it would have been
   wrong.** After a merge one job carries records from several boards and its
   timestamp reflects whichever wrote last, so the phase-2 diff would refetch
   what had not changed and skip what had. The new column is on
   `source_job_records`, because it answers a per-board question.
9. **The pipeline had never been tested against Greenhouse at all.** Every
   ingestion, closure, merge and route test drove a stub wrapping *Lever*.
   After Task 4, live Greenhouse ingestion produced zero jobs and **nothing
   went red** — a green suite over a provider that had stopped working.

### Two things Tasks 1–5 changed about what is written down

- **ADR 0007's phase 2 is Greenhouse-only, and its "no `updated_at`" problem
  dissolved.** Lever and Ashby return every posting in full from one request,
  so there is no second fetch for a timestamp to gate. Recorded in the design;
  the carried finding below is struck through.
- **Criterion 13's "zero writes" is claimed precisely.** A `304` does write one
  row — the board's own poll bookkeeping, which is the point of polling. What is
  asserted is zero writes to *job state*: no insert or update to
  `source_job_records`, `jobs`, `job_locations`, `job_source_links`,
  `job_status_events` or `job_embeddings`, no miss-counter movement, no closure.
  `_job_state_snapshot` in `tests/test_ingestion.py` is that assertion.

### What was measured before planning, and what it changed

All three providers were probed live on 2026-08-02, because ADR 0007 asked for
exactly this and never got it.

1. **All three honour `If-None-Match` and return `304`.** Greenhouse, Lever and
   Ashby, each sent its own ETag back, each answering `304` with an empty body.
   ADR 0007 verified only Greenhouse and provided a fallback for a provider that
   could not revalidate. No fallback is needed.
2. **"Neither Lever nor Ashby publishes an `updated_at`" is no longer M1d's
   biggest problem — it mostly dissolves.** This file recorded it three times,
   most recently as *"the most consequential"* finding carried into M1d. The
   worry was that ADR 0007's phase-2 diff has no timestamp to compare on two of
   three providers. True, and close to irrelevant: **Lever and Ashby return the
   complete posting, description included, in the single board request** (Lever
   `alloy`, 6,373 characters of `description` on the first posting; Ashby
   `ramp`, 7,332 of `descriptionHtml`). There is no second fetch for a timestamp
   to gate. Two-phase polling is a **Greenhouse-only** mechanism, and Greenhouse
   publishes `updated_at` on its listing.
3. **Greenhouse's per-posting payload is byte-identical to its `content=true`
   list item** — compared key-by-key and value-by-value, zero differences. So
   phase 2 reuses `GreenhouseAdapter.normalize` unchanged and there is no second
   normalization path for the location parser to drift in.
4. **Lever does not compress.** 232,855 bytes with no `Content-Encoding` despite
   being offered gzip. A Lever `200` is the most expensive response this system
   takes, which makes its `304`s the most valuable.

### The defect the design exists to prevent

`apply_freshness` ages a record by `last_seen_at < now`. Phase 2 deliberately
does not refetch an unchanged posting, so that posting is never written, so it
looks absent — **every unchanged posting on every Greenhouse board would take a
miss per poll and close on the third.** Nothing errors; the damage lands three
polls after the change. `FetchOutcome` therefore separates *listed* (phase 1,
complete, drives freshness) from *fetched* (phase 2, partial, drives
persistence). Plan Task 5, with the mutation check that proves it.

Related, and already true in committed code: `FetchOutcome.is_authoritative_empty`
is `ok and not jobs`, which a `304` satisfies — so a `304` currently reads as
"this board authoritatively has no postings". Plan Task 2 fixes it and adds a
validator making the confusion unrepresentable.

### `promote` destroys the registry's comments — found by running it

The human approved promoting M1c's 19 discovered boards. Running
`make registry-approve-write` for the first time in the project's history
exposed a defect M1c structurally could not see, because M1c deliberately never
wrote to the registry and cited byte-identity as evidence of restraint.

`promote`'s docstring says *"Additive, never destructive."* In the data sense it
is — verified semantically: all four existing boards came through identical,
nothing re-enabled, nothing lost. But it rebuilds the file with
`yaml.safe_dump`, preserving only the leading comment block, and it **deleted
ten lines of human-written rationale from between the entries** — including the
note on `Stripe` reading *"enable once the freshness and closure state machine
lands"*, which is a message to M1d, deleted by approving unrelated boards. It
also writes `added: '2026-08-02'` where hand-written entries use bare dates,
leaving one file with two conventions.

**The write was reverted; `data/board-registry.yaml` is unchanged at 4 boards.**
Plan Task 10 fixes `promote` to append rather than re-serialize, then promotes
the 19 for real, with a diff that must be additions only.

Also in Task 10: `test_the_pollable_set_is_exactly_these_three_boards` fired
correctly on all 19 and needs reshaping — enumerating every pollable board does
not survive a registry meant to grow into the thousands, and deleting the guard
would remove the only thing stopping a hand-disabled board going live. Replaced
by an exact set over the four hand-curated boards plus a provenance requirement
on every other pollable one.

### Scope decided by the human this session

- Merge PR #3 — done, `f377303`.
- Approve the 19 discovered boards — deferred into Task 10 behind the `promote`
  fix, so their arrival does not destroy the file they arrive in.
- Of the three carried weaknesses, M1d fixes **the `merge_jobs` row lock only**.
  The discovery mass-failure signal and `cmd_validate`'s per-board file rewrite
  stay recorded as debt and are explicitly out of scope.
- Scheduling shape: `next_poll_at` per board drained by a small cron, over a
  cron per tier. ADR 0011 records it during Task 11.

**The M1c record, kept for the history below:** six tasks, three acceptance
criteria evidenced, review written. Branch head `19236f5`, run
[30764366853](https://github.com/Tahmudun/Nightshift/actions/runs/30764366853):
all five jobs green — `python` **607 passed, zero skipped** (read from the log,
not inferred), `e2e` 2m22s, `migrations`, `web`, `secret scan`.

**The first CI run failed, and it caught something no local command could
have.** Recorded here rather than only in the review, because the lesson is
about how this repo verifies itself: `.gitignore` carried an unanchored
`coverage/` — meant for vitest output — and an unanchored pattern matches a
directory of that name at *any* depth. It silently swallowed
`apps/web/src/app/analyze/coverage/page.tsx`, the whole coverage route, for the
entire milestone. `git add -A` said nothing. `make check`, `make acceptance`
and all 16 seeded browser tests passed, **because every one of them reads the
working tree, where the file existed.** CI built from a clean checkout and got
a 404 — its accessibility snapshot literally reads "This page could not be
found".

A local suite cannot see a file missing from the repository, because it is not
missing locally. `services/api/tests/test_repo_integrity.py` now closes that
gap: it is the one test that asks `git ls-files` rather than the filesystem. It
sweeps the source trees, names the lost file specifically so a future
over-broad ignore rule cannot absorb the regression, and asserts the unanchored
pattern itself never comes back. This is the fourth time in this project that a
defect lived somewhere no local command looks.

After the merge, M1d is the last piece of M1: two-phase
conditional polling (ADR 0007), hot/warm tiers, queue-driven ARQ. No plan file
exists for it yet. **Read the four items below before writing that plan** —
they are M1c's output and they change what M1d has to do.

### What M1d inherited, and what it did about it

1. **No mass-failure signal in a discovery sweep.** A provider that changes its
   payload envelope classifies *every* board `unreachable`, and nothing says so
   louder than a per-candidate note. **Still open** — explicitly out of M1d's
   scope by the human's decision, not by oversight.
2. **`cmd_validate` rewrites the whole candidate file after every board.**
   Correct at 23 candidates; O(n²) at 2,605. **Still open**, same reason.
3. ~~**`merge_jobs` has no row lock**~~ — **fixed in M1d** (`408c768`), and the
   deadlock was reproduced from Postgres before being fixed rather than argued
   about. See the review §3.4.
4. ~~**ADR 0007's phase-2 diff has no timestamp on two of three providers**~~ —
   **resolved by measurement.** Lever and Ashby return every posting in full
   from the board endpoint, so there is no phase 2 on those providers and
   nothing for a timestamp to gate. Greenhouse, the only two-phase provider,
   publishes `updated_at` on its listing. This file had recorded it three times
   as the most consequential item here and it had never been re-checked against
   a live board since M1a.

### What M1 leaves for M2 and beyond

Ranked, from `docs/reviews/milestone-1d-review.md` §4:

1. **`max_jobs` is still 1, and raising it is not free.** `PoliteClient`'s rate
   limiter is per process, so two concurrent jobs against one provider halve the
   spacing it enforces. Queue-driven polling makes raising it a config change
   rather than a rewrite — but the limiter must become per-host and shared
   first. Recorded as a comment on the line somebody would change.
2. **The ARQ *worker* has never consumed a queued job.** The scheduler half is
   now verified against live Redis (2026-08-03): `enqueue_due_boards` synced 22
   boards and queued 22 `poll_board` jobs with correct arguments, and a second
   tick enqueued zero — the double-enqueue guard holding, because `next_poll_at`
   moves forward before the jobs run. What is untested is a worker process
   dequeuing them; the poll cycle they invoke has run live twice through the CLI.
   The queue was drained and the schedules reset afterwards.
3. **Only `datadog` has been polled conditionally against a live provider.**
   Lever and Ashby were measured serving `304` during design; their adapters'
   conditional path has been exercised only against fixtures.
4. **`nyc_presence` is now decorative.** Nothing in the polling path reads it —
   asserted by a test that inspects code with docstrings stripped — so deleting
   it is a cleanup rather than a behaviour change.

### The M1c pipeline, run end to end on 2026-08-02

Real network, real providers, `SOURCE_REQUESTS_PER_SECOND=0.8`:

```
make discover          400 crawl rows -> 23 distinct tokens; 23 new candidates
registry-validate      validated 23: live_named 21, empty 2      (0 failures)
make registry-approve  21 eligible -> 19 offered, 2 withheld (name collision)
                       Dry run. Nothing was written.
```

**`data/board-registry.yaml` is byte-identical to its state at branch start.**
Verified: `git diff cf48719..HEAD -- data/board-registry.yaml` is empty.
Promoting 19 employers is a product decision for the human; the plan's job was
to prove the pipeline works. `make registry-approve-write` is the command that
would do it.

Six of the 21 live boards produce NYC postings: a16z New Media (13 of 25), 9fin
(12 of 40), 3i Members (5 of 8), Abacum (5 of 18), Aaron School (2 of 2),
1Password (1 of 68).

### Plan defects found and fixed rather than copied

Four, all in the plan's own code or tests:

1. **Repo-root arithmetic off by one** in Tasks 2 and 4 (`parents[3]` is
   `services/`, not the root). Would have written
   `services/data/board-candidates.yaml` while approval read an empty file from
   the correct path — a silent split, not a crash.
2. **`test_validation_never_raises` was vacuous.** Its stub route key matched no
   URL, so the stub raised "no route" and the test passed without ever reaching
   the unexpected-exception branch it exists to cover.
3. **Task 4's test violated Task 2's own model rule** (`nyc_posting_count=7`
   against the default `posting_count=3`). The invariant catching the plan that
   specified it is the system working.
4. **`approval_report` promised an ordering it did not apply** — it rendered in
   the order given while its header said "NYC-producing first".

### M1c findings — measured 2026-08-02, all against live sources

These are the reason Task 3 took the shape it did. All four change something
already written down.

1. **`a3c41b8b71eff8c4` is dead.** The design (`board-discovery.md` §6) names it
   as *the* live-but-unnameable board — 200 with ten well-formed postings under
   a machine-generated token — and the plan says deleting its fixture "would
   hollow out the whole design". Its API now returns **404**, and it is absent
   from the July 2026 crawl index in a range the committed slice covers
   (`a-place-for-mom` … `abridge` brackets it), so it is gone rather than
   transiently missing.
2. **What replaced it is stronger evidence, not weaker.** Ashby serves
   **HTTP 200 with `<title>Jobs</title>`** for *any* token that does not exist —
   verified against both the dead token and a made-up one, byte-identical 7,128-
   byte pages. So "a live page that names no employer" is now a recording
   (`ashby_unnameable_page.html`), where the plan had specified a hand-written
   stub. Acceptance criterion 11 is still evidenced, by a real recording of the
   real mechanism.
3. **The token is not the name, about half the time.** Of the 23 Ashby tokens in
   the committed crawl slice, 21 boards are live and **10 have a name that
   differs from the token**: `0g`→"0g Labs", `a-place-for-mom`→"A Place for Mom",
   `a-team`→"A.Team", `10xteam`→"10x Team", `8fleet-inc`→"8Fleet Inc.". This is
   the measured basis for I2's rule here, and it is a stronger number than the
   design's single `0g` anecdote.
4. **Case-variant duplicate tokens are real.** The same slice holds both
   `Abridge` and `abridge` — two Ashby tokens, one employer, both live with 42
   postings. **M1d and the approval step must expect this**: `(ats, token)` is
   the candidate key and these are two distinct keys, so they will both reach
   approval as separate boards and then produce a full set of duplicate jobs
   for dedupe to merge. Cheaper to catch at approval as a `name_collision`.

Also recorded, lower urgency:

- **`scripts/record_crawl_fixture.py` (Task 1) uses `urllib`, which cannot
  verify TLS on this host** — `CERTIFICATE_VERIFY_FAILED`, no certifi bundle
  wired in. `PoliteClient` uses httpx and works. Task 3's recorder
  (`scripts/record_discovery_fixture.py`) goes through `PoliteClient`
  accordingly. The crawl recorder should be moved onto it too.
- **Common Crawl's index 504s** at `limit=6000` and above for
  `jobs.ashbyhq.com/*`; `limit=400` succeeds. Any bulk harvest has to page.
- `0x` and `abe` are live Ashby boards with **zero** postings — real `empty`
  verdicts, now recorded (`ashby_0x_empty_board.json`) so that branch is
  asserted on Ashby's `{"jobs": []}` shape and not only on Lever's `[]`.

**M1b is merged.** `main` is at `cf48719` and contains it; PR #2 was merged by
the human and both the branch and its worktree are gone.

The M1c plan was written last session: six tasks, TDD, real code in every step.
The design it implements already existed in full at
`docs/architecture/board-discovery.md` — this plan does not re-decide anything,
it sequences it.

**Re-verified before planning, per §3's own instruction** (2026-08-02):

- Common Crawl is reachable. `collinfo.json` → HTTP 200, **126 collections**,
  newest `CC-MAIN-2026-30` — the same crawl §3's 2,605-token count was measured
  against, so the design's numbers are not stale.
- The CDX query shape works and returns what the design assumes: newline-
  delimited JSON, one object per captured URL, token as the **first** path
  segment. Most captured URLs are job pages *beneath* a board, which is why
  Task 1's parser takes segment 1 — a last-segment parser would harvest UUIDs.
- **`0g` is in the live index**, which is the case ADR 0005's approval gate
  turns on: the token is not the name, and the board page says "0g Labs".
- `PoliteClient` has only `get_json` (`adapters/http.py:95`), so Task 3 adds
  `get_text` to that class rather than opening a second HTTP path.

**Two things the plan deliberately does not build**, recorded here so the gap
is visible rather than discovered later:

1. **The careers-page probe for Lever.** It needs a list of employer domains to
   start from and nothing in the repo has one. Building a domain-guessing
   heuristic would be exactly the fabrication this milestone exists to prevent.
   Lever therefore stays undiscovered, and the coverage page is required to say
   so by name.
2. **The community-snapshot source**, for the same reason.

### The M1b decisions, kept because M1c and M1d inherit them

M1b is done, but two of its rules govern everything downstream and are easier
to find here than in an ADR:

- **Closure is cautious** — three consecutive misses *and* seven elapsed days,
  both required (ADR 0009). M1d's tiers change the poll rate, and the elapsed
  condition is what stops that changing what closure *means*.
- **Similarity may never merge on its own** (ADR 0010). It is reachable only
  after company, employment type, title and location already agree. M1c's
  validator reuses `normalize_company_name` for the `name_collision` verdict
  and must not quietly widen that.

### Findings from writing the plan — read these before M1d

Live boards were probed while planning, so these are measured, not assumed. All
three change work that is already designed.

1. **Neither Lever nor Ashby publishes an updated-at field.** Lever has
   `createdAt` only; Ashby has `publishedAt` only. **ADR 0007's phase-2 diff is
   specified as "new or changed `updated_at`" and has no timestamp to compare on
   two of the three providers.** M1d must fall back to the description hash
   there. This is the most consequential of the three.
2. **Parser bugs fabricating a city, present in real payloads.**
   `"Vancouver, BC"` parsed to a city called `"BC"` and `"New York, NY (HQ)"` to
   one called `"NY (HQ)"` — I1 failures in the module whose docstring claims to
   enforce I1. The first appears 3× on the recorded Lever board, the second 95×
   on the Ashby board. M1a Tasks 3–4 fix them. **Two more of the same class were
   found later and are recorded below** — a latent `;`-splitting gap found by the
   pre-merge review, and one introduced during M1a itself and caught in task
   review. Four in total; the count is the point, because every one of them
   turned a string the source really wrote into a place that does not exist.
3. **Ten Lever tokens guessed, two live** (`alloy` populated, `plaid` empty,
   the rest 404). Direct support for ADR 0006: Lever boards genuinely have to be
   found by careers-page probing, not guessed and not harvested.

Also recorded, less urgent: Ashby's `address.postalAddress` is structured
(`{addressLocality, addressRegion, addressCountry}`) and is better input for
geocoding than its location string; Ashby's `isRemote` is `true` on 33 postings
sitting at the New York office, so it does **not** mean the job is remote.

### What was decided this session, in one place

The product goal was restated by the human: *if any tech job or internship opens
in NYC, the system knows the day of, from any employer.* That changed M1's
registry from a curated file into a discovery pipeline.

| Decision | Where it lives |
|---|---|
| Registry filled by discovery, not curation; 2,605 tokens measured available | `board-discovery.md` §3 |
| Batch approval, exceptions held individually | ADR 0005 |
| Common Crawl as primary source; Lever needs careers-page probing | ADR 0006 |
| Two-phase conditional polling, hot/warm tiers, queue-driven | ADR 0007 |
| Employer scope: tech roles at *any* employer | `board-discovery.md` §2 |
| Workday/iCIMS/Taleo deferred to the next milestone | `board-discovery.md` §2 |
| LinkedIn and Indeed rejected, with reasons | `board-discovery.md` §9 |
| Scaling to other cities, states, and job types | `board-discovery.md` §10 |
| Discovery runs on command, not on a schedule | ADR 0006, `board-discovery.md` §4 |

Two open questions remain in `docs/QUESTIONS.md` (Q1 Gmail, Q2 deployment cost),
neither blocking. Q3 is answered there in full.

`make acceptance` is the single-command acceptance run. Most recently run at
`bb80680` (M1a's closing commit) on 2026-07-30, against the containers already
running from earlier in the session (not a clean/empty volume — see the
"Verified locally" table below for that caveat):

```
18 verify checks + 6 seeded browser tests, all green, corpus 31 jobs / 3
companies / 3 sources / 62 locations (greenhouse + lever + ashby)
```

The earlier run this line used to cite, `19dc760` (the rename, against an
empty volume), still stands as the last *clean-volume* run — it predates
M1a and is superseded here only for "what does `make acceptance` currently
report," not for "was it ever run from empty."

CI: **M1a is green.** Run #9 at `430347a` — the branch head — passed all five
jobs on the first attempt: https://github.com/Tahmudun/Nightshift/actions/runs/30592177638
(`python` 74s, `e2e` 122s, inside A14's five-minute target). The `python` job's
new `postgres` service worked: `Initialize containers`, `Create extensions`,
`Migrate` and `Unit tests` all succeeded in order, so the database-backed tests
were reachable rather than skipped. See "Next exact action" for the one caveat —
the `350 passed` line itself was not read, only inferred.

The previous green run was `6f88d9a`, which **predated all of M1a.** Twenty-one commits landed between `6f88d9a` and the
M1a-closing commit — the Lever and Ashby adapters, the widened location
parser, the upserts, the ingestion and route test suites, everything in this
plan — and CI has not run against any of them this session. Do not read this
line as M1a being CI-verified; it is not. Check the Actions tab for the
current head before trusting anything past `6f88d9a`.

**Pre-merge review finding, fixed 2026-07-30: the `python` CI job had no
`postgres` service.** Only `migrations` and `e2e` did. `tests/conftest.py`
skips every database-backed test when it cannot reach a database, so on CI
the `python` job was running 323 tests and silently skipping the other 13 —
including the only tests of the ingestion pipeline and the API routes
against a real database — while still reporting green. Fixed by giving the
`python` job the same `postgres` service, env, and migration steps the
`migrations` job already uses (copied verbatim rather than retyped, per the
image-tag history in that job's comment). Verified locally: with the
database unreachable, `323 passed, 13 skipped`; with a freshly-migrated
CI-equivalent Postgres (same image, same recipe, no seed step) reachable,
`336 passed, 0 skipped`. **The workflow change is now verified in
production**: run #9 at `430347a` shows the `python` job initialising the
postgres container, creating extensions, migrating, and running the suite, all
green. The fix did what it was written to do.

---

## Blockers

### B4 — Host disk full; Docker would not start — RESOLVED 2026-08-01

Both halves are now clear, and they were two problems rather than one.

**Disk.** `/System/Volumes/Data` was at **100% — 180 MB free** of 233 GB. Now
**11 GB free**. Freed by the human; nothing in this project was deleted by an
agent.

**Docker.** Freeing the disk was *not* sufficient. With 12 GB free,
`open -a Docker` started `com.docker.backend` (two processes, confirmed by
`pgrep`) but no socket was ever created — `~/.docker/run/` stayed empty and
`docker info` failed with `connect: no such file or directory` after 180 s of
polling. Fixed by the human at the GUI. Engine now reports **29.6.2**.

**What that unblocked, verified the same session at `c52315e`:**

```
make up       postgres + redis healthy (postgres recreated from the compose file)
make migrate  alembic upgrade head, clean
make test-py  350 passed          <- 0 skipped
```

**`350 passed` with zero skips closes the open question this file had been
carrying.** The 13 database-backed tests in `test_ingestion.py` and
`test_routes.py` skip when Postgres is unreachable, so every previous local run
reported `337 passed, 13 skipped` and CI's `350` was established by inference
rather than by a read count. It is now a direct local observation: the same 13
tests run, against a real PostGIS cluster, and pass. No inference left in the
chain.

### B1 — No container runtime — RESOLVED 2026-07-30

Docker Desktop was installed by the human after `brew install --cask
docker-desktop` had rolled itself back on an interactive-sudo step
(`mkdir -p /usr/local/cli-plugins`; `/usr/local` is `root:wheel`).

Everything B1 had been blocking is now verified with recorded output. Kept here
because the acceptance table's history refers to it.

### B3 — Acceptance re-run outstanding — RESOLVED 2026-07-30

Caused by B2. The Docker daemon died mid-session with `no space left on device`,
came back showing an Electron error dialog, and then recovered once disk pressure
was relieved. The re-run it was blocking has now happened.

`make acceptance` ran to completion at commit `14abb68` from a clean shell with
nothing pre-started: **18 verify checks and 6 seeded browser tests, all green.**
That closes the one gap this entry described — the 6 seeded browser tests had
last run one commit earlier, at `bb46732`. Every acceptance row is now verified at
current HEAD.

### B2 — Host disk was full — RESOLVED 2026-07-30

`/System/Volumes/Data` was down to **1.2 GB free** of 233 GB, which is why the
final clean-clone re-run was skipped rather than risk destabilising the host.
Recovered to 14 GB, and **5.8 GB free** as of the end of the CI session, which
pulled a 4 GB Postgres image to replicate CI locally and then deleted it again.
Still tight: this host has no room for a spare clone. The earlier clean-clone run
at `0830589` stands and row 1 says
precisely what it covers; a fresh clean-clone run is no longer blocked, but it is
also no longer load-bearing, since `make acceptance` passes at HEAD.

Docker's own reclaimable space was pruned (build cache and dangling images,
~477 MB). The remaining large image, `hg-engine:latest` (2.06 GB), is not part of
this project and was left alone.

---

## Acceptance criteria — M1

Per invariant I6, "the code exists" is not evidence. M1 has fifteen criteria in
`CLAUDE.md` §6 across four plans. **Nine are earned and verified below. Six
belong to M1c and M1d and are explicitly unclaimed** — listing them as pending
rather than omitting them is the point of this table.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Same fixture input → byte-identical normalized output, twice | **VERIFIED** (M1a) | `test_normalization_is_deterministic` per adapter. Unaffected by M1b; `test_decision_is_deterministic` extends the same guarantee to the closure verdict |
| 2 | Re-ingestion is idempotent: no dupes, no spurious updates | **VERIFIED** | `test_reingestion_is_idempotent` (M1a) plus `test_re_ingesting_a_merged_board_is_idempotent` — the second poll of a merged pair reports `created == 0`, leaves 1 job, and writes no second merge event. `test_an_unchanged_repoll_does_not_re_embed` asserts the model does no work either |
| 3 | Simulated source outage closes zero jobs | **VERIFIED** | `test_a_failed_board_does_not_increment_a_miss`: five consecutive failed polls, well past every ADR 0009 threshold, leave all 9 jobs open **and every miss counter at 0**. The counter is the assertion, not the status — a failed fetch that bumps the counter closes jobs three polls later, and the pre-existing status-only test does not catch that. Confirmed by mutation: making a failed board count as answered fails this test and not the older one |
| 4 | Dedupe fixture suite: true dupes merge, near-dupes and same-title-different-role stay separate | **VERIFIED** | `tests/fixtures/dedupe_pairs.yaml`, all seven §7.5 categories, both verdicts, 55 assertions in `test_dedupe.py`. Zero skips locally — the similarity cases require the real model and it is present. Non-vacuity: removing the title guard collapses the 9 real postings on the recorded Alloy board |
| 5 | Every canonical job traces to at least one raw source record | **VERIFIED** | `test_every_job_still_traces_to_a_raw_record` and `test_a_merge_keeps_every_source_link` — after a merge the surviving job carries **both** links, with distinguishable reasons (`sole_source_record`, `identical_content`). Also asserted at the API boundary: `test_admin_rows_carry_provenance` |
| 6 | Multi-location postings produce multiple `job_locations` rows | **VERIFIED** | `test_multi_location_posting_yields_multiple_rows` (M1a), plus the browser test on real seeded data. **And a merge no longer destroys them** — `test_a_merge_absorbs_locations_the_winner_did_not_have`, which is the review's headline bug |
| 7 | Ingestion failures are visible in the UI, not just logs | **VERIFIED** | `/operate` shows per-source last success, last failure, last run error and a job breakdown by closure state; `/operate/jobs` shows every job's state with a permanent legend. 5 seeded browser tests, including one asserting the status is readable as a word rather than only a colour (§12.4) |
| 8 | Freshness + closure state machine | **VERIFIED** | 22 pure decision tests + 11 pipeline tests against a real database. Both ADR 0009 thresholds asserted, and `test_unverified_never_becomes_closed_however_long_it_lasts` runs the outage out to ten years |
| 9 | Admin job table, source health page | **VERIFIED** | `/operate/jobs` and the grown `/operate`. `job_status_counts` was added to the source route because `job_count` cannot move when a job closes — asserted directly: three empty-but-live polls take a source from 9 open to 9 stale while its total stays 9 |
| 10 | Discovery yields candidates from a committed crawl fixture, deterministically | **VERIFIED** (M1c) | `tokens_from_cdx` over the committed 400-row Ashby crawl slice → 23 distinct tokens. `test_is_deterministic_and_sorted` asserts same input → same sorted output twice; `make discover` run twice leaves the candidate file byte-identical (`test_is_idempotent`). Ran for real: `400 crawl rows -> 23 distinct tokens` |
| 11 | A live-but-unnameable board cannot reach bulk approval | **VERIFIED** (M1c) | Asserted at both layers — `test_a_live_but_unnameable_board_cannot_be_bulk_approved` on the verdict, and `test_an_unnameable_board_is_not_promoted_even_with_write` through the command a human types. **Mutation-checked twice**: making the Ashby name fall back to the token classifies the board `live_named` with `company_name='0g'` (the I2 fabrication) and fails exactly that test; dropping the verdict filter in `approvable` fails 8 tests |
| 12 | The coverage page names what is *not* covered | **VERIFIED** (M1c) | `/analyze/coverage`, four structural blind spots by id (`lever_undiscovered`, `workday_icims_taleo`, `no_public_board`, `aggregator_only`), each with its reason in plain language. 5 seeded browser tests, including one asserting the section holds no `<details>` and its text is visible unexpanded, and one asserting **no percent sign appears anywhere on the page** — there is no denominator, so a coverage percentage would be invented. `count=null` renders "unknown", mutation-checked by typing the field `int = 0`, which fails the route test |
| 13 | A `304 Not Modified` produces zero writes and closes zero jobs | **VERIFIED** (M1d) | Two consecutive live polls of `datadog`: `200`/429 created, then `304`/0 created in 0.009s, with job state byte-identical across all eight measures. Plus `test_a_304_writes_no_job_state` at pipeline and poll-cycle level. Claimed as *zero writes to job state* — the board's own bookkeeping row does move, which is the point of polling. Mutation-checked: ageing `304` boards fails exactly that test |
| 14 | Greenhouse + Lever + Ashby behind one interface | **VERIFIED** (M1a) | Three adapters on the unchanged `JobSourceAdapter` Protocol |
| 15 | `source_job_records` preserving raw payloads | **VERIFIED** (M0/M1a) | Asserted again in M1b: a merge collapses the canonical view and leaves both raw records untouched |

**M1 is complete.** All fifteen criteria are verified with recorded evidence.

Criterion 13 was the last, and it is the one worth reading the evidence for
rather than the claim: a `304` from a real provider, with eight independent
measures of job state identical either side of it.

Two criteria were re-earned rather than merely inherited. Criterion 3 (a source
outage closes zero jobs) now also holds for a board that answers `304`, which is
a new way to learn nothing and would have closed every posting on every
unchanged board. Criterion 2 (re-ingestion is idempotent) now covers a
two-phase poll, where "unchanged" means a posting is deliberately never
refetched — the case that made the freshness fix necessary.

---

## Acceptance criteria — M0

Per invariant I6, "the code exists" is not evidence. Each row is either verified
with recorded output or explicitly marked blocked.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean clone → `make setup && make demo` works, documented, no hidden steps | **VERIFIED** | Genuine `git clone` into a scratch directory at commit `0830589`, no `.env`, no Docker volumes: `make setup` built the venv and installed JS deps in **47.8s**, then `make setup && make acceptance` passed **18/18** checks. Postgres initialised from an empty volume, so the extension init script ran for real. `make acceptance` was re-run to completion at `bb46732` from a wiped volume with nothing pre-started, which is the same chain minus the `git clone`. Commits after that (`f0cb5a6` palette, `14abb68` docs) were verified in place rather than by re-cloning, because the host disk filled (B2). Of everything post-clone, only the Makefile `browsers` target touches the setup path, and it was exercised including its ~100 MB first-run download |
| 2 | CI green | **VERIFIED** | Run **#3** at commit `4c1643f` on `github.com/Tahmudun/Nightshift`: all five jobs green — `python`, `web`, `migrations`, `e2e`, `secrets`. https://github.com/Tahmudun/Nightshift/actions/runs/30528565491 · Longest job 129s, inside A14's five-minute target. Runs 1 and 2 failed and were worth more than a first-try pass: between them they exposed a secret scan that had never executed, a Postgres image that did not exist, a formatter hook that could never resolve, a drift probe comparing our models against the whole server, and a migration path that rolled back every upgrade while exiting 0. Every one of those lived in configuration no local command runs, which is precisely the gap this row exists to close |
| 3 | Migrations apply and roll back | **VERIFIED** | Against live PostGIS 16 + pgvector. Before: 12 tables, 8 enum types. `make migrate-down` → the 8 project tables and **all 8 enum types** dropped, leaving only `alembic_version` and PostGIS's own `geography_columns` / `geometry_columns` / `spatial_ref_sys`. A downgrade that forgets `DROP TYPE` leaves enums behind and this is how you see it. `make migrate` → 12 tables and 8 enums restored; re-seeding produced a byte-identical corpus (10 jobs, 21 locations, same confidence split) |
| 4 | `/health` reports DB + Redis honestly, including when they are down | **VERIFIED** | Real containers stopped, not mocked. Both up → `200 {"status":"ok",…"database":{"ok":true,"detail":"postgis + pgvector present","latency_ms":4.27},"redis":{"ok":true,"detail":"PONG","latency_ms":3.2}}`. Postgres stopped → `503 "degraded"`, `database.ok:false`, `detail:"ConnectionRefusedError: [Errno 61] Connection refused"`, **redis still `ok:true`** — the two are reported independently. Redis stopped too → both false, with distinguishable details. `/health/live` stayed `204` throughout, as a liveness probe should. Both restarted → `200`, and `/stats` still reported all 10 jobs open: an outage closed nothing (I3) |
| 5 | One real Greenhouse board's jobs appear in the browser | **VERIFIED** | Board fetched live 2026-07-29: `boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true` → HTTP 200, 5,309,493 bytes, 426 postings, 134 naming New York. 10 recorded verbatim into a committed fixture. Now rendered in a real Chromium via `apps/web/e2e-seeded/` — **6 tests, all passing** — which reads the expected titles from the API at run time and finds them in the DOM. Also asserts the A2 multi-location rows, the I7 "committed fixture" badge, and that no job ladder claims verified/approximate placement |
| 6 | No secrets committed | **VERIFIED** | No key-shaped strings anywhere in the tree (scanned for `sk-*`, `AKIA*`, `ghp_*`, PEM private keys). `.env` is gitignored (`.gitignore:2`), confirmed via `git check-ignore`. Only credential-shaped value in the repo is `nightshift_dev_only`, the local compose password, confined to the files entitled to contain it. `tests/test_env_example.py` asserts this rather than trusting it. **gitleaks itself had never executed until 2026-07-30** — its config used a negative lookahead, which Go's RE2 cannot compile, so it panicked at config load on every invocation (see the session log). Now: `gitleaks detect` over full history exits 0 on gitleaks **8.24.3**, the version the action pins, and a planted `nightshift_dev_only` in a non-allowlisted file exits 2 — so the rule is proven able to fail |

**M0 is complete.** All six rows are verified with recorded output above.

Row 2 was not a formality, and the record shows it: three CI runs were needed,
and the two failures found five defects that every local command had passed
straight over. CI is the only thing that runs the `migrations` up → down → up
sequence, the drift probe, and the secret scan on every change, and it is where
the `e2e` job guards acceptance row 5 from regressing.

---

## Before M1 starts

Carried from `docs/reviews/milestone-0-review.md` so a new session does not have to
open it. Do these in order; items 1 and 2 are the ones that get expensive later.

**Items 1, 2 and 3 were Tasks 3–5, 8 and 9 of the M1a plan — all three are now
done**, marked below with the commits that closed them. They stayed listed
here as well because this file is what a cold session reads first; the plan
was where the ordered steps lived. Items 4 and 5 were not in M1a and remain
open — 4 waits for geocoding, and 5 is a one-line cleanup with no milestone
attached.

The board-discovery design (`docs/architecture/board-discovery.md` §14) depends on
the first three and does not replace them. Item 1 is a hard prerequisite: NYC-ness
is derived from parsed locations, so a first-provider parser caps the accuracy of
everything downstream. Item 2 stops being theoretical the moment polling becomes
queue-driven (ADR 0007) — concurrency above 1 is the point of that design.

1. **DONE — Write Lever and Ashby location fixtures before touching the parser.**
   Fixtures added at `43dd80a`; the parser was then widened and two real
   fabricated-city bugs fixed at `96a4e16`, `12da0ce`, `d81b03c` (ADR 0008
   accepted at `031a6b9`). `tests/test_locations.py` now has 145 assertions
   (measured 2026-07-30; 98 at M0) across three providers' shapes rather than
   one. (W1)
2. **DONE — Make `get_or_create_source` / `get_or_create_company` upserts.**
   Fixed at `1b37ed9` (`ON CONFLICT DO NOTHING` + read, not check-then-insert).
   No longer a landmine for the moment worker concurrency goes above 1.
3. **DONE — `domain/ingestion.py` and the API routes now have tests.**
   `domain/ingestion.py` covered against a real database at `5573231`
   (vacuous-assertion fixes at `c677822`); the API routes covered in this
   session's commit (`services/api/tests/test_routes.py`, M1a Task 10) —
   `/health`, `/health/live`, `/jobs`, `/jobs/{id}` against the app's own
   dependency-injected session, not a mock.
4. **Re-read `_replace_locations` when geocoding lands.** It deletes and reinserts
   location rows; once coordinates are resolved it must not discard them. Today
   there is nothing to lose, which is the only reason it is safe.
5. **Delete the redundant ordering in `_existing_location_signature`** — the caller
   wraps it in `set()`. (W4)

Not blocking M1, deferred deliberately to M4's accessibility pass: no test asserts
focus-visible styling, and the confidence ladder has never been checked with a real
screen reader.

---

## Verified locally (recorded output)

These ran on this machine and passed:

| Check | Command | Result |
|---|---|---|
| Python format | `ruff format --check services/api` | 45 files already formatted |
| Python lint | `ruff check services/api` | All checks passed |
| Python types | `mypy nightshift` | Success: no issues found in 31 source files (strict) |
| Python tests | `pytest -q` | **856 passed**, zero skipped (local, 2026-08-03; 804 at M1 close, 607 at M1c). Read from the output rather than computed — an earlier draft of this line said 797, a real measurement taken before the `/boards` tests existed |
| Web types | `tsc --noEmit` | clean, `strict` + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` |
| Web lint | `eslint . --max-warnings 0` | clean |
| Web tests | `vitest run` | **63 passed** (8 files; 42 at M1 close) |
| Colour contrast | `vitest run colour-contrast` | 16 assertions on measured WCAG 2.1 ratios |
| Web build | `next build` | compiled, 7 static routes, 102 kB shared JS |
| E2E — degraded (no API) | `make test-e2e` | **5 passed** in 15.0s |
| E2E — seeded corpus | `make test-e2e-seeded` | **27 passed, 1 skipped**, 53.3s — 7 new on search and the detail pages (20 at M1 close). The skip is honest: `an unchanged board is not presented as a problem` needs a board that has answered `304`, and the seeded stack has polled nothing |
| Migration renders | `alembic upgrade head --sql` | full DDL emitted, 8 tables, 8 enums |
| Migration round trip | `make migrate-down && make migrate` | 8 tables + 8 enum types dropped and restored, live cluster |
| Whole-stack acceptance | `make acceptance` | **18 checks + 20 browser tests**, re-run 2026-08-03 at `d3738b6`; seeded corpus 31 jobs / 3 companies / 62 locations, plus **22 board poll schedules, none polled** |
| Migration round trip (M1d) | `make migrate-down && make migrate` | `0003` and `0004` both reversible against the live cluster. `board_tier` confirmed absent from `pg_type` after the downgrade and present after the upgrade — checked directly rather than inferred from a clean exit |
| Model/migration drift | `alembic check` | No new upgrade operations detected |
| Conditional poll, live | `nightshift poll --ats greenhouse --token datadog` ×2 | `200` then **`304` in 0.009s**, job state byte-identical across eight measures |
| Live source reachable | `GET /v1/boards/datadog/jobs` | HTTP 200, 426 postings |

**Total: 951 automated tests passing** (856 Python, 63 web unit, 5 degraded e2e,
27 seeded e2e), plus the 18 assertions in `scripts/verify.py`, which are not
pytest tests but do gate `make acceptance` with an exit code. Was 871 at the
close of M1.

M1d added 197 Python tests. The ones that carry the milestone are small in
number: `test_an_unchanged_posting_takes_no_miss_when_it_is_not_refetched`,
`test_a_304_writes_no_job_state`, and
`test_two_workers_merging_the_same_pair_leave_one_survivor`. Each was
mutation-checked, and the last was run eight times because one green run proves
nothing about a race.

**`tests/test_merge_concurrency.py` deliberately does not use the `db_session`
fixture.** That fixture holds one transaction and rolls it back, which is
correct isolation for every other test in the suite and precisely wrong for a
race: two sessions inside one transaction cannot contend, so the defect under
test could not occur. Those three tests commit, contend for real against
Postgres, and truncate after themselves.

**That gap is now closed, and it was closed by reading rather than by
inferring.** At M1a those tests skipped in CI (no `postgres` service) and the
fix had never been proven. `gh` was installed this session, so CI run #10's
`python` job log was read directly: `467 passed, 2 warnings` with no skip
line. The `Fetch the embedding model` step ran too, which matters for the same
reason — the real-model tests and the similarity half of the dedupe suite skip
themselves when the weights are missing, so without that step CI would have
been green while never testing the component the threshold depends on.

Re-run in the M1a session on 2026-07-30 (Task 10, closing M1a): Python format,
lint, types, tests (via `make check`); web types, lint, unit tests (also
`make check`, unchanged at 35 — no web code changed this plan); and the whole
stack via `make acceptance`, including the seeded e2e suite. Python went from
204 to 336 tests (Lever, Ashby, the widened location parser,
ingestion-against-a-real-database, and the new API route tests all landed in
this plan), and `make acceptance`'s seeded corpus grew from 10 jobs/1 source
to 31 jobs/3 sources because `make seed` now loads all three fixture boards
(M1a Task 10 step 3) — a deliberate, permanent change to the dev database, not
drift. Migration round-trip, colour contrast as a standalone command, web
build, and the live-source-reachable check were not re-run this session; their
last verified values stand at `f0cb5a6` / `14abb68`.

### What those tests actually cover

The counts are only meaningful if the tests can fail. The invariant-bearing ones:

- **I1 (no fabricated locations)** — 159 location-parser assertions (measured
  2026-07-30: `pytest tests/test_locations.py --collect-only -q`, up from 145
  earlier the same day), up from 98 at M0, driven by
  `tests/fixtures/locations.yaml`, whose cases are real unedited
  `location.name` strings from the three recorded boards
  (Greenhouse/Datadog, Lever/Alloy, Ashby/Ramp) plus labelled synthetic edge
  cases. Includes the ten-location posting that mixes one physical office with
  nine remote states. Plus: `test_never_produces_coordinates` asserts
  structurally that `ParsedLocation` has no latitude/longitude field at all;
  `test_country_only_does_not_round_up_to_city_only`;
  `test_unrecognised_country_is_unknown_not_guessed`. On the web side, six Zod
  tests reject a point whose confidence does not justify it, in both directions.
  **Pre-merge review, fixed 2026-07-30: two latent fabricated-city/on-site
  bugs, same class as the Vancouver/BC and NY(HQ) fixes above, neither yet
  seen in a recorded payload.** `parse_location_list` — the entry point
  Lever's `categories.allLocations` and Ashby's `secondaryLocations` actually
  call — never applied the `;`/`|` segment split its own module docstring
  says both providers use; `"New York, NY; Boston, MA"` as one array element
  parsed as a single segment with city `"NY; Boston"`. Separately, a
  trailing parenthetical Remote (`"Austin, TX (Remote)"`) was lifted out
  before Remote detection ran and then never re-checked, resolving
  `city_only`/`on_site` instead of `remote`. Both fixed in
  `nightshift/domain/locations.py`; both pinned with `synthetic: true`
  fixture cases, the first also exercised through `parse_location_list`
  directly (`test_list_entry_point_matches_field_entry_point`) rather than
  only through `parse_location_field`, since that was the entry point the
  bug actually lived in.
- **I3 (no silent closure)** — `TestInvariantI3`, six cases: 404, connect
  timeout, 503, malformed JSON, and a 200 with the wrong shape all produce
  `ok=False`; a genuine empty board produces `ok=True` and
  `is_authoritative_empty=True`. That last one matters — without it the
  invariant could be satisfied by never trusting anything.
- **A10 (fields that are usually null)** — `test_absent_deadline_stays_none`,
  `test_last_modified_is_never_stored_as_a_publication_date`,
  `test_pay_transparency_range_is_extracted` (asserts `salary_period is None`,
  because Greenhouse states no period and inferring one from magnitude would be
  a guess presented as data).
- **A2 (many locations per job)** —
  `test_multi_location_posting_yields_one_row_per_place`, on real data.
- **Determinism** — `test_normalization_is_deterministic` and
  `test_parse_is_deterministic`, both asserted from M0 so M1's "byte-identical
  output twice" criterion cannot quietly become false first.
- **Company identity** — 27 assertions (measured 2026-07-30) organised around
  the two ways `normalize_company_name` can fail: splitting one employer in
  two, or merging two real ones. Includes the false merges a fuzzy matcher
  would make (Meta/Metabase, Ramp/Rampart) and the suffixes that must *not*
  be stripped (Palantir vs Palantir Technologies). **This suite found a real
  bug** — see the session log.
- **Board registry** — 35 assertions (measured 2026-07-30, up from 29 at M0)
  on the file that decides which boards get polled, where a typo means
  silently never seeing a company's jobs. Includes path-traversal rejection
  on the token, since it is interpolated into a URL, and the closed-set test
  pinning the pollable set to exactly `{greenhouse:datadog, lever:alloy,
  ashby:ramp}`.

---

## What exists

### `services/api` — FastAPI + ARQ (one deployable, A11)

```
nightshift/
  config.py              pydantic-settings; refuses to start on a bad value
  logging.py             structlog, console locally / JSON in production
  cli.py                 seed | ingest | enqueue | stats
  adapters/
    base.py              JobSourceAdapter Protocol, FetchOutcome, RawJob
    http.py              PoliteClient — the ONLY module importing httpx
    greenhouse.py        real adapter, field shapes read off a live response
    lever.py             real adapter; no updated_at, no company name (M1a)
    ashby.py             real adapter; no updated_at, no company name (M1a)
  domain/
    locations.py         location parsing; I1 lives here
    companies.py         conservative company-name normalization
    registry.py          board-registry.yaml loading + validation
    ingestion.py         fetch → preserve → normalize → persist
  db/
    base.py              declarative base, 8 PG enums as StrEnum
    types.py             UTCDateTime — rejects naive datetimes at the boundary
    models.py            8 tables
    session.py           one async engine per process
  api/
    main.py              app factory
    routes/health.py     /health, /health/live
    routes/jobs.py       GET /jobs, GET /jobs/{id}
    routes/sources.py    /sources, /ingestion-runs, /stats, /registry
  workers/
    main.py              ARQ WorkerSettings, hourly cron at :17
    tasks.py             ingest_greenhouse — one real task, not a no-op
migrations/              alembic, async env, one reversible migration
tests/                   336 tests (pytest -q, measured 2026-07-30); fixtures/ committed
```

**Schema (8 tables):** `users`, `companies`, `sources`, `source_job_records`,
`jobs`, `job_locations`, `job_source_links`, `ingestion_runs`.

Deliberately narrower than PRODUCT-SPEC §6 — applications, match results,
snapshots, and user skills arrive at the milestone that reads them. What is here
is shaped for what comes later: `users` exists so every user-owned table can
carry a real FK from its first migration (A3); raw payloads are preserved and
canonical jobs are reachable only through `job_source_links`, so M1's dedupe adds
a merge step rather than restructuring anything.

### `apps/web` — Next.js App Router

```
src/
  app/layout.tsx         shell: wordmark, ModeNav, HealthTelemetry, skip link
  app/explore/           jobs list + confidence legend + corpus readout
  app/operate/           source health table
  app/analyze/           corpus readout + why nothing is geocoded
  components/
    ConfidenceLadder     the signature element (below)
    CorpusReadout        counts incl. "placeable on a map: 0"
    HealthTelemetry      polls /health every 10s; can say "down"
    JobRow / JobList     one confidence ladder per location
    SourceHealthTable    labels fixture sources in gold
  lib/
    schemas.ts           Zod at every network boundary; I1 re-checked here
    api.ts               single API client
    confidence.ts        the five-value scale + user-facing meanings
  app/colour-contrast.test.ts   WCAG ratios computed from the real tokens
e2e/                     Playwright with NO API — the degraded path
e2e-seeded/              Playwright against a seeded stack — acceptance row 5
playwright.config.ts     starts the web server only
playwright.seeded.config.ts    starts web + API, gated on /health
```

Two Playwright configs on purpose. `e2e/` proves the app says "api unreachable"
rather than rendering an empty list, so it must run with the API *absent* —
starting one would make it pass for the wrong reason. `e2e-seeded/` proves real
rows reach a browser. Neither substitutes for the other, and CI runs both in that
order.

**The confidence ladder** is the product's signature UI element: five ticks of
increasing height, lit to the precision actually achieved, with a text label and
an accessible name. It appears on every location of every job. In M0 no ladder
anywhere in the app rises above three ticks — which is the truth, rendered.
§4.3 requires the interface to document its own visual language, so the legend
ships as a permanent panel rather than a tooltip (§12.4: no essential
information available only through hover).

### Infrastructure

- `infra/docker-compose.yml` — postgres + redis, real healthchecks. The Postgres
  healthcheck asserts PostGIS **and** pgvector exist, so "healthy" means
  "usable" rather than "accepting connections during initdb".
- `infra/postgres/Dockerfile` — see ADR 0001.
- `Makefile` — 20 targets; every command runs from the repo root.
- `scripts/dev.py` — runs api + worker + web with correct group shutdown.
- `scripts/doctor.py` — names a missing prerequisite instead of failing deep in a
  pip build. It reports B1 correctly.
- `scripts/record_fixture.py` — regenerates a committed fixture from a live board.

### Documentation

- 8 ADRs: 0001 Postgres image, 0002 I1 in the schema, 0003 `FetchOutcome` and I3,
  0004 fixture seeding labelled in the data, 0005 batch approval of discovered
  boards, 0006 Common Crawl as a discovery source, 0007 two-phase conditional
  polling, 0008 decided bare place names (M1a).
- `docs/architecture/costs.md` — required from M0 by A9. **$0/month, 0 API keys.**
- `docs/QUESTIONS.md` — **2** open questions (Q1 Gmail, Q2 deployment cost),
  none blocking. Q3 (registry scope) was answered 2026-07-30 — see the M1
  design session log entry below.

---

## Not real yet

Everything half-built or standing in for something real. Nothing in this list is
presented to a user as working.

| Thing | What it actually is | Real at |
|---|---|---|
| `data/skills.yaml` coverage against real postings | **Largely addressed at M3a.1, and the remainder is now a decision rather than a gap.** The vocabulary went from **73 entries to 107** — 34 added, counted from the file
rather than from memory, because the commit message for this work says 36 and is
wrong: ML frameworks (JAX, LangChain, HuggingFace, DSPy), accelerators (CUDA, ROCm, Triton, SYCL), HDLs (Verilog, VHDL, SystemVerilog), Windows/network/security administration (Active Directory, SIEM, EDR, SSO, MFA, VPN, DNS, TCP/IP, PowerShell, Windows, macOS, firewalls), and business systems (Salesforce, Google Sheets, Microsoft 365). Recall moved 0.459 → 0.861. **What is deliberately still absent**: structural engineering codes (ACI 318, ASCE 7, IBC, IFC, AISC, FM Global), treasury systems (Kyriba, GTreasury, Trovata, TMS), accounting standards (US GAAP, IFRS), and words too ordinary to match safely (`Word`, `MS Office`). Those are real requirements of real postings in the corpus and are not software skills — adding them would raise recall by teaching the product a domain it does not serve | Closed as vocabulary work. The residual absences are a scope decision, revisited only if the product's scope changes |
| Eligibility answer key (`tests/fixtures/eligibility/labels.yaml`) | **Filled in, and model-labeled rather than human-verified.** All 60 postings × 9 fields were labeled 2026-08-04 by a browser-side Claude reading the recorded excerpts, with the web explicitly off — the grader compares against text the extractor also sees, so a label sourced from outside that text marks a correct extractor wrong. Audited on install: 0 of 199 named technologies absent from the posting text, and no sponsorship, graduation-window, internship or years claim unsupported by the text. Two `+equivalent` calls read an escape hatch worded without the word "equivalent" (`akunacapital/8035515`, `openai/8fb1615c…`) and are the entries most likely to be wrong. Not spot-checked by a human | Human spot-check of ~10 entries, unscheduled |
| `FixtureGreenhouseAdapter` (`cli.py`) | Subclasses the real adapter, overrides only `fetch_board` to read a committed JSON file. Constructed with no HTTP client, so it cannot make a request. Attributed to source `greenhouse_fixture` with `source_type='fixture'`, badged **"committed fixture"** in the Operate UI. ADR 0004 | Permanent — this is the offline demo path, not a stopgap |
| Geocoding | **Does not exist.** No coordinate has ever been written. Every location is `city_only`, `remote`, or `unknown`; `mappable_locations` reads 0 and the UI says "nothing geocoded yet" | M1 (NYC GeoSearch, A4) |
| Dedupe similarity threshold | **Real, thinly calibrated, and now with one real-world data point.** `SIMILARITY_THRESHOLD = 0.85` was derived from three labelled pairs. M1d's live Datadog poll merged two genuine postings on `similar_description` at **0.864** — the first evidence from outside the labelled set, and it landed close to the line. One observation is not a calibration and nothing was changed on the strength of it, but it is the first sign the number is doing real work at a real boundary. Re-derive as the fixture set grows | Unscheduled; revisit when more live boards are polled |
| ~~Merge concurrency~~ | **Fixed in M1d** (`408c768`). The defect was reproduced before being fixed — Postgres reported a real `DeadlockDetectedError` between two workers merging the same pair in opposite directions. Both rows are now locked in primary-key order, as two statements rather than one `IN` clause, because a single statement's lock acquisition follows the query plan rather than the sort. Mutation-checked: the caller's order deadlocks on 3 of 3 runs; the fix passed 8 consecutive | Done |
| Later-arising duplicates | Dedupe runs only on creation, deliberately: re-running the matcher every poll is how a settled merge starts oscillating. The consequence is that two jobs which become duplicates *later* — a title corrected on one board to match the other — never merge, and nothing reconciles them | No milestone. Revisit if visible duplicates are reported |
| `job_locations.geom` | Column and GiST index exist; always NULL | M1 |
| `normalize_title` | Whitespace and dash folding only. Deliberately does **not** attempt role-family normalization — asserted by `test_does_not_attempt_role_family_normalisation` | M3 |
| `jobs.role_family`, `jobs.seniority` | Columns exist, always NULL. NULL means "not classified", never a guessed default | M3 |
| Stripe board registry entry | Verified live (HTTP 200) but `status: disabled`. Polling more boards before the closure machine exists would mean ingesting jobs the system cannot honestly age out | M1 |
| `/registry` route | Still read-only. The *crawl-index* half of the resolution pipeline now exists (M1c) and fills `data/board-candidates.yaml`; the careers-page probe does not | M1c partly, careers probe unscheduled |
| Lever board discovery | **Does not exist and cannot, from the crawl archive.** `jobs.lever.co/robots.txt` disallows CCBot, so no Lever page is in Common Crawl (ADR 0006). `sources/careers_probe.py` is designed but not built: it needs a list of employer domains and nothing in the repo has one, and guessing domains would be the fabrication this milestone exists to prevent. Named as the first blind spot on `/analyze/coverage`, with the structural reason, and a browser test asserts it reaches the screen. **Lever boards enter the registry only by hand** | No milestone. Needs a domain source first |
| Community-snapshot discovery source | Designed in `board-discovery.md` §4, not built, same reason as the careers probe | No milestone |
| Discovery beyond Ashby | `PROVIDER_PATTERNS` includes both Greenhouse board domains and the code paths work, but **no Greenhouse crawl fixture is recorded**, so `make discover --provider greenhouse` has never run against real data. Greenhouse *validation* is tested, on the recorded `6sense` board | M1d |
| The 2,605-token figure | Not re-measured by M1c and never claimed by it. The committed slice is **400 rows → 23 tokens**, the alphabetical head of one provider (`0g`…`abridge`). Common Crawl's index 504s at `limit=6000`, so a full harvest needs paging that does not exist | M1d |
| ~~Discovered boards in the registry~~ | **19 promoted in M1d** (`d3738b6`), on the human's decision. 4 boards → 23, 171 insertions and 0 deletions, nothing lost or modified. Two `Abridge` candidates and two `empty` boards remain withheld for individual review under ADR 0005 | Done |
| Ashby's `address.postalAddress` | Structured (`addressLocality`/`addressRegion`/`addressCountry`), recorded verbatim in every raw payload, and better geocoding input than the free-text `location`/`secondaryLocations` strings — but deliberately unread by `AshbyAdapter.normalize`. Feeding a second location source into `job_locations` before geocoding has its own fixtures would mean two code paths writing the same table | M1, at the geocoding stage |
| 3D city, map, MapLibre, Three.js | Not started, not scaffolded, no dependency added. Explore is a list and says so | M4 |
| Auth | None. Single seeded `dev_user`, id in config (A3). Every user-owned table will still carry a real `user_id` FK from its first migration | M5 |
| Live polling of Lever/Ashby | **Fixed in M1d.** `ADAPTERS` in `domain/polling.py` covers all three providers, `sync_board_poll_state` gives every pollable registry board a schedule, and `nightshift poll --ats lever --token alloy` works. `active` in the registry now means what an operator would assume. **Caveat:** only `greenhouse:datadog` has actually been polled live end to end. Lever and Ashby were measured serving `304` during design, but their conditional path has been exercised only against fixtures | Polled path proven on one provider; the other two are wired and fixture-tested |

---

## Session log

### 2026-08-03 — M1d: conditional polling, and the close of M1

Eleven tasks, eleven commits. A `304` now costs one request and writes nothing,
which closes the last M1 criterion.

**Fourteen defects. Ten were in code that reported success** — the same pattern
M1a, M1b and M1c each recorded, four milestones running. This time the sharpest
was self-inflicted and worth stating plainly.

**The pipeline had never been tested against Greenhouse.** After Task 4 made it
two-phase, live Greenhouse ingestion produced **zero jobs** and the suite stayed
green. Every ingestion, closure, merge and route test drove a stub wrapping
*Lever*, handed a `FetchOutcome` the test built itself — so the pipeline had
never seen a Greenhouse-shaped response, and outcomes constructed by tests
cannot disagree with what adapters actually return. I predicted the suite would
fail; it did not; the green run was the finding.

**ADR 0007's own optimisation creates a silent mass-closure bug.**
`apply_freshness` ages a record whose `last_seen_at` predates the run. Phase 2
deliberately never refetches an unchanged posting. Wire those together literally
and every unchanged posting on every Greenhouse board takes a miss per poll and
closes on the third — no error, damage landing three polls after the cause.
`FetchOutcome` now separates *listed* from *fetched*, and both halves of the
guard are mutation-checked.

**The same footgun appeared three times, so the type changed rather than the
call sites.** A `FetchOutcome` with postings but no `listed` set reads as a
board that listed nothing. It now derives one — a posting we hold the content
of was self-evidently on the board.

**`make seed` would have crashed.** `FixtureGreenhouseAdapter` inherited
`is_two_phase = True` from the real adapter, along with a `fetch_full_board`
that needs an HTTP client the fixture adapter deliberately lacks. The fixture
adapters — the thing that makes `make demo` work offline — **had no tests at
all**. There are now 24, and two consecutive `make seed` runs were verified to
leave 31 jobs open with zero misses.

**A real deadlock, reproduced before fixing.** The M1b review named the missing
`merge_jobs` row lock as the one thing M1d must not inherit. Postgres reported
it directly. Locking both rows in primary-key order fixes it, as two statements
rather than one `IN` clause, because a single statement's lock acquisition
follows the query plan rather than the sort. The mutation deadlocks on 3 of 3
runs; the fix passed 8 consecutive.

**`promote` was destructive in everything a human had written.** Found by
running `--write` for the first time in the project's history — it deleted ten
lines of rationale between entries, including the `Stripe` note addressed to
this very milestone. Now literally appended, asserted as
`after.startswith(before)`.

**Structural typing did the wrong thing quietly.** `isinstance` against a
runtime-checkable Protocol matches method *names*, so a single-phase Lever stub
that implemented them for convenience got pulled into a phase Lever has no
endpoint for. The pipeline gates on the flag and *then* narrows.

**Existing guards that earned their keep:** `test_repo_integrity` (added in M1c
after `.gitignore` swallowed a route) caught two new modules before they were
staged; `conftest`'s no-CASCADE truncate refused `board_poll_state` until it was
listed; the `job_merge_events` append-only trigger refused a test's cleanup
`DELETE`; the `jobs` check constraint refused a `closed` job with no
`closed_at`; and the registry closed-set test refused all 19 new boards until
deliberately reshaped.

**Two of my own tests were badly written and got stronger.** They grepped module
source for `nyc_presence` and borough names, and failed on the docstrings
explaining why neither belongs in the code. A test that greps prose punishes
documenting the rule. They now parse the module and strip docstrings.

**Two things written down turned out to be wrong**, corrected in place: phase 2
is Greenhouse-only, and the "no `updated_at` on Lever and Ashby" problem this
file recorded three times as M1d's most consequential inheritance dissolved once
someone measured the payloads.

### 2026-08-02 — M1c: board discovery

Six tasks, seven commits. The registry stops being a hand-written list and
becomes the reviewed output of a pipeline — and the pipeline's own output is
what found most of what was wrong.

**The design's central example board is dead.** `a3c41b8b71eff8c4` is the
live-but-unnameable board the entire approval gate is built around; the plan
says deleting its fixture "would hollow out the whole design". Probing it
before recording returned **404**, and it is absent from the July 2026 crawl
index in a range the committed slice covers (`a-place-for-mom` … `abridge`
brackets it), so it is gone rather than transiently missing.

What replaced it is stronger, and finding it was the useful part: **Ashby
serves HTTP 200 with `<title>Jobs</title>` for any token that does not
exist** — verified against both the dead token and a made-up one, byte-identical
7,128-byte pages. So "a live page that names no employer" is now a committed
recording rather than the hand-written stub the plan specified. The plan's own
test synthesised that HTML; a recording is strictly better evidence.

**Four defects, three of them found by running something rather than reading
it.** That is the same pattern M1a and M1b recorded — three milestones running.

1. **Two candidates naming one employer both reached the approval report.**
   `Abridge` and `abridge`: two live Ashby tokens, one employer, 42 postings
   each. Found by `make registry-approve` on real validated data. The
   `name_collision` verdict compares against names already in the *registry*,
   so it is structurally unable to see a collision inside a single batch.
   Approving would have written two rows for one company, polled the same board
   twice, and handed dedupe 42 duplicate jobs. Fixed: both held, neither wins,
   and the report names what it withheld — an operator reading a report these
   were merely absent from would conclude the boards were never discovered.
2. **Harvested tokens were recorded as `unreachable`.** Found by reading the
   first real `make discover` output. That claims we tried and failed, about
   boards nobody had contacted, and the coverage page would have reported 23
   failures that never happened. Fixed by adding a sixth verdict,
   `unvalidated`, with `last_validated = date.min` so nothing downstream reads
   a never-contacted board as freshly checked.
3. **`test_validation_never_raises` was vacuous** — the one caught by reading.
   Its stub route key matched no URL, so the stub raised "no route" and the
   test passed without ever entering the branch it exists to cover.
4. **The plan's repo-root arithmetic was off by one** in two tasks.

**The token is not the name, about half the time.** Measured across the 23
Ashby tokens in the committed slice: 21 boards live, and **10 have a name that
differs from the token** — `0g`→"0g Labs", `a-place-for-mom`→"A Place for Mom",
`a-team`→"A.Team", `8fleet-inc`→"8Fleet Inc.". Deriving an employer name from a
token would be wrong roughly half the time, always in the direction of
inventing an employer. That is a far stronger basis for I2's rule here than the
design's single `0g` anecdote.

**Two gates, both mutation-checked rather than merely tested.** Making the
Ashby name fall back to the token classifies the junk board `live_named` with
`company_name='0g'` — the exact I2 fabrication — and exactly one test fails.
Dropping the verdict filter in `approvable` fails eight, including one that
drives the command a human actually types. Typing the coverage `count` field as
`int = 0` instead of `int | None` fails the route test, which is what keeps
"we cannot know" from silently becoming "there is no gap".

**The coverage page reports no percentage anywhere, and says why.** There is no
denominator — nobody knows how many tech roles open in New York — so a figure
like "we cover 73%" would be arithmetic on a number nobody has. Asserted three
ways: in the summary, in the text report, and in a browser test that fails if
any percent sign reaches the page.

**Deliberately not built: the careers-page probe, so Lever stays
undiscoverable.** It needs a list of employer domains and nothing in the repo
has one; guessing them would be the fabrication this milestone exists to
prevent. Carried honestly instead — `lever_undiscovered` is the first blind
spot on `/analyze/coverage`, it states the structural reason (Lever's own
robots.txt disallows CCBot), and a browser test asserts it reaches the screen.

**Also recorded:** `scripts/record_crawl_fixture.py` (Task 1) cannot run on
this host — it uses `urllib`, which has no certifi bundle here and fails TLS
verification. Task 3's recorder goes through `PoliteClient` and works. Common
Crawl's index 504s at `limit=6000` for `jobs.ashbyhq.com/*` while `limit=400`
succeeds, so any bulk harvest needs paging that does not exist yet.

### 2026-08-01/02 — M1b: the canonical spine

Ten tasks, ten separate commits, each mutation-checked. The engine — closure,
dedupe, embeddings — and the operational surface that makes both observable.

**The session opened by finding the repo ahead of its own notes.** PROGRESS
said M1a was "written, not started". It was finished, CI-green and already
merged as PR #1; the file was simply stale. Synced, removed the leftover
worktree, and — with Docker back — ran the database tests locally for the first
time ever: `350 passed`, zero skipped. Until that moment every local
`make check` on this host had reported `337 passed, 13 skipped` and nobody had
seen the other 13 run anywhere except by inference.

**Two decisions were the human's, and one of them was against my
recommendation.** ADR 0009 fixes closure at three misses *and* seven days, the
cautious end of three options offered. ADR 0010 admits embedding similarity
into dedupe; I recommended deterministic rules only. Both ADRs record who
decided what. The constraint that makes the second safe is that similarity is
unreachable until company, employment type, title and location already agree —
so it breaks ties and never matches on its own, asserted by
`TestSimilarityIsConfined` with a control case so its negative tests cannot
pass by the layer merely being broken.

**Three bugs, none of them found by reading code.**

1. **A merge silently dropped locations only the losing posting named.** The
   worst of the three. Board A says "Washington, DC"; board B says
   "Washington, DC" and "Austin, TX"; they share a location so they merge, and
   Austin cascaded away with the deleted row. A user filtering for Austin would
   never have seen the role, at the exact moment two sources agreed it exists
   there. Found by writing a throwaway probe with a deliberately asymmetric
   pair — every existing merge test used pairs whose location sets were
   identical, so the suite was green and blind. *A fixture that varies only in
   the dimension under test will not catch a bug in a dimension held constant.*
2. **Two descriptionless postings merged on their emptiness.**
   `content_hash(None)` returns the sha256 of the empty string — a genuine
   64-character digest, equal on both sides — so layer 2 found them identical
   and merged them on "identical content". The same failure shape as two null
   URLs matching each other, which `normalize_url` had already guarded. One
   guard existed and its twin did not.
3. **Alembic autogenerate produced three defects at once**, all of which would
   have failed at runtime rather than at review: it referenced `pgvector` and
   `nightshift.db.types` without importing either, and emitted a `CREATE TYPE`
   for `job_status`, which already exists and is in use by `jobs`. The M0
   migration leaves a note at its head about exactly this; that note is now
   load-bearing rather than historical.

**The similarity threshold was derived, not chosen.**
`scripts/derive_dedupe_threshold.py` scores the labelled set under the real
model: merges at 0.9693 and 0.9370, the distinct pair at 0.7640. Any value in
(0.7640, 0.9370] separates the set; 0.85 is the midpoint. The script refuses to
suggest a number when no separating window exists, which is the branch that
matters. **Three labelled pairs carry descriptions, so three points define this
number** — recorded in "Not real yet" as the thing most likely to be wrong in
a way no current test can see.

**The mutation that mattered most.** Making a failed board count as answered
fails two closure tests — and *not* the pre-existing
`test_a_failed_board_closes_nothing`, because one failed poll never reaches a
threshold. The damage only becomes visible three polls later. That is why the
new assertion is on the miss counter rather than on the status, and it is the
clearest example in this project so far of an invariant test that was true and
insufficient.

**`gh` was installed, and it had been failing for a reason unrelated to `gh`.**
The dead tap `homebrew/cask-versions` — a repository Homebrew itself deleted —
made `brew update` error, and since every `brew install` auto-updates first,
*any* package would have failed the same way. Untapped. That likely explains
part of the earlier Docker Desktop trouble too. With `gh` working, CI run #10's
log was read directly rather than inferred, closing the last inference in the
evidence chain.

**Deliberately not done:** a row lock in `merge_jobs`. Two workers merging
concurrently is unreachable at `max_jobs=1` and becomes routine the day ADR
0007's queue-driven polling lands. It is named in the M1b review as the single
thing M1d must not inherit unnoticed, and it should be designed against M1d's
real concurrency model rather than guessed at now.


### 2026-07-31 — Review session: state verified; host disk full again (B4)

A review pass requested by the human, run deliberately lean on a metered
budget. What was checked, and what it found:

- **Repo state matches this file.** Clean tree, 24 commits on
  `m1a-provider-breadth`, head `2c2594c` (docs-only commits past the
  CI-verified `430347a`), branch up to date with origin, PR still open.
- **`make check` green at head**: 337 Python + 35 web tests passed. The 13
  database-backed tests skipped — investigated rather than waved through, and
  the cause is environmental, not code: Docker cannot start because the disk
  is at 100% (180 MB free). Recorded as blocker **B4**; Docker Desktop was
  launched to run them, failed with `Docker Desktop is unable to start`, and
  was quit again. Nothing was deleted; the space measurements are in B4.
- **No code was changed.** The two known open cleanups ("Before M1 starts"
  items 4–5) are deliberately deferred with reasons, and the branch head is
  CI-verified green — pushing cosmetic changes would invalidate that evidence
  for no functional gain. This was a judgement call, on the record.
- Scope caveat, per I6: this session verified the branch's *claims* (state,
  checks, CI record) and relied on M1a's existing review layers — per-task
  review, mutation testing, the pre-merge fix wave, CI run #9 — rather than
  re-reading all 24 commits line by line. A full independent re-review of an
  already-multiply-reviewed green branch was judged not worth its cost.

### 2026-07-31 — M1a CI-green on the first run

PR opened; run #9 at `430347a` passed all five jobs — `python` 74s,
`e2e` 122s, `migrations` 55s, `web` 52s, `secret scan` 5s.
https://github.com/Tahmudun/Nightshift/actions/runs/30592177638

Notable against M0, which took three runs and whose two failures found five
defects — every one in a file no local command executes. The difference is
probably that the pre-merge fix wave verified the new `postgres` service
against a container matching CI's exact pinned image rather than trusting the
YAML, which is the same lesson M0's `manifest unknown` failure taught.

**The CI fix is confirmed working.** The `python` job ran
`Initialize containers` → `Create extensions` → `Migrate` → `Unit tests`, in
order, all green. Before this branch that job had no database at all and would
have skipped 13 tests while reporting success.

One honest gap: nobody read the `350 passed` line. Downloading Actions logs
needs admin rights on the repository, which the agent does not have, so the
claim "the database tests ran" rests on inference — the skip fires only when
the database is unreachable, and two earlier steps connected to it. Sound, but
it is inference. Expanding the "Unit tests" step in that run would settle it
outright, and doing so costs one click.

### 2026-07-30 — M1a pushed, PR pending

Branch `m1a-provider-breadth` pushed to origin: 23 commits from merge base
`3e3dee1`. **Not merged, and CI has never seen it.**

> Superseded 2026-07-31: the PR was opened and CI run #9 passed at `430347a`.
> Left as written — this entry records what was true when the branch was
> pushed, and editing a dated record to match later events makes it tidier and
> untrue.

The PR was not opened by the agent — `gh` is not installed on this machine, so
there is no way to create one from the CLI. The push output printed the
creation URL and it is recorded in "Next exact action" above. `brew install gh`
and `gh auth login` would let a future session open PRs directly; that is the
only thing standing between this repo and a fully automated finish.

Worth being precise about what "done" means here, because the file says
COMPLETE in several places: **every M1a acceptance claim in this file was
verified on a laptop.** `make check` (350 Python, 35 web), `make acceptance`
(18 checks + 6 browser tests), mypy strict, ruff, and a live-Postgres run of
the 13 database tests. None of it has been verified by CI, and the branch
changes CI configuration — including adding the `postgres` service without
which those 13 tests silently skip. Per I6 that gap is named rather than
glossed: laptop-green is evidence, but it is not the evidence M0 learned to
demand, and M0's own record is that every defect CI found lived in a file no
local command executes.

One process note for whoever runs the next plan. A subagent doing mutation
testing was killed mid-run by a usage limit, between "confirmed the test
fails" and "restore the code" — leaving the deliberate bug (`company_name =
board.token.title()`, the exact I2 fabrication) live in the working tree and
uncommitted. It was caught by checking `git status` before trusting the
agent's report. Mutation testing is worth doing and found three tests that
could not fail, but it writes real bugs to disk on purpose, so an interrupted
run is a hazard: check the tree, not the summary.

### 2026-07-30 — M1a final pre-merge review: fix wave

A final pre-merge review of the M1a branch flagged five findings, all fixed
in this session, no second wave planned.

1. **CI silently skipped every database test.** The `python` CI job had no
   `postgres` service — only `migrations` and `e2e` did — so `tests/conftest.py`'s
   database-unreachable skip fired on every CI run, and the 13 tests covering
   the ingestion pipeline and the API routes against a real database never
   executed there, while the job still reported green. Fixed by adding the
   `migrations` job's `postgres` service, env, and migration steps to the
   `python` job verbatim (same image, same pinned tag — see that job's own
   comment for why retyping it from memory has cost CI runs before). Verified
   locally the way the reviewer did: `POSTGRES_PORT=5999 pytest -q` →
   `323 passed, 13 skipped`; a freshly-migrated CI-equivalent Postgres
   (`imresamu/postgis:16-3.4-bundle0`, same recipe, no seed step) reachable →
   `336 passed, 0 skipped`. **The workflow file change itself is unverified —
   CI has never run against this branch.** *(Superseded 2026-07-31: run #9
   confirmed it works in production. Left as written, per the note above.)*
2. **Latent fabricated-city bug in `parse_location_list`.** The function
   Lever's `categories.allLocations` and Ashby's `secondaryLocations` arrays
   actually call never applied the `;`/`|` segment split that
   `parse_location_field` does and that the module's own docstring says both
   providers need. `["New York, NY; Boston, MA"]` (one array element) parsed
   as a single segment with city `"NY; Boston"` — a fabricated place at
   `city_only` confidence, same failure class as the Vancouver/BC and
   NY(HQ) bugs M1a already fixed twice. Not yet seen in a recorded fixture,
   which is exactly how the first two got in. Fixed: every element passed to
   `parse_location_list` is now run through the same split before parsing.
   De-duplication and primary-first ordering preserved. Pinned with two
   `synthetic: true` fixture cases, one exercised directly through
   `parse_location_list` via a new `raw_list` field and a new
   `test_list_entry_point_matches_field_entry_point` test.
3. **Latent remote-misclassification bug, same defect class.** Parenthetical
   annotations are lifted out of a segment before Remote detection runs, and
   Remote detection never looked at the lifted annotations — only at comma
   parts. `"Austin, TX (Remote)"` therefore resolved `city_only`/`on_site`
   instead of `remote`. Leading Remote (`"Remote (US)"`) already worked,
   which is what made the trailing case easy to miss. Fixed in the same pass
   as item 2; pinned with a `synthetic: true` fixture case.
4. **Two false docstrings.** `lever.py`'s `fetch_board` said "Never raises"
   directly above a `raise RuntimeError` for a null client — reworded to say
   the no-raise guarantee covers source failures, not caller bugs. (`ashby.py`
   has the identical phrasing and the identical null-client raise, but was
   not named in the review; left untouched rather than guessing it should be
   in scope.) `locations.py`'s module docstring said `"Global, Remote"` stays
   `unknown` "same as a lone `Global`" — true for `city` (`None` both ways),
   false for `confidence` (`remote` vs. `unknown`); corrected.
5. **Registry/poller mismatch undocumented.** `data/board-registry.yaml`
   marks `lever:alloy` and `ashby:ramp` `status: active`, and the registry
   test pins them into the pollable set, but `workers/tasks.py` and `cli.py`
   both hard-filter `pollable(ats="greenhouse")` — nothing polls Lever or
   Ashby boards; their jobs enter the corpus only via `make seed`'s
   fixtures. Recorded in "Not real yet" so an operator reading the registry
   does not conclude otherwise.

Net effect on the numbers elsewhere in this file: Python tests 336 → 350 (14
new: 2 new fixture cases × the field-entry-point checks, plus a
list-entry-point check on 2 cases); location-parser assertions 145 → 159;
total automated tests 382 → 396. Row counts on the seeded dev database
(`jobs=31, companies=3, sources=3, source_job_records=31, job_locations=62,
job_source_links=31, ingestion_runs=4, users=1`) were checked before and
after this session and are unchanged — the new database-backed test
coverage referenced above is exercised entirely inside rolled-back
transactions (see `tests/conftest.py`).

### 2026-07-30 — M1a closed: provider breadth (Lever + Ashby)

All 10 tasks of `docs/plans/2026-07-30-m1a-provider-breadth.md` executed this
session. Greenhouse, Lever, and Ashby now sit behind one `JobSourceAdapter`
Protocol; the location parser handles all three providers' shapes; the two
upserts that would have raced under concurrency are fixed;
`domain/ingestion.py` and the API routes are both tested against a real
database for the first time; and `make seed` / `make demo` load all three
fixture boards.

**The most consequential finding: neither Lever nor Ashby publishes an
updated-at field.** Lever has `createdAt` only (a creation timestamp, not a
freshness signal); Ashby has `publishedAt` only. ADR 0007 specifies M1d's
phase-2 conditional polling as a diff on "new or changed `updated_at`" — and
on two of the three providers there is no such field to diff. Both adapters
set `source_updated_at=None` and the test suite asserts this as a recorded
fact (`test_lever_publishes_no_updated_at`-shaped assertions), not an
oversight. **M1d must fall back to the description content hash on these two
providers** — the hash already exists (`content_hash`, reused from the
Greenhouse adapter) and `persist_source_job` already compares it
(`content_changed`), so the fallback is not new machinery, but ADR 0007's text
describes a diff that two-thirds of the registry cannot perform as written.

**Ten Lever board tokens were guessed from company names; two were live**
(`alloy` populated, `plaid` empty with `200 []`, the other eight 404). Direct,
measured support for the existing ADR 0006 conclusion: Lever boards must be
found by probing a company's own careers page, not guessed and not harvested
from Common Crawl (`jobs.lever.co/robots.txt` disallows `CCBot`). Recorded as
fixtures — `alloy_board.json`, `plaid_empty_board.json`,
`ramp_unknown_board.json` (Lever's 404 shape) — so I3's empty-vs-unavailable
distinction has real Lever payloads behind it, not just Greenhouse's.

**Two fabricated-city bugs, both found by running the parser against real
recorded payloads rather than by reading it.** `"Vancouver, BC"` (3× on the
Alloy board) parsed to a city literally named `"BC"` — the subdivision code
was being read as if it were the city. `"New York, NY (HQ)"` (95 of 123
postings on the recorded Ashby/Ramp board) parsed to a city named
`"NY (HQ)"` — the parenthetical annotation was never stripped before the tail
token became the city. Both are I1 failures in the module whose own docstring
claims to enforce I1, on the two provider fixtures this plan added. Fixed
(`96a4e16`, `12da0ce`); both are now regression fixtures, not just a bug
report.

**ADR 0008, and what it deliberately does not fix.** Fixing the two bugs
above surfaced a separate, older gap: `"New York"` alone (no state, no
country, no corroboration) resolved to `unknown` — the parser's
corroboration rule is right for junk like `"Global"` but wrong for the one
city this whole product exists to find. ADR 0008 adds a short, enumerated,
committed list of NYC place names (the five boroughs and their common
spellings) that resolve to `city_only` without corroboration, and nothing
else. The cost is stated in the ADR and repeated here on purpose: **`"London"`
stays `unknown`**, and so does every other bare city name not on the list —
the enumeration is deliberately narrow rather than a general gazetteer, which
would be the guessing I1 forbids. A second, smaller residual gap is marked
`TODO(M1)` in `locations.py:481`: a corroborated-but-unresolved second part
still lets junk corroborate junk — `"Global, XX"` comes out with city
`"Global"`. Not a new failure mode (the pre-ADR-0008 parser did the same, just
naming the city `"XX"` instead) and not fixable without a real gazetteer.

**Also found and recorded, less urgent:** `ParsedLocation.is_nyc` tests
`city` only (`locations.py:331`). A location parsed as `state="New York"`,
`city=None` — the real shape of `"New York, USA, Remote"`, a recorded
Greenhouse string — is therefore `is_nyc == False`. ADR 0007 assigns a board
to the hourly `hot` tier on producing an NYC posting, so a board whose
postings only ever say statewide-remote New York would poll daily instead of
hourly: the product's stated goal (same-day knowledge of an NYC opening)
failing in the direction that loses coverage, not the direction that
fabricates one. Not fixed this session — flagged for whoever builds M1d's
tiering, since fixing it means deciding whether a state-level "New York" claim
is strong enough evidence of NYC-ness to actually place, which is a product
call, not a parser bug.

**Task 10 (this task, closing the plan): API route tests.** The database
fixture from Task 9 (`db_session`) truncates and rolls back inside its own
transaction; letting the FastAPI app open its *own* session in a route test
would make the app blind to that transaction's uncommitted rows, block on the
`TRUNCATE`'s lock, and commit for real against this developer's database.
Avoided by overriding `get_db_session` via
`app.dependency_overrides` with a stand-in that yields the fixture's own
session — every route in `tests/test_routes.py` now reads and writes inside
the same transaction the test controls, and nothing it does survives the
test's rollback. Confirmed empirically, not just by reasoning about it: dev
database row counts were queried before writing any route test and again
after the full 336-test suite ran — `jobs=10, companies=1,
source_job_records=10, job_locations=21, job_source_links=10,
ingestion_runs=1, sources=1, users=1` both times, identical.

The route response shapes in the task's own draft test code were wrong in one
place, caught by reading the real schemas before writing assertions (per this
task's own instruction that the route is the contract): `HealthResponse` has
no `checks` wrapper — `database` and `redis` are top-level keys — so the
draft's `body["checks"]` assertion was rewritten to match
`nightshift/api/schemas.py` rather than the other way around.

`make seed` was extended to load all three fixture boards (Task 10 step 3),
attributed to `greenhouse_fixture` / `lever_fixture` / `ashby_fixture`
respectively, following `FixtureGreenhouseAdapter`'s exact shape (client-less
subclass, overrides only `fetch_board`). Verified safely before running it
for real: a throwaway, uncommitted pytest file exercised
`FixtureLeverAdapter` / `FixtureAshbyAdapter` through the same
truncate-then-rollback `db_session` fixture, confirming 9 and 12 jobs created
respectively with zero failures, then deleted. Only after that did `make seed`
run for real via `make acceptance` — a deliberate, permanent change to the
dev database (not the hazard above): the corpus grew from 10 jobs / 1 source
to **31 jobs / 3 companies / 3 sources / 62 locations**, and `make acceptance`
passed in full — 18 verify checks plus 6 seeded browser tests, all green,
against the new three-provider corpus.

### 2026-07-30 — M1 design: board discovery

Design only. No implementation code was written; the deliverable is
`docs/architecture/board-discovery.md` plus ADRs 0005–0007.

**The milestone changed shape because the goal was restated.** M1's registry was
specified as a curated file. Asked how many companies belonged in it, the human
answered that the goal is same-day knowledge of *any* NYC tech opening from *any*
employer. No list length reaches that, so the registry becomes the output of a
pipeline. Q3 in `docs/QUESTIONS.md` records the original question and why it was
the wrong one.

**Everything in §3 of the design was measured, not estimated.** Common Crawl's
July 2026 index yields 2,605 board tokens in about two minutes at no cost.
Greenhouse serves two board domains and the newer one contributed 433 tokens the
older one did not. Listing a board costs 27 KB against 841 KB for full
descriptions — a 31× gap that decided the polling design — and the listing
endpoint carries an `ETag`, so unchanged boards revalidate for nothing.

**Lever is structurally invisible to the archive.** `jobs.lever.co/robots.txt`
names `CCBot` — Common Crawl's crawler — and disallows it, so Lever job pages are
absent and always will be. Its API remains sanctioned. Lever must be discovered by
careers-page probing, which is now a test assertion rather than a footnote.

**Two errors in my own first draft, both found by checking rather than reading.**
I wrote that Ashby returns the employer name. It does not — not at board level,
not on any job object — which would have routed all 383 Ashby boards to manual
review and quietly broken the approval design. The name is on the board page,
which Ashby's robots.txt permits. Second, I had treated the token as a usable
name; Ashby's `0g` is "0g Labs" and `10xteam` is "10x Team". Deriving an employer
from its slug is exactly the fabrication I2 forbids, and it is now a fixture.

Also established: Lever returns `404` with `{"ok":false}` for an unknown token and
`200` with `[]` for a live board with no openings. I3 depends on those being
distinguishable and they are.

**A rule of the human's was relaxed, deliberately and on the record.** A1 requires
per-entry human review of discovered boards. At 2,605 that is a control nobody
performs, and an unperformed control is worse than a weaker one that runs, because
the documentation still claims the strong one. ADR 0005 moves it to batch approval
with typed exceptions. Asked whether I would have invented that rule unprompted,
the honest answer was mostly no — the tell being that my first instinct on seeing
the number was to ask for it to be relaxed. The junk board `a3c41b8b71eff8c4`,
which returns ten well-formed postings under a machine-generated name, is why the
rule earns its place and why deleting its fixture would hollow out the gate.

**Scope answered for the long term** (§10): geography is nearly free because the
unit of polling is a company, not a city — whole boards are already fetched and
`job_locations` already stores every location, so NYC is a query filter. What
costs money is the geocoder, which A4 chose as an NYC-government service that
knows nothing else. Job-type breadth is free to collect and expensive to be useful
about, since M3's matching is tech-shaped. And the small end of the labour market
— local restaurants, contractors — publishes nothing machine-readable, so it is
unreachable by any polling strategy. The honest ceiling is every job posted to a
machine-readable board in the US.

**LinkedIn and Indeed were asked about directly and refused** (§9), with the
robots.txt evidence recorded so it is not re-litigated.

### 2026-07-30 — renamed CitySignal → Nightshift

Product decision by the human. Done before M1 rather than after, because the
discovery subsystem would have roughly doubled the number of references.

193 occurrences across 47 files, in three case forms (`citysignal`,
`CitySignal`, `CITYSIGNAL`) — which collapse to three substitutions, since the
lowercase form is a prefix of `citysignal_dev_only`, `citysignal_ci` and
`citysignal_env`. The Python package directory was moved with `git mv` so history
follows it. Recorded ATS fixtures were checked first and contain the string
nowhere, so no committed payload was edited.

Three things the text substitution could not reach, all found by running it:

1. **The Docker Compose project name changed too.** `docker compose down -v`
   addressed the *new* project and left `citysignal-postgres-1` running on port
   5433, so the new stack could not bind. Removed the orphaned containers,
   volume and network by name.
2. **A container created during that failed attempt was reused.** It reported
   `running (healthy)` with no host port mapping at all, because it had been
   created while the port was taken. `up -d` left it alone since the config hash
   matched. Fixed with `--force-recreate`; worth remembering that "healthy" and
   "reachable" are different claims.
3. **The database role, database name and password are all in the name.** The
   existing cluster was initialised as `citysignal`, and initdb only runs on an
   empty volume, so the volume had to be destroyed rather than migrated. Fine
   here — the corpus is fixture data — but it is the reason the rename is cheap
   now and would not have been later.

Two judgement calls in the diff. The self-identifying `HTTP_USER_AGENT` URL was
corrected to the real repository casing, `Tahmudun/Nightshift`, since its purpose
is to let a site owner look us up. And the quoted `.env` syntax error in the
2026-07-30 acceptance entry below was **restored to `CitySignal`**: it is
presented as recorded output, and rewriting a product name inside a verbatim
error message would make the record tidier and untrue.

Verified: `make check` (204 Python, 35 web), `gitleaks` clean, and
`make acceptance` — 18 checks and 6 browser tests — against a cluster
initialised from empty under the new name.

### 2026-07-30 — first CI run on real infrastructure

Remote created (`github.com/Tahmudun/Nightshift`, public) and `main` pushed. The
push was made over HTTPS, not SSH: there are no SSH keys on this machine, so
`git@github.com:` was refused, and there was already a working GitHub credential
in the macOS keychain.

Run 1: `python` and `web` green, `migrations`, `e2e` and `secrets` red. Both
failures were in CI configuration that had never been executed, which is the
entire argument for acceptance row 2 not being a formality.

**1. The secret scan had never run — not once.** It did not fail to find
anything; it crashed before scanning a single file:

```
panic: regexp: Compile(`^(?!\.env\.example$|...).*`):
       error parsing regexp: bad perl operator: `(?!`
```

`.gitleaks.toml` expressed "flag this password anywhere except these four files"
as a negative lookahead in `path`. gitleaks compiles rule patterns with Go's
`regexp`, which is RE2: no backtracking, therefore no lookahead, and
`MustCompile` panics. Reproduced locally, byte-identical.

The failure mode is worth naming. A crash and a strict scan both leave CI red,
so nothing about the job's colour distinguishes "this scanned everything and
objected" from "this has never scanned anything." The evidence for acceptance
row 6 had been written as though the tool ran.

Rewritten as a rule-level `[rules.allowlist]`, which is the supported way to say
"except these paths". Scanning then surfaced two files that legitimately name the
password and were never in the original list — `tests/test_env_example.py`, which
asserts the confinement, and `docs/PROGRESS.md`, which quotes it as evidence —
plus `.gitleaks.toml` itself, whose regex is a literal copy of the string. All
three added.

Verified against gitleaks **8.24.3**, the version `gitleaks-action@v2` pins,
rather than the newer build Homebrew installs: full history exits 0, and a
planted `nightshift_dev_only` in a non-allowlisted file exits 2. Per CLAUDE.md
§7, an allowlist that silences everything is not a scan.

**2. The CI Postgres image does not exist.** `Initialize containers` failed in
both `migrations` and `e2e`, before checkout:

```
docker pull ghcr.io/imresamu/postgis:16-3.4-bundle
Error response from daemon: manifest unknown
```

Two independent errors in one reference. The tag is `16-3.4-bundle0`, with a
trailing zero, and ghcr.io denies anonymous pulls of that package at all — the
runner authenticated to ghcr as the repo owner and still could not fetch it.
Docker Hub serves it unauthenticated.

Confirmed by running the image and executing the committed
`infra/postgres/init/001-extensions.sql` against it rather than trusting the tag
name: postgis 3.4.3, vector 0.7.4, pg_trgm 1.6, pgcrypto 1.3 on PostgreSQL 16.4,
all four `CREATE EXTENSION` statements succeeding.

**Worth carrying forward:** CI runs a third-party prebuilt image while local dev
and `make demo` build `infra/postgres/Dockerfile`. That divergence is why a
non-existent tag sat in the repo unnoticed — no local command ever pulls it.
Acceptable now that CI actually exercises it every push; revisit if the two
builds drift in a way that matters.

Run 2: `python`, `web`, `secrets` and `e2e` green. `migrations` still red, now
on the drift probe, which had also never run anywhere.

**3. The post-write hook could never have worked.** `alembic revision` died with
`Could not find entrypoint console_scripts.ruff`, on CI and on this machine
alike. `alembic.ini` declared the hook as `type = console_scripts`, and the ruff
distribution publishes **no console_scripts entry points at all** — it ships a
compiled binary as a plain script. Changed to `type = module`, which runs
`sys.executable -m ruff`: the interpreter already running alembic, so it needs
ruff on neither PATH nor an entry point.

**4. The drift probe compared our models against the whole server.** With the
hook fixed, autogenerate proposed dropping about forty tables — `addrfeat`,
`faces`, `featnames`, `topology`, `layer` and the rest of postgis_tiger_geocoder
and postgis_topology, which CI's bundle image installs and puts on the search
path. `include_object` excluded exactly three PostGIS names by hand, so
everything else looked like drift.

Now filtered by ownership read from `pg_depend`, which follows whatever is
installed instead of a hand-kept list. The filter refuses to exclude any table
present in the models, whatever pg_depend says: an extension shipping a table
named like one of ours would otherwise switch off drift detection for that
table — the filter hiding the change it exists to surface. Moved to
`nightshift/db/autogenerate.py`, because `migrations/env.py` runs migrations as
an import side effect and cannot be imported by a test. Eight tests, checked
non-vacuous by mutation: removing the models guard fails one, disabling the
table filter fails two.

**5. And then I introduced silent data loss, and nearly shipped it.** Reading
`pg_depend` inside `do_run_migrations` autobegins a SQLAlchemy transaction.
Alembic only commits a transaction it opened itself; finding one already open,
it treated it as externally managed, and the enclosing `connect()` block rolled
the whole migration back on close. Every `CREATE TABLE` ran, the
`alembic_version` row was inserted, then `ROLLBACK` — and `alembic upgrade head`
printed "Running upgrade" and **exited 0** with an empty database.

Found only by checking the database after a run that claimed success, against a
local container built to match CI's image. Reproduced, then isolated by removing
the one added line: `COMMIT` and the tables came back. Fixed by ending the read
before configuring alembic, so alembic owns its transaction again.

The exit code cannot see this, so a CI step now asks the database instead:
**Upgrade actually persisted** fails if `alembic current` is not at head after a
successful upgrade. Verified in both directions — it passes at head and fails
after a downgrade.

Worth stating plainly: the mistake was mine, made while fixing something else,
and the only reason it did not land is that verification looked at the database
rather than at the exit code. A green `alembic upgrade head` was, for one commit,
completely compatible with an empty schema.

**Verified after the fix** — `make check` (204 Python, 35 web), `make reset-db`
(version row present, 10 tables), `make acceptance` (18 checks + 6 browser
tests), and CI's full migrations sequence replayed against a local replica of
the CI image: up, down, up, drift probe clean, seed loads.

Run 3 at `4c1643f`: **all five jobs green**, longest 129s.
https://github.com/Tahmudun/Nightshift/actions/runs/30528565491 — acceptance
row 2 satisfied, and M0 closed.

The pattern across all three runs is worth keeping. Every defect CI found lived
in a file no local command executes: a scanner config, a service image tag, a
formatter hook, an autogenerate filter. The application code was green on run 1
and never broke. "The same commands pass on my laptop" was true the whole time
and would have shipped five bugs.

### 2026-07-30 — M0 acceptance

Docker Desktop installed by the human, clearing B1. Ran the acceptance criteria
against live infrastructure for the first time. Four bugs, every one of them found
by running the thing rather than by reading it.

**1. `make demo` failed on a clean clone.** The reported symptom:

```
.env: line 53: syntax error near unexpected token `('
.env: line 53: `HTTP_USER_AGENT=CitySignal/0.1 (+https://github.com/tahmudun/citysignal)'
make[1]: *** [migrate] Error 1
```

(Recorded before the project was renamed to Nightshift, and left as it was
actually emitted. Rewriting the product name inside a quoted error message would
make the record tidier and untrue.)

The Makefile loads config with `set -a && source .env`, because Alembic and the
seed CLI read the process environment rather than pydantic-settings. An unquoted
`(` is a bash syntax error. Three parsers read this file — bash, `docker compose
--env-file`, python-dotenv — with three different quoting rules, and only
python-dotenv had ever been exercised. `tests/test_env_example.py` now sources the
file exactly as the Makefile does and requires bash and python-dotenv to agree on
every value.

This is the M0 acceptance criterion that matters most and it was broken by one
missing pair of quotes. Worth remembering that the failure had nothing to do with
the interesting parts of the system.

**2. Acceptance row 5 had no automated coverage at all.** The existing Playwright
suite runs with *no API* on purpose — it proves the app reports "api unreachable"
instead of rendering an empty list, which is the right thing to test. But it meant
nothing asserted that real rows from Postgres ever reach a screen. Added
`apps/web/e2e-seeded/`, and an `e2e` job to CI so the criterion cannot regress
silently.

While writing it: the first version of the I1 test failed, and the app was right
and the test was wrong. `ConfidenceLegend` renders the same ladder component for
all five levels to document the visual language, so an unscoped
`getByRole('img')` was asserting against the legend rather than against job data.
Scoped to `role="article"`. Then added the assertion that the rejected label *does*
appear in the legend — otherwise over-narrow scoping would make the test pass by
matching nothing, which is the failure mode CLAUDE.md §7 means by "a test that
cannot fail is not a test."

**3. `make setup` never installed Playwright's browser.** It ships separately from
the npm package and the required build changes on minor upgrades, so
`make test-e2e` could not work from a clean clone. The e2e targets provision it
now; keeping it out of `make setup` avoids putting a 100 MB download in front of
every first run.

**4. `make acceptance` had a hidden step — mine.** I added the seeded suite to the
target, but `verify.py` starts its own uvicorn and tears it down on exit, so the
suite that ran after it had nothing to talk to. Six tests failed on
`ECONNREFUSED`. It had passed when I first ran it only because I had started
uvicorn by hand — precisely the class of thing acceptance criterion 1 exists to
forbid, committed by me while verifying that criterion. `playwright.seeded.config.ts`
now declares both servers, gated on `/health`, and the duplicate CI step is gone.

**5. The palette failed WCAG AA, and worse than the review guessed.** Review action
6 was "measure contrast on `paper-faint`/`ink-500`; lighten if below 4.5:1".
Measured: `paper-faint` 3.89:1, a genuine fail for the 9-11px labels it carries.
But `ink-500` — a *surface* shade — was being used as a text colour in fourteen
places at **1.69:1**, which is close to invisible. The palette had three named
text weights and a fourth unnamed one that nobody had decided on. Fixed by
lightening `paper-faint` to 5.43:1 and moving every `text-ink-500` onto it, so
there are now exactly three text steps and all three are readable.

`colour-contrast.test.ts` computes the ratios from the real tokens rather than
trusting a comment. Confirmed non-vacuous by restoring the old value: three tests
fail. It also pins `ink-500` *below* 3:1, so lightening it to reuse as text trips
a failure that points at the explanation.

**Verified against live infrastructure:** migration down/up dropping and restoring
all 8 enum types; `/health` degrading per-dependency with real containers stopped;
all four `job_locations` check constraints refusing their violations. The review's
line — *"a constraint nobody has seen reject anything is a comment with extra
syntax"* — is now settled: each one raised `IntegrityError`.

**Not verified at the time:** CI (no remote exists — it needs an account
decision), the final clean-clone re-run (host disk, B2), and the 6 seeded browser
tests after the last commit (Docker died, B3). B2 and B3 were both cleared later
the same day — `make acceptance` passed at `14abb68`, 18 checks plus 6 browser
tests. CI remains the one open item, and it is the one that needs a human.

The disk filling up was self-inflicted in part: I made two full clones of the repo
to test the clean-clone path, ~730 MB each in `node_modules` and venvs, on a
machine that had ~2 GB free to begin with. Both are deleted. Testing the
clean-clone path is right; doing it twice without checking `df` first was not.

### 2026-07-29 — M0 build

Read CLAUDE.md, AMENDMENTS (all 15), and the relevant PRODUCT-SPEC sections.

Verified the Greenhouse endpoint against a live board before writing the adapter,
per A1's instruction to re-verify field shapes. That paid for itself immediately —
five things the spec did not say, now encoded in the code and its comments:

1. `content` arrives **HTML-escaped** (`&lt;p&gt;`), so unescaping must precede
   any tag handling.
2. `location.name` is one `;`-delimited string that routinely names ten places.
   Concrete proof of A2 — the messiest real value found was
   `"Boston, Massachusetts, USA; Connecticut, USA, Remote; … ; Rhode Island, USA, Remote"`.
3. `application_deadline` was **null on all 426 postings**. A10, confirmed on
   real data.
4. Compensation is not a top-level field; it hides in `metadata` as
   `value_type == "currency_range"`, and it is present on NYC postings
   (pay-transparency law) while absent on most others.
5. `updated_at` is a last-modified stamp and `first_published` is the real
   publication date. They are carried in separately-named columns and there is no
   `posted_at` anywhere in the codebase to be misread.

Wrote `tests/fixtures/locations.yaml` **before** the parser, as A2 directs.

**Two real bugs found by tooling rather than by reading:**

1. mypy strict caught `IngestionRun.source` being used by `GET /sources` but never
   defined as a relationship on the model — a runtime `AttributeError` on a route
   that had no test yet.
2. The company-normalization suite, written during the milestone review, caught
   `normalize_company_name("Moody's")` returning `"moody s"`. The apostrophe was
   being replaced with a space, leaving a dangling token, so `Moody's Analytics`
   and `Moodys Analytics` would have become two separate companies in a table
   whose `normalized_name` is unique. Real NYC employers affected: Moody's,
   Macy's, Lowe's, McDonald's. Fixed by deleting apostrophes rather than spacing
   them, and both the typewriter and typographic forms are now covered.

The second one is the argument for writing those tests earlier: it was a pure
function with no database dependency, so nothing was stopping me.

Deviations from spec, all deliberate and documented above: no
`discover_companies()` (A1), location on its own table (A2), ARQ (A11), no
Turborepo (A12), schema narrower than §6.

Did not start the 3D city. It is at M4 for a reason.
