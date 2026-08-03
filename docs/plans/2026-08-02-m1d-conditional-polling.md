# M1d — Conditional polling. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll every board in the registry conditionally and on a schedule, so a
`304 Not Modified` costs one request and writes nothing — closing M1 criterion 13
and the milestone.

**Architecture:** `PoliteClient` learns `If-None-Match`. `FetchOutcome` grows the
distinction between a posting being *listed* on a board and its content being
*fetched*, because Greenhouse's two-phase poll only fetches what changed and the
freshness pass would otherwise read "not fetched" as "gone". Per-board state
(ETag, tier, `next_poll_at`) lives in a new `board_poll_state` table; a cron
drains due boards into individual ARQ jobs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, ARQ, httpx,
Pydantic v2, pytest / pytest-asyncio, mypy strict, ruff.

**Design:** `docs/architecture/conditional-polling.md`. Read §4 and §5 before
Task 5 — they are what the milestone can get invisibly wrong.

## Global Constraints

- **Invariant I3 governs this whole plan.** A failure, a timeout, a `304`, or an
  empty array never closes a job. `ok=False` means we learned nothing.
- **Never `content=true` on a routine Greenhouse poll.** It is reserved for a
  board's first ingestion (ADR 0007).
- **Nothing outside `nightshift/adapters/http.py` imports `httpx`** (CLAUDE.md §7).
- **All timestamps `TIMESTAMPTZ`, UTC in the database.** `UTCDateTime` rejects
  naive datetimes at the boundary — use `utcnow()` from `nightshift.db.types`.
- **Enums are PG enums**, declared as `enum.StrEnum` in `nightshift/db/base.py`
  and created/dropped explicitly in the migration. A downgrade that forgets
  `DROP TYPE` leaves the type behind and is a failing migration test.
- **Every migration is reversible and tested both directions.**
- **mypy strict must pass** (`make typecheck`). Full annotations, no `Any` that
  is not forced by a provider payload.
- **`TODO` must carry a milestone**: `TODO(M2): ...`. A bare `TODO` fails lint.
- **Run `make check` before every commit.** Conventional commits, scoped.
- Adapters return `FetchOutcome`; they do not raise for source failures.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `nightshift/adapters/http.py` | Conditional GET; the only httpx importer | 1 |
| `nightshift/adapters/base.py` | `ListedPosting`, `FetchOutcome`, Protocol | 2, 3, 4 |
| `nightshift/adapters/greenhouse.py` | Two-phase: listing, then changed postings | 3, 4 |
| `nightshift/adapters/lever.py` | Single-phase, conditional | 3 |
| `nightshift/adapters/ashby.py` | Single-phase, conditional | 3 |
| `nightshift/domain/ingestion.py` | Freshness ages against the *listed* set | 5 |
| `nightshift/db/base.py` | `BoardTier` enum | 6 |
| `nightshift/db/models.py` | `BoardPollState` | 6 |
| `migrations/versions/20260802_*_board_poll_state.py` | Table + enum, reversible | 6 |
| `nightshift/domain/polling.py` | **New.** Poll one board end to end | 7 |
| `nightshift/domain/tiers.py` | **New.** Derive hot/warm from postings | 8 |
| `nightshift/workers/tasks.py` | `poll_board`, `enqueue_due_boards` | 7, 8 |
| `nightshift/workers/main.py` | Cron registration | 7 |
| `nightshift/discovery/approve.py` | `promote` appends instead of re-serializing | 10 |

`polling.py` and `tiers.py` are new modules rather than additions to
`ingestion.py`, which is already 850 lines and is the file this milestone leans
on hardest.

---

## Task 1: `PoliteClient` sends `If-None-Match` and reports `304`

**Files:**
- Modify: `services/api/nightshift/adapters/http.py`
- Test: `services/api/tests/test_http_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ConditionalResponse` (frozen Pydantic model with
  `not_modified: bool`, `payload: Any`, `etag: str | None`, `http_status: int`)
  and `PoliteClient.get_json_conditional(url: str, *, etag: str | None = None)
  -> ConditionalResponse`. `get_json(url) -> Any` keeps its exact current
  signature and behaviour.

**Why this shape:** `get_json` has the retry loop, the rate limiter, the kill
switch, and the I3 error funnel. A second HTTP path would be a second place to
forget all four, so `get_json` becomes a thin wrapper over the conditional one.

- [ ] **Step 1: Write the failing tests**

Append to `services/api/tests/test_http_client.py`:

```python
class TestConditionalRequests:
    """M1d: a 304 is a distinct outcome, not an error and not an empty board."""

    async def test_sends_if_none_match_when_given_an_etag(self) -> None:
        seen: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(dict(request.headers))
            return httpx.Response(200, json={"jobs": []}, headers={"ETag": 'W/"abc"'})

        async with _client_with(handler) as client:
            await client.get_json_conditional("https://example.test/jobs", etag='W/"abc"')

        assert seen[0]["if-none-match"] == 'W/"abc"'

    async def test_omits_if_none_match_when_there_is_no_etag(self) -> None:
        seen: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(dict(request.headers))
            return httpx.Response(200, json={"jobs": []})

        async with _client_with(handler) as client:
            await client.get_json_conditional("https://example.test/jobs", etag=None)

        assert "if-none-match" not in seen[0]

    async def test_a_304_is_not_modified_and_carries_no_payload(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(304)

        async with _client_with(handler) as client:
            result = await client.get_json_conditional(
                "https://example.test/jobs", etag='W/"abc"'
            )

        assert result.not_modified is True
        assert result.payload is None
        assert result.http_status == 304

    async def test_a_304_is_never_retried(self) -> None:
        """A 304 is a successful answer. Retrying it is pure rudeness."""
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(304)

        async with _client_with(handler) as client:
            await client.get_json_conditional("https://example.test/jobs", etag='W/"abc"')

        assert calls == 1

    async def test_a_200_returns_the_etag_for_storage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jobs": []}, headers={"ETag": 'W/"fresh"'})

        async with _client_with(handler) as client:
            result = await client.get_json_conditional("https://example.test/jobs")

        assert result.not_modified is False
        assert result.etag == 'W/"fresh"'
        assert result.payload == {"jobs": []}

    async def test_a_200_without_an_etag_yields_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jobs": []})

        async with _client_with(handler) as client:
            result = await client.get_json_conditional("https://example.test/jobs")

        assert result.etag is None

    async def test_the_kill_switch_still_applies(self) -> None:
        client = PoliteClient(_settings(outbound_http_enabled=False))
        async with client:
            with pytest.raises(OutboundHTTPDisabledError):
                await client.get_json_conditional("https://example.test/jobs")

    async def test_get_json_is_unchanged_and_still_returns_a_payload(self) -> None:
        """The old entry point keeps its exact contract for every caller."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jobs": [1, 2]})

        async with _client_with(handler) as client:
            assert await client.get_json("https://example.test/jobs") == {"jobs": [1, 2]}
```

If `_client_with` and `_settings` helpers do not already exist in that test
file, add them — a transport-stubbed client and a `Settings` factory with
`outbound_http_enabled=True`, `http_max_retries=0`, `source_requests_per_second=100`
so tests do not sleep:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from nightshift.adapters.http import OutboundHTTPDisabledError, PoliteClient
from nightshift.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "outbound_http_enabled": True,
        "http_max_retries": 0,
        "source_requests_per_second": 100.0,
        "http_backoff_base_seconds": 0.001,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@asynccontextmanager
async def _client_with(
    handler: Callable[[httpx.Request], httpx.Response],
    **overrides: object,
) -> AsyncIterator[PoliteClient]:
    client = PoliteClient(_settings(**overrides))
    async with client:
        client._client = httpx.AsyncClient(  # noqa: SLF001 - test seam
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": "test"},
        )
        yield client
        await client._client.aclose()  # noqa: SLF001
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_http_client.py -k Conditional -v
```

Expected: `AttributeError: 'PoliteClient' object has no attribute 'get_json_conditional'`.

- [ ] **Step 3: Implement**

In `nightshift/adapters/http.py`, add the model near the top (after `MAX_TEXT_BYTES`):

```python
class ConditionalResponse(BaseModel):
    """The result of one conditional GET.

    ``not_modified`` is the whole point: it is neither a failure nor an empty
    body, and a caller that collapses it into either is the I3 bug ADR 0007
    warned about before there was code to warn about.
    """

    model_config = ConfigDict(frozen=True)

    not_modified: bool
    payload: Any = None
    etag: str | None = None
    http_status: int
```

Add `from pydantic import BaseModel, ConfigDict` to the imports.

Replace the body of `get_json` and add `get_json_conditional`:

```python
    async def get_json(self, url: str) -> Any:
        """GET and parse JSON, or raise :class:`SourceUnavailableError`.

        Every failure path funnels into that one exception type because callers
        must treat them identically under I3: a timeout, a 503, and a truncated
        body are all "we learned nothing", never "the jobs are gone".

        Unconditional by construction: with no ETag the server cannot answer
        ``304``, so ``payload`` is always present for this caller.
        """
        return (await self.get_json_conditional(url)).payload

    async def get_json_conditional(
        self, url: str, *, etag: str | None = None
    ) -> ConditionalResponse:
        """GET with ``If-None-Match``, returning ``304`` as data rather than as an error.

        A ``304`` is not retried. It is the answer, and the cheapest one the
        provider can give us.
        """
        if not self._settings.outbound_http_enabled:
            raise OutboundHTTPDisabledError(
                "outbound HTTP is disabled (OUTBOUND_HTTP_ENABLED=false); "
                "ingestion must run from committed fixtures"
            )
        if self._client is None:
            raise RuntimeError("PoliteClient must be used as an async context manager")

        headers = {"If-None-Match": etag} if etag else None

        attempts = self._settings.http_max_retries + 1
        last_error: str = "no attempt made"
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                last_status = None
            else:
                last_status = response.status_code
                if response.status_code == 304:
                    # Before the terminal branch below: 304 is not in
                    # _RETRYABLE_STATUS, so falling through would raise and turn
                    # the cheapest possible success into a source failure.
                    return ConditionalResponse(
                        not_modified=True,
                        payload=None,
                        etag=etag,
                        http_status=304,
                    )
                if response.is_success:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        # A 200 with a broken body is a source problem, and
                        # retrying it occasionally does help (partial transfer).
                        last_error = f"invalid JSON: {exc}"
                    else:
                        return ConditionalResponse(
                            not_modified=False,
                            payload=payload,
                            etag=response.headers.get("ETag"),
                            http_status=response.status_code,
                        )
                elif response.status_code in _RETRYABLE_STATUS:
                    last_error = f"HTTP {response.status_code}"
                else:
                    # Terminal: 404, 403, 401. Fail now, do not hammer.
                    raise SourceUnavailableError(
                        f"GET {url} failed with HTTP {response.status_code}",
                        http_status=response.status_code,
                    )

            if attempt < attempts:
                delay = _backoff_delay(attempt, self._settings.http_backoff_base_seconds)
                log.warning(
                    "source_request_retry",
                    url=url,
                    attempt=attempt,
                    of=attempts,
                    error=last_error,
                    retry_in=round(delay, 2),
                )
                await asyncio.sleep(delay)

        raise SourceUnavailableError(
            f"GET {url} failed after {attempts} attempt(s): {last_error}",
            http_status=last_status,
        )
```

Note the `304` returns the **caller's** etag, not a response header: a `304`
body-less response may omit `ETag`, and the stored value is still valid.

- [ ] **Step 4: Run the tests and watch them pass**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_http_client.py -v
```

Expected: all pass, including the pre-existing `get_json` tests.

- [ ] **Step 5: Mutation check**

Delete the `if response.status_code == 304:` block. Re-run:
`test_a_304_is_not_modified_and_carries_no_payload` must fail with
`SourceUnavailableError`. Restore it.

