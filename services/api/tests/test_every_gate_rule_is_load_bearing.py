"""Neuter each gate rule in turn and watch a named case go red.

`matching.md` §8 asks for mutation testing on the gate specifically, and gives
the reason: this project has found three tests that could not fail, and the gate
is where that would be most expensive. A rule nobody notices the absence of is a
rule that could be deleted tomorrow by someone tidying up.

Run as a test rather than as a one-off exercise a human did once and wrote down.
A mutation result recorded in a review is true on the day it was written; a
mutation result in the suite is true every time the suite runs.

The mutation is the realistic one: each rule is replaced by a version that
returns `passes` unconditionally, which is what a rule looks like after somebody
deletes the branch they did not understand. If the verdict is unchanged, the
rule was decorative.
"""

from __future__ import annotations

from typing import Any

import pytest

from nightshift.db.base import EligibilityState, WorkAuthorization
from nightshift.domain import eligibility
from nightshift.domain.eligibility import SeekerProfile, evaluate
from tests.test_eligibility_gate import reading

#: rule function name -> (posting, person, the verdict the rule is responsible
#: for). Each row is a case from `test_eligibility_gate.py`, so a failure here
#: points at a test that exists rather than at a scenario invented for the
#: mutation.
CASES: dict[str, tuple[Any, SeekerProfile, EligibilityState]] = {
    "_degree_rule": (
        reading(degree="phd"),
        SeekerProfile(degree="bachelors"),
        EligibilityState.INELIGIBLE,
    ),
    "_graduation_rule": (
        reading(graduation_window="2026-2027"),
        SeekerProfile(graduation_year=2024),
        EligibilityState.INELIGIBLE,
    ),
    "_years_rule": (
        reading(min_years_experience=10),
        SeekerProfile(years_experience=1),
        EligibilityState.LIKELY_INELIGIBLE,
    ),
    "_enrollment_rule": (
        reading(enrollment_required="yes"),
        SeekerProfile(is_enrolled=False),
        EligibilityState.INELIGIBLE,
    ),
    "_authorization_rule": (
        reading(sponsorship="not_offered"),
        SeekerProfile(work_authorization=WorkAuthorization.NEEDS_SPONSORSHIP),
        EligibilityState.INELIGIBLE,
    ),
}


def _neutered(*_args: object, **_kwargs: object) -> tuple[str, str]:
    return "passes", "neutered by the mutation harness"


@pytest.mark.parametrize("rule_name", sorted(CASES))
def test_neutering_a_rule_changes_the_verdict(
    rule_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    posting, person, expected = CASES[rule_name]

    assert evaluate(posting, person).state is expected, (
        f"{rule_name}'s case does not produce {expected} before the mutation, "
        "so the mutation below would prove nothing"
    )

    # `_RULES` holds direct function references captured at import, so patching
    # `eligibility._degree_rule` would leave the tuple pointing at the original
    # and every mutation below would pass for the wrong reason. The tuple is
    # rebuilt instead. `test_the_harness_itself_is_not_vacuous` is what would
    # catch it if this were ever done the easy way.
    patched = tuple(
        (dimension, kind, _neutered if rule.__name__ == rule_name else rule)
        for dimension, kind, rule in eligibility._RULES  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(eligibility, "_RULES", patched)

    assert evaluate(posting, person).state is not expected, (
        f"{rule_name} can be replaced by an unconditional pass without changing "
        "the verdict — it is not doing anything"
    )


def test_every_rule_in_the_gate_has_a_case_here() -> None:
    """A rule added without a mutation case is a rule this file silently skips.

    The same guard `test_every_label_field_is_graded_or_named` provides one
    layer down, and for the same reason: the failure mode is a check that looks
    complete because nothing counts what it is missing.
    """
    in_the_gate = {rule.__name__ for _, _, rule in eligibility._RULES}  # type: ignore[attr-defined]
    assert in_the_gate == set(CASES), {
        "in the gate but not mutated": sorted(in_the_gate - set(CASES)),
        "mutated but not in the gate": sorted(set(CASES) - in_the_gate),
    }


def test_the_harness_itself_is_not_vacuous() -> None:
    """The mutation must be capable of changing a verdict at all.

    If `_neutered` did not match the rule signature, or `_RULES` were rebuilt
    wrongly, every mutation above would raise rather than assert — and a raise
    inside `evaluate` would still fail the test, but for the wrong reason and
    with a misleading message. This runs the mutation on every rule at once and
    asserts the outcome is the one an all-passing gate must give.
    """
    all_passing = tuple(
        (dimension, kind, _neutered)
        for dimension, kind, _ in eligibility._RULES  # type: ignore[attr-defined]
    )
    original = eligibility._RULES  # type: ignore[attr-defined]
    try:
        eligibility._RULES = all_passing  # type: ignore[attr-defined]
        demanding = reading(
            degree="phd",
            graduation_window="2020-2021",
            min_years_experience=15,
            enrollment_required="yes",
            sponsorship="not_offered",
        )
        verdict = evaluate(demanding, SeekerProfile(degree="none", is_enrolled=False))
        assert verdict.state is EligibilityState.ELIGIBLE
        assert verdict.blockers == ()
    finally:
        eligibility._RULES = original  # type: ignore[attr-defined]
