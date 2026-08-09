"""The three span-bound components, against fixtures and no database.

`matching.md` §2.1: role relevance, skill overlap and project evidence each make
a claim about a *person*, and each must trace to two quotable strings. Most of
this file is about the cases where one of those strings cannot be produced,
because that is where a scorer invents things.

No `requires_db`. The module imports no ORM on purpose (M3c plan §1.2), and a
test that needs Postgres is a test that skips when Docker is down — which this
project has already had happen for three days without noticing.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nightshift.db.base import MatchComponent, RoleFamily
from nightshift.domain.requirement_extraction import RequirementProposal
from nightshift.domain.role_classification import TextSpan, classify_role
from nightshift.domain.scoring import (
    ComponentScore,
    ConfirmedProject,
    ConfirmedSkill,
    PostingForScoring,
    ScoringProfile,
    families_wanted,
    score_project_evidence,
    score_role_relevance,
    score_skill_overlap,
)

DESCRIPTION = (
    "What you'll need: strong Python and production experience with PostgreSQL. "
    "Nice to have: Kubernetes."
)


def _requirement(
    value: str, *, necessity: str = "required", text: str | None = None
) -> RequirementProposal:
    raw = text or value
    start = DESCRIPTION.index(raw)
    return RequirementProposal(
        kind="technology",
        value=value,
        raw_text=raw,
        char_start=start,
        char_end=start + len(raw),
        necessity=necessity,  # type: ignore[arg-type]
    )


def _posting(**overrides: Any) -> PostingForScoring:
    fields: dict[str, Any] = {
        "title": "Software Engineer, Platform",
        "description_text": DESCRIPTION,
        "role_family": RoleFamily.SOFTWARE_ENGINEERING,
        "role_family_span": TextSpan(
            field="title", text="Software Engineer", char_start=0, char_end=17
        ),
        "requirements": (_requirement("Python"), _requirement("PostgreSQL")),
    }
    fields.update(overrides)
    return PostingForScoring(**fields)


# ---------------------------------------------------------------------------
# Skill overlap
# ---------------------------------------------------------------------------


def test_a_posting_naming_no_required_technology_is_not_assessable() -> None:
    """The measurement this module is shaped around.

    26 of the 60 labeled postings name no required technology. Scoring those 0
    would remove 30 points from 43% of the corpus for something about the
    employer's prose, which is the argument §5.1 used to defer application
    urgency. `assessable=False` is a different statement from a zero and the
    total has to be able to tell them apart.
    """
    result = score_skill_overlap(
        _posting(requirements=()),
        ScoringProfile(skills=(ConfirmedSkill(name="Python", taxonomy_id="Python"),)),
        weight=30,
    )

    assert (result.assessable, result.points, result.evidence) == (False, 0, ())
    assert "no required technologies" in result.why


def test_a_profile_missing_everything_the_posting_requires_scores_zero_and_is_assessable() -> None:
    """The other zero, and the one that means something about the person."""
    result = score_skill_overlap(_posting(), ScoringProfile(), weight=30)

    assert (result.assessable, result.points) == (True, 0)
    assert "none of the 2 required technologies" in result.why


def test_every_required_technology_confirmed_earns_the_whole_weight() -> None:
    profile = ScoringProfile(
        skills=(
            ConfirmedSkill(name="Python", taxonomy_id="Python"),
            ConfirmedSkill(name="PostgreSQL", taxonomy_id="PostgreSQL"),
        )
    )

    result = score_skill_overlap(_posting(), profile, weight=30)

    assert result.points == 30
    assert len(result.evidence) == 2


def test_half_the_requirements_earns_half_the_weight() -> None:
    profile = ScoringProfile(skills=(ConfirmedSkill(name="Python", taxonomy_id="Python"),))

    result = score_skill_overlap(_posting(), profile, weight=30)

    assert result.points == 15


def test_a_preferred_technology_earns_nothing() -> None:
    """§4.1 calls necessity the column the product turns on.

    Ramp's Android internship lists nine technologies under *nice to haves*.
    Scoring those rewards a posting for listing more things, and it is the
    difference between a usable product and one reporting nine gaps against a
    fully qualified candidate.
    """
    posting = _posting(requirements=(_requirement("Kubernetes", necessity="preferred"),))
    profile = ScoringProfile(skills=(ConfirmedSkill(name="Kubernetes", taxonomy_id="Kubernetes"),))

    result = score_skill_overlap(posting, profile, weight=30)

    assert (result.assessable, result.points) == (False, 0)


def test_a_skill_outside_the_taxonomy_matches_nothing() -> None:
    """`skill_id` null means confirmed and outside the vocabulary. Resolving it
    to a neighbour would fabricate a qualification, which is I2."""
    profile = ScoringProfile(skills=(ConfirmedSkill(name="Snake charming", taxonomy_id=None),))

    result = score_skill_overlap(_posting(), profile, weight=30)

    assert result.points == 0


def test_a_skill_confirmed_under_an_alias_still_matches_by_taxonomy_name() -> None:
    """The reason `skill_id` exists. Typed "postgres", stored under the
    taxonomy's "PostgreSQL", and the requirement says "PostgreSQL"."""
    profile = ScoringProfile(skills=(ConfirmedSkill(name="postgres", taxonomy_id="PostgreSQL"),))

    result = score_skill_overlap(_posting(), profile, weight=30)

    assert result.points == 15
    assert result.evidence[0].user_span_text == "postgres"