- [ ] **Step 6: Commit**

```bash
make check
git add services/api/nightshift/adapters/http.py services/api/tests/test_http_client.py
git commit -m "feat(http): conditional GET with If-None-Match, 304 as data not error"
```

---

## Task 2: `FetchOutcome` separates *listed* from *fetched*

**Files:**
- Modify: `services/api/nightshift/adapters/base.py`
- Test: `services/api/tests/test_adapters_base.py` (create if absent)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ListedPosting` — frozen model, `source_job_id: str`,
    `source_updated_at: datetime | None`.
  - `FetchOutcome` gains `not_modified: bool = False`, `etag: str | None = None`,
    `listed: tuple[ListedPosting, ...] = ()`.
  - `FetchOutcome.listed_source_job_ids -> tuple[str, ...]` property.
  - `FetchOutcome.is_authoritative_empty` now excludes `not_modified`.

**Why:** design §4. `jobs` means "we have the full payload"; `listed` means "the
board says this posting exists". Greenhouse's two-phase poll makes those
different sets, and freshness must read the second one.

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_adapters_base.py`:

```python
"""FetchOutcome's I3 guarantees, including the two M1d adds.

A 304 carries no jobs. So does a genuinely empty board. Conflating them closes
every posting on every unchanged board, which is the most destructive single
bug available in this system.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nightshift.adapters.base import BoardRef, FetchOutcome, ListedPosting, RawJob

BOARD = BoardRef(company="Acme", ats="greenhouse", token="acme")


def _raw(job_id: str) -> RawJob:
    return RawJob(source_job_id=job_id, source_company_key="acme", payload={"id": job_id})


class TestNotModified:
    def test_a_304_is_not_an_authoritative_empty_board(self) -> None:
        """The M1d bug. A 304 is a success carrying no jobs, and so is an empty
        board — but only one of them is evidence that the postings are gone."""
        outcome = FetchOutcome(board=BOARD, ok=True, not_modified=True, etag='W/"abc"')
        assert outcome.is_authoritative_empty is False

    def test_a_genuinely_empty_board_still_is_one(self) -> None:
        outcome = FetchOutcome(board=BOARD, ok=True, http_status=200)
        assert outcome.is_authoritative_empty is True

    def test_a_304_cannot_carry_jobs(self) -> None:
        """Belt and braces: the confusion cannot even be expressed."""
        with pytest.raises(ValidationError):
            FetchOutcome(board=BOARD, ok=True, not_modified=True, jobs=(_raw("1"),))

    def test_a_304_cannot_carry_listed_postings(self) -> None:
        with pytest.raises(ValidationError):
            FetchOutcome(
                board=BOARD,
                ok=True,
                not_modified=True,
                listed=(ListedPosting(source_job_id="1", source_updated_at=None),),
            )

    def test_a_failed_fetch_is_not_authoritative_empty(self) -> None:
        outcome = FetchOutcome(board=BOARD, ok=False, error="timeout")
        assert outcome.is_authoritative_empty is False


class TestListedVersusFetched:
    def test_listed_ids_are_exposed_for_freshness(self) -> None:
        outcome = FetchOutcome(
            board=BOARD,
            ok=True,
            listed=(
                ListedPosting(
                    source_job_id="1",
                    source_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
                ),
                ListedPosting(source_job_id="2", source_updated_at=None),
            ),
        )
        assert outcome.listed_source_job_ids == ("1", "2")

    def test_listed_may_exceed_fetched(self) -> None:
        """Greenhouse phase 2: ten listed, one changed and fetched."""
        outcome = FetchOutcome(
            board=BOARD,
            ok=True,
            jobs=(_raw("1"),),
            listed=tuple(
                ListedPosting(source_job_id=str(n), source_updated_at=None)
                for n in range(1, 11)
            ),
        )
        assert len(outcome.listed_source_job_ids) == 10
        assert len(outcome.jobs) == 1

    def test_a_board_with_listings_is_not_authoritative_empty(self) -> None:
        """Phase 1 succeeded and named ten postings; phase 2 fetched none because
        nothing changed. That is emphatically not an empty board."""
        outcome = FetchOutcome(
            board=BOARD,
            ok=True,
            jobs=(),
            listed=(ListedPosting(source_job_id="1", source_updated_at=None),),
        )
        assert outcome.is_authoritative_empty is False
```

- [ ] **Step 2: Run and watch them fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_adapters_base.py -v
```

Expected: `ImportError: cannot import name 'ListedPosting'`.

- [ ] **Step 3: Implement**

In `nightshift/adapters/base.py`, add before `FetchOutcome`:

```python
class ListedPosting(BaseModel):
    """One posting as it appears in a board *listing*.

    Deliberately thin. A listing is the cheap request (ADR 0007: 33 KB against
    499 KB on the same Greenhouse board), and it carries an id and a
    last-modified stamp but no description. Its job is to answer two questions:
    which postings are still open, and which of them changed.
    """

    model_config = ConfigDict(frozen=True)

    source_job_id: str
    #: Greenhouse publishes this. Lever and Ashby do not, and do not need to —
    #: their board response already contains every posting in full, so there is
    #: no second fetch for a timestamp to gate.
    source_updated_at: datetime | None = None
```

Replace `FetchOutcome` with:

```python
class FetchOutcome(BaseModel):
    """What happened when we polled one board.

    Invariant I3 depends on this type. ``ok=False`` means we learned nothing
    about the jobs on this board, so the caller must not touch their state.
    ``ok=True`` with an empty ``jobs`` list is a genuine, different fact: the
    board responded and has no open postings.

    M1d adds a third state and a distinction:

    * ``not_modified`` — the provider answered ``304``. Nothing changed, so
      there is nothing to write. It is *not* an empty board.
    * ``listed`` versus ``jobs`` — ``listed`` is every posting the board says
      exists, and it is what freshness ages against. ``jobs`` is the subset we
      hold full payloads for. Greenhouse's two-phase poll makes those differ;
      for Lever and Ashby they cover the same postings.
    """

    model_config = ConfigDict(frozen=True)

    board: BoardRef
    ok: bool
    jobs: tuple[RawJob, ...] = ()
    listed: tuple[ListedPosting, ...] = ()
    not_modified: bool = False
    etag: str | None = None
    http_status: int | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _not_modified_carries_nothing(self) -> Self:
        """A 304 has no body, so it cannot describe any posting.

        Enforced rather than documented: an adapter that returned jobs beside
        ``not_modified`` would make every downstream guard ambiguous.
        """
        if self.not_modified and (self.jobs or self.listed):
            raise ValueError("not_modified=True cannot carry jobs or listed postings")
        return self

    @property
    def listed_source_job_ids(self) -> tuple[str, ...]:
        """Every posting id the board listed. The freshness pass ages on this."""
        return tuple(posting.source_job_id for posting in self.listed)

    @property
    def is_authoritative_empty(self) -> bool:
        """True only when the source successfully told us the board is empty.

        ``not_modified`` is excluded explicitly. A 304 carries no jobs, so
        without that clause this property would report an unchanged board as an
        empty one and close every posting on it.

        ``listed`` is checked too: phase 1 naming ten postings while phase 2
        fetches none is the normal state of a Greenhouse board where nothing
        changed.
        """
        return self.ok and not self.not_modified and not self.jobs and not self.listed
```

Add `model_validator` and `Self` to the imports:

```python
from typing import Any, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator
```

- [ ] **Step 4: Run and watch them pass**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_adapters_base.py -v
```

- [ ] **Step 5: Run the whole suite — this type is used everywhere**

```bash
cd services/api && .venv/bin/python -m pytest -q
```

Expected: green. Existing adapters do not set `listed`, so their
`is_authoritative_empty` still depends on `jobs` alone, which is correct until
Task 3 populates `listed`.

- [ ] **Step 6: Mutation check**

Revert `is_authoritative_empty` to `return self.ok and not self.jobs`.
`test_a_304_is_not_an_authoritative_empty_board` and
`test_a_board_with_listings_is_not_authoritative_empty` must both fail. Restore.

- [ ] **Step 7: Commit**

```bash
make check
git add services/api/nightshift/adapters/base.py services/api/tests/test_adapters_base.py
git commit -m "feat(adapters): separate listed from fetched, and make a 304 unable to look empty"
```

---

## Task 3: All three adapters go conditional

**Files:**
- Modify: `services/api/nightshift/adapters/base.py` (Protocol signature)
- Modify: `services/api/nightshift/adapters/greenhouse.py`,
  `lever.py`, `ashby.py`
- Test: `services/api/tests/test_greenhouse_adapter.py`,
  `test_lever_adapter.py`, `test_ashby_adapter.py`

**Interfaces:**
- Consumes: `ConditionalResponse` (Task 1), `ListedPosting` / `FetchOutcome`
  (Task 2).
- Produces: `JobSourceAdapter.fetch_board(self, board: BoardRef, *,
  etag: str | None = None) -> FetchOutcome` on all three adapters, each
  returning `etag`, `not_modified`, and a populated `listed`. Also
  `adapter.parser_version: str` — a module constant, `"1"` on each — and
  `adapter.is_two_phase: bool`, `False` on all three for now (Greenhouse flips
  in Task 4).

**Note:** Greenhouse keeps `content=true` in this task. Task 4 replaces it. Doing
both at once would mean a failing test could be either change.

- [ ] **Step 1: Write the failing tests**

Add to `services/api/tests/test_lever_adapter.py` (and the mirror image in
`test_ashby_adapter.py`, changing only the adapter, fixture and token):

```python
class TestConditionalFetch:
    """M1d: Lever revalidates. Measured 2026-08-02 — it returns 304."""

    async def test_a_304_yields_not_modified_and_touches_nothing(self) -> None:
        client = _stub_client({BOARD_URL.format(token="alloy"): _NOT_MODIFIED})
        outcome = await LeverAdapter(client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.ok is True
        assert outcome.not_modified is True
        assert outcome.jobs == ()
        assert outcome.listed == ()
        assert outcome.is_authoritative_empty is False
        assert outcome.etag == 'W/"abc"'

    async def test_the_etag_is_passed_through_to_the_client(self) -> None:
        seen: list[str | None] = []
        client = _recording_client(seen, _board_payload())
        await LeverAdapter(client).fetch_board(BOARD, etag='W/"abc"')
        assert seen == ['W/"abc"']

    async def test_a_200_returns_the_new_etag(self) -> None:
        client = _stub_client({BOARD_URL.format(token="alloy"): _board_response()})
        outcome = await LeverAdapter(client).fetch_board(BOARD)
        assert outcome.etag == 'W/"fresh"'

    async def test_every_fetched_posting_is_also_listed(self) -> None:
        """Single-phase provider: the two sets describe the same postings.

        Asserted rather than assumed — freshness ages against `listed`, so a
        Lever adapter that forgot to populate it would age every posting it just
        successfully fetched and close the whole board in three polls.
        """
        client = _stub_client({BOARD_URL.format(token="alloy"): _board_response()})
        outcome = await LeverAdapter(client).fetch_board(BOARD)

        assert outcome.listed_source_job_ids == tuple(j.source_job_id for j in outcome.jobs)
        assert len(outcome.listed) > 0
```

Add the stub helpers to each adapter test module (they differ only in payload
shape). For Lever:

```python
from nightshift.adapters.http import ConditionalResponse

_NOT_MODIFIED = ConditionalResponse(not_modified=True, payload=None, etag=None, http_status=304)


def _board_payload() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text())


def _board_response() -> ConditionalResponse:
    return ConditionalResponse(
        not_modified=False,
        payload=_board_payload(),
        etag='W/"fresh"',
        http_status=200,
    )


class _StubClient:
    """Stands in for PoliteClient. Only get_json_conditional is used by adapters."""

    def __init__(self, routes: dict[str, ConditionalResponse]) -> None:
        self._routes = routes

    async def get_json_conditional(
        self, url: str, *, etag: str | None = None
    ) -> ConditionalResponse:
        if url not in self._routes:
            raise AssertionError(f"no stub route for {url}")
        return self._routes[url]


def _stub_client(routes: dict[str, ConditionalResponse]) -> _StubClient:
    return _StubClient(routes)


class _RecordingClient(_StubClient):
    def __init__(self, seen: list[str | None], payload: object) -> None:
        super().__init__({})
        self._seen = seen
        self._payload = payload

    async def get_json_conditional(
        self, url: str, *, etag: str | None = None
    ) -> ConditionalResponse:
        self._seen.append(etag)
        return ConditionalResponse(
            not_modified=False, payload=self._payload, etag='W/"fresh"', http_status=200
        )


def _recording_client(seen: list[str | None], payload: object) -> _RecordingClient:
    return _RecordingClient(seen, payload)
```

- [ ] **Step 2: Run and watch them fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_lever_adapter.py -k Conditional -v
```

Expected: `TypeError: fetch_board() got an unexpected keyword argument 'etag'`.

- [ ] **Step 3: Update the Protocol**

In `nightshift/adapters/base.py`:

```python
@runtime_checkable
class JobSourceAdapter(Protocol):
    """Implemented once per ATS provider. The ingestion pipeline knows only this."""

    source_name: str
    source_type: SourceType
    #: Bumped by hand when normalization changes. A stored ETag is only valid
    #: for the parser that earned it (ADR 0007): a changed parser plus a stale
    #: ETag means the new parser never sees the payload it was written for.
    parser_version: str
    #: True when a board listing does not carry posting content, so changed
    #: postings need a second request. Greenhouse only — Lever and Ashby return
    #: every posting in full from the board endpoint (measured 2026-08-02).
    is_two_phase: bool

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        """Poll one company board, revalidating against ``etag`` when given one.

        Must not raise for an unreachable source — it returns ``ok=False``, so a
        single bad board cannot abort a run over the others. A ``304`` is
        neither: it returns ``ok=True, not_modified=True``.
        """
        ...
```

- [ ] **Step 4: Implement in each adapter**

For **Lever** (`lever.py`) — Ashby is the same shape with its own payload check:

```python
PARSER_VERSION: Final = "1"


class LeverAdapter:
    source_name = "lever"
    source_type = SourceType.ATS_LEVER
    parser_version = PARSER_VERSION
    is_two_phase = False

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        if self._client is None:
            raise RuntimeError("LeverAdapter needs a client to fetch")
        url = BOARD_URL.format(token=board.token)
        try:
            response = await self._client.get_json_conditional(url, etag=etag)
        except SourceUnavailableError as exc:
            log.warning(
                "lever_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if response.not_modified:
            # Zero writes downstream. The board is byte-identical to the copy we
            # already parsed, so every posting we know about is still listed and
            # none of them needs re-reading.
            return FetchOutcome(
                board=board, ok=True, not_modified=True, etag=etag, http_status=304
            )

        payload = response.payload
        if not isinstance(payload, list):
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=200,
                error=(
                    f"unexpected payload shape: expected a JSON array, got {type(payload).__name__}"
                ),
            )

        jobs = tuple(self._raw_job(entry, board) for entry in payload if isinstance(entry, dict))
        return FetchOutcome(
            board=board,
            ok=True,
            jobs=jobs,
            # Single-phase: everything fetched is everything listed. Lever
            # publishes no updated-at field, and needs none — there is no second
            # fetch for a timestamp to gate.
            listed=tuple(
                ListedPosting(source_job_id=job.source_job_id, source_updated_at=None)
                for job in jobs
            ),
            etag=response.etag,
            http_status=response.http_status,
        )
```

Keep each adapter's existing `_raw_job` (or equivalent inline construction) —
this task changes how the payload is obtained and what is reported, not how a
posting is read.

Greenhouse gets the identical treatment, still against
`BOARD_URL` with `content=true`, and builds `listed` from the same `jobs` array
with `source_updated_at` parsed from each entry's `updated_at` via the adapter's
existing timestamp parser.

- [ ] **Step 5: Run every adapter test**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_lever_adapter.py tests/test_ashby_adapter.py tests/test_greenhouse_adapter.py -v
```

Expected: green. Any existing stub client in those files that only implements
`get_json` must gain `get_json_conditional` — that is the intended blast radius.

- [ ] **Step 6: Run the whole suite**

```bash
cd services/api && .venv/bin/python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
make check
git add services/api/nightshift/adapters/ services/api/tests/
git commit -m "feat(adapters): revalidate with If-None-Match on all three providers"
```

---

## Task 4: Greenhouse polls in two phases

**Files:**
- Modify: `services/api/nightshift/adapters/greenhouse.py`
- Test: `services/api/tests/test_greenhouse_adapter.py`
- Create: `services/api/tests/fixtures/greenhouse/datadog_listing.json`
- Create: `services/api/tests/fixtures/greenhouse/datadog_listing.meta.json`
- Create: `services/api/tests/fixtures/greenhouse/datadog_single_job.json`
- Create: `services/api/tests/fixtures/greenhouse/datadog_single_job.meta.json`

**Interfaces:**
- Consumes: Task 3's adapter shape.
- Produces: `GreenhouseAdapter.is_two_phase = True`;
  `GreenhouseAdapter.fetch_postings(board: BoardRef, source_job_ids:
  Sequence[str]) -> tuple[tuple[RawJob, ...], list[str]]` returning the fetched
  postings and the ids that failed. `fetch_board` now returns `jobs=()` and a
  populated `listed`.

**Measured 2026-08-02:** the per-posting payload is byte-identical to the
`content=true` list item — same keys, same values — so `normalize` is reused
unchanged and there is no second normalization path to drift.

- [ ] **Step 1: Record the fixtures**

```bash
cd /Users/tahmudun/Projects/Nightshift
OUTBOUND_HTTP_ENABLED=true SOURCE_REQUESTS_PER_SECOND=0.8 \
  services/api/.venv/bin/python scripts/record_fixture.py \
  --url 'https://boards-api.greenhouse.io/v1/boards/datadog/jobs' \
  --out services/api/tests/fixtures/greenhouse/datadog_listing.json
```

If `record_fixture.py` does not accept `--url`, read it and follow its actual
interface; every fixture in this repo carries a `.meta.json` recording the URL,
the fetch date, the HTTP status, and what coverage the recording does and does
not have. Match that format exactly — `tests/test_fixture_provenance.py`
enforces it.

Trim the listing fixture to ~25 postings to keep the repo small, and note the
trimming in the meta file. Record one single-job fixture for a posting that is
present in the trimmed listing.

- [ ] **Step 2: Write the failing tests**

```python
class TestTwoPhase:
    """ADR 0007: the listing is 14.9x cheaper than content=true on this board."""

    async def test_the_listing_is_fetched_without_content(self) -> None:
        """content=true on a routine poll is the 499 KB path and is a bug."""
        seen: list[str] = []
        client = _url_recording_client(seen, _listing_payload())
        await GreenhouseAdapter(client).fetch_board(BOARD)

        assert seen == ["https://boards-api.greenhouse.io/v1/boards/datadog/jobs"]
        assert "content=true" not in seen[0]

    async def test_fetch_board_lists_without_fetching_content(self) -> None:
        client = _stub_client({LISTING_URL.format(token="datadog"): _listing_response()})
        outcome = await GreenhouseAdapter(client).fetch_board(BOARD)

        assert outcome.ok is True
        assert outcome.jobs == ()
        assert len(outcome.listed) == 25
        assert outcome.is_authoritative_empty is False

    async def test_the_listing_carries_an_updated_at_per_posting(self) -> None:
        """This is the field the phase-2 diff turns on, and Greenhouse is the
        only provider that publishes it."""
        client = _stub_client({LISTING_URL.format(token="datadog"): _listing_response()})
        outcome = await GreenhouseAdapter(client).fetch_board(BOARD)

        assert all(p.source_updated_at is not None for p in outcome.listed)
        assert all(p.source_updated_at.tzinfo is not None for p in outcome.listed)

    async def test_fetch_postings_returns_full_payloads(self) -> None:
        job_id = _first_listed_id()
        client = _stub_client({JOB_URL.format(token="datadog", job_id=job_id): _single_response()})
        fetched, failed = await GreenhouseAdapter(client).fetch_postings(BOARD, [job_id])

        assert failed == []
        assert len(fetched) == 1
        assert fetched[0].source_job_id == job_id
        assert fetched[0].payload["content"]

    async def test_a_posting_that_fails_does_not_lose_the_others(self) -> None:
        """One 404 among ten must not cost the nine."""
        good = _first_listed_id()
        client = _failing_for("999", {JOB_URL.format(token="datadog", job_id=good): _single_response()})
        fetched, failed = await GreenhouseAdapter(client).fetch_postings(BOARD, [good, "999"])

        assert [j.source_job_id for j in fetched] == [good]
        assert failed == ["999"]

    def test_a_single_posting_normalizes_identically_to_a_listing_item(self) -> None:
        """Measured: the two payloads are byte-identical, so one normalizer serves
        both. If Greenhouse ever diverges, this fails rather than silently
        producing two different canonical jobs for one posting."""
        adapter = GreenhouseAdapter(_stub_client({}))
        single = json.loads(SINGLE_FIXTURE.read_text())
        raw = RawJob(
            source_job_id=str(single["id"]),
            source_company_key="datadog",
            canonical_url=single.get("absolute_url"),
            payload=single,
        )
        normalized = adapter.normalize(raw, BOARD)

        assert normalized.title == single["title"]
        assert normalized.description_hash
        assert normalized.source_updated_at is not None
```

- [ ] **Step 3: Run and watch them fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_greenhouse_adapter.py -k TwoPhase -v
```

Expected: `AttributeError: 'GreenhouseAdapter' object has no attribute 'fetch_postings'`.

- [ ] **Step 4: Implement**

```python
#: The cheap request. 33 KB against 499 KB for content=true on the Datadog
#: board (measured 2026-08-02). Carries id, updated_at, location and title —
#: everything freshness needs and nothing it does not.
LISTING_URL: Final = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
#: One posting, with content. 4,852 bytes. Its payload is byte-identical to the
#: same posting inside ?content=true, verified key-by-key on 2026-08-02, which
#: is why `normalize` is reused rather than duplicated.
JOB_URL: Final = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}"
#: Reserved for a board's first ingestion only. Using it on a routine poll is a
#: bug (ADR 0007).
FULL_BOARD_URL: Final = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
```

```python
    is_two_phase = True

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        url = LISTING_URL.format(token=board.token)
        try:
            response = await self._client.get_json_conditional(url, etag=etag)
        except SourceUnavailableError as exc:
            log.warning(
                "greenhouse_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if response.not_modified:
            return FetchOutcome(
                board=board, ok=True, not_modified=True, etag=etag, http_status=304
            )

        payload = response.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            # A 200 with an unexpected shape is a source problem, not evidence
            # of zero jobs. Treat it as unavailable.
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=200,
                error="unexpected payload shape: missing 'jobs' array",
            )

        listed = tuple(
            ListedPosting(
                source_job_id=str(entry["id"]),
                source_updated_at=_parse_timestamp(entry.get("updated_at")),
            )
            for entry in payload["jobs"]
            if isinstance(entry, dict) and entry.get("id") is not None
        )
        # No `jobs`: phase 1 deliberately carries no content. The caller decides
        # which postings changed and calls fetch_postings for those alone.
        return FetchOutcome(
            board=board,
            ok=True,
            listed=listed,
            etag=response.etag,
            http_status=response.http_status,
        )

    async def fetch_postings(
        self, board: BoardRef, source_job_ids: Sequence[str]
    ) -> tuple[tuple[RawJob, ...], list[str]]:
        """Phase 2: pull full content for the postings that changed.

        Returns what succeeded and the ids that did not, rather than raising.
        One posting 404-ing mid-poll must not cost the rest of the board, and it
        must not read as those postings being gone (I3).
        """
        fetched: list[RawJob] = []
        failed: list[str] = []
        for job_id in source_job_ids:
            url = JOB_URL.format(token=board.token, job_id=job_id)
            try:
                response = await self._client.get_json_conditional(url)
            except SourceUnavailableError as exc:
                log.warning(
                    "greenhouse_posting_unavailable",
                    board=board.token,
                    source_job_id=job_id,
                    error=str(exc),
                    http_status=exc.http_status,
                )
                failed.append(job_id)
                continue

            entry = response.payload
            if not isinstance(entry, dict) or entry.get("id") is None:
                failed.append(job_id)
                continue

            fetched.append(
                RawJob(
                    source_job_id=str(entry["id"]),
                    source_company_key=board.token,
                    canonical_url=entry.get("absolute_url"),
                    payload=entry,
                )
            )
        return tuple(fetched), failed
