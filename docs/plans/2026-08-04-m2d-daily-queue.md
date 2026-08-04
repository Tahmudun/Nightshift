# M2d — the daily queue: four rows that are true, and four named as absent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One page that answers "what should I do today?" from data the system already holds — and that names the four rows it cannot compute yet, with the reason, instead of faking them.

**Architecture:** A read-only projection. `domain/queue.py` holds four queries and three named thresholds; `GET /queue` returns their rows plus the deferred four plus the thresholds themselves, so the page never hardcodes a number the API also knows. Nothing in this slice writes. There is no dismiss, no snooze, and no new table — the queue suggests, and every row is a link to the application where acting actually happens.

**Tech Stack:** PostgreSQL 16 (two partial indexes, migration `0010`), SQLAlchemy 2.0 async, FastAPI, Pydantic v2, Next.js App Router, TanStack Query, Zod, Playwright.

**Design:** `docs/architecture/command-center.md` §7, including §7.1, §7.2 and §7.3, which were written on 2026-08-04 and settle the three decisions this plan is not free to revisit: assessments fold into Follow up, the thresholds are 7 / 21 / 14 days, and the queue writes nothing.

## Global Constraints

- **I4 — never present a score without a breakdown.** The queue shows no number that ranks anything. Every row carries a plain sentence saying why it is there, and that sentence is derived from the same data the query filtered on. There is no priority ordering, no urgency score, and no "top pick" — those are the deferred four.
- **I7 — never let a mock become the product.** The four deferred rows are named on the page with their reason and are **not** rendered as empty sections. An empty section says "you have nothing"; a named absence says "this does not exist yet". They are different claims and only one of them is true.
- **I5 — never take an irreversible action for the user.** Nothing on this page mutates. §7.3.
- **I3 — never silently close a listing.** The queue *reads* `jobs.status`; it never writes it, and a source outage that leaves a job `possibly_stale` must not put it in "Closed while saved".
- **I6** — "the code exists" is not evidence. Task 7 records measured output per criterion in `docs/PROGRESS.md`.
- **A3** — no auth until M5, and nothing may assume one user. Every query in this slice filters on `user_id` from `api/deps.py`, including the ones that reach `application_events` through a join.
- **A9 — $0 and no API keys.** This slice adds no dependency at all. If a task seems to need one, that is a signal the task is wrong.
- **Python** — full type annotations, mypy strict clean, ruff clean. Pydantic models at every boundary. Domain logic never in a route handler (CLAUDE.md §3): `api/routes/queue.py` calls one function and shapes the response.
- **TypeScript** — strict, no `any`. Every API response parsed through Zod before it reaches a component. Named exports. Colocated `*.test.tsx`.
- **Colour** — `paper*` tokens are text, `ink*` tokens are surfaces and never carry text. A new colour token requires a new assertion in `colour-contrast.test.ts`. This slice should need none; if a row needs an accent, it reuses `signal-400`, which is already asserted.
- **Migrations** — reversible and tested both directions. `alembic check` must report no drift once the model and the migration are both in. **`op.create_index` on a partial index needs `postgresql_where`, and autogenerate has emitted `nightshift.db.types.UTCDateTime` with no import four times in this project** — read the note at the head of `0002` before writing `0010`.
- **Time** — `TIMESTAMPTZ` in the database, UTC always, converted at the edge only. The thresholds are `timedelta`s applied to a `now` that is **passed in**, never read inside a query function. A function that calls `utcnow()` internally cannot be tested at a boundary.
- **TODOs** — must carry a milestone: `TODO(M3): ...`. A bare `TODO` fails lint.
- **Commits** — conventional and scoped, one per task. Run `make check` before each.
- **Before pushing, run three commands, not two.** `make check`, `make acceptance`, **and `make test-e2e`**. The degraded suite needs the API *down*, which is the opposite stack state from acceptance, so neither aggregate target can run it. M2a shipped a red CI run by forgetting this.

---

## What this slice deliberately does not build

Name these in the UI rather than hiding them, and repeat them in PROGRESS:

| Not built | Why | Where it lands |
|---|---|---|
| Best new internships | Needs a match score. A "best" with no ranking behind it is I4's exact prohibition | M3 |
| High-match roles closing soon | Same. "Closing soon" is also a deadline the sources mostly do not publish (A10) | M3 |
| Resume mismatch warnings | Needs requirement extraction and the evidence graph | M3 |
| The single recommended action | Ranking across four heterogeneous row types. It is the most valuable row on the page and the least honest to fake | M3 |
| Dismiss / snooze a row | New state, a new table, and a decision about whether a dismissed row returns tomorrow — none of it needed to make four rows useful (§7.3) | Unscheduled |
| `assessment_due_at` | §7.1. `next_action_at` already carries the date, and a column that is NULL for every user is shape with no use | Only if a real assessment deadline must differ from the next action |
| Email or push reminders | The queue is a page you visit. A notification is an outbound action and M2 has no delivery path | Unscheduled |
| Ordering rows by importance across sections | That is the recommended-action row wearing a different hat | M3 |

---

### Task 1: The queue rules — four queries, three thresholds, one shared subquery

The whole of this slice's logic. Pure query construction plus an async function per row, tested against a real database at the boundaries. No HTTP, no routes, no schemas.

**Files:**
- Create: `services/api/nightshift/domain/queue.py`
- Create: `services/api/tests/test_queue.py`

**Interfaces:**
- Consumes: `nightshift.db.models.{Application, ApplicationEvent, Job, Company}`, `nightshift.db.base.{ApplicationStage, ApplicationEventType, EventActor, JobStatus}`.
- Produces:
  - `FOLLOW_UP_SILENT_DAYS: int = 7`, `STALE_SAVED_DAYS: int = 21`, `INTERVIEW_HORIZON_DAYS: int = 14`, `ROW_CAP: int = 20`
  - `AWAITING_STAGES: tuple[ApplicationStage, ...]`, `TERMINAL_STAGES: tuple[ApplicationStage, ...]`
  - `QueueSectionKey` (StrEnum: `follow_up`, `interviews_approaching`, `stale_saved`, `closed_while_saved`)
  - `QueueRow` frozen dataclass: `application_id: UUID`, `job_id: UUID`, `job_title: str`, `company_name: str`, `current_stage: ApplicationStage`, `at: datetime | None`, `because: str`
  - `QueueSection` frozen dataclass: `key: QueueSectionKey`, `rows: tuple[QueueRow, ...]`, `total: int`
  - `DailyQueue` frozen dataclass: `sections: tuple[QueueSection, ...]`, `total_rows: int`
  - `async def build_queue(session: AsyncSession, *, user_id: UUID, now: datetime) -> DailyQueue`
  - `def queue_selects(*, user_id: UUID, now: datetime) -> dict[QueueSectionKey, Select[Any]]` — the four row selects, exposed so Task 2 can run `EXPLAIN` over exactly what production runs

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_queue.py`. The helpers mirror `tests/test_applications.py` so the two files read the same; copy them rather than importing, which is what every other test file in this repo does.

```python
"""The daily queue: four rows, and the boundaries that decide who is in them.

Every threshold here is tested at three points — one day inside, exactly on,
and one day outside. An off-by-one in this file shows a person the wrong jobs
and looks completely plausible while doing it, which is why the boundary cases
are the point of the file rather than an extra.

`now` is passed in everywhere. A query function that read the clock itself
could not be tested at a boundary at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EventActor,
    JobStatus,
    TransitionClass,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job, User
from nightshift.domain.queue import (
    FOLLOW_UP_SILENT_DAYS,
    INTERVIEW_HORIZON_DAYS,
    ROW_CAP,
    STALE_SAVED_DAYS,
    QueueSectionKey,
    build_queue,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test")
    session.add(user)
    await session.flush()
    return user


async def _a_job(
    session: AsyncSession,
    *,
    title: str = "Software Engineer",
    status: JobStatus = JobStatus.OPEN,
) -> Job:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    session.add(company)
    await session.flush()
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.casefold(),
        status=status,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(job)
    await session.flush()
    return job


async def _an_application(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    stage: ApplicationStage = ApplicationStage.SAVED,
    next_action_at: datetime | None = None,
    archived_at: datetime | None = None,
    saved_at: datetime = NOW,
) -> Application:
    """An application with its one `saved` event, as `save_job` would leave it."""
    application = Application(
        user_id=user.id,
        job_id=job.id,
        current_stage=stage,
        next_action_at=next_action_at,
        archived_at=archived_at,
    )
    session.add(application)
    await session.flush()
    session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.SAVED,
            actor=EventActor.USER,
            occurred_at=saved_at,
            to_stage=ApplicationStage.SAVED,
            transition_class=TransitionClass.ADVANCE,
        )
    )
    await session.flush()
    return application


async def _an_event(
    session: AsyncSession,
    *,
    application: Application,
    event_type: ApplicationEventType,
    actor: EventActor,
    occurred_at: datetime,
) -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application.id,
        event_type=event_type,
        actor=actor,
        occurred_at=occurred_at,
    )
    session.add(event)
    await session.flush()
    return event


def _section(queue: object, key: QueueSectionKey) -> object:
    sections = {section.key: section for section in queue.sections}  # type: ignore[attr-defined]
    return sections[key]


def _ids(queue: object, key: QueueSectionKey) -> set[uuid.UUID]:
    return {row.application_id for row in _section(queue, key).rows}  # type: ignore[attr-defined]


# --- Follow up -------------------------------------------------------------


async def test_a_due_next_action_is_a_follow_up(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW - timedelta(hours=1),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_future_next_action_is_not_a_follow_up_yet(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW + timedelta(days=1),
        saved_at=NOW,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.FOLLOW_UP)


@pytest.mark.parametrize(
    ("days_silent", "expected"),
    [(FOLLOW_UP_SILENT_DAYS - 1, False), (FOLLOW_UP_SILENT_DAYS, True), (FOLLOW_UP_SILENT_DAYS + 1, True)],
)
async def test_the_follow_up_boundary(
    db_session: AsyncSession, days_silent: int, expected: bool
) -> None:
    """Exactly seven days of silence counts. Six does not."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=days_silent),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)) is expected


