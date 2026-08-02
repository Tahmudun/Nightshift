# M1b — Canonical spine: dedupe, freshness, closure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One canonical job per real-world opening however many boards describe
it, and a listing life cycle where a job that goes away stops being presented
as available — without an outage ever being mistaken for a closure.

**Architecture:** Two new pure-domain modules (`domain/freshness.py`,
`domain/dedupe.py`) whose decision functions take values and return verdicts,
with the database work confined to thin appliers in `domain/ingestion.py`.
Three new tables carry the audit trail the invariants require. Embeddings live
behind a Protocol so every test but one runs without the model.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0 async, Alembic,
PostgreSQL 16 + pgvector, fastembed (`BAAI/bge-small-en-v1.5`, 384-dim),
pytest, pytest-asyncio, ruff, mypy strict. Next.js/React/Tailwind for §5.

**Design:** `docs/architecture/canonical-spine.md`. **ADR 0009** fixes the
closure thresholds; **ADR 0010** fixes the dedupe layers and confines
similarity. Read both before Task 2.

---

## Where this sits

| Plan | Contents | Status |
|---|---|---|
| M1a — provider breadth | Lever + Ashby adapters, parser breadth, upserts, ingestion + route tests | **Merged** (`54ef35a`) |
| **M1b — canonical spine** (this) | Dedupe, freshness, closure state machine, admin job table, source health page | Ready |
| M1c — board discovery | `nightshift/discovery/`, Common Crawl, validation, batch approval, coverage page | Not written — design at `docs/architecture/board-discovery.md` |
| M1d — polling | Two-phase conditional polling, hot/warm tiers, queue-driven ARQ | Not written — design at ADR 0007 |

M1b comes before M1c and M1d because both of them multiply the number of
boards. Closing jobs correctly at three boards is a debuggable problem; finding
out the rule was wrong at 2,605 is not. M1d in particular depends on this
milestone's `job_status_events` to tell whether a change in poll cadence
changed closure behaviour.

---

## Global Constraints

Every task's requirements implicitly include these.

- **I1 — never fabricate a location.** No task here produces a coordinate.
  Dedupe compares locations; it never resolves them.
- **I3 — never silently close a listing.** `FetchOutcome(ok=False)` changes
  nothing: not status, not `consecutive_misses`, not `last_seen_at`. Only a
  board that answered contributes evidence.
- **I4 — never present a score without a breakdown.** Every merge stores its
  reason, its confidence, and its `ruleset_version`.
- **I6 — never claim a milestone is done without evidence.** Record recorded
  output in `docs/PROGRESS.md`, not "the code exists".
- **I7 — never let a mock become the product.** The `StubEmbedder` is a test
  double and is named one; the real model is exercised by at least one test.
- **Nothing outside `nightshift/adapters/http.py` imports `httpx`.**
- **`OUTBOUND_HTTP_ENABLED` defaults to `false`.** Tests never reach the
  network. The embedding model is fetched by `make setup`, not at run time.
- **mypy strict must pass** — `cd services/api && mypy nightshift`.
- **Every migration is reversible and tested both directions.**
- **Time is UTC everywhere.** `TIMESTAMPTZ`; naive datetimes are rejected at
  the boundary by `nightshift/db/types.py`.
- **TODOs carry a milestone**: `TODO(M1d): ...`. A bare `TODO` is a lint failure.
- **Run `make check` before every commit.** Conventional commits, scoped.
- **The database is required from Task 1 onward.** `make up && make migrate`
  first. Tests that need it use the existing `requires_db` marker in
  `tests/conftest.py`.

---

## Facts this plan is built on

Read off the repository at `520ae66`, not assumed.

**The M0 schema already has the columns.** No task needs to add a column to
`jobs` or `source_job_records`:

| Column | File | Use here |
|---|---|---|
| `source_job_records.consecutive_misses` | `db/models.py:162` | Miss counter |
| `source_job_records.last_seen_at` | `db/models.py:158` | Absence clock |
| `source_job_records.source_status` | `db/models.py:165` | Per-record source verdict |
| `jobs.status` | `db/models.py:244` | The four-state machine |
| `jobs.closed_at` | `db/models.py:243` | Paired with `status` by check constraint `closed_at_matches_status` (`db/models.py:197`) |
| `jobs.last_seen_at` | `db/models.py:242` | Derived from live records |
| `job_source_links` | `db/models.py:345` | Unique per (job, record); a merge adds edges |

`JobStatus` already has all four members (`db/base.py:95-101`).
`ResolutionMethod`, `LocationConfidence`, `SourceStatus` all exist.

**The pipeline is already shaped for a merge step.** `persist_source_job`
(`domain/ingestion.py:223`) reaches its canonical job only through
`_canonical_job_for` (`:325`), which resolves through `job_source_links` and
never re-matches on title or URL. Dedupe therefore adds a step; it does not
restructure the pipeline.

**`IngestionStats.closed` exists and is hardcoded to 0** (`:73`). Task 3 makes
it real.

**What is missing and must be added:** the `pgvector` and `fastembed` Python
dependencies. `services/api/pyproject.toml:28` already carries the comment
`fastembed / pgvector -> M1 dedupe + M3 matching (AMENDMENTS A5)` marking the
intent.

---

## File Structure

**Create**

| Path | Responsibility |
|---|---|
| `services/api/migrations/versions/20260801_*_canonical_spine.py` | Three tables + two append-only triggers |
| `services/api/nightshift/domain/freshness.py` | Pure closure decision function + thresholds |
| `services/api/nightshift/domain/dedupe.py` | Pure comparison function + layers + ruleset version |
| `services/api/nightshift/domain/embeddings.py` | `Embedder` Protocol, `FastEmbedEmbedder`, `StubEmbedder` |
| `services/api/tests/test_freshness.py` | Table-driven closure cases |
| `services/api/tests/test_dedupe.py` | The seven §7.5 categories, fixture-driven |
| `services/api/tests/test_embeddings.py` | Determinism + dimension |
| `services/api/tests/test_closure_pipeline.py` | Closure against a real database |
| `services/api/tests/test_merge_pipeline.py` | Merge + reversibility against a real database |
| `services/api/tests/fixtures/dedupe_pairs.yaml` | Labelled pairs, all seven categories |
| `apps/web/src/components/JobAdminTable.tsx` | The admin job table |
| `apps/web/src/app/operate/jobs/page.tsx` | Its page |

**Modify**

| Path | Change |
|---|---|
| `services/api/pyproject.toml` | Add `pgvector`, `fastembed` |
| `services/api/nightshift/db/models.py` | `JobStatusEvent`, `JobEmbedding`, `JobMergeEvent` |
| `services/api/nightshift/domain/ingestion.py` | Apply freshness; apply dedupe on create |
| `services/api/nightshift/api/routes/jobs.py` | `GET /jobs/admin`, status filter |
| `services/api/nightshift/api/routes/sources.py` | Per-board health detail |
| `services/api/nightshift/api/schemas.py` | New response models |
| `services/api/nightshift/config.py` | Embedding model settings |
| `apps/web/src/components/SourceHealthTable.tsx` | Outage-vs-empty wording, per-board rows |
| `apps/web/src/lib/schemas.ts` | Zod for the new shapes |
| `Makefile` | `make setup` fetches the embedding model |
| `.github/workflows/ci.yml` | Cache the model |
| `docs/PROGRESS.md` | Evidence, "Not real yet", session log |

---

## Task 1: The migration — three tables, two triggers

**Files:**
- Create: `services/api/migrations/versions/20260801_*_canonical_spine.py`
- Modify: `services/api/nightshift/db/models.py`
- Modify: `services/api/pyproject.toml`
- Test: `services/api/tests/test_models_canonical_spine.py` (create)

**Interfaces:**
- Produces: ORM classes `JobStatusEvent`, `JobEmbedding`, `JobMergeEvent`, used
  by Tasks 3, 6 and 8.

- [ ] **Step 1: Add the two dependencies**

In `services/api/pyproject.toml`, in the main dependency list, replacing the
comment at line 28 with real entries:

```toml
  # AMENDMENTS A5: embeddings run locally. bge-small-en-v1.5 via fastembed —
  # free, offline, deterministic, no vendor. pgvector is the storage side.
  "pgvector>=0.3.6",
  "fastembed>=0.4.2",
```

Run: `make setup` — expect a large install (onnxruntime is a transitive
dependency of fastembed). Then `cd services/api && python3 -c "import
fastembed, pgvector; print('ok')"`.

- [ ] **Step 2: Write the failing model test**

```python
# services/api/tests/test_models_canonical_spine.py
"""The three tables M1b adds, and the guarantees they are supposed to carry.

The append-only assertions are the point of this file. `job_status_events` is
what makes a closure auditable after the job reopens, and an append-only table
enforced by convention is a comment. CLAUDE.md §7 requires a trigger.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, JobMergeEvent, JobStatusEvent
from tests.conftest import requires_db

pytestmark = requires_db


async def _a_job(session: AsyncSession) -> Job:
    company = Company(canonical_name="Acme", normalized_name=f"acme {uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    now = datetime.now(tz=UTC)
    job = Job(
        company_id=company.id,
        title="Engineer",
        normalized_title="engineer",
        first_seen_at=now,
        last_seen_at=now,
        status=JobStatus.OPEN,
    )
    session.add(job)
    await session.flush()
    return job


async def test_status_event_can_be_inserted(db_session: AsyncSession) -> None:
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(
            job_id=job.id,
            from_status=JobStatus.OPEN,
            to_status=JobStatus.POSSIBLY_STALE,
            reason="missed 3 consecutive polls",
        )
    )
    await db_session.flush()
    rows = (
        (await db_session.execute(select(JobStatusEvent).where(JobStatusEvent.job_id == job.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].to_status is JobStatus.POSSIBLY_STALE


async def test_status_events_cannot_be_updated(db_session: AsyncSession) -> None:
    """Append-only, enforced by trigger rather than by good intentions."""
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(job_id=job.id, from_status=None, to_status=JobStatus.OPEN, reason="created")
    )
    await db_session.flush()

    with pytest.raises((InternalError, ProgrammingError)):
        await db_session.execute(text("UPDATE job_status_events SET reason = 'rewritten'"))


async def test_status_events_cannot_be_deleted(db_session: AsyncSession) -> None:
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(job_id=job.id, from_status=None, to_status=JobStatus.OPEN, reason="created")
    )
    await db_session.flush()

    with pytest.raises((InternalError, ProgrammingError)):
        await db_session.execute(text("DELETE FROM job_status_events"))


async def test_merge_event_keeps_the_loser_id_without_a_foreign_key(
    db_session: AsyncSession,
) -> None:
    """The loser row is gone after a merge, so an FK would be unsatisfiable.

    Reversibility comes from the preserved raw payloads, not from this row —
    but the row has to survive the deletion of what it describes, which is why
    `loser_job_id` is a plain uuid column.
    """
    winner = await _a_job(db_session)
    vanished = uuid.uuid4()
    db_session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=vanished,
            loser_snapshot={"title": "Engineer"},
            reason="same_canonical_url",
            match_confidence=1.0,
            ruleset_version="1",
        )
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(JobMergeEvent).where(JobMergeEvent.loser_job_id == vanished)
        )
    ).scalar_one()
    assert row.ruleset_version == "1"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd services/api && pytest tests/test_models_canonical_spine.py -v`
Expected: FAIL — `ImportError: cannot import name 'JobStatusEvent'`.

- [ ] **Step 4: Add the three models**

Append to `services/api/nightshift/db/models.py`. Add
`from pgvector.sqlalchemy import Vector` to the imports.

```python
class JobStatusEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only record of every closure-machine transition.

    Exists because reopening is permitted (ADR 0009 §3.4). A reopened job has
    `status = open` and `closed_at = NULL` again, so without this table the
    fact that it ever closed is gone — and I6's standard of evidence would
    have nothing to point at. Enforced append-only by trigger, per CLAUDE.md §7.
    """

    __tablename__ = "job_status_events"
    __table_args__ = (Index("ix_job_status_events_job_id_created_at", "job_id", "created_at"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    # Null on the first event of a job's life: there was no prior state.
    from_status: Mapped[JobStatus | None] = mapped_column(_enum(JobStatus, "job_status"))
    to_status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    # Which poll produced this. SET NULL rather than CASCADE: pruning old run
    # rows must never delete the closure history they caused.
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    observed_misses: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )


class JobEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One vector per canonical job description (AMENDMENTS A5).

    `model_name` and `dimension` are stored on every row so replacing the model
    is a backfill rather than a mystery. `source_hash` is the description hash
    the vector was computed from, which is what lets a re-poll skip re-embedding
    an unchanged description.

    No vector index. At a few thousand jobs a sequential scan inside one
    company's candidates is faster than maintaining one, and an ivfflat index
    built on an almost-empty table returns wrong neighbours. Add one with a
    measurement, not in advance.
    """

    __tablename__ = "job_embeddings"
    __table_args__ = (UniqueConstraint("job_id", name="uq_job_embeddings_job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class JobMergeEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only record of one dedupe merge, with the evidence that caused it.

    I4 in spirit one milestone before I4's subsystem exists: a merge stores its
    components, not just its verdict. `loser_job_id` deliberately carries no
    foreign key — the row it names is deleted by the merge, and an FK would make
    the audit trail unstorable.
    """

    __tablename__ = "job_merge_events"
    __table_args__ = (
        Index("ix_job_merge_events_winner_job_id", "winner_job_id"),
        CheckConstraint(
            "match_confidence BETWEEN 0 AND 1", name="merge_confidence_is_a_probability"
        ),
        CheckConstraint("winner_job_id <> loser_job_id", name="merge_has_two_distinct_jobs"),
    )

    winner_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    loser_job_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    loser_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    match_confidence: Mapped[float] = mapped_column(NUMERIC(4, 3), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )
```