```

Reuse the module's existing timestamp parser for `_parse_timestamp`; if the
existing one is a private method on the adapter, call it as such rather than
adding a second parser.

- [ ] **Step 5: Run and watch them pass**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_greenhouse_adapter.py -v
```

- [ ] **Step 6: Commit**

```bash
make check
git add services/api/nightshift/adapters/greenhouse.py services/api/tests/
git commit -m "feat(greenhouse): two-phase poll, listing then changed postings only"
```

---

## Task 5: Freshness ages against the *listed* set

**This is the task the milestone turns on.** Read design §4 first.

**Files:**
- Modify: `services/api/nightshift/domain/ingestion.py`
- Test: `services/api/tests/test_ingestion.py`

**Interfaces:**
- Consumes: `FetchOutcome.listed_source_job_ids` (Task 2).
- Produces: `mark_listed(session, *, source: Source, token: str,
  source_job_ids: Sequence[str], now: datetime) -> int` returning rows touched;
  `apply_freshness` unchanged in signature.

**The bug being prevented:** `apply_freshness` ages any record with
`last_seen_at < now`. Phase 2 persists only changed postings. So unchanged
postings would take a miss every poll and close on the third — silently, three
polls after the change.

- [ ] **Step 1: Write the failing test**

Add to `services/api/tests/test_ingestion.py`:

```python
class TestTwoPhaseFreshness:
    """M1d design §4. The defect ADR 0007 creates, and the guard against it."""

    @requires_db
    async def test_an_unchanged_posting_takes_no_miss_when_it_is_not_refetched(
        self, session: AsyncSession
    ) -> None:
        """Ten postings listed, one changed and fetched, nine not fetched.

        The nine must take zero misses. Without mark_listed they take one each,
        per poll, and close on the third — the whole board, silently.
        """
        source = await get_or_create_source(
            session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        board = BoardRef(company="Acme", ats="greenhouse", token="acme")
        now = utcnow()

        # First poll: all ten arrive with content.
        for n in range(10):
            await persist_source_job(
                session, source=source,
                raw_job=_raw_job(str(n), "acme"),
                normalized=_normalized(str(n), title=f"Role {n}"),
                now=now,
            )
        await session.flush()

        # Second poll, one hour later: the board lists all ten; only #0 changed,
        # so only #0 is refetched and persisted.
        later = now + timedelta(hours=1)
        await persist_source_job(
            session, source=source,
            raw_job=_raw_job("0", "acme"),
            normalized=_normalized("0", title="Role 0 (updated)"),
            now=later,
        )
        await mark_listed(
            session, source=source, token="acme",
            source_job_ids=[str(n) for n in range(10)], now=later,
        )
        await session.flush()

        closed = await apply_freshness(
            session, source=source, polled_tokens=["acme"],
            run=await _a_run(session, source), now=later,
        )

        records = (
            await session.execute(
                select(SourceJobRecord).where(SourceJobRecord.source_id == source.id)
            )
        ).scalars().all()

        assert closed == 0
        assert len(records) == 10
        assert {r.consecutive_misses for r in records} == {0}, (
            "an unchanged posting that the board still lists must not take a miss"
        )
        assert {r.source_status for r in records} == {SourceStatus.ACTIVE}

    @requires_db
    async def test_a_posting_the_board_stopped_listing_still_takes_a_miss(
        self, session: AsyncSession
    ) -> None:
        """The guard must not become 'nothing ever ages'. Removing a posting from
        the listing is exactly how a real closure starts."""
        source = await get_or_create_source(
            session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        now = utcnow()
        for n in range(3):
            await persist_source_job(
                session, source=source,
                raw_job=_raw_job(str(n), "acme"),
                normalized=_normalized(str(n), title=f"Role {n}"),
                now=now,
            )
        await session.flush()

        later = now + timedelta(hours=1)
        # The board now lists only 0 and 1. Posting 2 is gone.
        await mark_listed(
            session, source=source, token="acme", source_job_ids=["0", "1"], now=later
        )
        await session.flush()
        await apply_freshness(
            session, source=source, polled_tokens=["acme"],
            run=await _a_run(session, source), now=later,
        )

        by_id = {
            r.source_job_id: r
            for r in (
                await session.execute(
                    select(SourceJobRecord).where(SourceJobRecord.source_id == source.id)
                )
            ).scalars().all()
        }
        assert by_id["0"].consecutive_misses == 0
        assert by_id["1"].consecutive_misses == 0
        assert by_id["2"].consecutive_misses == 1
        assert by_id["2"].source_status == SourceStatus.MISSING

    @requires_db
    async def test_marking_listed_does_not_resurrect_a_missing_posting_silently(
        self, session: AsyncSession
    ) -> None:
        """A posting that reappears legitimately resets its miss counter — but
        through the same path a real re-listing takes, not a special case."""
        source = await get_or_create_source(
            session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        now = utcnow()
        await persist_source_job(
            session, source=source,
            raw_job=_raw_job("0", "acme"),
            normalized=_normalized("0", title="Role 0"),
            now=now,
        )
        await session.flush()

        gone = now + timedelta(hours=1)
        await mark_listed(session, source=source, token="acme", source_job_ids=[], now=gone)
        await session.flush()
        await apply_freshness(
            session, source=source, polled_tokens=["acme"],
            run=await _a_run(session, source), now=gone,
        )

        back = now + timedelta(hours=2)
        await mark_listed(session, source=source, token="acme", source_job_ids=["0"], now=back)
        await session.flush()
        await apply_freshness(
            session, source=source, polled_tokens=["acme"],
            run=await _a_run(session, source), now=back,
        )

        record = (
            await session.execute(
                select(SourceJobRecord).where(SourceJobRecord.source_job_id == "0")
            )
        ).scalar_one()
        assert record.consecutive_misses == 0
        assert record.source_status == SourceStatus.ACTIVE
```

Use the test module's existing `_raw_job` / `_normalized` / `requires_db`
helpers. If `_a_run` does not exist, add a two-line helper creating an
`IngestionRun` in `RUNNING` status for the given source.

- [ ] **Step 2: Run and watch them fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_ingestion.py -k TwoPhaseFreshness -v
```

Expected: `NameError: name 'mark_listed' is not defined`.

- [ ] **Step 3: Implement**

Add to `nightshift/domain/ingestion.py`, immediately above `apply_freshness` so
the two read together:

```python
async def mark_listed(
    session: AsyncSession,
    *,
    source: Source,
    token: str,
    source_job_ids: Sequence[str],
    now: datetime,
) -> int:
    """Record that these postings were on the board, without re-reading them.

    This is the seam between the two phases, and the reason M1d does not close
    every unchanged posting on every Greenhouse board.

    ``apply_freshness`` ages any record with ``last_seen_at < now``, on the
    reasoning that persisting a posting sets it to ``now`` so anything older was
    absent from the payload. That reasoning holds only while every listed
    posting is also persisted. Under ADR 0007's phase 2 it is false: an
    unchanged posting is deliberately never refetched, so it would look absent
    and take a miss on every poll.

    "The board listed it" is the fact that keeps a posting open. "We refetched
    its content" is a different, stronger fact, and it belongs to
    ``last_verified_at``, which this function deliberately does not touch.

    Returns the number of records updated.
    """
    if not source_job_ids:
        return 0

    result = await session.execute(
        update(SourceJobRecord)
        .where(
            SourceJobRecord.source_id == source.id,
            SourceJobRecord.source_company_key == token,
            SourceJobRecord.source_job_id.in_(list(source_job_ids)),
        )
        .values(last_seen_at=now, consecutive_misses=0, source_status=SourceStatus.ACTIVE)
    )
    return int(result.rowcount or 0)
```

Add `update` to the SQLAlchemy imports at the top of the module.

Then wire it into `ingest_boards`, replacing the loop body's success branch:

```python
        stats.boards_ok.append(board.token)
        # Set before apply_freshness reads it, or the first poll of a new source
        # would decide `unverified` on a board that just answered.
        source.last_success_at = timestamp

        if outcome.not_modified:
            # I3 at the level ADR 0007 introduced: a 304 says the listing is
            # byte-identical, so nothing is written and nothing is aged. The
            # board's own bookkeeping is the caller's business (Task 7).
            stats.not_modified.append(board.token)
            continue

        # Every posting the board listed is still open, whether or not we
        # refetched its content. See mark_listed.
        await mark_listed(
            session,
            source=source,
            token=board.token,
            source_job_ids=outcome.listed_source_job_ids,
            now=timestamp,
        )

        if adapter.is_two_phase:
            changed = await _postings_needing_content(
                session, source=source, outcome=outcome
            )
            fetched, failed_ids = await adapter.fetch_postings(board, changed)
            for job_id in failed_ids:
                stats.failed += 1
                stats.errors.append(f"{board.ats}:{board.token}: fetch posting {job_id}")
            outcome = outcome.model_copy(update={"jobs": fetched})

        await _persist_outcome(session, adapter, outcome, source=source, stats=stats, now=timestamp)
```

A `304` board must still count as polled for freshness, and it does: it is in
`stats.boards_ok`, and `apply_freshness` will find no record with
`last_seen_at < now`… **which is wrong.** A `304` board's records were last
seen at the *previous* poll, so they are all older than `now` and would all age.

Guard it in `apply_freshness` by passing only the boards that produced a
listing. Change the call site:

```python
    # Only the boards that answered with a listing. A failed board contributes
    # no evidence; a 304 board contributes no *new* evidence, and ageing its
    # records against a timestamp it never wrote would close the entire board.
    stats.closed = await apply_freshness(
        session, source=source, polled_tokens=stats.boards_listed, run=run, now=timestamp
    )
```

Add both fields to `IngestionStats`:

```python
    #: Boards that answered 304. Polled successfully, wrote nothing.
    not_modified: list[str] = field(default_factory=list)
    #: Boards that answered with a listing. Only these may age records.
    boards_listed: list[str] = field(default_factory=list)