async def test_an_assessment_with_a_date_is_a_follow_up(db_session: AsyncSession) -> None:
    """§7.1: assessments fold in here rather than getting their own row."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.ASSESSMENT,
        next_action_at=NOW - timedelta(hours=2),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_rejected_application_is_never_a_follow_up(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.REJECTED,
        next_action_at=NOW - timedelta(days=30),
        saved_at=NOW - timedelta(days=90),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_system_event_does_not_count_as_activity(db_session: AsyncSession) -> None:
    """The load-bearing filter on the whole page (§7.2).

    A `listing_closed` written by the poller is not the user touching the job.
    If it counted, a closing listing would silently make its application look
    freshly handled and drop it out of the queue that exists to surface it.
    """
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=30),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.LISTING_CLOSED,
        actor=EventActor.SYSTEM,
        occurred_at=NOW,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_user_note_does_count_as_activity(db_session: AsyncSession) -> None:
    """The other half of the same filter — without this, the test above would
    pass on a function that ignored events entirely."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=30),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.NOTE_ADDED,
        actor=EventActor.USER,
        occurred_at=NOW - timedelta(days=1),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.FOLLOW_UP)


# --- Interviews approaching ------------------------------------------------


@pytest.mark.parametrize(
    ("days_ahead", "expected"),
    [(-1, False), (1, True), (INTERVIEW_HORIZON_DAYS, True), (INTERVIEW_HORIZON_DAYS + 1, False)],
)
async def test_the_interview_horizon(
    db_session: AsyncSession, days_ahead: int, expected: bool
) -> None:
    """Yesterday's interview is history, not a queue row."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.INTERVIEW,
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=NOW + timedelta(days=days_ahead),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (application.id in _ids(queue, QueueSectionKey.INTERVIEWS_APPROACHING)) is expected


async def test_two_interviews_are_two_rows_soonest_first(db_session: AsyncSession) -> None:
    """One application, two scheduled times. Both are real appointments."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.INTERVIEW,
    )
    for days in (5, 2):
        await _an_event(
            db_session,
            application=application,
            event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
            actor=EventActor.USER,
            occurred_at=NOW + timedelta(days=days),
        )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    rows = _section(queue, QueueSectionKey.INTERVIEWS_APPROACHING).rows  # type: ignore[attr-defined]
    assert len(rows) == 2
    assert rows[0].at < rows[1].at


# --- Stale saved -----------------------------------------------------------


@pytest.mark.parametrize(
    ("days_old", "expected"),
    [(STALE_SAVED_DAYS - 1, False), (STALE_SAVED_DAYS, True), (STALE_SAVED_DAYS + 1, True)],
)
async def test_the_stale_saved_boundary(
    db_session: AsyncSession, days_old: int, expected: bool
) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.SAVED,
        saved_at=NOW - timedelta(days=days_old),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (application.id in _ids(queue, QueueSectionKey.STALE_SAVED)) is expected


async def test_an_applied_job_is_not_stale_saved(db_session: AsyncSession) -> None:
    """It moved on. Follow up is the row that covers it now."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=90),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.STALE_SAVED)


# --- Closed while saved ----------------------------------------------------


async def test_a_closed_listing_surfaces(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


async def test_a_possibly_stale_listing_does_not_surface(db_session: AsyncSession) -> None:
    """I3. A source that went quiet is not a job that closed, and the queue
    must not tell the user it is."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.POSSIBLY_STALE),
        stage=ApplicationStage.APPLIED,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


async def test_a_reopened_listing_leaves_the_queue(db_session: AsyncSession) -> None:
    """§7.2: membership is read from the job's *current* status, not from the
    `listing_closed` event. Reading the event would pin a reopened role here
    forever."""
    user = await _a_user(db_session)
    job = await _a_job(db_session, status=JobStatus.CLOSED)
    application = await _an_application(
        db_session, user=user, job=job, stage=ApplicationStage.APPLIED
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.LISTING_CLOSED,
        actor=EventActor.SYSTEM,
        occurred_at=NOW - timedelta(days=2),
    )
    job.status = JobStatus.OPEN
    await db_session.flush()

    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


async def test_a_withdrawn_application_ignores_its_closed_listing(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.WITHDRAWN,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


# --- Rules that hold across every section ----------------------------------


async def test_an_archived_application_is_in_no_section(db_session: AsyncSession) -> None:
    """§7.2, and the bug M2b already shipped once from the other direction."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW - timedelta(days=5),
        saved_at=NOW - timedelta(days=90),
        archived_at=NOW - timedelta(days=1),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=NOW + timedelta(days=2),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    for key in QueueSectionKey:
        assert application.id not in _ids(queue, key), key


async def test_another_users_application_is_in_no_section(db_session: AsyncSession) -> None:
    """A3. Every query filters on user_id, including the ones reaching events
    through a join."""
    mine = await _a_user(db_session)
    theirs = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=theirs,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW - timedelta(days=5),
        saved_at=NOW - timedelta(days=90),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=NOW + timedelta(days=2),
    )
    queue = await build_queue(db_session, user_id=mine.id, now=NOW)
    assert queue.total_rows == 0


async def test_every_row_says_why_it_is_there(db_session: AsyncSession) -> None:
    """I4's spirit: no bare signal. A row with an empty reason is a bug."""
    user = await _a_user(db_session)
    await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=90),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert queue.total_rows > 0
    for section in queue.sections:
        for row in section.rows:
            assert row.because.strip()
            assert row.job_title.strip()
            assert row.company_name.strip()


async def test_a_section_is_capped_and_says_how_many_it_capped(
    db_session: AsyncSession,
) -> None:
    """Unbounded render work is CLAUDE.md §8's anti-pattern, and it applies to
    a list as much as to a map. `total` is the honest count behind the cap."""
    user = await _a_user(db_session)
    for index in range(ROW_CAP + 3):
        await _an_application(
            db_session,
            user=user,
            job=await _a_job(db_session, title=f"Engineer {index}"),
            stage=ApplicationStage.SAVED,
            saved_at=NOW - timedelta(days=STALE_SAVED_DAYS + 1),
        )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    section = _section(queue, QueueSectionKey.STALE_SAVED)
    assert len(section.rows) == ROW_CAP  # type: ignore[attr-defined]
    assert section.total == ROW_CAP + 3  # type: ignore[attr-defined]


