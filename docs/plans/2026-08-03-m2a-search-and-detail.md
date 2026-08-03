# M2a — search, filters, detail pages

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person can find a specific job in the corpus by text, employer, city, employment type, remote policy, recency, salary and source, then open that job and its employer and see everything the system honestly knows.

**Architecture:** The filter set becomes a Pydantic model and a query builder in `nightshift/domain/search.py`; the route validates and delegates (CLAUDE.md §3). Postgres does the text search with a generated `tsvector` column and a GIN index — no new dependency. The web app holds filter state in the URL, so a filtered view is a link you can send.

**Tech Stack:** Postgres 16 full-text search, SQLAlchemy 2.0 async, FastAPI, Pydantic v2, Next.js App Router, TanStack Query, Zod, Playwright.

**Design:** `docs/architecture/command-center.md` §4. Read it first — it decides which spec'd filters are deferred and why.

## Global Constraints

- **I1** — no filter may infer a place the source did not state. There is no borough or neighborhood filter in M2 (`command-center.md` §4.3).
- **I4** — no match score, no eligibility, anywhere in this slice. They belong to M3.
- **A10** — a field the source omitted renders as "not provided by source", never as blank or zero. `first_seen_at` is never labelled "posted".
- **A3** — nothing in this slice is user-scoped yet, but no query may assume a single user exists.
- **Python** — full type annotations, mypy strict clean, ruff clean. Pydantic models at every boundary. Nothing outside `adapters/http.py` imports `httpx`.
- **TypeScript** — strict, no `any`. Every API response parsed through Zod before it reaches a component. Named exports. Colocated `*.test.ts`.
- **Colour** — `paper*` tokens are text, `ink*` tokens are surfaces and never carry text. A new colour token requires a new assertion in `colour-contrast.test.ts`.
- **Migrations** — reversible and tested both directions. `alembic check` must report no drift when the model and migration are both in.
- **TODOs** — must carry a milestone: `TODO(M3): ...`. A bare `TODO` fails lint.
- **Commits** — conventional and scoped. Run `make check` before each.

---

### Task 1: The search index

Adds the generated `tsvector` column and the indexes every later filter depends on. Nothing user-visible; everything after this is fast because of it.

**Files:**
- Modify: `services/api/nightshift/db/models.py` (the `Job` class, `__table_args__` at :199 and columns from :219)
- Create: `services/api/migrations/versions/20260803_1200_job_search_index.py`
- Create: `services/api/tests/test_search_index.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Job.search_vector` (a `TSVECTOR` column), and the indexes `ix_jobs_search_vector`, `ix_jobs_employment_type`, `ix_jobs_remote_policy`, `ix_jobs_first_seen_at`, `ix_jobs_salary_max`, `ix_job_locations_city_lower`.

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_search_index.py`:

```python
"""The search index exists in the database, and it indexes what we think it does.

A GIN index that was never created is invisible until the corpus is large
enough for the difference to matter, which is exactly when it is expensive to
discover. These tests ask the live catalogue rather than trusting the model.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def test_search_vector_column_exists_and_is_generated(db_session: AsyncSession) -> None:
    row = (
        await db_session.execute(
            text(
                """
                SELECT data_type, is_generated
                FROM information_schema.columns
                WHERE table_name = 'jobs' AND column_name = 'search_vector'
                """
            )
        )
    ).one_or_none()
    assert row is not None, "jobs.search_vector is missing"
    data_type, is_generated = row
    assert data_type == "tsvector"
    # ALWAYS, not NEVER: a column the application has to remember to update is
    # a column that goes stale on the one write path somebody forgets.
    assert is_generated == "ALWAYS"


@pytest.mark.parametrize(
    "index_name",
    [
        "ix_jobs_search_vector",
        "ix_jobs_employment_type",
        "ix_jobs_remote_policy",
        "ix_jobs_first_seen_at",
        "ix_jobs_salary_max",
        "ix_job_locations_city_lower",
    ],
)
async def test_index_exists(db_session: AsyncSession, index_name: str) -> None:
    found = (
        await db_session.execute(
            text("SELECT 1 FROM pg_indexes WHERE indexname = :name"), {"name": index_name}
        )
    ).scalar_one_or_none()
    assert found == 1, f"{index_name} is not in pg_indexes"


async def test_the_vector_indexes_title_and_description(db_session: AsyncSession) -> None:
    """Both source columns reach the vector, and stop words do not."""
    vector = (
        await db_session.execute(
            text(
                """
                SELECT to_tsvector(
                    'english',
                    coalesce(:title, '') || ' ' || coalesce(:description, '')
                )::text
                """
            ),
            {"title": "Senior Platform Engineer", "description": "Kubernetes and Terraform"},
        )
    ).scalar_one()
    assert "platform" in vector
    assert "kubernet" in vector  # stemmed
    # "and" is an english stop word and must not occupy a lexeme slot.
    assert "'and'" not in vector
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd services/api && pytest tests/test_search_index.py -v`
Expected: FAIL — `jobs.search_vector is missing`. (If Postgres is unreachable the tests skip rather than fail; start it with `make up` first, or the task is untested.)

- [ ] **Step 3: Add the column to the model**

In `services/api/nightshift/db/models.py`, add to the imports at the top:

```python
from sqlalchemy import Computed
from sqlalchemy.dialects.postgresql import TSVECTOR
```

Inside `class Job`, immediately after the `canonical_description_hash` column, add:

```python
    # Full-text search, computed by Postgres rather than by us. STORED means it
    # is written on insert and update and read straight off the heap; the GIN
    # index below is what makes `@@` cheap.
    #
    # The regconfig is the literal 'english' rather than a column, because
    # to_tsvector is only IMMUTABLE — and therefore only legal in a generated
    # column — when the configuration is fixed at definition time.
    # Typed Any, matching the `geom` column above: TSVECTOR has no Python
    # equivalent and annotating it `str` makes mypy strict reject the mapping.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_text, ''))",
            persisted=True,
        ),
        nullable=False,
    )
```

Extend `Job.__table_args__` with the new indexes (keep the existing entries):

```python
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_jobs_employment_type", "employment_type"),
        Index("ix_jobs_remote_policy", "remote_policy"),
        Index("ix_jobs_first_seen_at", "first_seen_at"),
        Index("ix_jobs_salary_max", "salary_max"),
```

**Do not add the city index to the model.** `ix_job_locations_city_lower` is an
index on the *expression* `lower(city)`, and Alembic's autogenerate does not
reflect expression indexes — declaring it on `JobLocation.__table_args__` makes
`alembic check` report a phantom diff on every subsequent run, and the usual
reaction to that is a migration that drops and recreates it forever.

The migration owns this index outright (Step 4 creates it with raw SQL), and
`test_index_exists` is what stops it silently disappearing. That test is the
reason it is safe to keep the index out of the model.

- [ ] **Step 4: Write the migration**

Create `services/api/migrations/versions/20260803_1200_job_search_index.py`:

```python
"""jobs.search_vector and the M2a filter indexes

M2a filters on text, employment type, remote policy, first-seen date, salary
and city. Every one of those is a sequential scan without an index, and the
milestone's acceptance criterion is that filters stay fast.

``search_vector`` is a STORED generated column rather than a trigger-maintained
one. A trigger is a second write path that can be forgotten; a generated column
cannot go stale because Postgres computes it. The regconfig is the literal
'english' because ``to_tsvector`` is only IMMUTABLE with a fixed configuration,
and only IMMUTABLE expressions are legal in a generated column.

Hand-checked after autogenerate for the defect recorded at the head of
``0002``: autogenerate emits ``nightshift.db.types.UTCDateTime`` without
importing ``nightshift``, which is a NameError at upgrade time. No UTCDateTime
column is added here, but the check is cheap and this is the third migration
that note has applied to.

The downgrade drops the column, which drops its index with it. The other five
indexes are dropped explicitly, because dropping an index Postgres created
implicitly is an error and dropping one it did not is a silent no-op — the
round-trip test asserts they are gone rather than trusting the exit code.

Revision ID: 0005_job_search
Revises: 0004_board_poll_state
Create Date: 2026-08-03 12:00:00+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_job_search"
down_revision: str | None = "0004_board_poll_state"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VECTOR = (
    "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_text, ''))"
)


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_VECTOR, persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_jobs_search_vector", "jobs", ["search_vector"], postgresql_using="gin"
    )
    op.create_index("ix_jobs_employment_type", "jobs", ["employment_type"])
    op.create_index("ix_jobs_remote_policy", "jobs", ["remote_policy"])
    op.create_index("ix_jobs_first_seen_at", "jobs", ["first_seen_at"])
    op.create_index("ix_jobs_salary_max", "jobs", ["salary_max"])
    op.execute(
        "CREATE INDEX ix_job_locations_city_lower ON job_locations (lower(city))"
    )