```

and append `board.token` to `boards_listed` in the non-304 path.

Add the helper:

```python
async def _postings_needing_content(
    session: AsyncSession, *, source: Source, outcome: FetchOutcome
) -> list[str]:
    """Which listed postings we must refetch: new ones, and ones that changed.

    Greenhouse publishes ``updated_at`` on the listing, which is what makes this
    diff possible. Lever and Ashby publish no such field and need none — their
    board response already carries every posting in full, so ``is_two_phase`` is
    False and this function is never reached for them.

    A posting whose stored timestamp is NULL is refetched. That is the
    conservative direction: refetching costs one request, while skipping it
    means never seeing a change.
    """
    known = {
        row.source_job_id: row.source_updated_at
        for row in (
            await session.execute(
                select(
                    SourceJobRecord.source_job_id,
                    SourceJobRecord.source_updated_at,
                ).where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key == outcome.board.token,
                )
            )
        ).all()
    }
    return [
        posting.source_job_id
        for posting in outcome.listed
        if posting.source_job_id not in known
        or known[posting.source_job_id] is None
        or posting.source_updated_at is None
        or posting.source_updated_at > known[posting.source_job_id]
    ]
```

**`source_job_records` has no `source_updated_at` column today.** Add it in
Task 6's migration alongside `board_poll_state`, and set it in
`persist_source_job` from `normalized.source_updated_at`. Without it the diff
has nothing to compare and every poll refetches every posting — correct, but it
throws away the entire saving.

- [ ] **Step 4: Run and watch them pass**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_ingestion.py -v
```

- [ ] **Step 5: The mutation check that matters most**

In `ingest_boards`, delete the `mark_listed` call. Re-run:

```bash
cd services/api && .venv/bin/python -m pytest tests/test_ingestion.py -k TwoPhaseFreshness -v
```

`test_an_unchanged_posting_takes_no_miss_when_it_is_not_refetched` must fail
with nine records at `consecutive_misses == 1`. Restore the call.

Then delete the `boards_listed` change so `304` boards age: no existing test
catches it yet — **write one** before restoring:

```python
    @requires_db
    async def test_a_304_board_does_not_age_its_own_postings(
        self, session: AsyncSession
    ) -> None:
        """A 304 says nothing changed. Ageing against a timestamp the board never
        wrote would close every posting on it — the exact I3 failure at the level
        ADR 0007 introduced."""
        source = await get_or_create_source(
            session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        now = utcnow()
        for n in range(5):
            await persist_source_job(
                session, source=source,
                raw_job=_raw_job(str(n), "acme"),
                normalized=_normalized(str(n), title=f"Role {n}"),
                now=now,
            )
        await session.flush()

        board = BoardRef(company="Acme", ats="greenhouse", token="acme")
        adapter = _adapter_returning(
            FetchOutcome(board=board, ok=True, not_modified=True, etag='W/"abc"', http_status=304)
        )
        _run, stats = await ingest_boards(session, adapter, [board], source=source, now=now + timedelta(hours=1))

        records = (
            await session.execute(
                select(SourceJobRecord).where(SourceJobRecord.source_id == source.id)
            )
        ).scalars().all()

        assert stats.not_modified == ["acme"]
        assert stats.closed == 0
        assert {r.consecutive_misses for r in records} == {0}
        assert len(records) == 5
```

`_adapter_returning` is a three-line stub adapter with `is_two_phase = False`,
`parser_version = "1"`, a `fetch_board` returning the given outcome, and a
`normalize` that raises — it must never be called.

- [ ] **Step 6: Commit**

```bash
make check
git add services/api/nightshift/domain/ingestion.py services/api/tests/test_ingestion.py
git commit -m "fix(ingestion): age freshness against listed postings, not fetched ones"
```

---

## Task 6: `board_poll_state`

**Files:**
- Modify: `services/api/nightshift/db/base.py` (add `BoardTier`)
- Modify: `services/api/nightshift/db/models.py` (add `BoardPollState`,
  add `Job`-side nothing, add `source_updated_at` to `SourceJobRecord`)
- Modify: `services/api/nightshift/domain/ingestion.py` (`persist_source_job`
  sets `source_updated_at`)
- Create: `services/api/migrations/versions/20260802_XXXX_board_poll_state.py`
- Test: `services/api/tests/test_models.py`, `tests/test_migrations.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BoardTier` (`StrEnum`: `HOT = "hot"`, `WARM = "warm"`);
  `BoardPollState` ORM model, table `board_poll_state`, unique `(ats, token)`.

- [ ] **Step 1: Write the failing test**

```python
class TestBoardPollState:
    @requires_db
    async def test_a_board_is_unique_per_ats_and_token(self, session: AsyncSession) -> None:
        """Two rows for one board means two schedules and double the requests."""
        source = await get_or_create_source(
            session, name="ashby", source_type=SourceType.ATS_ASHBY,
            base_url="https://api.ashbyhq.com",
        )
        for _ in range(2):
            session.add(
                BoardPollState(
                    source_id=source.id, ats="ashby", token="ramp",
                    tier=BoardTier.WARM, parser_version="1", next_poll_at=utcnow(),
                )
            )
        with pytest.raises(IntegrityError):
            await session.flush()

    @requires_db
    async def test_the_same_token_on_two_providers_is_two_boards(
        self, session: AsyncSession
    ) -> None:
        """`ramp` on Ashby and `ramp` on Greenhouse are different boards. The
        uniqueness is on the pair, and getting that wrong silently drops one."""
        gh = await get_or_create_source(
            session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        ashby = await get_or_create_source(
            session, name="ashby", source_type=SourceType.ATS_ASHBY,
            base_url="https://api.ashbyhq.com",
        )
        session.add(BoardPollState(source_id=gh.id, ats="greenhouse", token="ramp",
                                   tier=BoardTier.WARM, parser_version="1", next_poll_at=utcnow()))
        session.add(BoardPollState(source_id=ashby.id, ats="ashby", token="ramp",
                                   tier=BoardTier.WARM, parser_version="1", next_poll_at=utcnow()))
        await session.flush()  # must not raise

    @requires_db
    async def test_next_poll_at_rejects_a_naive_datetime(self, session: AsyncSession) -> None:
        """UTCDateTime guards the boundary; a naive timestamp here would mean a
        board scheduled in an unknown timezone."""
        source = await get_or_create_source(
            session, name="ashby", source_type=SourceType.ATS_ASHBY,
            base_url="https://api.ashbyhq.com",
        )
        with pytest.raises((ValueError, StatementError)):
            session.add(
                BoardPollState(
                    source_id=source.id, ats="ashby", token="ramp", tier=BoardTier.WARM,
                    parser_version="1", next_poll_at=datetime(2026, 8, 2),  # noqa: DTZ001
                )
            )
            await session.flush()
```

- [ ] **Step 2: Run and watch it fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_models.py -k BoardPollState -v
```

- [ ] **Step 3: Add the enum and model**

In `nightshift/db/base.py`, beside the other `StrEnum`s:

```python
class BoardTier(enum.StrEnum):
    """How often a board is polled. Derived from postings, never hand-set.

    ADR 0007 rejected a weekly tier: a company's first NYC posting could sit
    unseen for six days, which breaks the one promise the product makes.
    """

    HOT = "hot"
    WARM = "warm"
```

In `nightshift/db/models.py`:

```python
class BoardPollState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What polling knows about one board.

    The registry YAML stays the declarative source of which boards exist; this
    is runtime state about them, and the two are deliberately separate tables of
    knowledge. The name says which one this is.
    """

    __tablename__ = "board_poll_state"
    __table_args__ = (
        UniqueConstraint("ats", "token", name="uq_board_poll_state_ats_token"),
        # The scheduler's only query (design §7).
        Index("ix_board_poll_state_next_poll_at", "next_poll_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    ats: Mapped[str] = mapped_column(String(50), nullable=False)
    token: Mapped[str] = mapped_column(String(200), nullable=False)

    #: The last ETag the provider served for this board's listing.
    etag: Mapped[str | None] = mapped_column(String(500))
    #: ADR 0007: a stored ETag is only valid for the parser that earned it. When
    #: this differs from the adapter's current value the ETag is discarded, so a
    #: parser change cannot mean the new parser never sees the payload.
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)

    tier: Mapped[BoardTier] = mapped_column(
        _enum(BoardTier, "board_tier"), nullable=False, server_default=BoardTier.WARM.value
    )
    next_poll_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: 200 or 304. A failure does not move it, so "how long since this board
    #: actually answered" stays answerable.
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    source: Mapped[Source] = relationship()
```

Add to `SourceJobRecord`:

```python
    #: The provider's own last-modified stamp, when it publishes one. Greenhouse
    #: does; Lever and Ashby do not (measured 2026-08-02) and leave it NULL.
    #: This is what the phase-2 diff compares against, and a NULL means refetch.
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
```

In `persist_source_job`, set it wherever the other normalized fields are copied
onto the record: `record.source_updated_at = normalized.source_updated_at`.

- [ ] **Step 4: Generate and then *read* the migration**

```bash
cd /Users/tahmudun/Projects/Nightshift && make migrate-autogenerate name=board_poll_state
```

If that target does not exist, run alembic directly from `services/api`.

**Read the generated file before running it.** M1b recorded three separate
autogenerate defects in one migration — a missing `pgvector` import, a missing
`nightshift.db.types` import, and a `CREATE TYPE` for an enum that already
existed. Check specifically:

1. `UTCDateTime` columns render as `nightshift.db.types.UTCDateTime()` and the
   module is imported at the top of the migration.
2. The `board_tier` enum is created in `upgrade()` **and dropped in
   `downgrade()`**. A downgrade that forgets `DROP TYPE` leaves it behind and
   the round-trip test catches it — do not make it catch it.
3. `source_job_records.source_updated_at` is added and dropped.
4. No spurious drops of anything M1c added.

- [ ] **Step 5: Verify the round trip against a live database**

```bash
cd /Users/tahmudun/Projects/Nightshift
make up && make migrate
make migrate-down && make migrate
```

Expected: clean both directions. Then confirm the enum is genuinely gone after a
downgrade:

```bash
docker compose -f infra/docker-compose.yml exec -T postgres \
  psql -U nightshift -d nightshift -c "\dT"
```

- [ ] **Step 6: Run the tests**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py -v
```

- [ ] **Step 7: Commit**

```bash
make check
git add services/api/nightshift/db/ services/api/migrations/ services/api/nightshift/domain/ingestion.py services/api/tests/
git commit -m "feat(db): board_poll_state, board_tier enum, and source_updated_at"
```

---

## Task 7: Poll one board, and schedule the due ones

**Files:**
- Create: `services/api/nightshift/domain/polling.py`
- Modify: `services/api/nightshift/workers/tasks.py`
- Modify: `services/api/nightshift/workers/main.py`
- Modify: `services/api/nightshift/config.py`
- Test: `services/api/tests/test_polling.py` (create)

**Interfaces:**
- Consumes: `BoardPollState` (Task 6), adapters (Tasks 3–4),
  `ingest_boards` (Task 5).
- Produces:
  - `nightshift/domain/polling.py`:
    - `ADAPTERS: dict[str, type]` — ats name → adapter class.
    - `async def sync_board_poll_state(session, *, now: datetime) -> int` —
      creates a `BoardPollState` row for every pollable registry board that
      lacks one, due immediately. Returns rows created.
    - `async def due_boards(session, *, now: datetime, limit: int = 500)
      -> list[BoardPollState]`.
    - `async def poll_one_board(session, client, *, ats: str, token: str,
      now: datetime) -> BoardPollState` — the whole cycle for one board.
    - `def next_interval(tier: BoardTier) -> timedelta`.
    - `def failure_backoff(consecutive_failures: int) -> timedelta`.
  - `nightshift/workers/tasks.py`: `poll_board(ctx, ats, token)` and
    `enqueue_due_boards(ctx)`.

- [ ] **Step 1: Add the settings**

In `nightshift/config.py`, beside the other source settings:

```python
    # --- Polling (M1d, ADR 0007) -------------------------------------------
    poll_hot_interval_seconds: int = Field(default=3600, ge=60)
    poll_warm_interval_seconds: int = Field(default=86_400, ge=60)
    #: Caps one scheduler tick. At 22 boards it never binds. It exists so a
    #: scheduler waking after an outage, with every board overdue, drains over
    #: several ticks instead of queueing the whole registry at once.
    poll_enqueue_batch_limit: int = Field(default=500, ge=1, le=10_000)
    poll_backoff_base_seconds: int = Field(default=900, ge=1)
    poll_backoff_max_seconds: int = Field(default=86_400, ge=60)
```

Every new setting needs a line in `.env.example` with the same default, or
`tests/test_env_example.py` fails. Add them, unquoted (all are plain integers,
no shell metacharacters).

- [ ] **Step 2: Write the failing tests**

Create `services/api/tests/test_polling.py`:

```python
"""One board's poll cycle, and the scheduler that decides when it happens.

