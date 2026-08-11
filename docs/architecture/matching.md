# Explainable matching — the M3 design

> Required reading before any M3 work. `CLAUDE.md`'s read-order table points here.
>
> This document decides M3's slice order, its tables, where a guess is allowed to
> touch a number, and which spec'd components are deferred and why. Where it
> disagrees with `PRODUCT-SPEC.md` §8, this document is the later decision and
> `AMENDMENTS.md` A13 is the authority it is applying.

M3 is the milestone where the system starts making claims about a person. Every
milestone before it made claims about the world — this board listed these jobs,
this posting names these locations — which are checkable against a recorded
payload. A match score is different in kind: it is an assertion that somebody is
or is not suited to something, and there is no payload to check it against.

That is what invariants I2 and I4 exist for, and it is why this document spends
more space on evidence and evaluation than on arithmetic. The arithmetic is easy.

---

## 1. What M3 delivers, and in what order

Four slices, each ending in something runnable and visible in a browser.

| Slice | What lands | Why it is here |
|---|---|---|
| **M3a** | The recorded corpus, the labeling worksheet, the committed answer key, and requirement extraction. The job page shows what a posting requires, each requirement quoting the sentence it came from | The human is the bottleneck, so their task is generated first and labeling happens in parallel with the extractor being built |
| **M3a.1** | Raise required-technology recall from 0.459 toward 0.70+, holding precision and necessity accuracy. No new tables, no new surface | **Added 2026-08-05 by the human, after M3a shipped and reported 0.459.** Not in the original design. M3b's gate turns these readings into a verdict about a person, and A13 makes a wrong `ineligible` the worst output this engine can produce — a gate reading half the requirements is a gate guessing. The measured lever is in PROGRESS under "M3a.1" |
| **M3b** | The deterministic eligibility gate, the role-family and seniority classifier. `jobs.role_family` and `jobs.seniority` stop being null. Blockers named on the job page; the internship-season filter becomes real | Graded against M3a's answer key from its first commit |
| **M3c** | The score, the versioned weights, the evidence graph, the explanation panel. `match_results` precomputed so a ranked query is possible | Nothing here is honest before M3b's gate exists |
| **M3d** | The evaluation suite in CI, ranking metrics, hallucination checks, and the four queue rows that have been named-but-empty since M2d | M3's acceptance criteria are mostly earned here |

### 1.1 The order is not negotiable, and the reason is specific

The answer key is committed **before** any matching rule is written. If the rules
come first, the corpus gets chosen — unconsciously, in good faith — to contain
the cases the rules already handle, and the evaluation suite reports a number
that measures nothing. A13 states this directly: collect first, label first.

This project has recorded eight consecutive milestones in which something that
reported success was wrong. An evaluation suite written after the thing it
evaluates is the highest-leverage version of that failure available here,
because its whole purpose is to be the thing that catches the others.

---

## 2. Where a guess is allowed to touch a number

PRODUCT-SPEC §8.1 asks for a hybrid: deterministic rules for hard eligibility,
semantic models to assist with skill normalization, role similarity, project
evidence and adjacent experience. It does not say where the boundary is. This is
the boundary.

**An embedding may propose. It may never score.**

Concretely: the local `bge-small-en-v1.5` model (A5) may suggest that a
posting's phrase *"experience with distributed systems"* relates to a user
project bullet reading *"built a sharded work queue"*. That suggestion earns
points only if it resolves to **a character span in `jobs.description_text` and
a character span in the user's own confirmed data**, both of which are stored,
both of which are shown. If either span cannot be produced, the proposal
produces nothing — no points, no explanation line, no mention.

There is no cosine similarity anywhere in the score. There is no component whose
value came from a model.

> **M3c Task 11 measured this permission and then declined to use it. Nothing in
> this system proposes.** ADR 0018 has the figures. Two corrections belong here
> rather than only in the ADR, because this section's argument depends on them:
>
> 1. **The span rule proves provenance, not entailment**, and the paragraph
>    above quietly assumed otherwise. A proposal of *"you meet the Java
>    requirement"* quoting the posting's word *Java* and the user's word
>    *Python* satisfies both spans literally and completely — and renders on the
>    page beside both quotes, looking audited. The rule stops invented text. It
>    does not stop unwarranted inference, which is the thing a similarity score
>    actually produces.
> 2. **Cosine over technology names ranks siblings above concepts**, so the
>    permission has nothing safe to spend itself on. Measured over this corpus,
>    the highest-confidence proposal available anywhere is *Java from Python* at
>    0.797, and the one relation worth having — *Machine Learning* from PyTorch
>    — finishes ninth at 0.624.
>
> The rule stated at the top of this section still stands and is still the
> boundary. It is now enforced by there being no proposer at all.

### 2.1 The span rule binds three components, and the reason is not arbitrary

The rule above applies to **role relevance, skill overlap and project
evidence** — the three components that make a claim about *the person*. Those
are the claims I2 exists to govern, and each must trace to two quotable strings.

**Location, freshness and internship priority make no claim about the person.**
Freshness is arithmetic on a date the source published; location compares
`job_locations.city` and `remote_policy` against a preference the user typed;
priority reads the posting's own seniority. There is no span to quote on the
user's side because there is no assertion about their qualifications being made.

**Freshness reads `source_published_at`, not `last_seen_at`**, and this
paragraph said `last_seen_at` until M3c Task 4 measured it. `last_seen_at`
records when *this system* last polled: across 31 seeded jobs it held one
distinct day, against a 10-to-347-day spread of publication dates over the same
rows. Scoring on it would also make a job's freshness depend on which poll tier
ADR 0007 assigned its board — this system's own infrastructure, which is the
`application_urgency` argument in §5.1 pointed at ourselves. `source_published_at`
is a genuine publication date on all three adapters (Greenhouse
`first_published`, Ashby `publishedAt`, Lever `createdAt`) and is present on 153
of 153 recorded postings. A source that gives none makes the component
unassessable rather than zero.

These components still record evidence — the values that were compared, so the
breakdown is inspectable and I4 holds — but they are exempt from the span
requirement, and §4.3's constraint distinguishes the two cases explicitly.
Requiring a quoted span where none exists would mean inventing one, which is the
failure this whole section is arranged to prevent.

### 2.2 Why not the alternatives

**Fully deterministic** — vocabulary and rules only, no embeddings at all — is
defensible and was seriously considered. Its failure mode is invisible: matches
the user never sees, with no signal that they were missed. Rejected for that
reason rather than for capability.

**And then chosen anyway, on evidence, at Task 11.** M3 ships fully
deterministic. The invisible-recall objection above is real and still stands as
a cost; what Task 11 established is that the semantic layer offered to pay it
would have bought fabricated qualifications rather than missed matches. §2.3
now carries the measurement.

**Embedding-first ranking**, with rules as a post-filter, makes I4
unsatisfiable. "You scored 0.83" has no breakdown because there is not one; any
explanation panel built on top of it is text generated after the fact to justify
a number that did not come from it. That is precisely the failure I4 was written
to forbid, and it would be undetectable from the outside — the UI would look
identical to an honest one.

