"""M3c Task 11 — what an embedding would propose, and why none of it ships.

The M3c plan §1.1 held this task back until the whole score was measurable
without it, and said in advance that measuring a poor result is a legitimate
outcome: *"If Task 11 measures a small number, it is correct to not ship it and
record the figure, and that outcome has to be reachable from the plan rather
than embarrassing."*

The number is not small. It is **inverted**, which is worse, and this file is
the evidence.

## What was measured

`matching.md` §2 lets an embedding *propose* a match between a posting and a
person, and lets that proposal earn points only when it resolves to a character
span on both sides. Over the committed corpus — 153 recorded postings, 240
`required` technology rows per profile, four fixture profiles — the vocabulary
matches 90, 88, 59 and 0 of those rows. Everything it misses is what an
embedding was supposed to recover.

Ranking every (missed requirement, confirmed skill) pair by cosine similarity
under the real `bge-small-en-v1.5`, the highest-scoring proposal in the entire
corpus is:

    0.797   required "Java"  <-  confirmed "Python"

and the rest of the top of that ranking is the same failure repeated: `macOS`
from Linux (0.764), `Azure` from AWS (0.750), `Excel` from SQL (0.742),
`Windows` from Linux (0.736), `TensorFlow` from PyTorch (0.725), `Google Cloud`
from AWS (0.705), `Kubernetes` from Docker (0.699).

The single relation in this corpus a person would actually defend — the
requirement `Machine Learning` against somebody whose confirmed skills include
PyTorch and whose project trained a reranker — scores **0.624**, below every
one of them.

## Why that is structural and not a tuning problem

Cosine similarity between two technology names measures **topical relatedness**.
Substitutability is what a match claim needs, and the two run *opposite* to each
other over exactly the pairs that matter: Java and Python are maximally related
and not remotely substitutable, and it is precisely because they are siblings
that the model puts them together. The strongest signal the layer produces is
its most dangerous output.

So there is no threshold to find. Any cut low enough to admit the one defensible
relation admits at least eight fabricated qualifications first, and each of those
is I2 — *never fabricate a user qualification* — failing in the exact way I2 was
written to prevent, with a character span on both sides making it look audited.

The span rule (§2) does not save it either, and that is the part worth stating
plainly because the plan assumed otherwise. A proposal of "you have Java" quoting
the posting's word *Java* and the user's word *Python* satisfies both spans
literally. **Spans prove provenance, not entailment.** They guarantee that both
strings were really written by the parties named; they say nothing about whether
one implies the other.

## What the vocabulary already covers, and what is actually left

Every case where two different strings denote the *same* technology is already
handled by `data/skills.yaml`'s alias table — `golang`/`Go`, `cpp`/`C++`. So the
residue an embedding is offered is, by construction, pairs of strings that denote
*different* technologies. There is no honest match hiding in there to find.

The one real gap the measurement did surface is a different shape: concept terms
like `Machine Learning` (26 occurrences), `Distributed Systems` (4) and
`Data Structures` (3), which somebody may genuinely demonstrate through a
concrete tool. That is an ontology edge — "PyTorch is evidence of machine
learning" — and the honest way to carry it is a `demonstrates:` relation in the
vocabulary file, reviewable and diffable, not a similarity number. Recorded in
ADR 0018 as the constructive successor; not built here.

## What this file is for

The decision not to ship a feature is normally invisible, which is how it gets
quietly reversed. These tests make it a thing that can go red:

- the rules-only baseline is pinned, so the "what was missed" figure is real;
- the inverted ordering is asserted against the real model, so a future model
  that fixes it turns this file red and reopens ADR 0018 on evidence;
- and nothing the scorer produces is allowed to claim an embedding proposed it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nightshift.db.base import EvidenceSource, MatchComponent
from nightshift.domain.embeddings import cosine_similarity, default_embedder, real_model_available
from nightshift.domain.matching_weights import load_weights
from nightshift.domain.scoring import ScoringProfile, score_match
from tests.matching_corpus import AS_OF, CorpusPosting, load_profiles, required_technologies

#: What the rules-only scorer matched on 2026-08-10, per fixture profile, out of
#: 240 `required` technology rows each. Pinned rather than described: §1.1 says
#: the embedding is measured "against a rules-only baseline", and a baseline
#: recorded only in prose is one nobody can check moved.
RULES_ONLY_BASELINE: dict[str, int] = {
    "new_grad_backend": 90,
    "experienced_ml": 88,
    "early_career_no_experience": 59,
    "states_nothing": 0,
}

#: Every profile sees every posting, so the denominator is shared.
REQUIRED_ROWS_PER_PROFILE = 240

#: 71 of the 153 recorded postings name at least one required technology. The
#: other 82 are Q6's finding — the reason `assessed_out_of` exists at all.
POSTINGS_NAMING_A_REQUIRED_TECHNOLOGY = 71

#: The one (requirement, confirmed skill) pair in this corpus that a person
#: would defend: PyTorch is genuine evidence of machine learning. It is the
#: ceiling any threshold would have to clear to be worth having.
DEFENSIBLE = ("Machine Learning", "PyTorch")

#: Pairs that name two different technologies. Matching any of these to a
#: requirement asserts a qualification the person never claimed, which is I2.
FABRICATIONS = (
    ("Java", "Python"),
    ("macOS", "Linux"),
    ("Azure", "AWS"),
    ("Excel", "SQL"),
    ("Windows", "Linux"),
    ("TensorFlow", "PyTorch"),
    ("Google Cloud", "AWS"),
    ("Kubernetes", "Docker"),
)

needs_the_real_model = pytest.mark.skipif(
    not real_model_available(),
    reason="embedding model not downloaded — run `make model`",
)


# ---------------------------------------------------------------------------
# The rules-only baseline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Missed:
    """One required technology the rules did not match, and who missed it."""

    profile: str
    term: str
    posting_key: str


def _matched_and_missed(
    corpus: tuple[CorpusPosting, ...],
    profiles: tuple[tuple[str, ScoringProfile], ...],
) -> tuple[dict[str, int], tuple[Missed, ...]]:
    """Run the real scorer and read what its evidence covers.

    Deliberately not a reimplementation of the matching rule. The question is
    what *this product* misses, so the answer has to come out of the same
    function the product calls — a second implementation would measure a
    scorer that does not exist.
    """
    weights = load_weights()
    matched: dict[str, int] = {}
    missed: list[Missed] = []

    for name, profile in profiles:
        hits = 0
        for entry in corpus:
            required = required_technologies(entry.posting)
            if not required:
                continue
            score = score_match(entry.posting, profile, weights=weights, as_of=AS_OF)
            covered = {
                row.requirement.value
                for row in score.evidence
                if row.component in (MatchComponent.SKILL, MatchComponent.PROJECT)
                and row.requirement is not None
            }
            for requirement in required:
                if requirement.value in covered:
                    hits += 1
                else:
                    missed.append(
                        Missed(profile=name, term=requirement.value, posting_key=entry.key)
                    )
        matched[name] = hits

    return matched, tuple(missed)


def test_the_corpus_denominator_is_what_the_measurement_assumed(
    scoring_corpus: tuple[CorpusPosting, ...],
) -> None:
    """71 postings, 240 required rows. Everything below divides by these."""
    with_required = [c for c in scoring_corpus if required_technologies(c.posting)]

    assert len(with_required) == POSTINGS_NAMING_A_REQUIRED_TECHNOLOGY
    assert sum(len(required_technologies(c.posting)) for c in with_required) == (
        REQUIRED_ROWS_PER_PROFILE
    )


def test_the_rules_only_baseline_is_what_task_11_was_measured_against(
    scoring_corpus: tuple[CorpusPosting, ...],
) -> None:
    """The figure ADR 0018 quotes, as an assertion rather than a sentence.

    If the vocabulary grows or a fixture profile changes, this goes red and the
    ADR's arithmetic has to be re-read — which is the point. The decision not to
    ship rests on these numbers, so they are not allowed to drift silently.
    """
    matched, missed = _matched_and_missed(scoring_corpus, load_profiles())

    assert matched == RULES_ONLY_BASELINE
    assert len(missed) == sum(
        REQUIRED_ROWS_PER_PROFILE - hit for hit in RULES_ONLY_BASELINE.values()
    )


# ---------------------------------------------------------------------------
# What the embedding would have proposed
# ---------------------------------------------------------------------------


@needs_the_real_model
class TestTheProposalsTheEmbeddingWouldMake:
    """The real model, over the real corpus. A stub would prove nothing here —
    `StubEmbedder` hashes trigrams, and every claim in this class is about
    semantics, which is exactly the property it does not have."""

    @staticmethod
    def _ranked(
        corpus: tuple[CorpusPosting, ...],
        profiles: tuple[tuple[str, ScoringProfile], ...],
    ) -> list[tuple[float, str, str]]:
        """Every (missed requirement, confirmed skill) pair, best first.

        Cheap despite the corpus size: the distinct strings are 55 required
        technologies and 13 confirmed skills, so the cache does ~68 embeddings
        for thousands of pairs.
        """
        _, missed = _matched_and_missed(corpus, profiles)
        skills_by_profile = {name: profile.skills for name, profile in profiles}
        embedder = default_embedder()
        cache: dict[str, tuple[float, ...]] = {}

        def vector(text: str) -> tuple[float, ...]:
            if text not in cache:
                cache[text] = embedder.embed([text])[0]
            return cache[text]

        best: dict[tuple[str, str], float] = {}
        for entry in missed:
            for skill in skills_by_profile[entry.profile]:
                pair = (entry.term, skill.name)
                if pair not in best:
                    best[pair] = cosine_similarity(vector(entry.term), vector(skill.name))
        return sorted(((sim, term, skill) for (term, skill), sim in best.items()), reverse=True)

    def test_the_highest_ranked_proposal_in_the_corpus_is_a_fabrication(
        self, scoring_corpus: tuple[CorpusPosting, ...]
    ) -> None:
        """`Java` from `Python`, at 0.797.

        The single most confident thing this layer would say, across every
        posting and every profile, is a qualification the person does not have.
        """
        ranked = self._ranked(scoring_corpus, load_profiles())
        similarity, term, skill = ranked[0]

        assert (term, skill) == ("Java", "Python"), (
            f"the top proposal is now {term!r} from {skill!r} at {similarity:.3f}; "
            "ADR 0018 rests on what sits at the top of this ranking, so re-read it"
        )
        assert similarity > 0.79

    def test_no_threshold_admits_the_defensible_relation_without_fabrications_first(
        self, scoring_corpus: tuple[CorpusPosting, ...]
    ) -> None:
        """The decisive measurement, and the reason there is nothing to tune.

        A threshold is only useful if the things worth keeping sit above it and
        the things worth dropping sit below. Here the ordering is inverted:
        every named fabrication outranks the one relation worth having, so the
        cut that keeps the good match has already kept eight bad ones.
        """
        ranked = self._ranked(scoring_corpus, load_profiles())
        by_pair = {(term, skill): sim for sim, term, skill in ranked}

        floor = by_pair[DEFENSIBLE]
        outranking = [pair for pair in FABRICATIONS if by_pair[pair] > floor]

        assert outranking == list(FABRICATIONS), (
            f"{DEFENSIBLE} scores {floor:.3f} and these no longer outrank it: "
            f"{sorted(set(FABRICATIONS) - set(outranking))}. The model's ordering has "
            "changed and ADR 0018's central claim needs re-measuring."
        )

    def test_the_layer_would_have_been_large_rather_than_negligible(
        self, scoring_corpus: tuple[CorpusPosting, ...]
    ) -> None:
        """Recording the size, because "we tried it and it did nothing" would be
        the wrong lesson to leave behind.

        At 0.70 the layer adds 44, 58 and 43 requirement rows on the three
        profiles that state anything — +49%, +66% and +73% on top of what the
        rules matched. At 0.50 it matches essentially everything the vocabulary
        missed and above 0.80 it matches nothing, so the whole usable band sits
        inside the confusion zone. It was never rejected for being ineffective.
        It was rejected for being wrong.
        """
        ranked = self._ranked(scoring_corpus, load_profiles())

        admitted_at_070 = [pair for sim, *pair in ranked if sim >= 0.70]
        admitted_at_050 = [pair for sim, *pair in ranked if sim >= 0.50]

        assert len(admitted_at_070) >= 15
        # And at a cut low enough to be called generous, it matches essentially
        # everything the vocabulary missed — which is the same statement as
        # "this signal does not discriminate".
        assert len(admitted_at_050) > 4 * len(admitted_at_070)


# ---------------------------------------------------------------------------
# The decision, kept true
# ---------------------------------------------------------------------------


def test_the_scorer_emits_no_evidence_row_an_embedding_proposed(
    scoring_corpus: tuple[CorpusPosting, ...],
) -> None:
    """`EvidenceSource.EMBEDDING` exists and nothing produces it. On purpose.

    The enum member, the API field and `MatchPanel`'s "proposed by the
    embedding" branch all stay. They are not decoration and they are not a
    half-built feature: if a row with that source ever did arrive, rendering it
    as "matched by a vocabulary rule" would be the failure worth preventing.
    An unreachable branch that is correct beats a reachable branch that lies.

    Deleting this test is the honest way to ship a proposal path — it is the
    tripwire that sends the next person to ADR 0018 first.
    """
    weights = load_weights()
    sources = {
        row.proposed_by
        for entry in scoring_corpus
        for _, profile in load_profiles()
        for row in score_match(entry.posting, profile, weights=weights, as_of=AS_OF).evidence
    }

    assert sources == {EvidenceSource.RULE}
