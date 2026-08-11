"""Is the ranking any *good*? `matching.md` §7.3, and QUESTIONS Q5.

M3d Task 5. Every other measurement in this milestone grades the system against
what a posting *says* — a fact with a right answer a human can write down. This
one grades it against what a person *wants*, which is not a property of the
posting and cannot be read out of the answer key by construction.

So it needs the one thing no amount of engineering produces: somebody's
judgement. `services/api/tests/fixtures/relevance/ratings.yaml` is thirty
postings rated `good` / `acceptable` / `poor` on 2026-08-10, with the profile
they were rated against carried in the same file.

## Why the file carries its own profile

Because `poor` from a first-year student and `poor` from a staff engineer are
different claims about the same posting. Grading against whatever the database
holds on the day would make this metric a function of seed data — it would move
when nothing about the ranking had changed, and it would be reproducible on
nobody else's machine. Everything below is a pure function of two committed
files.

## Reported, not gated

M3a's rule, and there is a second reason here. A ranking metric over thirty items
with three relevance levels is a coarse instrument, and the corpus is nine
employers — all quant trading firms or AI labs, recorded for eligibility-rule
coverage rather than as a sample of New York tech. What this file reports is the
ranking's quality **over that slice, for that person**. Saying so is the
difference between a measurement and a number that sounds broader than it is.

`test_the_ratings_discriminate` is the guard that matters: the first rating pass
put 27 of 30 postings in one class, which is the ranking-metric form of a gate
answering `uncertain` to everything — every ordering scores about the same and
the metric reports nothing while looking like a success.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
import yaml

from nightshift.db.base import EligibilityState, WorkAuthorization
from nightshift.domain.eligibility import SeekerProfile, evaluate
from nightshift.domain.eligibility_reading import read_posting
from nightshift.domain.matching import BAND_ORDER
from nightshift.domain.matching_weights import load_weights
from nightshift.domain.scoring import ConfirmedSkill, ScoringProfile, score_match
from nightshift.domain.skill_vocabulary import load_vocabulary
from tests.matching_corpus import AS_OF, CorpusPosting, load_corpus

RATINGS_FILE = Path(__file__).parent / "fixtures" / "relevance" / "ratings.yaml"
CORPUS_DIR = Path(__file__).parent / "fixtures" / "eligibility"

#: `good` is worth twice `acceptable`, and `poor` is worth nothing. The gap
#: between the top two is what NDCG is actually measuring here — a ranker that
#: buries the `poor` rows and shuffles the rest scores well on precision@5 and
#: should not score well on this.
GAIN = {"good": 2.0, "acceptable": 1.0, "poor": 0.0}


def _board_tokens() -> dict[str, str]:
    """Fixture file stem -> the board token `load_corpus` keys postings by.

    Two keying schemes already exist in this repository — the answer-key tests
    use the file stem, the scoring corpus uses the token inside the meta file —
    and this is the join between them. Read rather than derived by stripping
    `_eligibility` off the stem, because a derivation that happens to work is a
    derivation nobody notices breaking.
    """
    tokens = {}
    for path in sorted(CORPUS_DIR.glob("*.meta.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        tokens[path.name.removesuffix(".meta.json")] = str(meta["provenance"]["board_token"])
    return tokens


def load_ratings() -> tuple[dict[str, Any], dict[str, str]]:
    """The profile block, and rating by corpus key."""
    raw = yaml.safe_load(RATINGS_FILE.read_text(encoding="utf-8"))
    tokens = _board_tokens()
    rated = {f"{tokens[row['board']]}/{row['id']}": row["rating"] for row in raw["ratings"]}
    return raw["profile"], rated


def profiles_from_block(block: dict[str, Any]) -> tuple[ScoringProfile, SeekerProfile]:
    """The rater, as the two dataclasses the two subsystems read.

    **Nothing here is inferred and three fields are deliberately absent.** The
    worksheet never asked for work authorization, enrollment, or a remote
    preference, so they stay unset — `unspecified` and `None`, which the gate
    reads as *this person has not told us* (I2). Filling them with plausible
    values would make the metric grade a person who does not exist.

    No projects, for the same reason: the rating profile lists skills and the
    worksheet asked for nothing else. Project evidence is therefore unassessable
    across all thirty, which narrows every denominator — and that is a true fact
    about what this person has told the system, not a defect to paper over.
    """
    vocabulary = load_vocabulary()
    year, _, month = str(block["graduation"]).partition("-")
    skills = tuple(
        ConfirmedSkill(name=name, taxonomy_id=vocabulary.canonical(name))
        for name in block["skills"]
    )
    return (
        ScoringProfile(
            skills=skills,
            preferred_roles=tuple(block["preferred_roles"]),
            preferred_locations=tuple(block["preferred_locations"]),
            years_experience=block["years_experience"],
        ),
        SeekerProfile(
            graduation_year=int(year),
            graduation_month=int(month),
            degree=block["degree"],
            years_experience=block["years_experience"],
            work_authorization=WorkAuthorization.UNSPECIFIED,
        ),
    )


def _sort_key(entry: tuple[str, Any, EligibilityState]) -> tuple[int, float, str]:
    """The product's own ordering (§5.3), not a second opinion about it.

    Band first, then the *fraction* rather than the raw total, then the key. A
    ranking metric computed over an order the product does not serve would be
    measuring something nobody sees — and `RankedMatches` sorts on the fraction
    because 40 out of 50 beats 45 out of 100. Nulls last, as the API's
    `unassessed_sort_last` puts them.
    """
    key, score, state = entry
    fraction = score.fraction
    return (BAND_ORDER.index(state), -(fraction if fraction is not None else -1.0), key)


@pytest.fixture(scope="module")
def ranked() -> dict[str, Any]:
    block, rated = load_ratings()
    scoring_profile, seeker_profile = profiles_from_block(block)
    weights = load_weights()
    corpus: dict[str, CorpusPosting] = {entry.key: entry for entry in load_corpus()}

    rows: list[tuple[str, Any, EligibilityState]] = []
    for key in rated:
        posting = corpus[key].posting
        score = score_match(
            posting,
            scoring_profile,
            weights=weights,
            as_of=AS_OF,
            demonstrates=load_vocabulary().edges,
        )
        state = evaluate(read_posting(list(posting.requirements)), seeker_profile).state
        rows.append((key, score, state))

    rows.sort(key=_sort_key)
    return {
        "order": [key for key, _, _ in rows],
        "rows": rows,
        "rated": rated,
        "gains": [GAIN[rated[key]] for key, _, _ in rows],
    }


def _dcg(gains: list[float]) -> float:
    return sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))


def ndcg_at(gains: list[float], k: int) -> float:
    """Discounted cumulative gain over the ideal ordering of the same ratings.

    `None` is impossible here and 0.0 is meaningful: it means every one of the
    top `k` was rated `poor`.
    """
    ideal = _dcg(sorted(gains, reverse=True)[:k])
    return _dcg(gains[:k]) / ideal if ideal else 0.0


def precision_at(gains: list[float], k: int) -> float:
    """The share of the top `k` the rater would actually open — `good` only.

    Counting `acceptable` here would make the number agree with itself: 23 of 30
    are `good` or `acceptable`, so almost any ordering scores above 0.75 and the
    metric stops discriminating. `good` is the class the product exists to
    surface.
    """
    return sum(1 for gain in gains[:k] if gain == GAIN["good"]) / k


def test_report_the_numbers(ranked: dict[str, Any], capsys: Any) -> None:
    """Always passes. Prints what the ranking does. Run with `-s`."""
    gains: list[float] = ranked["gains"]
    with capsys.disabled():
        print(f"\n  ranking quality over {len(gains)} rated postings, one profile\n")
        print(f"  NDCG@10      {ndcg_at(gains, 10):.3f}")
        print(f"  NDCG@30      {ndcg_at(gains, 30):.3f}")
        print(f"  precision@5  {precision_at(gains, 5):.3f}")
        print(f"  precision@10 {precision_at(gains, 10):.3f}\n")
        for rank, (key, score, state) in enumerate(ranked["rows"][:10], start=1):
            fraction = score.fraction
            shown = "  —  " if fraction is None else f"{fraction:.2f}"
            print(f"  {rank:>2}. {ranked['rated'][key]:<11}{shown}  {state.value:<18}{key}")
        print()


def test_the_ratings_discriminate(ranked: dict[str, Any]) -> None:
    """The guard the first rating pass failed.

    27 of 30 in one class makes every ordering score about the same, so the
    metrics above would report a number that measures nothing while reading as a
    success. This is the ranking-metric form of `uncertain`-for-everything, and
    it is why the ratings were re-done rather than used.
    """
    counts = {rating: list(ranked["rated"].values()).count(rating) for rating in GAIN}

    assert all(counts.values()), f"a rating class is empty: {counts}"
    assert max(counts.values()) <= 0.7 * len(ranked["rated"]), (
        f"one class holds most of the corpus: {counts} — every ordering scores alike"
    )


def test_the_ranking_is_not_the_rating_order(ranked: dict[str, Any]) -> None:
    """Anti-vacuity, and it catches the mistake that would flatter this file most.

    If the ordering were computed from the ratings — by a join gone wrong, or by
    somebody sorting the fixture — NDCG would be 1.000 and every test here would
    pass. The scorer has never seen a rating, so a perfect score is evidence of a
    bug rather than of quality.
    """
    assert ndcg_at(ranked["gains"], 30) < 1.0


def test_the_metrics_can_fail() -> None:
    """The instruments themselves, against orderings constructed here.

    A metric that returns the same number for the best and worst possible
    ordering is a metric that cannot report a regression, and this project has
    shipped three comparisons that could not see what they existed to find.
    """
    best = [2.0, 2.0, 1.0, 1.0, 0.0]
    worst = list(reversed(best))

    assert ndcg_at(best, 5) == 1.0
    assert ndcg_at(worst, 5) < 1.0
    assert precision_at(best, 5) == 0.4
    assert precision_at([0.0] * 5, 5) == 0.0
    # An all-`poor` top-k is 0.0 rather than undefined: the ordering exists and
    # is bad, which is a different statement from having nothing to rank.
    assert ndcg_at([0.0, 0.0], 2) == 0.0


def test_every_rated_posting_is_in_the_corpus(ranked: dict[str, Any]) -> None:
    """A rating whose posting cannot be found would be silently dropped, and the
    metric would then be computed over however many happened to join."""
    assert len(ranked["order"]) == len(ranked["rated"]) == 30
