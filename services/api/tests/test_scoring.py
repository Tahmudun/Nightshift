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

import inspect
import uuid
from datetime import date, timedelta
from itertools import pairwise
from typing import Any, get_args

import pytest

from nightshift.db.base import MatchComponent, RequirementKind, RoleFamily, Seniority
from nightshift.domain.eligibility import Dimension
from nightshift.domain.matching_weights import (
    COMPONENT_NAMES,
    PENALTY_NAMES,
    MatchingWeights,
    load_weights,
)
from nightshift.domain.requirement_extraction import RequirementProposal
from nightshift.domain.role_classification import TextSpan, classify_role
from nightshift.domain.scoring import (
    PENALIZED_REQUIREMENT_KINDS,
    WEIGHT_NAME,
    ComponentScore,
    ConfirmedProject,
    ConfirmedSkill,
    Evidence,
    JobLocationForScoring,
    Penalty,
    PostingForScoring,
    ScoringProfile,
    compose_score,
    families_wanted,
    penalize_missing_requirements,
    penalize_seniority_mismatch,
    score_early_career_priority,
    score_listing_freshness,
    score_location_and_work_mode,
    score_match,
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


# ---------------------------------------------------------------------------
# Location and work mode — the first of the three exempt components
# ---------------------------------------------------------------------------

TODAY = date(2026, 8, 9)


def test_a_profile_stating_no_place_and_no_work_mode_is_not_assessable() -> None:
    posting = _posting(locations=(JobLocationForScoring(city="New York"),), remote_policy="hybrid")

    result = score_location_and_work_mode(posting, ScoringProfile(), weight=10)

    assert (result.assessable, result.points) == (False, 0)


def test_a_stated_city_the_posting_matches_earns_the_whole_weight() -> None:
    """The whole weight, not half, because the profile stated one dimension.

    Scoring somebody against a work-mode preference they did not express would
    mean inventing one and then marking them down against it.
    """
    posting = _posting(locations=(JobLocationForScoring(city="New York"),), remote_policy="hybrid")
    profile = ScoringProfile(preferred_locations=("new york",))

    result = score_location_and_work_mode(posting, profile, weight=10)

    assert result.points == 10


def test_both_dimensions_stated_splits_the_weight() -> None:
    posting = _posting(locations=(JobLocationForScoring(city="Chicago"),), remote_policy="hybrid")
    profile = ScoringProfile(preferred_locations=("New York",), remote_preference="hybrid")

    result = score_location_and_work_mode(posting, profile, weight=10)

    assert result.points == 5


def test_an_unknown_remote_policy_is_dropped_rather_than_failed() -> None:
    """A10: absence of data is data. The source not saying how a job is worked
    is not the same as it being worked the wrong way."""
    posting = _posting(locations=(JobLocationForScoring(city="New York"),), remote_policy="unknown")
    profile = ScoringProfile(preferred_locations=("New York",), remote_preference="remote")

    result = score_location_and_work_mode(posting, profile, weight=10)

    assert result.points == 10, "the place dimension should carry the whole weight alone"


def test_remote_typed_as_a_place_matches_a_remote_posting() -> None:
    """ "remote" is what people type into a locations field, and refusing to read
    it there marks a remote job against somebody who said the only thing that
    could express what they wanted."""
    posting = _posting(locations=(), remote_policy="remote")
    profile = ScoringProfile(preferred_locations=("remote",))

    result = score_location_and_work_mode(posting, profile, weight=10)

    assert result.points == 10


def test_an_unmatched_dimension_is_still_recorded() -> None:
    """A component that records only its wins is not a breakdown. "You asked for
    hybrid and this is on-site" is the line the explanation panel needs."""
    posting = _posting(locations=(JobLocationForScoring(city="Chicago"),), remote_policy="on_site")
    profile = ScoringProfile(preferred_locations=("New York",), remote_preference="hybrid")

    result = score_location_and_work_mode(posting, profile, weight=10)

    assert result.points == 0
    assert len(result.evidence) == 2
    assert all(row.points == 0 for row in result.evidence)


def test_no_location_evidence_row_ever_quotes_the_person() -> None:
    """§2.1, and the database refuses it too
    (`ck_match_evidence_only_a_person_claim_quotes_a_person`)."""
    posting = _posting(locations=(JobLocationForScoring(city="New York"),), remote_policy="remote")
    profile = ScoringProfile(preferred_locations=("New York",), remote_preference="remote")

    result = score_location_and_work_mode(posting, profile, weight=10)

    assert result.evidence
    for row in result.evidence:
        assert row.user_span_text is None
        assert row.job_span_text is None
        assert row.compared


# ---------------------------------------------------------------------------
# Listing freshness
# ---------------------------------------------------------------------------


def test_a_posting_published_this_week_earns_the_whole_weight() -> None:
    posting = _posting(source_published_at=TODAY - timedelta(days=3))

    result = score_listing_freshness(posting, weight=10, full_days=7, zero_days=90, as_of=TODAY)

    assert result.points == 10


def test_a_posting_older_than_the_window_earns_nothing_and_is_still_assessable() -> None:
    posting = _posting(source_published_at=TODAY - timedelta(days=200))

    result = score_listing_freshness(posting, weight=10, full_days=7, zero_days=90, as_of=TODAY)

    assert (result.assessable, result.points) == (True, 0)
    assert "200 days ago" in result.why


def test_freshness_falls_linearly_rather_than_off_a_cliff() -> None:
    """One day should never cost several points, so the two ends are checked
    against a midpoint rather than only at the thresholds."""
    scores = [
        score_listing_freshness(
            _posting(source_published_at=TODAY - timedelta(days=age)),
            weight=10,
            full_days=7,
            zero_days=90,
            as_of=TODAY,
        ).points
        for age in (7, 30, 48, 70, 90)
    ]

    assert scores == sorted(scores, reverse=True), scores
    assert scores[0] == 10
    assert scores[-1] == 0
    steps = [a - b for a, b in pairwise(scores)]
    assert max(steps) <= 3, scores


def test_a_source_giving_no_publication_date_is_not_assessable() -> None:
    """Not a zero. Every recorded posting carries one today, and a source that
    stops would otherwise silently lose 10 points on every job it lists."""
    result = score_listing_freshness(
        _posting(source_published_at=None), weight=10, full_days=7, zero_days=90, as_of=TODAY
    )

    assert (result.assessable, result.points) == (False, 0)


def test_freshness_reads_no_profile_at_all() -> None:
    """The signature is the assertion: there is no person in this calculation,
    which is why §2.1 exempts it from quoting one."""

    assert "profile" not in inspect.signature(score_listing_freshness).parameters


# ---------------------------------------------------------------------------
# Early-career priority
# ---------------------------------------------------------------------------


def test_an_internship_earns_the_priority_weight() -> None:
    result = score_early_career_priority(_posting(seniority=Seniority.INTERNSHIP), weight=10)

    assert result.points == 10


def test_a_staff_posting_earns_no_priority_and_is_assessable() -> None:
    result = score_early_career_priority(_posting(seniority=Seniority.STAFF), weight=10)

    assert (result.assessable, result.points) == (True, 0)


def test_an_unclear_level_is_not_assessable() -> None:
    result = score_early_career_priority(_posting(seniority=Seniority.UNCLEAR), weight=10)

    assert (result.assessable, result.points) == (False, 0)


def test_priority_reads_the_posting_and_never_the_person() -> None:
    """PRODUCT-SPEC §23 asks for the opposite — boost only when eligibility
    looks plausible — and `matching.md` §5.2 forbids it, because that is
    eligibility becoming points. The signature is where the decision is
    enforced: there is no profile to consult.
    """

    assert "profile" not in inspect.signature(score_early_career_priority).parameters


# ---------------------------------------------------------------------------
# The missing-requirement penalty — 0 to -25
#
# `matching.md` §5.1 gives the ceiling and nothing else, so the curve is decided
# here. Two constraints shaped it, and neither is cosmetic.
#
# **It may only read `technology`.** The other required kinds a posting can carry
# are `degree`, `graduation_window`, `years_experience`, `enrollment` and
# `authorization` — which are exactly the five dimensions M3b's gate owns. A
# penalty for an unmet degree requirement is eligibility converted into points,
# and §5.2 forbids that in the plainest terms this document has. `role_level` is
# the other penalty's.
#
# **The curve counts, it does not divide.** A fraction-based penalty combines
# with skill overlap into `55·matched - 25`, which is algebraically a single
# component of weight 55 with an offset — the penalty would be a weight change
# wearing a penalty's name, and zeroing either one in Task 7's mutation test
# would be compensated by the other. Counting the unmet requirements reads a
# different fact: five technologies you cannot evidence are five things to learn
# whether the posting lists five of them or fifty.
# ---------------------------------------------------------------------------


def _matched(*requirements: RequirementProposal) -> tuple[Evidence, ...]:
    """Evidence rows of the shape the span-bound components actually emit."""
    return tuple(
        Evidence(
            component=MatchComponent.SKILL,
            points=1,
            job_span_text=r.raw_text,
            job_span_field="description_text",
            job_char_start=r.char_start,
            job_char_end=r.char_end,
            user_span_text=r.value,
            requirement=r,
        )
        for r in requirements
    )


def _tech_posting(count: int) -> PostingForScoring:
    names = [f"Tech{i}" for i in range(1, count + 1)]
    text = "Requirements: " + ", ".join(names) + "."
    requirements = tuple(
        RequirementProposal(
            kind="technology",
            value=name,
            raw_text=name,
            char_start=text.index(name),
            char_end=text.index(name) + len(name),
            necessity="required",
        )
        for name in names
    )
    return PostingForScoring(title="Engineer", description_text=text, requirements=requirements)


def test_a_posting_naming_no_required_technology_has_nothing_to_miss() -> None:
    penalty = penalize_missing_requirements(
        _posting(requirements=()), (), ceiling=-25, per_requirement=5
    )

    assert penalty.points == 0
    assert penalty.applicable is False


def test_every_required_technology_evidenced_costs_nothing() -> None:
    posting = _posting()

    penalty = penalize_missing_requirements(
        posting, _matched(*posting.requirements), ceiling=-25, per_requirement=5
    )

    assert penalty.points == 0
    # Assessable and zero, not inapplicable: the question was asked and the
    # answer was "nothing missing", which is a different sentence.
    assert penalty.applicable is True


def test_each_unevidenced_required_technology_costs_a_fixed_amount() -> None:
    penalty = penalize_missing_requirements(_posting(), (), ceiling=-25, per_requirement=5)

    assert penalty.points == -10
    assert penalty.compared["missing"] == ["Python", "PostgreSQL"]
    assert penalty.compared["per_requirement"] == 5


def test_the_missing_requirement_penalty_stops_at_its_ceiling() -> None:
    """Nine unmet requirements is -45 uncapped, and -45 alone outweighs three
    whole components. The ceiling is what stops one verbose posting's
    requirements block from dominating the corpus."""
    penalty = penalize_missing_requirements(_tech_posting(9), (), ceiling=-25, per_requirement=5)

    assert penalty.points == -25
    assert len(penalty.compared["missing"]) == 9


def test_a_requirement_evidenced_by_a_project_alone_is_not_missing() -> None:
    """The penalty reads evidence rows, not the skill component's answer.

    A technology the person never listed as a skill but demonstrably built with
    has an evidence row under `project`, and counting it as missing would
    contradict a row this score is about to store."""
    posting = _posting()
    python, _postgres = posting.requirements
    rows = (
        Evidence(
            component=MatchComponent.PROJECT,
            points=1,
            job_span_text=python.raw_text,
            job_span_field="description_text",
            job_char_start=python.char_start,
            job_char_end=python.char_end,
            user_span_text="Built the ingest in Python.",
            requirement=python,
        ),
    )

    penalty = penalize_missing_requirements(posting, rows, ceiling=-25, per_requirement=5)

    assert penalty.points == -5
    assert penalty.compared["missing"] == ["PostgreSQL"]


def test_a_preferred_technology_never_reaches_the_penalty() -> None:
    """§4.1. Ramp's Android internship lists nine technologies under nice to
    haves; charging for those reports nine gaps against a qualified candidate."""
    posting = _posting(requirements=(_requirement("Kubernetes", necessity="preferred"),))

    penalty = penalize_missing_requirements(posting, (), ceiling=-25, per_requirement=5)

    assert penalty.points == 0
    assert penalty.applicable is False


def test_a_required_degree_never_reaches_the_penalty() -> None:
    """§5.2, mechanically. The gate owns `degree`; a penalty for one is the
    eligibility state converted into points by another route."""
    posting = _posting(
        requirements=(
            RequirementProposal(
                kind="degree",
                value="bachelors",
                raw_text="Bachelor's degree",
                char_start=0,
                char_end=17,
                necessity="required",
            ),
        )
    )

    penalty = penalize_missing_requirements(posting, (), ceiling=-25, per_requirement=5)

    assert penalty.points == 0
    assert penalty.applicable is False


def test_every_requirement_kind_is_owned_by_the_gate_the_penalty_or_the_level() -> None:
    """The guard that makes the exclusion above survive a seventh kind.

    Adding a `RequirementKind` and forgetting this penalty means it either
    silently starts charging for a gate dimension or silently ignores a real
    requirement. Neither fails anything else, so this goes red instead and
    forces the decision to be taken rather than inherited.
    """
    gate = set(get_args(Dimension))
    assert {kind.value for kind in RequirementKind} == gate | {"technology", "role_level"}
    assert PENALIZED_REQUIREMENT_KINDS == frozenset({"technology"})
    assert not PENALIZED_REQUIREMENT_KINDS & gate


# ---------------------------------------------------------------------------
# The seniority-mismatch penalty — 0 to -30
# ---------------------------------------------------------------------------

_LADDER = {
    Seniority.INTERNSHIP: 0,
    Seniority.NEW_GRAD: 0,
    Seniority.JUNIOR: 1,
    Seniority.MID: 3,
    Seniority.SENIOR: 5,
    Seniority.STAFF: 8,
    Seniority.DIRECTOR: 10,
}


def _seniority_penalty(
    seniority: Seniority | None, years: int | None, *, per_year: int = 3, ceiling: int = -30
) -> Penalty:
    return penalize_seniority_mismatch(
        _posting(seniority=seniority),
        ScoringProfile(years_experience=years),
        ceiling=ceiling,
        per_year=per_year,
        implied_years=_LADDER,
    )


def test_a_staff_posting_costs_an_early_career_profile_points() -> None:
    penalty = _seniority_penalty(Seniority.STAFF, 1)

    assert penalty.points == -21  # (8 implied - 1 stated) * 3
    assert penalty.compared["posting_implies_years"] == 8
    assert penalty.compared["stated_years"] == 1


def test_a_posting_pitched_at_or_below_the_persons_level_costs_nothing() -> None:
    penalty = _seniority_penalty(Seniority.JUNIOR, 5)

    assert penalty.points == 0
    assert penalty.applicable is True


def test_the_seniority_penalty_stops_at_its_ceiling() -> None:
    penalty = _seniority_penalty(Seniority.DIRECTOR, 0, per_year=6)

    assert penalty.points == -30  # 10 * 6 capped


def test_a_profile_stating_no_years_of_experience_is_not_penalised() -> None:
    """I2. `years_experience` is null for most profiles and null means *not
    told*, never zero. Reading it as zero charges every silent profile the full
    penalty on every senior posting in the corpus — an invented qualification
    claim, pointed downwards."""
    penalty = _seniority_penalty(Seniority.STAFF, None)

    assert penalty.points == 0
    assert penalty.applicable is False


def test_an_unclear_posting_level_is_not_penalised() -> None:
    assert _seniority_penalty(Seniority.UNCLEAR, 1).applicable is False
    assert _seniority_penalty(None, 1).applicable is False


def test_a_level_the_ladder_does_not_name_is_an_error_not_a_zero() -> None:
    """A missing rung must not read as "this posting deserves no penalty"."""
    with pytest.raises(KeyError):
        penalize_seniority_mismatch(
            _posting(seniority=Seniority.STAFF),
            ScoringProfile(years_experience=1),
            ceiling=-30,
            per_year=3,
            implied_years={Seniority.JUNIOR: 1},
        )


def test_a_senior_title_is_a_penalty_and_can_never_be_a_blocker() -> None:
    """The acceptance line for this task, asserted where it can actually fail.

    M3b refused to let seniority produce `ineligible`, on A13's grounds: a
    posting's title is not a statement about who may apply. The mechanical form
    of that refusal is that the gate has no seniority dimension at all — so this
    penalty cannot become a blocker without someone adding one, and adding one
    turns this red.
    """
    assert "role_level" not in get_args(Dimension)
    assert "seniority" not in get_args(Dimension)

    penalty = _seniority_penalty(Seniority.DIRECTOR, 0, per_year=6)
    assert penalty.points == -30
    assert not hasattr(penalty, "blocks")


# ---------------------------------------------------------------------------
# Composition — the total out of what could be assessed (§5.1.1, Q6)
# ---------------------------------------------------------------------------


def _weights(**overrides: int) -> MatchingWeights:
    """§5.1's published numbers, written out rather than loaded.

    Task 7 may tune the committed file; what these tests assert is the shape of
    the arithmetic, which tuning must not change.
    """
    components = {
        "role_relevance": 20,
        "skill_overlap": 30,
        "project_evidence": 20,
        "location_and_work_mode": 10,
        "listing_freshness": 10,
        "early_career_priority": 10,
    }
    components.update(overrides)
    return MatchingWeights(
        version="test.1",
        components=components,
        penalties={"missing_requirement": -25, "seniority_mismatch": -30},
        thresholds={},
    )


def _component(
    component: MatchComponent, points: int, *, assessable: bool = True
) -> ComponentScore:
    return ComponentScore(
        component=component,
        points=points,
        assessable=assessable,
        why="fixture",
        evidence=(
            (Evidence(component=component, points=points, compared={"fixture": True}),)
            if points
            else ()
        ),
    )


def test_a_fully_assessable_posting_is_scored_out_of_one_hundred() -> None:
    score = compose_score(tuple(_component(c, 0) for c in MatchComponent), (), weights=_weights())

    assert score.assessed_out_of == 100


def test_a_posting_naming_no_technology_is_scored_out_of_fifty() -> None:
    """Q6's answer, and the 43% of the corpus it was measured on.

    Skill overlap and project evidence both read the required-technology list.
    A posting naming none leaves 50 points nobody can compute, and the total
    says so instead of pretending the person scored zero on them.
    """
    components = tuple(
        _component(c, 0, assessable=c not in (MatchComponent.SKILL, MatchComponent.PROJECT))
        for c in MatchComponent
    )

    score = compose_score(components, (), weights=_weights())

    assert score.assessed_out_of == 50
    assert {c.component for c in score.unassessable} == {
        MatchComponent.SKILL,
        MatchComponent.PROJECT,
    }


def test_the_fraction_is_what_the_ranked_list_sorts_on() -> None:
    """The reason the denominator is stored rather than assumed.

    25 out of 50 and 50 out of 100 are the same match. Ranking on the raw total
    puts every terse posting below every verbose one, which measures the
    employer's prose and not the fit — §5.1's `application_urgency` argument.
    """
    terse = compose_score(
        (
            _component(MatchComponent.ROLE, 20),
            _component(MatchComponent.SKILL, 0, assessable=False),
            _component(MatchComponent.PROJECT, 0, assessable=False),
            _component(MatchComponent.LOCATION, 5),
            _component(MatchComponent.FRESHNESS, 0),
            _component(MatchComponent.PRIORITY, 0),
        ),
        (),
        weights=_weights(),
    )
    verbose = compose_score(
        (
            _component(MatchComponent.ROLE, 20),
            _component(MatchComponent.SKILL, 20),
            _component(MatchComponent.PROJECT, 5),
            _component(MatchComponent.LOCATION, 5),
            _component(MatchComponent.FRESHNESS, 0),
            _component(MatchComponent.PRIORITY, 0),
        ),
        (),
        weights=_weights(),
    )

    assert (terse.overall, terse.assessed_out_of) == (25, 50)
    assert (verbose.overall, verbose.assessed_out_of) == (50, 100)
    assert terse.fraction == verbose.fraction == 0.5
    assert terse.overall < verbose.overall


def test_a_score_nothing_could_assess_has_no_fraction_at_all() -> None:
    """Not zero, which sorts last, and not one, which sorts first.

    A profile with no skills, no projects, no stated roles or places against a
    posting with no dates and no readable level reaches this. Giving it a number
    is the vacuous-metric failure §1.1 of the architecture doc names.
    """
    score = compose_score(
        tuple(_component(c, 0, assessable=False) for c in MatchComponent), (), weights=_weights()
    )

    assert score.assessed_out_of == 0
    assert score.fraction is None
    assert score.overall == 0


def test_the_total_is_the_sum_of_its_parts() -> None:
    """The `the_total_is_its_parts` check constraint, asserted without Postgres."""
    components = (
        _component(MatchComponent.ROLE, 20),
        _component(MatchComponent.SKILL, 15),
        _component(MatchComponent.PROJECT, 10),
        _component(MatchComponent.LOCATION, 10),
        _component(MatchComponent.FRESHNESS, 7),
        _component(MatchComponent.PRIORITY, 0),
    )

    score = compose_score(components, (), weights=_weights())

    assert score.component_total == 62
    assert score.overall == 62


def test_the_overall_is_floored_at_zero_and_the_parts_still_show_why() -> None:
    """Components reach 100 and penalties reach -55, so the arithmetic can go
    negative and the meaning cannot. The floor is applied to the total only —
    the penalty rows keep their real values, or the breakdown stops explaining
    the number."""
    components = tuple(_component(c, 0) for c in MatchComponent)
    penalties = (
        Penalty(name="missing_requirement", points=-25, applicable=True, why="fixture"),
        Penalty(name="seniority_mismatch", points=-30, applicable=True, why="fixture"),
    )

    score = compose_score(components, penalties, weights=_weights())

    assert score.penalty_total == -55
    assert score.component_total == 0
    assert score.overall == 0


def test_penalties_do_not_change_the_denominator() -> None:
    """A penalty is a subtraction from the numerator, not a widening of what
    could be assessed. Adding it to the denominator would make a heavily
    penalised posting look like it was scored out of more."""
    components = tuple(_component(c, 0) for c in MatchComponent)
    penalised = compose_score(
        components,
        (Penalty(name="missing_requirement", points=-10, applicable=True, why="fixture"),),
        weights=_weights(),
    )

    assert penalised.assessed_out_of == 100


def test_a_penalty_that_adds_points_is_unrepresentable() -> None:
    with pytest.raises(ValueError, match="never adds"):
        Penalty(name="missing_requirement", points=5, applicable=True, why="fixture")


def test_a_penalty_that_did_not_apply_cannot_have_cost_anything() -> None:
    with pytest.raises(ValueError, match="did not apply"):
        Penalty(name="seniority_mismatch", points=-3, applicable=False, why="fixture")


def test_every_component_has_a_weight() -> None:
    """`MatchComponent`'s docstring promises this test by name.

    The two vocabularies are deliberately different strings — one names a kind
    of claim in the database, the other names a weight in a file a human edits —
    and nothing but this keeps them mapped rather than merely similar.
    """
    assert set(WEIGHT_NAME) == set(MatchComponent)
    assert sorted(WEIGHT_NAME.values()) == sorted(COMPONENT_NAMES)


# ---------------------------------------------------------------------------
# The whole score, end to end
# ---------------------------------------------------------------------------


def test_score_match_runs_every_component_and_both_penalties() -> None:
    profile = ScoringProfile(
        skills=(ConfirmedSkill(name="Python"),),
        preferred_roles=("backend engineer",),
        preferred_locations=("New York",),
        years_experience=1,
    )
    posting = _posting(
        seniority=Seniority.STAFF,
        locations=(JobLocationForScoring(city="New York"),),
        source_published_at=date(2026, 8, 1),
    )

    score = score_match(posting, profile, weights=load_weights(), as_of=date(2026, 8, 9))

    assert {c.component for c in score.components} == set(MatchComponent)
    assert {p.name for p in score.penalties} == set(PENALTY_NAMES)
    # One of two required technologies confirmed, and one unevidenced.
    assert score.penalties[0].points == -5
    assert score.penalty_total < 0
    assert score.overall == max(0, score.component_total + score.penalty_total)


def test_the_same_inputs_score_identically_twice() -> None:
    """M3's acceptance criterion, in the smallest form that can hold it. The
    corpus-wide version with its stored rows is Task 6's golden test."""
    profile = ScoringProfile(
        skills=(ConfirmedSkill(name="Python"),), preferred_roles=("backend engineer",)
    )
    args = (_posting(source_published_at=date(2026, 7, 1)), profile)
    kwargs = {"weights": load_weights(), "as_of": date(2026, 8, 9)}

    assert score_match(*args, **kwargs) == score_match(*args, **kwargs)  # type: ignore[arg-type]


def test_a_score_missing_a_component_is_refused() -> None:
    """Five components sum to a smaller total *and* a smaller denominator, so
    the fraction still looks reasonable and nothing else notices.

    Task 8 assembles this tuple from six separate calls; dropping one there is
    a plausible edit, and the failure it produces is a score that is quietly
    out of 90 while claiming to be a match.
    """
    five = tuple(_component(c, 0) for c in MatchComponent if c is not MatchComponent.PRIORITY)

    with pytest.raises(ValueError, match="priority"):
        compose_score(five, (), weights=_weights())


def test_a_component_counted_twice_is_refused() -> None:
    duplicated = (*(_component(c, 0) for c in MatchComponent), _component(MatchComponent.ROLE, 0))

    with pytest.raises(ValueError, match="role"):
        compose_score(duplicated, (), weights=_weights())