ADR 0007 and docs/architecture/conditional-polling.md §7.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from nightshift.db.base import BoardTier
from nightshift.db.models import BoardPollState
from nightshift.db.types import utcnow
from nightshift.domain.polling import (
    due_boards,
    failure_backoff,
    next_interval,
    poll_one_board,
    sync_board_poll_state,
)
from tests.conftest import requires_db


class TestIntervals:
    def test_hot_is_hourly_and_warm_is_daily(self) -> None:
        assert next_interval(BoardTier.HOT) == timedelta(hours=1)
        assert next_interval(BoardTier.WARM) == timedelta(days=1)

    def test_backoff_grows_and_then_stops(self) -> None:
        """A dead board must stop costing requests, but must not fall out of the
        system — the ceiling matches the warm tier so it is still noticed daily."""
        assert failure_backoff(0) == timedelta(minutes=15)
        assert failure_backoff(1) == timedelta(minutes=30)
        assert failure_backoff(2) == timedelta(hours=1)
        assert failure_backoff(20) == timedelta(hours=24)

    def test_backoff_never_returns_zero(self) -> None:
        """A zero backoff is a hot loop against a failing provider."""
        assert all(failure_backoff(n) > timedelta(0) for n in range(0, 50))


class TestScheduling:
    @requires_db
    async def test_only_due_boards_are_returned(self, session) -> None:
        now = utcnow()
        await _a_board(session, token="due", next_poll_at=now - timedelta(minutes=1))
        await _a_board(session, token="notdue", next_poll_at=now + timedelta(hours=1))
        await session.flush()

        due = await due_boards(session, now=now)
        assert [b.token for b in due] == ["due"]

    @requires_db
    async def test_the_batch_limit_is_honoured(self, session) -> None:
        """A scheduler waking after an outage must not queue the whole registry."""
        now = utcnow()
        for n in range(10):
            await _a_board(session, token=f"b{n}", next_poll_at=now - timedelta(minutes=n + 1))
        await session.flush()

        due = await due_boards(session, now=now, limit=3)
        assert len(due) == 3
        # Longest-overdue first, so nothing starves.
        assert [b.token for b in due] == ["b9", "b8", "b7"]

    @requires_db
    async def test_sync_creates_a_row_per_pollable_registry_board(self, session) -> None:
        created = await sync_board_poll_state(session, now=utcnow())
        await session.flush()

        rows = (await session.execute(select(BoardPollState))).scalars().all()
        assert created == len(rows)
        assert created >= 3  # datadog, alloy, ramp at minimum
        assert ("greenhouse", "datadog") in {(r.ats, r.token) for r in rows}

    @requires_db
    async def test_sync_is_idempotent(self, session) -> None:
        """Run on every scheduler tick; it must not duplicate or reset a board."""
        now = utcnow()
        await sync_board_poll_state(session, now=now)
        await session.flush()
        first = (await session.execute(select(BoardPollState))).scalars().all()
        for row in first:
            row.next_poll_at = now + timedelta(hours=5)
        await session.flush()

        created = await sync_board_poll_state(session, now=now)
        await session.flush()
        second = (await session.execute(select(BoardPollState))).scalars().all()

        assert created == 0
        assert len(second) == len(first)
        assert all(r.next_poll_at == now + timedelta(hours=5) for r in second)

    @requires_db
    async def test_a_disabled_board_gets_no_row(self, session) -> None:
        """Stripe is `disabled`. A poll state row for it would poll it."""
        await sync_board_poll_state(session, now=utcnow())
        await session.flush()
        rows = (await session.execute(select(BoardPollState))).scalars().all()
        assert ("greenhouse", "stripe") not in {(r.ats, r.token) for r in rows}


class TestPollCycle:
    @requires_db
    async def test_a_304_writes_no_job_state_and_reschedules(self, session) -> None:
        """M1 criterion 13, at the level a human runs it."""
        state = await _a_board(session, token="acme", next_poll_at=utcnow(), etag='W/"abc"')
        await session.flush()
        before = await _job_state_snapshot(session)

        now = utcnow()
        client = _client_returning_304()
        result = await poll_one_board(session, client, ats="greenhouse", token="acme", now=now)
        await session.flush()

        assert result.last_status == 304
        assert result.etag == 'W/"abc"'  # unchanged, still valid
        assert result.consecutive_failures == 0
        assert result.last_success_at == now
        assert result.next_poll_at == now + timedelta(days=1)
        assert await _job_state_snapshot(session) == before

    @requires_db
    async def test_a_failure_backs_off_and_closes_nothing(self, session) -> None:
        state = await _a_board(session, token="acme", next_poll_at=utcnow())
        await session.flush()
        before = await _job_state_snapshot(session)

        now = utcnow()
        result = await poll_one_board(
            session, _client_raising(), ats="greenhouse", token="acme", now=now
        )
        await session.flush()

        assert result.consecutive_failures == 1
        assert result.last_error is not None
        assert result.last_success_at is None
        assert result.next_poll_at == now + timedelta(minutes=15)
        assert await _job_state_snapshot(session) == before

    @requires_db
    async def test_a_stale_parser_version_discards_the_stored_etag(self, session) -> None:
        """ADR 0007. A changed parser plus a stale ETag means the new parser
        never sees the payload it was written for."""
        seen: list[str | None] = []
        await _a_board(
            session, token="acme", next_poll_at=utcnow(),
            etag='W/"abc"', parser_version="0",
        )
        await session.flush()

        await poll_one_board(
            session, _client_recording(seen), ats="greenhouse", token="acme", now=utcnow()
        )
        assert seen == [None], "a stale ETag must not be sent"

    @requires_db
    async def test_a_current_parser_version_keeps_the_etag(self, session) -> None:
        seen: list[str | None] = []
        await _a_board(
            session, token="acme", next_poll_at=utcnow(),
            etag='W/"abc"', parser_version="1",
        )
        await session.flush()

        await poll_one_board(
            session, _client_recording(seen), ats="greenhouse", token="acme", now=utcnow()
        )
        assert seen == ['W/"abc"']
```

`_job_state_snapshot` returns a tuple of counts and miss sums across
`source_job_records`, `jobs`, `job_locations`, `job_source_links`,
`job_status_events`, `job_embeddings` — the concrete form of "zero writes to job
state" from design §5:

```python
async def _job_state_snapshot(session) -> tuple[int, ...]:
    counts = []
    for model in (SourceJobRecord, Job, JobLocation, JobSourceLink, JobStatusEvent, JobEmbedding):
        counts.append(
            (await session.execute(select(func.count()).select_from(model))).scalar_one()
        )
    counts.append(
        (await session.execute(select(func.coalesce(func.sum(SourceJobRecord.consecutive_misses), 0)))).scalar_one()
    )
    counts.append(
        (await session.execute(select(func.count()).select_from(Job).where(Job.status == JobStatus.CLOSED))).scalar_one()
    )
    return tuple(counts)
```

Before running these, check that every test in this class actually reaches the
branch it names. M1c shipped `test_validation_never_raises` whose stub route key
matched no URL, so the stub raised "no route" and the test passed without ever
entering the branch it existed to cover. The stub clients here have the same
shape and the same failure mode: assert the stub was *called* with the URL you
expect, not merely that the call returned.

- [ ] **Step 3: Run and watch them fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_polling.py -v
```

- [ ] **Step 4: Implement `polling.py`**

```python
"""Polling one board, and deciding when each board is next due.

ADR 0007 and docs/architecture/conditional-polling.md §7. The scheduling shape
is `next_poll_at` on the board row drained by a small cron, rather than a cron
per tier: boards drift apart instead of stampeding at :00, per-board backoff has
somewhere to live, "what is overdue" is a query the coverage page already needs,
and the state survives a worker restart because it is in Postgres rather than in
the queue.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.ashby import AshbyAdapter
from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.lever import LeverAdapter
from nightshift.config import get_settings
from nightshift.db.base import BoardTier, SourceType
from nightshift.db.models import BoardPollState
from nightshift.db.types import utcnow
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.registry import get_registry

log = structlog.get_logger(__name__)

ADAPTERS: dict[str, tuple[type, SourceType, str]] = {
    "greenhouse": (GreenhouseAdapter, SourceType.ATS_GREENHOUSE, "https://boards-api.greenhouse.io"),
    "lever": (LeverAdapter, SourceType.ATS_LEVER, "https://api.lever.co"),
    "ashby": (AshbyAdapter, SourceType.ATS_ASHBY, "https://api.ashbyhq.com"),
}


def next_interval(tier: BoardTier) -> timedelta:
    settings = get_settings()
    seconds = (
        settings.poll_hot_interval_seconds
        if tier is BoardTier.HOT
        else settings.poll_warm_interval_seconds
    )
    return timedelta(seconds=seconds)


def failure_backoff(consecutive_failures: int) -> timedelta:
    """Board-level backoff: 15 minutes doubling to a 24-hour ceiling.

    Separate from PoliteClient's per-request retry backoff, which handles one
    flaky response and is measured in seconds. This one handles a board that is
    simply gone. The ceiling matches the warm tier so a board that comes back is
    noticed within a day rather than falling out of the system.
    """
    settings = get_settings()
    seconds = min(
        settings.poll_backoff_base_seconds * (2**consecutive_failures),
        settings.poll_backoff_max_seconds,
    )
    return timedelta(seconds=seconds)
```

`sync_board_poll_state` reads `get_registry().pollable()`, skips
`(ats, token)` pairs that already have a row, and inserts the rest with
`next_poll_at=now`, `tier=BoardTier.WARM`, and the adapter's `parser_version`.
Use `ON CONFLICT DO NOTHING` on the unique constraint — M1a made
`get_or_create_source` an upsert for exactly this reason, and this row is
created from a worker that will soon run concurrently.

`due_boards` is `select(BoardPollState).where(next_poll_at <= now)
.order_by(next_poll_at).limit(limit)`.

`poll_one_board` resolves the adapter from `ADAPTERS[ats]`, loads the row, sends
the stored ETag **only when `row.parser_version == adapter.parser_version`**,
calls `ingest_boards` with that single board, then writes the outcome back onto
the row: on success `last_success_at = now`, `consecutive_failures = 0`,
`last_error = None`, `etag` from the outcome (keeping the old value on a `304`),
`next_poll_at = now + next_interval(row.tier)`; on failure
`consecutive_failures += 1`, `last_error` set, `next_poll_at = now +
failure_backoff(previous_failures)`. `last_polled_at = now` and `last_status`
always.

- [ ] **Step 5: Add the worker tasks**

In `nightshift/workers/tasks.py`:

