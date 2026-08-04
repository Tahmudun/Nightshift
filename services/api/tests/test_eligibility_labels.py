"""The answer key's own guards.

A label that parses but says nothing is the failure this file exists to catch:
`TO_LABEL` is a valid string, so without an explicit check a half-filled key
would load cleanly and every metric computed against it would be quietly wrong.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nightshift.domain.eligibility_labels import (
    AnswerKey,
    PostingLabel,
    load_answer_key,
    unlabeled,
)

_COMPLETE = {
    "title": "Software Engineer Internship, Android",
    "is_internship": "yes",
    "graduation_window": "2026-2028",
    "enrollment_required": "yes",
    "degree": "bachelors",
    "min_years_experience": None,
    "required_tech": ["Kotlin"],
    "mentioned_not_required": ["React", "TypeScript"],
    "sponsorship": "not_stated",
    "note": "",
}


def test_a_complete_label_parses() -> None:
    label = PostingLabel.model_validate(_COMPLETE)
    assert label.required_tech == ["Kotlin"]
    assert label.min_years_experience is None


def test_a_degree_may_carry_the_equivalence_suffix() -> None:
    """A13: "PhD or equivalent experience" is not a hard blocker."""
    label = PostingLabel.model_validate({**_COMPLETE, "degree": "phd+equivalent"})
    assert label.degree == "phd+equivalent"
    assert label.has_degree_equivalence is True


def test_a_degree_without_the_suffix_does_not_claim_equivalence() -> None:
    label = PostingLabel.model_validate({**_COMPLETE, "degree": "phd"})
    assert label.has_degree_equivalence is False


def test_an_unknown_degree_is_refused() -> None:
    with pytest.raises(ValidationError):
        PostingLabel.model_validate({**_COMPLETE, "degree": "postdoc"})


def test_a_technology_may_not_appear_in_both_lists() -> None:
    """Required and merely-mentioned are exclusive. Both would make the
    precision metric meaningless, since either answer would score."""
    with pytest.raises(ValidationError):
        PostingLabel.model_validate(
            {**_COMPLETE, "required_tech": ["Kotlin"], "mentioned_not_required": ["Kotlin"]}
        )


def test_unlabeled_reports_every_field_still_saying_to_label() -> None:
    text = """
boards:
  janestreet_eligibility:
    "42":
      title: Software Engineer
      is_internship: TO_LABEL
      graduation_window: not_stated
      enrollment_required: TO_LABEL
      degree: none
      min_years_experience: not_stated
      required_tech: []
      mentioned_not_required: []
      sponsorship: not_stated
      note: ""
"""
    assert unlabeled(text) == [
        "janestreet_eligibility/42/enrollment_required",
        "janestreet_eligibility/42/is_internship",
    ]


def _labeling_state() -> tuple[int, int]:
    """(fields still unlabeled, postings in the key). Cheap, and read twice."""
    from nightshift.domain.eligibility_labels import ANSWER_KEY_PATH

    if not ANSWER_KEY_PATH.exists():
        return (0, 0)
    remaining = len(unlabeled(ANSWER_KEY_PATH.read_text()))
    key: AnswerKey | None = load_answer_key() if remaining == 0 else None
    total = sum(len(v) for v in key.boards.values()) if key else 0
    return (remaining, total)


_REMAINING, _POSTINGS = _labeling_state()

#: The gate tests skip — with a reason naming the shortfall — while the human
#: is still labeling, and activate by themselves the moment the key is filled
#: in. Decided 2026-08-04 rather than leaving them red: a red suite for however
#: long labeling takes destroys "is `make check` green" as a usable signal, and
#: this project's whole discipline rests on that question having an answer.
#:
#: A skip that could go stale is worse than a red test, so
#: `test_the_skip_condition_is_honest` below asserts the condition itself.
skip_until_labeled = pytest.mark.skipif(
    _REMAINING > 0,
    reason=f"answer key incomplete: {_REMAINING} fields still say TO_LABEL",
)


def test_the_skip_condition_is_honest() -> None:
    """Never skipped. Asserts the two gate tests skip for a real reason.

    Without this, a bug in `unlabeled` that returned `[]` on a blank key would
    silently un-skip both gates and they would pass over nothing at all.
    """
    from nightshift.domain.eligibility_labels import ANSWER_KEY_PATH

    assert ANSWER_KEY_PATH.exists(), "the answer key file is missing entirely"
    remaining, _ = _labeling_state()
    if remaining == 0:
        # Labeling is done: prove the checker can still see an unlabeled field.
        assert unlabeled("boards: {b: {'1': {is_internship: TO_LABEL}}}") == ["b/1/is_internship"]


@skip_until_labeled
def test_the_committed_answer_key_is_complete() -> None:
    """The gate. Skipped while labeling is in progress; then it must hold."""
    from nightshift.domain.eligibility_labels import ANSWER_KEY_PATH

    remaining = unlabeled(ANSWER_KEY_PATH.read_text())
    assert remaining == [], f"{len(remaining)} fields still unlabeled, e.g. {remaining[:5]}"


@skip_until_labeled
def test_the_committed_answer_key_parses_and_is_big_enough() -> None:
    """A13 asks for at least 50 real postings."""
    key = load_answer_key()
    total = sum(len(v) for v in key.boards.values())
    assert total >= 50, f"answer key holds {total} postings, A13 requires 50"
