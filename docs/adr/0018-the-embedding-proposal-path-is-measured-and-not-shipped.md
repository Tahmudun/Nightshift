# ADR 0018 — The embedding proposal path is measured and not shipped: its strongest signal is its worst claim

- **Status:** accepted
- **Date:** 2026-08-10
- **Milestone:** M3c (Task 11)
- **Relates to:** `matching.md` §2, §2.1, §2.2 and §2.3; the M3c plan §1.1; AMENDMENTS A5; invariants I2, I4 and I7

## Context

`matching.md` §2 drew the boundary this milestone was built around: **an
embedding may propose, it may never score.** A local `bge-small-en-v1.5` model
may suggest that a posting relates to something in a person's confirmed data,
and that suggestion earns points only if it resolves to a character span on both
sides. No cosine similarity reaches the number.

The M3c plan §1.1 then deferred building it to Task 11, behind ten tasks of
rules-only work, for a reason it stated in advance:

> the span rule means an embedding proposal can only ever re-rank things that
> already have spans. It cannot invent evidence — that is the whole design. So
> the honest question is how many *additional* (job span, user span) pairs a
> proposal finds that the vocabulary missed, and that question has no answer
> until the vocabulary's own yield is on the table.

It also wrote down, before any measuring, that not shipping was a permitted
outcome — so that this decision would be a result rather than a retreat.

Task 11 measured it. The measurement is committed as
`services/api/tests/test_embedding_proposals.py`, which pins every figure quoted
below as an assertion rather than a sentence.

## What was measured

Over the committed corpus — 153 recorded postings, of which 71 name at least one
`required` technology, giving 240 requirement rows per profile — the rules-only
scorer matches:

| Fixture profile | Required rows matched, of 240 |
|---|---|
| `new_grad_backend` | 90 |
| `experienced_ml` | 88 |
| `early_career_no_experience` | 59 |
| `states_nothing` | 0 |

Everything missed is what the embedding layer existed to recover: 150, 152 and
181 rows on the three profiles that state anything.

Ranking every (missed requirement, confirmed skill) pair by cosine similarity
under the real model gives this at the top:

| Similarity | The proposal it would make |
|---|---|
| 0.797 | you meet a **Java** requirement, because you confirmed **Python** |
| 0.764 | **macOS**, because you confirmed **Linux** |
| 0.750 | **Azure**, because you confirmed **AWS** |
| 0.742 | **Excel**, because you confirmed **SQL** |
| 0.736 | **Windows**, because you confirmed **Linux** |
| 0.725 | **TensorFlow**, because you confirmed **PyTorch** |
| 0.705 | **Google Cloud**, because you confirmed **AWS** |
| 0.699 | **Kubernetes**, because your project used **Docker** |
| **0.624** | **Machine Learning**, because you confirmed **PyTorch** |

The last row is the only relation in this corpus a person would defend. It
finishes ninth.

The layer is not weak, which matters for what lesson gets carried forward. At a
0.70 cut it adds 44, 58 and 43 requirement rows on the three profiles that state
anything — **+49%, +66% and +73%** on top of what the rules matched. At 0.50 it
matches essentially everything the vocabulary missed; above 0.80 it matches
nothing at all. The entire usable band sits inside the confusion zone.

Feeding the model richer text does not reorder it. Embedding the requirement
inside its own sentence from the posting — the most context available on the job
side — puts `Windows`←Linux, `macOS`←Linux, `Azure`←AWS, `Google Cloud`←AWS,
`TensorFlow`←PyTorch and `Java`←Python in the top twenty again. Comparing
posting sentences against project bullets produces `Kubernetes` from *"packaged
the whole thing with Docker"* and `CUDA`, `Triton`, `SYCL` and `ROCm` from
*"trained the reranker in PyTorch across eight GPUs"*. The input was not the
problem.

## Decision

**No embedding proposal path is built. The score is rules-only through M3.**

Three findings drive it, and the first is the one that closes the question.

### 1. The ordering is inverted, so there is no threshold to find

A threshold is worth having when the claims worth keeping sit above it. Here
they sit below. Cosine similarity between two technology names measures
**topical relatedness**; a match claim needs **substitutability**; and over
exactly the pairs that matter the two run opposite to one another. Java and
Python are maximally related and not remotely interchangeable, and it is
*because* they are siblings that the model puts them together. The layer's
highest-confidence output is its most dangerous one.

Any cut generous enough to admit the one defensible relation admits at least
eight fabricated qualifications ahead of it. That is I2 — *never fabricate a
user qualification* — failing, and failing in the specific way I2 was written to
catch: as a confident, specific, plausible-looking claim.

### 2. Spans prove provenance, not entailment — and §2 assumed otherwise

This is the part of `matching.md` §2 that Task 11 found to be wrong, and it is
worth stating plainly rather than filing under "measured".

The span rule was carrying the safety argument. The reasoning was that a
proposal which must quote both sides cannot invent anything. But a proposal of
"you meet the Java requirement" quoting the posting's word *Java* and the user's
word *Python* satisfies both spans **literally and completely**. Both strings
were really written by the parties named. The rule guarantees that neither
string was invented; it says nothing about whether one implies the other.

