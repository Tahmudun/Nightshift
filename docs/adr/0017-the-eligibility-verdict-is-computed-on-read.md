# ADR 0017 — The eligibility verdict is computed on read, stored nowhere, and refuses more often than it blocks

- **Status:** accepted
- **Date:** 2026-08-09
- **Milestone:** M3b
- **Relates to:** ADR 0015 (requirements are extracted with spans), `matching.md` §3–§5 and §8, AMENDMENTS A13, invariants I2 and I4

## Context

M3b is the first thing in this system that makes a claim about a **person**.
Everything before it made claims about the world — this board listed these jobs,
this posting names these locations — and every one of those is checkable against
a payload committed in this repository. "You are not eligible for this role" has
no payload to check it against.

That changes what the engineering has to protect against. A wrong location is
visible beside the address it came from. A wrong `ineligible` deletes an
opportunity from somebody's world and reports nothing: they never learn the role
existed, so they never report the bug, so nothing measures it.

A13 ranks the two directions and the ranking is not symmetric. A wrong
`ineligible` is the worst output this engine can produce. Every decision below
follows from taking that literally rather than treating it as a preamble.

Three questions had to be settled: where the verdict lives, what a rule is
allowed to conclude, and what the page does with an answer that is not an answer.

## Decision

### 1. The verdict is computed on read and stored nowhere

`GET /jobs/{id}` builds a `PostingReading` from the stored requirement rows,
builds a `SeekerProfile` from the `users` row, and calls `evaluate`. Nothing is
written. There is no `eligibility` column, no cache, no invalidation, and no
worker.

The alternative — a stored verdict per (job, profile), refreshed by a job — is
what `match_results` will be at M3c, and it is wrong for M3b for a reason that
is not performance:

**A stored verdict is stale the moment somebody edits their graduation year, and
the direction it is stale in is the dangerous one.** The person fixes their
profile precisely because a posting told them they were blocked; the page keeps
telling them so until a worker they cannot see decides otherwise. Stale in that
direction is A13's worst output with a delay attached.

The cost is real and small enough to accept at this scale: one detail request
runs five rules over at most a few dozen extracted rows. One user, a few thousand
jobs. When M3c stores a score, the verdict stored beside it carries the three
version strings — extractor, reading, gate — for exactly this reason, and the
staleness question comes back and gets a different answer.

`check_eligibility_gate` in `scripts/verify.py` asserts this against a live
stack rather than in a comment: the same URL, requested twice, answers
identically; a profile column changed, and it answers differently; the column put
back, and the payload is restored exactly. No worker ran in between.

### 2. `blocks` needs two explicit halves, and either half missing is an unknown

A rule may return `blocks` only when the posting states the requirement under a
**required** heading *and* the person's **confirmed** profile contradicts it.

This is I2 doing the work rather than being cited. An inferred fact never blocks
anybody, because an inferred fact is not a fact. `work_authorization` is the
sharp case: `unspecified` is the column's default and most users' day-one value,
and reading it as "needs sponsorship" would silently block them out of every
posting that says it does not sponsor, before they had typed anything. `f1_student`
is likewise not `needs_sponsorship` — an F-1 on OPT does not need sponsorship
today, and inferring one from the other is a fabrication in the field where being
wrong costs most.

Two rules are deliberately asymmetric, and neither is a matter of taste:

- **A years shortfall may never hard-block.** "5+ years" is a wish far more often
  than a rule, and A13's first hard case is an employer writing "Intern" and
  "3+ years required" into the same document. It reaches `likely_ineligible` and
  stops. The person sees the role, sees the gap, and decides.
- **Enrollment may hard-block**, because it is categorical and checkable rather
  than a matter of degree. An internship requiring a registered student is
  genuinely closed to somebody who graduated two years ago, and saying so is
  useful.

`seniority` is absent from the dimension list entirely. `matching.md` §5.1 makes
a seniority mismatch a score *penalty*, which is M3c's. A senior title is not a
legal barrier and treating one as a blocker is precisely the wrong `ineligible`.

The rule shape is enforced rather than described.
`test_every_gate_rule_is_load_bearing.py` replaces each of the five rules with an
unconditional `passes` and requires a
named case to change its verdict, so a rule that has quietly stopped mattering
fails the suite instead of passing it. Two guards sit on the harness itself,
because a mutation harness that mutates nothing is the most confident kind of
vacuous test — one of them exists because `_RULES` captures function references
at import and `monkeypatch.setattr` on the module left the tuple pointing at the
originals, which was measured rather than supposed.