- [ ] **Step 5: Generate the migration**

```bash
make up && make migrate
cd services/api && ../../services/api/.venv/bin/alembic revision --autogenerate -m "canonical spine"
```

Autogenerate will produce the three `create_table` calls. It will **not**
produce the triggers — add them by hand to both `upgrade()` and `downgrade()`:

```python
APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION nightshift_refuse_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only table: % may not be %d', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # ... autogenerated create_table calls ...
    op.execute(APPEND_ONLY_FN)
    for table in ("job_status_events", "job_merge_events"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only "
            f"BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION nightshift_refuse_mutation()"
        )


def downgrade() -> None:
    for table in ("job_status_events", "job_merge_events"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS nightshift_refuse_mutation()")
    # ... autogenerated drop_table calls ...
```

Note the `%d` in the RAISE is deliberate — `TG_OP` is text, so use `%` twice:
write the message as `'append-only table: % may not accept %'` with
`TG_TABLE_NAME, TG_OP`. Fix it to that exact form; the placeholder above is
wrong on purpose only if you copy it blind, so copy this instead:

```sql
RAISE EXCEPTION 'append-only table: % may not accept %', TG_TABLE_NAME, TG_OP;
```

Check the autogenerated file for a `DROP TYPE` on `job_status`: the enum
already exists and is used by `jobs`, so autogenerate must **not** recreate or
drop it. If it emits one, delete that line — dropping it would break `jobs`.

- [ ] **Step 6: Test the migration both directions**

```bash
make migrate
cd services/api && ../../services/api/.venv/bin/alembic downgrade -1
../../services/api/.venv/bin/alembic upgrade head
```

Then confirm the trigger and function are actually gone after a downgrade:

```bash
docker exec nightshift-postgres-1 psql -U nightshift -d nightshift -c \
  "SELECT tgname FROM pg_trigger WHERE tgname LIKE '%append_only%';"
```

Expected after `downgrade -1`: zero rows. A downgrade that forgets the trigger
leaves a function behind that the next upgrade will `CREATE OR REPLACE` over —
silently working, and wrong.

- [ ] **Step 7: Run the model tests**

Run: `cd services/api && pytest tests/test_models_canonical_spine.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 8: `make check`, then commit**

```bash
make check
git add services/api/pyproject.toml services/api/nightshift/db/models.py \
        services/api/migrations/versions services/api/tests/test_models_canonical_spine.py
git commit -m "feat(db): add job_status_events, job_embeddings and job_merge_events

Two of the three are append-only and enforced by trigger, not convention.
job_status_events is what makes a closure auditable after the job reopens:
reopening nulls closed_at, so without the event table the closure is gone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The closure decision function (pure)

No database. The decision is a function of observations, and keeping it pure is
what makes the twenty-odd cases in ADR 0009 cheap to assert.

**Files:**
- Create: `services/api/nightshift/domain/freshness.py`
- Create: `services/api/tests/test_freshness.py`

**Interfaces:**
- Produces:
  - `MISSES_BEFORE_STALE: int`, `DAYS_ABSENT_BEFORE_CLOSED: int`,
    `DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED: int`, `CLOSURE_RULESET_VERSION: str`
  - `RecordObservation(consecutive_misses: int, last_seen_at: datetime)`
  - `ClosureDecision(status: JobStatus, reason: str)`
  - `decide_job_status(*, current: JobStatus, records: Sequence[RecordObservation], board_last_success_at: datetime | None, now: datetime) -> ClosureDecision`
  - Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/test_freshness.py
"""The closure state machine, as a table of cases.

ADR 0009 fixes the thresholds: three consecutive misses AND seven elapsed days
to close, fourteen days without a successful poll to become unverified. The
cases below are organised around the two ways this function can be wrong —
closing a job that is open, and failing to close one that is gone — because
those failures are not symmetric and the first one is invisible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nightshift.db.base import JobStatus
from nightshift.domain.freshness import (
    DAYS_ABSENT_BEFORE_CLOSED,
    DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED,
    MISSES_BEFORE_STALE,
    RecordObservation,
    decide_job_status,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _seen(days_ago: float, misses: int = 0) -> RecordObservation:
    return RecordObservation(
        consecutive_misses=misses, last_seen_at=NOW - timedelta(days=days_ago)
    )


def _decide(
    records: list[RecordObservation],
    *,
    current: JobStatus = JobStatus.OPEN,
    polled_days_ago: float | None = 0,
) -> JobStatus:
    board = None if polled_days_ago is None else NOW - timedelta(days=polled_days_ago)
    return decide_job_status(
        current=current, records=records, board_last_success_at=board, now=NOW
    ).status


class TestStaysOpen:
    def test_seen_on_the_last_poll(self) -> None:
        assert _decide([_seen(0)]) is JobStatus.OPEN

    def test_one_miss_is_not_enough(self) -> None:
        assert _decide([_seen(1, misses=1)]) is JobStatus.OPEN

    def test_two_misses_is_not_enough(self) -> None:
        assert _decide([_seen(2, misses=2)]) is JobStatus.OPEN

    def test_one_live_source_keeps_a_multi_source_job_open(self) -> None:
        """A job described by two boards is only gone when both stop listing it."""
        assert _decide([_seen(0, misses=0), _seen(30, misses=40)]) is JobStatus.OPEN

    def test_old_but_still_listed_is_open_not_stale(self) -> None:
        """Age is not absence. A job posted a year ago and still on the board is open."""
        assert _decide([_seen(365, misses=0)]) is JobStatus.OPEN


class TestBecomesStale:
    def test_three_misses_recently(self) -> None:
        assert _decide([_seen(1, misses=3)]) is JobStatus.POSSIBLY_STALE

    def test_three_misses_and_six_days_is_still_only_stale(self) -> None:
        """Both conditions are required. Six days is not seven."""
        assert _decide([_seen(6, misses=3)]) is JobStatus.POSSIBLY_STALE

    def test_all_sources_must_be_missing(self) -> None:
        assert _decide([_seen(9, misses=5), _seen(9, misses=5)]) is JobStatus.CLOSED


class TestBecomesClosed:
    def test_three_misses_and_seven_days(self) -> None:
        assert _decide([_seen(7, misses=3)]) is JobStatus.CLOSED

    def test_long_absence_with_too_few_misses_does_not_close(self) -> None:
        """The other half of the pair: a board polled twice in a month is not
        evidence of a month's absence."""
        assert _decide([_seen(30, misses=2)]) is JobStatus.OPEN


class TestUnverified:
    def test_board_silent_for_fourteen_days(self) -> None:
        assert _decide([_seen(20, misses=0)], polled_days_ago=14) is JobStatus.UNVERIFIED

    def test_never_successfully_polled(self) -> None:
        assert _decide([_seen(20, misses=0)], polled_days_ago=None) is JobStatus.UNVERIFIED

    def test_unverified_never_becomes_closed_however_long_it_lasts(self) -> None:
        """The invariant, asserted directly. A source outage cannot close a job
        no matter how long the source stays down — I3 has no time limit."""
        for days in (14, 90, 365, 3650):
            assert (
                _decide(
                    [_seen(days, misses=99)],
                    current=JobStatus.UNVERIFIED,
                    polled_days_ago=days,
                )
                is JobStatus.UNVERIFIED
            )

    def test_a_board_that_answers_again_leaves_unverified(self) -> None:
        assert (
            _decide([_seen(0, misses=0)], current=JobStatus.UNVERIFIED, polled_days_ago=0)
            is JobStatus.OPEN
        )


class TestReopening:
    def test_a_closed_job_seen_again_reopens(self) -> None:
        assert _decide([_seen(0, misses=0)], current=JobStatus.CLOSED) is JobStatus.OPEN

    def test_a_closed_job_still_missing_stays_closed(self) -> None:
        assert _decide([_seen(30, misses=30)], current=JobStatus.CLOSED) is JobStatus.CLOSED


class TestEdges:
    def test_a_job_with_no_records_is_unverified_not_closed(self) -> None:
        """Should be unreachable — every job has at least one link. If it
        happens, the honest answer is that we know nothing, not that it closed."""
        assert _decide([]) is JobStatus.UNVERIFIED

    def test_every_decision_carries_a_reason(self) -> None:
        """I4's spirit: no bare verdict. The reason reaches job_status_events
        and is the only thing a human reads when asking why a job vanished."""
        for records, current in (
            ([_seen(0)], JobStatus.OPEN),
            ([_seen(1, misses=3)], JobStatus.OPEN),
            ([_seen(7, misses=3)], JobStatus.POSSIBLY_STALE),
            ([], JobStatus.OPEN),
        ):
            decision = decide_job_status(
                current=current, records=records, board_last_success_at=NOW, now=NOW
            )
            assert decision.reason
            assert len(decision.reason) <= 200


class TestThresholdsAreTheOnesTheAdrFixed:
    """If these change, ADR 0009 is out of date and must be superseded first."""

    def test_thresholds(self) -> None:
        assert MISSES_BEFORE_STALE == 3
        assert DAYS_ABSENT_BEFORE_CLOSED == 7
        assert DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED == 14


def test_decision_is_deterministic() -> None:
    records = [_seen(7, misses=3)]
    first = decide_job_status(
        current=JobStatus.OPEN, records=records, board_last_success_at=NOW, now=NOW
    )
    second = decide_job_status(
        current=JobStatus.OPEN, records=records, board_last_success_at=NOW, now=NOW
    )
    assert first == second
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/test_freshness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.domain.freshness'`.

- [ ] **Step 3: Write the module**

```python
# services/api/nightshift/domain/freshness.py
"""The closure state machine (PRODUCT-SPEC §7.4, ADR 0009).

Pure by design: this module takes observations and returns a verdict. It never
touches a session, so every branch of a state machine with four states and two
thresholds is cheap to assert, and the database applier in
``domain/ingestion.py`` stays a translation layer with no policy in it.

Invariant I3 is the reason for the shape. The function is only ever called with
observations from a board that *answered* — a failed fetch produces no
observation at all, so there is no code path here that can close a job because
a request failed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from nightshift.db.base import JobStatus

# ADR 0009. Both closure conditions are required, and they are a pair on
# purpose: a miss count alone stops meaning anything once ADR 0007 gives
# different boards different poll rates, and elapsed time alone would close a
# job on a board nobody re-checked.
MISSES_BEFORE_STALE = 3
DAYS_ABSENT_BEFORE_CLOSED = 7
DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED = 14

# Bumped whenever a threshold or a transition changes, so a change in closure
# behaviour is attributable rather than mysterious.
CLOSURE_RULESET_VERSION = "1"


@dataclass(frozen=True, slots=True)
class RecordObservation:
    """What one source record looked like after the most recent poll."""

    consecutive_misses: int
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class ClosureDecision:
    """A verdict and the sentence that explains it.

    The reason is stored on ``job_status_events.reason`` and is what a human
    reads when asking why a job disappeared, so it is written for that reader.
    """

    status: JobStatus
    reason: str


def decide_job_status(
    *,
    current: JobStatus,
    records: Sequence[RecordObservation],
    board_last_success_at: datetime | None,
    now: datetime,
) -> ClosureDecision:
    """Decide what state a canonical job should be in.

    Order matters and each step depends on the one above:

    1. If the board has not answered in a fortnight we know nothing about the
       job, whatever its counters say.
    2. If any source still lists it, it is open — a job described by two boards
       is gone only when both stop listing it.
    3. Absence closes it only when both ADR 0009 conditions hold.
    """
    unverified_after = timedelta(days=DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED)
    if board_last_success_at is None or now - board_last_success_at >= unverified_after:
        return ClosureDecision(
            JobStatus.UNVERIFIED,
            f"no successful poll of this board in {DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED} days",
        )

    if not records:
        # Unreachable in practice: every job reaches at least one source record
        # through job_source_links. If it ever happens, "we know nothing" is the
        # honest answer and closing would be a fabrication.
        return ClosureDecision(JobStatus.UNVERIFIED, "job has no source records")

    if any(record.consecutive_misses == 0 for record in records):
        if current is JobStatus.CLOSED:
            return ClosureDecision(JobStatus.OPEN, "listed again after being closed")
        return ClosureDecision(JobStatus.OPEN, "listed at the most recent poll")

    misses = min(record.consecutive_misses for record in records)
    last_seen = max(record.last_seen_at for record in records)
    absent_for = now - last_seen

    if misses < MISSES_BEFORE_STALE:
        return ClosureDecision(
            JobStatus.OPEN,
            f"missing from {misses} poll(s), fewer than the {MISSES_BEFORE_STALE} required",
        )

    if absent_for >= timedelta(days=DAYS_ABSENT_BEFORE_CLOSED):
        return ClosureDecision(
            JobStatus.CLOSED,
            f"missing from {misses} consecutive polls over {absent_for.days} days",
        )

    return ClosureDecision(
        JobStatus.POSSIBLY_STALE,
        f"missing from {misses} consecutive polls, but only {absent_for.days} days "
        f"since it was last listed ({DAYS_ABSENT_BEFORE_CLOSED} required to close)",
    )
```

