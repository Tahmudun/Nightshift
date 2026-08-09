"""The filter builder, as pure functions.

These tests do not touch a database. They assert the *decisions* — which rows a
filter is willing to claim, and which it refuses to guess about — because those
are the parts that can be wrong in a way no integration test would notice.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nightshift.db.base import EmploymentType, InternshipSeason, JobStatus, RemotePolicy
from nightshift.domain.search import (
    DEFERRED_FILTERS,
    JobSearchQuery,
    build_filters,
    canonical_skill,
)


def test_an_empty_query_filters_nothing() -> None:
    assert build_filters(JobSearchQuery()) == []


def test_each_field_contributes_one_filter() -> None:
    query = JobSearchQuery(
        q="platform engineer",
        company="datadog",
        city="Brooklyn",
        employment_type=EmploymentType.INTERNSHIP,
        remote_policy=RemotePolicy.HYBRID,
        job_status=JobStatus.OPEN,
        source="greenhouse",
        first_seen_after=datetime(2026, 7, 1, tzinfo=UTC),
        salary_at_least=90000.0,
    )
    assert len(build_filters(query)) == 9


def test_the_description_search_is_off_by_default() -> None:
    """Guarded at the model as well as the route.

    Found by mutation: flipping this default alone failed nothing, because the
    route re-declares its own default in the FastAPI signature. Two defaults
    govern one behaviour, so both need a test — otherwise whichever one is
    unguarded can drift and the other quietly covers for it.
    """
    assert JobSearchQuery().include_description is False


def test_the_default_search_target_is_the_title() -> None:
    """The measured reason: on the recorded Alloy board, searching descriptions
    for 'developer' matches all nine postings because it stems to 'develop'.
    Without relevance ranking (M3) that default is a search box that does
    nothing."""
    title_filters = build_filters(JobSearchQuery(q="developer"))
    wide_filters = build_filters(JobSearchQuery(q="developer", include_description=True))
    assert "title_vector" in str(title_filters[0])
    assert "search_vector" in str(wide_filters[0])


def test_blank_text_is_not_a_filter() -> None:
    """An empty search box must return the corpus, not zero rows."""
    for blank in ("", "   ", "\t"):
        assert build_filters(JobSearchQuery(q=blank)) == []


def test_blank_company_and_city_are_not_filters() -> None:
    assert build_filters(JobSearchQuery(company="  ", city="")) == []


def test_a_naive_first_seen_after_is_rejected() -> None:
    """Time is UTC in the database, always. A naive datetime is a bug, not a default."""
    with pytest.raises(ValueError, match="timezone"):
        # DTZ001 forbids a naive datetime, which is exactly the value under
        # test here — the whole point is that the model rejects it.
        JobSearchQuery(first_seen_after=datetime(2026, 7, 1))  # noqa: DTZ001


def test_a_negative_salary_floor_is_rejected() -> None:
    with pytest.raises(ValueError):
        JobSearchQuery(salary_at_least=-1.0)


def test_deferred_filters_name_what_blocks_them() -> None:
    """I4 and command-center.md §4.3: a missing filter is stated, with its reason."""
    names = {entry.name for entry in DEFERRED_FILTERS}
    assert names == {
        "match_score",
        "eligibility",
        "borough",
    }
    for entry in DEFERRED_FILTERS:
        # M3b, not M3: M3a landed and none of these arrived with it, so a bare
        # "M3" now points at a milestone that is partly done — which reads as
        # "any day now" for work that is not scheduled until the next slice.
        assert entry.blocked_on in {"M3", "M3b", "M4"}
        assert entry.reason.strip() != ""


def test_no_deferred_filter_blames_something_that_now_exists() -> None:
    """The stale-reason check, which this project keeps needing.

    A "not built" list goes stale in the one direction nobody looks: nobody
    re-reads it when the thing it was waiting for lands. M2c's and M2d's reviews
    each found one. This found the `skill` filter still blaming the absence of
    the skill taxonomy, which shipped at M2c.

    Only the named artefacts are checkable here — a test cannot read English —
    but these are the three that have actually gone stale.
    """
    built = ("skill taxonomy", "skills.yaml", "requirement extraction")
    for entry in DEFERRED_FILTERS:
        lowered = entry.reason.lower()
        for artefact in built:
            assert artefact not in lowered, (
                f"{entry.name} is deferred on {artefact!r}, which exists"
            )


class TestTheTwoFiltersM3bTurnsOn:
    """`skill` and `internship_season`, deferred since M2a and on as of Task 11.

    Both arrive with a caveat attached rather than silently, and the caveats are
    the reason these are tests rather than a line in a changelog. A filter that
    hides part of its own answer without saying so is worse than no filter,
    because an empty result reads as "no such job".
    """

    def test_a_season_and_a_year_are_two_filters_not_one(self) -> None:
        """The shape decision, asserted where it can be seen.

        Two corpus internships state a year and no season, so the two must be
        independently askable. Filtering "2027" and getting only the eight
        postings that also name a season would drop the two that named nothing
        but the year.
        """
        assert len(build_filters(JobSearchQuery(internship_season=InternshipSeason.SUMMER))) == 1
        assert len(build_filters(JobSearchQuery(internship_year=2027))) == 1
        assert (
            len(
                build_filters(
                    JobSearchQuery(internship_season=InternshipSeason.SUMMER, internship_year=2027)
                )
            )
            == 2
        )

    def test_a_skill_contributes_one_filter(self) -> None:
        assert len(build_filters(JobSearchQuery(skill="Python"))) == 1

    def test_a_blank_skill_is_not_a_filter(self) -> None:
        """Consistent with `q`: an empty box returns the corpus, not nothing."""
        assert build_filters(JobSearchQuery(skill="   ")) == []

    def test_a_skill_resolves_through_the_same_vocabulary_the_extractor_used(self) -> None:
        """`GCP` must find the postings stored as `Google Cloud`.

        `job_requirements.value` holds canonical names, so a filter comparing
        the user's raw string would return nothing for every alias a person is
        likely to type — and an empty result is indistinguishable from "no such
        job". This is M3a.1's opening defect (a grader comparing raw strings)
        in the one place a user would feel it.
        """
        assert canonical_skill("GCP") == "Google Cloud"
        assert canonical_skill("golang") == "Go"
        assert canonical_skill("  pytorch  ") == "PyTorch"

    def test_a_skill_the_vocabulary_does_not_carry_is_left_alone(self) -> None:
        """It then matches nothing, which is honest: the corpus is not indexed
        for a technology `data/skills.yaml` has never heard of. Rewriting it to
        a near neighbour would answer a question nobody asked."""
        assert canonical_skill("Fortran77") == "Fortran77"


def test_borough_is_deferred_for_an_invariant_reason_not_a_schedule() -> None:
    """The one deferral that is not about ordering. If this ever reads 'M3',
    somebody has decided to infer a borough from a city, which is I1."""
    borough = next(entry for entry in DEFERRED_FILTERS if entry.name == "borough")
    assert borough.blocked_on == "M4"
    assert "geocod" in borough.reason.lower()
