"""The classifier, graded against the labels committed before it existed.

`role_family` and `seniority` were labeled across all 60 postings in Task 2 and
committed before a line of `role_classification.py` was written. That ordering
is what `matching.md` §1.1 asks for.

**It is weaker independence than M3a had, and the difference is worth stating.**
M3a's key was labeled by reading descriptions, and its extraction rules were
about headings and vocabulary — a different surface. Here the labels and the
rules were both derived from the same 60 titles, hours apart. So these numbers
are an upper bound rather than a generalisation estimate. The held-out check
this wants is the 93 recorded-but-unlabeled postings, and it is not done.

Floors are set below, after measuring and just under what the rules achieve —
M3a's rule, for M3a's reason: a floor picked before measuring is either
unreachable or vacuous and there is no way to tell which from the outside.
"""

from __future__ import annotations

from typing import Any

import pytest

from nightshift.domain.eligibility_labels import load_answer_key
from nightshift.domain.eligibility_reading import read_posting
from nightshift.domain.requirement_extraction import extract_requirements
from nightshift.domain.role_classification import classify_role
from nightshift.domain.skill_vocabulary import load_vocabulary
from tests.test_eligibility_reading_against_the_answer_key import FieldTally
from tests.test_requirement_extraction_against_the_answer_key import _corpus_postings

CLASSIFIED_FIELDS = ("role_family", "seniority", "is_internship")

#: Measured on the committed corpus, set just under what the rules achieve, per
#: the rule M3a established. Never lowered without a sentence in the commit
#: saying what regressed.
#:
#:     role_family    0.933 -> 0.950   the role type beats the domain
#:     seniority      0.967            unchanged
#:     is_internship  0.933            unchanged
#:
#: The one movement is attributable to one rule, which is why it was made and
#: measured on its own rather than folded in with the rest.
ROLE_FAMILY_FLOOR = 0.94
SENIORITY_FLOOR = 0.96
IS_INTERNSHIP_FLOOR = 0.93


@pytest.fixture(scope="module")
def graded() -> dict[str, Any]:
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()

    tallies = {field: FieldTally() for field in CLASSIFIED_FIELDS}
    examples: dict[str, list[str]] = {field: [] for field in CLASSIFIED_FIELDS}

    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings[board][posting_id]
            # The years figure comes from the reading rather than being re-read,
            # so the level rule and the gate cannot disagree about it.
            years = read_posting(extract_requirements(text, vocabulary=vocab)).min_years_experience
            result = classify_role(label.title, description=text, years=years)

            for field in CLASSIFIED_FIELDS:
                predicted = getattr(result, field)
                predicted = predicted.value if hasattr(predicted, "value") else predicted
                expected = getattr(label, field)
                tallies[field].record(predicted, expected)
                if predicted != expected and len(examples[field]) < 8:
                    examples[field].append(
                        f"{board.replace('_eligibility', '')}/{posting_id} "
                        f"{label.title.strip()[:52]!r}: said {predicted!r}, labeled {expected!r}"
                    )

    return {"tallies": tallies, "examples": examples}


def test_report_the_numbers(graded: dict[str, Any], capsys: Any) -> None:
    """Always passes. Run with `-s`."""
    with capsys.disabled():
        print("\n  role classification, graded against the 60-posting answer key\n")
        for field in CLASSIFIED_FIELDS:
            tally: FieldTally = graded["tallies"][field]
            print(
                f"  {field:<16} accuracy {tally.accuracy:.3f}"
                f"   ({tally.right} right, {tally.wrong} wrong)"
            )
        print()
        for field in CLASSIFIED_FIELDS:
            for line in graded["examples"][field]:
                print(f"    {field}: {line}")


def test_the_classifier_never_invents_a_value_outside_the_enum(graded: dict[str, Any]) -> None:
    """Enum members make this nearly free, and it is here because `unclear` and
    `not_tech` are both real answers — a typo'd literal would be a third."""
    from nightshift.db.base import RoleFamily, Seniority

    result = classify_role("Staff Software Engineer", description="", years=None)
    assert result.role_family in set(RoleFamily)
    assert result.seniority in set(Seniority)
    assert result.is_internship in {"yes", "no", "unclear"}


def test_every_classification_carries_a_reason(graded: dict[str, Any]) -> None:
    """I4's habit applied to a label. A value nobody can argue with is one
    nobody can correct, and the reason names the matched phrase."""
    key = load_answer_key()
    postings = _corpus_postings()
    blank = []
    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            result = classify_role(label.title, description=postings[board][posting_id])
            if not result.family_reason.strip() or not result.seniority_reason.strip():
                blank.append(f"{board}/{posting_id}")
    assert blank == [], blank