- [ ] **Step 4: Run the tests**

Run: `cd services/api && pytest tests/test_freshness.py -v`
Expected: PASS, all cases.

- [ ] **Step 5: Prove the tests can fail**

Non-vacuity, per CLAUDE.md §7. Temporarily change
`DAYS_ABSENT_BEFORE_CLOSED` to `6` and confirm
`test_three_misses_and_six_days_is_still_only_stale` and `test_thresholds`
both fail. Then remove the `board_last_success_at` guard and confirm
`test_unverified_never_becomes_closed_however_long_it_lasts` fails. Restore
both, and record the two results in the commit message.

- [ ] **Step 6: `make check`, then commit**

```bash
make check
git add services/api/nightshift/domain/freshness.py services/api/tests/test_freshness.py
git commit -m "feat(freshness): add the closure decision function

ADR 0009: three misses AND seven days, both required. possibly_stale and
unverified are kept apart because one is evidence about the job and the
other only about the source, and only the first can reach closed.

Non-vacuity: shortening the window to 6 days fails two tests; removing the
board-silence guard fails the 'an outage never closes' test.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Apply freshness in the pipeline

**Files:**
- Modify: `services/api/nightshift/domain/ingestion.py`
- Create: `services/api/tests/test_closure_pipeline.py`

**Interfaces:**
- Consumes: `decide_job_status`, `RecordObservation` from Task 2;
  `JobStatusEvent` from Task 1.
- Produces: `apply_freshness(session, *, source, polled_tokens, run, now) -> int`
  returning the number of jobs newly closed. Called by `ingest_boards`.

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/test_closure_pipeline.py
"""Closure against a real database.

The load-bearing test is test_a_failed_board_does_not_increment_a_miss. I3 is
usually stated as 'an outage closes nothing', but the way it actually breaks is
subtler: an outage that quietly increments a miss counter closes jobs three
polls later, and by then nothing in the data says why.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import JobStatus, SourceType
from nightshift.db.models import Job, JobStatusEvent, SourceJobRecord
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from tests.conftest import requires_db

pytestmark = requires_db

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


def _payload() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())


class _StubAdapter:
    """The real adapter with only its network call replaced."""

    def __init__(self, outcome: FetchOutcome) -> None:
        self._inner = LeverAdapter(client=None)
        self._outcome = outcome
        self.source_name = self._inner.source_name
        self.source_type = self._inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef | None = None) -> Any:
        return self._inner.normalize_with_board(raw_job, BOARD)


def _outcome(jobs: list[dict[str, Any]], *, ok: bool = True) -> FetchOutcome:
    if not ok:
        return FetchOutcome(board=BOARD, ok=False, http_status=503, error="HTTP 503")
    return FetchOutcome(
        board=BOARD,
        ok=True,
        http_status=200,
        jobs=tuple(
            RawJob(
                source_job_id=str(j["id"]),
                source_company_key="alloy",
                canonical_url=j.get("hostedUrl"),
                payload=j,
            )
            for j in jobs
        ),
    )


async def _poll(session: AsyncSession, outcome: FetchOutcome, now: datetime) -> Any:
    source = await get_or_create_source(
        session, name="lever_closure_test", source_type=SourceType.ATS_LEVER
    )
    return await ingest_boards(session, _StubAdapter(outcome), [BOARD], source=source, now=now)


async def _status_counts(session: AsyncSession) -> dict[JobStatus, int]:
    rows = (
        await session.execute(select(Job.status, func.count()).group_by(Job.status))
    ).all()
    return {status: count for status, count in rows}


async def test_a_job_still_listed_stays_open(db_session: AsyncSession) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    await _poll(db_session, _outcome(_payload()), start + timedelta(days=1))
    assert await _status_counts(db_session) == {JobStatus.OPEN: 9}


async def test_a_failed_board_does_not_increment_a_miss(db_session: AsyncSession) -> None:
    """I3, at the counter rather than at the status.

    A failed fetch that bumps the miss count closes jobs three polls later,
    which looks like a closure rule working correctly and is not.
    """
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)

    for day in range(1, 6):
        await _poll(db_session, _outcome([], ok=False), start + timedelta(days=day))

    misses = (
        (await db_session.execute(select(SourceJobRecord.consecutive_misses))).scalars().all()
    )
    assert set(misses) == {0}
    assert await _status_counts(db_session) == {JobStatus.OPEN: 9}


async def test_an_empty_but_live_board_does_increment(db_session: AsyncSession) -> None:
    """The other side of I3. A live board returning [] is real evidence.

    M1a recorded the plaid empty board as its own fixture precisely so this
    branch is distinguishable from the 404 one.
    """
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    await _poll(db_session, _outcome([]), start + timedelta(days=1))

    misses = (
        (await db_session.execute(select(SourceJobRecord.consecutive_misses))).scalars().all()
    )
    assert set(misses) == {1}


async def test_three_misses_makes_a_job_stale_not_closed(db_session: AsyncSession) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    for day in (1, 2, 3):
        await _poll(db_session, _outcome([]), start + timedelta(days=day))
    assert await _status_counts(db_session) == {JobStatus.POSSIBLY_STALE: 9}


async def test_seven_days_of_absence_closes(db_session: AsyncSession) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    for day in (1, 2, 3, 7):
        await _poll(db_session, _outcome([]), start + timedelta(days=day))

    assert await _status_counts(db_session) == {JobStatus.CLOSED: 9}
    closed = (
        (await db_session.execute(select(Job).where(Job.status == JobStatus.CLOSED)))
        .scalars()
        .all()
    )
    for job in closed:
        assert job.closed_at is not None


async def test_closing_is_recorded_in_the_run(db_session: AsyncSession) -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    for day in (1, 2, 3):
        await _poll(db_session, _outcome([]), start + timedelta(days=day))
    run, stats = await _poll(db_session, _outcome([]), start + timedelta(days=7))
    assert stats.closed == 9
    assert run.records_closed == 9


async def test_a_reappearing_job_reopens_and_keeps_its_history(
    db_session: AsyncSession,
) -> None:
    """Reposts are ordinary. Refusing to reopen would leave the system
    permanently wrong about a job that is demonstrably available."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    for day in (1, 2, 3, 7):
        await _poll(db_session, _outcome([]), start + timedelta(days=day))
    await _poll(db_session, _outcome(_payload()), start + timedelta(days=8))

    assert await _status_counts(db_session) == {JobStatus.OPEN: 9}
    reopened = (await db_session.execute(select(Job))).scalars().all()
    for job in reopened:
        assert job.closed_at is None

    # The closure is still on the record even though the column that showed it
    # has been reset. This is the entire reason job_status_events exists.
    closures = (
        await db_session.execute(
            select(func.count())
            .select_from(JobStatusEvent)
            .where(JobStatusEvent.to_status == JobStatus.CLOSED)
        )
    ).scalar_one()
    assert closures == 9


async def test_every_transition_writes_exactly_one_event(db_session: AsyncSession) -> None:
    """No event on a no-op poll: a job that was open and is still open has not
    transitioned, and writing a row per poll would bury the real ones."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
    await _poll(db_session, _outcome(_payload()), start)
    before = (
        await db_session.execute(select(func.count()).select_from(JobStatusEvent))
    ).scalar_one()

    await _poll(db_session, _outcome(_payload()), start + timedelta(days=1))
    after = (
        await db_session.execute(select(func.count()).select_from(JobStatusEvent))
    ).scalar_one()
    assert after == before
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/test_closure_pipeline.py -v`
Expected: FAIL — several tests fail on status counts, because nothing closes
anything yet. `test_a_failed_board_does_not_increment_a_miss` should already
PASS: M0 never increments, and this test exists to keep it that way.

- [ ] **Step 3: Add the applier to `domain/ingestion.py`**

Add the imports:

```python
from nightshift.db.models import JobStatusEvent
from nightshift.domain.freshness import RecordObservation, decide_job_status
```

Then, after `_canonical_job_for`:

```python
async def apply_freshness(
    session: AsyncSession,
    *,
    source: Source,
    polled_tokens: Sequence[str],
    run: IngestionRun,
    now: datetime,
) -> int:
    """Age every record on the boards that answered, then re-decide their jobs.

    ``polled_tokens`` carries only the boards whose fetch succeeded. That
    argument is where I3 lives in this function: a board that failed is not in
    the list, so none of its records are aged and none of its jobs are
    re-decided. There is deliberately no parameter by which a caller could ask
    for a failed board to be processed anyway.

    Returns the number of jobs that newly became ``closed``.
    """
    if not polled_tokens:
        return 0

    # Records on a polled board that this run did not touch are absent.
    stale_records = (
        (
            await session.execute(
                select(SourceJobRecord).where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key.in_(list(polled_tokens)),
                    SourceJobRecord.last_seen_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    for record in stale_records:
        record.consecutive_misses += 1
        record.source_status = SourceStatus.MISSING
    await session.flush()

    # Re-decide every job reachable from this source's polled boards, not only
    # the missing ones: a job whose second source vanished has not changed
    # itself but its verdict may have.
    jobs = (
        (
            await session.execute(
                select(Job)
                .join(JobSourceLink, JobSourceLink.job_id == Job.id)
                .join(
                    SourceJobRecord,
                    SourceJobRecord.id == JobSourceLink.source_job_record_id,
                )
                .where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key.in_(list(polled_tokens)),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    closed = 0
    for job in jobs:
        observations = (
            (
                await session.execute(
                    select(
                        SourceJobRecord.consecutive_misses,
                        SourceJobRecord.last_seen_at,
                    )
                    .join(
                        JobSourceLink,
                        JobSourceLink.source_job_record_id == SourceJobRecord.id,
                    )
                    .where(JobSourceLink.job_id == job.id)
                )
            )
            .all()
        )
        decision = decide_job_status(
            current=job.status,
            records=[
                RecordObservation(consecutive_misses=misses, last_seen_at=last_seen)
                for misses, last_seen in observations
            ],
            board_last_success_at=source.last_success_at,
            now=now,
        )
        if decision.status is job.status:
            continue

        session.add(
            JobStatusEvent(
                job_id=job.id,
                from_status=job.status,
                to_status=decision.status,
                reason=decision.reason,
                ingestion_run_id=run.id,
                observed_misses=(
                    min((m for m, _ in observations), default=None) if observations else None
                ),
            )
        )
        job.status = decision.status
        # The check constraint closed_at_matches_status pairs these two, so a
        # buggy transition is a database error rather than a silent one.
        job.closed_at = now if decision.status is JobStatus.CLOSED else None
        if decision.status is JobStatus.CLOSED:
            closed += 1

    await session.flush()
    return closed
```

- [ ] **Step 4: Call it from `ingest_boards`**

`source.last_success_at` must be set *before* `apply_freshness` reads it, or
the first poll of a brand-new source decides `unverified`. Replace the loop
body's success branch and add the call after the loop:

```python
    for board in boards:
        outcome = await adapter.fetch_board(board)
        if not outcome.ok:
            # I3: we learned nothing. No listing state changes, nothing closes,
            # and crucially no miss counter moves — see apply_freshness.
            stats.boards_failed.append(board.token)
            stats.errors.append(f"{board.ats}:{board.token}: {outcome.error}")
            source.last_failure_at = timestamp
            log.warning("ingest_board_failed", board=board.token, error=outcome.error)
            continue

        stats.boards_ok.append(board.token)
        source.last_success_at = timestamp
        await _persist_outcome(session, adapter, outcome, source=source, stats=stats, now=timestamp)

    # Only the boards that answered. A failed board contributes no evidence and
    # is not in this list.
    stats.closed = await apply_freshness(
        session, source=source, polled_tokens=stats.boards_ok, run=run, now=timestamp
    )
```

No enum work is needed. `SourceStatus` already has `ACTIVE`, `MISSING` and
`REMOVED` (`nightshift/db/base.py:104-109`), checked while writing this plan.
`MISSING` is the value `apply_freshness` sets above. `REMOVED` stays unused
until M1d can fetch a posting's own endpoint and be told so directly — that is
a stronger claim than absence from a listing and it deliberately has no code
path yet.

- [ ] **Step 5: Update the `IngestionStats.closed` comment**

The comment at `domain/ingestion.py:71-72` says closure is an M1 deliverable
and the counter stays zero. That is now false. Replace with:

```python
    # Jobs that transitioned to `closed` during this run (ADR 0009). Only ever
    # non-zero for boards that answered.
    closed: int = 0
```

- [ ] **Step 6: Run the tests**

Run: `cd services/api && pytest tests/test_closure_pipeline.py tests/test_ingestion.py -v`
Expected: PASS. `test_ingestion.py` must still pass unchanged — in particular
`test_a_failed_board_closes_nothing`, which is the M1 acceptance criterion.

- [ ] **Step 7: Prove I3 can fail**

