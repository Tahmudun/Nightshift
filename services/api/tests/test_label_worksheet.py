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


def test_a_short_text_with_no_heading_is_returned_whole(worksheet: Any) -> None:
    text = "We want someone who can write Kotlin and has shipped an app."
    assert worksheet.requirements_excerpt(text) == text


def test_a_long_text_with_no_heading_returns_a_marked_tail(worksheet: Any) -> None:
    """Never the whole document. The first version produced 8,000-character
    excerpts, and an unmarked fallback reads as evidence rather than a guess."""
    text = "Company blurb. " * 400 + "You will write Kotlin."
    excerpt = worksheet.requirements_excerpt(text, window=200)
    assert excerpt.startswith(worksheet.NO_HEADING_NOTICE)
    assert "You will write Kotlin." in excerpt
    assert len(excerpt) <= 200 + len(worksheet.NO_HEADING_NOTICE)


def test_a_heading_word_inside_prose_is_not_an_anchor(worksheet: Any) -> None:
    """The exact compensation boilerplate that broke 16 Akuna postings.

    "qualifications" appears mid-clause. Anchoring there shows a labeler a pay
    disclaimer and none of the posting's requirements.
    """
    text = (
        "The base salary depends on experience, qualifications, and skill set. "
        "This role is also eligible for a discretionary bonus. "
        "Qualities that make great candidates: Graduating between 2027 and 2028."
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt.startswith("Qualities that make great candidates")


def test_a_duty_containing_a_heading_word_is_not_an_anchor(worksheet: Any) -> None:
    """ "meet regulatory requirements by translating..." is a job duty."""
    text = (
        "You will meet regulatory requirements by translating commitments into "
        "engineering work. WHAT YOU'LL NEED Proficiency in Kotlin."
    )
    assert worksheet.requirements_excerpt(text).startswith("WHAT YOU'LL NEED")


def test_a_capitalised_heading_anchors_even_without_a_colon(worksheet: Any) -> None:
    text = "About us we are great. WHAT YOU'LL NEED Proficiency in Kotlin."
    assert worksheet.requirements_excerpt(text).startswith("WHAT YOU'LL NEED")


def test_no_selected_excerpt_starts_mid_sentence(worksheet: Any) -> None:
    """The property that failed on the first real run: 30 of 60 broken.

    Runs over the actual corpus rather than invented strings, because the
    failure was invisible to every invented string in this file.
    """
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        excerpt = worksheet.requirements_excerpt(posting["text"])
        if excerpt[:1].islower():
            offenders.append(f"{board}/{posting['id']}: {excerpt[:70]}")
    assert offenders == [], f"{len(offenders)} excerpts anchored mid-sentence"


def test_no_selected_excerpt_is_a_wall_of_text(worksheet: Any) -> None:
    """13 of the first 60 ran past 1,500 characters; one hit 8,019."""
    offenders = []
    for board, posting in worksheet.select_for_labeling(worksheet._all_postings()):
        excerpt = worksheet.requirements_excerpt(posting["text"])
        if len(excerpt) > 1400:
            offenders.append(f"{board}/{posting['id']}: {len(excerpt)} chars")
    assert offenders == [], f"{len(offenders)} excerpts too long: {offenders[:5]}"


def test_most_selected_excerpts_find_a_real_heading(worksheet: Any) -> None:
    """The fallback is honest, but it is still a fallback.

    If most of the corpus lands on it, `_REQUIREMENT_HEADINGS` is missing the
    vocabulary these boards actually use, and the right fix is to add it rather
    than to accept tails.
    """
    picked = worksheet.select_for_labeling(worksheet._all_postings())
    fell_back = sum(
        worksheet.requirements_excerpt(p["text"]).startswith(worksheet.NO_HEADING_NOTICE)
        for _, p in picked
    )
    assert fell_back <= len(picked) // 4, (
        f"{fell_back} of {len(picked)} excerpts had no heading to anchor on"
    )


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
