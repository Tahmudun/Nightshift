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

### 2.1 The span rule binds three components, and the reason is not arbitrary

The rule above applies to **role relevance, skill overlap and project
evidence** — the three components that make a claim about *the person*. Those
are the claims I2 exists to govern, and each must trace to two quotable strings.

**Location, freshness and internship priority make no claim about the person.**
Freshness is arithmetic on `last_seen_at`; location compares
`job_locations.city` and `remote_policy` against a preference the user typed;
priority reads the posting's own seniority. There is no span to quote on the
user's side because there is no assertion about their qualifications being made.

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

**`penalty_score` is one column rather than two.** §5.1 keeps two penalties;
this stores their sum. The evidence trigger binds the six positive components
(§4.3's enum has no penalty member), so a split column would imply an evidence
link that does not exist. What each penalty cost belongs to the explanation.

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

**Precomputed, not computed on read.** The daily queue has to sort thousands of
jobs by score, and a sort needs the value in the database. Recomputed on: a new
or changed job, any profile change, and a ruleset version bump. An ARQ task,
inside the existing worker module.

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
it literally quotes `jobs.description_text` at the offsets it claims, the same
trigger `job_requirements` and `resume_extractions` carry. §7.2 files this under
a test, and it is both — the trigger is the strictly stronger version and cannot
see `user_span_text`, which points into several different tables and stays M3d's.

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
`match_results` row.

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

---

## 6. Explanation

§8.5 requires nine elements. Seven are computed in M3c; two are not built and
are named rather than faked.

| Element | M3 |
|---|---|
| Why the role fits | Evidence rows with positive points, quoted both sides |
| Why it may not fit | Required requirements with no evidence row |
| Hard blockers | The eligibility gate's failing rules, each quoting the sentence |
| Soft gaps | `preferred` requirements with no evidence |
| Relevant project evidence | `match_evidence` rows with a `user_project_id` |
| Recommended resume | Which stored resume best covers the required set |
| Confidence | The eligibility state. **Not a number** |
| Recommended emphasis | **Not built.** Advice about how to present oneself, which this system has no basis for |
| Suggested next action | **Not built.** M2d's queue owns next actions and computes them from application state |

No explanation text is generated. Every line is assembled from evidence rows and
quotes stored strings. There is no template that can produce a sentence about a
skill with no row behind it — which is exactly what M3d's hallucination check
asserts.

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

---

## 9. Deliberately not built

Named here so nothing in M3 is quietly assumed to be coming.

- **Any LLM.** §8.1 permits one to assist; §2 of this document gives it nothing
  to do that would not violate the span rule. No ADR, no dependency, no key.
- **Resume rewriting, tailoring, or generation.** I5.
- **Recommended emphasis and suggested next action** — §6.
- **Company preference and application urgency** — §5.1.
- **Top-k relevance**, unless the second labeling pass happens — §7.3.
- **Coordinates, boroughs, neighborhoods.** M4. The location component scores
  against `job_locations.city` and `remote_policy`, which is what the source
  actually said.
- **Non-ATS employers**, including all of big tech — §3.6.
- **Gmail-derived evidence.** M7.
