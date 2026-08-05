# ADR 0015 — A posting's requirements are extracted by rules, and every one quotes its span

- **Status:** accepted
- **Date:** 2026-08-04
- **Milestone:** M3a
- **Relates to:** ADR 0013 (resume facts are proposals with spans), `matching.md` §3–§4, invariants I2 and I4

## Context

M3 has to answer "does this person meet this posting's requirements", and it
cannot answer that until it can say what the posting requires. That is a reading
problem over free text written by seven different companies with no agreed
vocabulary, no agreed structure, and no obligation to be consistent between two
postings on the same board.

Two questions had to be settled before any code: what does the reading, and what
is stored when it is done.

## Decision

### 1. Rules, not a model

`nightshift/domain/requirement_extraction.py` is regular expressions, a heading
table, and the skill vocabulary from `data/skills.yaml`. No LLM, no classifier,
no embedding.

The argument for a model is recall, and recall is genuinely bad here — 0.459 on
required technologies against the answer key. The argument against is that a
score has to be reproducible from its inputs, which is the whole of I4 and the
M3 acceptance criterion "identical inputs + identical `ruleset_version` →
identical output". A model that is 15 points better and cannot be replayed
buys nothing this milestone is allowed to spend.

The second argument is smaller and turned out to matter more while building:
when a rule is wrong you can see *which* rule, because it is a named pattern in
a table with a comment saying which board it came from. Thirteen of the sixty
labeled postings are governed by Akuna's "Qualities that make great candidates",
and knowing that is what let the necessity rules be fixed rather than tuned.

**This is not permanent.** A model may propose; it may not score. `matching.md`
§5 already draws that line for M3b.

### 2. Every requirement carries the characters it came from, enforced by trigger

`job_requirements` stores `raw_text`, `char_start`, `char_end`, and a trigger
refuses any row where `description_text[char_start:char_end] != raw_text`.

A convention was the alternative and it is not enough, for the reason M2c
recorded about `resume_extractions`: the writer is not the only thing that can
falsify a span. The *parent* can. A re-poll assigns `jobs.description_text` on
every content change, and a span that was honest yesterday indexes into moved
characters today — while still passing every insert-time check, because nothing
was inserted. So there are two triggers, not one:

| Trigger | Fires on | Prevents |
|---|---|---|
| `job_requirements_span_must_quote` | insert/update of a requirement | a row that never quoted its span |
| `jobs_description_change_clears_requirements` | update of `jobs.description_text` | rows outliving the text they quote |

The second is the load-bearing one and it is the one a convention cannot
express, because the code that breaks the invariant is code that is doing its
job correctly.

**Measured while building Task 8:** removing the delete from
`sync_requirements` leaves every description-change test green, because the
trigger is what holds them up. The delete's real job is idempotency — a second
sync over unchanged text re-emits the same `(kind, value, char_start)` tuples
and the unique constraint would reject them.

### 3. I2 does not govern this table, and it looks like it should

`resume_extractions` proposes and never confirms, because I2 forbids storing a
claim about a *person's* qualifications without an explicit action. Requirements
look identical in shape — extracted, spanned, uncertain — and get no confirmation
step at all.

The difference is whose claim it is. A resume claim is about a person and is
checkable only by that person. A requirement is a claim about a *posting*,
checkable by anyone against a payload committed in this repository. Asking a
user to confirm sixty postings' requirements before their queue works would be
an invariant applied by resemblance rather than by reason.

What the two do share is the span, and for the same reason: an extraction nobody
can trace back to a sentence is not auditable. The job page shows the sentence
rather than asking anyone to trust a summary.

### 4. Necessity is three-way, and it comes from the heading above

`required` / `preferred` / `mentioned`. Text before any heading is `mentioned` —
an "about us" paragraph naming a stack is not an ask — and a posting with no
headings at all is `mentioned` throughout rather than promoted by guesswork.

The three-way split exists because two would force a choice that is wrong in
both directions. Collapse `mentioned` into `preferred` and every company's tech
blog paragraph becomes a soft requirement. Collapse it into nothing and the
extractor discards the evidence that a posting mentions Kubernetes at all, which
M3b's gate needs in order to say "not required here" rather than "not present".

**The worked example is Akuna, not Ramp** — the plan named Ramp and the corpus
settled it differently. "Qualities that make great candidates" governs 13 of the
60 labeled postings. In the 11 with no other requirements heading, the human
labeled C++, Linux and Python *required* from it. In the 2 that also say
"Requirements for this role" — both internships, where that harder heading
carries graduation year, GPA and work authorization — the human labeled
`required_tech` **empty** and put Kubernetes and AWS under
`mentioned_not_required`. The same phrase means "these are the requirements" in
one posting and "these would be nice" in another, and what separates them is
whether the posting already said the harder thing. `_SOFT_REQUIRED_HEADINGS`
is that rule, and it exists because the corpus produced it.

## Consequences

**Recall is the known weakness and it is published, not hidden.**
`test_requirement_extraction_against_the_answer_key.py` grades against 60
human-labeled postings and fails below floors of 0.65 precision, 0.45 recall and
0.66 necessity accuracy on required technologies. Current: 0.659 / 0.459 /
0.668. Those floors are close enough to the measurements that a regression is
caught; they are not aspirations.

**Necessity accuracy of 0.668 means one technology in three is filed under the
wrong heading, and the job page makes that visible rather than hiding it.**
Measured on the seeded corpus: 2 of 32 rows shown as `required` sit beside a
quoted sentence that itself says "preferred" or "a plus". A reader can see the
disagreement because the sentence is printed. That is the argument for showing
the quote, and it is also the honest statement of where this extractor is.

**The skill filter became buildable and stayed deferred.** Every posting's
technologies are now indexed, so `/jobs?skill=Kotlin` is a query away. It is
still off, because at 0.459 recall it would hide more than half the roles that
ask for a skill and return them as an empty result — which reads as "no such
job". The deferred entry now says that, replacing a reason that had gone stale.

**M3b inherits `has_equivalence` unused.** "or equivalent experience" is stored
per row and read by nothing except the tests and the badge on the job page.
A13 requires the gate resolve it to `uncertain` rather than `ineligible`, and
storing it now is what makes that possible without re-extracting.
