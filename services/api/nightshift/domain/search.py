"""Job search: the query model, and the filters it becomes.

Routes validate and delegate (CLAUDE.md §3), so the decisions live here rather
than in ``api/routes/jobs.py``. The decisions worth naming:

* A blank search box is not a filter. ``q=""`` returns the corpus, not nothing.
* ``salary_at_least`` cannot silently hide the majority of the corpus. Most
  postings state no salary at all (A10), so the route counts what this filter
  excluded and the UI says so out loud.
* There is no borough filter, and its absence is an I1 matter rather than a
  scheduling one. See ``DEFERRED_FILTERS``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import ColumnElement, func, or_, select

from nightshift.db.base import (
    EmploymentType,
    InternshipSeason,
    JobStatus,
    LocationConfidence,
    RemotePolicy,
    RequirementKind,
    Seniority,
)
from nightshift.db.models import (
    Company,
    Job,
    JobLocation,
    JobRequirement,
    JobSourceLink,
    Source,
    SourceJobRecord,
)
from nightshift.domain.skill_vocabulary import load_vocabulary


def _require_aware(value: datetime | None) -> datetime | None:
    """UTC in the database, always (CLAUDE.md §7). Naive input is a caller bug."""
    if value is not None and value.tzinfo is None:
        raise ValueError("first_seen_after must carry a timezone")
    return value


class JobSearchQuery(BaseModel):
    """Everything M2a can filter on, and nothing it cannot."""

    q: str | None = None
    # Widens `q` from the title to the title-plus-description vector. Off by
    # default, and the reason is measured rather than assumed: on the recorded
    # Alloy board `q=developer` matches all nine postings through the
    # description, because it stems to 'develop' and every description says
    # "business development" somewhere. Without relevance ranking (M3,
    # PRODUCT-SPEC §24) a description-wide default returns the corpus in
    # recency order, which is a search box that does nothing.
    include_description: bool = False
    company: str | None = None
    city: str | None = None
    employment_type: EmploymentType | None = None
    remote_policy: RemotePolicy | None = None
    job_status: JobStatus | None = None
    confidence: LocationConfidence | None = None
    source: str | None = None
    first_seen_after: Annotated[datetime | None, AfterValidator(_require_aware)] = None
    salary_at_least: float | None = Field(default=None, ge=0)
    # M3b Task 11. Both were deferred at M2a and both come on with what they are
    # based on stated beside them, which is the human's decision of 2026-08-05.
    skill: str | None = None
    internship_season: InternshipSeason | None = None
    #: Not bounded to a plausible window, for the same reason the column is not.
    #: A range meaning "near now" makes the filter behave differently next year;
    #: `ge=2000` only rejects what no posting states anyway.
    internship_year: int | None = Field(default=None, ge=2000)


class DeferredFilter(BaseModel):
    """A filter PRODUCT-SPEC §12.2 asks for that M2a will not fake.

    Serialised to the client so the panel can render it disabled with the
    reason showing, rather than omitting it and leaving the gap invisible.
    """

    name: str
    blocked_on: str
    reason: str


DEFERRED_FILTERS: tuple[DeferredFilter, ...] = (
    DeferredFilter(
        name="match_score",
        blocked_on="M3",
        reason="No score exists yet. I4 forbids presenting one without a breakdown.",
    ),
    DeferredFilter(
        name="eligibility",
        blocked_on="M3",
        reason="Requires the deterministic eligibility gate.",
    ),
    # `skill` and `internship_season` were both here until M3b Task 11.
    #
    # The `skill` entry outlived two separate reasons. The first — "requires the
    # skill taxonomy and its aliases" — went stale at M2c when `skills.yaml`
    # landed, and nobody noticed for a milestone. The second was measured rather
    # than assumed, which is why it could be watched: required-technology recall
    # of 0.459 meant a filter would hide more than half the postings asking for
    # a skill. M3a.1 moved that to 0.861 and the reason went stale in turn — but
    # this time PROGRESS caught it in the same session.
    #
    # 0.861 hides roughly one matching role in seven, so the filter ships with
    # that stated on the panel and with `excluded_no_requirements` counting the
    # postings it could not have matched. Turning it on with no caveat was
    # rejected: it would be the first filter in this product that quietly
    # returns an incomplete result.
    DeferredFilter(
        name="borough",
        blocked_on="M4",
        reason=(
            "A posting that says 'New York, NY' does not say which borough it is in, "
            "and inferring one would be the interpolation invariant I1 forbids. "
            "Boroughs arrive with the geocoder at M4. Filter by city instead."
        ),
    ),
)


def salary_excluded_filter() -> ColumnElement[bool]:
    """Jobs the salary floor necessarily hides: the ones stating no salary.

    Exported so the route can count them. A filter that quietly drops most of
    the corpus is the A10 failure this project keeps designing against.
    """
    return Job.salary_min.is_(None) & Job.salary_max.is_(None)


def canonical_skill(term: str) -> str:
    """The vocabulary's name for a skill a person typed.

    `job_requirements.value` stores canonical names, so a filter comparing the
    raw string returns nothing for every alias somebody is likely to type —
    `GCP`, `golang`, `pytorch` — and an empty result is indistinguishable from
    "no such job". Resolving here means the filter and the answer-key grader
    ask the same question of the same vocabulary.

    Unknown terms come back unchanged and therefore match nothing, which is the
    honest outcome: the corpus is not indexed for a technology `skills.yaml` has
    never heard of, and resolving it to a near neighbour would answer a
    different question than the one asked.
    """
    return load_vocabulary().canonical(term.strip())


def skill_excluded_filter() -> ColumnElement[bool]:
    """Jobs the skill filter cannot match however well it works: the ones with
    no technology requirement extracted at all.

    These are not evidence of a posting that wants nothing. They are postings
    the extractor got nothing out of — a PDF-ish description, an unusual layout,
    a vocabulary gap. Counting them separately is what keeps a thin result
    readable as "we could not read 4 of these" rather than as "there are only
    two such jobs".
    """
    return ~Job.id.in_(
        select(JobRequirement.job_id).where(JobRequirement.kind == RequirementKind.TECHNOLOGY)
    )


def season_excluded_filter(query: JobSearchQuery) -> ColumnElement[bool]:
    """Internships the season filter necessarily hides: the ones stating nothing
    in the dimension that was asked about.

    Measured over the recorded corpus, 11 of 19 internships name no season and
    9 of 19 name no year. **A season filter is the most aggressive hider in this
    product** — more so than the salary floor — so the number belongs on screen
    beside the result for the same reason A10 put the salary one there.

    It takes the query because the answer differs by dimension: asking for
    `summer` hides the internships with no season, asking for `2027` hides the
    ones with no year, and asking for both hides either.

    Non-internships are not counted. They are excluded by being the wrong kind
    of posting, which is the filter working, not a gap in what was read.
    """
    unstated = [
        column.is_(None)
        for column, asked in (
            (Job.internship_season, query.internship_season),
            (Job.internship_year, query.internship_year),
        )
        if asked is not None
    ]
    return (Job.seniority == Seniority.INTERNSHIP) & or_(*unstated)


def build_filters(query: JobSearchQuery) -> list[ColumnElement[bool]]:
    """Turn the query model into SQLAlchemy predicates, in a stable order."""
    filters: list[ColumnElement[bool]] = []

    if query.q and query.q.strip():
        # websearch_to_tsquery, not plainto_tsquery: it understands quoted
        # phrases and a leading '-' for exclusion, and it never raises on
        # syntax a person typed. plainto_ would treat a quote as a word.
        tsquery = func.websearch_to_tsquery("english", query.q.strip())
        target = Job.search_vector if query.include_description else Job.title_vector
        filters.append(target.op("@@")(tsquery))

    if query.company and query.company.strip():
        needle = query.company.strip().lower()
        filters.append(Job.company.has(func.lower(Company.canonical_name).contains(needle)))

    if query.city and query.city.strip():
        # Matches what the source actually wrote. lower() to hit
        # ix_job_locations_city_lower rather than scanning.
        needle = query.city.strip().lower()
        filters.append(
            Job.id.in_(select(JobLocation.job_id).where(func.lower(JobLocation.city) == needle))
        )

    if query.employment_type is not None:
        filters.append(Job.employment_type == query.employment_type)

    if query.remote_policy is not None:
        filters.append(Job.remote_policy == query.remote_policy)

    if query.job_status is not None:
        filters.append(Job.status == query.job_status)

    if query.confidence is not None:
        filters.append(
            Job.id.in_(
                select(JobLocation.job_id).where(
                    JobLocation.location_confidence == query.confidence
                )
            )
        )

    if query.source and query.source.strip():
        needle = query.source.strip().lower()
        filters.append(
            Job.id.in_(
                select(JobSourceLink.job_id)
                .join(
                    SourceJobRecord,
                    SourceJobRecord.id == JobSourceLink.source_job_record_id,
                )
                .join(Source, Source.id == SourceJobRecord.source_id)
                .where(func.lower(Source.name).contains(needle))
            )
        )

    if query.first_seen_after is not None:
        filters.append(Job.first_seen_at >= query.first_seen_after)

    if query.salary_at_least is not None:
        # Either bound clearing the floor is enough: a range of 80k-120k does
        # pay at least 90k for somebody. A posting with no salary at all cannot
        # satisfy this and is counted separately rather than silently dropped.
        filters.append(
            or_(
                Job.salary_max >= query.salary_at_least,
                Job.salary_min >= query.salary_at_least,
            )
        )

    if query.skill and query.skill.strip():
        # Any necessity, deliberately. Restricting to `required` would hide a
        # posting that lists Python under "nice to have" — a posting that does
        # ask for Python and that the person can apply to. The filter's promise
        # is "this posting names this technology", which is what the extraction
        # supports; which list it sits in is shown on the job page, where it can
        # be read rather than silently applied.
        filters.append(
            Job.id.in_(
                select(JobRequirement.job_id).where(
                    JobRequirement.kind == RequirementKind.TECHNOLOGY,
                    JobRequirement.value == canonical_skill(query.skill),
                )
            )
        )

    if query.internship_season is not None:
        filters.append(Job.internship_season == query.internship_season)

    if query.internship_year is not None:
        filters.append(Job.internship_year == query.internship_year)

    return filters
