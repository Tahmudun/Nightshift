"""Greenhouse adapter tests against the committed real payload.

Two things these tests are careful about:

* They mock the *network*, never the adapter. ``respx`` intercepts at the
  transport layer, so the code under test is the real ``PoliteClient`` doing
  real retry and rate-limit work — mocking the thing under test is the
  anti-pattern CLAUDE.md §8 names explicitly.
* The I3 tests assert on ``FetchOutcome.ok`` rather than on job counts, because
  the invariant is about the *distinction* between "source failed" and "board is
  empty", and only the flag carries it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from citysignal.adapters.base import BoardRef, JobSourceAdapter, RawJob
from citysignal.adapters.greenhouse import (
    BOARD_URL,
    GreenhouseAdapter,
    _extract_employment_type,
    content_hash,
    html_to_text,
    normalize_title,
)
from citysignal.adapters.http import OutboundHTTPDisabledError, PoliteClient
from citysignal.config import Settings
from citysignal.db.base import EmploymentType, LocationConfidence, SourceType
from tests.conftest import make_settings

BOARD = BoardRef(company="Datadog", ats="greenhouse", token="datadog", nyc_presence=True)
BOARD_ENDPOINT = BOARD_URL.format(token="datadog")


def adapter_for(settings: Settings) -> tuple[GreenhouseAdapter, PoliteClient]:
    client = PoliteClient(settings)
    return GreenhouseAdapter(client), client


def test_adapter_satisfies_the_protocol() -> None:
    """The pipeline depends on the Protocol, not on this class."""
    adapter, _ = adapter_for(make_settings())
    assert isinstance(adapter, JobSourceAdapter)
    assert adapter.source_name == "greenhouse"
    assert adapter.source_type is SourceType.ATS_GREENHOUSE
    # A1: this method cannot be implemented and must not exist.
    assert not hasattr(adapter, "discover_companies")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_board_returns_every_job(greenhouse_board_payload: dict[str, Any]) -> None:
    respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(200, json=greenhouse_board_payload))
    adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
    async with client:
        outcome = await adapter.fetch_board(BOARD)

    assert outcome.ok
    assert len(outcome.jobs) == len(greenhouse_board_payload["jobs"])
    assert all(job.source_company_key == "datadog" for job in outcome.jobs)


@respx.mock
async def test_fetch_sends_an_identifying_user_agent() -> None:
    """§7.3: every request identifies itself."""
    route = respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": []}))
    adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
    async with client:
        await adapter.fetch_board(BOARD)

    user_agent = route.calls[0].request.headers["user-agent"]
    assert "CitySignal" in user_agent
    assert "github.com" in user_agent


class TestInvariantI3:
    """A source that errors, times out, or misbehaves is never evidence of closure."""

    @respx.mock
    async def test_404_is_not_authoritative_empty(self) -> None:
        respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(404, text="Not found"))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is False
        assert outcome.jobs == ()
        assert outcome.http_status == 404
        assert outcome.is_authoritative_empty is False

    @respx.mock
    async def test_timeout_is_not_authoritative_empty(self) -> None:
        respx.get(BOARD_ENDPOINT).mock(side_effect=httpx.ConnectTimeout("timed out"))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False

    @respx.mock
    async def test_500_is_not_authoritative_empty(self) -> None:
        respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(503))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False

    @respx.mock
    async def test_malformed_json_is_not_authoritative_empty(self) -> None:
        respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(200, text="<html>oops"))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is False

    @respx.mock
    async def test_200_with_missing_jobs_key_is_not_authoritative_empty(self) -> None:
        """A well-formed response of the wrong shape is a source problem, not zero jobs."""
        respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(200, json={"meta": {}}))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is False

    @respx.mock
    async def test_genuine_empty_board_is_authoritative(self) -> None:
        """The other half of the invariant: a real empty board must be usable as evidence.

        Without this, I3 could be satisfied by never trusting anything, and a
        board that genuinely emptied would never close its jobs.
        """
        respx.get(BOARD_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"jobs": [], "meta": {"total": 0}})
        )
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is True
        assert outcome.is_authoritative_empty is True

    @respx.mock
    async def test_fetch_board_never_raises(self) -> None:
        """One bad board must not abort a run over the others."""
        respx.get(BOARD_ENDPOINT).mock(side_effect=httpx.ConnectError("dns"))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True))
        async with client:
            outcome = await adapter.fetch_board(BOARD)  # must not raise
        assert outcome.ok is False


class TestPoliteClient:
    @respx.mock
    async def test_retries_transient_failures_then_succeeds(self) -> None:
        route = respx.get(BOARD_ENDPOINT).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(429),
                httpx.Response(200, json={"jobs": [], "meta": {"total": 0}}),
            ]
        )
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True, http_max_retries=2))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert outcome.ok is True
        assert route.call_count == 3

    @respx.mock
    async def test_does_not_retry_a_404(self) -> None:
        """§7.3 "avoid hammering endpoints": a 404 will still be a 404 next time."""
        route = respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(404))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True, http_max_retries=3))
        async with client:
            await adapter.fetch_board(BOARD)

        assert route.call_count == 1

    @respx.mock
    async def test_gives_up_after_the_configured_retry_budget(self) -> None:
        route = respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(503))
        adapter, client = adapter_for(make_settings(outbound_http_enabled=True, http_max_retries=2))
        async with client:
            outcome = await adapter.fetch_board(BOARD)

        assert route.call_count == 3  # 1 attempt + 2 retries
        assert outcome.ok is False

    @respx.mock
    async def test_kill_switch_blocks_every_request(self) -> None:
        """`make demo` is offline by construction, not by convention."""
        route = respx.get(BOARD_ENDPOINT).mock(return_value=httpx.Response(200, json={"jobs": []}))
        client = PoliteClient(make_settings(outbound_http_enabled=False))
        async with client:
            with pytest.raises(OutboundHTTPDisabledError):
                await client.get_json(BOARD_ENDPOINT)

        assert route.call_count == 0

    async def test_kill_switch_surfaces_as_source_unavailable(self) -> None:
        """So the ingestion pipeline handles it under I3 like any other outage."""
        adapter, client = adapter_for(make_settings(outbound_http_enabled=False))
        async with client:
            outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert "disabled" in (outcome.error or "")


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalized_all(payload: dict[str, Any]) -> list[Any]:
    adapter, _ = adapter_for(make_settings())
    return [
        adapter.normalize(
            RawJob(
                source_job_id=str(job["id"]),
                source_company_key="datadog",
                canonical_url=job.get("absolute_url"),
                payload=job,
            )
        )
        for job in payload["jobs"]
    ]


def test_every_fixture_job_normalizes(greenhouse_board_payload: dict[str, Any]) -> None:
    results = normalized_all(greenhouse_board_payload)
    assert len(results) == len(greenhouse_board_payload["jobs"])
    for job in results:
        assert job.title
        assert job.normalized_title
        assert job.description_hash


def test_normalization_is_deterministic(greenhouse_board_payload: dict[str, Any]) -> None:
    """M1's headline criterion, asserted from M0 so it never regresses into being false."""
    first = normalized_all(greenhouse_board_payload)
    second = normalized_all(greenhouse_board_payload)
    assert [job.model_dump_json() for job in first] == [job.model_dump_json() for job in second]