### 3. `uncertain` is a real answer, and it splits into two sentences

The composition runs in one direction only:

```
any blocks       -> ineligible
else any soft    -> likely_ineligible
else any cannot  -> uncertain
else                eligible
```

There is no branch producing `likely_eligible`. It would mean "every rule passed,
but one leaned on something uncertain", and no rule here passes on an uncertain
input — each returns `cannot_tell` instead. A fifth state no rule can reach is
shape with no use. The enum keeps the member because PRODUCT-SPEC §8.3 names it
and M3c's score components may earn it; the plan's five-way composition above is
corrected here rather than quietly not implemented.

**What `uncertain` cannot be is a number.** `matching.md` §5.2: the moment
uncertainty is worth points it stops being uncertainty. It stays a state, beside
the score rather than inside it.

Two outcomes reach `uncertain` and they are different sentences to a person:

| Outcome | Means | `profile_field` | The page |
|---|---|---|---|
| `cannot_tell` | you have not told us | the column to fill | "What would let this answer", with a link |
| `cannot_assess` | the *posting* is written so that nothing you could tell us settles it | `null` | "What nothing in your profile can settle", no link |

A13's equivalence hatch is the only `cannot_assess` today. "Bachelor's degree
**or equivalent experience**" is checked before `profile.degree` is read — that
ordering is what makes the hatch always win — so a PhD holder lands there exactly
as somebody with no degree does.

**This distinction was collapsed until the browser walk, and the walk is what
found it.** Filed as `cannot_tell`, the page printed "Add your degree" beside a
profile that already had one. The reader follows the link, fills a field that is
already filled, and the verdict does not move: an action that cannot work, which
is worse than no action because they take it. Every unit test passed the whole
time — a `why` sentence saying "not something this system can assess" reads
perfectly well in a fixture and reads as a broken promise underneath a link.
`verify.py` now checks the shape rather than the wording: every unknown names a
field `GET /profile` actually carries, or names none.

### 4. An `ineligible` posting is dimmed, never hidden

`matching.md` §3.3, and it is the decision that makes the rest survivable. The
gate is allowed to be wrong. It is not allowed to be wrong invisibly.

A hidden row is a parsing bug the reader cannot see and therefore cannot report.
So a blocked posting stays in the list, stays searchable, keeps its Save control,
and shows every blocker with the posting's own words and the character offsets
they came from. The Playwright walk asserts the list membership and the Save
control, because neither is a property of the component that renders the verdict
and no component test could ever reach them.

## Consequences

**The empty profile is blocked from nothing, as an equality rather than a rate.**
Over 60 labeled postings × 5 profiles, zero wrong `ineligible`s — and the checker
is written from the answer key and never calls the gate, because a checker that
called the gate would agree with it by construction. `verify.py` now asserts the
same thing over the live seeded corpus: with every gate column cleared, the count
of `ineligible` is 0. A person who has typed nothing has contradicted nothing, so
every block against them is wrong by construction.

**The opposite failure is guarded separately, and it has to be.** A gate
answering `uncertain` to everything satisfies the equality above, forever, having
decided nothing. Both suites assert the corpus reaches more than one state.

**Accuracy could not see the most valuable fix in this milestone.** "MS Office"
was being read as a master's degree on an administrative posting labeled
`degree: none`, hard-blocking a bachelor's graduate. Fixing it moved reading
accuracy from 0.850 to 0.867 — nearly nothing — and removed a hard block on a
real person. A metric that cannot distinguish a false positive costing precision
from one costing somebody a job is not the metric to gate on alone, which is why
the wrong-ineligible equality sits beside the floors rather than instead of them.

**No eligibility precision or recall in CI, and that is a deferral with a date.**
`matching.md` §7 puts the ranking and eligibility metrics at M3d. M3b publishes
reading accuracy per label field, classifier accuracy per field, and the
wrong-ineligible equality. Those are what it can honestly measure with a 60-posting
key that has no eligibility ground truth in it.

**The gate is graded on the same 60 postings the classifier's thresholds were
chosen against.** The corpus carries 93 recorded-but-unlabeled postings that
would be a genuine held-out check, and they are not labeled. Until they are,
every number in this milestone is an upper bound rather than an estimate of
behaviour on an unseen posting.