def downgrade() -> None:
    op.drop_index("ix_job_locations_city_lower", table_name="job_locations")
    op.drop_index("ix_jobs_salary_max", table_name="jobs")
    op.drop_index("ix_jobs_first_seen_at", table_name="jobs")
    op.drop_index("ix_jobs_remote_policy", table_name="jobs")
    op.drop_index("ix_jobs_employment_type", table_name="jobs")
    op.drop_index("ix_jobs_search_vector", table_name="jobs")
    op.drop_column("jobs", "search_vector")
```

- [ ] **Step 5: Apply it and run the tests**

Run: `make migrate && cd services/api && pytest tests/test_search_index.py -v`
Expected: all 9 PASS.

- [ ] **Step 6: Prove the migration reverses**

Run:
```bash
make migrate-down && make migrate
```
Then confirm the column really went away and came back rather than trusting the exit code:
```bash
docker compose -f infra/docker-compose.yml exec -T postgres \
  psql -U nightshift -d nightshift -c \
  "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_jobs_%' ORDER BY 1;"
```
Expected: the five `ix_jobs_*` indexes listed after the upgrade.

- [ ] **Step 7: Check for model/migration drift**

Run: `cd services/api && alembic check`
Expected: `No new upgrade operations detected.`

If it reports a diff on `search_vector`, the model's `Computed` string and the migration's `_VECTOR` differ by whitespace. Make them byte-identical.

- [ ] **Step 8: Commit**

```bash
git add services/api/nightshift/db/models.py \
        services/api/migrations/versions/20260803_1200_job_search_index.py \
        services/api/tests/test_search_index.py
git commit -m "feat(search): add the jobs search vector and the M2a filter indexes"
```

---

### Task 2: The query model and the filter builder

Pure domain logic, no database, no route. This is where the honest decisions live.

**Files:**
- Create: `services/api/nightshift/domain/search.py`
- Create: `services/api/tests/test_search.py`

**Interfaces:**
- Consumes: `Job`, `JobLocation`, `Company`, `Source`, `SourceJobRecord`, `JobSourceLink` from `nightshift.db.models`.
- Produces:
  - `class JobSearchQuery(BaseModel)` with fields `q: str | None`, `company: str | None`, `city: str | None`, `employment_type: EmploymentType | None`, `remote_policy: RemotePolicy | None`, `job_status: JobStatus | None`, `confidence: LocationConfidence | None`, `source: str | None`, `first_seen_after: datetime | None`, `salary_at_least: float | None`.
  - `def build_filters(query: JobSearchQuery) -> list[ColumnElement[bool]]`
  - `def salary_excluded_filter() -> ColumnElement[bool]` — the "states no salary" predicate, exported because the route counts what the salary filter hid.
  - `DEFERRED_FILTERS: tuple[DeferredFilter, ...]` and `class DeferredFilter(BaseModel)` with `name: str`, `blocked_on: str`, `reason: str`.

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_search.py`:

```python
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


def test_blank_text_is_not_a_filter() -> None:
    """An empty search box must return the corpus, not zero rows."""
    for blank in ("", "   ", "\t"):
        assert build_filters(JobSearchQuery(q=blank)) == []


def test_blank_company_and_city_are_not_filters() -> None:
    assert build_filters(JobSearchQuery(company="  ", city="")) == []


def test_a_naive_first_seen_after_is_rejected() -> None:
    """Time is UTC in the database, always. A naive datetime is a bug, not a default."""
    with pytest.raises(ValueError, match="timezone"):
        JobSearchQuery(first_seen_after=datetime(2026, 7, 1))


def test_a_negative_salary_floor_is_rejected() -> None:
    with pytest.raises(ValueError):
        JobSearchQuery(salary_at_least=-1.0)


def test_deferred_filters_name_what_blocks_them() -> None:
    """I4 and the design's §4.3: a missing filter is stated, with its reason."""
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
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd services/api && pytest tests/test_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.domain.search'`

- [ ] **Step 3: Write the module**

Create `services/api/nightshift/domain/search.py`:

```python
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
    JobStatus,
    LocationConfidence,
    RemotePolicy,
)
from nightshift.db.models import (
    Company,
    Job,
    JobLocation,
    JobSourceLink,
    Source,
    SourceJobRecord,
)


def _require_aware(value: datetime | None) -> datetime | None:
    """UTC in the database, always (CLAUDE.md §7). Naive input is a caller bug."""
    if value is not None and value.tzinfo is None:
        raise ValueError("first_seen_after must carry a timezone")
    return value


class JobSearchQuery(BaseModel):
    """Everything M2a can filter on, and nothing it cannot."""

    q: str | None = None
    company: str | None = None
    city: str | None = None
    employment_type: EmploymentType | None = None
    remote_policy: RemotePolicy | None = None
    job_status: JobStatus | None = None
    confidence: LocationConfidence | None = None
    source: str | None = None
    first_seen_after: Annotated[datetime | None, AfterValidator(_require_aware)] = None
    salary_at_least: float | None = Field(default=None, ge=0)


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
    DeferredFilter(
        name="skill",
        blocked_on="M3",
        reason="Requires the skill taxonomy and its aliases.",
    ),
    DeferredFilter(
        name="internship_season",
        blocked_on="M3",
        reason="Requires the seniority and role-family classifier.",
    ),
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


def build_filters(query: JobSearchQuery) -> list[ColumnElement[bool]]:
    """Turn the query model into SQLAlchemy predicates, in a stable order."""
    filters: list[ColumnElement[bool]] = []

    if query.q and query.q.strip():
        # websearch_to_tsquery, not plainto_tsquery: it understands quoted
        # phrases and a leading '-' for exclusion, and it never raises on
        # syntax a person typed. plainto_ would treat a quote as a word.
        filters.append(
            Job.search_vector.op("@@")(func.websearch_to_tsquery("english", query.q.strip()))
        )

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

    return filters
```

- [ ] **Step 4: Run the tests**