```python
async def poll_board(ctx: dict[str, Any], ats: str, token: str) -> dict[str, Any]:
    """Poll exactly one board. One ARQ job per board (ADR 0007).

    Individual rather than a loop inside one long task, so going from 22 boards
    to 100,000 is a worker-count question rather than a rewrite.
    """
    async with PoliteClient() as client, session_scope() as session:
        state = await poll_one_board(session, client, ats=ats, token=token, now=utcnow())
        return {
            "ats": ats,
            "token": token,
            "status": state.last_status,
            "next_poll_at": state.next_poll_at.isoformat(),
            "consecutive_failures": state.consecutive_failures,
        }


async def enqueue_due_boards(ctx: dict[str, Any]) -> dict[str, Any]:
    """Queue every board whose next_poll_at has passed."""
    settings = get_settings()
    redis = ctx["redis"]
    now = utcnow()
    async with session_scope() as session:
        created = await sync_board_poll_state(session, now=now)
        due = await due_boards(session, now=now, limit=settings.poll_enqueue_batch_limit)
        tokens = [(board.ats, board.token) for board in due]
        # Push next_poll_at forward before the jobs run, so a slow poll cannot be
        # enqueued twice by the following tick.
        for board in due:
            board.next_poll_at = now + next_interval(board.tier)

    for ats, token in tokens:
        await redis.enqueue_job("poll_board", ats, token)

    return {"boards_created": created, "enqueued": len(tokens)}
```

Keep `ingest_greenhouse` as it is — it is what `make demo` and the CLI use.

In `nightshift/workers/main.py`, register `poll_board` and `enqueue_due_boards`
in `functions`, and add a cron for `enqueue_due_boards` every five minutes.
Leave the existing hourly `ingest_greenhouse` cron alone.

- [ ] **Step 6: Write the double-enqueue test**

```python
    @requires_db
    async def test_a_board_is_not_enqueued_twice_by_consecutive_ticks(self, session) -> None:
        """A poll slower than the tick interval must not stack up jobs against
        one provider — that is the retry storm §7.3 forbids, self-inflicted."""
        now = utcnow()
        await _a_board(session, token="slow", next_poll_at=now - timedelta(minutes=1))
        await session.flush()

        first = await due_boards(session, now=now, limit=500)
        for board in first:
            board.next_poll_at = now + next_interval(board.tier)
        await session.flush()

        second = await due_boards(session, now=now + timedelta(minutes=5), limit=500)
        assert [b.token for b in first] == ["slow"]
        assert second == []
```

- [ ] **Step 7: Run and commit**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_polling.py -v
cd /Users/tahmudun/Projects/Nightshift && make check
git add services/api/nightshift/domain/polling.py services/api/nightshift/workers/ services/api/nightshift/config.py .env.example services/api/tests/test_polling.py
git commit -m "feat(polling): queue-driven per-board polling with next_poll_at scheduling"
```

---

## Task 8: Tiers, derived from postings

**Files:**
- Create: `services/api/nightshift/domain/tiers.py`
- Modify: `services/api/nightshift/domain/polling.py` (recompute after a poll)
- Test: `services/api/tests/test_tiers.py` (create)

**Interfaces:**
- Consumes: `BoardPollState` (Task 6).
- Produces: `async def derive_tier(session, *, source_id: UUID, token: str,
  now: datetime) -> BoardTier`; `NYC_WINDOW: Final[timedelta]` of 30 days.

**Rule:** hot when the board has an open NYC posting, or had one seen in the
last 30 days. Read from `job_locations`, never from `nyc_presence` in the YAML.

- [ ] **Step 1: Write the failing tests**

```python
class TestTierDerivation:
    @requires_db
    async def test_a_board_with_an_open_nyc_posting_is_hot(self, session) -> None: ...

    @requires_db
    async def test_a_board_with_no_nyc_postings_is_warm(self, session) -> None: ...

    @requires_db
    async def test_a_board_that_loses_its_nyc_postings_demotes(self, session) -> None:
        """A tier that can only be entered eventually contains everything."""

    @requires_db
    async def test_a_recently_closed_nyc_posting_still_counts_for_30_days(
        self, session
    ) -> None:
        """An employer that just closed its NYC role is still an NYC employer.
        Demoting instantly would mean missing their next one by up to a day."""

    @requires_db
    async def test_nyc_presence_in_the_registry_is_not_consulted(self, session) -> None:
        """ADR 0007: a board is hot because of what its postings said. Set the
        YAML flag true on a board with no NYC postings and it must stay warm."""

    @requires_db
    async def test_a_remote_posting_is_not_an_nyc_posting(self, session) -> None:
        """Ashby's isRemote is true on 33 postings sitting at the New York
        office (measured in M1a), so remote-ness cannot stand in for location."""
```

Write each body out in full when implementing — seed a board, postings and
`job_locations` rows through the real `persist_source_job` path rather than by
inserting `JobLocation` directly, so the location parser is exercised and a
change in what counts as NYC shows up here.

- [ ] **Step 2: Implement**

`derive_tier` joins `job_locations` → `jobs` → `job_source_links` →
`source_job_records`, filtered to `source_id` and `source_company_key == token`,
counting rows where the location is New York City and either the job is open or
`last_seen_at >= now - NYC_WINDOW`.

Reuse whatever `coverage.py` already uses to decide NYC-ness rather than writing
a second definition — grep for it first. Two definitions of "is this NYC" is how
the coverage page and the tiers start disagreeing.

- [ ] **Step 3: Call it from `poll_one_board`**

After a successful poll that produced a listing, set
`row.tier = await derive_tier(...)` before computing `next_poll_at`, so a board
promoted this poll gets its hourly interval immediately.

Do **not** recompute on a `304` — nothing changed, so the tier cannot have.

- [ ] **Step 4: Assert `nyc_presence` is unread**

```python
def test_no_polling_code_reads_nyc_presence() -> None:
    """board-discovery.md §16 anticipates deleting this field. Until then, prove
    nothing in the polling path depends on it, so the deletion stays a cleanup
    rather than a behaviour change."""
    for module in (polling, tiers):
        source = inspect.getsource(module)
        assert "nyc_presence" not in source
```

- [ ] **Step 5: Commit**

```bash
make check
git add services/api/nightshift/domain/tiers.py services/api/nightshift/domain/polling.py services/api/tests/test_tiers.py
git commit -m "feat(polling): derive hot/warm tiers from ingested postings"
```

---

## Task 9: A row lock in `merge_jobs`

**Files:**
- Modify: `services/api/nightshift/domain/ingestion.py`
- Test: `services/api/tests/test_dedupe.py`

**Interfaces:** `merge_jobs` keeps its signature.

**Why now:** named in the M1b review as the one thing M1d must not inherit
unnoticed. Unreachable at one worker; routine the moment Task 7's per-board jobs
run concurrently. Two workers can each decide postings A and B are duplicates
and each delete the other's survivor.

- [ ] **Step 1: Write the failing test**

Two real concurrent transactions against the live database — not two calls in
one session, which cannot reproduce the race:

```python
    @requires_db
    async def test_two_workers_merging_the_same_pair_leave_one_survivor(
        self, engine: AsyncEngine
    ) -> None:
        """The M1b review's carried defect, made reachable by M1d.

        Both transactions decide A and B are duplicates. Without a lock each
        deletes the other's winner and the pair vanishes, or one raises on a
        row that is already gone.
        """
        job_a, job_b = await _two_duplicate_jobs(engine)

        async def merge(first: UUID, second: UUID) -> None:
            async with AsyncSession(engine) as session, session.begin():
                await merge_jobs(session, winner_id=first, loser_id=second, reason="identical_content")

        results = await asyncio.gather(
            merge(job_a, job_b), merge(job_b, job_a), return_exceptions=True
        )

        async with AsyncSession(engine) as session:
            survivors = (
                await session.execute(select(Job).where(Job.id.in_([job_a, job_b])))
            ).scalars().all()
            links = (
                await session.execute(
                    select(JobSourceLink).where(JobSourceLink.job_id == survivors[0].id)
                )
            ).scalars().all()

        assert len(survivors) == 1, f"expected one survivor, got {len(survivors)}"
        assert len(links) == 2, "the survivor must carry both source links"
        assert not any(isinstance(r, Exception) for r in results), results
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_dedupe.py -k two_workers -v
```

Expected: zero or two survivors, or an exception in `results`. Run it several
times — it is a race and may not fail every run. If it passes three times
running, add `await asyncio.sleep(0)` between the read and the delete inside
`merge_jobs` to widen the window, confirm the failure, then remove it.

- [ ] **Step 3: Implement**

At the top of `merge_jobs`, before reading either job:

```python
    # Lock both rows in primary-key order. Deterministic ordering is what makes
    # two workers that picked the pair in opposite directions queue behind each
    # other instead of deadlocking.
    ordered = sorted([winner_id, loser_id])
    locked = (
        await session.execute(
            select(Job).where(Job.id.in_(ordered)).order_by(Job.id).with_for_update()
        )
    ).scalars().all()

    if len(locked) < 2:
        # The other worker already merged this pair and deleted one of them.
        # Nothing to do, and emphatically not an error.
        log.info("merge_already_applied", winner_id=str(winner_id), loser_id=str(loser_id))
        return
```

Confirm the existing return type allows this early return; if `merge_jobs`
returns a value, return the surviving job by re-reading it.

- [ ] **Step 4: Run it repeatedly**

```bash
cd services/api && for i in 1 2 3 4 5; do .venv/bin/python -m pytest tests/test_dedupe.py -k two_workers -q || break; done
```

- [ ] **Step 5: Commit**

```bash
make check
git add services/api/nightshift/domain/ingestion.py services/api/tests/test_dedupe.py
git commit -m "fix(dedupe): lock both rows in merge_jobs before merging"
```

---

## Task 10: `promote` stops destroying comments, and the 19 boards land

**Files:**
- Modify: `services/api/nightshift/discovery/approve.py`
- Modify: `services/api/tests/test_registry.py`
- Modify: `data/board-registry.yaml` (generated, then committed)
- Test: `services/api/tests/discovery/test_approve.py`

**Interfaces:** `promote` keeps its signature.

**The defect:** `promote`'s docstring says "Additive, never destructive." In the
data sense it is — verified semantically on 2026-08-02: promoting 19 boards left
all four existing entries identical and re-enabled nothing. But it rebuilds the
file with `yaml.safe_dump`, preserving only the leading comment block, and the
first real `--write` in this project's history deleted ten lines of rationale
from between the entries — including the `Stripe` note reading *"enable once the
freshness and closure state machine lands"*, a message to this very milestone,
deleted by approving unrelated boards.

- [ ] **Step 1: Write the failing test**

```python
    def test_promotion_preserves_comments_between_entries(self, tmp_path: Path) -> None:
        """The registry's rationale lives in comments, and a round-trip through
        yaml.safe_dump silently eats every one that is not at the top of the
        file. M1c could not catch this: it deliberately never wrote."""
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(
            "# Header comment, survives today.\n"
            "boards:\n"
            "  # Why Datadog: NYC HQ, and its location strings are the messiest\n"
            "  # available, which is useful for a project whose first invariant\n"
            "  # is about not fabricating locations.\n"
            "  - company: Datadog\n"
            "    ats: greenhouse\n"
            "    token: datadog\n"
            "    added: 2026-07-29\n"
            "    status: active\n"
            "    nyc_presence: true\n"
            "\n"
            "  # Disabled until the closure state machine lands.\n"
            "  - company: Stripe\n"
            "    ats: greenhouse\n"
            "    token: stripe\n"
            "    added: 2026-07-29\n"
            "    status: disabled\n"
            "    nyc_presence: true\n"
        )
        before = registry.read_text()

        count, _ = promote(_a_candidate_file(), registry_path=registry, today=date(2026, 8, 2))
        after = registry.read_text()

        assert count == 1
        assert before in after, "every existing byte must survive; promotion appends"
        assert "Why Datadog" in after
        assert "Disabled until the closure state machine lands." in after

    def test_promotion_does_not_requote_existing_dates(self, tmp_path: Path) -> None:
        """A round-trip turns `added: 2026-07-29` into a date object and back,
        while new entries are written as strings — leaving one file with two
        conventions."""
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(
            "boards:\n"
            "  - company: Datadog\n    ats: greenhouse\n    token: datadog\n"
            "    added: 2026-07-29\n    status: active\n    nyc_presence: true\n"
        )
        promote(_a_candidate_file(), registry_path=registry, today=date(2026, 8, 2))
        assert "added: 2026-07-29\n" in registry.read_text()

    def test_the_appended_entry_still_parses(self, tmp_path: Path) -> None:
        """Appending text rather than dumping a document means the renderer must
        produce valid YAML by itself. Prove it round-trips."""
        registry = tmp_path / "board-registry.yaml"
        registry.write_text("boards:\n  - company: Datadog\n    ats: greenhouse\n"
                            "    token: datadog\n    added: 2026-07-29\n"
                            "    status: active\n    nyc_presence: true\n")
        promote(_a_candidate_file(), registry_path=registry, today=date(2026, 8, 2))

        loaded = load_registry(registry)
        assert len(loaded.boards) == 2
        assert loaded.boards[-1].status is BoardStatus.ACTIVE

    def test_a_quote_in_a_company_name_cannot_break_the_file(self, tmp_path: Path) -> None:
        """Rendering text by hand means quoting is now our problem. `O'Reilly`
        and a name containing a colon must both survive."""
