"""The filter builder, as pure functions.

These tests do not touch a database. They assert the *decisions* — which rows a
filter is willing to claim, and which it refuses to guess about — because those
are the parts that can be wrong in a way no integration test would notice.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nightshift.db.base import EmploymentType, JobStatus, RemotePolicy
from nightshift.domain.search import (
    DEFERRED_FILTERS,
    JobSearchQuery,
    build_filters,
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
        "skill",
        "internship_season",
        "borough",
    }
    for entry in DEFERRED_FILTERS:
        assert entry.blocked_on in {"M3", "M4"}
        assert entry.reason.strip() != ""


def test_borough_is_deferred_for_an_invariant_reason_not_a_schedule() -> None:
    """The one deferral that is not about ordering. If this ever reads 'M3',
    somebody has decided to infer a borough from a city, which is I1."""
    borough = next(entry for entry in DEFERRED_FILTERS if entry.name == "borough")
    assert borough.blocked_on == "M4"
    assert "geocod" in borough.reason.lower()
