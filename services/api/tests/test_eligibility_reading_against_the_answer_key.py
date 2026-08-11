"""The five eligibility fields nobody has ever graded.

M3a graded exactly one of the answer key's nine label fields — `required_tech`,
plus necessity. The extractor has been emitting `degree`, `graduation_window`,
`years_experience`, `enrollment` and `authorization` proposals since
`3722026`, against a key committed before any of those rules existed, and no
test has ever compared one of them to a label.

This is that comparison. It was written **before** any of the rules it grades
were changed, so its first numbers are a baseline rather than a result.
`matching.md` §1.1 is the reason the ordering matters: an evaluation written
after the thing it evaluates reports a number that measures nothing.

    Task 1 baseline    0.567 / 0.917 / 0.883 / 0.317 / 0.917
    after Task 5       0.850 / 0.917 / 0.883 / 0.483 / 0.917

**M3d Task 2 closed the condition this file used to state here.** Until
2026-08-10 the paragraph below said exactly one floor was set — the binary
enrollment question — and that *"the other five stay reported and ungated until
Task 5's remaining repairs are done, because a floor set mid-repair is a floor
that has to be edited again next week."*

That was right when written and stopped being right on 2026-08-05, when M3b Task
5 shipped and merged. Nobody came back, and five accuracies sat measured and
enforced by nothing for a milestone. The lesson is not that the deferral was
wrong — it was correct and well-argued — but that **a condition written into a
docstring has no owner and no expiry**, and a number reported under one reads,
in a green test run, exactly like a number under a floor.

Four of the five are now gated by `READING_FLOORS`, measured and set just under
per M3a's rule. The fifth is `enrollment_required`, deliberately not gated on its
three-way accuracy, and it is named in `REPORTED_NOT_GATED` with the reason
rather than left to a reader to infer from its absence —
`test_every_graded_field_is_gated_or_named_as_ungated` is what makes that a
decision instead of an omission.
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

#: The floor on the binary question, and the first one this file ever carried.
#: See `test_enrollment_is_graded_on_the_question_the_gate_asks` for why that one
#: field is graded differently from how it is labeled.
ENROLLMENT_IS_REQUIRED_FLOOR = 0.90

#: **Added at M3d Task 2**, and the reason it took a milestone is worth keeping.
#: This file's own docstring gated these on a condition — *"reported and ungated
#: until Task 5's remaining repairs are done, because a floor set mid-repair is a
#: floor that has to be edited again next week"* — which was right when written.
#: M3b Task 5 shipped and merged on 2026-08-05 and nobody came back. A number
#: reported and held to nothing is indistinguishable, in a passing test run, from
#: a number under a floor.
#:
#: Measured on 2026-08-10 against the committed 60-posting key and set just
#: under, per M3a's rule. A floor chosen before measuring is either unreachable
#: or vacuous and there is no way to tell which from outside; a floor set far
#: below what the reader achieves is the second of those wearing a gate's
#: clothes, which is what `test_no_reading_floor_is_vacuous` exists to catch.
#:
#:     degree                0.867    graduation_window    1.000
#:     min_years_experience  0.883    sponsorship          0.917
READING_FLOORS: dict[str, float] = {
    "degree": 0.86,
    "graduation_window": 0.98,
    "min_years_experience": 0.88,
    "sponsorship": 0.91,
}

#: Graded, reported, and deliberately not gated — with the reason, because an
#: ungated number with no entry here is the thing Task 2 was cleaning up.
REPORTED_NOT_GATED: dict[str, str] = {
    "enrollment_required": (
        "the three-way accuracy is 0.483 and gating it would gate a distinction "
        "no decision in this system reads: 30 of its 31 errors are `not_stated` "
        "read where the key says `no`, and both mean *you need not be a student* "
        "to the gate. The question that changes a verdict is gated instead, at "
        "ENROLLMENT_IS_REQUIRED_FLOOR — see "
        "test_enrollment_is_graded_on_the_question_the_gate_asks"
    ),
}

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
    # Added at Task 2 and immediately caught by the guard below, which is the
    # first time in this project that a new label field has been unable to
    # arrive unmeasured. All three are graded in
    # test_role_classification_against_the_answer_key once Task 4 exists.
    "role_family": "graded against the classifier, Task 4 — nothing produces it yet",
    "seniority": "same",
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
    enrollment_binary = FieldTally()

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

            # The only enrollment distinction the gate consumes. See
            # `test_enrollment_is_graded_on_the_question_the_gate_asks`.
            enrollment_binary.record(
                reading.enrollment_required == "yes", label.enrollment_required == "yes"
            )

    return {
        "tallies": tallies,
        "examples": examples,
        "readings": readings,
        "postings": key,
        "enrollment_binary": enrollment_binary,
    }


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


def test_enrollment_is_graded_on_the_question_the_gate_asks(
    graded: dict[str, Any], capsys: Any
) -> None:
    """`yes` versus not-`yes`, and the three-way figure is the misleading one.

    **The answer key's `no` and `not_stated` are not separable from the
    postings.** Among the 47 non-internship postings, 30 are labeled `no` and 17
    `not_stated`, and reading the descriptions the split is not driven by
    anything the postings say — some `no` labels have a note pointing at real
    text ("the closing line pushes current students to other postings"), and
    most do not. Both mean the same thing to a person: you do not have to be a
    student to apply.

    **No label was edited.** The M3a key was committed before any of these rules
    existed and that ordering is the only reason its numbers mean anything;
    rewriting 30 labels to lift a metric is the exact move `matching.md` §1.1
    forbids. The metric is redefined instead, on the distinction that changes a
    verdict — and the three-way accuracy is still reported beside it, so the
    change is visible rather than a quiet improvement.

    Nothing downstream needs the other distinction: the gate asks "must this
    person be enrolled", and a posting that is silent and a posting that says no
    produce the identical answer.
    """
    binary: FieldTally = graded["enrollment_binary"]
    three_way: FieldTally = graded["tallies"]["enrollment_required"]
    with capsys.disabled():
        print(
            f"\n  enrollment, as the gate asks it   accuracy {binary.accuracy:.3f}"
            f"   ({binary.right} right, {binary.wrong} wrong)"
            f"\n  enrollment, three-way             accuracy {three_way.accuracy:.3f}"
            f"   <- reported, not gated: see this test's docstring\n"
        )
    assert binary.accuracy >= ENROLLMENT_IS_REQUIRED_FLOOR


# -- M3d Task 2: the four floors this file has reported and not gated --------


def test_every_graded_field_is_gated_or_named_as_ungated(graded: dict[str, Any]) -> None:
    """The partition, one level down from `test_every_label_field_is_graded_or_named`.

    That test asks whether a label field is graded. This one asks whether a
    graded field is *gated* — which is the distinction that let five accuracies
    sit measured and unenforced for a whole milestone on a condition ("until
    Task 5's repairs are done") that was met and never revisited. A number
    nobody is holding to anything reads exactly like a number somebody is.
    """
    decided = set(READING_FLOORS) | set(REPORTED_NOT_GATED)
    assert set(GRADED_FIELDS) == decided, (
        f"graded but with no decision about gating: {sorted(set(GRADED_FIELDS) - decided)}"
    )
    assert not (set(READING_FLOORS) & set(REPORTED_NOT_GATED)), "a field cannot be both"


def test_no_reading_floor_is_vacuous(graded: dict[str, Any]) -> None:
    """A floor far below what the reader achieves is a floor that cannot fail.

    M3a's rule is that a floor is measured and set just under. The rule's failure
    mode is the opposite of a floor set too high: 0.10 on `degree` would pass
    every run forever, would look like a gate in the diff, and would let the
    field regress to a coin flip without a red test. The tolerance here is what
    makes "just under" checkable rather than a habit.
    """
    for field, floor in READING_FLOORS.items():
        measured = graded["tallies"][field].accuracy
        assert floor <= measured, f"{field}: floor {floor} is above the measured {measured:.3f}"
        assert measured - floor <= 0.05, (
            f"{field}: floor {floor} is {measured - floor:.3f} below the measured "
            f"{measured:.3f} — set it just under, or it gates nothing"
        )


@pytest.mark.parametrize("field", sorted(READING_FLOORS))
def test_the_reading_accuracy_holds(graded: dict[str, Any], field: str) -> None:
    """One test per field, so a red suite names which reading regressed."""
    assert graded["tallies"][field].accuracy >= READING_FLOORS[field]
