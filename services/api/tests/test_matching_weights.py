"""The weights loader, and the committed file it refuses to score without.

Every test below is a small file that would produce a plausible number. That is
the whole point: a weights bug does not crash and does not look wrong. A
component typed as 3 instead of 30 still yields a score between 0 and 100, still
sorts, still renders, and is wrong for every job in the corpus.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from nightshift.db.base import Seniority
from nightshift.domain.matching_weights import (
    COMPONENT_NAMES,
    DEFAULT_WEIGHTS_PATH,
    PENALTY_NAMES,
    RULESET_LOGIC_VERSION,
    SENIORITY_LADDER,
    THRESHOLD_NAMES,
    WEIGHT_TOTAL,
    WeightsError,
    load_weights,
    parse_weights,
)


@pytest.fixture
def raw() -> dict[str, Any]:
    """The committed file, as data, so a test mutates a real shape."""
    return copy.deepcopy(yaml.safe_load(DEFAULT_WEIGHTS_PATH.read_text(encoding="utf-8")))


# -- the committed file --------------------------------------------------


def test_the_committed_weights_load_and_sum_to_one_hundred() -> None:
    weights = load_weights()
    assert set(weights.components) == set(COMPONENT_NAMES)
    assert set(weights.penalties) == set(PENALTY_NAMES)
    assert sum(weights.components.values()) == WEIGHT_TOTAL
    assert all(value < 0 for value in weights.penalties.values())


def test_the_ruleset_version_composes_both_halves() -> None:
    """§4.2: one column covers the rules *and* the weights. Two versions would
    let a rule change while the data version stayed put, and the acceptance
    criterion would pass over a result nobody can reproduce."""
    weights = load_weights()
    assert weights.ruleset_version == f"{RULESET_LOGIC_VERSION}+{weights.version}"
    assert weights.version in weights.ruleset_version
    assert weights.ruleset_version.count("+") == 1


def test_a_different_weights_file_is_a_different_ruleset_version(
    raw: dict[str, Any], tmp_path: Path
) -> None:
    raw["version"] = "2099-01-01.9"
    other = tmp_path / "matching.yaml"
    other.write_text(yaml.safe_dump(raw))
    assert load_weights(other).ruleset_version != load_weights().ruleset_version


# -- shown able to fail --------------------------------------------------


def test_a_weight_typed_short_by_a_digit_is_refused(raw: dict[str, Any]) -> None:
    """The sum-to-100 assertion, shown able to fail on the realistic mistake.

    30 typed as 3. Nothing crashes without this check: skill overlap simply
    stops mattering, every score in the corpus shifts down by up to 27 points,
    every existing test still passes, and the only visible symptom is a ranking
    that is quietly worse than it was.
    """
    raw["components"]["skill_overlap"] = 3
    with pytest.raises(WeightsError, match="sum to 73, not 100"):
        parse_weights(raw)


def test_weights_summing_over_one_hundred_are_refused(raw: dict[str, Any]) -> None:
    raw["components"]["role_relevance"] += 1
    with pytest.raises(WeightsError, match="sum to 101"):
        parse_weights(raw)


@pytest.mark.parametrize("name", COMPONENT_NAMES)
def test_every_component_is_required_by_name(raw: dict[str, Any], name: str) -> None:
    """A missing component is a component scoring zero for every job, forever.

    Parametrised over all six rather than spot-checked: this is the list a
    future component gets added to, and a check that covers five of six is a
    check that stops describing what it is named for — M3b's lesson, and the
    reason `PROFILE_COLUMNS` is now guarded against the real table.
    """
    del raw["components"][name]
    with pytest.raises(WeightsError, match=f"missing \\['{name}'\\]"):
        parse_weights(raw)


def test_a_component_the_code_does_not_read_is_refused(raw: dict[str, Any]) -> None:
    """`company_preference` is deferred (§5.1). Writing it into the file and
    having it silently ignored would look exactly like shipping it."""
    raw["components"]["company_preference"] = 0
    with pytest.raises(WeightsError, match="unknown"):
        parse_weights(raw)


@pytest.mark.parametrize("name", PENALTY_NAMES)
def test_a_penalty_written_positive_is_refused(raw: dict[str, Any], name: str) -> None:
    """A penalty that adds points is not a smaller bug than a wrong weight — it
    is the score meaning the opposite of what it says, on exactly the jobs the
    user is least suited to."""
    raw["penalties"][name] = abs(raw["penalties"][name])
    with pytest.raises(WeightsError, match="must be negative"):
        parse_weights(raw)


def test_a_penalty_of_zero_is_refused(raw: dict[str, Any]) -> None:
    """Zero is how a penalty is disabled by accident. Removing one is a
    deliberate change to §5.1 and belongs in a version bump, not in a digit."""
    raw["penalties"]["missing_requirement"] = 0
    with pytest.raises(WeightsError, match="must be negative"):
        parse_weights(raw)


@pytest.mark.parametrize("value", [12.5, "20", True, None])
def test_a_weight_that_is_not_a_whole_number_is_refused(raw: dict[str, Any], value: object) -> None:
    """`"20"` sums as a string concatenation error, `12.5` claims a precision
    nothing here can evidence, and `true` reads as 1 because Python says a bool
    is an int."""
    raw["components"]["listing_freshness"] = value
    with pytest.raises(WeightsError, match="whole number"):
        parse_weights(raw)


def test_a_negative_component_is_refused(raw: dict[str, Any]) -> None:
    raw["components"]["role_relevance"] = -20
    raw["components"]["skill_overlap"] = 70
    with pytest.raises(WeightsError, match="negative"):
        parse_weights(raw)


def test_a_component_worth_nothing_is_refused(raw: dict[str, Any]) -> None:
    """Added at M3c Task 9, and the sum-to-100 assertion does not cover it.

    Zero and 50 sum to 100, so this file passes every other check while role
    relevance has been removed from every score in the corpus — the same silent
    removal `test_a_weight_typed_short_by_a_digit_is_refused` catches, in the one
    shape that gets past it.

    It is also what `match_results_components_are_assessed` rests on: that trigger
    asserts a full denominator means every component was assessable, which is only
    true while an unassessable component necessarily narrows it. A zero weight
    would make a legal weights file produce scores the database refuses, with the
    error naming a row rather than the file that caused it.
    """
    raw["components"]["role_relevance"] = 0
    raw["components"]["skill_overlap"] = 50
    with pytest.raises(WeightsError, match="is 0; a component worth nothing"):
        parse_weights(raw)


@pytest.mark.parametrize("version", ["", "   ", None, 20260809])
def test_a_file_with_no_usable_version_is_refused(raw: dict[str, Any], version: object) -> None:
    """Every stored score names the version that produced it. A blank or numeric
    one makes `"<logic>+<data>"` unreadable and a stale row indistinguishable
    from a current one."""
    raw["version"] = version
    with pytest.raises(WeightsError, match="version"):
        parse_weights(raw)


@pytest.mark.parametrize("section", ["components", "penalties"])
def test_a_missing_section_is_refused(raw: dict[str, Any], section: str) -> None:
    del raw[section]
    with pytest.raises(WeightsError, match=section):
        parse_weights(raw)


def test_a_file_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(WeightsError, match="mapping"):
        parse_weights([20, 30, 20, 10, 10, 10])


# -- thresholds, added at Task 4 -----------------------------------------
#
# Freshness is the first rule with a tunable number in it, and §4.2 puts every
# threshold in the data file for the same reason it puts the weights there: a
# number that moves a score has to travel with the version stored on the row.


def test_the_committed_thresholds_load() -> None:
    weights = load_weights()

    assert set(weights.thresholds) == set(THRESHOLD_NAMES)
    assert weights.threshold("freshness_days.full") == 7
    assert weights.threshold("freshness_days.zero") == 90


def test_a_missing_threshold_is_refused(raw: dict[str, Any]) -> None:
    del raw["thresholds"]["freshness_days"]["full"]

    with pytest.raises(WeightsError, match="missing"):
        parse_weights(raw)


def test_a_threshold_the_code_has_never_heard_of_is_refused(raw: dict[str, Any]) -> None:
    """A weight nobody reads is a number somebody tuned and watched do nothing."""
    raw["thresholds"]["freshness_days"]["halfway"] = 30

    with pytest.raises(WeightsError, match="unknown"):
        parse_weights(raw)


def test_a_freshness_window_running_backwards_is_refused(raw: dict[str, Any]) -> None:
    """The realistic mistake, and it is silent.

    Swap the two and an ancient posting scores above a new one. Nothing crashes,
    every score stays between 0 and 100, and the ranked list is upside down on
    the one axis a person can check by eye.
    """
    raw["thresholds"]["freshness_days"] = {"full": 90, "zero": 7}

    with pytest.raises(WeightsError, match="runs backwards"):
        parse_weights(raw)


def test_equal_thresholds_are_refused(raw: dict[str, Any]) -> None:
    """`zero - full` is a divisor. Equal values are a ZeroDivisionError at
    scoring time, which is a crash in a worker rather than a load error."""
    raw["thresholds"]["freshness_days"] = {"full": 30, "zero": 30}

    with pytest.raises(WeightsError, match="must be below"):
        parse_weights(raw)


def test_a_negative_threshold_is_refused(raw: dict[str, Any]) -> None:
    raw["thresholds"]["freshness_days"]["full"] = -1

    with pytest.raises(WeightsError, match="negative"):
        parse_weights(raw)


def test_a_file_with_no_thresholds_at_all_is_refused(raw: dict[str, Any]) -> None:
    del raw["thresholds"]

    with pytest.raises(WeightsError, match="thresholds must be a mapping"):
        parse_weights(raw)


# -- the penalty thresholds, added at Task 5 -----------------------------
#
# Both penalties needed a curve, and §5.1 gives only their ceilings. The numbers
# that shape the curve are thresholds like any other and live in the file; how a
# curve *uses* them is logic and carries `RULESET_LOGIC_VERSION`.


def test_the_committed_penalty_thresholds_load() -> None:
    weights = load_weights()

    assert weights.threshold("missing_requirement.per_requirement") == 5
    assert weights.threshold("seniority_mismatch.per_year") == 6
    assert weights.threshold("seniority_years.internship") == 0
    assert weights.threshold("seniority_years.director") == 10


def test_the_seniority_ladder_names_every_level_the_classifier_can_produce() -> None:
    """A level with no implied years is a level the penalty silently skips.

    `Seniority` is the classifier's own output. If M3b ever gains a level and
    this file does not, the missing key is a posting the penalty cannot weigh —
    which looks exactly like a posting that deserves no penalty.

    `unclear` is the one member with no rung, and deliberately: it is "no rule
    could tell", and inventing years for it is inventing the mismatch.
    """
    levels = tuple(level.value for level in Seniority if level is not Seniority.UNCLEAR)
    assert levels == SENIORITY_LADDER
    assert "seniority_years.unclear" not in THRESHOLD_NAMES
    assert all(f"seniority_years.{level}" in THRESHOLD_NAMES for level in SENIORITY_LADDER)


def test_a_backwards_seniority_ladder_is_refused(raw: dict[str, Any]) -> None:
    """The freshness window's failure, one penalty over.

    Swap staff and junior and nothing crashes: every score stays in range, the
    penalty still fires, and a Lead posting now costs an early-career profile
    *less* than a Junior one. There is no error and no test that would notice.
    """
    raw["thresholds"]["seniority_years"]["junior"] = 8
    raw["thresholds"]["seniority_years"]["staff"] = 1

    with pytest.raises(WeightsError, match="does not rise"):
        parse_weights(raw)


def test_a_flat_seniority_ladder_is_refused(raw: dict[str, Any]) -> None:
    """Every level implying the same years is the penalty turned off in data.

    It is a valid file, it loads, and the seniority penalty is then zero for
    every posting in the corpus — which reads as "no posting is mispitched"
    rather than as "this rule stopped running".
    """
    for level in raw["thresholds"]["seniority_years"]:
        raw["thresholds"]["seniority_years"][level] = 3

    with pytest.raises(WeightsError, match="never rises"):
        parse_weights(raw)


def test_a_zero_per_requirement_is_refused(raw: dict[str, Any]) -> None:
    """Zero is the missing-requirement penalty deleted, spelled as a number."""
    raw["thresholds"]["missing_requirement"]["per_requirement"] = 0

    with pytest.raises(WeightsError, match="per_requirement"):
        parse_weights(raw)


def test_a_zero_per_year_is_refused(raw: dict[str, Any]) -> None:
    raw["thresholds"]["seniority_mismatch"]["per_year"] = 0

    with pytest.raises(WeightsError, match="per_year"):
        parse_weights(raw)
