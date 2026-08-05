"""Precision and recall, and the reason they are never averaged."""

from __future__ import annotations

import pytest

from nightshift.domain.extraction_metrics import score_sets


def test_a_perfect_match_scores_one_on_both() -> None:
    s = score_sets({"Kotlin"}, {"Kotlin"})
    assert (s.precision, s.recall) == (1.0, 1.0)


def test_proposing_nothing_has_perfect_precision_and_no_recall() -> None:
    """The reason the two are never averaged."""
    s = score_sets(set(), {"Kotlin", "Python"})
    assert s.precision == 1.0
    assert s.recall == 0.0


def test_proposing_everything_has_perfect_recall_and_poor_precision() -> None:
    s = score_sets({"Kotlin", "Python", "Rust"}, {"Kotlin"})
    assert s.recall == 1.0
    assert s.precision == pytest.approx(1 / 3)


def test_matching_is_case_insensitive() -> None:
    assert score_sets({"kotlin"}, {"Kotlin"}).precision == 1.0