async def test_an_empty_queue_is_four_empty_sections_not_an_error(
    db_session: AsyncSession,
) -> None:
    """A user with nothing to do gets a well-formed answer. The page needs the
    section list to render "nothing today" honestly."""
    user = await _a_user(db_session)
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert len(queue.sections) == len(QueueSectionKey)
    assert queue.total_rows == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd services/api && uv run pytest tests/test_queue.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'nightshift.domain.queue'`.

- [ ] **Step 3: Write `domain/queue.py`**

```python
"""The daily queue: four questions this system can answer honestly today.

Read `docs/architecture/command-center.md` §7 before changing anything here.
§7.1 records why assessments do not have their own row, §7.2 records the three
rules that decide whether the page tells the truth, and §7.3 records that this
module has no write path and is not to grow one.

Everything here is a read. `build_queue` is called once per page load and runs
four independent queries rather than one clever join — they answer four
different questions, they are separately indexable, and a join producing all
four would be the kind of query nobody can change safely later.

`now` is a parameter, never `utcnow()` read inside. Every threshold in this
file is a boundary somebody will get wrong eventually, and a function that
reads its own clock cannot be tested at one.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EventActor,
    JobStatus,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job

#: Decided by the human on 2026-08-04 (`command-center.md` §7). A week is when
#: silence after applying starts to mean something; three weeks of a saved job
#: untouched is genuinely stale; two weeks is far enough ahead to prepare for
#: an interview and near enough that it is still this month's problem.
FOLLOW_UP_SILENT_DAYS = 7
STALE_SAVED_DAYS = 21
INTERVIEW_HORIZON_DAYS = 14

#: Rows per section. The count before the cap travels with it, so the page can
#: say "and 6 more" rather than quietly truncating.
ROW_CAP = 20

#: Applied and now waiting on somebody else. Silence in these stages is the
#: thing worth surfacing. `assessment` is here because §7.1 folds assessments
#: into follow-up rather than giving them a row of their own.
AWAITING_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.APPLIED,
    ApplicationStage.ASSESSMENT,
    ApplicationStage.INTERVIEW,
)

#: Over, one way or another. Nothing in these stages belongs in a queue of
#: things to do today — including `offer`, which is a decision rather than a
#: chase, and which the pipeline already shows prominently.
TERMINAL_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.REJECTED,
    ApplicationStage.WITHDRAWN,
    ApplicationStage.CLOSED,
)


class QueueSectionKey(enum.StrEnum):
    """The four sections. Deliberately not a database enum — this is a shape of
    the API, not a stored value, and nothing persists it."""

    FOLLOW_UP = "follow_up"
    INTERVIEWS_APPROACHING = "interviews_approaching"
    STALE_SAVED = "stale_saved"
    CLOSED_WHILE_SAVED = "closed_while_saved"


@dataclass(frozen=True, slots=True)
class QueueRow:
    """One thing to look at, and the sentence saying why.

    `at` is the date the row is *about* — the follow-up date, the interview
    time, the day it went quiet. It is read from a column, never invented, and
    it is None when the section has no meaningful date (I1's habit applied to
    time rather than to place).
    """

    application_id: UUID
    job_id: UUID
    job_title: str
    company_name: str
    current_stage: ApplicationStage
    at: datetime | None
    because: str


@dataclass(frozen=True, slots=True)
class QueueSection:
    key: QueueSectionKey
    rows: tuple[QueueRow, ...]
    #: Before the cap. `len(rows) < total` is how the page knows to say so.
    total: int


@dataclass(frozen=True, slots=True)
class DailyQueue:
    sections: tuple[QueueSection, ...]
    total_rows: int


def _last_user_activity() -> Any:
    """The most recent event *the user caused*, per application.

    §7.2, and the load-bearing filter on this page. `application_events` holds
    system events too — `record_listing_closed` writes one — and a system event
    is not somebody touching their application. If it counted here, a listing
    going closed would make its application look freshly handled and drop it
    out of the very queue that exists to surface it. Mutation-checked by
    `test_a_system_event_does_not_count_as_activity`.
    """
    return (
        select(
            ApplicationEvent.application_id.label("application_id"),
            func.max(ApplicationEvent.occurred_at).label("last_at"),
        )
        .where(ApplicationEvent.actor == EventActor.USER)
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )


def _live(user_id: UUID) -> list[Any]:
    """Filters every section shares: this user's, not archived, not over.

    Archived exclusion is §7.2's second rule, and M2b shipped the same bug from
    the other direction — an archived application rendered as unsaved and
    saving it changed nothing.
    """
    return [
        Application.user_id == user_id,
        Application.archived_at.is_(None),
        Application.current_stage.not_in(TERMINAL_STAGES),
    ]


def _row_columns() -> list[Any]:
    """The columns every section selects, in one place so they cannot drift."""
    return [
        Application.id,
        Application.job_id,
        Job.title,
        Company.canonical_name,
        Application.current_stage,
    ]


def _joined(stmt: Select[Any]) -> Select[Any]:
    return stmt.join(Job, Job.id == Application.job_id).join(Company, Company.id == Job.company_id)


def _follow_up_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Due by date, or silent past the threshold.

    Two branches, one row per application — an application matching both is
    still one thing to do. `coalesce` falls back to the application's own
    creation time so an application with no user event is surfaced rather than
    silently skipped; `save_job` always writes one today, and being wrong in
    the direction of showing too much is the right way to be wrong here.
    """
    activity = _last_user_activity()
    silent_since = now - timedelta(days=FOLLOW_UP_SILENT_DAYS)
    last_at = func.coalesce(activity.c.last_at, Application.created_at)
    return (
        _joined(select(*_row_columns(), Application.next_action_at, last_at.label("last_at")))
        .outerjoin(activity, activity.c.application_id == Application.id)
        .where(
            *_live(user_id),
            or_(
                and_(
                    Application.next_action_at.is_not(None),
                    Application.next_action_at <= now,
                ),
                and_(
                    Application.current_stage.in_(AWAITING_STAGES),
                    last_at <= silent_since,
                ),
            ),
        )
        # Most overdue first: a date we were given beats one we inferred.
        .order_by(func.coalesce(Application.next_action_at, last_at), Application.id)
    )


def _interviews_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Scheduled times inside the horizon. One row per interview, not per
    application — two interviews are two appointments to prepare for."""
    horizon = now + timedelta(days=INTERVIEW_HORIZON_DAYS)
    return (
        _joined(select(*_row_columns(), ApplicationEvent.occurred_at))
        .join(ApplicationEvent, ApplicationEvent.application_id == Application.id)
        .where(
            *_live(user_id),
            ApplicationEvent.event_type == ApplicationEventType.INTERVIEW_SCHEDULED,
            ApplicationEvent.occurred_at > now,
            ApplicationEvent.occurred_at <= horizon,
        )
        .order_by(ApplicationEvent.occurred_at, Application.id)
    )


def _stale_saved_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Still at `saved`, untouched past the threshold."""
    activity = _last_user_activity()
    stale_since = now - timedelta(days=STALE_SAVED_DAYS)
    last_at = func.coalesce(activity.c.last_at, Application.created_at)
    return (
        _joined(select(*_row_columns(), last_at.label("last_at")))
        .outerjoin(activity, activity.c.application_id == Application.id)
        .where(
            *_live(user_id),
            Application.current_stage == ApplicationStage.SAVED,
            last_at <= stale_since,
        )
        # Stalest first.
        .order_by(last_at, Application.id)
    )


def _closed_while_saved_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """The listing is closed *right now*.

    §7.2's third rule: membership comes from `jobs.status`, not from the
    `listing_closed` event, so a role that closed and reopened leaves this
    section instead of sitting in it permanently. `now` is unused and that is
    deliberate — the signature matches its three siblings so `queue_selects`
    can hold them in one dict.
    """
    del now
    return (
        _joined(select(*_row_columns(), Job.last_seen_at))
        .where(*_live(user_id), Job.status == JobStatus.CLOSED)
        .order_by(Job.last_seen_at.desc(), Application.id)
    )


def queue_selects(*, user_id: UUID, now: datetime) -> dict[QueueSectionKey, Select[Any]]:
    """Exactly what `build_queue` runs, exposed for the query-plan test.

    Task 2 asserts each of these is servable by an index. It matters that it
    reads the real statements rather than a copy that can drift out of step.
    """
    return {
        QueueSectionKey.FOLLOW_UP: _follow_up_select(user_id=user_id, now=now),
        QueueSectionKey.INTERVIEWS_APPROACHING: _interviews_select(user_id=user_id, now=now),
        QueueSectionKey.STALE_SAVED: _stale_saved_select(user_id=user_id, now=now),
        QueueSectionKey.CLOSED_WHILE_SAVED: _closed_while_saved_select(user_id=user_id, now=now),
    }


def _days(a: datetime, b: datetime) -> int:
    return max((a - b).days, 0)