```

- [ ] **Step 2: Implement**

Replace the write in `promote`:

```python
    rendered = "".join(_render_entry(entry) for entry in new_entries)
    with target.open("a", encoding="utf-8") as handle:
        if text and not text.endswith("\n"):
            handle.write("\n")
        handle.write(rendered)
```

and add a renderer that emits one entry as text, using `yaml.safe_dump` on
**each scalar value** so quoting stays correct without re-serializing the
document:

```python
def _render_entry(entry: dict[str, Any]) -> str:
    """Render one board as YAML text, appended to the file as-is.

    Appending rather than re-dumping the document is what preserves the
    comments a human wrote between entries. The cost is that quoting becomes
    this function's job, so every scalar goes through yaml.safe_dump rather
    than through an f-string — a company name containing a colon or an
    apostrophe must not be able to corrupt the registry.
    """
    lines = ["\n"]
    for index, (key, value) in enumerate(entry.items()):
        scalar = yaml.safe_dump(value, default_flow_style=True, width=10**6).strip()
        if scalar.endswith("..."):
            # safe_dump of a bare scalar can append a document-end marker.
            scalar = scalar[:-3].strip()
        prefix = "  - " if index == 0 else "    "
        lines.append(f"{prefix}{key}: {scalar}\n")
    return "".join(lines)
```

Do not trust that document-end behaviour to be version-stable — the
`test_the_appended_entry_still_parses` and quoting tests above are what pin it.

Match the existing file's indentation exactly: entries are `  - key:` with
continuation at four spaces.

- [ ] **Step 3: Reshape the registry guard**

Replace `test_the_pollable_set_is_exactly_these_three_boards`:

```python
    def test_the_hand_curated_boards_are_exactly_these(self) -> None:
        """Closed-set check over the boards a human wrote by hand.

        Enumerating every pollable board stopped scaling when the registry began
        being filled by a pipeline (ADR 0005). What still matters is that a
        board a human deliberately turned off cannot come back silently: Stripe
        sits at `status: disabled` and nothing else in this file would catch it
        turning `active`.
        """
        curated = {
            ("greenhouse", "datadog"),
            ("greenhouse", "stripe"),
            ("lever", "alloy"),
            ("ashby", "ramp"),
        }
        pollable = {(e.ats, e.token) for e in load_registry().pollable()}
        assert pollable & curated == {
            ("greenhouse", "datadog"),
            ("lever", "alloy"),
            ("ashby", "ramp"),
        }, "a hand-curated board changed status without this test being updated"

    def test_every_other_pollable_board_carries_its_approval_provenance(self) -> None:
        """A board that reached `active` without going through ADR 0005's
        approval gate has no audit trail, and a hand-added one is exactly what
        the gate exists to prevent."""
        curated = {
            ("greenhouse", "datadog"),
            ("greenhouse", "stripe"),
            ("lever", "alloy"),
            ("ashby", "ramp"),
        }
        for entry in load_registry().pollable():
            if (entry.ats, entry.token) in curated:
                continue
            assert entry.notes and "ADR 0005" in entry.notes, (
                f"{entry.ats}:{entry.token} is pollable but records no approval"
            )
```

- [ ] **Step 4: Promote the 19 boards for real**

```bash
cd /Users/tahmudun/Projects/Nightshift
make registry-approve          # dry run: read the report
make registry-approve-write
git diff data/board-registry.yaml
```

The diff must be **additions only**. If a single existing line is modified or
removed, the renderer is wrong — fix it rather than accepting the diff.

Verify semantically as well as visually:

```bash
services/api/.venv/bin/python - <<'PY'
import subprocess, yaml
old = yaml.safe_load(subprocess.run(
    ["git", "show", "HEAD:data/board-registry.yaml"], capture_output=True, text=True).stdout)
new = yaml.safe_load(open("data/board-registry.yaml"))
ob = {(b["ats"], b["token"]): b for b in old["boards"]}
nb = {(b["ats"], b["token"]): b for b in new["boards"]}
assert not set(ob) - set(nb), f"lost boards: {set(ob) - set(nb)}"
assert all(ob[k] == nb[k] for k in ob), "an existing board was modified"
print(f"ok: {len(ob)} -> {len(nb)} boards, none modified")
PY
```

- [ ] **Step 5: Run the whole suite and commit**

```bash
cd services/api && .venv/bin/python -m pytest -q
cd /Users/tahmudun/Projects/Nightshift && make check
git add services/api/nightshift/discovery/approve.py services/api/tests/ data/board-registry.yaml
git commit -m "fix(discovery): append to the registry instead of rewriting it, and promote 19 boards"
```

---

## Task 11: Surface it, and close the milestone

**Files:**
- Modify: `services/api/nightshift/api/routes/sources.py`,
  `nightshift/api/schemas.py`
- Modify: `services/api/nightshift/discovery/coverage.py`
- Modify: `apps/web/src/lib/schemas.ts`, `apps/web/src/app/operate/page.tsx`
- Modify: `apps/web/e2e-seeded/` — a new spec
- Modify: `docs/PROGRESS.md`
- Create: `docs/reviews/milestone-1d-review.md`
- Create: `docs/adr/0011-next-poll-at-scheduling.md`

- [ ] **Step 1: Expose poll state on `/sources`**

Add per-board rows to the source health payload: `ats`, `token`, `tier`,
`last_polled_at`, `last_success_at`, `last_status`, `consecutive_failures`,
`next_poll_at`. Zod-validate on the web side; `tier` is a union of the two
literals, not a bare string.

- [ ] **Step 2: Show it, including what is stale**

On `/operate`, a board table sorted by `last_success_at` ascending — the boards
we have heard from least recently first, because that is the operational
question. Show `304` counts distinctly from `200`s: a board answering `304` is
healthy, and a UI that renders "no new jobs" as a warning trains people to
ignore it.

Freshness on this page reads `last_success_at` from `board_poll_state`, **not**
each posting's `last_seen_at` (design §6): a board that `304`s for sixty days
leaves its postings' timestamps sixty days old while the postings are correctly
open.

- [ ] **Step 3: Browser tests**

Add to `apps/web/e2e-seeded/`: the board table renders, a board's tier is
readable as a word rather than only as a colour (§12.4), and a `304`-healthy
board is not presented as failing.

- [ ] **Step 4: Write ADR 0011**

Record `next_poll_at` scheduling over a cron per tier: the alternatives
considered (two crons; self-rescheduling jobs), why the stampede and the missing
per-board backoff decided it, and the two constants (batch limit 500, backoff 15
minutes to a 24-hour ceiling) with their reasons.

- [ ] **Step 5: Run the whole acceptance chain from a clean shell**

Per CLAUDE.md §4 — a server you started an hour ago makes a broken target look
like a passing one.

```bash
cd /Users/tahmudun/Projects/Nightshift
make acceptance
```

- [ ] **Step 6: Prove criterion 13 end to end, against a real provider**

Not only in fixtures. With one board in the registry and the containers up:

```bash
OUTBOUND_HTTP_ENABLED=true SOURCE_REQUESTS_PER_SECOND=0.8 \
  services/api/.venv/bin/python -m nightshift.cli poll --ats greenhouse --token datadog
# then immediately again — the second must report 304 and write nothing
```

Record the actual output in PROGRESS, including the row counts before and after.
If the CLI has no `poll` subcommand, add one in Task 7 — a human needs a way to
run a single board's poll without waiting for a cron.

- [ ] **Step 7: Update PROGRESS and write the review**

In `docs/PROGRESS.md`:

- Move criterion 13 to **VERIFIED**, with the recorded evidence, and state the
  criterion as "zero writes to job state" with the list of tables asserted —
  design §5. Do not claim a literal zero-row-write; the board's own bookkeeping
  row moves, and that is the point of polling.
- Correct the three places recording "no `updated_at` on Lever/Ashby" as M1d's
  most consequential carried finding. It dissolved: those providers return every
  posting in full, so there is no second fetch for a timestamp to gate.
- Update "Not real yet": Lever and Ashby are now polled; `board_poll_state` is
  real; the mass-failure signal and the candidate-file batching are still not.
- Update the test counts by **reading** them from the output, not inferring.

Write `docs/reviews/milestone-1d-review.md` looking specifically for: a `304`
path that writes anything; a board that can be enqueued twice; the tier that can
only be entered; retry storms from the scheduler; a stored ETag outliving a
parser change; the lock ordering in `merge_jobs`; and any test that passes
because the thing it asserts about is missing entirely — M1c shipped one of
those and it is worth one deliberate pass.

- [ ] **Step 8: Commit, push, open the PR**

```bash
make check
git add -A
git commit -m "docs(progress): close M1d — criterion 13 verified, review written"
git push -u origin m1d-conditional-polling
gh pr create --title "M1d — conditional polling: a 304 costs one request and writes nothing" --body "..."
```

**Check `git status` before committing** and confirm every new file is actually
tracked. M1c lost an entire route to an unanchored `.gitignore` pattern and
`git add -A` said nothing; `tests/test_repo_integrity.py` now guards the known
case, and it runs in `make check`.

---

## Self-review

**Spec coverage.** Design §1 items 1–8 map to Tasks 1/3 (conditional requests),
4 (two-phase), 6 (poll state), 7 (queue-driven), 8 (tiers), 7+10 (Lever and
Ashby polled — the `ADAPTERS` map replaces the `pollable(ats="greenhouse")`
filter), 9 (row lock), 10 (promote and the 19 boards). §4's listed/fetched split
is Tasks 2 and 5; §5's `304` semantics are Tasks 1, 2, 5 and 7; §6's table is
Task 6; §7's scheduling is Task 7; §9's registry guard is Task 10; §11's tests
are distributed across every task; §12's exclusions are asserted nowhere because
they are absences — they are recorded in PROGRESS at Task 11 instead.

**One gap found and closed while reviewing:** `_postings_needing_content` needs
`source_job_records.source_updated_at`, which does not exist. Added to Task 6's
migration and called out in Task 5 where it is first needed.

**A second gap:** `ingest_boards` aged `304` boards' records because they were
in `boards_ok`. Fixed in Task 5 with a separate `boards_listed` list and a test
that fails without it.

**Type consistency.** `fetch_board(board, *, etag=None)` is used identically in
Tasks 3, 4 and 7. `ConditionalResponse` fields match between Tasks 1 and 3.
`listed_source_job_ids` is a property in Task 2 and consumed as one in Task 5.
`BoardTier` is `db.base` in Tasks 6, 7 and 8. `failure_backoff` takes the count
*before* the increment in both Task 7's implementation and its test.
