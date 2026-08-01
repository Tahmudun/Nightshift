# ADR 0010 — Dedupe is layered, and similarity may never merge on its own

- **Status:** accepted
- **Date:** 2026-08-01
- **Milestone:** M1 (M1b)

## Context

PRODUCT-SPEC §7.5 calls deduplication a flagship engineering feature and lists
ten kinds of evidence, ending with embedding similarity and "known
cross-posting patterns". It also says, flatly: *do not merge records solely
because titles are similar.*

Today there is no dedupe at all. Every source record becomes one canonical job
with `link_reason='sole_source_record'`.

The decision to make was how much of §7.5 to build now. Two positions were put
to the human:

- **Rules only** — hard evidence, every merge explainable in a sentence, no
  model in the ingestion path. Cross-provider duplicates with reworded text
  stay separate.
- **Rules plus similarity** — adds the local embedding model to catch the same
  job posted with different wording on two boards.

I recommended rules-only. The human chose rules plus similarity. This ADR
records that, and records the constraint that makes it safe.

## Decision

Four layers, evaluated strongest-first within a single company. The first that
fires decides and writes its reason and confidence to `job_source_links`.

| # | Rule | Confidence | `link_reason` |
|---|---|---|---|
| 1 | Same canonical URL, after normalisation | 1.0 | `same_canonical_url` |
| 2 | Same company + normalized title + shared location + identical `description_hash` | 0.99 | `identical_content` |
| 3 | Same company + normalized title + shared location + similarity ≥ threshold | scaled | `similar_description` |
| — | otherwise | — | distinct |

**Similarity is a tie-breaker, never a matcher.** Layer 3 is reachable only
when company, normalized title and location already agree. A high cosine score
between two postings that disagree on any of those produces nothing at all.

Three blocking rules refuse a merge whatever the layers say: differing
employment types, no shared location, differing companies.

The threshold is derived from the labelled fixture set, not chosen by taste,
and is pinned as `DEDUPE_RULESET_VERSION`.

## Why similarity is confined this way

The asymmetry is the argument. A missed merge shows a user the same job twice —
mildly annoying, immediately obvious, self-correcting when they click. A wrong
merge deletes a real opening from their view and replaces it with a different
one. They never learn it existed.

So the layer that is hardest to explain gets the least authority. Layers 1 and
2 assert facts: the same URL, or byte-identical descriptions. Layer 3 asserts a
number, and a number is not a reason. Requiring the deterministic facts to
agree first means every merge can still be explained in a sentence — "same
company, same title, same office, and the descriptions are near-identical" —
which is what §7.5's audit-trail requirement actually demands.

This also keeps I4's spirit intact one milestone before I4's subsystem exists:
no bare number decides anything a user can see.

## Why embeddings at all, given the recommendation against them

Because the cross-posting case is real and the deterministic layers cannot
reach it. A company running both a Greenhouse board and a Lever board will
publish the same role with hand-edited copy in each, and `description_hash`
equality fails on a single changed word. AMENDMENTS A5 already committed the
project to a local, free, offline, deterministic model for exactly this, and
pgvector is already installed. The cost is a ~130 MB one-time download at
`make setup`, and `make demo` stays offline afterwards.

Determinism matters more here than it looks: a hosted embedding API would make
the dedupe fixture suite non-reproducible, and a fixture suite that can drift
cannot enforce the blocking rules above.

## Consequences

- The similarity threshold is a committed constant with a fixture behind it.
  Changing it is a reviewable event.
- `job_embeddings` stores model name and dimension on every row (A5), so
  replacing the model is a backfill rather than a mystery.
- Embedding runs at ingestion, once per canonical job description. At this
  volume (thousands of jobs) that is unremarkable; if it ever is not, the
  answer is to embed lazily on merge-candidate generation, not to weaken the
  rules.
- **A dedupe evaluation fixture set is a deliverable, not a nicety.** All seven
  categories from §7.5 — true duplicates, near duplicates, distinct roles with
  similar titles, reposts, seasonal internship variants, multi-location roles,
  and edited descriptions — get labelled pairs before the matcher is written.
  The suite sets the threshold and it is what fails when a rule change starts
  merging a pair labelled distinct.
- Merges are reversible: `job_merge_events` records each one, and canonical
  jobs are derivable from preserved raw payloads regardless.

## Alternatives rejected

**Similarity as an independent layer.** Merging on a high score alone, without
title or location agreement, is the version of this feature that eventually
deletes a real job. Rejected outright.

**Fuzzy title matching (edit distance, token overlap).** §7.5 forbids merging
on title similarity, and `test_companies.py` already documents what fuzzy
matching does to names — Meta/Metabase, Ramp/Rampart. The same failure applies
to titles, where "Software Engineer II" and "Software Engineer III" differ by
one character and are different jobs.

**Deferring dedupe to M3 alongside matching.** Tempting, since both involve
embeddings, but M2 builds saved jobs and application tracking on top of
canonical job identity. Changing what a canonical job *is* after users have
saved some of them is a migration nobody wants.
