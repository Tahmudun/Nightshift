"""The five eligibility fields nobody has ever graded.

M3a graded exactly one of the answer key's nine label fields — `required_tech`,
plus necessity. The extractor has been emitting `degree`, `graduation_window`,
`years_experience`, `enrollment` and `authorization` proposals since
`3722026`, against a key committed before any of those rules existed, and no
test has ever compared one of them to a label.

This is that comparison. It is written **before** any of the rules it grades are
changed, so the first numbers it prints are a baseline rather than a result.
`matching.md` §1.1 is the reason the ordering matters: an evaluation written
after the thing it evaluates reports a number that measures nothing.

Floors are set from measurement, per the rule M3a established. They are absent
from this file on purpose until Task 1's numbers are recorded in PROGRESS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from nightshift.domain.eligibility_labels import PostingLabel, load_answer_key
from nightshift.domain.eligibility_reading import PostingReading, read_posting
from nightshift.domain.requirement_extraction import extract_requirements
from nightshift.domain.skill_vocabulary import load_vocabulary
from tests.test_requirement_extraction_against_the_answer_key import _corpus_postings

#: Every field compared, and how the label spells it. Kept as data rather than
#: as five near-identical loops so a field cannot be silently dropped from the
#: report — `test_every_label_field_is_graded_or_named` fails if one is.
GRADED_FIELDS: tuple[str, ...] = (
    "degree",
    "graduation_window",
    "min_years_experience",
    "enrollment_required",
    "sponsorship",
)

#: Label fields this file deliberately does not grade, with the reason. A field
#: in neither tuple is a field nobody decided about.
NOT_GRADED_HERE: dict[str, str] = {
    "title": "not a requirement; it is how the posting is identified",
    "note": "free text the labeler wrote for a human, with no predicted counterpart",
    "required_tech": "graded in test_requirement_extraction_against_the_answer_key",
    "mentioned_not_required": "same file",
    "is_internship": "no rule produces it yet — it arrives with the M3b classifier",
}


@dataclass
class FieldTally:
    """Right, wrong, and what the wrong ones looked like."""

    right: int = 0
    wrong: int = 0
    confusions: dict[tuple[str, str], int] | None = None

    def __post_init__(self) -> None:
        if self.confusions is None:
            self.confusions = {}

    def record(self, predicted: object, expected: object) -> None:
        if predicted == expected:
            self.right += 1
            return
        self.wrong += 1
        assert self.confusions is not None
        seen = (f"{predicted}", f"{expected}")
        self.confusions[seen] = self.confusions.get(seen, 0) + 1

    @property
    def accuracy(self) -> float:
        total = self.right + self.wrong
        return 1.0 if total == 0 else self.right / total


def _expected(label: PostingLabel, field: str) -> object:
    """The label's value, in the reading's own vocabulary.

    `min_years_experience` is the one that needs care: the loader has already
    turned the labeler's `not_stated` into `None`, and `None` must not compare
    equal to `0`. Nothing else is translated, because both sides were built to
    use the same words — see the module docstring of `eligibility_reading`.
    """
    return getattr(label, field)


def _predicted(reading: PostingReading, field: str) -> object:
    return getattr(reading, field)


@pytest.fixture(scope="module")
def graded() -> dict[str, Any]:
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()

    tallies = {field: FieldTally() for field in GRADED_FIELDS}
    examples: dict[str, list[str]] = {field: [] for field in GRADED_FIELDS}
    readings: dict[str, PostingReading] = {}

    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings.get(board, {}).get(posting_id)
            assert text is not None, f"{board}/{posting_id} labeled but not in corpus"
            reading = read_posting(extract_requirements(text, vocabulary=vocab))
            readings[f"{board}/{posting_id}"] = reading
            for field in GRADED_FIELDS:
                predicted, expected = _predicted(reading, field), _expected(label, field)
                tallies[field].record(predicted, expected)
                if predicted != expected and len(examples[field]) < 6:
                    examples[field].append(
                        f"{board}/{posting_id}: read {predicted!r}, labeled {expected!r}"
                    )

    return {"tallies": tallies, "examples": examples, "readings": readings, "postings": key}


def test_report_the_numbers(graded: dict[str, Any], capsys: Any) -> None:
    """Always passes. Prints the baseline. Run with `-s` to read it."""
    with capsys.disabled():
        print("\n  eligibility reading, graded against the 60-posting answer key\n")
        for field in GRADED_FIELDS:
            tally: FieldTally = graded["tallies"][field]
            print(
                f"  {field:<24} accuracy {tally.accuracy:.3f}"
                f"   ({tally.right} right, {tally.wrong} wrong)"
            )
        print()
        for field in GRADED_FIELDS:
            tally = graded["tallies"][field]
            assert tally.confusions is not None
            if not tally.confusions:
                continue
            top = sorted(tally.confusions.items(), key=lambda kv: -kv[1])[:4]
            summary = ", ".join(f"read {p!r} for {e!r} x{n}" for (p, e), n in top)
            print(f"  {field}: {summary}")
        print()
        for field in GRADED_FIELDS:
            for line in graded["examples"][field][:3]:
                print(f"    {field}: {line}")


def test_every_label_field_is_graded_or_named(graded: dict[str, Any]) -> None:
    """A label field in neither tuple is a field nobody decided about.

    The failure this prevents is specific and this project has shipped it: M3a
    graded one field of nine and no test anywhere said the other eight were
    unmeasured. It read as complete because nothing counted.
    """
    labeled = set(PostingLabel.model_fields)
    accounted = set(GRADED_FIELDS) | set(NOT_GRADED_HERE)
    assert labeled - accounted == set(), (
        f"label fields with no decision about grading: {sorted(labeled - accounted)}"
    )
    assert accounted - labeled == set(), (
        f"named as graded but not a label field: {sorted(accounted - labeled)}"
    )


def test_the_grader_can_fail(graded: dict[str, Any]) -> None:
    """A tally that cannot record a miss is a tally stuck at 1.000.

    M3a shipped `test_no_nice_to_have_is_ever_reported_as_required` reporting
    zero violations for a whole milestone because its comparison could not see
    the disagreement it existed to find. This asserts the machinery itself,
    against a difference constructed here rather than found in the corpus.
    """
    tally = FieldTally()
    tally.record("bachelors", "bachelors")
    tally.record("phd", "bachelors")
    assert (tally.right, tally.wrong) == (1, 1)
    assert tally.accuracy == 0.5
    assert tally.confusions == {("phd", "bachelors"): 1}


def test_none_years_never_compares_equal_to_zero(graded: dict[str, Any]) -> None:
    """`not_stated` and "no experience required" are different postings.

    Merging them is the kind of quiet coercion that would make the years tally
    look better than the rules are, and it would carry straight into the gate:
    one of the two must pass and the other cannot decide.
    """
    tally = FieldTally()
    tally.record(None, 0)
    tally.record(0, None)
    assert tally.wrong == 2
