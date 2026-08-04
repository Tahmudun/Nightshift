"""The worksheet generator.

The excerpt is the only part of a posting a human will read, so a bug here does
not produce a wrong label — it produces a label made from the wrong evidence,
which is worse because it looks identical.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def worksheet() -> Any:
    spec = importlib.util.spec_from_file_location(
        "make_label_worksheet", ROOT / "scripts" / "make_label_worksheet.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_label_worksheet"] = module
    spec.loader.exec_module(module)
    return module


def test_the_excerpt_starts_at_the_requirements_heading(worksheet: Any) -> None:
    text = (
        "ABOUT US We are a company. " * 20
        + "WHAT YOU'LL NEED Proficiency in Kotlin. "
        + "NICE TO HAVES Experience with React."
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt.startswith("WHAT YOU'LL NEED")
    assert "Proficiency in Kotlin" in excerpt


def test_the_excerpt_keeps_the_preferred_section(worksheet: Any) -> None:
    """The nice-to-have section is the single most important thing to label.

    An excerpt that stops at the required list would produce an answer key with
    an empty `mentioned_not_required` for every posting, and that field is the
    difference between a usable product and one that reports nine false gaps.
    """
    text = "WHAT YOU'LL NEED Kotlin. NICE TO HAVES React, TypeScript, Flask."
    excerpt = worksheet.requirements_excerpt(text)
    assert "NICE TO HAVES" in excerpt
    assert "Flask" in excerpt


def test_the_excerpt_falls_back_to_the_whole_text_when_no_heading_matches(
    worksheet: Any,
) -> None:
    """No heading is not a reason to show nothing. It is a reason to show all."""
    text = "We want someone who can write Kotlin and has shipped an app."
    assert worksheet.requirements_excerpt(text) == text


def _posting(pid: str, title: str, reason: str) -> dict[str, Any]:
    return {"id": pid, "title": title, "reason": reason, "text": "REQUIREMENTS Python."}


def test_selection_covers_every_reason_before_deepening_any(worksheet: Any) -> None:
    """Round-robin across shapes, not the first N in file order.

    Taking postings in file order would hand back sixty postings from three
    boards with whole eligibility shapes missing, and the answer key would be
    blind to exactly the cases A13 calls hard.
    """
    postings = [("b1", _posting(f"a{i}", f"Engineer {i}", "internship")) for i in range(50)]
    postings += [("b2", _posting("z1", "Researcher", "doctorate"))]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert "doctorate" in {p["reason"] for _, p in picked}


def test_a_reason_with_one_example_still_contributes(worksheet: Any) -> None:
    """A shape with a single instance is the one most likely to be got wrong."""
    postings = [("b1", _posting(f"a{i}", f"Engineer {i}", "internship")) for i in range(100)]
    postings += [("b2", _posting("solo", "Research Scientist", "doctorate"))]
    picked = worksheet.select_for_labeling(postings, target=60)
    assert ("b2", postings[-1][1]) in picked


def test_recruiting_roles_are_skipped_under_the_new_grad_reason(
    worksheet: Any,
) -> None:
    """ "Campus Recruiter" matched the new-grad selector on a real board.

    It is a job recruiting new grads, not a job for one. Labeling it teaches
    the answer key nothing about new-grad eligibility.
    """
    postings = [
        ("b1", _posting("1", "Campus Recruiter", "new grad / university programme")),
        ("b1", _posting("2", "University Recruiter", "new grad / university programme")),
        ("b1", _posting("3", "Software Engineer, New Grad", "new grad / university programme")),
    ]
    picked = worksheet.select_for_labeling(postings, target=3)
    assert [p["title"] for _, p in picked] == ["Software Engineer, New Grad"]


def test_an_immigration_role_is_skipped_under_the_sponsorship_reason(
    worksheet: Any,
) -> None:
    """Jane Street's "Immigration and Mobility Specialist", found on real data.

    It matched on "advise on visa sponsorship considerations during the hiring
    process" — a job administering sponsorship for employees, not a posting
    stating its own policy toward an applicant.
    """
    postings = [
        (
            "b1",
            _posting("1", "Immigration and Mobility Specialist", "sponsorship stated in writing"),
        ),
        ("b1", _posting("2", "Software Engineer", "sponsorship stated in writing")),
    ]
    picked = worksheet.select_for_labeling(postings, target=2)
    assert [p["title"] for _, p in picked] == ["Software Engineer"]


def test_the_skip_is_scoped_to_the_reason_that_earned_it(worksheet: Any) -> None:
    """An immigration specialist is a fine example of a *senior title*.

    Skipping it under every reason would throw away real signal to fix one bad
    annotation.
    """
    postings = [
        (
            "b1",
            _posting("1", "Immigration and Mobility Specialist", "senior or above in the title"),
        ),
    ]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert len(picked) == 1


def test_a_reason_made_entirely_of_recruiting_roles_still_contributes(
    worksheet: Any,
) -> None:
    """Dropping every posting under a reason would delete the shape silently.

    Better a weak example the human can mark odd in `note` than a shape that
    vanishes without appearing anywhere.
    """
    postings = [("b1", _posting("1", "Campus Recruiter", "new grad / university programme"))]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert len(picked) == 1


def test_selection_is_deterministic(worksheet: Any) -> None:
    """Regenerating must not reshuffle what a human has already worked through."""
    postings = [
        ("b2", _posting("9", "B", "internship")),
        ("b1", _posting("3", "A", "doctorate")),
        ("b1", _posting("1", "C", "internship")),
    ]
    first = worksheet.select_for_labeling(postings, target=3)
    second = worksheet.select_for_labeling(list(reversed(postings)), target=3)
    assert [p["id"] for _, p in first] == [p["id"] for _, p in second]


def test_selection_never_pads_past_the_corpus(worksheet: Any) -> None:
    postings = [("b1", _posting("1", "Engineer", "internship"))]
    assert len(worksheet.select_for_labeling(postings, target=60)) == 1


def test_no_posting_is_selected_twice(worksheet: Any) -> None:
    postings = [("b1", _posting(str(i), f"Engineer {i}", "internship")) for i in range(80)]
    picked = worksheet.select_for_labeling(postings, target=60)
    keys = [(b, p["id"]) for b, p in picked]
    assert len(keys) == len(set(keys)) == 60


def test_a_blank_label_has_every_field_and_no_value(worksheet: Any) -> None:
    label = worksheet.blank_label("abc123", "Software Engineer Internship")
    assert label["title"] == "Software Engineer Internship"
    for field in (
        "is_internship",
        "graduation_window",
        "enrollment_required",
        "degree",
        "min_years_experience",
        "required_tech",
        "mentioned_not_required",
        "sponsorship",
        "note",
    ):
        assert field in label, field
    assert label["is_internship"] == "TO_LABEL"
    assert label["required_tech"] == "TO_LABEL"
