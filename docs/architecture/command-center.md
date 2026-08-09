# The command center — the M2 design

- **Status:** accepted
- **Date:** 2026-08-03
- **Milestone:** M2 (four slices, M2a–M2d)
- **Implements:** PRODUCT-SPEC §6.1–6.4, §6.11–6.12, §10, §12.1–12.3
- **Constrained by:** invariants I2, I4, I5, I7; AMENDMENTS A3, A9, A10

M1 built a spine that knows what jobs exist. M2 makes the product useful to one
person before any of it is three-dimensional. The acceptance criterion is a
sentence from `CLAUDE.md` §6: *full discover→save→apply→track loop works with
zero 3D.*

Read this before writing any M2 plan. It decides the shapes; the plans sequence
them.

---

## 1. What M2 delivers, and in what order

Four slices, each a PR. The order is deliberate and was chosen by the human on
2026-08-03 over the spec's own first-run ordering.

| Slice | Delivers |
|---|---|
| **M2a** | Job search, filters, job detail page, company detail page |
| **M2b** | Save, apply, track, notes, stage history, archive/restore |
| **M2c** | Profile, resume upload/paste, extraction, the confirmation screen |
| **M2d** | Daily queue and dashboard |

**The milestone's headline criterion is earned at the end of M2b**, not at the
end of M2. Browsing and tracking need no profile and no resume — the seeded
`dev_user` is a sufficient owner for an application row. Resume extraction is
the slice with the most invariant risk and the least contribution to the loop,
so it goes third, where running long costs the least.

`discovered` as a stage is reserved for M3. In M2 nothing enters your pipeline
without you clicking it, so every application starts at `saved`.

---

## 2. Seven tables, and one structural idea

### 2.1 Saving and tracking are the same object

PRODUCT-SPEC §10.1 lists `saved` as one of ten stages. There is therefore **no
`saved_jobs` table**. Clicking Save creates an `applications` row at stage
`saved`. One row, one history, and no migration on the day a saved job becomes
a real application.

### 2.2 Pending facts live in a different table from confirmed facts

This is the whole of invariant I2's enforcement, and it is structural rather
than procedural.

```
resume_extractions          users / user_skills / user_projects
(proposed, with a span)  →  (confirmed, by an explicit click)
```

`resume_extractions` holds *"this file appears to say you graduate May 2027, at
characters 214–229"*. `users.graduation_date` holds only what a human confirmed.
Promotion is a write across two tables, so no bug in the extractor can produce a
confirmed fact — the extractor cannot reach those tables at all.

This is the same shape as `source_job_records → jobs`, which has held for four
milestones, and it is why the confirmation step is cheap to prove rather than a
matter of reviewing every write path.

### 2.3 The tables

| Table | Purpose | Notes |
|---|---|---|
| `users` *(grown)* | Confirmed profile | `graduation_date`, `degree`, `school`, `work_authorization`, `home_location_text`, `remote_preference`, `minimum_salary`. `preferred_roles` and `preferred_locations` are `JSONB` arrays of strings — nothing filters on them in M2, so a table would be shape without a use |
| `user_skills` | One row per **confirmed** skill | §6.2 fields. `skill_id` FK arrives with M3's taxonomy; M2 stores the name |
| `user_projects` | §6.3 | `evidence` is the text M3's evidence graph will cite |
| `resumes` | §6.4 | `parsed_text` is the extraction's substrate; `content_hash` makes re-upload idempotent |
| `resume_extractions` | Proposals awaiting confirmation | Not in the spec. Justified by I2 — see §2.2 |
| `applications` | §6.11 | One per (user, job). `selected_resume_id` nullable until M2c exists |
| `application_events` | §6.12, append-only | Enforced by trigger, not convention |

Every one of these carries a real `user_id` foreign key and every query filters
on it, per A3, even though there is one user until M5.

### 2.4 Append-only is a trigger

`CLAUDE.md` §7 requires it and M2 is the first table it applies to. A Postgres
trigger raises on `UPDATE` and `DELETE` against `application_events`. The test
that proves it attempts an update and asserts the raised error, so the guard is
demonstrated able to fire rather than assumed present.

Consequence: **notes are events, not a column.** `applications.notes` from
§6.11 is deliberately not implemented as mutable text. A note is a `note_added`
event, which means note history is free and cannot be quietly rewritten.

---

## 3. Stage transitions: classify, do not block

PRODUCT-SPEC §10.2 requires that the user can always *"set stage"* and
*"correct stage"*. A state machine that rejects `saved → offer` would violate
that, and the jump is real — referrals happen. So the machine does not block.

Each transition is **classified and recorded**:

| Class | Meaning |
|---|---|
| `advance` | Forward along the default order |
| `correction` | Backward, or a jump that skips stages |
| `reopen` | Out of a terminal stage (`rejected`, `withdrawn`, `closed`) |

The classification lands on the event. History stays honest without the product
telling its user they are wrong about their own job search.