Change `polled_tokens=stats.boards_ok` to
`polled_tokens=[b.token for b in boards]` — the bug of processing every board
including the failed ones — and confirm
`test_a_failed_board_does_not_increment_a_miss` **fails**. Restore it. Record
the result in the commit message.

- [ ] **Step 8: `make check`, then commit**

```bash
make check
git add services/api/nightshift/domain/ingestion.py services/api/tests/test_closure_pipeline.py
git commit -m "feat(ingestion): close jobs that go away, and only those

apply_freshness takes only the boards that answered, so a failed fetch
moves no counter. Non-vacuity: passing every board instead of the
successful ones makes the outage test fail three polls later, which is
exactly the silent version of the bug I3 exists to prevent.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: The dedupe fixture set (RED)

PRODUCT-SPEC §7.5 names seven categories. Per AMENDMENTS A2's precedent, the
fixtures land before the matcher, so one provider's conventions cannot be
encoded as general and so a reviewer can read the expectations separately from
the code that satisfies them.

**Files:**
- Create: `services/api/tests/fixtures/dedupe_pairs.yaml`
- Create: `services/api/tests/test_dedupe.py`

**Interfaces:**
- Produces: the fixture file, read by Tasks 5 and 7.

- [ ] **Step 1: Write the fixture file**

```yaml
# services/api/tests/fixtures/dedupe_pairs.yaml
#
# Labelled pairs for the dedupe evaluation suite (PRODUCT-SPEC §7.5).
#
# `verdict: merge`    these two describe one real-world opening
# `verdict: distinct` these are two different jobs and merging them costs the
#                     user one of them permanently
#
# Cases marked `synthetic: true` were written at the keyboard. The rest are
# derived from the committed board recordings in tests/fixtures/{lever,ashby}.
# Every case names the category from §7.5 it exercises.

cases:
  # --- 1. True duplicates ---------------------------------------------------
  - name: same_posting_seen_twice
    category: true_duplicate
    synthetic: true
    verdict: merge
    expect_reason: same_canonical_url
    a:
      canonical_url: "https://jobs.lever.co/alloy/abc-123"
      normalized_title: "senior software engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "aaa"
    b:
      canonical_url: "https://jobs.lever.co/alloy/abc-123?utm_source=linkedin"
      normalized_title: "senior software engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "bbb"

  - name: cross_posted_identical_text
    category: true_duplicate
    synthetic: true
    verdict: merge
    expect_reason: identical_content
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/1"
      normalized_title: "backend engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "ccc"
    b:
      canonical_url: "https://jobs.lever.co/acme/2"
      normalized_title: "backend engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "ccc"

  # --- 2. Near duplicates ---------------------------------------------------
  # Same role, same office, copy reworded between the two boards. Layers 1 and
  # 2 cannot see this; it is the entire reason ADR 0010 admits similarity.
  - name: cross_posted_reworded_text
    category: near_duplicate
    synthetic: true
    verdict: merge
    expect_reason: similar_description
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/3"
      normalized_title: "backend engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "ddd"
      description: >-
        We are looking for a backend engineer to build and operate the services
        behind our payments platform. You will work in Python and Go, own
        systems end to end, and partner closely with product.
    b:
      canonical_url: "https://jobs.lever.co/acme/4"
      normalized_title: "backend engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "eee"
      description: >-
        Backend engineer wanted to build and run the services powering our
        payments platform. Python and Go, end-to-end ownership, and close
        collaboration with the product team.

  # --- 3. Distinct roles with similar titles --------------------------------
  # The case §7.5 calls out by name: do not merge on title similarity.
  - name: engineer_two_and_three_are_different_jobs
    category: distinct_similar_title
    synthetic: true
    verdict: distinct
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/5"
      normalized_title: "software engineer ii"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "fff"
    b:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/6"
      normalized_title: "software engineer iii"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "ggg"

  - name: frontend_and_backend_share_a_stem
    category: distinct_similar_title
    synthetic: true
    verdict: distinct
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/7"
      normalized_title: "frontend engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "hhh"
    b:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/8"
      normalized_title: "backend engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "iii"

  # --- 4. Reposts -----------------------------------------------------------
  # A genuinely re-published requisition: new source id, new URL, same role,
  # same office, unchanged text. It is one opening and must merge.
  - name: repost_with_a_new_id
    category: repost
    synthetic: true
    verdict: merge
    expect_reason: identical_content
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/9"
      normalized_title: "data engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "jjj"
    b:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/10"
      normalized_title: "data engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "jjj"

  # --- 5. Seasonal internship variations ------------------------------------
  # The blocking rule on employment type. An internship and a full-time role
  # sharing a title are different jobs even when everything else matches.
  - name: internship_never_merges_with_full_time
    category: seasonal_internship
    synthetic: true
    verdict: distinct
    a:
      canonical_url: "https://jobs.ashbyhq.com/ramp/11"
      normalized_title: "software engineer"
      employment_type: internship
      locations: ["new york|new york|"]
      description_hash: "kkk"
    b:
      canonical_url: "https://jobs.ashbyhq.com/ramp/12"
      normalized_title: "software engineer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "kkk"

  - name: summer_and_winter_internships_are_different_jobs
    category: seasonal_internship
    synthetic: true
    verdict: distinct
    a:
      canonical_url: "https://jobs.ashbyhq.com/ramp/13"
      normalized_title: "software engineer intern summer 2027"
      employment_type: internship
      locations: ["new york|new york|"]
      description_hash: "lll"
    b:
      canonical_url: "https://jobs.ashbyhq.com/ramp/14"
      normalized_title: "software engineer intern winter 2027"
      employment_type: internship
      locations: ["new york|new york|"]
      description_hash: "mmm"

  # --- 6. Jobs in multiple locations ----------------------------------------
  # M0's dedupe note: keep multi-location roles distinct. Two postings of the
  # same title in two cities are two openings.
  - name: same_title_different_cities_stay_separate
    category: multi_location
    synthetic: true
    verdict: distinct
    a:
      canonical_url: "https://jobs.lever.co/alloy/15"
      normalized_title: "account executive"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "nnn"
    b:
      canonical_url: "https://jobs.lever.co/alloy/16"
      normalized_title: "account executive"
      employment_type: full_time
      locations: ["denver|colorado|"]
      description_hash: "nnn"

  # One shared location out of several is enough: a role open in NYC and
  # Denver, cross-posted, is still one role.
  - name: overlapping_location_sets_merge
    category: multi_location
    synthetic: true
    verdict: merge
    expect_reason: identical_content
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/17"
      normalized_title: "solutions architect"
      employment_type: full_time
      locations: ["new york|new york|", "denver|colorado|"]
      description_hash: "ooo"
    b:
      canonical_url: "https://jobs.lever.co/acme/18"
      normalized_title: "solutions architect"
      employment_type: full_time
      locations: ["new york|new york|", "austin|texas|"]
      description_hash: "ooo"

  # --- 7. Jobs with modified descriptions -----------------------------------
  # Same posting, one paragraph edited. The hash differs; it is still one job.
  - name: edited_description_still_merges
    category: modified_description
    synthetic: true
    verdict: merge
    expect_reason: similar_description
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/19"
      normalized_title: "product designer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "ppp"
      description: >-
        Product designer for our core experience. You will own flows end to
        end, from research through high-fidelity design, and work daily with
        engineers. Five years of experience with complex web products.
    b:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/20"
      normalized_title: "product designer"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "qqq"
      description: >-
        Product designer for our core experience. You will own flows end to
        end, from research through high-fidelity design, and work daily with
        engineers. Five years of experience with complex web products. This
        role reports to the Head of Design and is hybrid, three days in office.

  # A rewrite that is not the same job: same title and office, but the actual
  # role changed. This is the pair that must not merge however high the
  # similarity score gets, and it is the reason the threshold is derived from
  # this file rather than chosen.
  - name: same_title_genuinely_different_role
    category: modified_description
    synthetic: true
    verdict: distinct
    a:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/21"
      normalized_title: "engineering manager"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "rrr"
      description: >-
        Engineering manager for our infrastructure group. You will lead a team
        of eight, own reliability and cost, and be responsible for the
        roadmap of our compute platform.
    b:
      canonical_url: "https://boards.greenhouse.io/acme/jobs/22"
      normalized_title: "engineering manager"
      employment_type: full_time
      locations: ["new york|new york|"]
      description_hash: "sss"
      description: >-
        Engineering manager for growth marketing engineering. You will lead a
        team of four, own the experimentation platform, and partner with
        marketing on acquisition funnels.
```

- [ ] **Step 2: Write the test that drives off it**

```python
# services/api/tests/test_dedupe.py
"""The dedupe evaluation suite (PRODUCT-SPEC §7.5, ADR 0010).

Fixture-driven, and the fixture file is the specification. A merge the rules
get wrong in the `distinct` direction removes a real opening from a user's
view and they never learn it existed, so `distinct` cases are the ones that
matter most here even though they look like the boring half.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nightshift.db.base import EmploymentType
from nightshift.domain.dedupe import DedupeCandidate, compare

FIXTURE = Path(__file__).parent / "fixtures" / "dedupe_pairs.yaml"


def _cases() -> list[dict[str, Any]]:
    return list(yaml.safe_load(FIXTURE.read_text())["cases"])


def _candidate(spec: dict[str, Any], *, company: str = "acme") -> DedupeCandidate:
    return DedupeCandidate(
        company_key=company,
        canonical_url=spec.get("canonical_url"),
        normalized_title=spec["normalized_title"],
        employment_type=EmploymentType(spec["employment_type"]),
        location_keys=frozenset(spec.get("locations", [])),
        description_hash=spec["description_hash"],
        description=spec.get("description"),
        embedding=None,
    )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_labelled_pair_gets_the_expected_verdict(case: dict[str, Any]) -> None:
    verdict = compare(_candidate(case["a"]), _candidate(case["b"]))
    expected_merge = case["verdict"] == "merge"
    assert verdict.merge is expected_merge, (
        f"{case['name']} ({case['category']}): expected {case['verdict']}, "
        f"got merge={verdict.merge} reason={verdict.reason!r}"
    )
    if expected_merge and "expect_reason" in case:
        assert verdict.reason == case["expect_reason"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_comparison_is_symmetric(case: dict[str, Any]) -> None:
    """compare(a, b) and compare(b, a) must agree.

    An asymmetric matcher makes merges depend on which posting was ingested
    first, and the same board polled twice would produce different canonical
    jobs.
    """
    a, b = _candidate(case["a"]), _candidate(case["b"])
    assert compare(a, b).merge == compare(b, a).merge


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_nothing_merges_across_companies(case: dict[str, Any]) -> None:
    """The blocking rule, asserted on every pair in the file.

    Candidate generation already blocks by company, so this is structurally
    unreachable today. It is asserted anyway because a future change to
    candidate generation must not be able to quietly enable it.
    """
    a = _candidate(case["a"], company="acme")
    b = _candidate(case["b"], company="globex")
    assert compare(a, b).merge is False


def test_every_seven_categories_is_represented() -> None:
    """A suite missing a category passes while proving nothing about it."""
    categories = {case["category"] for case in _cases()}
    assert categories == {
        "true_duplicate",
        "near_duplicate",
        "distinct_similar_title",
        "repost",
        "seasonal_internship",
        "multi_location",
        "modified_description",
    }


def test_the_suite_contains_both_verdicts_in_useful_numbers() -> None:
    """A file of nothing but `merge` cases is satisfied by `return True`."""
    verdicts = [case["verdict"] for case in _cases()]
    assert verdicts.count("merge") >= 4
    assert verdicts.count("distinct") >= 4


def test_every_merge_verdict_carries_a_reason() -> None:
    """I4's spirit: the reason is what reaches job_source_links.link_reason,
    and a merge nobody can explain is a merge nobody can review."""
    for case in _cases():
        verdict = compare(_candidate(case["a"]), _candidate(case["b"]))
        if verdict.merge:
            assert verdict.reason
            assert 0.0 < verdict.confidence <= 1.0
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd services/api && pytest tests/test_dedupe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.domain.dedupe'`.

- [ ] **Step 4: Commit the red fixtures**

Committing red is deliberate, per A2's precedent in M1a Task 3.

```bash
git add services/api/tests/fixtures/dedupe_pairs.yaml services/api/tests/test_dedupe.py
git commit -m "test(dedupe): add the labelled evaluation fixture set ahead of the matcher

All seven PRODUCT-SPEC 7.5 categories, both verdicts. The distinct cases
are the load-bearing half: a wrong merge deletes a real opening from the
user's view and they never learn it existed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Deterministic dedupe layers (GREEN 1)

Layers 1 and 2, plus all three blocking rules. Similarity is Task 7; the
`near_duplicate`, `similar_description` and `modified_description`-merge cases
stay red until then.

**Files:**
- Create: `services/api/nightshift/domain/dedupe.py`

**Interfaces:**
- Consumes: the fixture set from Task 4.
- Produces:
  - `DEDUPE_RULESET_VERSION: str`
  - `DedupeCandidate` — frozen dataclass, fields exactly as used in Task 4's
    `_candidate` helper: `company_key: str`, `canonical_url: str | None`,
    `normalized_title: str`, `employment_type: EmploymentType`,
    `location_keys: frozenset[str]`, `description_hash: str`,
    `description: str | None`, `embedding: tuple[float, ...] | None`
  - `DedupeVerdict(merge: bool, reason: str, confidence: float)`
  - `compare(a: DedupeCandidate, b: DedupeCandidate) -> DedupeVerdict`
  - `normalize_url(url: str | None) -> str | None`
  - `location_key(city: str | None, state: str | None, country: str | None) -> str`
  - Consumed by Tasks 7 and 8.

- [ ] **Step 1: Write the module**

```python
# services/api/nightshift/domain/dedupe.py
"""Layered deduplication (PRODUCT-SPEC §7.5, ADR 0010).