### 2.3 What this costs

Recall. A posting that describes a requirement in words the vocabulary does not
carry, and which the embedding cannot tie back to a span, is a requirement this
system will not see. That is a real limitation and it is measured rather than
assumed: M3d reports skill-extraction recall against the answer key, so the size
of the gap is a number in CI rather than a hope.

**Measured, at Task 11.** Against the committed corpus — 71 postings naming at
least one required technology, 240 requirement rows per profile — the rules-only
scorer matches 90, 88, 59 and 0 rows on the four fixture profiles. So the gap is
150 to 181 rows on any profile that states anything.

The number that matters is what is *inside* that gap, and it is not a queue of
matches waiting for a model. Ranked by similarity, it is dominated by sibling
technologies the person specifically does not have — `Java` beside Python,
`Azure` beside AWS, `TensorFlow` beside PyTorch. See ADR 0018.

The residue that is genuinely recoverable is small, specific, and not an
embedding problem: concept terms like `Machine Learning` (26 occurrences),
`Distributed Systems` (4) and `Data Structures` (3), which a concrete tool can
demonstrate. The carrier for those is a `demonstrated_by:` relation in
`data/skills.yaml` — a claim a human writes down and can be argued with. Not
built in M3.

---

## 3. The answer key

### 3.1 What is labeled

**What each posting requires — never what it means for a particular person.**

A verdict ("I am ineligible for this") bakes the labeler's own graduation date
and authorization status into the fixture. Both change. When they change, every
label silently becomes wrong while continuing to pass, which is the exact
failure class this project keeps finding. A posting's stated requirements do not
change.

The verdict is therefore **computed** from (labeled requirements × profile),
which also means the computation is what gets graded — which is what we want to
test in the first place.

### 3.2 The label shape

Per posting:

| Field | Values |
|---|---|
| `is_internship` | yes / no / unclear |
| `graduation_window` | years, or `not stated` |
| `enrollment_required` | yes / no / not stated |
| `degree` | none / bachelors / masters / phd, each optionally `+equivalent` |
| `min_years_experience` | number, or `not stated` |
| `required_tech` | list |
| `mentioned_not_required` | list |
| `sponsorship` | offered / not offered / not stated |
| `note` | free text — what made this one hard |

Two fields carry most of the value.

**`mentioned_not_required`** is the difference between a usable product and a
useless one. Ramp's Android internship lists Kotlin and the Android SDK under
*what you'll need*, and React, TypeScript, Python, Flask, SQL, Compose, MVVM,
coroutines and Gradle under *nice to haves*. A naive extractor harvests every
technology name in the description and concludes the internship requires twelve
technologies — then confidently reports nine gaps against a candidate who is
fully qualified. The label is what turns that from an invisible product defect
into a red test.

**`+equivalent`** is the escape hatch A13 names. Datadog's AI Research Scientist
posting reads *"You hold a PhD in Computer Science... (or have equivalent
experience)"*. A rule that matches `PhD` and stops has permanently removed that
role from the user's world. `phd+equivalent` must resolve to **`uncertain`**,
never `ineligible`.

### 3.3 A wrong `ineligible` is the worst output this engine can produce

Every other error is visible. A wrong score is visible next to its breakdown; a
missing skill is visible in the gap list; a stale listing is visible in its
freshness badge. A wrong `ineligible` removes an opportunity from the user's
world and reports nothing. They never learn it existed.

Consequences carried through the rest of this document:

- When a rule cannot decide, it returns `uncertain`. Never a default.
- Ineligible jobs are **shown and dimmed with the blocker named**, never hidden.
  A hidden row is a parsing bug nobody can see.
- M3d reports eligibility precision **and recall separately**, because a gate
  that answers `uncertain` to everything has perfect precision and is worthless.

### 3.4 The corpus

Nine boards, recorded live, sampled to roughly 60 postings. All nine were probed
and confirmed live on 2026-08-04 before being chosen.

| Board | ATS | Live count | What it is in the corpus for |
|---|---|---|---|
| Jane Street | greenhouse | 225 | Explicit graduation windows and sponsorship statements |
| Jump Trading | greenhouse | 105 | Same, plus separate intern eligibility |
| IMC | greenhouse | 157 | Same |
| Databricks | greenhouse | 809 | A large new-grad / university programme |
| Anthropic | greenhouse | 399 | High-comp tech |
| OpenAI | ashby | 737 | High-comp tech, and a second real Ashby board |
| Point72 | greenhouse | 231 | Non-engineering roles at a high-comp firm |
| Akuna Capital | greenhouse | 34 | A small board with less polished copy |
| Old Mission | greenhouse | 34 | Same |

The existing three fixture boards — Datadog, Alloy, Ramp — stay in the corpus
but cannot carry it. All three are well-organised NYC companies writing tidy
descriptions, which is the corpus most likely to make a parser look better than
it is. `datadog_board.meta.json` already records the gap in its own
`coverage_not_available_on_this_board` field: *"internship in the title"*.

Trading firms were chosen over big tech deliberately and not only for
reachability (§3.6). They are the most explicit employers in this market about
exactly what M3 has to parse: graduation years stated numerically, sponsorship
stated in writing, and named internship programmes whose eligibility differs
from the firm's full-time roles — one of the six hard cases A13 lists.

### 3.5 Fixture format

Unchanged from M1's, because M1's is already right. Per board: every posting
object byte-identical to the live response, only the *set* reduced, with a
sibling `.meta.json` recording the endpoint, the timestamp, the full response
count, a per-posting note saying why that posting is in the corpus, and a
`coverage_not_available_on_this_board` list.

Labels live beside them in `services/api/tests/fixtures/eligibility/labels.yaml`,
keyed by board token and posting id, so a label always points at a payload in
the same commit.

### 3.6 A blind spot this milestone names

Probed 2026-08-04, three ATS endpoints each: `meta`, `facebook`,
`metaplatforms` and `apple` return **404 on all twelve**. Meta, Apple, Google,
Amazon, Microsoft and Bloomberg run their own careers systems and are not on
Greenhouse, Lever or Ashby. They are therefore invisible to this system.

The coverage page currently names four structural blind spots — Lever's crawler
policy, Workday/iCIMS/Taleo, employers with no public board, aggregator-only
postings. **None of them covers this case**, and a reader would reasonably
conclude big tech is covered. It is not. M3a adds the fifth blind spot.

It must distinguish two situations, because they are different disclosures:

- **Refused in writing.** `metacareers.com/robots.txt` opens with a notice
  prohibiting automated collection without written permission.
  `google.com/robots.txt` disallows `/about/careers/applications/jobs/results`
  by name. CLAUDE.md §8's rule is *scraping anything that asks not to be
  scraped* — these ask, so these are out, and no future milestone changes that
  without those employers changing their terms.
- **Simply unbuilt.** `amazon.jobs/robots.txt` disallows only `/internal`.
  `jobs.apple.com` serves no robots.txt at all. Neither refuses. Neither is
  built, and neither is M3's business.

