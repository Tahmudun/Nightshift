# ADR 0019 — A score is stored and withdrawn; the verdict beside it is not

- **Status:** accepted
- **Date:** 2026-08-10
- **Milestone:** M3c
- **Relates to:** ADR 0017 (the eligibility verdict is computed on read), ADR 0018 (the embedding proposal path is measured and not shipped), `matching.md` §4.2, §5.1.1, §5.1.2, §5.3, §7.2, invariants I2 and I4

## Context

One milestone ago, ADR 0017 decided that an eligibility verdict is **computed on
read and stored nowhere**, and gave a reason that had nothing to do with
performance: a stored verdict is stale the moment somebody edits their graduation
year, and it is stale in the direction A13 calls the worst output this engine can
produce.

M3c puts a **score** on the same page, computed from an overlapping set of
profile columns, and stores it. That looks like a reversal, and this ADR exists
because the next person to read the two documents together will ask.

Three things had to be settled: why the score is stored when the verdict beside
it is not, what happens to a stored score when its inputs move, and what a
denominator that varies per posting does to a ranked list.

## Decision

### 1. The score is stored, and the reason is not caching

A verdict is a branch over five rules reading six columns. A score is six
components, two penalties, up to a dozen evidence rows with spans on both sides,
six component assessments with their own sentences, and a denominator — and I4
requires **all of it** to be recoverable beside the number, permanently.

Computing that on read would mean the breakdown a person reads is derived a
second time from inputs that may have moved since, and a second derivation can
disagree with the first while looking perfectly reasonable. Storing it makes the
row the single account of itself: every number the page prints is read off the
row that carries it, and the components sum to the total because they *are* the
total's parts rather than a re-execution of the rules that produced it.

There is a second reason, and it is §7.1's: **ranking stability is a claim about
a stored artefact.** "Identical inputs and identical `ruleset_version` produce
identical output" is not checkable against something recomputed per request, and
comparing a version bump against what preceded it needs the row that preceded it
to still exist.

### 2. When an input moves, the score is deleted — never refreshed in place, never left

A stored score whose inputs have changed has exactly three possible fates, and
two of them are wrong:

| | |
|---|---|
| **Left as it is** | The page shows a number computed against a profile the person has replaced. This is ADR 0017's objection, unmitigated. |
| **Refreshed in place** | The window between the edit and the refresh serves a stale number *as a current one*, and nothing on the row says which it is. |
| **Deleted** | The pair reads as not-yet-computed until the sweep reaches it. |

Deletion is the only one whose intermediate state is true. "Not scored yet" is a
fact about this system, and the panel says so in those words — *"Scores are
computed in the background and refresh whenever the posting or your profile
changes, so this fills in on its own — it is not a zero."*

The deletion happens **inside the transaction that caused it**. `PATCH /profile`
compares the nine columns in `matching.SCORING_RELEVANT_PROFILE_COLUMNS` before
and after, and deletes this person's scores when any of them actually moved. A
job's description, its requirements, a confirmed skill and a confirmed project
are watched by database triggers written at Task 2, so those need no application
code at all. Neither path can be lost the way an enqueue after commit can.

**Compared rather than merely provided**, which is the difference between a rule
and a retry storm: a form submitted unedited provides fifteen columns and moves
none of them, so nothing is deleted and nothing is recomputed. Editing a display
name is free.

### 3. Recomputation is a sweep over a state, not an event

Three triggers are named in `matching.md` §4.2 — a new or changed job, a profile
change, a ruleset version bump — and they are **one query**, not three
mechanisms: *(user, open job) pairs with no `match_results` row at the current
ruleset version.* A new job has never had one; a bumped ruleset invalidates every
one; a profile change deletes them.

Absence of a row is the work item, and it is durable. There is no event to miss
and no queue to lose, and there is exactly one code path that computes a score
rather than three that can drift apart.

The sweep runs on a one-minute ARQ cron, and — as of Task 12 — also from
`make score` and at the end of `make seed`. All three call `recompute_pending`
and nothing else does.

### 4. Eligibility stays computed on read, beside a score that is not

Both appear on the job page. They are derived differently and that is deliberate,
not an inconsistency:

- The **verdict** is cheap, is a claim that must never be stale in the blocking
  direction, and has no breakdown that needs to outlive the request.
- The **score** is expensive, is never a blocker, and has a breakdown that I4
  requires to be stored.

`match_results.eligibility_status` exists as a column anyway — the ranked list
bands on it — and because that is a second derivation of the same fact, a test
asserts the stored state agrees with the live verdict on the same pair.

### 5. The denominator is stored, and the ranked list sorts on the fraction

Measured on the answer key: **26 of 60 labeled postings name no required
technology at all.** Scoring those out of 100 removes 50 points for how an
employer writes, which is the argument §5.1 used to defer application urgency
with a bigger number behind it. So a score is out of what could be assessed,
`assessed_out_of` is a stored column, and the ranked list orders on
`overall_score / assessed_out_of`.

A component that scored zero and a component nobody could assess both store `0`,
so the denominator alone cannot say *which* — that is what
`match_component_assessments` is for, and why the page can name them.

## Consequences

**What this buys.** Every number on the page is read off one row. A profile edit
withdraws every score that depended on it, atomically, and the page says
"not scored yet" rather than showing something computed against a person who has
changed. A ruleset bump is comparable against what it replaced. Ranking is stable
by construction and was measured to be: the corpus was deleted and rebuilt twice
in one `make verify` run and landed on identical numbers for all 31 postings.

**What it costs.**

- **Latency.** A score is absent for up to a minute after a profile edit. This is
  the right side to err on — absent is true, and a number computed against a
  replaced profile is not — but it is a real gap a person will notice, and
  `make score` exists partly because a developer notices it constantly.
- **A worker is now load-bearing for a demo.** `make acceptance` runs no ARQ
  worker, so `make seed` ends by running the sweep itself. Without that, every
  M3 surface renders its honest empty state and the browser suite asserts
  against a milestone that is not there.
- **Rows accumulate per version.** Old-version rows are kept on purpose (§4.2),
  and nothing prunes them yet. At one user and 31 postings this is not a problem;
  it is named here so that it is a decision rather than an oversight.
- **The fraction is not a total order anyone should read as "best first".** 19
  of 40 outranks 30 of 100, and the two denominators are not comparable
  quantities. §7.3 already says ranking *quality* is unmeasured in M3; this is
  what that looks like on screen, and the M3c review records it as the first
  thing M3d's relevance pass should look at.

## Alternatives considered

**Compute the score on read, like the verdict.** Rejected on I4: the breakdown
must be stored, and once the breakdown is stored, deriving the total separately
is the second-derivation failure with extra steps.

**Refresh in place instead of deleting.** Rejected because its intermediate state
is a lie, and because a refresh cannot be done inside the request's transaction
without putting a multi-second corpus rescore in the path of a form submission.

**Rescore on every profile write.** Rejected as §4.2's own trap: fifteen columns
are written by one endpoint and six components read nine of them, so an unedited
form would rescore the corpus for nothing.

**Always score out of 100 and show the gaps.** Rejected in §5.1.1 and QUESTIONS
Q6: it systematically ranks terse postings below verbose ones, which is a
property of the employer's prose and not of the reader.