Run: `cd services/api && pytest tests/test_search.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Typecheck**

Run: `cd services/api && mypy nightshift`
Expected: `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
git add services/api/nightshift/domain/search.py services/api/tests/test_search.py
git commit -m "feat(search): add the job search query model and filter builder"
```

---

### Task 3: Wire the filters into `/jobs`

**Files:**
- Modify: `services/api/nightshift/api/routes/jobs.py:103-154` (the `list_jobs` handler)
- Modify: `services/api/nightshift/api/schemas.py:140-145` (`JobListOut`)
- Modify: `services/api/tests/test_routes.py` (append)

**Interfaces:**
- Consumes: `JobSearchQuery`, `build_filters`, `salary_excluded_filter`, `DEFERRED_FILTERS` from Task 2.
- Produces: `GET /jobs` accepting `q`, `company`, `city`, `employment_type`, `remote_policy`, `status`, `confidence`, `source`, `first_seen_after`, `salary_at_least`; `JobListOut` gaining `excluded_no_salary: int` and `deferred_filters: list[DeferredFilterOut]`.

- [ ] **Step 1: Write the failing tests**

Append to `services/api/tests/test_routes.py`. The file's existing fixtures seed a Lever board; these use the same client fixture:

```python
async def test_text_search_matches_a_title_word(client: AsyncClient) -> None:
    response = await client.get("/jobs", params={"q": "engineer"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    for item in body["items"]:
        haystack = item["title"].lower()
        assert "engineer" in haystack or "engineering" in haystack


async def test_a_blank_query_returns_the_corpus(client: AsyncClient) -> None:
    """An empty search box is not a filter. This is the regression that turns
    a search page into a permanently empty one."""
    everything = (await client.get("/jobs")).json()["total"]
    blank = (await client.get("/jobs", params={"q": "   "})).json()["total"]
    assert blank == everything


async def test_text_search_does_not_raise_on_punctuation_a_person_typed(
    client: AsyncClient,
) -> None:
    """websearch_to_tsquery tolerates this; plainto_tsquery would not."""
    for typed in ['"platform engineer"', "engineer -manager", "c++", "&&&"]:
        response = await client.get("/jobs", params={"q": typed})
        assert response.status_code == 200, f"{typed!r} produced {response.status_code}"


async def test_the_city_filter_matches_what_the_source_wrote(client: AsyncClient) -> None:
    response = await client.get("/jobs", params={"city": "new york"})
    assert response.status_code == 200
    for item in response.json()["items"]:
        cities = {(loc["city"] or "").lower() for loc in item["locations"]}
        assert "new york" in cities


async def test_a_salary_floor_reports_what_it_hid(client: AsyncClient) -> None:
    """A10: most postings state no salary, so a floor that silently removed
    them would misrepresent the corpus. The count is the honesty."""
    body = (await client.get("/jobs", params={"salary_at_least": 1})).json()
    assert body["excluded_no_salary"] >= 1
    for item in body["items"]:
        assert item["salary"]["provided"] is True


async def test_no_salary_filter_means_no_exclusion_count(client: AsyncClient) -> None:
    body = (await client.get("/jobs")).json()
    assert body["excluded_no_salary"] == 0


async def test_filters_compose(client: AsyncClient) -> None:
    """Two filters must intersect, not union — the classic and silent bug."""
    open_only = (await client.get("/jobs", params={"status": "open"})).json()["total"]
    both = (
        await client.get("/jobs", params={"status": "open", "q": "engineer"})
    ).json()["total"]
    assert both <= open_only


async def test_the_response_names_the_filters_it_will_not_fake(client: AsyncClient) -> None:
    body = (await client.get("/jobs")).json()
    names = {entry["name"] for entry in body["deferred_filters"]}
    assert "match_score" in names
    assert "borough" in names
    borough = next(e for e in body["deferred_filters"] if e["name"] == "borough")
    assert borough["blocked_on"] == "M4"


async def test_an_unknown_employment_type_is_rejected_not_ignored(
    client: AsyncClient,
) -> None:
    """A typo'd filter that returns everything is worse than an error: it looks
    like an answer."""
    response = await client.get("/jobs", params={"employment_type": "part_time_ish"})
    assert response.status_code == 422
```

- [ ] **Step 2: Run and watch them fail**

Run: `cd services/api && pytest tests/test_routes.py -k "search or filter or salary or corpus or deferred or employment" -v`
Expected: FAIL — unknown query parameters are ignored, so `test_text_search_matches_a_title_word` returns unfiltered rows and `excluded_no_salary` raises `KeyError`.

- [ ] **Step 3: Extend the response schema**

In `services/api/nightshift/api/schemas.py`, add above `JobListOut`:

```python
class DeferredFilterOut(BaseModel):
    """A filter the spec asks for that this milestone will not fake.

    Serialised so the panel renders it disabled with its reason visible. An
    omitted filter is an invisible gap; a named one is a decision.
    """

    name: str
    blocked_on: str
    reason: str
```

and change `JobListOut` to:

```python
class JobListOut(BaseModel):
    items: list[JobSummaryOut]
    total: int
    limit: int
    offset: int
    # A10: how many jobs the salary floor necessarily hid, because they state
    # no salary at all. Zero when no floor was given.
    excluded_no_salary: int = 0
    deferred_filters: list[DeferredFilterOut] = []
```

- [ ] **Step 4: Rewrite the handler**

Replace `list_jobs` in `services/api/nightshift/api/routes/jobs.py` with:

```python
@router.get("", response_model=JobListOut)
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(description="Full-text search over title and description")] = None,
    company: Annotated[str | None, Query(description="Company name substring")] = None,
    city: Annotated[str | None, Query(description="City exactly as the source wrote it")] = None,
    employment_type: Annotated[EmploymentType | None, Query()] = None,
    remote_policy: Annotated[RemotePolicy | None, Query()] = None,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    confidence: Annotated[
        LocationConfidence | None,
        Query(description="Only jobs with at least one location at this confidence"),
    ] = None,
    source: Annotated[str | None, Query(description="Source name substring")] = None,
    first_seen_after: Annotated[datetime | None, Query()] = None,
    salary_at_least: Annotated[float | None, Query(ge=0)] = None,
) -> JobListOut:
    """Search canonical jobs, most-recently-seen first.

    Ordering is recency, not relevance. PRODUCT-SPEC §24's ranking is M3 work
    and depends on the match score, so ranking by a relevance number here would
    be inventing half of it.
    """
    query = JobSearchQuery(
        q=q,
        company=company,
        city=city,
        employment_type=employment_type,
        remote_policy=remote_policy,
        job_status=job_status,
        confidence=confidence,
        source=source,
        first_seen_after=first_seen_after,
        salary_at_least=salary_at_least,
    )
    filters = build_filters(query)

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
    ).scalar_one()

    # What the salary floor necessarily removed, counted against the *other*
    # filters so the number describes this result set rather than the corpus.
    excluded_no_salary = 0
    if query.salary_at_least is not None:
        without_salary = build_filters(query.model_copy(update={"salary_at_least": None}))
        excluded_no_salary = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(*without_salary, salary_excluded_filter())
            )
        ).scalar_one()

    rows = (
        (
            await session.execute(
                select(Job)
                .where(*filters)
                .options(selectinload(Job.company), selectinload(Job.locations))
                # Deterministic: id breaks ties so pagination cannot skip or repeat
                # a row when several jobs share a last_seen_at, which they always do
                # because a whole board is ingested with one timestamp.
                .order_by(Job.last_seen_at.desc(), Job.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return JobListOut(
        items=[_to_summary(job) for job in rows],
        total=total,
        limit=limit,
        offset=offset,
        excluded_no_salary=excluded_no_salary,
        deferred_filters=[
            DeferredFilterOut(name=e.name, blocked_on=e.blocked_on, reason=e.reason)
            for e in DEFERRED_FILTERS
        ],
    )
```

Add the imports this needs at the top of the file:

```python
from datetime import datetime

from nightshift.api.schemas import DeferredFilterOut
from nightshift.db.base import EmploymentType, RemotePolicy
from nightshift.domain.search import (
    DEFERRED_FILTERS,
    JobSearchQuery,
    build_filters,
    salary_excluded_filter,
)
```

- [ ] **Step 5: Run the tests**

Run: `cd services/api && pytest tests/test_routes.py -v`
Expected: all PASS, including the pre-existing route tests — the old `status`, `company` and `confidence` parameters keep their names and behaviour.

- [ ] **Step 6: Mutation-check the honest bits**

Two guards here are load-bearing and must be shown able to fail.

Temporarily change `build_filters` so blank text still builds a filter:
```python
    if query.q is not None:          # was: if query.q and query.q.strip():
```
Run: `pytest tests/test_routes.py::test_a_blank_query_returns_the_corpus -v`
Expected: FAIL. Revert.

Temporarily hard-code `excluded_no_salary = 0`.
Run: `pytest tests/test_routes.py::test_a_salary_floor_reports_what_it_hid -v`
Expected: FAIL. Revert.

- [ ] **Step 7: Commit**

```bash
git add services/api/nightshift/api/routes/jobs.py \
        services/api/nightshift/api/schemas.py \
        services/api/tests/test_routes.py
git commit -m "feat(search): filter /jobs on text, city, type, source, date and salary"
```

---

### Task 4: The query-plan guard

The acceptance criterion is "filters return in <200ms on seeded data". A stopwatch assertion in CI is flaky and gets deleted; this asserts the structural property that keeps it true.

**Files:**
- Create: `services/api/tests/test_query_plans.py`

**Interfaces:**
- Consumes: `JobSearchQuery`, `build_filters` from Task 2.
- Produces: nothing importable.

**Why it is written this way — read before editing.** On a 31-row seeded table
Postgres will choose a sequential scan for *every* query, because scanning 31
rows is genuinely cheaper than an index lookup. A test asserting "the plan has
no Seq Scan" would therefore fail on correct code, and a test asserting the
opposite would pass on a table with no indexes at all — vacuous.

So the test sets `enable_seqscan = off`, which makes the planner prefer any
usable index, and asserts that one is used. That answers the question that
actually matters: **is this filter servable by an index?** It fails the day
somebody adds a filter on an unindexed column, which is the regression worth
catching, and it does not depend on corpus size.

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_query_plans.py`:

```python
"""Every supported filter is servable by an index.

See the plan's Task 4 note: this deliberately does not assert "no Seq Scan".
With `enable_seqscan = off` the planner prefers any usable index, so an
index-bearing filter produces an index node and an unindexed one falls back to
a sequential scan Postgres was told to avoid. That distinction is the test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import EmploymentType, JobStatus, RemotePolicy
from nightshift.db.models import Job
from nightshift.domain.search import JobSearchQuery, build_filters
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

INDEXED_QUERIES = [
    pytest.param(JobSearchQuery(q="engineer"), id="text"),
    pytest.param(JobSearchQuery(employment_type=EmploymentType.INTERNSHIP), id="employment_type"),
    pytest.param(JobSearchQuery(remote_policy=RemotePolicy.REMOTE), id="remote_policy"),
    pytest.param(JobSearchQuery(job_status=JobStatus.OPEN), id="status"),
    pytest.param(
        JobSearchQuery(first_seen_after=datetime(2026, 1, 1, tzinfo=UTC)), id="first_seen_after"
    ),
    pytest.param(JobSearchQuery(salary_at_least=50000.0), id="salary_at_least"),
    pytest.param(JobSearchQuery(city="New York"), id="city"),
]


def _index_nodes(node: dict[str, Any]) -> list[str]:
    """Every index this plan touches, at any depth."""
    found: list[str] = []
    if "Index Name" in node:
        found.append(str(node["Index Name"]))
    for child in node.get("Plans", []):
        found.extend(_index_nodes(child))
    return found


async def _plan(session: AsyncSession, query: JobSearchQuery) -> dict[str, Any]:
    statement = select(func.count()).select_from(Job).where(*build_filters(query))
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    raw = (await session.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))).scalar_one()
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return dict(parsed[0]["Plan"])


@pytest.mark.parametrize("query", INDEXED_QUERIES)
async def test_the_filter_can_be_served_by_an_index(
    db_session: AsyncSession, query: JobSearchQuery
) -> None:
    plan = await _plan(db_session, query)
    used = _index_nodes(plan)
    assert used, f"no index node in the plan for {query.model_dump(exclude_none=True)}"


async def test_a_filter_on_an_unindexed_column_is_detectable(
    db_session: AsyncSession,
) -> None:
    """Non-vacuity. `normalized_title` has an index; `description_text` does
    not, and a query against it must produce no index node — otherwise the
    assertion above would pass for anything."""
    statement = select(func.count()).select_from(Job).where(Job.description_text.like("%zzz%"))
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    raw = (await db_session.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))).scalar_one()
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    assert _index_nodes(dict(parsed[0]["Plan"])) == []
```

- [ ] **Step 2: Run it**

Run: `cd services/api && pytest tests/test_query_plans.py -v`
Expected: 8 PASS. If `city` fails, `ix_job_locations_city_lower` was created on `city` rather than `lower(city)` and the expression does not match the predicate — recheck Task 1 Step 4.

- [ ] **Step 3: Record the real number**

The plan test prevents regression; a measurement earns the criterion. With the seeded stack up:

```bash
curl -s -o /dev/null -w '%{time_total}s\n' \
  'http://127.0.0.1:8000/jobs?q=engineer&status=open&limit=25'
```

Run it five times and keep the slowest. Note the figure — it goes into PROGRESS in Task 10.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/test_query_plans.py
git commit -m "test(search): assert every filter is servable by an index"
```

---

### Task 5: Company routes

**Files:**
- Create: `services/api/nightshift/api/routes/companies.py`
- Modify: `services/api/nightshift/api/schemas.py` (append)
- Modify: `services/api/nightshift/api/main.py:12` and `:51`
- Create: `services/api/tests/test_company_routes.py`

**Interfaces:**
- Consumes: `Company`, `Job` models; `JobStatusCounts` from `nightshift.api.schemas`.
- Produces: `GET /companies` → `CompanyListOut`; `GET /companies/{company_id}` → `CompanyDetailOut` with `id`, `canonical_name`, `website`, `job_status_counts: JobStatusCounts`, `first_seen_at: datetime | None`.

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_company_routes.py`:

```python
"""Company routes against a real database.

`/companies/{id}` exists so a job's employer is a place you can go, not just a
string on a row. The counts are by closure state because a company page showing
only open roles hides the thing the closure machine exists to make visible.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.main import create_app
from nightshift.db.models import Company
from nightshift.db.session import get_db_session
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The app, reading the test's own uncommitted transaction.

    Same hazard as test_routes.py: letting the app open its own session would
    make it blind to this test's seed data and would commit for real.
    """
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


async def test_listing_companies_returns_the_seeded_ones(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seeded = (await db_session.execute(select(Company))).scalars().all()
    body = (await client.get("/companies")).json()
    assert body["total"] == len(seeded)
    assert {item["canonical_name"] for item in body["items"]} == {
        company.canonical_name for company in seeded
    }


async def test_a_company_detail_counts_jobs_by_closure_state(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company = (await db_session.execute(select(Company))).scalars().first()
    assert company is not None
    body = (await client.get(f"/companies/{company.id}")).json()
    assert body["canonical_name"] == company.canonical_name
    counts = body["job_status_counts"]
    # Every state present as an explicit integer: a missing key and a real zero
    # are different claims and the UI must not have to guess.
    assert set(counts) == {"open", "possibly_stale", "unverified", "closed"}
    assert sum(counts.values()) >= 1


async def test_an_unknown_company_is_404_not_an_empty_company(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/companies/{uuid4()}")
    assert response.status_code == 404


async def test_company_search_filters_by_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company = (await db_session.execute(select(Company))).scalars().first()
    assert company is not None
    fragment = company.canonical_name[:3].lower()
    body = (await client.get("/companies", params={"q": fragment})).json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert fragment in item["canonical_name"].lower()
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd services/api && pytest tests/test_company_routes.py -v`
Expected: FAIL — all four return 404, because no `/companies` router is registered.

- [ ] **Step 3: Add the schemas**

Append to `services/api/nightshift/api/schemas.py`:

```python
class CompanyRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    website: str | None
    job_count: int


class CompanyListOut(BaseModel):
    items: list[CompanyRowOut]
    total: int
    limit: int
    offset: int


class CompanyDetailOut(BaseModel):
    id: UUID
    canonical_name: str
    website: str | None
    job_status_counts: JobStatusCounts
    # Ours, not the source's. Never presented as "on the market since" (A10).
    first_seen_at: datetime | None
```

- [ ] **Step 4: Write the route**

Create `services/api/nightshift/api/routes/companies.py`:

```python
"""Company read routes.

A job's employer should be somewhere you can go. Counts are by closure state
rather than a single total, because a company page that shows only open roles
makes the closure machine invisible — the same reasoning as ``/jobs/admin``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.schemas import (
    CompanyDetailOut,
    CompanyListOut,
    CompanyRowOut,
    JobStatusCounts,
)
from nightshift.db.models import Company, Job
from nightshift.db.session import get_db_session

router = APIRouter(prefix="/companies", tags=["companies"])

MAX_LIMIT = 200


@router.get("", response_model=CompanyListOut)
async def list_companies(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: Annotated[str | None, Query(description="Company name substring")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyListOut:
    filters = []
    if q and q.strip():
        filters.append(func.lower(Company.canonical_name).contains(q.strip().lower()))

    total = (
        await session.execute(select(func.count()).select_from(Company).where(*filters))
    ).scalar_one()

    rows = (
        await session.execute(
            select(Company, func.count(Job.id))
            .outerjoin(Job, Job.company_id == Company.id)
            .where(*filters)
            .group_by(Company.id)
            # canonical_name then id: two employers can share a display name
            # after normalization keeps them apart, and pagination must be stable.
            .order_by(Company.canonical_name, Company.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return CompanyListOut(
        items=[
            CompanyRowOut(
                id=company.id,
                canonical_name=company.canonical_name,
                website=company.website,
                job_count=job_count,
            )
            for company, job_count in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{company_id}", response_model=CompanyDetailOut)
async def get_company(
    company_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyDetailOut:
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")

    counted = (
        await session.execute(
            select(Job.status, func.count())
            .where(Job.company_id == company_id)
            .group_by(Job.status)
        )
    ).all()

    first_seen = (
        await session.execute(
            select(func.min(Job.first_seen_at)).where(Job.company_id == company_id)
        )
    ).scalar_one_or_none()

    return CompanyDetailOut(
        id=company.id,
        canonical_name=company.canonical_name,
        website=company.website,
        job_status_counts=JobStatusCounts(**{s.value: c for s, c in counted}),
        first_seen_at=first_seen,
    )
```

- [ ] **Step 5: Register the router**

In `services/api/nightshift/api/main.py`, change line 12 to:

```python
from nightshift.api.routes import companies, health, jobs, sources
```

and add after line 51:

```python
    app.include_router(companies.router)
```

- [ ] **Step 6: Run the tests**

Run: `cd services/api && pytest tests/test_company_routes.py -v`
Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/nightshift/api/routes/companies.py \
        services/api/nightshift/api/schemas.py \
        services/api/nightshift/api/main.py \
        services/api/tests/test_company_routes.py
git commit -m "feat(companies): add company list and detail routes"
```

---

### Task 6: Web — schemas and the API client

**Files:**
- Modify: `apps/web/src/lib/schemas.ts` (after `jobListSchema` at :110-116)
- Modify: `apps/web/src/lib/api.ts:109-123` (`JobQuery` and `fetchJobs`)
- Modify: `apps/web/src/lib/schemas.test.ts` (append)

**Interfaces:**
- Consumes: `JobListOut`, `CompanyListOut`, `CompanyDetailOut` shapes from Tasks 3 and 5.
- Produces: `deferredFilterSchema`, `jobDetailSchema`, `companyRowSchema`, `companyListSchema`, `companyDetailSchema`, types `DeferredFilter`, `JobDetail`, `CompanyRow`, `CompanyList`, `CompanyDetail`; `fetchJobs(query: JobQuery)` accepting the full filter set, plus `fetchJob`, `fetchCompanies`, `fetchCompany`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/src/lib/schemas.test.ts`:

```ts
import { companyDetailSchema, jobDetailSchema, jobListSchema } from './schemas';

describe('jobListSchema', () => {
  it('defaults the honesty fields when an older API omits them', () => {
    const parsed = jobListSchema.parse({ items: [], total: 0, limit: 25, offset: 0 });
    expect(parsed.excluded_no_salary).toBe(0);
    expect(parsed.deferred_filters).toEqual([]);
  });

  it('keeps the reason a deferred filter carries', () => {
    const parsed = jobListSchema.parse({
      items: [],
      total: 0,
      limit: 25,
      offset: 0,
      excluded_no_salary: 3,
      deferred_filters: [
        { name: 'borough', blocked_on: 'M4', reason: 'needs the geocoder' },
      ],
    });
    expect(parsed.deferred_filters[0]?.reason).toBe('needs the geocoder');
  });
});

describe('companyDetailSchema', () => {
  it('requires every closure state as an explicit number', () => {
    expect(() =>
      companyDetailSchema.parse({
        id: '11111111-1111-4111-8111-111111111111',
        canonical_name: 'Datadog',
        website: null,
        job_status_counts: { open: 4, possibly_stale: 0, unverified: 0 },
        first_seen_at: null,
      }),
    ).toThrow();
  });
});

describe('jobDetailSchema', () => {
  it('accepts a job whose description the source never provided', () => {
    const parsed = jobDetailSchema.parse({
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Engineer',
      company: { id: '22222222-2222-4222-8222-222222222222', canonical_name: 'X', website: null },
      employment_type: 'full_time',
      remote_policy: 'unknown',
      status: 'open',
      locations: [],
      salary: { provided: false },
      source_published_at: null,
      source_updated_at: null,
      first_seen_at: '2026-08-03T00:00:00+00:00',
      last_seen_at: '2026-08-03T00:00:00+00:00',
      application_deadline: null,
      description_text: null,
      description_html: null,
      sources: [],
    });
    expect(parsed.description_text).toBeNull();
  });
});
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd apps/web && npx vitest run src/lib/schemas.test.ts`
Expected: FAIL — `companyDetailSchema` and `jobDetailSchema` are not exported.

- [ ] **Step 3: Add the schemas**

**Order matters here.** `jobListSchema` is going to reference
`deferredFilterSchema`, and these are `const` bindings evaluated top to bottom,
so the new schema must be declared *above* the existing `jobListSchema` at :110.
Insert this block immediately **before** `jobListSchema`:

```ts
/** A filter the spec asks for that this milestone will not fake. */
export const deferredFilterSchema = z.object({
  name: z.string(),
  blocked_on: z.string(),
  reason: z.string(),
});
export type DeferredFilter = z.infer<typeof deferredFilterSchema>;

export const jobSourceSchema = z.object({
  source_name: z.string(),
  source_job_id: z.string(),
  canonical_url: z.string().nullable(),
  first_seen_at: z.string().datetime({ offset: true }),
  last_seen_at: z.string().datetime({ offset: true }),
});

export const jobDetailSchema = jobSummarySchema.extend({
  description_text: z.string().nullable(),
  description_html: z.string().nullable(),
  sources: z.array(jobSourceSchema),
});
export type JobDetail = z.infer<typeof jobDetailSchema>;

export const jobStatusCountsSchema = z.object({
  open: z.number().int(),
  possibly_stale: z.number().int(),
  unverified: z.number().int(),
  closed: z.number().int(),
});

export const companyRowSchema = z.object({
  id: z.string().uuid(),
  canonical_name: z.string(),
  website: z.string().nullable(),
  job_count: z.number().int(),
});
export type CompanyRow = z.infer<typeof companyRowSchema>;

export const companyListSchema = z.object({
  items: z.array(companyRowSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type CompanyList = z.infer<typeof companyListSchema>;

export const companyDetailSchema = z.object({
  id: z.string().uuid(),
  canonical_name: z.string(),
  website: z.string().nullable(),
  job_status_counts: jobStatusCountsSchema,
  first_seen_at: z.string().datetime({ offset: true }).nullable(),
});
export type CompanyDetail = z.infer<typeof companyDetailSchema>;
```

Then extend `jobListSchema` in place — it is currently at :110:

```ts
export const jobListSchema = z.object({
  items: z.array(jobSummarySchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
  // Defaulted so a response from an older API parses rather than throwing.
  excluded_no_salary: z.number().int().default(0),
  deferred_filters: z.array(deferredFilterSchema).default([]),
});
```

Every schema in the inserted block references only `jobSummarySchema`, which is
already declared at :93 — above the insertion point — so nothing is used before
it is defined.

- [ ] **Step 4: Extend the API client**

In `apps/web/src/lib/api.ts`, replace `JobQuery` and `fetchJobs`:

```ts
export interface JobQuery {
  limit?: number;
  offset?: number;
  q?: string;
  company?: string;
  city?: string;
  employment_type?: string;
  remote_policy?: string;
  status?: string;
  confidence?: string;
  source?: string;
  first_seen_after?: string;
  salary_at_least?: number;
}

/** Only non-empty values become query parameters, so a cleared filter really clears. */
export function fetchJobs(query: JobQuery = {}): Promise<JobList> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit ?? 25));
  params.set('offset', String(query.offset ?? 0));
  const optional: ReadonlyArray<[string, string | number | undefined]> = [
    ['q', query.q],
    ['company', query.company],
    ['city', query.city],
    ['employment_type', query.employment_type],
    ['remote_policy', query.remote_policy],
    ['status', query.status],
    ['confidence', query.confidence],
    ['source', query.source],
    ['first_seen_after', query.first_seen_after],
    ['salary_at_least', query.salary_at_least],
  ];
  for (const [key, value] of optional) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  return request(`/jobs?${params.toString()}`, jobListSchema);
}

export function fetchJob(jobId: string): Promise<JobDetail> {
  return request(`/jobs/${jobId}`, jobDetailSchema);
}

export function fetchCompanies(q?: string): Promise<CompanyList> {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  return request(`/companies?${params.toString()}`, companyListSchema);
}

export function fetchCompany(companyId: string): Promise<CompanyDetail> {
  return request(`/companies/${companyId}`, companyDetailSchema);
}
```

Add the new names to the import block at the top of the file:

```ts
  companyDetailSchema,
  companyListSchema,
  jobDetailSchema,
  type CompanyDetail,
  type CompanyList,
  type JobDetail,
```

- [ ] **Step 5: Run tests and typecheck**

Run: `cd apps/web && npx vitest run && npx tsc --noEmit`
Expected: all tests PASS, `tsc` clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/schemas.ts apps/web/src/lib/api.ts apps/web/src/lib/schemas.test.ts
git commit -m "feat(web): add search, job detail and company schemas to the API client"
```

---

### Task 7: Web — the filter panel

**Files:**
- Create: `apps/web/src/components/JobFilters.tsx`
- Create: `apps/web/src/components/JobFilters.test.tsx`
- Modify: `apps/web/src/components/JobList.tsx`
- Modify: `apps/web/src/app/explore/page.tsx`

**Interfaces:**
- Consumes: `JobQuery`, `fetchJobs`, `DeferredFilter` from Task 6.
- Produces: `<JobFilters value={...} onChange={...} deferred={...} />`, and `JobList` reading filter state from the URL via `useSearchParams`.

**Design constraint.** CLAUDE.md §8 names "a 400-line React component that renders a map, fetches data, and holds filter state" as an anti-pattern. `JobFilters` renders controls and calls `onChange`. `JobList` fetches. The URL holds the state. None of the three knows what the others do.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/JobFilters.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { JobFilters } from './JobFilters';

const DEFERRED = [
  {
    name: 'borough',
    blocked_on: 'M4',
    reason: 'A posting saying "New York, NY" does not say which borough it is in.',
  },
  { name: 'match_score', blocked_on: 'M3', reason: 'No score exists yet.' },
];

describe('JobFilters', () => {
  it('reports a text change to its parent without fetching anything itself', async () => {
    const onChange = vi.fn();
    render(<JobFilters value={{}} onChange={onChange} deferred={[]} />);
    await userEvent.type(screen.getByLabelText(/search/i), 'engineer');
    expect(onChange).toHaveBeenCalled();
    const last = onChange.mock.calls.at(-1)?.[0] as { q?: string };
    expect(last.q).toBe('engineer');
  });

  it('names every deferred filter and shows its reason unexpanded', () => {
    render(<JobFilters value={{}} onChange={vi.fn()} deferred={DEFERRED} />);
    // Visible without clicking anything: the gap must not be hidden behind a
    // disclosure, the same rule the coverage page is tested against.
    expect(screen.getByText(/which borough it is in/i)).toBeVisible();
    expect(screen.getByText(/no score exists yet/i)).toBeVisible();
  });

  it('renders a deferred filter as disabled so it cannot be used', () => {
    render(<JobFilters value={{}} onChange={vi.fn()} deferred={DEFERRED} />);
    expect(screen.getByLabelText(/borough/i)).toBeDisabled();
  });

  it('clearing a field removes it rather than sending an empty string', async () => {
    const onChange = vi.fn();
    render(<JobFilters value={{ city: 'Brooklyn' }} onChange={onChange} deferred={[]} />);
    await userEvent.clear(screen.getByLabelText(/city/i));
    const last = onChange.mock.calls.at(-1)?.[0] as { city?: string };
    expect(last.city).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd apps/web && npx vitest run src/components/JobFilters.test.tsx`
Expected: FAIL — cannot resolve `./JobFilters`.

Note: if `@testing-library/user-event` is not yet a dependency, add it first:
```bash
cd apps/web && npm install --save-dev @testing-library/user-event
```

- [ ] **Step 3: Write the component**

Create `apps/web/src/components/JobFilters.tsx`:

```tsx
'use client';

/**
 * The filter controls. Renders and reports; it does not fetch and it does not
 * own state — CLAUDE.md §8.
 *
 * Deferred filters render disabled with their reason visible, rather than being
 * omitted. An absent control is an invisible gap; a disabled one with a
 * sentence attached is a decision the reader can check.
 */

import type { DeferredFilter } from '@/lib/schemas';
import type { JobQuery } from '@/lib/api';

const EMPLOYMENT_TYPES = [
  'full_time',
  'part_time',
  'internship',
  'contract',
  'temporary',
  'unknown',
] as const;

const REMOTE_POLICIES = ['on_site', 'hybrid', 'remote', 'unknown'] as const;

const LABEL = 'block font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';
const FIELD =
  'mt-1 w-full border border-ink-700 bg-ink-900 px-2 py-1.5 text-[13px] text-paper ' +
  'placeholder:text-paper-faint focus-visible:outline focus-visible:outline-1 ' +
  'focus-visible:outline-signal-400 disabled:cursor-not-allowed disabled:text-paper-faint';

export interface JobFiltersProps {
  value: JobQuery;
  onChange: (next: JobQuery) => void;
  deferred: readonly DeferredFilter[];
}

export function JobFilters({ value, onChange, deferred }: JobFiltersProps) {
  /** Empty means absent. An empty string in the URL is a filter matching nothing. */
  function set(key: keyof JobQuery, raw: string) {
    const next: JobQuery = { ...value };
    if (raw === '') {
      delete next[key];
    } else if (key === 'salary_at_least') {
      next.salary_at_least = Number(raw);
    } else {
      (next as Record<string, string>)[key] = raw;
    }
    onChange(next);
  }

  return (
    <div className="border border-ink-700 bg-ink-900/40 p-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label className={LABEL} htmlFor="filter-q">
            Search
          </label>
          <input
            id="filter-q"
            className={FIELD}
            type="search"
            placeholder="title or description"
            value={value.q ?? ''}
            onChange={(event) => set('q', event.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-company">
            Company
          </label>
          <input
            id="filter-company"
            className={FIELD}
            value={value.company ?? ''}
            onChange={(event) => set('company', event.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-city">
            City
          </label>
          <input
            id="filter-city"
            className={FIELD}
            placeholder="as the posting wrote it"
            value={value.city ?? ''}
            onChange={(event) => set('city', event.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-employment-type">
            Employment type
          </label>
          <select
            id="filter-employment-type"
            className={FIELD}
            value={value.employment_type ?? ''}
            onChange={(event) => set('employment_type', event.target.value)}
          >
            <option value="">any</option>
            {EMPLOYMENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-remote-policy">
            Remote policy
          </label>
          <select
            id="filter-remote-policy"
            className={FIELD}
            value={value.remote_policy ?? ''}
            onChange={(event) => set('remote_policy', event.target.value)}
          >
            <option value="">any</option>
            {REMOTE_POLICIES.map((policy) => (
              <option key={policy} value={policy}>
                {policy.replace('_', ' ')}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-salary">
            Pays at least
          </label>
          <input
            id="filter-salary"
            className={FIELD}
            type="number"
            min={0}
            placeholder="e.g. 90000"
            value={value.salary_at_least ?? ''}
            onChange={(event) => set('salary_at_least', event.target.value)}
          />
        </div>
      </div>

      {deferred.length > 0 && (
        <div className="mt-5 border-t border-ink-700 pt-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
            Not available yet
          </h3>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {deferred.map((entry) => (
              <li key={entry.name}>
                <label className={LABEL} htmlFor={`filter-${entry.name}`}>
                  {entry.name.replace(/_/g, ' ')}
                </label>
                <input
                  id={`filter-${entry.name}`}
                  className={FIELD}
                  disabled
                  value=""
                  readOnly
                  aria-describedby={`reason-${entry.name}`}
                />
                <p
                  id={`reason-${entry.name}`}
                  className="mt-1 text-[12px] leading-relaxed text-paper-dim"
                >
                  {entry.reason} <span className="text-paper-faint">({entry.blocked_on})</span>
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the component test**

Run: `cd apps/web && npx vitest run src/components/JobFilters.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Put the state in the URL**

Replace `apps/web/src/components/JobList.tsx` with:

```tsx
'use client';

/**
 * The jobs list. Reads filters from the URL, fetches, and delegates each row.
 *
 * The URL is the state, so a filtered view is a link you can send and the back
 * button works. Kept small on purpose — CLAUDE.md §8.
 */

import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo } from 'react';

import { JobFilters } from './JobFilters';
import { JobRow } from './JobRow';
import { fetchJobs, type JobQuery } from '@/lib/api';

const FILTER_KEYS = [
  'q',
  'company',
  'city',
  'employment_type',
  'remote_policy',
  'status',
  'confidence',
  'source',
  'salary_at_least',
] as const;

export function JobList() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const filters = useMemo<JobQuery>(() => {
    const next: JobQuery = {};
    for (const key of FILTER_KEYS) {
      const raw = searchParams.get(key);
      if (raw === null || raw === '') continue;
      if (key === 'salary_at_least') next.salary_at_least = Number(raw);
      else (next as Record<string, string>)[key] = raw;
    }
    return next;
  }, [searchParams]);

  const onChange = useCallback(
    (next: JobQuery) => {
      const params = new URLSearchParams();
      for (const key of FILTER_KEYS) {
        const value = next[key];
        if (value !== undefined && value !== '') params.set(key, String(value));
      }
      const queryString = params.toString();
      router.replace(queryString === '' ? '/explore' : `/explore?${queryString}`, {
        scroll: false,
      });
    },
    [router],
  );

  const { data, error, isPending } = useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => fetchJobs({ ...filters, limit: 50 }),
  });

  return (
    <div className="space-y-6">
      <JobFilters
        value={filters}
        onChange={onChange}
        deferred={data?.deferred_filters ?? []}
      />

      <section className="border border-ink-700 bg-ink-900/40">
        {isPending ? (
          <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
            Loading roles…
          </p>
        ) : error !== null ? (
          // §25: a failure states what happened and what to do, in the
          // interface's voice. It does not apologise and it is not vague.
          <div className="m-5 border border-alert-900 bg-alert-900/30 px-4 py-3">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
              Could not load roles
            </p>
            <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
          </div>
        ) : data.items.length === 0 ? (
          <div className="m-5 border border-ink-700 px-4 py-6">
            <p className="text-[14px] text-paper">No roles match these filters.</p>
            <p className="mt-1.5 text-[13px] text-paper-dim">
              Clear a filter, or run{' '}
              <code className="border border-ink-700 bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-signal-400">
                make seed
              </code>{' '}
              if the corpus is empty.
            </p>
          </div>
        ) : (
          <div>
            <div className="flex items-baseline justify-between border-b border-ink-700 px-5 py-2">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
                Roles
              </h2>
              <p className="font-mono text-[10px] tracking-wide text-paper-faint tnum">
                showing {data.items.length} of {data.total}
              </p>
            </div>
            {data.excluded_no_salary > 0 && (
              // A10: absence of data is data. A salary floor necessarily hides
              // every posting that states no salary, and most of them do.
              <p className="border-b border-ink-700 px-5 py-2 text-[12px] text-paper-dim">
                {data.excluded_no_salary} further{' '}
                {data.excluded_no_salary === 1 ? 'role states' : 'roles state'} no salary and
                cannot be matched against a floor.
              </p>
            )}
            {data.items.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 6: Wrap the page in a Suspense boundary**

`useSearchParams` requires one, and `next build` fails without it. In
`apps/web/src/app/explore/page.tsx`, change the JobList section to:

```tsx
      <Suspense
        fallback={
          <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
            Loading filters…
          </p>
        }
      >
        <JobList />
      </Suspense>
```

and add `import { Suspense } from 'react';` at the top. Remove the
`<section className="border border-ink-700 bg-ink-900/40">` wrapper that used to
surround `<JobList />` — the component now draws its own.

- [ ] **Step 7: Verify the whole web suite and the build**

Run: `cd apps/web && npx vitest run && npx tsc --noEmit && npx next build`
Expected: all PASS, `tsc` clean, build compiles.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/components/JobFilters.tsx \
        apps/web/src/components/JobFilters.test.tsx \
        apps/web/src/components/JobList.tsx \
        apps/web/src/app/explore/page.tsx \
        apps/web/package.json apps/web/package-lock.json
git commit -m "feat(web): add the job filter panel, with state in the URL"
```

---

### Task 8: Web — the job detail page

**Files:**
- Create: `apps/web/src/app/explore/jobs/[id]/page.tsx`
- Create: `apps/web/src/components/JobDetail.tsx`
- Create: `apps/web/src/components/JobDetail.test.tsx`
- Modify: `apps/web/src/components/JobRow.tsx` (link the title)

**Interfaces:**
- Consumes: `fetchJob`, `JobDetail` type from Task 6.
- Produces: route `/explore/jobs/<uuid>`; `<JobDetailView jobId={...} />`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/JobDetail.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { JobFacts } from './JobDetail';

const BASE = {
  id: '11111111-1111-4111-8111-111111111111',
  title: 'Platform Engineer',
  company: { id: '22222222-2222-4222-8222-222222222222', canonical_name: 'Datadog', website: null },
  employment_type: 'full_time' as const,
  remote_policy: 'hybrid' as const,
  status: 'open' as const,
  locations: [],
  salary: { provided: false, minimum: null, maximum: null, currency: null, period: null },
  source_published_at: null,
  source_updated_at: null,
  first_seen_at: '2026-08-01T00:00:00+00:00',
  last_seen_at: '2026-08-03T00:00:00+00:00',
  application_deadline: null,
  description_text: 'We build things.',
  description_html: null,
  sources: [],
};

describe('JobFacts', () => {
  it('says a missing salary was not provided rather than hiding the row', () => {
    render(<JobFacts job={BASE} />);
    expect(screen.getByText(/not provided by source/i)).toBeVisible();
  });

  it('never labels first_seen_at as a posting date', () => {
    render(<JobFacts job={BASE} />);
    // A10: first_seen_at is ours, not the source's.
    expect(screen.queryByText(/^posted$/i)).toBeNull();
    expect(screen.getByText(/first seen/i)).toBeVisible();
  });

  it('names the M3 fields it cannot compute yet', () => {
    render(<JobFacts job={BASE} />);
    expect(screen.getByText(/match score/i)).toBeVisible();
    expect(screen.getByText(/not yet computed/i)).toBeVisible();
  });

  it('shows no number anywhere near the match score', () => {
    // I4: a bare score is a bug, and an invented one is worse.
    const { container } = render(<JobFacts job={BASE} />);
    const deferred = container.querySelector('[data-testid="deferred-facts"]');
    expect(deferred?.textContent ?? '').not.toMatch(/\d+%/);
  });
});
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd apps/web && npx vitest run src/components/JobDetail.test.tsx`
Expected: FAIL — cannot resolve `./JobDetail`.

- [ ] **Step 3: Write the component**

Create `apps/web/src/components/JobDetail.tsx`:

```tsx
'use client';

/**
 * One job, in full.
 *
 * Two kinds of absence, and they are different claims:
 *   "not provided by source"  — the posting did not say (A10)
 *   "not yet computed"        — M3 has not been built (I4)
 * Collapsing them would be the lie this file exists to avoid.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { ConfidenceLadder } from './ConfidenceLadder';
import { fetchJob } from '@/lib/api';
import type { JobDetail } from '@/lib/schemas';

const DEFERRED_FACTS = [
  'Match score',
  'Eligibility',
  'Match breakdown',
  'Missing requirements',
  'Project evidence',
  'Recommended resume',
  'Similar jobs',
] as const;

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';
const VALUE = 'mt-1 text-[14px] text-paper';
const ABSENT = 'mt-1 text-[13px] italic text-paper-dim';

function formatDate(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

export function JobFacts({ job }: { job: JobDetail }) {
  return (
    <div className="space-y-8">
      <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className={TERM}>Employment type</dt>
          <dd className={VALUE}>{job.employment_type.replace('_', ' ')}</dd>
        </div>
        <div>
          <dt className={TERM}>Remote policy</dt>
          <dd className={VALUE}>{job.remote_policy.replace('_', ' ')}</dd>
        </div>
        <div>
          <dt className={TERM}>Salary</dt>
          {job.salary.provided ? (
            <dd className={VALUE}>
              {job.salary.minimum ?? '?'}–{job.salary.maximum ?? '?'} {job.salary.currency ?? ''}
            </dd>
          ) : (
            <dd className={ABSENT}>not provided by source</dd>
          )}
        </div>
        <div>
          <dt className={TERM}>Application deadline</dt>
          {job.application_deadline !== null ? (
            <dd className={VALUE}>{formatDate(job.application_deadline)}</dd>
          ) : (
            <dd className={ABSENT}>not provided by source</dd>
          )}
        </div>
        <div>
          <dt className={TERM}>First seen by Nightshift</dt>
          <dd className={VALUE}>{formatDate(job.first_seen_at)}</dd>
        </div>
        <div>
          <dt className={TERM}>Last verified</dt>
          <dd className={VALUE}>{formatDate(job.last_seen_at)}</dd>
        </div>
      </dl>

      {job.locations.length > 0 && (
        <section>
          <h2 className={TERM}>Locations</h2>
          <ul className="mt-3 space-y-2">
            {job.locations.map((location) => (
              <li key={location.id} className="flex items-baseline gap-3">
                <span className="text-[14px] text-paper">{location.raw_text}</span>
                <ConfidenceLadder confidence={location.location_confidence} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section data-testid="deferred-facts">
        <h2 className={TERM}>Not yet computed</h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          These arrive with the matching engine at milestone 3. They are listed rather than
          hidden, because a score with no breakdown behind it is a bug, and an invented one is
          worse.
        </p>
        <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1">
          {DEFERRED_FACTS.map((fact) => (
            <li key={fact} className="text-[13px] text-paper-dim">
              {fact}
            </li>
          ))}
        </ul>
      </section>

      {job.sources.length > 0 && (
        <section>
          <h2 className={TERM}>Sources</h2>
          <ul className="mt-3 space-y-2">
            {job.sources.map((source) => (
              <li key={`${source.source_name}-${source.source_job_id}`}>
                {source.canonical_url !== null ? (
                  <a
                    className="text-[14px] text-signal-400 underline underline-offset-2"
                    href={source.canonical_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {source.source_name}
                  </a>
                ) : (
                  <span className="text-[14px] text-paper">{source.source_name}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {job.description_text !== null && (
        <section>
          <h2 className={TERM}>Description</h2>
          <p className="mt-3 max-w-3xl whitespace-pre-line text-[14px] leading-relaxed text-paper-dim">
            {job.description_text}
          </p>
        </section>
      )}
    </div>
  );
}

export function JobDetailView({ jobId }: { jobId: string }) {
  const { data, error, isPending } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => fetchJob(jobId),
  });

  if (isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading role…
      </p>
    );
  }

  if (error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load this role
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">{data.title}</h1>
        <Link
          className="mt-1 inline-block text-[14px] text-signal-400 underline underline-offset-2"
          href={`/explore/companies/${data.company.id}`}
        >
          {data.company.canonical_name}
        </Link>
      </header>
      <JobFacts job={data} />
    </div>
  );
}
```

If `ConfidenceLadder`'s export name or prop differs, read
`apps/web/src/components/ConfidenceLadder.tsx` and match it rather than
changing that file.

- [ ] **Step 4: Add the route**

Create `apps/web/src/app/explore/jobs/[id]/page.tsx`:

```tsx
import { JobDetailView } from '@/components/JobDetail';

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobDetailView jobId={id} />;
}
```

- [ ] **Step 5: Link the row title**

In `apps/web/src/components/JobRow.tsx`, wrap the rendered title in:

```tsx
<Link
  className="text-signal-400 underline-offset-2 hover:underline"
  href={`/explore/jobs/${job.id}`}
>
  {job.title}
</Link>
```

and add `import Link from 'next/link';` at the top.

- [ ] **Step 6: Run the tests, typecheck and build**

Run: `cd apps/web && npx vitest run && npx tsc --noEmit && npx next build`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/app/explore/jobs apps/web/src/components/JobDetail.tsx \
        apps/web/src/components/JobDetail.test.tsx apps/web/src/components/JobRow.tsx
git commit -m "feat(web): add the job detail page"
```

---

### Task 9: Web — the company detail page

**Files:**
- Create: `apps/web/src/app/explore/companies/[id]/page.tsx`
- Create: `apps/web/src/components/CompanyDetail.tsx`
- Create: `apps/web/src/components/CompanyDetail.test.tsx`

**Interfaces:**
- Consumes: `fetchCompany`, `fetchJobs`, `CompanyDetail` type from Task 6.
- Produces: route `/explore/companies/<uuid>`; `<CompanyDetailView companyId={...} />`, `<CompanyCounts counts={...} />`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/CompanyDetail.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CompanyCounts } from './CompanyDetail';

describe('CompanyCounts', () => {
  it('shows every closure state including the empty ones', () => {
    render(
      <CompanyCounts counts={{ open: 4, possibly_stale: 0, unverified: 0, closed: 2 }} />,
    );
    // A state with no jobs reads as an explicit 0 rather than vanishing: a
    // missing count and a real zero are different claims.
    expect(screen.getByText(/possibly stale/i)).toBeVisible();
    expect(screen.getByTestId('count-possibly_stale')).toHaveTextContent('0');
    expect(screen.getByTestId('count-closed')).toHaveTextContent('2');
  });

  it('does not hide closed roles', () => {
    render(
      <CompanyCounts counts={{ open: 0, possibly_stale: 0, unverified: 0, closed: 7 }} />,
    );
    expect(screen.getByTestId('count-closed')).toHaveTextContent('7');
  });
});
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd apps/web && npx vitest run src/components/CompanyDetail.test.tsx`
Expected: FAIL — cannot resolve `./CompanyDetail`.

- [ ] **Step 3: Write the component**

Create `apps/web/src/components/CompanyDetail.tsx`:

```tsx
'use client';

/**
 * One employer: who they are, and every role we have ever seen from them.
 *
 * Counts are by closure state rather than a single total. A company page that
 * showed only open roles would make the closure machine invisible, which is
 * the one thing it must not be.
 */

import { useQuery } from '@tanstack/react-query';

import { JobRow } from './JobRow';
import { fetchCompany, fetchJobs } from '@/lib/api';
import type { CompanyDetail } from '@/lib/schemas';

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';

const STATES = ['open', 'possibly_stale', 'unverified', 'closed'] as const;

export function CompanyCounts({ counts }: { counts: CompanyDetail['job_status_counts'] }) {
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {STATES.map((state) => (
        <div key={state}>
          <dt className={TERM}>{state.replace('_', ' ')}</dt>
          <dd
            data-testid={`count-${state}`}
            className="mt-1 text-[20px] font-medium text-paper tnum"
          >
            {counts[state]}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function CompanyDetailView({ companyId }: { companyId: string }) {
  const company = useQuery({
    queryKey: ['company', companyId],
    queryFn: () => fetchCompany(companyId),
  });

  const jobs = useQuery({
    queryKey: ['jobs', { company: companyId }],
    queryFn: () => fetchJobs({ company: company.data?.canonical_name, limit: 50 }),
    enabled: company.data !== undefined,
  });

  if (company.isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading employer…
      </p>
    );
  }

  if (company.error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load this employer
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{company.error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">
          {company.data.canonical_name}
        </h1>
        {company.data.website !== null && (
          <a
            className="mt-1 inline-block text-[14px] text-signal-400 underline underline-offset-2"
            href={company.data.website}
            target="_blank"
            rel="noreferrer"
          >
            {company.data.website}
          </a>
        )}
      </header>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <CompanyCounts counts={company.data.job_status_counts} />
      </section>

      <section className="border border-ink-700 bg-ink-900/40">
        <div className="border-b border-ink-700 px-5 py-2">
          <h2 className={TERM}>Roles</h2>
        </div>
        {jobs.data?.items.map((job) => <JobRow key={job.id} job={job} />) ?? (
          <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
            Loading roles…
          </p>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Add the route**

Create `apps/web/src/app/explore/companies/[id]/page.tsx`:

```tsx
import { CompanyDetailView } from '@/components/CompanyDetail';

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CompanyDetailView companyId={id} />;
}
```

- [ ] **Step 5: Run tests, typecheck, build**

Run: `cd apps/web && npx vitest run && npx tsc --noEmit && npx next build`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/app/explore/companies apps/web/src/components/CompanyDetail.tsx \
        apps/web/src/components/CompanyDetail.test.tsx
git commit -m "feat(web): add the company detail page"
```

---

### Task 10: Seeded browser tests, then close the slice

**Files:**
- Create: `apps/web/e2e-seeded/search-and-detail.spec.ts`
- Modify: `docs/PROGRESS.md`
- Create: `docs/reviews/milestone-2a-review.md`

**Interfaces:**
- Consumes: everything above, running against the seeded stack.
- Produces: the evidence M2a's criteria are claimed on.

- [ ] **Step 1: Write the browser tests**

Create `apps/web/e2e-seeded/search-and-detail.spec.ts`. Read an existing spec
(`apps/web/e2e-seeded/operate-boards.spec.ts`) first and match its fixture
imports and base-URL convention:

```ts
import { expect, test } from '@playwright/test';

test.describe('search and detail, against the seeded corpus', () => {
  test('a text search narrows the list and survives a reload', async ({ page }) => {
    await page.goto('/explore');
    const before = await page.getByText(/showing \d+ of \d+/).textContent();

    await page.getByLabel(/search/i).fill('engineer');
    await expect(page.getByText(/showing \d+ of \d+/)).not.toHaveText(before ?? '');

    // The URL is the state, so the filter must survive a reload.
    await expect(page).toHaveURL(/[?&]q=engineer/);
    await page.reload();
    await expect(page.getByLabel(/search/i)).toHaveValue('engineer');
  });

  test('the filters it will not fake are named on the page', async ({ page }) => {
    await page.goto('/explore');
    // Visible without expanding anything — same rule as the coverage page.
    await expect(page.getByText(/which borough it is in/i)).toBeVisible();
    await expect(page.getByText(/no score exists yet/i)).toBeVisible();
  });

  test('a job opens, and states what the source did not provide', async ({ page }) => {
    await page.goto('/explore');
    await page.getByRole('link', { name: /engineer/i }).first().click();
    await expect(page).toHaveURL(/\/explore\/jobs\//);
    await expect(page.getByText(/first seen by nightshift/i)).toBeVisible();
    await expect(page.getByText(/not yet computed/i)).toBeVisible();
  });

  test('no job page presents a match score', async ({ page }) => {
    await page.goto('/explore');
    await page.getByRole('link', { name: /engineer/i }).first().click();
    const deferred = page.getByTestId('deferred-facts');
    await expect(deferred).toBeVisible();
    await expect(deferred).not.toHaveText(/\d+\s*%/);
  });

  test('an employer page shows every closure state, including zero', async ({ page }) => {
    await page.goto('/explore');
    await page.getByRole('link', { name: /engineer/i }).first().click();
    await page.getByRole('link', { name: /datadog|alloy|ramp/i }).first().click();
    await expect(page).toHaveURL(/\/explore\/companies\//);
    await expect(page.getByTestId('count-open')).toBeVisible();
    await expect(page.getByTestId('count-closed')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run them against the seeded stack**

Run:
```bash
make up && make migrate && make seed && make test-e2e-seeded
```
Expected: the existing 20 plus these 5 pass. Record the totals.

- [ ] **Step 3: Run the whole gate**

Run: `make check && make acceptance`
Expected: both green. Record the Python and web test counts read from the
output — not computed, not inferred.

- [ ] **Step 4: Write the review**

Create `docs/reviews/milestone-2a-review.md`. Follow the structure of
`docs/reviews/milestone-1d-review.md`, and actively hunt for: filters that
silently return everything, a filter that returns nothing when blank, pagination
that repeats or skips rows, a query that scans, an absence rendered as a zero,
`first_seen_at` labelled as a posting date, any number presented as a score,
and tests that cannot fail.

For each defect found, record whether it was found by a test, by review, or by
running the thing — the four previous milestones each found most defects in code
that reported success, and the count is the point.

- [ ] **Step 5: Update PROGRESS**

In `docs/PROGRESS.md`: set the current milestone to M2, mark M2a complete with
per-criterion evidence, record the measured filter latency from Task 4 Step 3,
the test counts read from Step 3's output, and the commit each task landed in.

State plainly what is **not** real yet: no profile, no resume, no saving, no
tracking, no daily queue.

- [ ] **Step 6: Commit and open the PR**

```bash
git add apps/web/e2e-seeded/search-and-detail.spec.ts docs/
git commit -m "test(search): add seeded browser tests, and close M2a"
git push -u origin m2a-search-and-detail
gh pr create --title "M2a — search, filters and detail pages" --body "$(cat <<'BODY'
M2a of the M2 command center: `docs/architecture/command-center.md` §4.

A person can now find a specific job by text, employer, city, employment type,
remote policy, recency, salary and source, then open that job and its employer.

- Text search is a generated `tsvector` column with a GIN index. No new dependency.
- Five filters the spec asks for are rendered **disabled with their reason**
  rather than omitted. Borough is one of them, and its reason is invariant I1
  rather than scheduling: a posting saying "New York, NY" does not say which
  borough it is in.
- A salary floor reports how many roles it necessarily hid, because most
  postings state no salary at all (A10).
- The <200ms criterion is guarded by a query-plan test rather than a stopwatch.
  On a 31-row table Postgres seq-scans everything, so the test sets
  `enable_seqscan = off` and asserts an index is usable — with a non-vacuity
  case proving the assertion can fail.

Not in this slice: save, apply, tracking, profile, resume, daily queue.
BODY
)"
```

Then check CI at the pushed head, read the job logs rather than inferring from
the badge, and record the run id and the read counts in PROGRESS.

---

## Self-review

**Spec coverage** — `command-center.md` §4 asks for: text search (Task 2/3),
employment type, remote policy, first-seen date, minimum salary, source, city
(Task 2/3), the deferred-filter list rendered with reasons (Tasks 2, 3, 7), the
query-plan guard for the <200ms criterion (Task 4), job detail with the two
kinds of absence (Task 8), and company detail (Tasks 5, 9). All covered.

**Not in this slice, by design** — save and apply controls on the detail page
(M2b owns them, and the design's §5 puts the Apply-never-applies rule there),
notes and application history on the detail panel (M2b), match fields (M3),
boroughs (M4).

**One known ordering constraint** — Task 7's `JobList` reads
`data.deferred_filters`, which Task 3 adds to the response. Running Task 7
before Task 3 yields an empty panel section and two failing tests. The task
order is the dependency order.