def test_multi_location_posting_yields_one_row_per_place(
    greenhouse_board_payload: dict[str, Any],
) -> None:
    """AMENDMENTS A2, on real data."""
    by_id = {job.source_job_id: job for job in normalized_all(greenhouse_board_payload)}
    raw_by_id = {str(j["id"]): j for j in greenhouse_board_payload["jobs"]}

    multi = [
        job_id
        for job_id, raw in raw_by_id.items()
        if ";" in (raw.get("location") or {}).get("name", "")
    ]
    assert multi, "fixture no longer contains a multi-location posting — re-record it"

    for job_id in multi:
        raw_segments = (raw_by_id[job_id]["location"]["name"]).split(";")
        job = by_id[job_id]
        assert len(job.locations) == len({s.strip() for s in raw_segments if s.strip()})


def test_no_normalized_job_carries_coordinates(greenhouse_board_payload: dict[str, Any]) -> None:
    """Invariant I1: M0 does not geocode, so nothing may claim a point."""
    for job in normalized_all(greenhouse_board_payload):
        for location in job.locations:
            assert location.confidence in {
                LocationConfidence.CITY_ONLY,
                LocationConfidence.REMOTE,
                LocationConfidence.UNKNOWN,
            }, f"{job.title}: M0 cannot produce {location.confidence}"