def _because(key: QueueSectionKey, *, row: Any, now: datetime) -> str:
    """One plain sentence per row, derived from the same data the query filtered
    on. Never a score and never a ranking — those are M3's, and I4 forbids
    showing one without a breakdown behind it."""
    if key is QueueSectionKey.FOLLOW_UP:
        if row.next_action_at is not None and row.next_action_at <= now:
            return f"you set a next action for {row.next_action_at:%-d %b}"
        return f"no activity from you in {_days(now, row.last_at)} days"
    if key is QueueSectionKey.INTERVIEWS_APPROACHING:
        return f"interview scheduled for {row.occurred_at:%-d %b}"
    if key is QueueSectionKey.STALE_SAVED:
        return f"saved {_days(now, row.last_at)} days ago and untouched since"
    return "the source stopped listing this role"


def _at(key: QueueSectionKey, row: Any) -> datetime | None:
    if key is QueueSectionKey.FOLLOW_UP:
        return row.next_action_at or row.last_at
    if key is QueueSectionKey.INTERVIEWS_APPROACHING:
        return row.occurred_at
    if key is QueueSectionKey.STALE_SAVED:
        return row.last_at
    return row.last_seen_at


async def _section(
    session: AsyncSession, *, key: QueueSectionKey, stmt: Select[Any], now: datetime
) -> QueueSection:
    """Count first, then take the capped page.

    Two queries rather than a window function, because the count must be the
    honest total and `len(rows)` after a LIMIT is not it.
    """
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    result = (await session.execute(stmt.limit(ROW_CAP))).all()
    rows = tuple(
        QueueRow(
            application_id=row.id,
            job_id=row.job_id,
            job_title=row.title,
            company_name=row.canonical_name,
            current_stage=row.current_stage,
            at=_at(key, row),
            because=_because(key, row=row, now=now),
        )
        for row in result
    )
    return QueueSection(key=key, rows=rows, total=total)


async def build_queue(session: AsyncSession, *, user_id: UUID, now: datetime) -> DailyQueue:
    """Every section, in the order the page renders them.

    Sections are independent, so a role can legitimately appear in two of them
    — a closed listing you also owe a follow-up on is two different facts about
    the same job, and collapsing them would hide one.
    """
    sections = tuple(
        [
            await _section(session, key=key, stmt=stmt, now=now)
            for key, stmt in queue_selects(user_id=user_id, now=now).items()
        ]
    )
    return DailyQueue(sections=sections, total_rows=sum(section.total for section in sections))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd services/api && uv run pytest tests/test_queue.py -q
```

Expected: all pass. If `test_the_follow_up_boundary[7-True]` fails, the comparison is `<` where it must be `<=` — that is the off-by-one this parametrize exists to catch, and it is the single most likely defect in this task.

- [ ] **Step 5: Mutation-check the two load-bearing filters**

This is not optional and it is not a formality. A guard that has never been shown to fail is not yet evidence (`command-center.md` §8).

1. In `_last_user_activity`, delete the `.where(ApplicationEvent.actor == EventActor.USER)` line. Run `tests/test_queue.py`. **Expected: `test_a_system_event_does_not_count_as_activity` fails.** Restore it.
2. In `_live`, delete `Application.archived_at.is_(None)`. **Expected: `test_an_archived_application_is_in_no_section` fails.** Restore it.
3. In `_live`, delete `Application.user_id == user_id`. **Expected: `test_another_users_application_is_in_no_section` fails.** Restore it.

If any mutation leaves the suite green, the test is wrong rather than the mutation being harmless — fix the test before continuing, and record it in the review.

- [ ] **Step 6: Commit**

```bash
cd services/api && uv run ruff format . && uv run ruff check --fix . && uv run mypy .
cd ../.. && git add services/api/nightshift/domain/queue.py services/api/tests/test_queue.py
git commit -m "feat(queue): compute the four rows the queue can prove"
```

---

### Task 2: The indexes, and the proof each query can use one

`ix_applications_next_action_at` and `ix_jobs_status_last_seen_at` already exist — M2b added the first one *for* this milestone. What does not exist is anything serving the two event queries.

**Files:**
- Modify: `services/api/nightshift/db/models.py` (the `ApplicationEvent.__table_args__` block, around line 1018)
- Create: `services/api/migrations/versions/<rev>_queue_indexes.py`
- Modify: `services/api/tests/test_query_plans.py`

**Interfaces:**
- Consumes: `queue_selects` from Task 1.
- Produces: indexes `ix_application_events_user_activity` and `ix_application_events_interviews`.

- [ ] **Step 1: Add both indexes to the model**

In `services/api/nightshift/db/models.py`, inside `ApplicationEvent.__table_args__`, after the existing `Index(...)` and before the two `CheckConstraint`s:

```python
        # M2d. The queue asks "when did this person last touch this
        # application?" across the whole table, and `actor` is not the leading
        # column of the index above. Partial, because system events are
        # deliberately excluded from that answer (command-center.md §7.2) and
        # indexing them would be dead weight.
        Index(
            "ix_application_events_user_activity",
            "application_id",
            "occurred_at",
            postgresql_where=text("actor = 'user'"),
        ),
        # M2d. "Interviews in the next fortnight" scans by time across every
        # application, so application_id being the leading column of the index
        # above makes it unusable here.
        Index(
            "ix_application_events_interviews",
            "occurred_at",
            postgresql_where=text("event_type = 'interview_scheduled'"),
        ),
```

`text` is already imported in this module.

- [ ] **Step 2: Generate the migration and then read it**

```bash
make up
cd services/api && uv run alembic revision --autogenerate -m "queue indexes"
```

**Now open the generated file and check three things**, because autogenerate has produced a broken migration four times in this project:

1. Both `op.create_index` calls carry `postgresql_where=sa.text("...")`. If the `postgresql_where` is missing, the index is not partial and the plan test may still pass while the index is twice the size it should be.
2. `downgrade()` drops both indexes.
3. No `nightshift.db.types.UTCDateTime` appears without an import. It should not — this migration touches no columns — but the note at the head of `0002` exists because this keeps happening.

Rename the file to the house convention: `<YYYYMMDD>_<HHMM>_queue_indexes.py`.

- [ ] **Step 3: Test the migration both directions**

```bash
cd services/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check
```

Expected: three clean runs and `No new upgrade operations detected.`

- [ ] **Step 4: Add the query-plan assertions**

In `services/api/tests/test_query_plans.py`, append. This file's docstring explains the `enable_seqscan = off` technique — read it before writing; the reason it works is that it answers "is this filter servable by an index?" rather than "did the planner pick one on a tiny corpus?".

```python
QUEUE_SECTIONS = [pytest.param(key, id=key.value) for key in QueueSectionKey]


@pytest.mark.parametrize("key", QUEUE_SECTIONS)
async def test_every_queue_section_is_servable_by_an_index(
    db_session: AsyncSession, key: QueueSectionKey
) -> None:
    """M2d. The queue runs on every page load and grows with the user's
    pipeline, so each of its four queries must be able to use an index."""
    stmt = queue_selects(user_id=uuid.uuid4(), now=datetime(2026, 8, 4, tzinfo=UTC))[key]
    plan = await _plan(db_session, stmt)
    assert _index_nodes(plan), f"{key.value} can use no index: {json.dumps(plan)[:800]}"
```

Add the imports this needs at the top of the file: `import uuid`, and `from nightshift.domain.queue import QueueSectionKey, queue_selects`.

`_plan` and `_index_nodes` already exist in this file (lines 51 and 62) and both are reused as-is. Do not write a second `EXPLAIN (FORMAT JSON)` call — `_plan` compiles with `paramstyle="named"` and sets `enable_seqscan = off` inside the transaction, and the new assertions must run the statement exactly the way the existing ones do.

- [ ] **Step 5: Run the plan tests**

```bash
cd services/api && uv run pytest tests/test_query_plans.py -q
```

Expected: all pass, including the pre-existing non-vacuity guard
`test_a_filter_on_an_unindexed_column_is_detectable`. **If that guard fails, stop** — it means the assertion above would pass against anything and proves nothing.

- [ ] **Step 6: Commit**

```bash
cd services/api && uv run ruff format . && uv run ruff check --fix . && uv run mypy .
cd ../.. && git add services/api/nightshift/db/models.py services/api/migrations services/api/tests/test_query_plans.py
git commit -m "feat(queue): index the two event queries the queue runs"
```

---

### Task 3: The route — four sections, four named absences, and the thresholds

**Files:**
- Create: `services/api/nightshift/api/routes/queue.py`
- Modify: `services/api/nightshift/api/schemas.py`
- Modify: `services/api/nightshift/api/main.py` (router registration)
- Create: `services/api/tests/test_queue_routes.py`

**Interfaces:**
- Consumes: `build_queue`, `QueueSectionKey`, `FOLLOW_UP_SILENT_DAYS`, `STALE_SAVED_DAYS`, `INTERVIEW_HORIZON_DAYS` from Task 1.
- Produces: `GET /queue` returning `DailyQueueOut`; schemas `QueueRowOut`, `QueueSectionOut`, `DeferredQueueRowOut`, `QueueThresholdsOut`, `DailyQueueOut`.

- [ ] **Step 1: Add the schemas**

In `services/api/nightshift/api/schemas.py`, after the application schemas (around line 473):

```python
class QueueRowOut(BaseModel):
    """One row. `because` is a sentence, not a score — I4."""

    application_id: UUID
    job_id: UUID
    job_title: str
    company_name: str
    current_stage: ApplicationStage
    at: datetime | None
    because: str


