# ADR 0020 — A skill is evidence of another only where a human wrote it down

- **Status:** accepted
- **Date:** 2026-08-11
- **Milestone:** M3d (Task 1)
- **Relates to:** ADR 0018 (the embedding proposal path is measured and not shipped), ADR 0015 (requirements are extracted with spans), `matching.md` §2, §2.1, §4.1, §9, invariants I2 and I4

## Context

ADR 0018 measured a local embedding as a way of closing the gap between what a
posting asks for and what a person has confirmed, and declined to ship it. Its
argument was not that the model was bad. It was that a cosine similarity above a
threshold is **not a claim anybody made**, and I2 requires a positive match to
resolve to a concrete evidence row that a person could read and dispute. The
measurement it recorded was blunt about the failure mode: the embedding proposed
that knowing Python is evidence of knowing Java.

That ADR ended by naming what it would accept instead — a curated, one-hop,
one-directional relation in the versioned taxonomy — and left it unbuilt.

Meanwhile the corpus had a measurable hole of the exact shape the rejected model
was aimed at. The vocabulary carries **concept terms** (Machine Learning,
Distributed Systems, Data Structures) that appear in postings as requirements and
that no confirmed skill can ever match, because nobody lists "Machine Learning"
as a skill — they list PyTorch. 33 occurrences across the corpus matched nothing,
and the `experienced_ml` fixture profile — the one whose skills are precisely the
tools involved — matched 88 of 240 required rows.

## Decision

### 1. `demonstrated_by:` is an edge in `data/skills.yaml`, written by a person

A concept term may declare the technologies that count as evidence of it:

```yaml
- id: Machine Learning
  demonstrated_by: [PyTorch, TensorFlow, scikit-learn]
```

The edge is **one-directional**. PyTorch is evidence of Machine Learning;
Machine Learning is not evidence of PyTorch. The asymmetry is the whole content
of the relation — a person who has shipped PyTorch has done machine learning, and
a person who has studied machine learning has not thereby used PyTorch. A
symmetric relation would be a similarity, which is the thing ADR 0018 rejected
wearing different notation.

The edge is **one hop**. No transitive closure, no walking from PyTorch to
Machine Learning to something else Machine Learning demonstrates. Each additional
hop multiplies the number of claims the file makes without anybody having written
one of them down, and the second hop is where a chain stops being readable by the
person it is a claim about.

### 2. It is a claim in a versioned file, and that is the entire difference

The relation an embedding computes and the relation this file states can award
the same point. What separates them is that this one has an author, a diff, a
review, and a `ruleset_version` it moves. `RULESET_LOGIC_VERSION` went 2 → 3 and
the vocabulary to `2026-08-10.1`, so every stored score computed under the old
edges is superseded rather than silently reinterpreted — which is what makes an
edge revocable. A threshold is not revocable in that sense; there is no version
of "0.83 was close enough".

The evidence row it produces still quotes two literal spans (§7.2) and still
carries `proposed_by = rule`. Nothing about the shape of the output changes,
which is the point: this is the vocabulary getting a new kind of entry, not the
scorer getting a new kind of source.

### 3. What it bought, measured, because ADR 0018's argument was that a number beats a claim

Golden regenerated: 68 new evidence rows across 153 postings × 4 profiles.

| Profile | Required rows matched, before → after |
|---|---|
| `experienced_ml` | 88 → 118 of 240 |
| the other three | unchanged |

**The other three moving by zero is the result, not a footnote.** A narrow edge
should only reach the profile that confirms the tools involved. A change that
lifted every profile would mean the edges were matching something broader than
they say, and the right response would have been to read them again rather than
to keep the gain.

### 4. `Data Structures` deliberately gets no edges

Every language implements them. Any `demonstrated_by:` list for that term reads
"you have written code", which is true of everybody who reaches this system and
is therefore evidence of nothing. Its three corpus occurrences stay unmatched.

This is the rule the file is meant to be read by: an edge is justified when the
technology is *specific* to the concept, not when it is compatible with it. A
term that cannot pass that bar keeps its unmatched occurrences, and the honest
report of a gap is preferred to a low bar dressed as a match.

### 5. `demonstrates` is a required keyword-only argument to `score_match`

It began as an optional parameter defaulting to no edges, and that default hid
the feature from everything that grades it. The golden test, the mutation harness
and the embedding measurement all call `score_match` directly, so all three were
pinning a scorer that was not the one shipping — and the golden test **passed
with the feature complete and wired into production**.

Making it required means a call site has to say which rules it means, and the one
that forgets fails to run rather than measuring the wrong thing quietly. This is
the same defect class M3d Task 8 later found in the ranking grader, one
subsystem over, which is why it is written into an ADR rather than left in a
commit message.

## Consequences

**What this buys.** The 33 concept-term occurrences become answerable by evidence
a person can read, without a model, a threshold, or a claim nobody made. The gap
ADR 0018 identified is partly closed by the mechanism ADR 0018 recommended, and
the closure is versioned, so it can be argued with and rolled back.

**What it costs.**

- **The file is now a place where a wrong claim is expensive.** An edge that
  should not be there awards points to somebody who has not earned them, and it
  will do so quietly and consistently. There is no threshold to tune afterwards;
  the remedy is a diff.
- **It does not generalise.** Every concept term needs its edges written by hand,
  and the corpus will keep producing terms nobody has covered. This is the
  intended trade — coverage in exchange for authorship — and the honest report of
  an unmatched term is the fallback, not a silent near-match.
- **ADR 0018's baseline is now historical.** Its numbers (90/88/59/0) describe
  what the rules missed *at Task 11*, and building its recommended successor
  moves them. `_matched_and_missed` therefore takes the ruleset it is measuring
  and the historical assertions run with the edges off, so the evidence for that
  decision is not erased by the change it recommended.

## Alternatives considered

**Ship the embedding after all, with a higher threshold.** Rejected on ADR 0018's
own grounds, which a threshold does not address: the objection is that the
resulting row is not a claim anybody made, and that is true at every threshold.

**Make the relation bidirectional and weight the reverse direction lower.**
Rejected. A weighted reverse edge is a statement that studying machine learning
is *some* evidence of having used PyTorch, which nobody would write down in those
words, and a fraction of a fabricated qualification is still fabricated.

**Infer the edges from the corpus** — treat co-occurrence of a concept term and a
technology in the same posting as an edge. Rejected as the embedding with worse
statistics: it would encode what employers write near each other, which is a fact
about job-posting prose, and it would produce edges with no author for exactly
the terms nobody thought hard about.