def test_last_modified_is_never_stored_as_a_publication_date(
    greenhouse_board_payload: dict[str, Any],
) -> None:
    """AMENDMENTS A10: `updated_at` is not a posted date and does not travel as one."""
    raw_by_id = {str(j["id"]): j for j in greenhouse_board_payload["jobs"]}
    for job in normalized_all(greenhouse_board_payload):
        raw = raw_by_id[job.source_job_id]
        if raw.get("first_published"):
            assert job.source_published_at is not None
        if raw.get("updated_at"):
            assert job.source_updated_at is not None
        # The two fields are populated from two different source fields, and a
        # posting updated after publication proves they were not conflated.
        if job.source_published_at and job.source_updated_at:
            assert job.source_updated_at >= job.source_published_at

    # No field named `posted_at` exists to be misread.
    assert "posted_at" not in normalized_all(greenhouse_board_payload)[0].model_dump()


def test_absent_deadline_stays_none(greenhouse_board_payload: dict[str, Any]) -> None:
    """A10: this board publishes no deadlines. Absence must not become a default."""
    for job in normalized_all(greenhouse_board_payload):
        raw_deadline = {str(j["id"]): j for j in greenhouse_board_payload["jobs"]}[
            job.source_job_id
        ].get("application_deadline")
        if not raw_deadline:
            assert job.application_deadline is None


def test_pay_transparency_range_is_extracted(greenhouse_board_payload: dict[str, Any]) -> None:
    """NYC postings publish a range in `metadata`; it must be found, not ignored."""
    with_pay = [job for job in normalized_all(greenhouse_board_payload) if job.salary_min]
    assert with_pay, "fixture no longer contains a published pay range — re-record it"
    for job in with_pay:
        assert job.salary_max is not None
        assert job.salary_min <= job.salary_max
        assert job.salary_currency == "USD"
        # Greenhouse states no period; guessing one from magnitude is fabrication.
        assert job.salary_period is None


def test_utc_timestamps_only(greenhouse_board_payload: dict[str, Any]) -> None:
    for job in normalized_all(greenhouse_board_payload):
        for value in (job.source_published_at, job.source_updated_at, job.application_deadline):
            if value is not None:
                assert value.tzinfo is not None
                assert value.utcoffset() == UTC.utcoffset(None)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


class TestHtmlToText:
    def test_unescapes_double_encoded_html(self) -> None:
        """The payload arrives as `&lt;p&gt;`, so unescaping must precede tag stripping."""
        assert html_to_text("&lt;p&gt;Hello &lt;strong&gt;world&lt;/strong&gt;&lt;/p&gt;") == (
            "Hello world"
        )

    def test_renders_list_items_as_bullets(self) -> None:
        assert html_to_text(
            "&lt;ul&gt;&lt;li&gt;One&lt;/li&gt;&lt;li&gt;Two&lt;/li&gt;&lt;/ul&gt;"
        ) == ("• One\n\n• Two")

    def test_collapses_nbsp_and_runs_of_whitespace(self) -> None:
        assert html_to_text("&lt;p&gt;a&amp;nbsp;&amp;nbsp;  b&lt;/p&gt;") == "a b"

    def test_empty_and_none_return_none(self) -> None:
        assert html_to_text(None) is None
        assert html_to_text("") is None
        assert html_to_text("&lt;p&gt;&lt;/p&gt;") is None

    def test_real_fixture_description_has_no_residual_markup(
        self, greenhouse_board_payload: dict[str, Any]
    ) -> None:
        for raw in greenhouse_board_payload["jobs"]:
            text = html_to_text(raw.get("content"))
            if text is None:
                continue
            assert "<" not in text and "&lt;" not in text
            assert "&nbsp;" not in text and "&amp;" not in text


class TestContentHash:
    def test_is_stable_across_whitespace_reformatting(self) -> None:
        """Re-ingestion must not report an update for a cosmetically reflowed description."""
        assert content_hash("Build   things\n\nfast") == content_hash("Build things fast")

    def test_differs_for_different_content(self) -> None:
        assert content_hash("Python required") != content_hash("Go required")

    def test_none_and_empty_agree(self) -> None:
        assert content_hash(None) == content_hash("")