So the span rule is a real defence against *hallucinated text* and no defence at
all against *unwarranted inference* — and it is the second that a similarity
score produces. Worse, the two spans render on the page beside the claim, so a
fabricated qualification arrives looking audited. An honest-looking wrong answer
is worse than an obviously wrong one.

### 3. The vocabulary already owns the cases where a proposal would be right

Every case where two different strings denote the *same* technology is handled
by `data/skills.yaml`'s alias table: `golang`/`Go`, `cpp`/`C++`, `ts`/`TypeScript`.
Those never reach a proposal layer, because they never miss.

What is left over for an embedding is therefore, by construction, pairs of
strings denoting *different* technologies. There is no honest match hiding in
the residue to be found by a better model or a better threshold. The residue is
the set of things the person did not claim.

## What Task 11 found that is worth building instead

The measurement did surface one real gap, and it is a different shape from the
one the plan expected.

Three of the corpus's required terms are **concepts rather than tools**:
`Machine Learning` (26 occurrences), `Distributed Systems` (4), `Data Structures`
(3). Somebody can genuinely demonstrate these through a concrete tool — PyTorch
really is evidence of machine learning — and today the scorer misses all 33
occurrences.

The honest carrier for that is an **ontology edge in the vocabulary file**, not a
similarity number:

```yaml
- name: Machine Learning
  demonstrated_by: [PyTorch, TensorFlow, JAX, scikit-learn]
```

It is reviewable, diffable, versioned with `skills.yaml`, and it makes a claim a
human wrote down and can be argued with — which is everything a cosine score is
not. It is also strictly narrower: it says PyTorch demonstrates machine
learning, and never that PyTorch demonstrates TensorFlow.

Not built here. M3c's remaining budget is Task 12, and adding a vocabulary
relation would move scores across the corpus and require a `ruleset_version`
bump on the way out of the milestone. Recorded for M3d or later.

## Consequences

**`EvidenceSource.EMBEDDING` stays** — in the PG enum, in the API schema, in
`evidenceSourceSchema`, and in `MatchPanel`'s "proposed by the embedding" branch.
Nothing produces it.

That is deliberate and it is the one point where this ADR argues against its own
tidiness. The branch is a fail-safe, not decoration: if a row carrying that
source ever did reach the page, rendering it as *"matched by a vocabulary rule"*
would be the failure worth preventing. An unreachable branch that is correct
beats a reachable branch that lies. Removing the enum member would also be a
migration that buys nothing and would have to be reversed by whoever revisits
this.

It is listed in `PROGRESS.md` under **"Not real yet"** so that the gap between
*the wire can express this* and *nothing produces this* is written down rather
than inferred, which is I7's requirement.

**The recall cost §2.3 promised to measure is now measured**, and it lands
differently than expected. §2.3 said the cost of the span rule is recall,
"measured rather than assumed". The rules-only scorer misses 150–181 of 240
required rows per profile. But Task 11's finding is that essentially none of
that gap is recoverable by the mechanism §2 reserved for it — so the number is a
description of the corpus and the vocabulary's breadth, not a queue of matches
waiting for a model. M3d still reports skill-extraction recall against the answer
key; that is the number that can actually be improved, by growing `skills.yaml`.

**`matching.md` §2.2's conclusion is amended.** It rejected "fully
deterministic" for a stated reason — invisible recall loss — while accepting
that it was defensible. Through M3, this system *is* fully deterministic, and
§2.2 now records that the alternative was chosen on evidence rather than
tolerated.

**Reopening this is cheap and the tripwire is in place.**
`test_the_scorer_emits_no_evidence_row_an_embedding_proposed` fails the moment
any proposal path ships, which sends whoever writes it here first. And
`test_no_threshold_admits_the_defensible_relation_without_fabrications_first`
fails if a future model separates siblings from concepts — which is the evidence
that would justify reversing this decision, arriving as a red test rather than
as an opinion.

## What would make this ADR wrong

- **A model that scores substitutability rather than topic.** A cross-encoder
  trained on "does A satisfy a requirement for B" is a different instrument from
  cosine over names, and this ADR does not claim it would fail. It claims
  `bge-small` over the corpus does, decisively. A5 forbids reaching for a hosted
  one without an ADR, so that would be a new decision with new evidence.
- **A corpus where the misses are concepts rather than siblings.** Nine
  employers, all quant trading firms or AI labs, is a narrow corpus and PROGRESS
  says so about all of M3. A domain whose postings name capabilities rather than
  tools would shift the balance — though the fix there is still the ontology
  edge above, which is why the recommendation does not depend on this.
- **If the proposal were confined to the same taxonomy entry.** An embedding
  used only to decide *which existing vocabulary term a person's free-typed skill
  means* is a narrower question than the one measured here, and a safer one.
  It is also `skills.yaml`'s alias list doing its job, which is why it was not
  measured separately.