Whether to build the second group later is an M6-or-later question needing its
own ADR, answered **per employer rather than per category** — as the probes
above show, the answers genuinely differ. Two constraints for whoever writes it:
robots.txt is not the terms of service and the terms need reading separately;
and any scraped source needs the same I3 discipline the ATS adapters have,
because a scraper's commonest failure is a page that renders empty, which is
indistinguishable from an employer with no openings. `FetchOutcome` already
separates *listed* from *fetched* and would carry it.

The legitimate middle path, if it is ever wanted, is `JobPosting` structured
data — a machine-readable block employers embed deliberately so search engines
can index them. Reading a published machine-readable format is different in kind
from parsing rendered HTML, and it survives redesigns.

---

## 4. The tables

Three new, one column added.

### 4.1 `job_requirements` — what a posting asks for, and where it says so

One row per extracted requirement. Every row carries `start_char` / `end_char`
into `jobs.description_text` and is refused by a trigger if the span does not
quote the stored text — the same trigger pattern `resume_extractions` uses, for
the same reason.

```
job_requirements
  id
  job_id                FK
  kind                  degree | graduation_window | years_experience
                        | technology | authorization | enrollment | role_level
  value                 normalized (a skill name from the taxonomy, a year
                        range, an integer)
  raw_text              the exact substring the span points at
  start_char / end_char
  necessity             required | preferred | mentioned
  has_equivalence       boolean — "or equivalent experience"
  extractor_version
  created_at / updated_at
```

**`necessity` is the column the product turns on.** `preferred` and `mentioned`
never produce a missing-requirement penalty and never appear as a gap.

**Invariant I2 does not apply to this table**, and the distinction is worth
stating because it looks like it should. I2 governs claims about *a person's*
qualifications, which is why `resume_extractions` proposes and never confirms. A
job requirement is a claim about a *posting*, checkable against a stored payload
in the same commit. It needs no confirmation step. It still quotes its span,
because a requirement nobody can trace back to a sentence is not auditable.

### 4.2 `match_results` — PRODUCT-SPEC §6.13

Shape as §6.13, with two departures taken when the table was built at M3c Task 2
and recorded here rather than left for a reader to find in a migration.

**`explanation` is not a column.** §6.13 lists one; §6 of this document says no
explanation text is generated and every line is assembled from `match_evidence`
rows. A stored copy is therefore a second version of the same claim that can
disagree with the rows it was built from — the reason `resumes` dropped §6.4's
`structured_profile` at M2c — and it is also precisely what §2.2 forbids: text
written after the fact to justify a number that did not come from it.

§4.5's `why` is not a partial reversal of this, and the line between them is worth
being explicit about because it looks like one: an `explanation` is assembled
*from* the evidence rows and can therefore contradict them, while a `why` is
produced *alongside* the points by the same call, from the same inputs, and has no
other source to contradict.