class TestNormalizeTitle:
    def test_casefolds_and_collapses_whitespace(self) -> None:
        assert normalize_title("  Senior   Software   Engineer ") == "senior software engineer"

    def test_normalises_dash_variants(self) -> None:
        assert normalize_title("Engineer — Platform") == normalize_title("Engineer - Platform")

    def test_does_not_attempt_role_family_normalisation(self) -> None:
        """M3 owns that, with versioned rules and an eval set (A13). M0 must not pre-empt it."""
        assert normalize_title("SWE II") != normalize_title("Software Engineer 2")


class TestEmploymentType:
    """Synthetic titles, and labelled as such.

    The recorded Datadog board contains no internship postings (see
    ``datadog_board.meta.json`` -> ``coverage_not_available_on_this_board``), so
    these exercise the function directly rather than through a fabricated
    payload. Inventing a "real" recorded internship would be exactly the mock
    masquerading as product that I7 forbids.
    """

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Software Engineering Intern", EmploymentType.INTERNSHIP),
            ("2027 Summer Internship - Backend", EmploymentType.INTERNSHIP),
            ("Engineering Co-Op", EmploymentType.INTERNSHIP),
            ("Engineering Coop", EmploymentType.INTERNSHIP),
            ("Coordinator, Business Recruiting - Contract", EmploymentType.CONTRACT),
            # Word-boundary matching: neither of these is an internship.
            ("International Sales Manager", EmploymentType.UNKNOWN),
            ("Internal Tools Engineer", EmploymentType.UNKNOWN),
        ],
    )
    def test_classifies_from_title(self, title: str, expected: EmploymentType) -> None:
        assert _extract_employment_type(title, {}) is expected

    def test_time_type_metadata_is_used_when_the_title_is_silent(self) -> None:
        metadata = {"time type": {"name": "Time Type", "value": "Full time"}}
        assert _extract_employment_type("Software Engineer", metadata) is EmploymentType.FULL_TIME

    def test_internship_in_title_outranks_full_time_metadata(self) -> None:
        """Internships are routinely tagged full-time hours; the title is the stronger signal."""
        metadata = {"time type": {"name": "Time Type", "value": "Full time"}}
        assert (
            _extract_employment_type("Software Engineer Intern", metadata)
            is EmploymentType.INTERNSHIP
        )

    def test_unstated_is_unknown_not_a_plausible_default(self) -> None:
        """A13: eligibility-adjacent guessing belongs to M3, with an eval set."""
        assert _extract_employment_type("Software Engineer", {}) is EmploymentType.UNKNOWN
        assert (
            _extract_employment_type("Engineer", {"time type": {"value": None}})
            is EmploymentType.UNKNOWN
        )


def test_normalize_rejects_a_titleless_payload() -> None:
    adapter, _ = adapter_for(make_settings())
    with pytest.raises(ValueError, match="no title"):
        adapter.normalize(
            RawJob(source_job_id="1", source_company_key="datadog", payload={"id": 1})
        )


def test_timestamp_parsing_handles_the_boards_offset_format() -> None:
    """Greenhouse sends `-04:00` offsets, not `Z`."""
    adapter, _ = adapter_for(make_settings())
    job = adapter.normalize(
        RawJob(
            source_job_id="1",
            source_company_key="datadog",
            payload={
                "id": 1,
                "title": "Engineer",
                "updated_at": "2026-07-28T05:41:06-04:00",
                "first_published": "2025-08-27T10:34:20-04:00",
            },
        )
    )
    assert job.source_updated_at == datetime(2026, 7, 28, 9, 41, 6, tzinfo=UTC)
    assert job.source_published_at == datetime(2025, 8, 27, 14, 34, 20, tzinfo=UTC)


def test_unparseable_timestamp_becomes_none_not_now() -> None:
    """A wrong timestamp silently corrupts every freshness calculation downstream."""
    adapter, _ = adapter_for(make_settings())
    job = adapter.normalize(
        RawJob(
            source_job_id="1",
            source_company_key="datadog",
            payload={"id": 1, "title": "Engineer", "updated_at": "last tuesday"},
        )
    )
    assert job.source_updated_at is None
