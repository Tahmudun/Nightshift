"""The extractor's rules, each with a fixture, per CLAUDE.md §7.

The single most important behaviour in this file is that a technology under a
"nice to have" heading comes out `preferred`. Everything else here is ordinary
parsing; that one is the difference between a product that reports real gaps and
one that reports nine false ones.
"""

from __future__ import annotations

from nightshift.domain.requirement_extraction import (
    EXTRACTOR_VERSION,
    extract_requirements,
    necessity_at,
)


def _values(proposals: list, kind: str, necessity: str | None = None) -> set[str]:
    return {
        p.value
        for p in proposals
        if p.kind == kind and (necessity is None or p.necessity == necessity)
    }


def test_a_required_technology_is_required() -> None:
    text = "WHAT YOU'LL NEED Proficiency in Kotlin for Android development."
    assert _values(extract_requirements(text), "technology", "required") == {"Kotlin"}


def test_a_nice_to_have_technology_is_preferred_not_required() -> None:
    """The Ramp internship case, and the reason `necessity` exists."""
    text = (
        "WHAT YOU'LL NEED Proficiency in Kotlin. "
        "NICE TO HAVES Experience with web apps (React, TypeScript). "
        "Experience with backend technologies (Python, Flask, SQL)."
    )
    proposals = extract_requirements(text)
    assert _values(proposals, "technology", "required") == {"Kotlin"}
    assert {"React", "TypeScript", "Python", "SQL"} <= _values(proposals, "technology", "preferred")
    assert not _values(proposals, "technology", "required") & {"React", "Python"}


def test_a_bonus_points_heading_is_also_preferred() -> None:
    text = "REQUIREMENTS Python. Bonus Points: Experience with CUDA and PyTorch."
    proposals = extract_requirements(text)
    assert _values(proposals, "technology", "required") == {"Python"}
    assert "PyTorch" in _values(proposals, "technology", "preferred")


def test_a_technology_outside_any_heading_is_only_mentioned() -> None:
    """Prose about the stack is not a requirement."""
    text = "ABOUT US We are a Python shop and we love it here."
    assert _values(extract_requirements(text), "technology", "mentioned") == {"Python"}
    assert _values(extract_requirements(text), "technology", "required") == set()


def test_the_strongest_occurrence_of_a_technology_wins() -> None:
    """The case `SkillVocabulary.match` would have got wrong.

    "Python" appears twice: once in prose, once under a requirements heading.
    One posting asking for Python once is the truth, and the span shown must be
    the one that justifies calling it required.
    """
    text = "ABOUT US We are a Python shop. REQUIREMENTS Proficiency in Python."
    python = [
        p for p in extract_requirements(text) if p.kind == "technology" and p.value == "Python"
    ]
    assert len(python) == 1
    assert python[0].necessity == "required"
    assert python[0].char_start == text.rindex("Python")


def test_required_beats_preferred_for_the_same_technology() -> None:
    text = "REQUIREMENTS Python. NICE TO HAVES Python and React."
    python = [
        p for p in extract_requirements(text) if p.kind == "technology" and p.value == "Python"
    ]
    assert len(python) == 1
    assert python[0].necessity == "required"


def test_preferred_beats_mentioned_for_the_same_technology() -> None:
    text = "ABOUT US A React shop. NICE TO HAVES Experience with React."
    react = [p for p in extract_requirements(text) if p.kind == "technology" and p.value == "React"]
    assert len(react) == 1
    assert react[0].necessity == "preferred"


def test_a_graduation_window_is_read_as_a_range() -> None:
    text = (
        "WHAT YOU'LL NEED Currently pursuing a B.S. in Computer Science, with an "
        "expected graduation date between 2026 - 2028"
    )
    assert _values(extract_requirements(text), "graduation_window") == {"2026-2028"}


def test_a_single_graduation_year_is_read_as_a_one_year_window() -> None:
    text = "REQUIREMENTS Graduating in 2027 with a degree in a technical field."
    assert _values(extract_requirements(text), "graduation_window") == {"2027-2027"}


def test_a_years_of_experience_requirement_is_read_as_an_integer() -> None:
    text = "REQUIREMENTS 3+ years of experience building backend services."
    assert _values(extract_requirements(text), "years_experience") == {"3"}


def test_a_doctorate_is_read_as_a_degree() -> None:
    text = "WHO YOU ARE You hold a PhD in Computer Science or a related field"
    assert _values(extract_requirements(text), "degree") == {"phd"}


def test_or_equivalent_experience_sets_the_equivalence_flag() -> None:
    """A13: this is not a hard blocker, and the flag is how M3b learns that."""
    text = (
        "WHO YOU ARE You hold a PhD in Computer Science, with deep expertise "
        "in generative modeling (or have equivalent experience)"
    )
    degrees = [p for p in extract_requirements(text) if p.kind == "degree"]
    assert len(degrees) == 1
    assert degrees[0].value == "phd"
    assert degrees[0].has_equivalence is True


def test_a_degree_with_no_equivalence_clause_does_not_claim_one() -> None:
    text = "WHO YOU ARE You hold a PhD in Computer Science."
    degrees = [p for p in extract_requirements(text) if p.kind == "degree"]
    assert degrees[0].has_equivalence is False


def test_current_enrollment_is_its_own_kind() -> None:
    text = "WHAT YOU'LL NEED Currently pursuing a B.S. or higher in Computer Science"
    assert extract_requirements(text) and _values(extract_requirements(text), "enrollment") == {
        "required"
    }


def test_every_proposal_quotes_the_characters_it_points_at() -> None:
    """The property the database trigger enforces, asserted before it gets there."""
    text = (
        "WHAT YOU'LL NEED Proficiency in Kotlin. 3+ years of experience. "
        "NICE TO HAVES React and Python."
    )
    proposals = extract_requirements(text)
    assert proposals
    for p in proposals:
        assert text[p.char_start : p.char_end] == p.raw_text, p


def test_nothing_is_proposed_for_prose_with_no_requirements() -> None:
    text = "We are a fast-paced team that values high agency and high urgency."
    assert extract_requirements(text) == []


def test_the_extractor_does_not_import_the_orm() -> None:
    """The same guard `resume_extraction` carries, for the same reason: this is
    the only path by which a parsing bug could reach a stored row."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "nightshift"
        / "domain"
        / "requirement_extraction.py"
    ).read_text()
    assert "from nightshift.db" not in source
    assert "import nightshift.db" not in source


def test_the_version_is_stamped() -> None:
    assert EXTRACTOR_VERSION == "m3a.1"


def test_necessity_at_reports_the_governing_heading() -> None:
    text = "REQUIREMENTS Kotlin. NICE TO HAVES React."
    assert necessity_at(text, text.index("Kotlin")) == "required"
    assert necessity_at(text, text.index("React")) == "preferred"
    assert necessity_at(text, 0) == "required"


def test_preferred_qualifications_is_not_read_as_a_required_heading() -> None:
    """ "Preferred qualifications" contains the required heading "qualifications".

    The inner match starts ten characters later, so without the containment
    rule in `_heading_spans` it is the last heading before the whole preferred
    block, and every technology in that block comes out `required` — a false
    gap for each one. Four postings in the answer key's corpus are written this
    way.
    """
    text = (
        "Minimum qualifications Experience with Python. "
        "Preferred qualifications Experience with Kubernetes and Terraform."
    )
    proposals = extract_requirements(text)
    assert _values(proposals, "technology", "required") == {"Python"}
    assert {"Kubernetes", "Terraform"} <= _values(proposals, "technology", "preferred")
