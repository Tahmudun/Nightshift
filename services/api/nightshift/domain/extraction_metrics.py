"""Precision and recall, defined once so two graders cannot disagree.

Reported separately and never averaged into one number: an extractor that
proposes nothing has perfect precision, and one that proposes everything has
perfect recall. A single figure hides both failures.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        """Of what was proposed, how much was right. 1.0 when nothing was."""
        proposed = self.true_positives + self.false_positives
        return 1.0 if proposed == 0 else self.true_positives / proposed

    @property
    def recall(self) -> float:
        """Of what was there, how much was found. 1.0 when there was nothing."""
        present = self.true_positives + self.false_negatives
        return 1.0 if present == 0 else self.true_positives / present


def score_sets(predicted: set[str], expected: set[str]) -> Score:
    lowered_pred = {p.casefold() for p in predicted}
    lowered_exp = {e.casefold() for e in expected}
    return Score(
        true_positives=len(lowered_pred & lowered_exp),
        false_positives=len(lowered_pred - lowered_exp),
        false_negatives=len(lowered_exp - lowered_pred),
    )