**What the machine does enforce** is invariant I5: a stage change requires an
actor of `user`. Nothing in the system may set a stage. When a tracked job's
listing closes, ingestion writes a `listing_closed` **event** — a fact about the
world — and the UI surfaces a prompt. **The stage does not move.** Suggest,
surface, confirm.

The fixture suite covers every transition in the ten-stage grid for its
classification, plus the rejection of a system-actor stage change.

---

## 4. M2a — search, filters, detail pages

### 4.1 What `/jobs` already has

`limit`, `offset`, `status`, `company`, `location_confidence`
(`api/routes/jobs.py:103`).

### 4.2 What M2a adds

Free text over title and `description_text`, employment type, remote policy,
date first seen, minimum salary, source, and **city**.

Text search uses a generated `tsvector` column with a GIN index — Postgres's
own, no new dependency.

### 4.3 What is deferred, and shown as deferred

The filter panel renders these disabled with the reason visible, rather than
omitting them — the precedent is M1 criterion 12, where `/analyze/coverage`
names what it does not cover. Absence of a feature is stated, not hidden.

| Filter | Blocked on | Reason |
|---|---|---|
| Match score | M3 | No score exists. I4 forbids showing one without a breakdown |
| Eligibility | M3 | Requires the deterministic eligibility gate |
| ~~Skill~~ | ~~M3~~ | **Shipped at M3b Task 11.** The stated reason above went stale at M2c when `skills.yaml` landed, and nobody re-read this row for a milestone. Its replacement — recall of 0.459 — went stale at M3a.1. It ships at 0.861 with that figure stated on the panel and `excluded_no_requirements` counting what it could not match |
| ~~Internship season~~ | ~~M3~~ | **Shipped at M3b Task 11**, as *two* columns rather than one: 2 of the corpus's 19 internships state a year and no season, so a single `summer_2027` value could hold them only by inventing the season |
| **Borough / neighborhood** | **M4** | **See below** |

**Two of the five rows above went stale before anyone noticed, and both in the
same direction**: the thing they were waiting on landed and the row kept saying
it had not. That is the failure mode this whole section exists to prevent one
layer up, so the deferral list in `domain/search.py` is now guarded by
`test_no_deferred_filter_blames_something_that_now_exists`, which fails when a
reason names an artefact the repository contains.

**Borough and neighborhood cannot be built in M2, and this is an I1 matter, not
a scheduling one.** `job_locations` stores `city`, `state`, `country` and has no
borough column, because a posting that says `"New York, NY"` does not say which
borough it is in. Deriving one would be interpolation — precisely what I1
forbids. Boroughs arrive with the geocoder at M4. A **city** filter is honest
today, because it matches what the source actually wrote.

### 4.4 The <200ms criterion

A wall-clock assertion in CI is flaky and would eventually be deleted. The
committed test asserts the **query plan**: no sequential scan on `jobs` for any
supported filter combination. That is deterministic, and it fails the day
someone adds a filter without an index.

The measured millisecond figure is recorded in `docs/PROGRESS.md` as evidence,
the way live poll timings already are. Both are needed: the plan test prevents
regression, the measurement earns the criterion.

### 4.5 Detail pages

§12.3's list, with two categories of honest absence:

- **Not yet computed** — match score, eligibility, breakdown, project evidence,
  recommended resume, similar jobs. M3 owns them.
- **Not provided by source** — salary, deadline, posted date (A10). Stated
  explicitly rather than hidden, because absence of data is data.

`first_seen_at` is never labelled "posted" (A10).

---

## 5. M2b — the loop

Save, set stage, add notes, record dates (`next_action_at`, interview dates,
follow-ups), select a resume once M2c exists, record the application URL,
archive and restore. Every change writes an event.

**Apply never applies.** Invariant I5: the control records that *you* applied
and opens the source posting in a new tab. There is no code path in this
project that submits an application, and there is a test asserting the API
exposes no such route.

The evidence for the milestone is a seeded browser test that walks
discover → save → apply → track end to end. That test *is* the acceptance
criterion, not a proxy for it.

---

## 6. M2c — profile and resume

### 6.1 The extractor proposes only what it can point at

Decided by the human on 2026-08-03 over both a no-parsing form and an LLM.
Rules-based, deterministic, `$0`, no API key (A9).

Every proposal carries `char_start` and `char_end` into `resumes.parsed_text`,
so the confirmation screen highlights the literal words it came from. A
proposal with no span is unrepresentable.

| Proposed | Only when |
|---|---|
| Skill | The term matches a committed vocabulary exactly or by alias. Never free text |
| Graduation date | An explicit date pattern inside an Education section, adjacent to a degree keyword |
| Degree / school | Same section, explicit keyword match |
| Project | A heading with bullet text beneath it, both captured as evidence |

Anything else is **not proposed**. Recall is traded for precision on purpose:
`"5 years of experience"` and `"passionate self-starter"` yield nothing.

`data/skills.yaml` is seeded here with a starter vocabulary and a version field.
M3 grows it into the full taxonomy; the version field means that is a data
change, not a migration.