Pure: this module compares two candidates and returns a verdict. It performs no
I/O and holds no session, so the whole evaluation suite runs in milliseconds
and the database applier stays a translation layer.

The layers are ordered strongest-first and the first that fires decides. The
asymmetry that shapes every rule here: a missed merge shows a user the same job
twice, which is obvious and self-correcting; a wrong merge deletes a real
opening from their view and they never learn it existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from nightshift.db.base import EmploymentType

# Bumped whenever a layer, a threshold or a blocking rule changes. Stored on
# every merge event, so a change in merge behaviour is attributable.
DEDUPE_RULESET_VERSION = "1"

# Tracking parameters carry no identity. Everything else in the query string is
# kept: some boards identify the posting there, and stripping the whole query
# would merge every job on such a board into one.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gh_src",
        "gh_jid",
        "ref",
        "source",
        "src",
        "lever-source",
        "lever-origin",
    }
)


@dataclass(frozen=True, slots=True)
class DedupeCandidate:
    """One side of a comparison, flattened out of the ORM.

    ``embedding`` is None until Task 7's embedder has run. A None embedding
    disables layer 3 for that pair rather than failing it — an unembedded job
    falls back to the deterministic layers, which is the safe direction.
    """

    company_key: str
    canonical_url: str | None
    normalized_title: str
    employment_type: EmploymentType
    location_keys: frozenset[str]
    description_hash: str
    description: str | None = None
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class DedupeVerdict:
    """A decision, the reason for it, and how sure it is.

    ``reason`` becomes ``job_source_links.link_reason`` and
    ``job_merge_events.reason``. It is a short stable token, not prose, because
    it is queried.
    """

    merge: bool
    reason: str
    confidence: float = 0.0


def normalize_url(url: str | None) -> str | None:
    """Strip tracking parameters, lowercase the host, drop a trailing slash.

    Deliberately conservative. The path is untouched and only known tracking
    keys are removed, because a posting identifier hiding in the query string
    is common and dropping it would merge a whole board into one job.
    """
    if not url or not url.strip():
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.casefold() not in _TRACKING_PARAMS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def location_key(city: str | None, state: str | None, country: str | None) -> str:
    """A comparable key for one parsed location.

    Case-folded and pipe-joined rather than hashed, so a failing assertion
    prints something a human can read.
    """
    return "|".join((city or "", state or "", country or "")).casefold()


def _blocked(a: DedupeCandidate, b: DedupeCandidate) -> str | None:
    """Return the name of the blocking rule that refuses this pair, or None.

    These override every layer. Employment type first because it is the one
    that fires on real data: an internship and a full-time role with the same
    title at the same office match on everything else.
    """
    if a.company_key != b.company_key:
        return "different_company"
    if a.employment_type is not b.employment_type:
        return "different_employment_type"
    return None


def compare(a: DedupeCandidate, b: DedupeCandidate) -> DedupeVerdict:
    """Decide whether two candidates describe one real-world opening.

    Symmetric by construction: every comparison below is between values, never
    between "the new one" and "the existing one". An asymmetric matcher would
    make merges depend on ingestion order.
    """
    blocking = _blocked(a, b)
    if blocking is not None and blocking != "different_employment_type":
        return DedupeVerdict(False, blocking)

    # Layer 1 — same posting, literally. This is identity rather than evidence,
    # so it survives the employment-type block: two URLs being equal and the
    # types disagreeing is a source defect, and splitting the job in two would
    # not fix it.
    url_a, url_b = normalize_url(a.canonical_url), normalize_url(b.canonical_url)
    if url_a is not None and url_a == url_b:
        return DedupeVerdict(True, "same_canonical_url", 1.0)

    if blocking is not None:
        return DedupeVerdict(False, blocking)

    if a.normalized_title != b.normalized_title:
        return DedupeVerdict(False, "different_title")

    if not (a.location_keys & b.location_keys):
        # One shared location is enough — a role open in two cities and
        # cross-posted is still one role — but no overlap at all means two
        # openings, per M0's note on keeping multi-location roles distinct.
        return DedupeVerdict(False, "no_shared_location")

    # Layer 2 — byte-identical descriptions under an agreeing title and office.
    if a.description_hash == b.description_hash:
        return DedupeVerdict(True, "identical_content", 0.99)

    # Layer 3 is added in the similarity task and slots in here.
    return DedupeVerdict(False, "no_matching_layer")
```

- [ ] **Step 2: Run the suite**

Run: `cd services/api && pytest tests/test_dedupe.py -v`

Expected: every case passes **except** the three that need similarity —
`cross_posted_reworded_text`, `edited_description_still_merges`, and
`test_every_merge_verdict_carries_a_reason` if it trips on them. Record the
exact failures.

If `internship_never_merges_with_full_time` fails, the employment-type block is
being skipped: check that the two candidates do not also share a normalized
URL, since layer 1 bypasses that block by design.

- [ ] **Step 3: Typecheck**

Run: `cd services/api && mypy nightshift && ruff check nightshift && ruff format --check nightshift`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add services/api/nightshift/domain/dedupe.py
git commit -m "feat(dedupe): add the deterministic layers and the blocking rules

Same URL and identical content, under agreeing company, title and
location. Three fixture cases stay red until similarity lands — they are
the near-duplicates the deterministic layers cannot reach, which is the
whole argument ADR 0010 records for admitting embeddings at all.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Embeddings behind a Protocol

**Files:**
- Create: `services/api/nightshift/domain/embeddings.py`
- Create: `services/api/tests/test_embeddings.py`
- Modify: `services/api/nightshift/config.py`
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces:
  - `EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"`,
    `EMBEDDING_DIMENSION: int = 384`
  - `class Embedder(Protocol): def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]`
  - `FastEmbedEmbedder`, `StubEmbedder`
  - `cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float`
  - Consumed by Tasks 7 and 8.

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/test_embeddings.py
"""The local embedding model (AMENDMENTS A5).

Most of this file uses StubEmbedder, because a unit test should not load a
130 MB ONNX model. Exactly one test exercises the real one, and it is the test
that keeps A5 honest: determinism is what makes the dedupe fixture suite
reproducible, and a stub asserting its own determinism proves nothing.
"""

from __future__ import annotations

import math

import pytest

from nightshift.domain.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    StubEmbedder,
    cosine_similarity,
    real_model_available,
)


def test_cosine_of_identical_vectors_is_one() -> None:
    v = (0.1, 0.2, 0.3)
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)


def test_cosine_of_a_zero_vector_is_zero_not_nan() -> None:
    """A zero vector divides by zero. NaN silently compares false against every
    threshold, which would disable layer 3 without anything reporting it."""
    result = cosine_similarity((0.0, 0.0), (1.0, 1.0))
    assert not math.isnan(result)
    assert result == 0.0


def test_stub_is_deterministic_and_correctly_shaped() -> None:
    stub = StubEmbedder()
    assert stub.embed(["hello"]) == stub.embed(["hello"])
    assert len(stub.embed(["hello"])[0]) == EMBEDDING_DIMENSION


def test_stub_gives_similar_text_a_higher_score_than_unrelated_text() -> None:
    """The stub has to be directionally right or every test using it is a lie
    about what the real model would have decided."""
    stub = StubEmbedder()
    a, b, c = stub.embed(
        [
            "backend engineer python payments platform",
            "backend engineer python payments systems",
            "director of facilities and workplace operations",
        ]
    )
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


@pytest.mark.skipif(
    not real_model_available(),
    reason="embedding model not downloaded — run `make setup`",
)
class TestTheRealModel:
    def test_dimension_matches_what_the_schema_declares(self) -> None:
        """job_embeddings.embedding is Vector(384). A model that returns a
        different width fails at insert time, in production, at 3am."""
        from nightshift.domain.embeddings import FastEmbedEmbedder

        vectors = FastEmbedEmbedder().embed(["a job description"])
        assert len(vectors[0]) == EMBEDDING_DIMENSION

    def test_is_deterministic(self) -> None:
        """A5's central claim, and the reason a hosted API was rejected: the
        dedupe fixture suite cannot be reproducible without this."""
        from nightshift.domain.embeddings import FastEmbedEmbedder

        embedder = FastEmbedEmbedder()
        text = "Senior backend engineer, Python and Go, New York."
        assert embedder.embed([text]) == embedder.embed([text])

    def test_model_name_is_the_one_a5_specifies(self) -> None:
        assert EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.domain.embeddings'`.

- [ ] **Step 3: Write the module**

```python
# services/api/nightshift/domain/embeddings.py
"""Local, offline, deterministic embeddings (AMENDMENTS A5).

`bge-small-en-v1.5` via fastembed: ONNX on CPU, ~130 MB, no key, no network at
run time. A5 rejects a hosted API for a reason that matters more than cost —
the dedupe fixture suite has to be reproducible, and a remote model that is
silently retrained makes it not.

The model is fetched once by `make setup` into a cache directory outside the
repository. Nothing here reaches the network during a test or a request, and
`OUTBOUND_HTTP_ENABLED` is not consulted because this module never uses httpx.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)

# A5 fixes both. They are stored on every job_embeddings row so that replacing
# the model is a backfill rather than a mystery.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384


def _cache_dir() -> Path:
    return Path(
        os.environ.get("FASTEMBED_CACHE_PATH")
        or Path.home() / ".cache" / "nightshift" / "fastembed"
    )


def real_model_available() -> bool:
    """True when the model has been downloaded.

    Used to skip the real-model tests rather than fail them. A suite that
    cannot run without a 130 MB download is a suite people stop running; one
    that silently passes without it is worse, so the skip says which it is.
    """
    cache = _cache_dir()
    if not cache.exists():
        return False
    return any(cache.rglob("*.onnx"))


class Embedder(Protocol):
    """Anything that turns text into vectors of ``EMBEDDING_DIMENSION`` floats."""

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


class FastEmbedEmbedder:
    """The real model. Loaded lazily, because importing it costs ~2 s."""

    def __init__(self) -> None:
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            log.info("embedding_model_loading", model=EMBEDDING_MODEL_NAME)
            self._model = TextEmbedding(
                model_name=EMBEDDING_MODEL_NAME, cache_dir=str(_cache_dir())
            )
        return self._model

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        model = self._load()
        return [tuple(float(x) for x in vector) for vector in model.embed(list(texts))]


class StubEmbedder:
    """A deterministic test double. **Not** the product (I7).

    Hashes character trigrams into a fixed-width vector. That is not semantic
    similarity, but it is directionally right — texts sharing many trigrams
    score higher than texts sharing few — which is enough for tests whose
    subject is the *plumbing* around embeddings rather than their quality.
    Anything asserting a quality claim uses the real model and is skipped when
    it is absent.
    """

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            buckets = [0.0] * EMBEDDING_DIMENSION
            cleaned = " ".join((text or "").lower().split())
            for i in range(max(len(cleaned) - 2, 0)):
                trigram = cleaned[i : i + 3]
                digest = hashlib.sha256(trigram.encode()).digest()
                buckets[int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION] += 1.0
            norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
            vectors.append(tuple(v / norm for v in buckets))
        return vectors


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, with a zero vector scoring 0 rather than NaN.

    NaN compares false against every threshold, so an empty description would
    silently switch off layer 3 with nothing reporting it.
    """
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@lru_cache(maxsize=1)
def default_embedder() -> Embedder:
    """One process-wide model instance. Loading it per call would dominate."""
    return FastEmbedEmbedder()
```

- [ ] **Step 4: Make `make setup` fetch the model**

Add to the `Makefile`, and call it from `setup`:

```make
model: ## Download the embedding model (AMENDMENTS A5). ~130 MB, once.
	@$(PY) -c "from nightshift.domain.embeddings import FastEmbedEmbedder; \
	           FastEmbedEmbedder().embed(['warm the cache']); \
	           print('==> embedding model ready')"
```

Wire it into `setup` **after** the Python dependencies are installed. Keep it
in `setup` rather than in the test targets: unlike Playwright's browser, this
is needed by the product itself, not only by the tests.

- [ ] **Step 5: Cache it in CI**

In `.github/workflows/ci.yml`, in the `python` job before the test step:

```yaml
      - name: Cache the embedding model
        uses: actions/cache@v4
        with:
          path: ~/.cache/nightshift/fastembed
          key: fastembed-bge-small-en-v1.5-v1

      - name: Fetch the embedding model
        run: make model
```

- [ ] **Step 6: Run the tests**

```bash
make model
cd services/api && pytest tests/test_embeddings.py -v
```