def test_every_skill_row_quotes_both_sides_at_real_offsets() -> None:
    """The span rule, checked against the description the offsets index into."""
    profile = ScoringProfile(
        skills=(
            ConfirmedSkill(name="Python", taxonomy_id="Python"),
            ConfirmedSkill(name="PostgreSQL", taxonomy_id="PostgreSQL"),
        )
    )

    result = score_skill_overlap(_posting(), profile, weight=30)

    for row in result.evidence:
        assert row.job_span_field == "description_text"
        assert row.user_span_text
        assert DESCRIPTION[row.job_char_start : row.job_char_end] == row.job_span_text, row


def test_the_evidence_points_add_up_to_the_component() -> None:
    """A breakdown that does not sum to its own total is the small version of
    the defect I4 exists to prevent. Three rows and 20 points is where integer
    division would quietly lose one."""
    description = "What you'll need: Python, Go and Rust."
    requirements = tuple(
        RequirementProposal(
            kind="technology",
            value=value,
            raw_text=value,
            char_start=description.index(value),
            char_end=description.index(value) + len(value),
            necessity="required",
        )
        for value in ("Python", "Go", "Rust")
    )
    posting = _posting(description_text=description, requirements=requirements)
    profile = ScoringProfile(
        skills=tuple(ConfirmedSkill(name=v, taxonomy_id=v) for v in ("Python", "Go", "Rust"))
    )

    result = score_skill_overlap(posting, profile, weight=20)

    assert result.points == 20
    assert sum(row.points for row in result.evidence) == 20


# ---------------------------------------------------------------------------
# Role relevance
# ---------------------------------------------------------------------------


def test_a_stated_preference_naming_the_family_earns_the_whole_weight() -> None:
    profile = ScoringProfile(preferred_roles=("backend engineer",))

    result = score_role_relevance(_posting(), profile, weight=20)

    assert result.points == 20
    row = result.evidence[0]
    assert (row.job_span_text, row.job_span_field) == ("Software Engineer", "title")
    assert row.user_span_text == "backend engineer"


def test_a_profile_with_no_preferred_roles_is_not_assessable() -> None:
    result = score_role_relevance(_posting(), ScoringProfile(), weight=20)

    assert (result.assessable, result.points) == (False, 0)


def test_an_unclear_family_is_not_assessable() -> None:
    """A posting nothing could classify says nothing about the person either."""
    posting = _posting(role_family=RoleFamily.UNCLEAR, role_family_span=None)

    result = score_role_relevance(posting, ScoringProfile(preferred_roles=("backend",)), weight=20)

    assert (result.assessable, result.points) == (False, 0)


def test_a_family_with_no_quotable_span_scores_nothing() -> None:
    """§2.1 makes a claim about a person with nothing quoted unrepresentable, so
    a family whose span went missing must not score rather than score silently."""
    posting = _posting(role_family_span=None)

    result = score_role_relevance(posting, ScoringProfile(preferred_roles=("backend",)), weight=20)

    assert (result.assessable, result.points) == (False, 0)


def test_a_preference_for_another_family_scores_zero_and_says_so() -> None:
    profile = ScoringProfile(preferred_roles=("product manager",))

    result = score_role_relevance(_posting(), profile, weight=20)

    assert (result.assessable, result.points) == (True, 0)
    assert "none of the stated preferences names it" in result.why


def test_the_longer_role_phrase_wins() -> None:
    """ "data engineer" must beat "engineer", the same reason `skill_vocabulary`
    sorts its terms longest first."""
    wanted = families_wanted(("data engineer",))

    assert RoleFamily.DATA_ENGINEERING in wanted


def test_a_role_word_inside_another_word_does_not_count() -> None:
    """ "designer" is a role; "redesigned" is not. Substring matching is how
    `react` became a required technology on eight postings at M3a.1."""
    assert families_wanted(("i redesigned things",)) == {}


# ---------------------------------------------------------------------------
# Project evidence
# ---------------------------------------------------------------------------