**`penalty_score` is one column rather than two.** §5.1 keeps two penalties;
this stores their sum. The evidence trigger binds the six positive components
(§4.3's enum has no penalty member), so a split column would imply an evidence
link that does not exist. What each penalty cost belongs to the explanation —
and §4.6 is where it went at Task 10, because until then nothing carried it and
a reader saw `-18` with no account of it.

`model_version` records the embedding model that produced the proposals; it is
null for a rules-only score, which is every row until Task 11. Unique on
`(user_id, job_id, ruleset_version)`.

**Rows are deleted, never left stale.** Version-checking on read is necessary
and not sufficient: a rewritten job description does not change the ruleset
version, and the evidence rows underneath hold character offsets into text that
has moved. Four triggers added at Task 2 — on `jobs.description_text`,
`job_requirements`, `user_skills` and `user_projects` — delete the affected
scores, which then read as not-yet-computed. Without them ingestion cannot
commit at all: rewriting a description deletes the job's requirements, which
cascades to `match_evidence`, which leaves a positive component with no evidence
and fails the guard below.

**`ruleset_version` is one column covering both the rules and the weights**, and
it has to be, because M3's acceptance criterion is *identical inputs + identical
`ruleset_version` → identical output*. Two columns would let a rule change while
the weights version stayed put, and the criterion would pass over a result that
is no longer reproducible.

The weights and every rule threshold live in `data/matching.yaml` with a
`version`, alongside `data/skills.yaml` and for the same reason: a weight change
must be a traceable data change rather than a migration or a code edit. The rule
*logic* is Python and carries its own `RULESET_LOGIC_VERSION` constant. The
stored value composes the two — `"<logic>+<data>"` — so both are visible in the
row.

**What keeps the logic constant honest is a test, not discipline.** A golden
test pins the full `match_results` and `match_evidence` output for the fixture
corpus. Changing a rule without bumping the constant turns it red with a diff
showing exactly what moved, which is the moment to bump. Relying on a developer
remembering is the version of this that fails silently.

Built at Task 6: `tests/fixtures/matching/golden.txt`, 459 scores over 153
recorded postings × 3 fixture profiles, rendered as text because the diff is the
product. One thing had to be added that this paragraph did not anticipate — the
red test alone is not the guard, because the obvious response to it is to
regenerate. **Regeneration itself refuses** when a score present in both files
moved while `ruleset_version` stayed put, and prints what moved; growing the
corpus is allowed, because a new posting changes no existing score. `as_of` is a
frozen date rather than today, or freshness arithmetic would turn the file red
every morning and train everyone to regenerate without reading it.

**Precomputed, not computed on read.** The daily queue has to sort thousands of
jobs by score, and a sort needs the value in the database. Recomputed on: a new
or changed job, any profile change, and a ruleset version bump. An ARQ task,
inside the existing worker module.

Built at Task 8 as `domain/matching.py` and `workers.tasks.recompute_match_results`,
and the three triggers turned out to be **three routes into one state** rather
than three mechanisms. That was the design decision of the task and it is worth
stating plainly, because the shape it replaces is the obvious one:

* A **new or changed job** already has its scores deleted, by the four triggers
  above. A brand-new job never had any. Either way: no row at the current
  version.
* A **ruleset version bump** changes `ruleset_version`, which is part of the
  uniqueness key. No row at the current version, for every pair at once.
* A **profile change** is the only one no database trigger can see, so
  `domain/profile.py` deletes that person's rows itself — inside the request's
  own transaction. No row at the current version.

So the recompute task takes no arguments naming what changed. Its work item is
the *absence* of a row, found by one anti-join, which means there is no event to
miss and no queue message to lose while the worker is down: the next tick finds
exactly what the last one did not finish. It also means one code path computes a
score rather than three that can disagree about how.

**The profile trigger invalidates rather than enqueues, and that is a departure
from the M3c plan's wording** ("the task is enqueued from a named set of
scoring-relevant columns"). The named set is unchanged and is
`matching.SCORING_RELEVANT_PROFILE_COLUMNS`; what changed is what happens when
one of them moves. A delete committing with the change that caused it cannot be
lost the way an enqueue after commit can, and it needs no ARQ pool in the API
process. The cost is latency — a score reads as not-yet-computed until the cron
runs, which is every minute — and that is the right side to be wrong on: a
missing score is true, and a score computed against a profile the person has
just replaced is not.

**Compared, not provided.** The named set is only half the trap §4.2's wording
sets. M2c's `PATCH /profile` carries every field the form holds, so a person who
opens the page and presses save provides the entire scoring-relevant set and
changes none of it. `profile._clear_scores_if_inputs_moved` snapshots those
columns before the assignments and compares after, so an unedited save costs
nothing.

**A stale result is never silently served.** Results carry the
`ruleset_version` that produced them; the API refuses to return one whose
version is not current, and reports it as not-yet-computed rather than as a
score. A number computed under rules that no longer exist is worse than no
number.

### 4.3 `match_evidence` — the evidence graph

One row per link the score rests on.

```
match_evidence
  id
  match_result_id       FK
  component             role | skill | project | location | freshness | priority
  job_requirement_id    FK, nullable
  job_span_text         the words in the posting
  job_span_field        which of the posting's strings, added at Task 8 — below
  job_char_start        where they are, added at Task 2 — see below
  job_char_end
  user_skill_id         FK, nullable
  user_project_id       FK, nullable
  user_span_text        the words in the user's own confirmed data
  compared              what the exempt components compared, added at Task 2
  proposed_by           rule | embedding
  points                the contribution this row justifies
  created_at
```

The two additions are both from building it. **The offsets live on this row**
rather than being read through `job_requirement_id`, because §7.2's first
equality is stated *at the offsets recorded* and Task 11's embedding proposals
point at spans that are no requirement row at all. **`compared`** is where the
three exempt components put the values they weighed, so §2.1's exemption is from
quoting a span and not from being inspectable.

**`job_span_field` is a third addition, from Task 8**, and it is the column that
made the difference between storing role relevance's evidence and quietly
dropping it. Every other span in this system indexes into
`jobs.description_text` — `job_requirements`, `resume_extractions`, every
eligibility blocker — so the guard below was written checking that one string.
Role relevance is decided on the **title** and cannot be otherwise (§2.1 binds
it to a quoted span, and `role_classification.TextSpan` has carried the field it
read since Task 3). Left as it was, the first real role evidence row would have
been refused for not quoting a string it never claimed to come from, and the
cheapest way to make the insert pass would have been to stop storing the span —
losing the evidence for the component §2.1 cares most about, with a green
test suite. The span therefore travels as four things, not three: text, field,
and both offsets, tied together by `the_job_span_travels_together`.

**This table is the mechanism behind §2's rule**, and it enforces it in two
tiers matching §2.1's distinction:

1. A deferrable constraint trigger asserts that **any** `match_results` row with
   a positive component score has at least one `match_evidence` row for that
   component. This binds all six components.
2. A check constraint asserts that a row whose `component` is `role`, `skill` or
   `project` has **both** `job_span_text` and `user_span_text` non-null. The
   other three components may leave them null, and record the compared values
   instead.

   Built at Task 2 as **two** constraints rather than one, because a test found
   the half the obvious version does not cover. Written as the biconditional
   this paragraph describes — `component IN (role, skill, project)` equals
   *both spans non-null* — it accepts a `freshness` row carrying a user-side
   span and no job span, since both sides then evaluate false. That row quotes
   somebody's own words under a component that makes no claim about them. The
   second constraint says only a person-claim may carry a user-side span. A
   *job*-side span on an exempt component stays legal on purpose: the priority
   component reads a posting's own seniority and quoting the sentence it read is
   more auditable, not less.

A third guard, not in the original design: the job-side span is refused unless
it literally quotes the posting at the offsets it claims, the same trigger
`job_requirements` and `resume_extractions` carry. §7.2 files this under a test,
and it is both — the trigger is the strictly stronger version and cannot see
`user_span_text`, which points into several different tables and stays M3d's.
Rewritten at Task 8 to read the column `job_span_field` names rather than
`description_text` alone; the enum's members and the trigger's `CASE` branches
are asserted equal by a test, because a `CASE` with no matching branch returns
null in Postgres rather than raising, and the row would then be refused with a
message naming the wrong problem.

A score with no evidence cannot be committed, and a claim about the person with
no quoted span on both sides cannot be committed. Both are database errors
rather than code review findings.

`proposed_by` is what makes the semantic layer auditable: it is possible to ask
how many points across the corpus came from an embedding proposal rather than a
vocabulary hit, and that number belongs in M3d's report.

### 4.4 `user_skills.skill_id`

The column `command-center.md` §2.3 deferred. M3's taxonomy makes it real. The
existing `normalized_name` stays — a rename in the taxonomy must not orphan a
confirmed fact.

§2.3 called it an FK and Task 2 built it as a plain string, holding the
taxonomy's canonical name. There is no `skills` table to point at: the taxonomy
is `data/skills.yaml`, a versioned file whose identifier for a skill *is* its
canonical name, and that same string is what `job_requirements.value` stores —
which is what makes a requirement and a confirmed skill joinable. Mirroring the
file into a table would create a second source of truth that can disagree with
it; minting opaque slugs would create a second identifier space to keep in step
with the names the extractor already emits. If the taxonomy ever grows real ids,
they land in this column and the change is a data migration.

**Null is load-bearing.** `add_skill` takes free text on purpose, so a person may
confirm a skill the vocabulary has never heard of; null says *confirmed, and
outside the taxonomy*. Such a skill matches no `job_requirements.value`, and the
score has to say so rather than resolve it to a neighbour — which is the
substring failure M3b Task 11 measured, one table over.

### 4.5 `match_component_assessments` — what each component says for itself

Added at M3c Task 9 as `0018_match_component_assessments`, and not in the
original design. Task 9 is the task where a score first had a **reader**, which
is the point at which a missing column stops being invisible — the same argument
Task 8 made for `assessed_out_of`, one layer up.

One row per component per score, six exactly: `component`, `assessable`, `why`.

§5.1.1 requires the page to name the components that could not be assessed **and
why**. Neither half survives in `match_results` alone:

- **`assessable` cannot be recovered from the points.** §5.1.1's whole content is
  that a component scoring zero and a component the posting said too little to
  assess are different statements, and both store `0`. `assessed_out_of` does not
  resolve it either: the six weights are 20, 30, 20, 10, 10, 10, and several
  subsets sum to the same number, so the denominator names *how much* was
  assessed and can never name *which*.
- **`why` is the only sentence a component ever produces.** The three exempt
  components quote nobody and record their compared values in
  `match_evidence.compared`; an assessable component that scored zero has no
  evidence row at all. Without this text those components reach the page as bare
  numbers, which is I4 one level below the total.

**This is not the `explanation` column §4.2 refused**, and the difference is
where the text comes from rather than how long it is. That column would have held
a narrative assembled *from* `match_evidence`, able to disagree with the rows it
was built from. `why` is the scoring rule's own output, returned by the same call
and from the same inputs as the points beside it — a sibling of the evidence
rows, not a summary of them. The alternative is re-running the scorer at render
time, which is the second-derivation failure `posting_for`'s docstring is written
about and which can disagree with the stored number while looking plausible.

A deferred constraint trigger asserts three things, each a mistake this table
makes possible rather than one already prevented:

1. **Exactly six rows, one per component** — the database's copy of
   `MatchScore.__post_init__`. Five means a component silently has no statement
   and the page renders five of six with nothing looking wrong.
2. **An unassessable component scored nothing.** `ComponentScore.__post_init__`
   refuses this in Python; this is the same refusal for anything reaching the
   table another way.
3. **The denominator agrees with the rows** — `assessed_out_of = 100` exactly
   when every component was assessable. Without it the page can name three
   unassessable components beside a denominator of 100, and the ranked list then
   sorts on a fraction that contradicts the breakdown printed under it.

The third assertion is why `matching_weights.parse_weights` now refuses a weight
of **zero** rather than merely a negative one. It holds only while an
unassessable component necessarily narrows the denominator, which needs every
weight ≥ 1 — and the sum-to-100 assertion does not cover that: `role_relevance:
0` beside `skill_overlap: 50` totals 100 and passes, while removing role
relevance from every score in the corpus. That is the silent removal
`data/matching.yaml`'s own header claims is caught, in the one shape that got
past it.

### 4.6 `match_penalties` — what each subtraction cost, and why

Added at M3c Task 10 as `0019_match_penalties`, and not in the original design.
PROGRESS assigned the call to this task in as many words: *"Task 10 decides
whether that is acceptable or whether §4.2's one-column decision needs
revisiting."*

**§4.2's one column is not revisited.** `match_results.penalty_score` still
stores the sum and `the_total_is_its_parts` still adds it exactly once, for
§4.2's reason: `match_evidence.component` has no penalty member, so a second
*score* column would imply an evidence link that does not exist. What this table
adds is the half §4.2 named and left to somebody else — *what each penalty cost
belongs to the explanation* — which nothing then carried.

The gap was not theoretical. Before this task the page could render `-18` and
nothing else, and invariant I4 lists what a score stores as *"its components,
**its penalties**, its `ruleset_version`, and its evidence"*. Task 10 is the
task where a person reads a score, which is the point at which a missing column
stops being invisible — the same argument §4.5 made at Task 9 and §5.1.2 at
Task 8, now three times in three consecutive tasks.

One row per penalty per score, two exactly: `name`, `points`, `applicable`,
`why`, `compared`.

- **`applicable` is `assessable` one row down.** *There was nothing to ask* — a
  posting naming no required technologies, a profile stating no years — and
  *nothing was missing* both store `points = 0`, and only the flag and the
  sentence tell them apart.
- **`compared` is where §6's *why it may not fit* gets its list.** The
  missing-requirement rule already recorded which required technologies it
  charged for; the page shows that list rather than recomputing one that could
  differ from the number beside it.

A deferred constraint trigger asserts two things:

1. **The parts sum to the column.** Without this the table is a second account
   of the same claim, free to disagree with the number the total was actually
   computed from — which is the failure a split is supposed to avoid, arriving
   by the other door.
2. **Exactly two rows, one per name.** `score_match` always returns both
   penalties; dropping the inapplicable one keeps the arithmetic right and
   removes a sentence a person would have read.

`PenaltyName` is a PG enum rather than free text, and that is what makes the
count an assertion: a typo'd `seniority_missmatch` beside a correct row is two
rows, two names, and a guard that passes.

The page renders both, and prints no number for an inapplicable one — for the
same reason §5.1.1 prints none for an unassessable component.

---

## 5. The score

### 5.1 Two components are deferred, and the rest sum to 100

PRODUCT-SPEC §8.2 lists ten components. Two cannot be built honestly today.

**Company preference (0–5)** — there is no such data. `users` carries
`preferred_roles` and `preferred_locations`; there is no preferred-companies
field. Adding one is cheap and it is five points of stated taste. Deferred, and
named on the page.

**Application urgency (0–5)** — depends on `application_deadline`, which A10
records as rarely present; Datadog's registry note says that board publishes
none at all. If an absent deadline scores zero, every posting from every
employer who does not publish deadlines is penalised five points against the
handful who do. That measures an employer's ATS configuration, not urgency.
Deferred.

What remains needs no normalisation fudge, because the spec's own numbers
already total 100 once those two are gone:

```
role relevance                  0-20
skill overlap                   0-30
project evidence                0-20
location and work mode          0-10
listing freshness               0-10
internship / new-grad priority  0-10
                               ────
                                100
missing requirement penalty     0 to -25
seniority mismatch penalty      0 to -30
```

Weights live in `data/matching.yaml` and are versioned; §4.2 records how that
version is composed with the rule logic's own and stored on every
`match_results` row. Each is **at least 1** as well as summing to 100 — §4.5
records why that second assertion had to be added, and why the first one does not
imply it.

Both deferrals reach the page as `scoring.DEFERRED_COMPONENTS`, carried on the
score's own response with a weight and a reason, in the shape
`search.DEFERRED_FILTERS` already uses for the filters M2 would not fake. Ten
points nobody mentions is an invisible gap; ten points with a reason is a
decision a reader can check against the total.

### 5.1.1 A component that cannot be assessed, and what the total does about it

Decided 2026-08-09, QUESTIONS Q6, after M3c Task 3 measured the size of it: **26
of the 60 labeled postings name no required technology**, and 16 name none of
any kind. Skill overlap and project evidence both read that list, so on 43% of
the corpus half the available score cannot be computed.

A component that answers zero there subtracts 50 points for something about the
employer's prose, which is §5.1's `application_urgency` argument with a bigger
number. So each component returns whether it could be **assessed** alongside its
points, and the two are different statements: zero means this person does not
match, unassessable means the posting does not say enough to ask.

**The total is out of what could be assessed.** A posting naming no technologies
is scored out of 50, the page names the components that could not be assessed
and why, and the ranked list sorts on the fraction. The alternative — always out
of 100, with the gaps shown — systematically ranks terse postings below verbose
ones, and redistributing the missing weight would silently make location and
freshness worth 50 points between them on those postings, which nobody chose.

Awarding the points anyway was never available: §4.3's trigger refuses a
positive component with no evidence row, so the database removed that option
before anyone had to be disciplined about it.

**"The page names the components that could not be assessed and why" needed a
table, and that was found at Task 9.** Which components those are is not
recoverable from `match_results`: a component that scored zero and one nobody
could assess both store `0`, and `assessed_out_of` names how much was assessed
rather than which parts — several subsets of the six weights sum to the same
number. §4.5 is the table, and it carries the reason as well as the fact, because
the reason exists nowhere else.

### 5.1.2 The denominator has to be stored, and that is a column this table does not have yet

Following from §5.1.1 and found while implementing it at Task 5. §4.2 says the
score is precomputed because "a sort needs the value in the database" — and the
ranked list sorts on the *fraction*, so the denominator is part of that value.

It cannot be recomputed from the stored components. A component that scored zero
and a component that could not be assessed both store `0`, and telling those two
apart is the entire content of §5.1.1. `match_results` therefore needs an
`assessed_out_of` column beside `overall_score`. It lands with Task 8's
migration, alongside `match_evidence.job_span_field`, because Task 8 is when a
score first reaches the database — nothing writes these tables before then.

Shipped as `0017_match_score_denominator`, with one constraint the paragraph
above did not anticipate: **`overall_score <= assessed_out_of`**. Each component
is capped at its own weight and only assessable components widen the
denominator, so the inequality is already true of every score the rules can
produce — which is exactly why it is worth asserting. The ranked list divides by
this column, and a fraction above one is a posting sorting ahead of a perfect
match with nothing else on the row looking wrong. It also catches the specific
mistake of a total from one weights version stored beside a denominator from
another.

Existing rows are **deleted rather than backfilled**, in both directions. There
were none — nothing wrote these tables before Task 8 — so the choice cost
nothing, and it is still the right one to have made deliberately: `100` is not
an unknown denominator's default value, it is the assertion that every component
was assessable, which is the claim §5.1.1 exists to stop anybody making by
accident.

`match_results.the_total_is_its_parts` stays exactly as built: `overall_score`
remains the literal sum of the six components and the penalty, floored at zero.
Normalising the stored total to 100 would break that constraint and, worse,
would destroy the distinction the constraint exists to preserve. The fraction is
a division performed by the query, not a number written down.

### 5.1.3 The two penalty curves, decided at Task 5

§5.1 gives the ceilings — -25 and -30 — and nothing else. Both curves were
decided when the rules were written, and both decisions are constrained by
something other than taste.

**Missing requirement counts; it does not divide.** A fraction-based penalty —
*the share of required technologies you failed to meet, times 25* — combines
with skill overlap's *the share you met, times 30* into `55·matched - 25`. That
is arithmetically one component of weight 55 with an offset, so the penalty
would be a weight change wearing a penalty's name, and §8's mutation test could
zero either one and watch the other absorb it. The rule charges a flat 5 points
per unmet required technology instead, capped at the ceiling, because that reads
a fact the fraction cannot: five technologies you cannot evidence are five
things to learn whether the posting lists five of them or fifty.

**It may only read `technology`, and that is §5.2 rather than convenience.** The
other required kinds a posting can carry are `degree`, `graduation_window`,
`years_experience`, `enrollment` and `authorization` — which is exactly the set
of dimensions M3b's gate owns. Charging points for an unmet degree requirement
is the eligibility verdict converted into a number by a side door. A test
asserts that every `RequirementKind` is owned by the gate, by this penalty, or
by the seniority one, so a seventh kind forces the decision rather than
inheriting one.

**Seniority mismatch compares the posting's title band against confirmed years,
and can never block.** `data/matching.yaml` carries a rung per `Seniority`
level; the penalty charges 6 points per year of gap, capped at -30. Two silences
stop it: `unclear` is no rule having decided, and a null `years_experience` is
the person not having told us (I2) — neither resolves to zero, because reading
null as zero charges every silent profile the full penalty against every senior
posting in the corpus.

Scoring it off the *title band* is also what makes it additive rather than a
second copy of the gate's years rule: the gate reads a stated minimum in the
posting's text and can only answer when one is stated, so a "Lead Engineer"
title naming no number is invisible to it and obvious here. And the mechanical
form of "never a blocker" is that `eligibility.Dimension` has no seniority
member at all — this rule has no route to `ineligible` even if somebody wanted
one, which is A13's argument built into the type rather than into a convention.

### 5.2 Eligibility is never part of the number

The five states from §8.3 — `eligible`, `likely_eligible`, `uncertain`,
`likely_ineligible`, `ineligible` — are a PG enum on `match_results`, in their
own column, rendered as their own element. **No eligibility state is ever
converted into points.** That is what "never collapse uncertainty into
confidence" means mechanically: a job can score 82 and be `uncertain`, and the
UI shows both facts without reconciling them.

### 5.3 How a list is ordered without collapsing the state

Default ordering groups by eligibility band, then by score descending within the
band, and **the grouping is visible as section headers** rather than folded into
a number. `uncertain` sorts above `likely_ineligible`.

This is the compromise between two things that both matter: a list where a hard
blocker does not affect position is not usable, and a score that has silently
absorbed a penalty for uncertainty is a lie. Making the grouping a visible
structure satisfies both — the ordering reflects eligibility, and the number
never does.

**Built at Task 10 as `GET /matches`**, its own route rather than a flag on
`/jobs`. The two are different resources: `/jobs` is the corpus, the same rows
for everybody, ordered by recency and deliberately carrying no relevance number;
this is a list of `match_results`, which exist only for a person and only for the
pairs the sweep has reached. Folding them together gives one endpoint whose
shape, ordering and meaning change with a flag, and leaves `not_yet_scored`
nowhere honest to live.

Three decisions the section above did not settle, taken when it was built:

- **All five bands are always returned, empty or not.** §3.3's promise that an
  ineligible posting is shown and dimmed rather than hidden is only checkable if
  the heading is there when there is nothing under it. A band that vanishes when
  empty makes `ineligible` invisible exactly when there is nothing in it to see.
- **The sort is on the fraction, not on `overall_score`** (§5.1.1). 40 out of 50
  beats 45 out of 100, and `ORDER BY overall_score DESC` — the obvious clause —
  puts them the other way round while both numbers on the page stay true. In
  SQL that is `NULLIF(assessed_out_of, 0)`, which also hands the unassessable
  pairs the null they are entitled to instead of raising.

  **Amended at M3d Task 6: the sort is the fraction *weighted by coverage*.**
  The paragraph above is right that raw totals are not comparable and wrong to
  stop there — a fraction of 20 assessable points is not comparable to a fraction
  of 80 either, which is what the M3c review named at §2.10 and declined to fix
  for want of a way to choose. The rated corpus is that way. Measured over
  30 postings against the profile in `ratings.yaml`:

  | Ordering | NDCG@10 | NDCG@30 | P@5 |
  |---|---|---|---|
  | fraction (as shipped in M3c) | 0.811 | 0.926 | 0.600 |
  | raw `overall_score` | 0.777 | 0.902 | 0.800 |
  | fraction × shrink to corpus mean | 0.811 | 0.924 | 0.600 |
  | **fraction × √(assessed/100)** | **0.817** | **0.931** | **0.800** |
  | fraction, ≥50 assessed first | 0.822 | 0.934 | 0.800 |

  Three things decided it, and the size of the win was not one of them — +0.006
  NDCG@10 over 30 items is well inside what one swap moves.

  1. **It is never worse.** Leave-one-out across all 30 folds: better in 28,
     tied in 2, worse in none.
  2. **Both endpoints are worse than the middle.** Sweeping the exponent,
     `p=0` (the plain fraction) gives 0.811 and `p=1` (which is algebraically
     raw score) gives 0.777, while `p=0.5` and `p=0.75` both give 0.817. No
     weighting under-corrects and full weighting over-corrects.
  3. **The mechanism is the one §2.10 describes**, so the fix is not fitted to
     the corpus: a posting assessed on a fifth of the score has a fifth of the
     evidence, and discounting by coverage is what "these denominators are not
     comparable" means arithmetically.

  The bucketed variant scores marginally higher and was **not** taken: its
  threshold of 50 is a magic number with no support in this data, and it would
  need its own entry in `matching.yaml` and its own mutation test to be
  defensible. √ has no free parameter. **The exponent is not pinned harder than
  the data supports** — 0.5 and 0.75 are indistinguishable here, and 0.5 is the
  one with an ordinary name.

  What this cost is legibility, and it is disclosed rather than absorbed. Every
  row still prints its `fraction` — the honest *of what could be assessed*
  figure, unchanged on the wire — so a reader can see 17% ranked above 30%. The
  response therefore carries `ordering: "coverage_weighted_fraction"`, in the
  shape `unassessed_sort_last` already uses, because without it a reader's only
  available conclusion is that the list is broken.

  Concretely, on the rated corpus: an Employee Experience Specialist
  (Receptionist) rated `poor` ranked **fifth** under the plain fraction, above
  four postings rated `good`. It now ranks sixth. That single swap is the whole
  of the measured improvement, and it is the swap §2.10 predicted.
- **A null fraction sorts last inside its band, and the response says so.** Such
  a pair keeps its band, because the eligibility verdict on it is real; what it
  has nothing to say about is the ordering. Last rather than first is a decision
  rather than an accident of `NULLS FIRST` being Postgres' default for `DESC`,
  and `unassessed_sort_last` is on the wire so a client cannot quietly choose
  otherwise. The row renders as *nothing to assess*, never as `0%`.

**`not_yet_scored` is part of the response.** A ranked list covering 12 of 31
open postings renders identically to one covering all 31, and nothing in the rows
themselves can tell a reader which they are looking at. It counts stale-version
rows too: §4.2 refuses to serve one, and *refused* and *never computed* are the
same thing to a list — the sweep will fix both.

`BAND_ORDER` is written out in `domain/matching.py` rather than taken from
`EligibilityState`'s declaration order, which happens to agree today. The enum's
order is a fact about a Python file; the band order is a product decision, and
`uncertain` above `likely_ineligible` is the one line of it worth stating on its
own — an open question is not a soft no, and sorting them the other way round
buries the postings a person could resolve by filling in one profile field
underneath the ones they cannot resolve at all.

---

## 6. Explanation

§8.5 requires nine elements. **Six are computed in M3c; three are named rather
than faked** — the count moved at Task 10, which is when the panel was built and
the resume recommendation turned out to need a design of its own (below).

| Element | M3 |
|---|---|
| Why the role fits | Evidence rows with positive points, quoted both sides |
| Why it may not fit | Required requirements with no evidence row |
| Hard blockers | The eligibility gate's failing rules, each quoting the sentence |
| Soft gaps | `preferred` requirements with no evidence |
| Relevant project evidence | `match_evidence` rows with a `user_project_id` |
| Recommended resume | **Not built.** Which stored resume best covers the required set. The column exists, nothing writes it, and doing it from `resume_extractions` would be a claim about a person built on proposals (I2) — see below |
| Confidence | The eligibility state. **Not a number** |
| Recommended emphasis | **Not built.** Advice about how to present oneself, which this system has no basis for |
| Suggested next action | **Not built.** M2d's queue owns next actions and computes them from application state |

No explanation text is generated. Every line is assembled from evidence rows and
quotes stored strings. There is no template that can produce a sentence about a
skill with no row behind it — which is exactly what M3d's hallucination check
asserts.

**One sentence per component is stored rather than assembled**, and §4.5 records
the argument: it is the rule's own output, produced by the same call as the points
it explains, and it is the only text a component that scored nothing ever has.
That is a different thing from the narrative §4.2 refused to store, which would
have been assembled *from* the evidence rows and could disagree with them.

**One of the seven is not computed, and Task 9 is where that became visible**
rather than where it was decided. `match_results.resume_id` is the *Recommended
resume* row above and nothing writes it — it is null on every stored score.

**Task 10 built the panel and did not take the resume recommendation**, which is
a decision rather than a slip, and the reason is I2. *Which stored resume best
covers the required set* needs a per-resume set of skills, and this system has
none: `user_skills` is confirmed and belongs to the **person**, not to a
document, while `resume_extractions` is per-resume and holds **proposals** —
which §7.2 forbids any user-side span from quoting. Recommending a resume from
proposals would be a claim about somebody's qualifications derived from text
nobody has confirmed. Doing it honestly needs either a confirmation step that
attributes a confirmed skill to the resume it came from, or an explicit
"this resume mentions" reading that is never called evidence. Either is its own
small design and neither is a rider on the explanation panel.

So the panel **names it beside the two that are not built** — `MatchPanel`'s
`NOT_BUILT` list, printed on the page rather than left in a comment — and
PROGRESS carries it under "Not real yet." It is not one of the seven computed
elements and must not be described as one.

**The other six were assembled at Task 10.** *Why it may not fit* and *soft
gaps* are one computation read at two necessities, and it is a set difference
over the stored evidence rows — `matching.unmet_requirements`, served as
`JobDetailOut.unmet_requirements` and **null rather than empty when there is no
score**, because an empty list there reads as *you meet everything*: a claim
about a person computed from no evidence at all, which is the failure
`eligibility`'s own null exists to prevent one field up.

**A set difference is only honest over a set the other side can populate**, and
Task 12 found two ways it was not, both by looking at the page rather than at a
test:

- The difference ran over *every* non-`mentioned` requirement, and the evidence
  graph only ever contains technologies — so every degree, years, enrollment and
  graduation ask came back unanswered, and the page printed a bare **"2"** under
  *what it asks for that you have nothing on file for*. Those dimensions belong
  to the gate directly above. Fixed by filtering to
  `scoring.EVIDENCE_BEARING_REQUIREMENT_KINDS`.
- No component emitted a row for a `preferred` technology, so **every**
  nice-to-have was listed as one you have nothing on file for — including three
  the same page quoted as confirmed, eight lines higher. Fixed by having skill
  overlap and project evidence emit **zero-point** evidence rows for confirmed
  nice-to-haves, which is what `score_skill_overlap`'s docstring had claimed
  since Task 3 without any code behind it. No total moved; `RULESET_LOGIC_VERSION`
  went to `2` anyway, because the evidence graph is part of the score under I4
  and the golden test refused to regenerate without it.

The rule this leaves behind: **a gap is only ever something an evidence row could
have answered.** Anything else is an absence of information being rendered as a
statement about a person.

I5 is unchanged and worth restating here because §8.5 sits next to it: nothing
rewrites a resume, nothing tailors one, nothing submits anything.

---

## 7. Evaluation

### 7.1 What M3d measures, in CI

| Metric | Against |
|---|---|
| Eligibility precision **and recall** | The answer key, per state |
| Skill-extraction precision and recall | `required_tech` vs `mentioned_not_required` |
| `required` vs `preferred` classification accuracy | The answer key |
| Hallucination rate | Must be exactly zero — see below |
| Ranking stability | Identical inputs + identical `ruleset_version` → byte-identical output, twice |
| Embedding-proposed share | What fraction of awarded points came from `proposed_by = embedding` |

### 7.2 The hallucination check is an equality, not a rate

Two assertions, both of which must hold for every row in the corpus:

1. Every `match_evidence.job_span_text` is a **literal substring** of the job's
   `description_text`, at the offsets recorded.
2. Every `match_evidence.user_span_text` is a literal substring of a *confirmed*
   user record — never of `resume_extractions`, which holds proposals.

Neither is a percentage to improve. A single violation is a failing test.

**Where each is actually enforced, measured at M3c Task 12 by attacking the
database rather than by reasoning about it.** The two assertions do not have the
same teeth and it matters which:

| | Enforced by |
|---|---|
| A job span that does not match its offsets | A trigger, on INSERT **and** on UPDATE. Probed: both refused |
| A user span quoting something unconfirmed | `check_match_results` in `verify.py`, and the unit suite. Nothing in DDL |
| `proposed_by = 'embedding'` (ADR 0018) | `check_match_results`, three unit tests. **The database accepts such a row** |

**M3d Task 4 closed the CI half of the middle row.** The table above was written
at M3c Task 12 and was accurate: the user-span assertion ran only in `verify.py`,
which needs a live stack under `make acceptance` and which reads only rows it
rescored itself. A CI run asserted it nowhere.
`test_every_user_span_quotes_something_the_person_confirmed` now checks it over
the whole golden corpus — 153 postings × 4 profiles — with no database, so it
runs on every push. The DDL column of that row is still empty and still correct:
no trigger can see it, because `user_span_text` points into several different
tables.

The check found nothing wrong with the scorer and did find something wrong with
its own author's model of it. The first draft allowed a user span to quote a
confirmed skill or a project bullet, and went red naming 53 rows — all of them
role relevance, whose user-side span is the person's `preferred_roles` string.
That is confirmed profile data and belongs in the set; the point worth keeping is
that a corpus-wide equality is also a test of whether the person writing it knows
what the system stores.

**The embedding-proposed share is published rather than only asserted.** §7.1's
last row asks for a fraction, and `test_the_scorer_emits_no_evidence_row_an_
embedding_proposed` answers a different question — whether the *set* of sources
is `{rule}`. That set assertion is the stronger tripwire and has to be deleted
the day a proposal path ships; a share keeps reporting after that day. Measured
over the golden corpus: **0 of 9,417 awarded points.**

`check_match_results` runs last in `verify.py`, after every check that edits a
profile column or a confirmed skill — each of which deletes every score — so it
reads only rows it rescored itself. It therefore asserts *the scorer produces no
such row over the whole seeded corpus*, and cannot catch one inserted by hand.
That limit is stated in its docstring rather than implied.

### 7.3 What M3 does not measure, stated plainly

**Top-k relevance.** §8.6 asks for it and M3 will not have it. Relevance is
irreducibly personal — whether a role is a *good* role for someone is not a
property of the posting, so it cannot come from §3.1's answer key by
construction. Measuring it needs a second labeling pass in which the user rates
~30 postings good / acceptable / poor.

That pass is roughly twenty minutes and it is **in M3d's scope**, gated on the
human's availability. If it does not happen, M3 ships with ranking *stability*
measured and ranking *quality* unmeasured, and PROGRESS says so under "Not real
yet" rather than reporting a metric computed against labels the system wrote for
itself.

**The worksheet exists as of M3c Task 1** — `docs/labeling/relevance-worksheet.md`,
generated from the same corpus §3.1's answer key uses, filled in at
`services/api/tests/fixtures/relevance/ratings.yaml`. It carries the profile the
ratings were made against, so M3d grades a pure function against a committed
file rather than against whatever the database holds on the day. QUESTIONS Q5.

---

## 8. Testing

Beyond the evaluation suite:

- **Every eligibility rule has a fixture**, per CLAUDE.md §7. The answer key is
  the fixture set; a rule with no posting exercising it is a rule with no test.
- **Mutation testing on the gate.** Every rule is shown able to fail by
  neutering it and watching a named test go red. This project has now found
  three tests that could not fail; the gate is where that would be most
  expensive.
- **Mutation testing on the score's numbers**, built at Task 7 and wider than
  planned. Not only the six weights: the two penalty ceilings and all eleven
  thresholds move a score too, and a decorative threshold is exactly as
  invisible as a decorative weight. Nineteen mutations, each asserted to move
  at least one of the 612 golden scores.

  It found five dead mutations on first run — the lower rungs of the seniority
  ladder, because `gap` is `max(0, implied - years)` and a rung only bites
  somebody below it, and no fixture profile stated a number small enough. The
  fix was a fourth profile at `years_experience: 0`, which was worth more than
  the kills: somebody with no professional experience yet is this product's
  user, and the fixture set had nobody in it.
- **The span trigger is proven able to fail**, by shifting an offset by one
  character and catching the database error.
- **Both evidence guards are proven able to fail** — one by committing a
  positive component score with no evidence row, the other by committing a
  `skill` evidence row with a null `user_span_text`.
- **Enum parity.** Every new enum crossing the Python/TypeScript boundary goes
  into `test_enum_parity.py`, which is the only test in the repo that reads both
  sides at once. Two of the last four milestones found a hand-transcribed enum
  defect there, so the count is expected to be checked rather than trusted.
- **A determinism test that actually reruns.** Same fixtures, two full runs,
  byte-identical `match_results` and `match_evidence`. Embeddings are local and
  deterministic (A5), so this is a real assertion rather than an aspiration.
  Built at Task 6 — and it rebuilds the corpus, re-extracts every requirement
  and rescores every pair on the second run, because comparing a cached string
  against itself proves nothing.
- **An anti-vacuity test on the corpus, not only on the rules.** A scorer
  returning 50 for everything satisfies every line above it. Task 6 asserts the
  corpus reaches several distinct scores, several distinct *denominators*, and
  that every one of the six components earns points somewhere — the last of
  which is what stops Task 7's mutation test from "proving" a component
  load-bearing against a corpus that could never tell.

---

## 9. Deliberately not built

Named here so nothing in M3 is quietly assumed to be coming.

- **Any LLM.** §8.1 permits one to assist; §2 of this document gives it nothing
  to do that would not violate the span rule. No ADR, no dependency, no key.
- **Any embedding proposal path.** §2 permits one; Task 11 measured what it
  would say and ADR 0018 declines it. `EvidenceSource.EMBEDDING` remains on the
  wire and unreachable, deliberately — see the ADR's consequences.
- **`demonstrated_by:` edges in `data/skills.yaml`** — the constructive successor
  ADR 0018 recommends. Would move scores across the corpus, so it needs a
  `ruleset_version` bump and does not belong in M3c's last task.
- **Resume rewriting, tailoring, or generation.** I5.
- **Recommended emphasis, suggested next action, and the recommended resume** — §6.
- **Company preference and application urgency** — §5.1.
- **Top-k relevance**, unless the second labeling pass happens — §7.3.
- **Coordinates, boroughs, neighborhoods.** M4. The location component scores
  against `job_locations.city` and `remote_policy`, which is what the source
  actually said.
- **Non-ATS employers**, including all of big tech — §3.6.
- **Gmail-derived evidence.** M7.
