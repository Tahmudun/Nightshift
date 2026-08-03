"""The extractor. Precision over recall, and every claim points at its words."""

from __future__ import annotations

import json
from pathlib import Path

from nightshift.domain.resume_extraction import (
    EXTRACTOR_VERSION,
    extract_proposals,
    find_sections,
)
from nightshift.domain.resume_text import read_resume_bytes

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"
RESUME = (FIXTURES / "nadia_okonkwo.txt").read_text(encoding="utf-8")


def test_every_proposal_quotes_the_text_it_came_from() -> None:
    """The whole slice rests on this. A span that does not quote is a fabrication."""
    proposals = extract_proposals(RESUME)
    assert proposals
    for proposal in proposals:
        assert RESUME[proposal.char_start : proposal.char_end] == proposal.quoted_text
        assert proposal.char_end > proposal.char_start


def test_the_same_text_twice_gives_byte_identical_proposals() -> None:
    first = [p.as_dict() for p in extract_proposals(RESUME)]
    second = [p.as_dict() for p in extract_proposals(RESUME)]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_graduation_month_and_year_are_proposed_without_inventing_a_day() -> None:
    (grad,) = [p for p in extract_proposals(RESUME) if p.kind == "graduation"]
    assert grad.value == {"year": 2027, "month": 5}
    assert "May 2027" in grad.quoted_text


def test_the_degree_and_school_come_from_the_education_section() -> None:
    kinds = {p.kind: p for p in extract_proposals(RESUME)}
    assert kinds["degree"].value == {"degree": "Bachelor of Science"}
    assert kinds["school"].value == {"school": "Hunter College"}
    education_start, education_end = find_sections(RESUME)["education"]
    for kind in ("degree", "school", "graduation"):
        assert education_start <= kinds[kind].char_start < education_end


def test_the_skills_are_the_vocabulary_ones_and_nothing_else() -> None:
    names = sorted(str(p.value["name"]) for p in extract_proposals(RESUME) if p.kind == "skill")
    assert names == [
        "Data Structures",
        "Docker",
        "FastAPI",
        "Git",
        "Go",
        "Playwright",
        "PostgreSQL",
        "Python",
        "React",
        "SQL",
        "TypeScript",
    ]


def test_both_projects_are_proposed_with_their_bullets_as_evidence() -> None:
    projects = [p for p in extract_proposals(RESUME) if p.kind == "project"]
    assert [p.value["name"] for p in projects] == ["Transit Delay Tracker", "Cafe Queue"]
    assert "MTA real-time feeds" in str(projects[0].value["evidence"])
    assert "checkout path" in str(projects[1].value["evidence"])


def test_years_of_experience_is_never_proposed() -> None:
    """A13 and I2: seniority is the hard problem, and this is not the slice for it."""
    assert "Five years of experience" in RESUME
    for proposal in extract_proposals(RESUME):
        assert "five years" not in proposal.quoted_text.lower()


def test_work_authorization_is_never_proposed() -> None:
    """A claim about legal status is confirmed in a form, never read off a page."""
    assert "Authorized to work" in RESUME
    for proposal in extract_proposals(RESUME):
        assert proposal.kind != "work_authorization"
        assert "authorized" not in proposal.quoted_text.lower()


def test_a_resume_that_proves_nothing_proposes_nothing() -> None:
    prose = (FIXTURES / "prose_only.txt").read_text(encoding="utf-8")
    assert extract_proposals(prose) == []


def test_a_date_outside_an_education_section_is_not_a_graduation_date() -> None:
    text = "EXPERIENCE\n\nSummer analyst, May 2027 cohort\n"
    assert [p for p in extract_proposals(text) if p.kind == "graduation"] == []


def test_a_date_in_the_education_section_with_no_cue_is_not_a_graduation_date() -> None:
    """A resume mentions dates for many reasons. Only a cue promotes one."""
    text = "EDUCATION\n\nHunter College\nRelocated to New York in May 2027\n"
    assert [p for p in extract_proposals(text) if p.kind == "graduation"] == []


def test_the_pdf_and_the_text_agree_on_the_facts_they_propose() -> None:
    """Same person, two file formats. The values must match; the spans must not."""
    from_pdf = extract_proposals(
        read_resume_bytes(data=(FIXTURES / "nadia_okonkwo.pdf").read_bytes(), filename="r.pdf")
    )
    from_text = extract_proposals(RESUME)
    assert {(p.kind, json.dumps(p.value, sort_keys=True)) for p in from_pdf} == {
        (p.kind, json.dumps(p.value, sort_keys=True)) for p in from_text
    }


def test_the_extractor_cannot_reach_the_database() -> None:
    """I2's structural claim: a bug here has no path to a confirmed fact."""
    source = (
        Path(__file__).resolve().parents[1] / "nightshift" / "domain" / "resume_extraction.py"
    ).read_text(encoding="utf-8")
    assert "nightshift.db" not in source
    assert "sqlalchemy" not in source


def test_the_proposals_match_the_committed_golden_file() -> None:
    golden = json.loads((FIXTURES / "nadia_okonkwo.proposals.json").read_text(encoding="utf-8"))
    assert [p.as_dict() for p in extract_proposals(RESUME)] == golden


def test_the_version_is_declared() -> None:
    assert EXTRACTOR_VERSION