class QueueSectionOut(BaseModel):
    key: QueueSectionKey
    title: str
    rows: list[QueueRowOut]
    #: Before the cap, so the page can say "and N more" honestly.
    total: int


class DeferredQueueRowOut(BaseModel):
    """I7: a row this system cannot compute yet, named rather than faked.

    Same shape as `DeferredApplicationFieldOut` and `DeferredFilter` because it
    is the same idea in a third place.
    """

    name: str
    blocked_on: str
    reason: str


class QueueThresholdsOut(BaseModel):
    """The numbers behind the rows, so the page can explain itself without a
    second copy of them in TypeScript.

    M2c's enum-parity defect is the reason this is in the response: two
    vocabularies transcribed by hand into two languages drifted, and nothing
    local could see it.
    """

    follow_up_silent_days: int
    stale_saved_days: int
    interview_horizon_days: int
    row_cap: int


class DailyQueueOut(BaseModel):
    generated_at: datetime
    sections: list[QueueSectionOut]
    total_rows: int
    deferred_rows: list[DeferredQueueRowOut]
    thresholds: QueueThresholdsOut
```

Import `QueueSectionKey` from `nightshift.domain.queue` at the top of the file alongside the other domain imports.

- [ ] **Step 2: Write the failing route tests**

Create `services/api/tests/test_queue_routes.py`. **There is no `client` fixture in `conftest.py`** — each route-test file defines its own, because it overrides `current_user_id` as well as `get_db_session` so the suite does not depend on `make seed` having run. Copy the three fixtures from `tests/test_application_routes.py:33-72` verbatim (`user`, `job`, `client`); they are reproduced here so this task can be executed without reading that file:

```python
"""GET /queue — the shape the page depends on.

The queue's *rules* are tested in `test_queue.py` against the database. This
file tests the boundary: that the four sections always appear, that the four
deferred rows are named, and that the thresholds the page renders come from
the same constants the queries use.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, User
from nightshift.db.session import get_db_session
from nightshift.domain.queue import (
    FOLLOW_UP_SILENT_DAYS,
    INTERVIEW_HORIZON_DAYS,
    ROW_CAP,
    STALE_SAVED_DAYS,
    QueueSectionKey,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def job(db_session: AsyncSession) -> Job:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    db_session.add(company)
    await db_session.flush()
    row = Job(
        company_id=company.id,
        title="Software Engineer",
        normalized_title="software engineer",
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession, user: User) -> AsyncIterator[AsyncClient]:
    """Overrides the session *and* the current user, so these tests act as a
    user they created rather than depending on the seeded `dev_user`."""
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _user() -> uuid.UUID:
        return user.id

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[current_user_id] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_the_queue_always_returns_four_sections(client: AsyncClient) -> None:
    """Even with nothing to do. The page renders "nothing today" from a
    well-formed answer, not from an empty body."""
    response = await client.get("/queue")
    assert response.status_code == 200
    body = response.json()
    assert [section["key"] for section in body["sections"]] == [key.value for key in QueueSectionKey]


async def test_every_section_carries_a_human_title(client: AsyncClient) -> None:
    body = (await client.get("/queue")).json()
    for section in body["sections"]:
        assert section["title"].strip()
        assert section["title"] != section["key"]


async def test_the_four_deferred_rows_are_named_with_reasons(client: AsyncClient) -> None:
    """I7. The rows M3 will bring exist on the page as named absences."""
    body = (await client.get("/queue")).json()
    names = {row["name"] for row in body["deferred_rows"]}
    assert len(body["deferred_rows"]) == 4
    assert all(row["reason"].strip() and row["blocked_on"].strip() for row in body["deferred_rows"])
    assert any("internship" in name.lower() for name in names)
    assert any("resume" in name.lower() for name in names)


async def test_no_deferred_row_shows_a_number(client: AsyncClient) -> None:
    """A deferred row with a count beside it reads as real. I4 and I7."""
    body = (await client.get("/queue")).json()
    for row in body["deferred_rows"]:
        assert not any(character.isdigit() for character in row["name"])


async def test_the_thresholds_are_the_constants_the_queries_use(client: AsyncClient) -> None:
    """The guard against the M2c defect: a number transcribed into TypeScript
    by hand and drifting silently from the one Python filters on."""
    thresholds = (await client.get("/queue")).json()["thresholds"]
    assert thresholds == {
        "follow_up_silent_days": FOLLOW_UP_SILENT_DAYS,
        "stale_saved_days": STALE_SAVED_DAYS,
        "interview_horizon_days": INTERVIEW_HORIZON_DAYS,
        "row_cap": ROW_CAP,
    }


async def test_the_queue_has_no_write_route(client: AsyncClient) -> None:
    """§7.3. The queue suggests; it does not act (I5). If a POST appears here
    later, this test is the conversation about whether it should."""
    for method in ("post", "patch", "put", "delete"):
        response = await getattr(client, method)("/queue")
        assert response.status_code == 405, method
```

- [ ] **Step 3: Run them to verify they fail**

```bash
cd services/api && uv run pytest tests/test_queue_routes.py -q
```

Expected: every test fails with 404, because the route does not exist.

- [ ] **Step 4: Write the route**

Create `services/api/nightshift/api/routes/queue.py`:

```python
"""The daily queue.

Routes validate and delegate (CLAUDE.md §3). Every rule lives in
`nightshift.domain.queue`; this module reads the clock, calls one function, and
shapes the answer. There is no write route here and §7.3 says there is not to
be one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import CurrentUserId
from nightshift.api.schemas import (
    DailyQueueOut,
    DeferredQueueRowOut,
    QueueRowOut,
    QueueSectionOut,
    QueueThresholdsOut,
)
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.queue import (
    FOLLOW_UP_SILENT_DAYS,
    INTERVIEW_HORIZON_DAYS,
    ROW_CAP,
    STALE_SAVED_DAYS,
    QueueSectionKey,
    build_queue,
)

router = APIRouter(prefix="/queue", tags=["queue"])

#: Rendered as headings. Kept beside the keys rather than in TypeScript so the
#: API is self-describing and the page cannot invent a fifth section.
SECTION_TITLES: dict[QueueSectionKey, str] = {
    QueueSectionKey.FOLLOW_UP: "Follow up",
    QueueSectionKey.INTERVIEWS_APPROACHING: "Interviews approaching",
    QueueSectionKey.STALE_SAVED: "Saved and going quiet",
    QueueSectionKey.CLOSED_WHILE_SAVED: "Closed while you were tracking it",
}

#: I7: the four rows PRODUCT-SPEC §10.4 asks for that this system cannot
#: compute honestly yet. Named on the page with the reason, because an empty
#: section claims "you have none of these" and that is a different, false
#: statement. `command-center.md` §7.
DEFERRED_ROWS: tuple[DeferredQueueRowOut, ...] = (
    DeferredQueueRowOut(
        name="Best new internships",
        blocked_on="milestone 3",
        reason=(
            "'best' is a ranking, and there is no match score behind it yet. A list "
            "ordered by anything else would be a guess wearing a recommendation's clothes."
        ),
    ),
    DeferredQueueRowOut(
        name="High-match roles closing soon",
        blocked_on="milestone 3",
        reason=(
            "needs both a match score and a closing date. Most sources publish no "
            "deadline at all, so even the second half is often unknowable."
        ),
    ),
    DeferredQueueRowOut(
        name="Resume mismatch warnings",
        blocked_on="milestone 3",
        reason=(
            "needs requirement extraction and the evidence graph, so that a warning "
            "can point at the specific gap rather than assert one."
        ),
    ),
    DeferredQueueRowOut(
        name="The one thing to do today",
        blocked_on="milestone 3",
        reason=(
            "ranking across every row above. It is the most useful line on this page "
            "and the least honest to fake, so it waits."
        ),
    ),
)