Expected: PASS, including `TestTheRealModel` — three tests that would have
skipped before `make model` ran. Confirm they did **not** skip; a skipped
real-model test is exactly the I7 failure this file is written against.

- [ ] **Step 7: `make check`, then commit**

```bash
make check
git add services/api/nightshift/domain/embeddings.py services/api/tests/test_embeddings.py \
        Makefile .github/workflows/ci.yml
git commit -m "feat(embeddings): add the local bge-small-en-v1.5 embedder

AMENDMENTS A5. StubEmbedder is a labelled test double; one test class
exercises the real model and asserts the two things A5 actually claims —
384 dimensions matching the schema, and byte-identical output twice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Similarity as layer 3, with a derived threshold

**Files:**
- Modify: `services/api/nightshift/domain/dedupe.py`
- Modify: `services/api/tests/test_dedupe.py`
- Create: `services/api/scripts/derive_dedupe_threshold.py`

**Interfaces:**
- Consumes: `cosine_similarity`, `default_embedder` from Task 6;
  `DedupeCandidate.embedding` from Task 5.
- Produces: `SIMILARITY_THRESHOLD: float` and layer 3 inside `compare`.

- [ ] **Step 1: Write the threshold derivation script**

The threshold is measured, not chosen. This script prints the separation and
is committed so the number can be re-derived when the fixture set grows.

```python
# services/api/scripts/derive_dedupe_threshold.py
"""Derive the layer-3 similarity threshold from the labelled fixture set.

ADR 0010: the threshold is not chosen by taste. This prints every labelled
pair's cosine similarity under the real model, then reports the widest gap
between the merge cases and the distinct cases that reach layer 3.

Run: `cd services/api && python scripts/derive_dedupe_threshold.py`
"""

from __future__ import annotations

from pathlib import Path

import yaml

from nightshift.domain.embeddings import cosine_similarity, default_embedder

FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "dedupe_pairs.yaml"