### 6.2 Failure is stated, never filled

- A corrupt or unreadable file fails **whole**. There is no partial parse, and
  the error offers paste as the alternative.
- An extraction that proves nothing says *"nothing could be proven from this
  file"* and hands over the manual form. It never populates a field to look
  successful. That behaviour is I7 in miniature.

### 6.3 Test resumes are synthetic

Committed fixture resumes describe invented people. Real uploads are gitignored
and never leave the machine. This is the only genuinely personal data M2 holds,
and §13 applies to it.

---

## 7. M2d — the daily queue

Four rows are computable honestly without M3. The thresholds were decided by
the human on 2026-08-04 and are named constants, not literals scattered through
queries:

| Row | Derived from | Threshold |
|---|---|---|
| Follow up | `applications.next_action_at` due or past, **or** applied with no user activity since | 7 days |
| Interviews approaching | `interview_scheduled` events whose `occurred_at` is in the future | next 14 days |
| Stale saved jobs | Still at `saved`, no user activity since | 21 days |
| Closed while saved | A tracked job whose listing is *currently* `closed` | — |

Four more require the matching engine and are **named on the page with their
reason**: best new internships, high-match roles closing soon, resume mismatch
warnings, and the single recommended action. This is the same move
`/analyze/coverage` makes for source coverage, and it has a passing test
asserting the section is visible without expanding anything.

Building them against an invented score would violate I4. Rendering them as
empty placeholders would violate I7 and §27.7. Naming them is the third option
and the correct one.

### 7.1 Assessments due — folded, not dropped

PRODUCT-SPEC §10.4 lists **"Assessments due"** as a ninth row. Earlier drafts of
this section omitted it silently, which is the failure mode this document exists
to prevent. It is folded into **Follow up** by the human's decision on
2026-08-04, and the reason is that the data to separate it does not exist:
`applications` carries `next_action_at` and nothing else date-shaped, so an
application sitting in the `assessment` stage with a date set already surfaces
in Follow up. Splitting it into its own row would query the same column twice
and show an empty section to almost every user.

Adding an `assessment_due_at` column is the alternative and was rejected as
shape with no use — a migration, a form field and a test suite for a row one
user may never fill in. If a real assessment deadline ever needs to differ from
the next action, that column is the change to make.

### 7.2 Three rules that decide whether the queue tells the truth

**"No activity since" means no activity *by the user*.** `application_events`
records system events too, and `record_listing_closed` writes one. If staleness
counted every event, a listing going closed would make the application look
freshly touched and quietly remove it from the queue that exists to surface it.
Both silence queries therefore filter `actor = 'user'`. This is the load-bearing
filter on the page and it is mutation-checked.

**Archived applications are excluded from every row.** M2b already shipped this
bug from the other direction — an archived application rendered as unsaved and
saving it changed nothing.

**"Closed while saved" reads the job's current status, not the `listing_closed`
event.** A listing can close and reopen; §7.4's state machine allows it. Reading
the event would keep a reopened role in the queue permanently, telling the user
to act on something that stopped being true.

### 7.3 The queue writes nothing

No dismiss, no snooze, no "mark as done". Every row is a link to the application
it is about, and acting on it happens there. I5 governs: the queue suggests and
the user acts. Dismissal is also new state — a table, a route, and a decision
about whether a dismissed row returns tomorrow — and none of that is needed to
make the four rows useful.

Each row set is capped at 20 with an honest "and N more" count. Unbounded render
work is `CLAUDE.md` §8's anti-pattern and it applies to a list as much as to a
map.

An empty queue says so, and says that an empty queue is a normal state rather
than a failure. A blank panel and a permanent spinner both read as broken.

---

## 8. Testing

| Risk | Guard |
|---|---|
| A proposal becomes a confirmed fact without a click | Separate tables (§2.2), plus a structural test that no module outside the confirm handler writes `user_skills` / `user_projects` / the profile columns |
| History rewritten | Trigger, plus a test expecting the raised error |
| A stage change with a system actor | Type-level actor requirement, plus a fixture case |
| Transition misclassified | Fixture suite over the ten-stage grid |
| Extraction drifts | Same file twice → byte-identical proposals, as with adapter fixtures |
| Search degrades | Query-plan assertion (§4.4) |
| The loop breaks | Seeded browser test, end to end |

Mutation-check the load-bearing ones, per the practice from M1a–M1d: a guard
that has never been shown to fail is not yet evidence.

---

## 9. Deliberately not built

- **Auth.** A3: not until M5. `dev_user` owns everything, every query still
  filters on `user_id`.
- **Gmail.** M7, and A8 constrains it.
- **Matching, scores, eligibility, the skill taxonomy proper.** M3.
- **Boroughs, neighborhoods, any coordinate.** M4, with the geocoder.
- **Anything 3D.** M4, and starting it early is the first item in `CLAUDE.md` §8.
- **Custom substages.** §10.1 says "later"; ten stages are enough for one user.