@router.get("", response_model=DailyQueueOut)
async def get_queue(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> DailyQueueOut:
    """What to look at today, and what this page still cannot tell you."""
    now = utcnow()
    queue = await build_queue(session, user_id=user_id, now=now)
    return DailyQueueOut(
        generated_at=now,
        sections=[
            QueueSectionOut(
                key=section.key,
                title=SECTION_TITLES[section.key],
                rows=[
                    QueueRowOut(
                        application_id=row.application_id,
                        job_id=row.job_id,
                        job_title=row.job_title,
                        company_name=row.company_name,
                        current_stage=row.current_stage,
                        at=row.at,
                        because=row.because,
                    )
                    for row in section.rows
                ],
                total=section.total,
            )
            for section in queue.sections
        ],
        total_rows=queue.total_rows,
        deferred_rows=list(DEFERRED_ROWS),
        thresholds=QueueThresholdsOut(
            follow_up_silent_days=FOLLOW_UP_SILENT_DAYS,
            stale_saved_days=STALE_SAVED_DAYS,
            interview_horizon_days=INTERVIEW_HORIZON_DAYS,
            row_cap=ROW_CAP,
        ),
    )
```

- [ ] **Step 5: Register the router**

In `services/api/nightshift/api/main.py`, import the module beside the other route imports and add `app.include_router(queue.router)` in the same block as the others, keeping the file's existing ordering convention.

- [ ] **Step 6: Run the route tests**

```bash
cd services/api && uv run pytest tests/test_queue_routes.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd services/api && uv run ruff format . && uv run ruff check --fix . && uv run mypy .
cd ../.. && git add services/api/nightshift services/api/tests/test_queue_routes.py
git commit -m "feat(api): serve the daily queue, and name the rows it cannot compute"
```

---

### Task 4: Web schemas and the client call

**Files:**
- Modify: `apps/web/src/lib/schemas.ts`
- Modify: `apps/web/src/lib/schemas.test.ts`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `services/api/tests/test_enum_parity.py`

**Interfaces:**
- Consumes: the `DailyQueueOut` shape from Task 3.
- Produces: `queueSectionKeySchema`, `queueRowSchema`, `queueSectionSchema`, `deferredQueueRowSchema`, `queueThresholdsSchema`, `dailyQueueSchema`; types `QueueRow`, `QueueSection`, `DailyQueue`; `fetchQueue(): Promise<DailyQueue>`.

- [ ] **Step 1: Add the Zod schemas**

In `apps/web/src/lib/schemas.ts`, after the application schemas (around line 441):

```ts
export const queueSectionKeySchema = z.enum([
  'follow_up',
  'interviews_approaching',
  'stale_saved',
  'closed_while_saved',
]);
export type QueueSectionKey = z.infer<typeof queueSectionKeySchema>;

export const queueRowSchema = z.object({
  application_id: z.string().uuid(),
  job_id: z.string().uuid(),
  job_title: z.string(),
  company_name: z.string(),
  current_stage: applicationStageSchema,
  at: z.string().datetime({ offset: true }).nullable(),
  // A row with no reason is a bare signal, which is what I4 exists to prevent.
  because: z.string().min(1),
});
export type QueueRow = z.infer<typeof queueRowSchema>;

export const queueSectionSchema = z.object({
  key: queueSectionKeySchema,
  title: z.string().min(1),
  rows: queueRowSchema.array(),
  total: z.number().int().nonnegative(),
});
export type QueueSection = z.infer<typeof queueSectionSchema>;

export const deferredQueueRowSchema = z.object({
  name: z.string().min(1),
  blocked_on: z.string().min(1),
  reason: z.string().min(1),
});
export type DeferredQueueRow = z.infer<typeof deferredQueueRowSchema>;

export const queueThresholdsSchema = z.object({
  follow_up_silent_days: z.number().int().positive(),
  stale_saved_days: z.number().int().positive(),
  interview_horizon_days: z.number().int().positive(),
  row_cap: z.number().int().positive(),
});
export type QueueThresholds = z.infer<typeof queueThresholdsSchema>;

export const dailyQueueSchema = z.object({
  generated_at: z.string().datetime({ offset: true }),
  sections: queueSectionSchema.array(),
  total_rows: z.number().int().nonnegative(),
  deferred_rows: deferredQueueRowSchema.array(),
  thresholds: queueThresholdsSchema,
});
export type DailyQueue = z.infer<typeof dailyQueueSchema>;
```

- [ ] **Step 2: Add the schema tests**

In `apps/web/src/lib/schemas.test.ts`:

```ts
describe('dailyQueueSchema', () => {
  const row = {
    application_id: '00000000-0000-4000-8000-000000000001',
    job_id: '00000000-0000-4000-8000-000000000002',
    job_title: 'Software Engineer Intern',
    company_name: 'Example Inc.',
    current_stage: 'applied',
    at: '2026-08-04T12:00:00+00:00',
    because: 'no activity from you in 9 days',
  };

  it('accepts a well-formed queue', () => {
    const parsed = dailyQueueSchema.parse({
      generated_at: '2026-08-04T12:00:00+00:00',
      sections: [{ key: 'follow_up', title: 'Follow up', rows: [row], total: 1 }],
      total_rows: 1,
      deferred_rows: [
        { name: 'Best new internships', blocked_on: 'milestone 3', reason: 'no score yet' },
      ],
      thresholds: {
        follow_up_silent_days: 7,
        stale_saved_days: 21,
        interview_horizon_days: 14,
        row_cap: 20,
      },
    });
    expect(parsed.sections[0].rows[0].because).toContain('9 days');
  });

  it('refuses a row with no reason', () => {
    // A row that cannot say why it is there is the bug I4 describes, and the
    // schema is where it gets stopped rather than rendered as a bare title.
    const result = queueRowSchema.safeParse({ ...row, because: '' });
    expect(result.success).toBe(false);
  });

  it('allows a row with no date, because not every row has one', () => {
    expect(queueRowSchema.safeParse({ ...row, at: null }).success).toBe(true);
  });

  it('refuses a section key the API does not serve', () => {
    expect(queueSectionKeySchema.safeParse('recommended_action').success).toBe(false);
  });
});
```

- [ ] **Step 3: Add the client call**

In `apps/web/src/lib/api.ts`, following the shape of `fetchCoverage`:

```ts
export function fetchQueue(): Promise<DailyQueue> {
  return request('/queue', dailyQueueSchema);
}
```

Match the existing helper's name and signature exactly — read `fetchCoverage` at line 240 and copy its form rather than inventing one.

- [ ] **Step 4: Extend the enum-parity guard, and close the gap it already had**

`services/api/tests/test_enum_parity.py` is the only test in this repo that reads both sides of the Python/TypeScript boundary at once, and it exists because two enums were transcribed wrong in M2c and nothing local could see it. The registry is the `PAIRS` tuple at line 44.

**`QueueSectionKey` is new and goes in. So do four enums that were already crossing this boundary unguarded** — `PAIRS` covers nine enums, all of them M2c's, and M2b's application vocabulary was never added. The queue's own row schema parses `current_stage` through `applicationStageSchema`, so this slice depends directly on one of them being right. All four are already declared as `z.enum([...])` in `schemas.ts`, which is the form `_typescript_enum`'s regex requires.

```python
PAIRS: tuple[tuple[str, type[enum.Enum]], ...] = (
    # ... the nine existing pairs, unchanged ...
    # M2d. `QueueSectionKey` is the first entry here that is not a database
    # enum — it is a shape of the API, defined in `domain.queue`. It crosses
    # the same boundary and drifts the same way, which is what this file is
    # about.
    ("queueSectionKeySchema", QueueSectionKey),
    # M2b's vocabulary, unguarded until now. The queue's row schema parses
    # `current_stage`, so M2d depends on the first of these being correct.
    ("applicationStageSchema", ApplicationStage),
    ("applicationPrioritySchema", ApplicationPriority),
    ("applicationEventTypeSchema", ApplicationEventType),
    ("transitionClassSchema", TransitionClass),
)
```

Add the imports: `ApplicationEventType`, `ApplicationPriority`, `ApplicationStage` and `TransitionClass` from `nightshift.db.base`, and `QueueSectionKey` from `nightshift.domain.queue`.

**Expect at least one of the four M2b additions to fail on its first run.** Four enums transcribed by hand into TypeScript and never machine-checked is exactly the condition that produced M2c's defect — if all four pass immediately, that is a pleasant surprise and worth recording in the review rather than assuming. If one fails, fix the TypeScript to match Python (the API is the authority on what it can send) and note it in the review as a defect this guard found.

- [ ] **Step 5: Run both suites**

```bash
cd apps/web && npm run test -- src/lib/schemas.test.ts
cd ../../services/api && uv run pytest tests/test_enum_parity.py -q
```

Expected: `schemas.test.ts` passes. For the parity suite, see the note in Step 4 — a failure on one of the three M2b enums is a defect found, not a mistake in this plan.

**Verify the parity test can fail** — temporarily delete `'stale_saved'` from `queueSectionKeySchema` and confirm the `queueSectionKeySchema` case goes red, then restore it. A parity test that cannot fail is the exact thing M2c's defect hid behind.

- [ ] **Step 6: Commit**

```bash
cd apps/web && npm run lint && npx tsc --noEmit
cd ../.. && git add apps/web/src/lib services/api/tests/test_enum_parity.py
git commit -m "feat(web): add queue schemas, the client call, and the parity guard"
```

---

### Task 5: The page

**Files:**
- Create: `apps/web/src/components/QueuePanel.tsx`
- Create: `apps/web/src/components/QueuePanel.test.tsx`
- Create: `apps/web/src/app/operate/queue/page.tsx`
- Modify: `apps/web/src/app/operate/page.tsx`

**Interfaces:**
- Consumes: `fetchQueue`, `DailyQueue`, `QueueSection`, `QueueRow` from Task 4.
- Produces: `QueuePanel` (no props; fetches through TanStack Query, like `PipelineBoard`).

- [ ] **Step 1: Write the failing component tests**

Create `apps/web/src/components/QueuePanel.test.tsx`. Read `SkillList.test.tsx` first for this repo's render helper and query-client wrapper, and reuse them rather than writing new ones.

```tsx
const QUEUE: DailyQueue = {
  generated_at: '2026-08-04T12:00:00+00:00',
  sections: [
    {
      key: 'follow_up',
      title: 'Follow up',
      rows: [
        {
          application_id: '00000000-0000-4000-8000-000000000001',
          job_id: '00000000-0000-4000-8000-000000000002',
          job_title: 'Backend Engineer',
          company_name: 'Example Inc.',
          current_stage: 'applied',
          at: '2026-07-26T12:00:00+00:00',
          because: 'no activity from you in 9 days',
        },
      ],
      total: 24,
    },
    { key: 'interviews_approaching', title: 'Interviews approaching', rows: [], total: 0 },
    { key: 'stale_saved', title: 'Saved and going quiet', rows: [], total: 0 },
    { key: 'closed_while_saved', title: 'Closed while you were tracking it', rows: [], total: 0 },
  ],
  total_rows: 24,
  deferred_rows: [
    { name: 'Best new internships', blocked_on: 'milestone 3', reason: 'there is no match score yet' },
    { name: 'High-match roles closing soon', blocked_on: 'milestone 3', reason: 'needs a score' },
    { name: 'Resume mismatch warnings', blocked_on: 'milestone 3', reason: 'needs extraction' },
    { name: 'The one thing to do today', blocked_on: 'milestone 3', reason: 'needs ranking' },
  ],
  thresholds: {
    follow_up_silent_days: 7,
    stale_saved_days: 21,
    interview_horizon_days: 14,
    row_cap: 20,
  },
};

describe('QueuePanel', () => {
  it('parses its own fixture through the real schema', () => {
    // M2c shipped a component fixture the API could not produce, sitting
    // inside the test for the schema that would have refused it.
    expect(dailyQueueSchema.safeParse(QUEUE).success).toBe(true);
  });

  it('shows each row with the reason it is there', async () => {
    renderWithQuery(<QueuePanel />, { queue: QUEUE });
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText(/no activity from you in 9 days/i)).toBeInTheDocument();
  });

  it('links each row to its application', async () => {
    renderWithQuery(<QueuePanel />, { queue: QUEUE });
    const link = await screen.findByRole('link', { name: /Backend Engineer/i });
    expect(link).toHaveAttribute(
      'href',
      '/operate/applications/00000000-0000-4000-8000-000000000001',
    );
  });

  it('says how many rows it capped rather than truncating quietly', async () => {
    renderWithQuery(<QueuePanel />, { queue: QUEUE });
    expect(await screen.findByText(/23 more/i)).toBeInTheDocument();
  });

  it('names all four deferred rows without anything being expanded', async () => {
    renderWithQuery(<QueuePanel />, { queue: QUEUE });
    const deferred = await screen.findByTestId('deferred-queue-rows');
    expect(deferred).toHaveTextContent(/best new internships/i);
    expect(deferred).toHaveTextContent(/resume mismatch/i);
    expect(deferred).toHaveTextContent(/one thing to do today/i);
    expect(deferred).toHaveTextContent(/milestone 3/i);
  });

  it('shows no number beside a deferred row', async () => {
    // A count next to a deferred row reads as a real, empty result.
    renderWithQuery(<QueuePanel />, { queue: QUEUE });
    const deferred = await screen.findByTestId('deferred-queue-rows');
    expect(deferred.textContent ?? '').not.toMatch(/\(\s*\d+\s*\)/);
  });

  it('distinguishes an empty section from an empty queue', async () => {
    const empty: DailyQueue = {
      ...QUEUE,
      sections: QUEUE.sections.map((section) => ({ ...section, rows: [], total: 0 })),
      total_rows: 0,
    };
    renderWithQuery(<QueuePanel />, { queue: empty });
    expect(await screen.findByTestId('queue-empty')).toHaveTextContent(/nothing needs you today/i);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd apps/web && npm run test -- src/components/QueuePanel.test.tsx
```

Expected: fails to resolve `@/components/QueuePanel`.

- [ ] **Step 3: Write the component**

Create `apps/web/src/components/QueuePanel.tsx`. Constraints, all load-bearing:

- Fetch with `useQuery({ queryKey: ['queue'], queryFn: fetchQueue })`, matching `PipelineBoard`'s form.
- Render **every** section, including empty ones, each with its title. An empty section says so in one line ("nothing here today"). When `total_rows === 0`, render an additional block with `data-testid="queue-empty"` reading *"Nothing needs you today. That is a normal state, not a failure — this page only shows work that is actually waiting."*
- Each row is a `next/link` to `/operate/applications/{application_id}` whose accessible name contains the job title. Under it: company name, current stage, and `because`.
- Dates render with `toLocaleDateString` in the browser's zone. **The database is UTC and the conversion happens here, at the edge, and nowhere else.**
- When `rows.length < total`, render `and {total - rows.length} more` as text, not a link to a page that does not exist.
- Deferred rows go in a section with `data-testid="deferred-queue-rows"`, each showing name, `blocked_on` and `reason`, visible without expanding anything, and carrying **no count**.
- Use the existing `paper*` / `ink*` tokens and `signal-400`. No new colour token; if the design seems to need one, it needs an assertion in `colour-contrast.test.ts` too.
- No `any`. No client-side filtering or re-sorting — the API decided the order and duplicating that decision here is how the two drift apart.

- [ ] **Step 4: Write the page and link it from Operate**

`apps/web/src/app/operate/queue/page.tsx`, matching `pipeline/page.tsx`'s shape exactly:

```tsx
import { QueuePanel } from '@/components/QueuePanel';

export default function QueuePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Today</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          What is actually waiting on you, from what this system can prove. Nothing here is ranked
          and nothing here acts on its own — every row is a link to the application it is about.
        </p>
      </section>
      <QueuePanel />
    </div>
  );
}
```

In `apps/web/src/app/operate/page.tsx`:
1. Add a section linking to `/operate/queue`, placed **first**, above Pipeline — it is the page you open at the start of the day.
2. Delete the line `<li>The daily queue — milestone 2.</li>` from the "Not built yet" list. Leaving it there would make the page claim something false the moment this ships, which is the exact failure mode that list exists to prevent.

- [ ] **Step 5: Run the component tests**

```bash
cd apps/web && npm run test -- src/components/QueuePanel.test.tsx
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd apps/web && npm run lint && npx tsc --noEmit
cd ../.. && git add apps/web/src
git commit -m "feat(web): add the daily queue page, with its absences named"
```

---

### Task 6: The queue in a real browser, and in `make acceptance`

Two independent proofs against a running stack. Neither is a proxy for the criterion — each one *is* a check that the page shows true things.

**Files:**
- Create: `apps/web/e2e-seeded/queue.spec.ts`
- Modify: `scripts/verify.py`

**Interfaces:**
- Consumes: `GET /queue`, the page at `/operate/queue`.
- Produces: `check_daily_queue()` in `verify.py`, registered in `main()`.

- [ ] **Step 1: Write the browser test**

Create `apps/web/e2e-seeded/queue.spec.ts`. Read `e2e-seeded/pipeline.spec.ts` first — it is the closest analogue and it carries two lessons this test must inherit: **normalise what you find on entry** rather than trusting a previous run's tidy exit, and **clean up after yourself**.

The walk:

1. Go to `/operate` and follow the queue link. Assert the heading.
2. Assert all four section titles are present, even when empty.
3. Assert the deferred block names all four M3 rows and reads "milestone 3", **without clicking anything to expand it**.
4. Save a job through the UI, open its application, and set a next action in the past through the API (`PATCH /applications/{id}` with `next_action_at`). Reload the queue and assert the job appears under Follow up with a reason mentioning the next action.
5. Click the row and assert the browser lands on that application's page.
6. Record an interview two days out. Reload and assert it appears under Interviews approaching with the date shown.
7. Clean up: archive the application, and assert it then appears in **no** section. This is both the teardown and the archived-exclusion assertion, which is the strongest form of a cleanup step.

- [ ] **Step 2: Run it against the seeded stack**

```bash
make up && make migrate && make seed
cd apps/web && npx playwright test e2e-seeded/queue.spec.ts
```

Expected: passes. **Run it twice in a row** — the second run is the real test of step 7, and M2b's pipeline test could not run twice for exactly this reason.

- [ ] **Step 3: Add the acceptance check**

In `scripts/verify.py`, add `check_daily_queue()` modelled on `check_profile_confirmation` (line 110) and `check_application_tracking` (line 217), and register it in `main()`.

It must **compare before and after** rather than asserting an absolute state. `check_profile_confirmation` was written this way deliberately: asserting "the queue is empty" would pass vacuously on a fresh database and fail on a developer's own machine, which is a check that reports success for the wrong reason.

The steps, each printing a `✓` line with the value it measured:

```
✓ the queue answers                             HTTP 200
✓ four sections, always                         follow_up, interviews_approaching, stale_saved, closed_while_saved
✓ four deferred rows, each with a reason        4
✓ the thresholds match the ones queries use     7 / 21 / 14
✓ a saved job with a past next action appears   +1 in follow_up
✓ every row says why it is there
✓ archiving removes it from every section       back to the count we started with
✓ the application this check created is removed  nothing is left behind
```

The last line matters. `check_application_tracking` leaves one archived application behind by design and says so in its docstring; this check should leave nothing, and should say so.

- [ ] **Step 4: Run the whole acceptance path**

```bash
make acceptance
```

Expected: every verify check passes and the seeded browser suite passes, with the queue counts included.

- [ ] **Step 5: Commit**

```bash
git add apps/web/e2e-seeded/queue.spec.ts scripts/verify.py
git commit -m "test(queue): walk the queue in a browser and assert it in acceptance"
```

---

### Task 7: ADR, review, PROGRESS

**Files:**
- Create: `docs/adr/0014-the-queue-reads-current-state-not-history.md`
- Create: `docs/reviews/milestone-2d-review.md`
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: Write ADR 0014**

Follow the format of `docs/adr/0013-*.md`. The decision worth recording is not "we built a queue" — it is the rule that makes it honest:

> **Queue membership is computed from current state, never from the history that produced it.**

Context: `application_events` is append-only and complete, so it is tempting to read membership from it — "has a `listing_closed` event" is one join and no ambiguity. It is also wrong, because a listing can close and reopen and the event never stops being true. The same reasoning runs the other way for activity: there, history is the only source, and the rule that keeps it honest is that only `actor = 'user'` counts.

Consequences: two partial indexes; a section that empties itself when the world changes back; and a general rule for M3, which will face the identical choice with match results.

- [ ] **Step 2: Write the review**

`docs/reviews/milestone-2d-review.md`, following `milestone-2c-review.md`'s structure and actively hunting the failure modes CLAUDE.md §5 lists. For this slice specifically, check and write down the answer for each:

- **Does an empty section read as "you have none" or as "this is not built"?** They are different claims and the page makes both. Confirm each appears exactly where it is true.
- **Can a row point at an application the user cannot open?** Follow every link shape in a running browser rather than reasoning about it — M2c shipped a provenance link that 404'd.
- **Does the page do unbounded work?** `ROW_CAP` bounds the render; confirm the *count* queries are also bounded in cost, and that the four sections are four queries and not four per row.
- **Timezone.** A date rendered in UTC to a user in New York is wrong by up to five hours and looks completely plausible. Confirm conversion happens once, at the edge.
- **Does any test here assert nothing?** Re-run each mutation from Task 1 Step 5 and record which test caught it.
- **Does `make acceptance` leave anything behind?** Run it three times back to back.

- [ ] **Step 3: Update PROGRESS**

Set the milestone line, the task/commit table, and the evidence. **M2 has four acceptance criteria and M2d earns none of them** — all four were already verified at M2a, M2b and M2c. Say that plainly rather than inventing a fifth criterion for this slice to pass. What M2d does is complete M2's *deliverable* list from CLAUDE.md §6.

Record under "Not real yet": the four deferred rows, named, with milestone 3 beside each.

- [ ] **Step 4: Run all three commands and record their real counts**

```bash
make check
make acceptance
make test-e2e
```

**Read the counts from the output. Do not infer them.** M2a's first attempt at a measurement produced five plausible figures against a corpus of zero rows and was caught only because the corpus size was printed beside them.

- [ ] **Step 5: Commit, push, open the PR**

```bash
git add docs/
git commit -m "docs(m2d): record ADR 0014, the review, and the measured evidence"
git push -u origin m2d-daily-queue
gh pr create --title "M2d — the daily queue: four rows that are true, four named as absent" --body "..."
```

- [ ] **Step 6: Name the last commit CI must cover**

After CI runs, add to PROGRESS the run URL, the five job results with counts read from the logs, the `headSha` checked against the branch head, and the invariant line:

```
git diff <sha>..HEAD --stat    # must list nothing outside docs/
```

This is the check performed before merging, and it exists because PROGRESS has twice carried a green claim beside a SHA that was no longer the head.

---

## Self-review of this plan

**Spec coverage.** `command-center.md` §7 asks for four computable rows (Tasks 1, 3, 5), four named absences (Task 3's `DEFERRED_ROWS`, Task 5's `deferred-queue-rows` block, asserted in both), §7.1's assessment fold (Task 1's `AWAITING_STAGES`, `test_an_assessment_with_a_date_is_a_follow_up`), §7.2's three rules (the `actor = 'user'` filter with its mutation check, `_live`'s archived exclusion, and `_closed_while_saved_select` reading `Job.status`), and §7.3's read-only rule (`test_the_queue_has_no_write_route`). The thresholds are constants in one file and travel to the client in the response. PRODUCT-SPEC §10.4's ninth row is answered by §7.1 and by the fold test.

**Three things this plan asserts that could be wrong, and how the executor will find out.**

1. **`_last_user_activity` as a `GROUP BY` subquery may not use the new partial index** the way Task 2 assumes — an aggregate over the whole table can prefer a sequential scan even with `enable_seqscan = off` disfavouring it. Task 2 Step 5 is where this surfaces. If the plan test fails for `follow_up` or `stale_saved`, the fix is a `LATERAL` join taking `max(occurred_at)` per application rather than aggregating the table and joining; do not weaken the assertion to make it pass.
2. **`func.count()` over `stmt.subquery()`** carries the `ORDER BY` into the subquery, which Postgres allows but which is wasted work. If it is measurably slow on the seeded corpus, wrap with `.order_by(None)` before counting.
3. **`test_two_interviews_are_two_rows_soonest_first` assumes one application may appear twice in a section.** That is deliberate and stated in `build_queue`'s docstring, but it is a product judgement: two scheduled times are two appointments. If the review disagrees, the change is a `DISTINCT ON (application_id)` in `_interviews_select` and the test inverts — but say so in the review rather than changing it quietly.

**Type consistency.** `QueueSectionKey`, `QueueRow`, `QueueSection`, `DailyQueue` are defined in Task 1 and used unchanged in Tasks 2, 3, 4 and 5. The API field names (`application_id`, `job_id`, `job_title`, `company_name`, `current_stage`, `at`, `because`) are identical in the dataclass, the Pydantic model, the Zod schema and the component fixture. `queue_selects` is produced in Task 1 and consumed only in Task 2.

**Placeholders.** None. Task 5 Step 3 and Task 6 Steps 1 and 3 specify behaviour and constraints rather than full source — that is deliberate for a React component and two test walks whose surrounding conventions must be read from the neighbouring files they name, and each lists every assertion that must exist.