def test_a_title_word_does_not_beat_a_years_requirement_for_early_career() -> None:
    """Jane Street's "Campus Recruiter, Early Careers Partnerships & Initiatives".

    Three words in that title say early career and the posting asks for six
    years. A title-only classifier calls it `new_grad` and ranks a role wanting
    six years of experience into a new graduate's list. This is the one
    seniority rule that exists because a real posting broke the obvious version.
    """
    campus_with_experience = classify_role("Campus Recruiter, Early Careers", years=6)
    campus_without = classify_role("Campus AI Research Engineer (Full-Time)", years=None)

    assert campus_with_experience.seniority.value == "senior"
    assert campus_without.seniority.value == "new_grad"


def test_new_grad_beats_junior_in_the_same_title() -> None:
    """Databricks' "Associate Product Manager, New Grad (2027 Start)"."""
    assert classify_role("Associate Product Manager, New Grad (2027 Start)").seniority.value == (
        "new_grad"
    )


def test_a_business_role_wearing_a_technical_word_is_not_tech() -> None:
    """Four real titles, each containing a word that would file it under a tech
    family if `not_tech` were not tested first."""
    for title in (
        "AI Compliance Officer",
        "Capital Markets - Infrastructure Financing",
        "Cloud Partner Enablement Lead",
        "People Research Scientist, Recruiting",
    ):
        assert classify_role(title).role_family.value == "not_tech", title


def test_the_description_may_only_veto_towards_not_tech() -> None:
    """Anthropic's Applied AI Architect: "you will be a Pre-Sales architect".

    The veto runs one way on purpose. Every description in this corpus talks
    about technology, most of them at length, so a description allowed to
    *promote* a business title into an engineering family would promote most of
    them.
    """
    presales = classify_role(
        "Applied AI Architect", description="you will be a Pre-Sales architect"
    )
    assert presales.role_family.value == "not_tech"

    # ...and the reverse does not happen: a business title stays business, no
    # matter how much engineering its description describes.
    accountant = classify_role(
        "Senior Financial Reporting Accountant",
        description="Python SQL Kubernetes distributed systems machine learning",
    )
    assert accountant.role_family.value == "not_tech"


def test_the_role_type_beats_the_domain_in_the_title() -> None:
    """OpenAI's "Senior Technical Program Manager - Security".

    The title names a job and a subject area. The job is program management;
    security is what it is *about*. Graded with the domain families first this
    came out `security`, which describes the team rather than the work — the
    only role_family error in the corpus that was not a safe `unclear`.

    Both directions, because moving `product` above `security` unconditionally
    would break the second case.
    """
    assert classify_role("Senior Technical Program Manager - Security").role_family.value == (
        "product"
    )
    assert classify_role("Security Engineer, Application Security").role_family.value == "security"


def test_role_family_accuracy_holds(graded: dict[str, Any]) -> None:
    assert graded["tallies"]["role_family"].accuracy >= ROLE_FAMILY_FLOOR


def test_seniority_accuracy_holds(graded: dict[str, Any]) -> None:
    assert graded["tallies"]["seniority"].accuracy >= SENIORITY_FLOOR


def test_is_internship_accuracy_holds(graded: dict[str, Any]) -> None:
    assert graded["tallies"]["is_internship"].accuracy >= IS_INTERNSHIP_FLOOR


def test_every_role_family_error_is_a_refusal_rather_than_a_wrong_answer(
    graded: dict[str, Any],
) -> None:
    """Of the three remaining family errors, all three say `unclear`.

    That is the direction this milestone cares about. A wrong family is a claim
    about a posting; `unclear` is the classifier declining to make one, which
    is the same instinct A13 demands of the gate. If a future rule buys accuracy
    by guessing, this fails before the floor above does — a floor cannot tell a
    confident error from a refusal, and those are not the same mistake.
    """
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()
    confident_errors = []
    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings[board][posting_id]
            years = read_posting(extract_requirements(text, vocabulary=vocab)).min_years_experience
            said = classify_role(label.title, description=text, years=years).role_family.value
            if said != label.role_family and said != "unclear":
                confident_errors.append(
                    f"{board}/{posting_id}: said {said!r}, labeled {label.role_family!r}"
                )
    assert confident_errors == [], confident_errors
