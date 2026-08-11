"""Change each tunable number in turn and watch the golden corpus move.

`matching.md` §8 asks for mutation testing and gives the reason: this project
has found three tests that could not fail. M3b's
`test_every_gate_rule_is_load_bearing` is the same idea aimed at the gate's
rules; this is it aimed at the score's *numbers*.

The M3c plan's Task 7 says "zero each weight, a named test goes red". This file
does that and then keeps going, because the six weights are not the only numbers
in `data/matching.yaml` that move a score — the two penalty ceilings and all
eleven thresholds do too, and a decorative threshold is exactly as invisible as
a decorative weight.

## The named test is the golden file, and that is not a shortcut

No unit test in `test_scoring.py` reads `data/matching.yaml`: every component
takes its weight as a parameter, which is deliberate — it is what keeps those
tests stable when Task 7's successor tunes the numbers. So the golden test is
the only test a weight change can turn red, and this file asserts exactly that
by rendering the golden document under the mutated number and checking it
differs from the committed one.

That makes the kill stronger than a hand-picked case rather than weaker: the
assertion is over 612 real scores from 153 recorded postings, and the count of
scores that moved is reported, so a number that moves exactly one obscure
posting shows up as one rather than as a pass.

## The mutation bypasses the loader on purpose

`parse_weights` refuses a zeroed weight (the six must sum to 100) and a zeroed
per-unit threshold. Both refusals are correct and both are tested. The harness
constructs `MatchingWeights` directly instead, which is the only way to ask
"what would this number's absence look like" about a number the loader exists
to stop reaching production.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from nightshift.domain.matching_weights import (
    COMPONENT_NAMES,
    PENALTY_NAMES,
    THRESHOLD_NAMES,
    MatchingWeights,
    load_weights,
)
from nightshift.domain.scoring import ScoringProfile, score_match
from nightshift.domain.skill_vocabulary import load_vocabulary
from tests.matching_corpus import AS_OF, CorpusPosting, load_profiles
from tests.test_matching_golden import _blocks, render_golden

#: How each threshold is mutated. A threshold is not a weight — "zero it" is
#: meaningless for a rung that is already 0 and for a window whose lower bound
#: is 7 — so each one names the smallest change that could plausibly be a typo,
#: which is the mutation worth defending against.
THRESHOLD_MUTATION: dict[str, int] = {
    "freshness_days.full": +1,
    "freshness_days.zero": -1,
    "missing_requirement.per_requirement": +1,
    "seniority_mismatch.per_year": +1,
    "seniority_years.internship": +1,
    "seniority_years.new_grad": +1,
    "seniority_years.junior": +1,
    "seniority_years.mid": +1,
    "seniority_years.senior": +1,
    "seniority_years.staff": +1,
    "seniority_years.director": +1,
}


@dataclass(frozen=True)
class Baseline:
    """The corpus, the profiles, and what the committed numbers score them."""

    corpus: tuple[CorpusPosting, ...]
    profiles: tuple[tuple[str, ScoringProfile], ...]
    blocks: dict[str, str]

    def moved_under(self, weights: MatchingWeights) -> list[str]:
        """Which scores this set of numbers renders differently. Names, not a count."""
        after = _blocks(_render(self.corpus, self.profiles, weights))
        return sorted(key for key, block in self.blocks.items() if after.get(key) != block)


@pytest.fixture(scope="module")
def baseline(scoring_corpus: tuple[CorpusPosting, ...]) -> Baseline:
    corpus = scoring_corpus
    profiles = load_profiles()
    return Baseline(
        corpus=corpus,
        profiles=profiles,
        blocks=_blocks(_render(corpus, profiles, load_weights())),
    )


def _render(
    corpus: tuple[CorpusPosting, ...],
    profiles: tuple[tuple[str, ScoringProfile], ...],
    weights: MatchingWeights,
) -> str:
    scores = {
        (entry.key, name): score_match(
            entry.posting,
            profile,
            weights=weights,
            as_of=AS_OF,
            demonstrates=load_vocabulary().edges,
        )
        for entry in corpus
        for name, profile in profiles
    }
    return render_golden(corpus, profiles, scores)


# ---------------------------------------------------------------------------
# The six weights
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("component", COMPONENT_NAMES)
def test_zeroing_a_component_weight_moves_the_golden_corpus(
    component: str, baseline: Baseline
) -> None:
    """The six kills the plan asks for.

    A component whose weight can go to zero without moving a score is a
    component contributing nothing to any posting in the corpus — either the
    rule never fires or the corpus cannot exercise it, and both mean the weight
    beside its name is decoration.
    """
    weights = load_weights()
    mutated = replace(weights, components={**weights.components, component: 0})

    moved = baseline.moved_under(mutated)

    assert moved, (
        f"components.{component} can be set to 0 without changing a single one of "
        f"{len(baseline.blocks)} scores — the golden test would stay green and "
        "the component is not doing anything"
    )


# ---------------------------------------------------------------------------
# The two penalty ceilings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("penalty", PENALTY_NAMES)
def test_zeroing_a_penalty_ceiling_moves_the_golden_corpus(
    penalty: str, baseline: Baseline
) -> None:
    """A ceiling of 0 is the penalty deleted. If nothing moves, it already was."""
    weights = load_weights()
    mutated = replace(weights, penalties={**weights.penalties, penalty: 0})

    moved = baseline.moved_under(mutated)

    assert moved, f"penalties.{penalty} can be set to 0 without changing any score"


# ---------------------------------------------------------------------------
# The eleven thresholds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("threshold", THRESHOLD_NAMES)
def test_moving_a_threshold_by_one_moves_the_golden_corpus(
    threshold: str, baseline: Baseline
) -> None:
    """Every rung of the seniority ladder included, and five of them only pass
    because of a profile this test is the reason for.

    Measured on 2026-08-09 with three fixture profiles: `internship` and
    `new_grad` moved **zero** scores, and `junior` moved zero downwards. `gap`
    is `max(0, implied - years)`, so a rung only ever bites somebody below it,
    and no profile stated a number small enough. The fix was a fourth fixture
    profile at `years_experience: 0` — which was a gap worth closing on its own,
    because somebody with no professional experience yet is this product's user
    and the fixture set had nobody in it.
    """
    weights = load_weights()
    delta = THRESHOLD_MUTATION[threshold]
    mutated = replace(
        weights, thresholds={**weights.thresholds, threshold: weights.thresholds[threshold] + delta}
    )

    moved = baseline.moved_under(mutated)

    assert moved, (
        f"thresholds.{threshold} can move by {delta:+d} without changing any of "
        f"{len(baseline.blocks)} scores — no posting or profile in the corpus "
        "exercises it, so nothing would catch it being wrong"
    )


def test_every_threshold_has_a_mutation() -> None:
    """A threshold added without a mutation is a threshold this file skips.

    The same guard M3b's mutation harness carries, and for the same reason: the
    failure mode is a check that looks complete because nothing counts what it
    is missing.
    """
    assert set(THRESHOLD_MUTATION) == set(THRESHOLD_NAMES), {
        "in the file but not mutated": sorted(set(THRESHOLD_NAMES) - set(THRESHOLD_MUTATION)),
        "mutated but not in the file": sorted(set(THRESHOLD_MUTATION) - set(THRESHOLD_NAMES)),
    }


# ---------------------------------------------------------------------------
# The harness itself
# ---------------------------------------------------------------------------


def test_the_harness_reports_no_movement_when_nothing_is_mutated(
    baseline: Baseline,
) -> None:
    """Without this, every assertion above could be passing for free.

    If `_render` were non-deterministic, or `_blocks` keyed on something that
    changes run to run, every mutation would report movement and every kill
    above would be a false positive — a mutation harness that always says yes is
    worth less than no harness, because it certifies rules it never tested.
    """
    assert baseline.moved_under(load_weights()) == []


def test_the_harness_can_tell_which_scores_moved(baseline: Baseline) -> None:
    """It reports names, not a count, because a count cannot be checked.

    A weight that moves exactly one obscure posting passes the kill above and
    should be visible as such; the list is what makes that visible in a failure
    message and in the report below.
    """
    weights = load_weights()
    one_rung = replace(weights, thresholds={**weights.thresholds, "seniority_years.junior": 2})

    moved = baseline.moved_under(one_rung)

    assert 0 < len(moved) < len(baseline.blocks)
    assert all(" · " in key for key in moved), moved[:3]


def test_report_the_numbers(baseline: Baseline, capsys: pytest.CaptureFixture[str]) -> None:
    """Print what each number is worth across the corpus. Asserts nothing.

    Reported rather than gated, for M3a's reason: a floor set before measuring
    is either unreachable or vacuous and there is no way to tell from outside.
    The numbers belong in the M3c review, and the way to get them is to run
    this file with `-s`.
    """
    weights = load_weights()
    total = len(baseline.blocks)
    lines = [f"scores in the corpus: {total}"]

    for component in COMPONENT_NAMES:
        mutated = replace(weights, components={**weights.components, component: 0})
        lines.append(f"  components.{component:<24} 0  {len(baseline.moved_under(mutated))}")
    for penalty in PENALTY_NAMES:
        mutated = replace(weights, penalties={**weights.penalties, penalty: 0})
        lines.append(f"  penalties.{penalty:<25} 0  {len(baseline.moved_under(mutated))}")
    for threshold in THRESHOLD_NAMES:
        delta = THRESHOLD_MUTATION[threshold]
        mutated = replace(
            weights,
            thresholds={**weights.thresholds, threshold: weights.thresholds[threshold] + delta},
        )
        lines.append(
            f"  thresholds.{threshold:<36} {delta:+d}  {len(baseline.moved_under(mutated))}"
        )

    with capsys.disabled():
        print("\n" + "\n".join(lines))
