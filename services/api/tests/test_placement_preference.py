"""Which of several true statements the map speaks with.

archipelago.md §6: a New York location wins, then the primary, then the first.
Nothing is deleted — every other location is still stored and still returned by
the API, and named in the detail panel.
"""

from __future__ import annotations

import uuid

from nightshift.db.base import Landmass, LocationConfidence
from nightshift.db.models import Job, JobLocation
from nightshift.domain.placement import placement_location


def _row(landmass: Landmass, raw_text: str, *, is_primary: bool) -> JobLocation:
    """An unattached JobLocation. `placement_location` is pure over `job.locations`,
    so this needs no session and no database."""
    return JobLocation(
        id=uuid.uuid4(),
        raw_text=raw_text,
        landmass=landmass,
        is_primary=is_primary,
        location_confidence=LocationConfidence.CITY_ONLY,
    )


def _job(*locations: JobLocation) -> Job:
    job = Job(id=uuid.uuid4(), title="Software Engineer Intern")
    job.locations = list(locations)
    return job


def _new_york(*, is_primary: bool = False) -> JobLocation:
    return _row(Landmass.NEW_YORK, "New York, NY", is_primary=is_primary)


def _london(*, is_primary: bool = False) -> JobLocation:
    return _row(Landmass.ELSEWHERE_CITY, "London, UK", is_primary=is_primary)


def _san_francisco(*, is_primary: bool = False) -> JobLocation:
    return _row(Landmass.ELSEWHERE_CITY, "San Francisco, CA", is_primary=is_primary)


def test_a_new_york_location_wins_over_a_primary_elsewhere() -> None:
    """The 71 roles this rule exists for: NY is listed, but not typed first."""
    ny = _new_york()
    job = _job(_london(is_primary=True), ny)
    assert placement_location(job) is ny


def test_the_primary_wins_when_no_location_is_new_york() -> None:
    primary = _london(is_primary=True)
    job = _job(_san_francisco(), primary)
    assert placement_location(job) is primary


def test_the_first_wins_when_nothing_is_primary() -> None:
    first = _san_francisco()
    job = _job(first, _london())
    assert placement_location(job) is first


def test_a_job_with_no_new_york_location_is_untouched() -> None:
    """The control. Without it this rule could move every beacon and still pass."""
    primary = _london(is_primary=True)
    job = _job(primary, _san_francisco())
    assert placement_location(job) is primary


def test_the_first_new_york_row_is_chosen_when_there_are_several() -> None:
    first_ny = _new_york()
    job = _job(_london(is_primary=True), first_ny, _new_york())
    assert placement_location(job) is first_ny


def test_a_job_with_no_locations_at_all_returns_none() -> None:
    assert placement_location(_job()) is None