def test_a_project_demonstrating_a_requirement_quotes_its_own_bullet() -> None:
    project = ConfirmedProject(
        name="Sharded work queue",
        technologies=("Python",),
        evidence="Built a sharded work queue in Python. Ran it for a year.",
        user_project_id=uuid.uuid4(),
    )

    result = score_project_evidence(_posting(), ScoringProfile(projects=(project,)), weight=20)

    assert result.points == 10
    row = result.evidence[0]
    assert row.user_span_text == "Built a sharded work queue in Python."
    assert row.user_project_id == project.user_project_id


def test_a_project_listing_a_technology_no_bullet_mentions_produces_no_row() -> None:
    """The case that separates evidence from a claim.

    The technologies list is a set of tags; the bullets are what the person
    actually wrote. §2.1 does not let the project's *name* stand in for a
    user-side span, so a tag with nothing behind it earns nothing.
    """
    project = ConfirmedProject(
        name="Sharded work queue",
        technologies=("Python",),
        evidence="Built a sharded work queue. Ran it for a year.",
    )

    result = score_project_evidence(_posting(), ScoringProfile(projects=(project,)), weight=20)

    assert (result.points, result.evidence) == (0, ())


def test_a_project_with_no_bullets_at_all_earns_nothing() -> None:
    project = ConfirmedProject(name="Something", technologies=("Python",), evidence=None)

    result = score_project_evidence(_posting(), ScoringProfile(projects=(project,)), weight=20)

    assert result.points == 0


def test_no_projects_is_not_assessable() -> None:
    result = score_project_evidence(_posting(), ScoringProfile(), weight=20)

    assert (result.assessable, result.points) == (False, 0)


def test_a_posting_requiring_nothing_is_not_assessable_for_projects_either() -> None:
    project = ConfirmedProject(name="Thing", technologies=("Python",), evidence="Wrote Python.")

    result = score_project_evidence(
        _posting(requirements=()), ScoringProfile(projects=(project,)), weight=20
    )

    assert (result.assessable, result.points) == (False, 0)


def test_a_skill_and_a_project_for_the_same_technology_are_two_claims() -> None:
    """Not double counting. "I know Python" and "I built this in Python" are
    different assertions with different evidence, and §5.1 gives them separate
    weights precisely because they are."""
    profile = ScoringProfile(
        skills=(ConfirmedSkill(name="Python", taxonomy_id="Python"),),
        projects=(
            ConfirmedProject(
                name="Queue", technologies=("Python",), evidence="Built it in Python."
            ),
        ),
    )

    skill = score_skill_overlap(_posting(), profile, weight=30)
    project = score_project_evidence(_posting(), profile, weight=20)

    assert skill.points == 15
    assert project.points == 10


# ---------------------------------------------------------------------------
# The guards on a ComponentScore itself
# ---------------------------------------------------------------------------


def test_a_component_cannot_score_while_calling_itself_unassessable() -> None:
    with pytest.raises(ValueError, match="not assessable and scored"):
        ComponentScore(
            component=MatchComponent.SKILL, points=5, assessable=False, why="", evidence=()
        )


def test_a_component_cannot_score_with_no_evidence() -> None:
    """The database refuses this at commit; refusing it here means a unit test
    sees it without Postgres."""
    with pytest.raises(ValueError, match="no evidence row"):
        ComponentScore(
            component=MatchComponent.SKILL, points=5, assessable=True, why="", evidence=()
        )


def test_an_unassessable_component_with_no_points_is_fine() -> None:
    result = ComponentScore(
        component=MatchComponent.SKILL, points=0, assessable=False, why="nothing to read"
    )

    assert result.points == 0


# ---------------------------------------------------------------------------
# The span the classifier now carries
# ---------------------------------------------------------------------------


def test_the_classifier_hands_over_the_words_it_matched() -> None:
    """Role relevance cannot quote the posting without this, and recovering it
    by parsing `family_reason` back apart is the second derivation that goes
    wrong quietly."""
    result = classify_role(title="Senior Software Engineer", description="", years=None)

    assert result.family_span is not None
    assert result.family_span.field == "title"
    assert (
        "Senior Software Engineer"[result.family_span.char_start : result.family_span.char_end]
        == result.family_span.text
    )


def test_a_description_veto_quotes_the_description_and_says_so() -> None:
    """The classifier reads two different strings, which is why a span has to
    name its field: checked against the wrong one, a correct span looks wrong."""
    result = classify_role(
        title="Applied AI Architect",
        description="You will be a pre-sales architect working with customers.",
        years=None,
    )

    assert result.role_family is RoleFamily.NOT_TECH
    assert result.family_span is not None
    assert result.family_span.field == "description_text"


def test_a_title_nothing_matches_carries_no_span() -> None:
    result = classify_role(title="Zookeeper", description="", years=None)

    assert result.role_family is RoleFamily.UNCLEAR
    assert result.family_span is None
