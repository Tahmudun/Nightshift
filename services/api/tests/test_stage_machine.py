"""The stage machine: classify, never block.

PRODUCT-SPEC §10.2 requires the user can always set and correct a stage, so
this machine has no rejection branch for a transition. What it has is a
classification, recorded on the event, so the history stays honest without the
product telling its user they are wrong about their own job search.

The fixture is hand-written from the design's table. A generated one would
restate the function and assert nothing, so the coverage and count tests below
exist to prove the fixture is complete and is not all one answer.
"""

from __future__ import annotations

import itertools
from collections import Counter
from pathlib import Path

import pytest
import yaml

from nightshift.db.base import ApplicationStage, TransitionClass
from nightshift.domain.applications import (
    STAGE_ORDER,
    TERMINAL_STAGES,
    SameStageError,
    classify_transition,
)

FIXTURE = Path(__file__).parent / "fixtures" / "stage_transitions.yaml"


def _grid() -> dict[tuple[str, str], str]:
    raw = yaml.safe_load(FIXTURE.read_text())
    return {
        (from_stage, to_stage): verdict
        for from_stage, targets in raw.items()
        for to_stage, verdict in targets.items()
    }


GRID = _grid()


def test_the_fixture_covers_every_ordered_pair_exactly_once() -> None:
    """A grid with a hole is a grid that passes by not asking."""
    expected = {(a.value, b.value) for a, b in itertools.permutations(ApplicationStage, 2)}
    assert set(GRID) == expected
    assert len(GRID) == 90


def test_the_fixture_is_not_all_one_answer() -> None:
    """Non-vacuity: a grid of 90 `correction`s would pass a weaker test."""
    counts = Counter(GRID.values())
    assert counts == {"correction": 36, "advance": 27, "reopen": 27}


@pytest.mark.parametrize(("pair", "expected"), sorted(GRID.items()))
def test_transition_is_classified(pair: tuple[str, str], expected: str) -> None:
    from_stage, to_stage = pair
    assert classify_transition(
        ApplicationStage(from_stage), ApplicationStage(to_stage)
    ) is TransitionClass(expected)


def test_a_no_op_is_not_a_transition() -> None:
    """Writing `applied -> applied` would bury the real transitions.

    Same reasoning as `apply_freshness`, which skips a decision that does not
    change the status rather than writing a row per poll.
    """
    with pytest.raises(SameStageError):
        classify_transition(ApplicationStage.APPLIED, ApplicationStage.APPLIED)


def test_the_ordered_stages_and_the_terminal_ones_partition_the_enum() -> None:
    """No stage may be in both sets, and none may be in neither."""
    assert set(STAGE_ORDER).isdisjoint(TERMINAL_STAGES)
    assert set(STAGE_ORDER) | TERMINAL_STAGES == set(ApplicationStage)


def test_saved_to_offer_is_a_correction_not_a_refusal() -> None:
    """The design's own example, asserted by name so it cannot drift.

    A machine that refused this would violate §10.2. A machine that called it
    an advance would lose the fact that five stages were skipped.
    """
    assert (
        classify_transition(ApplicationStage.SAVED, ApplicationStage.OFFER)
        is TransitionClass.CORRECTION
    )