def main() -> None:
    cases = yaml.safe_load(FIXTURE.read_text())["cases"]
    embedder = default_embedder()

    scored: list[tuple[float, str, str]] = []
    for case in cases:
        a, b = case["a"], case["b"]
        if not a.get("description") or not b.get("description"):
            continue
        va, vb = embedder.embed([a["description"], b["description"]])
        scored.append((cosine_similarity(va, vb), case["verdict"], case["name"]))

    scored.sort(reverse=True)
    print(f"{'similarity':>10}  {'verdict':<9}  case")
    for score, verdict, name in scored:
        print(f"{score:>10.4f}  {verdict:<9}  {name}")

    merges = [s for s, v, _ in scored if v == "merge"]
    distincts = [s for s, v, _ in scored if v == "distinct"]
    if not merges or not distincts:
        print("\nnot enough labelled pairs with descriptions to derive a threshold")
        return

    lowest_merge, highest_distinct = min(merges), max(distincts)
    print(f"\nlowest  merge    : {lowest_merge:.4f}")
    print(f"highest distinct : {highest_distinct:.4f}")
    if lowest_merge <= highest_distinct:
        print(
            "\nNO SEPARATING THRESHOLD EXISTS.\n"
            "Do not pick a number that splits the difference — record this and "
            "either strengthen the deterministic layers or accept that these "
            "pairs are not separable by description similarity alone."
        )
        return
    print(f"\nany threshold in ({highest_distinct:.4f}, {lowest_merge:.4f}] separates the set")
    print(f"suggested (midpoint): {(lowest_merge + highest_distinct) / 2:.2f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and record the output**

```bash
cd services/api && python scripts/derive_dedupe_threshold.py
```

**Write the printed table into the commit message.** If it reports that no
separating threshold exists, stop and record that finding in
`docs/PROGRESS.md` and `docs/QUESTIONS.md` rather than picking a number — a
threshold that does not separate the labelled set is a threshold with no
evidence behind it, and ADR 0010 would need superseding.

- [ ] **Step 3: Add layer 3**

In `dedupe.py`, add the import and the constant:

```python
from nightshift.domain.embeddings import cosine_similarity

# Derived from tests/fixtures/dedupe_pairs.yaml by
# scripts/derive_dedupe_threshold.py, not chosen. Re-derive when the fixture
# set grows, and bump DEDUPE_RULESET_VERSION when this changes.
SIMILARITY_THRESHOLD = 0.90  # replace with the value step 2 printed
```

Then replace the final return of `compare`:

```python
    # Layer 3 — ADR 0010. Reachable only once company, employment type, title
    # and location already agree, so similarity breaks a tie and never makes a
    # match on its own. A pair that disagrees on any of the above never gets
    # here however high it would have scored.
    if a.embedding is not None and b.embedding is not None:
        similarity = cosine_similarity(a.embedding, b.embedding)
        if similarity >= SIMILARITY_THRESHOLD:
            # Confidence is the similarity itself, capped below the 0.99 that
            # layer 2 earns by comparing bytes. A number is not a reason, and
            # this layer must never outrank one that compared actual content.
            return DedupeVerdict(True, "similar_description", min(similarity, 0.95))
        return DedupeVerdict(False, "below_similarity_threshold")

    return DedupeVerdict(False, "no_matching_layer")
```

- [ ] **Step 4: Give the fixture test real embeddings**

In `tests/test_dedupe.py`, change `_candidate` so a case carrying a
`description` is embedded, and add the guard that keeps the suite honest:

```python
from nightshift.domain.embeddings import (
    StubEmbedder,
    default_embedder,
    real_model_available,
)


def _embedder() -> Any:
    """The real model when it is present, the stub otherwise.

    The verdict assertions must hold under the real model — that is what the
    threshold was derived against. Under the stub they are skipped rather than
    asserted, because a trigram hash is not a semantic model and a green run
    against it would be evidence of nothing.
    """
    return default_embedder() if real_model_available() else StubEmbedder()


def _candidate(spec: dict[str, Any], *, company: str = "acme") -> DedupeCandidate:
    embedding = None
    description = spec.get("description")
    if description:
        embedding = _embedder().embed([description])[0]
    return DedupeCandidate(
        company_key=company,
        canonical_url=spec.get("canonical_url"),
        normalized_title=spec["normalized_title"],
        employment_type=EmploymentType(spec["employment_type"]),
        location_keys=frozenset(spec.get("locations", [])),
        description_hash=spec["description_hash"],
        description=description,
        embedding=embedding,
    )
```

And mark the verdict test so similarity-dependent cases require the real model:

```python
@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_labelled_pair_gets_the_expected_verdict(case: dict[str, Any]) -> None:
    needs_model = bool(case["a"].get("description") and case["b"].get("description"))
    if needs_model and not real_model_available():
        pytest.skip("embedding model not downloaded — run `make setup`")
    verdict = compare(_candidate(case["a"]), _candidate(case["b"]))
    expected_merge = case["verdict"] == "merge"
    assert verdict.merge is expected_merge, (
        f"{case['name']} ({case['category']}): expected {case['verdict']}, "
        f"got merge={verdict.merge} reason={verdict.reason!r}"
    )
    if expected_merge and "expect_reason" in case:
        assert verdict.reason == case["expect_reason"]
```

- [ ] **Step 5: Run the whole suite**

Run: `cd services/api && pytest tests/test_dedupe.py -v`
Expected: PASS, every case, with none skipped (the model is present after
Task 6). Confirm zero skips — a skipped similarity case is the one that
matters most.

- [ ] **Step 6: Prove similarity cannot merge on its own**

Add this test to `test_dedupe.py` and confirm it passes:

```python
def test_similarity_cannot_merge_without_the_deterministic_agreement() -> None:
    """ADR 0010's central constraint, asserted rather than trusted.

    Two postings with byte-identical descriptions — similarity 1.0 — must
    still not merge when their titles disagree. If this ever fails, the layer
    ordering has been inverted and a number is deciding on its own.
    """
    text = "Backend engineer building payment systems in Python and Go."
    embedding = _embedder().embed([text])[0]
    base = {
        "company_key": "acme",
        "employment_type": EmploymentType.FULL_TIME,
        "location_keys": frozenset({"new york|new york|"}),
        "description": text,
        "embedding": embedding,
    }
    a = DedupeCandidate(
        canonical_url="https://boards.greenhouse.io/acme/jobs/90",
        normalized_title="backend engineer",
        description_hash="x",
        **base,
    )
    b = DedupeCandidate(
        canonical_url="https://boards.greenhouse.io/acme/jobs/91",
        normalized_title="staff backend engineer",
        description_hash="y",
        **base,
    )
    verdict = compare(a, b)
    assert verdict.merge is False
    assert verdict.reason == "different_title"
```

- [ ] **Step 7: `make check`, then commit**

```bash
make check
git add services/api/nightshift/domain/dedupe.py services/api/tests/test_dedupe.py \
        services/api/scripts/derive_dedupe_threshold.py
git commit -m "feat(dedupe): add similarity as layer 3, with a threshold derived from fixtures

The number comes from scripts/derive_dedupe_threshold.py against the
labelled set, not from taste. Similarity is reachable only once company,
employment type, title and location already agree — asserted directly by
test_similarity_cannot_merge_without_the_deterministic_agreement, where
two identical descriptions under different titles must not merge.

<paste the derivation table here>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Merging in the pipeline

**Files:**
- Modify: `services/api/nightshift/domain/ingestion.py`
- Create: `services/api/tests/test_merge_pipeline.py`

**Interfaces:**
- Consumes: `compare`, `DedupeCandidate`, `location_key`,
  `DEDUPE_RULESET_VERSION` from Tasks 5 and 7; `JobEmbedding`,
  `JobMergeEvent` from Task 1; `default_embedder` from Task 6.
- Produces: `find_duplicate(session, *, company_id, candidate) -> tuple[Job, DedupeVerdict] | None`
  and `merge_jobs(session, *, winner, loser, verdict) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/test_merge_pipeline.py
"""Dedupe against a real database: candidate generation, merging, provenance.

The invariant under test is that a merge never loses a source link. A canonical
job is derived from raw records, so losing an edge does not lose data — it
loses the *path* to it, and a job nobody can trace back to a posting is exactly
what M1's acceptance criterion forbids.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.db.base import EmploymentType, SourceType
from nightshift.db.models import Job, JobMergeEvent, JobSourceLink, SourceJobRecord
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from tests.conftest import requires_db

pytestmark = requires_db

NOW = datetime(2026, 8, 1, tzinfo=UTC)
BOARD = BoardRef(company="Acme", ats="greenhouse", token="acme", nyc_presence=True)


def _posting(job_id: str, *, url: str, title: str, text: str) -> dict[str, Any]:
    """A minimal Greenhouse-shaped posting.

    Hand-built rather than recorded, because these are dedupe scenarios that
    no single real board exhibits. Labelled as such: this dict never claims to
    be a recording and lives in a test, not in tests/fixtures.
    """
    return {
        "id": job_id,
        "title": title,
        "absolute_url": url,
        "content": text,
        "location": {"name": "New York, NY"},
        "metadata": [],
        "updated_at": "2026-08-01T00:00:00Z",
        "first_published": "2026-07-01T00:00:00Z",
    }


class _StubAdapter:
    def __init__(self, postings: list[dict[str, Any]]) -> None:
        from nightshift.adapters.greenhouse import GreenhouseAdapter

        self._inner = GreenhouseAdapter(client=None)
        self._postings = postings
        self.source_name = self._inner.source_name
        self.source_type = self._inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return FetchOutcome(
            board=board,
            ok=True,
            http_status=200,
            jobs=tuple(
                RawJob(
                    source_job_id=str(p["id"]),
                    source_company_key=board.token,
                    canonical_url=p["absolute_url"],
                    payload=p,
                )
                for p in self._postings
            ),
        )

    def normalize(self, raw_job: RawJob, board: BoardRef | None = None) -> Any:
        return self._inner.normalize(raw_job, BOARD)


async def _ingest(session: AsyncSession, postings: list[dict[str, Any]]) -> Any:
    source = await get_or_create_source(
        session, name="gh_merge_test", source_type=SourceType.ATS_GREENHOUSE
    )
    return await ingest_boards(session, _StubAdapter(postings), [BOARD], source=source, now=NOW)


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_two_postings_with_identical_content_become_one_job(
    db_session: AsyncSession,
) -> None:
    text = "<p>Backend engineer building payment systems.</p>"
    await _ingest(
        db_session,
        [
            _posting("1", url="https://boards.greenhouse.io/acme/jobs/1", title="Backend Engineer", text=text),
            _posting("2", url="https://boards.greenhouse.io/acme/jobs/2", title="Backend Engineer", text=text),
        ],
    )
    assert await _count(db_session, Job) == 1
    assert await _count(db_session, SourceJobRecord) == 2


async def test_a_merge_keeps_every_source_link(db_session: AsyncSession) -> None:
    """M1 acceptance: every canonical job traces to at least one raw record —
    and after a merge, to all of them."""
    text = "<p>Backend engineer building payment systems.</p>"
    await _ingest(
        db_session,
        [
            _posting("3", url="https://boards.greenhouse.io/acme/jobs/3", title="Backend Engineer", text=text),
            _posting("4", url="https://boards.greenhouse.io/acme/jobs/4", title="Backend Engineer", text=text),
        ],
    )
    assert await _count(db_session, JobSourceLink) == 2
    job = (await db_session.execute(select(Job))).scalars().one()
    links = (
        (await db_session.execute(select(JobSourceLink).where(JobSourceLink.job_id == job.id)))
        .scalars()
        .all()
    )
    assert len(links) == 2
    assert {link.link_reason for link in links} == {"sole_source_record", "identical_content"}


async def test_a_merge_writes_an_audit_row(db_session: AsyncSession) -> None:
    text = "<p>Backend engineer building payment systems.</p>"
    await _ingest(
        db_session,
        [
            _posting("5", url="https://boards.greenhouse.io/acme/jobs/5", title="Backend Engineer", text=text),
            _posting("6", url="https://boards.greenhouse.io/acme/jobs/6", title="Backend Engineer", text=text),
        ],
    )
    event = (await db_session.execute(select(JobMergeEvent))).scalars().one()
    assert event.reason == "identical_content"
    assert event.ruleset_version
    assert event.loser_snapshot


async def test_different_titles_stay_two_jobs(db_session: AsyncSession) -> None:
    """The direction that costs a user a job if it goes wrong."""
    text = "<p>Backend engineer building payment systems.</p>"
    await _ingest(
        db_session,
        [
            _posting("7", url="https://boards.greenhouse.io/acme/jobs/7", title="Backend Engineer", text=text),
            _posting("8", url="https://boards.greenhouse.io/acme/jobs/8", title="Staff Backend Engineer", text=text),
        ],
    )
    assert await _count(db_session, Job) == 2


async def test_re_ingesting_a_merged_board_is_idempotent(db_session: AsyncSession) -> None:
    """M1 acceptance: no dupes, no spurious updates — including after a merge.

    The failure this guards is a merge that re-fires on the second poll,
    merging the winner into a fresh job and churning the audit table.
    """
    text = "<p>Backend engineer building payment systems.</p>"
    postings = [
        _posting("9", url="https://boards.greenhouse.io/acme/jobs/9", title="Backend Engineer", text=text),
        _posting("10", url="https://boards.greenhouse.io/acme/jobs/10", title="Backend Engineer", text=text),
    ]
    await _ingest(db_session, postings)
    merges_after_first = await _count(db_session, JobMergeEvent)

    _, stats = await _ingest(db_session, postings)
    assert stats.created == 0
    assert await _count(db_session, Job) == 1
    assert await _count(db_session, JobMergeEvent) == merges_after_first


async def test_every_job_still_traces_to_a_raw_record(db_session: AsyncSession) -> None:
    text = "<p>Backend engineer building payment systems.</p>"
    await _ingest(
        db_session,
        [
            _posting("11", url="https://boards.greenhouse.io/acme/jobs/11", title="Backend Engineer", text=text),
            _posting("12", url="https://boards.greenhouse.io/acme/jobs/12", title="Backend Engineer", text=text),
        ],
    )
    orphans = (
        await db_session.execute(
            select(func.count())
            .select_from(Job)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .where(JobSourceLink.id.is_(None))
        )
    ).scalar_one()
    assert orphans == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/test_merge_pipeline.py -v`
Expected: FAIL — the merge tests report 2 jobs where 1 is expected. The two
`distinct` tests should already PASS, and must keep passing.

- [ ] **Step 3: Add the merge machinery to `domain/ingestion.py`**

```python
async def _candidate_for(
    session: AsyncSession, job: Job, normalized: NormalizedSourceJob
) -> DedupeCandidate:
    """Flatten a canonical job into a comparison candidate."""
    keys = (
        (
            await session.execute(
                select(JobLocation.city, JobLocation.state, JobLocation.country).where(
                    JobLocation.job_id == job.id
                )
            )
        )
        .all()
    )
    embedding = (
        await session.execute(
            select(JobEmbedding.embedding).where(JobEmbedding.job_id == job.id)
        )
    ).scalar_one_or_none()
    return DedupeCandidate(
        company_key=str(job.company_id),
        canonical_url=normalized.canonical_url,
        normalized_title=job.normalized_title,
        employment_type=job.employment_type,
        location_keys=frozenset(location_key(c, s, co) for c, s, co in keys),
        description_hash=job.canonical_description_hash or "",
        description=job.description_text,
        embedding=tuple(embedding) if embedding is not None else None,
    )


async def merge_jobs(
    session: AsyncSession, *, winner: Job, loser: Job, verdict: DedupeVerdict
) -> None:
    """Fold ``loser`` into ``winner``, preserving every provenance edge.

    Reversibility does not depend on the snapshot below. Canonical jobs are
    derived from ``source_job_records.raw_payload``, which is preserved
    verbatim, so any merge can be undone by re-deriving. The event exists to
    make the decision auditable and the un-merge cheap.
    """
    session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=loser.id,
            loser_snapshot={
                "title": loser.title,
                "normalized_title": loser.normalized_title,
                "canonical_description_hash": loser.canonical_description_hash,
                "company_id": str(loser.company_id),
                "first_seen_at": loser.first_seen_at.isoformat(),
                "status": loser.status.value,
            },
            reason=verdict.reason,
            match_confidence=verdict.confidence,
            ruleset_version=DEDUPE_RULESET_VERSION,
        )
    )

    links = (
        (await session.execute(select(JobSourceLink).where(JobSourceLink.job_id == loser.id)))
        .scalars()
        .all()
    )
    for link in links:
        link.job_id = winner.id
        link.match_confidence = verdict.confidence
        link.link_reason = verdict.reason

    # The winner keeps the earlier discovery date: it is the same opening, and
    # the earlier sighting is the true one.
    winner.first_seen_at = min(winner.first_seen_at, loser.first_seen_at)
    winner.last_seen_at = max(winner.last_seen_at, loser.last_seen_at)

    await session.flush()
    await session.delete(loser)
    await session.flush()


async def find_duplicate(
    session: AsyncSession, *, job: Job, normalized: NormalizedSourceJob
) -> tuple[Job, DedupeVerdict] | None:
    """Find an existing job that ``job`` duplicates, within the same company.

    Blocking by company is a correctness rule before it is a performance one:
    merging across employers is never right, and there is no code path here
    that can compare two companies' postings.
    """
    others = (
        (
            await session.execute(
                select(Job).where(Job.company_id == job.company_id, Job.id != job.id)
            )
        )
        .scalars()
        .all()
    )
    if not others:
        return None

    candidate = await _candidate_for(session, job, normalized)
    for other in others:
        other_normalized = normalized.model_copy(update={"canonical_url": None})
        other_candidate = await _candidate_for(session, other, other_normalized)
        # Reinstate the other job's own URL — _candidate_for takes it from the
        # normalized payload, which belongs to the incoming posting.
        other_candidate = replace(
            other_candidate, canonical_url=await _canonical_url_of(session, other)
        )
        verdict = compare(candidate, other_candidate)
        if verdict.merge:
            return other, verdict
    return None


async def _canonical_url_of(session: AsyncSession, job: Job) -> str | None:
    return (
        await session.execute(
            select(SourceJobRecord.canonical_url)
            .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
            .where(JobSourceLink.job_id == job.id)
            .limit(1)
        )
    ).scalar_one_or_none()


async def _store_embedding(session: AsyncSession, job: Job) -> None:
    """Embed a job's description, skipping unchanged ones.

    Keyed on the description hash, so a re-poll of an unchanged posting does no
    model work — which is what keeps embedding off the hot path of an
    idempotent poll.
    """
    if not job.description_text:
        return
    existing = (
        await session.execute(select(JobEmbedding).where(JobEmbedding.job_id == job.id))
    ).scalar_one_or_none()
    source_hash = job.canonical_description_hash or ""
    if existing is not None and existing.source_hash == source_hash:
        return

    vector = default_embedder().embed([job.description_text])[0]
    if existing is None:
        session.add(
            JobEmbedding(
                job_id=job.id,
                model_name=EMBEDDING_MODEL_NAME,
                dimension=EMBEDDING_DIMENSION,
                embedding=list(vector),
                source_hash=source_hash,
            )
        )
    else:
        existing.embedding = list(vector)
        existing.source_hash = source_hash
        existing.model_name = EMBEDDING_MODEL_NAME
        existing.dimension = EMBEDDING_DIMENSION
    await session.flush()
```

Add the imports: `from dataclasses import replace`, and from
`nightshift.domain.dedupe` import `DEDUPE_RULESET_VERSION`, `DedupeCandidate`,
`DedupeVerdict`, `compare`, `location_key`; from `nightshift.domain.embeddings`
import `EMBEDDING_DIMENSION`, `EMBEDDING_MODEL_NAME`, `default_embedder`; and
`JobEmbedding`, `JobMergeEvent` from `nightshift.db.models`.

- [ ] **Step 4: Call it from the create branch of `persist_source_job`**

Immediately before `return "created"`, replacing that line:

```python
        await session.flush()
        await _store_embedding(session, job)

        # Dedupe runs only on creation. An existing record already resolves to
        # its canonical job through the link table, and re-running the matcher
        # on every poll is how a stable merge starts oscillating.
        duplicate = await find_duplicate(session, job=job, normalized=normalized)
        if duplicate is not None:
            existing_job, verdict = duplicate
            await merge_jobs(session, winner=existing_job, loser=job, verdict=verdict)
        return "created"
```

- [ ] **Step 5: Run the tests**

Run: `cd services/api && pytest tests/test_merge_pipeline.py tests/test_ingestion.py tests/test_closure_pipeline.py -v`

Expected: PASS, all three files. `test_ingestion.py::test_reingestion_is_idempotent`
is the one most likely to break — if `created` is no longer 9 on the Lever
board, the matcher is merging postings that are genuinely distinct. Investigate
by printing each verdict rather than by loosening the assertion.

- [ ] **Step 6: Prove the blocking rules can fail**

Delete the `if a.normalized_title != b.normalized_title` guard in
`dedupe.compare` and confirm `test_different_titles_stay_two_jobs` **fails**.
Restore it. Record the result in the commit message.

- [ ] **Step 7: `make check`, then commit**

```bash
make check
git add services/api/nightshift/domain/ingestion.py services/api/tests/test_merge_pipeline.py
git commit -m "feat(dedupe): merge duplicate postings into one canonical job

Every provenance edge moves to the winner, so a merged job still traces to
both raw records. Dedupe runs only on creation: re-running the matcher on
every poll is how a stable merge starts oscillating.

Non-vacuity: removing the title guard makes the distinct-titles test fail,
which is the direction that costs a user a job.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: API surface for the admin table and source health

**Files:**
- Modify: `services/api/nightshift/api/routes/jobs.py`
- Modify: `services/api/nightshift/api/routes/sources.py`
- Modify: `services/api/nightshift/api/schemas.py`
- Modify: `services/api/tests/test_routes.py`

**Interfaces:**
- Consumes: `JobStatusEvent`, `JobMergeEvent` from Task 1.
- Produces: `GET /jobs/admin`, `GET /jobs/{id}/history`, and a `status` filter
  on `GET /jobs`. Consumed by Task 10.

- [ ] **Step 1: Read the current shapes**

Run: `cd services/api && grep -n "class .*Out" nightshift/api/schemas.py`

Follow the naming already in the file. Do not invent a second convention.

- [ ] **Step 2: Write the failing route tests**

Append to `services/api/tests/test_routes.py`:

```python
async def test_jobs_route_accepts_a_status_filter(client: AsyncClient) -> None:
    response = await client.get("/jobs", params={"status": "open"})
    assert response.status_code == 200
    for job in response.json()["items"]:
        assert job["status"] == "open"


async def test_admin_route_reports_the_status_breakdown(client: AsyncClient) -> None:
    """The count that answers 'is the closure machine doing anything?'"""
    response = await client.get("/jobs/admin")
    assert response.status_code == 200
    body = response.json()
    assert set(body["status_counts"]) <= {
        "open",
        "possibly_stale",
        "unverified",
        "closed",
    }
    assert isinstance(body["items"], list)


async def test_admin_rows_carry_provenance(client: AsyncClient) -> None:
    """Acceptance: every canonical job traces to at least one raw record.
    Asserted at the API boundary, where a human can actually see it."""
    body = (await client.get("/jobs/admin")).json()
    for job in body["items"]:
        assert job["source_count"] >= 1
        assert job["status"] in {"open", "possibly_stale", "unverified", "closed"}


async def test_history_route_is_404_for_an_unknown_job(client: AsyncClient) -> None:
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


async def test_source_health_distinguishes_an_outage_from_an_empty_board(
    client: AsyncClient,
) -> None:
    """§2.6 and I3 at the API boundary. If these two collapse into one number
    the UI cannot tell the user which one happened."""
    body = (await client.get("/sources")).json()
    for source in body:
        assert "last_success_at" in source
        assert "last_failure_at" in source
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd services/api && pytest tests/test_routes.py -v`
Expected: FAIL on the four new routes with 404 or 422.

- [ ] **Step 4: Add the schemas**

In `nightshift/api/schemas.py`:

```python
class JobAdminRowOut(BaseModel):
    """One row of the admin job table.

    Deliberately not the same shape as JobOut: this view answers operational
    questions — is it still listed, how many sources describe it, was it
    merged — and mixing those into the user-facing schema would put pipeline
    internals in front of a job seeker.
    """

    id: uuid.UUID
    title: str
    company_name: str
    status: JobStatus
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    source_count: int
    location_count: int
    merge_count: int


class JobAdminListOut(BaseModel):
    items: list[JobAdminRowOut]
    total: int
    status_counts: dict[str, int]


class JobStatusEventOut(BaseModel):
    """One transition, in the words the closure machine used at the time."""

    from_status: JobStatus | None
    to_status: JobStatus
    reason: str
    observed_misses: int | None
    created_at: datetime
```

- [ ] **Step 5: Add the routes**

In `nightshift/api/routes/jobs.py`. Register `/jobs/admin` **before** any
`/jobs/{job_id}` route, or FastAPI matches `admin` as a job id and returns 422.

```python
@router.get("/jobs/admin", response_model=JobAdminListOut)
async def list_jobs_for_admin(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: Annotated[JobStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobAdminListOut:
    """Operational view of the canonical job table.

    Includes closed jobs by default, unlike the user-facing list. Hiding them
    here would make the closure machine unobservable, which is the failure this
    page exists to prevent.
    """
    counts = dict(
        (row[0].value, row[1])
        for row in (
            await session.execute(select(Job.status, func.count()).group_by(Job.status))
        ).all()
    )

    query = (
        select(
            Job,
            Company.canonical_name,
            func.count(func.distinct(JobSourceLink.id)),
            func.count(func.distinct(JobLocation.id)),
            func.count(func.distinct(JobMergeEvent.id)),
        )
        .join(Company, Company.id == Job.company_id)
        .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
        .outerjoin(JobLocation, JobLocation.job_id == Job.id)
        .outerjoin(JobMergeEvent, JobMergeEvent.winner_job_id == Job.id)
        .group_by(Job.id, Company.canonical_name)
        .order_by(Job.last_seen_at.desc())
    )
    if status is not None:
        query = query.where(Job.status == status)

    total = int(
        (
            await session.execute(
                select(func.count()).select_from(Job).where(
                    Job.status == status if status is not None else text("true")
                )
            )
        ).scalar_one()
    )

    rows = (await session.execute(query.limit(limit).offset(offset))).all()
    return JobAdminListOut(
        items=[
            JobAdminRowOut(
                id=job.id,
                title=job.title,
                company_name=company_name,
                status=job.status,
                first_seen_at=job.first_seen_at,
                last_seen_at=job.last_seen_at,
                closed_at=job.closed_at,
                source_count=source_count,
                location_count=location_count,
                merge_count=merge_count,
            )
            for job, company_name, source_count, location_count, merge_count in rows
        ],
        total=total,
        status_counts=counts,
    )


@router.get("/jobs/{job_id}/history", response_model=list[JobStatusEventOut])
async def job_history(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[JobStatusEventOut]:
    """Every transition this job has been through.

    This is the answer to "why did this job disappear?", and it survives the
    job reopening — which is the whole reason job_status_events is append-only.
    """
    exists = (
        await session.execute(select(Job.id).where(Job.id == job_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="job not found")

    events = (
        (
            await session.execute(
                select(JobStatusEvent)
                .where(JobStatusEvent.job_id == job_id)
                .order_by(JobStatusEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [JobStatusEventOut.model_validate(event, from_attributes=True) for event in events]
```

Add the `status` filter to the existing `GET /jobs` handler the same way, and
confirm the existing default still excludes closed jobs — a user-facing list
that starts showing closed roles is a regression, not a feature.

- [ ] **Step 6: Run the tests**

Run: `cd services/api && pytest tests/test_routes.py -v`
Expected: PASS.

- [ ] **Step 7: `make check`, then commit**

```bash
make check
git add services/api/nightshift/api services/api/tests/test_routes.py
git commit -m "feat(api): add the admin job view and per-job status history

/jobs/admin includes closed jobs on purpose — hiding them would make the
closure machine unobservable, which is what this view exists to prevent.
/jobs/{id}/history answers 'why did this disappear' and survives a repost.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: The UI, and closing the milestone

**Files:**
- Create: `apps/web/src/components/JobAdminTable.tsx`
- Create: `apps/web/src/app/operate/jobs/page.tsx`
- Modify: `apps/web/src/components/SourceHealthTable.tsx`
- Modify: `apps/web/src/lib/schemas.ts`, `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/app/operate/page.tsx`
- Modify: `docs/PROGRESS.md`
- Test: `apps/web/e2e-seeded/` (extend)

**Interfaces:**
- Consumes: the routes from Task 9.
- Produces: nothing later in this plan depends on it. M1c starts from here.

- [ ] **Step 1: Read the existing patterns**

Run:
```bash
sed -n 1,80p apps/web/src/components/SourceHealthTable.tsx
sed -n 1,60p apps/web/src/lib/schemas.ts
```

Follow them. Zod at the network boundary, named exports, no `any`.

- [ ] **Step 2: Add the Zod schemas**

In `apps/web/src/lib/schemas.ts`:

```ts
export const jobStatusSchema = z.enum(['open', 'possibly_stale', 'unverified', 'closed']);

export const jobAdminRowSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  company_name: z.string(),
  status: jobStatusSchema,
  first_seen_at: z.string(),
  last_seen_at: z.string(),
  closed_at: z.string().nullable(),
  source_count: z.number().int().nonnegative(),
  location_count: z.number().int().nonnegative(),
  merge_count: z.number().int().nonnegative(),
});

export const jobAdminListSchema = z.object({
  items: z.array(jobAdminRowSchema),
  total: z.number().int().nonnegative(),
  status_counts: z.record(jobStatusSchema, z.number().int().nonnegative()),
});

export type JobAdminRow = z.infer<typeof jobAdminRowSchema>;
```

- [ ] **Step 3: Build the admin table**

`apps/web/src/components/JobAdminTable.tsx`. Requirements, all of which are
assertions in step 6:

- One row per job: title, company, status, last seen, source count, merge count.
- Status filter buttons, including `closed`.
- Each status renders with the word, never a colour alone — §12.4 forbids
  essential information available only through a visual channel.
- A short explanatory line per status, in the user's language, not the
  schema's. Specifically: `possibly_stale` reads "the board answered and this
  job was not in it", and `unverified` reads "we have not been able to check
  this board recently". Those two being distinguishable in words is the whole
  of I3 reaching a screen.
- Empty state says why it is empty, never renders a blank table.

- [ ] **Step 4: Grow the source health table**

Add per-source: last successful poll, last failure, and a sentence stating the
distinction — an outage leaves listings untouched, an empty board does not.
The existing "committed fixture" gold badge (ADR 0004) stays.

- [ ] **Step 5: Link it from Operate**

Add a link to `/operate/jobs` from `apps/web/src/app/operate/page.tsx` and
delete the "Not built yet" line that claims closure does not exist, if present.

- [ ] **Step 6: Extend the seeded e2e suite**

In `apps/web/e2e-seeded/`, following the existing file's patterns:

```ts
test('the admin job table renders real rows with a status word', async ({ page }) => {
  await page.goto('/operate/jobs');
  const rows = page.getByRole('row');
  await expect(rows.first()).toBeVisible();
  // The status must be readable as text, not only as a colour (§12.4).
  await expect(page.getByText('open', { exact: false }).first()).toBeVisible();
});

test('stale and unverified are explained in different words', async ({ page }) => {
  await page.goto('/operate/jobs');
  const legend = page.getByRole('region', { name: /status/i });
  await expect(legend).toContainText('was not in it');
  await expect(legend).toContainText('not been able to check');
});
```

- [ ] **Step 7: Run everything**

```bash
make check
make acceptance
```

Expected: `make check` green in both languages. `make acceptance` green —
record the exact check count and browser-test count, since both grow in this
task.

- [ ] **Step 8: Update `docs/PROGRESS.md`**

Do all of these:

1. **"Next exact action"** → M1c (board discovery), noting M1b is complete and
   that its plan is `docs/plans/2026-08-01-m1b-canonical-spine.md`.
2. **"Before M1 starts"** → item 4 (`_replace_locations` on geocoding) is still
   open; item 5 (redundant ordering) can be closed if done. Do not mark item 4
   done — geocoding has not landed.
3. **"Not real yet"** → delete the *Closure state machine* row and the *Dedupe*
   row; both are now real. Keep *Geocoding* and *`job_locations.geom`*. Add a
   row for the similarity threshold, naming the fixture set it was derived from
   and the fact that it is calibrated on 12 labelled pairs rather than on
   production data.
4. **Acceptance criteria** — add an M1 table and mark, with recorded evidence:
   re-ingestion idempotent; outage closes zero jobs; dedupe fixture suite
   passes; every canonical job traces to a raw record; multi-location rows;
   ingestion failures visible in the UI. Leave the four M1c/M1d rows explicitly
   unclaimed.
5. **Session log** — cover: the derived similarity threshold and its printed
   separation; whether any labelled pair sat on the wrong side of it; the
   non-vacuity results from Tasks 2, 3, 5 and 8; and anything the real data
   contradicted.
6. **"Verified locally"** — update the test counts.

- [ ] **Step 9: Write the milestone review**

Per CLAUDE.md §5, `docs/reviews/milestone-1b-review.md`. Actively look for:
hallucinated certainty in the merge confidences; silent data loss in
`merge_jobs`; the race between two workers merging into each other; retry
storms; a `possibly_stale` job that can never leave that state; tests that
assert nothing.

- [ ] **Step 10: Commit**

```bash
make check
git add apps/web docs/PROGRESS.md docs/reviews/milestone-1b-review.md
git commit -m "feat(web): add the admin job table and grow source health; close M1b

The status words are the deliverable, not the table: 'the board answered
and this job was not in it' and 'we have not been able to check this board
recently' are the two facts I3 exists to keep apart, and this is where
they reach a screen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** Against `CLAUDE.md` §6's M1 acceptance criteria:

| Criterion | Covered by |
|---|---|
| Same fixture in → byte-identical output twice | Already true from M1a; unaffected here |
| Re-ingestion idempotent: no dupes, no spurious updates | Task 8 — `test_re_ingesting_a_merged_board_is_idempotent` |
| Simulated source outage closes zero jobs | Task 3 — `test_a_failed_board_does_not_increment_a_miss` |
| Dedupe fixture suite: true dupes merge, near-dupes and same-title-different-role stay separate | Tasks 4, 5, 7 |
| Every canonical job traces to at least one raw source record | Task 8 — `test_every_job_still_traces_to_a_raw_record` |
| Multi-location postings produce multiple `job_locations` rows | Already true from M1a; asserted again in Task 4's fixtures |
| Ingestion failures are visible in the UI, not just logs | Tasks 9, 10 |
| Freshness + closure state machine | Tasks 2, 3 |
| Admin job table, source health page | Tasks 9, 10 |
| Discovery from a committed crawl fixture | **M1c** — not this plan |
| A live-but-unnameable board cannot reach bulk approval | **M1c** |
| A `304 Not Modified` produces zero writes | **M1d** |
| The coverage page names what is *not* covered | **M1c** |

Against `docs/architecture/canonical-spine.md`: §2's three tables are Task 1;
§3 is Tasks 2–3; §4 is Tasks 4–8; §5 is Tasks 9–10; §6 is deferred by name.

**Placeholders.** One, and it is marked: `SIMILARITY_THRESHOLD = 0.90` in
Task 7 Step 3 carries `# replace with the value step 2 printed`, and Step 2
requires running the derivation script first and pasting its table into the
commit message. The number cannot be known before the model runs, and inventing
one here would be exactly the guessing ADR 0010 forbids.

**Type consistency.** `DedupeCandidate`'s eight fields are defined in Task 5
and constructed with those exact names in Tasks 4, 7 and 8.
`DedupeVerdict(merge, reason, confidence)` is returned by `compare` and read in
Task 8. `decide_job_status(current, records, board_last_success_at, now)` is
defined in Task 2 and called with those keywords in Task 3.
`RecordObservation(consecutive_misses, last_seen_at)` likewise.
`Embedder.embed(texts) -> list[tuple[float, ...]]` is satisfied by both
`FastEmbedEmbedder` and `StubEmbedder` and consumed in Tasks 7 and 8.
`requires_db` and `db_session` come from `tests/conftest.py`, unchanged from
M1a.

**Risks, checked rather than left open.**

- **No task in this plan needs an enum migration.** `SourceStatus.MISSING`
  already exists (`db/base.py:108`) and `JobStatus` already has all four
  members (`db/base.py:95-101`), both verified while writing this plan. That
  matters because `ALTER TYPE ... ADD VALUE` is not reversible in PostgreSQL
  and this plan requires every migration to be tested in both directions.
- **The threshold may not separate the labelled set.** Task 7 Step 2 says to
  stop and record it rather than split the difference. That is the honest
  outcome, not a failure of the plan.
- **`find_duplicate` is O(jobs-per-company) per created job.** Fine at
  thousands; it will not be at M1c's scale. Deliberately not optimised here:
  the right fix is a blocking index on (company, normalized_title), and adding
  it before there is a measurement would be building for imaginary scale.
- **Two workers could merge concurrently.** Not reachable today at
  `max_jobs=1`, and it is named in Task 10's review checklist so M1d inherits
  it as a known question rather than a surprise.
