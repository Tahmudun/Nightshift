"""Lever adapter tests, driven by the committed board recordings.

The three I3 cases are the reason this file exists: a populated board, a live
board with no postings, and a token that does not resolve must produce three
distinguishable outcomes. Collapsing the last two is how a source outage
closes a thousand open jobs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.adapters.base import BoardRef, RawJob, SourceUnavailableError
from nightshift.adapters.http import ConditionalResponse
from nightshift.adapters.lever import BOARD_URL, LeverAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "lever"
BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


def _board_payload() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "alloy_board.json").read_text())


def _raw_jobs() -> list[RawJob]:
    return [
        RawJob(
            source_job_id=str(job["id"]),
            source_company_key=BOARD.token,
            canonical_url=job.get("hostedUrl"),
            payload=job,
        )
        for job in _board_payload()
    ]


@pytest.fixture
def adapter() -> LeverAdapter:
    # No client: normalize() is pure and must not need one. An adapter that
    # cannot be constructed without a client cannot be unit-tested offline.
    return LeverAdapter(client=None)


def test_normalizes_every_recorded_posting(adapter: LeverAdapter) -> None:
    for raw in _raw_jobs():
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.title
        assert normalized.company_name
        assert normalized.description_hash


def test_company_name_comes_from_the_registry_not_the_payload(adapter: LeverAdapter) -> None:
    """Lever publishes no company name. Inventing one from the token is I2.

    `alloy` happens to look like a company name; `a3c41b8b71eff8c4` does not.
    The rule has to hold for both, so the name comes from the registry entry a
    human approved.
    """
    payload = _board_payload()[0]
    assert "company" not in payload
    assert "companyName" not in payload
    normalized = adapter.normalize(_raw_jobs()[0], BOARD)
    assert normalized.company_name == "Alloy"


def test_company_name_cannot_be_derived_from_the_token(adapter: LeverAdapter) -> None:
    """A stronger check than test_company_name_comes_from_the_registry_not_the_payload.

    That test uses BOARD.company == "Alloy" against BOARD.token == "alloy", so
    a bug that derived the name from the token via `.title()` would pass it
    undetected. This board's company name cannot be produced by transforming
    its token, so only reading `board.company` can satisfy the assertion.
    """
    board = BoardRef(
        company="Alloy Labs Corporation",
        ats="lever",
        token="alloy",
        nyc_presence=True,
    )
    normalized = LeverAdapter(client=None).normalize(_raw_jobs()[0], board)
    assert normalized.company_name == "Alloy Labs Corporation"


def test_all_locations_array_yields_one_row_each(adapter: LeverAdapter) -> None:
    """A2: Lever hands us an array and every element becomes a location row."""
    for raw in _raw_jobs():
        expected = raw.payload["categories"].get("allLocations") or []
        normalized = adapter.normalize(raw, BOARD)
        assert len(normalized.locations) == len(set(expected)), raw.source_job_id


def test_no_location_carries_a_coordinate(adapter: LeverAdapter) -> None:
    """I1, structurally: ParsedLocation has no coordinate field to populate."""
    for raw in _raw_jobs():
        for location in adapter.normalize(raw, BOARD).locations:
            assert not hasattr(location, "latitude")
            assert not hasattr(location, "longitude")


def test_canadian_province_is_not_read_as_a_city(adapter: LeverAdapter) -> None:
    """The 'Vancouver, BC' regression, asserted end to end through the adapter."""
    cities = {loc.city for raw in _raw_jobs() for loc in adapter.normalize(raw, BOARD).locations}
    assert "BC" not in cities
    assert "Vancouver" in cities


def test_salary_range_is_read_from_the_structured_field(adapter: LeverAdapter) -> None:
    """Unlike Greenhouse, Lever states the interval, so salary_period is set.

    The fixture prices postings in both USD (Washington DC, Denver, remote-US)
    and CAD (Vancouver) — the adapter must carry through whichever currency
    the source actually stated, never overwrite it with an assumed one.
    """
    priced_raw = [raw for raw in _raw_jobs() if raw.payload.get("salaryRange")]
    assert priced_raw, "fixture has no priced posting — re-record with one"
    for raw in priced_raw:
        normalized = adapter.normalize(raw, BOARD)
        expected_currency = raw.payload["salaryRange"]["currency"]
        assert normalized.salary_min is not None
        assert normalized.salary_currency == expected_currency
        assert normalized.salary_period == "year"


def test_created_at_is_epoch_milliseconds_not_seconds(adapter: LeverAdapter) -> None:
    """1783951681940 read as seconds lands in the year 58,500.

    Every freshness calculation downstream reads this field, so getting the
    unit wrong is silent and total.
    """
    normalized = adapter.normalize(_raw_jobs()[0], BOARD)
    assert normalized.source_published_at is not None
    assert 2000 < normalized.source_published_at.year < 2100


def test_source_updated_at_is_none_because_lever_has_no_such_field(
    adapter: LeverAdapter,
) -> None:
    """Asserted rather than assumed: ADR 0007's diff strategy depends on it.

    A10 forbids presenting createdAt as a last-modified stamp, so the column
    stays null and M1d must diff on the content hash for this provider.
    """
    payload = _board_payload()[0]
    assert not [k for k in payload if "update" in k.lower() or "modif" in k.lower()]
    assert adapter.normalize(_raw_jobs()[0], BOARD).source_updated_at is None


def test_normalization_is_deterministic(adapter: LeverAdapter) -> None:
    """M1 acceptance: same fixture in, byte-identical output, twice."""
    first = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    second = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    assert first == second


class TestInvariantI3:
    """A source telling us nothing must be distinguishable from a source
    telling us there is nothing."""

    async def test_populated_board_is_ok_and_not_empty(self) -> None:
        adapter = LeverAdapter(client=_StubClient(_board_payload()))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert len(outcome.jobs) == 9
        assert outcome.is_authoritative_empty is False

    async def test_empty_board_is_authoritatively_empty(self) -> None:
        payload = json.loads((FIXTURES / "plaid_empty_board.json").read_text())
        assert payload == []
        adapter = LeverAdapter(client=_StubClient(payload))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert outcome.jobs == ()
        assert outcome.is_authoritative_empty is True

    async def test_unknown_token_is_not_ok_and_not_empty(self) -> None:
        from nightshift.adapters.base import SourceUnavailableError

        adapter = LeverAdapter(
            client=_StubClient(SourceUnavailableError("HTTP 404", http_status=404))
        )
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.http_status == 404
        assert outcome.is_authoritative_empty is False

    async def test_wrong_shape_is_not_read_as_empty(self) -> None:
        """Lever returns an array. An object means something changed upstream,
        and 'no jobs' is the one conclusion we must not draw from it."""
        adapter = LeverAdapter(client=_StubClient({"ok": False}))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False


class _StubClient:
    """Stands in for PoliteClient. Returns a payload, a 304, or raises.

    Not a mock of the adapter under test — it replaces the network, which is
    the boundary a unit test is entitled to replace.

    ``seen_etags`` records what the adapter actually sent. Asserting on it
    rather than only on the return value is deliberate: M1c shipped a stub whose
    route key matched no URL, so the stub raised and the test passed without
    ever reaching the branch it existed to cover.
    """

    def __init__(
        self,
        result: Any,
        *,
        etag: str | None = 'W/"fresh"',
        not_modified: bool = False,
    ) -> None:
        self._result = result
        self._etag = etag
        self._not_modified = not_modified
        self.seen_etags: list[str | None] = []
        self.seen_urls: list[str] = []

    async def get_json_conditional(
        self, url: str, *, etag: str | None = None
    ) -> ConditionalResponse:
        self.seen_urls.append(url)
        self.seen_etags.append(etag)
        if isinstance(self._result, Exception):
            raise self._result
        if self._not_modified:
            return ConditionalResponse(not_modified=True, payload=None, etag=etag, http_status=304)
        return ConditionalResponse(
            not_modified=False, payload=self._result, etag=self._etag, http_status=200
        )


class TestConditionalFetch:
    """M1d: Lever revalidates. Measured 2026-08-02 against the live board — it
    serves `W/"38d97-QpFUTs..."` and answers 304 when it is sent back.

    Lever is also the provider where a 304 is worth most: it is the one of the
    three that does not compress, so a 200 costs 232 KB on the wire.
    """

    async def test_a_304_yields_not_modified_and_describes_no_postings(self) -> None:
        client = _StubClient(None, not_modified=True)
        outcome = await LeverAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.ok is True
        assert outcome.not_modified is True
        assert outcome.jobs == ()
        assert outcome.listed == ()
        assert outcome.http_status == 304

    async def test_a_304_is_not_an_empty_board(self) -> None:
        """The whole point. Lever's empty-board case is a 200 with `[]`, and
        these two must stay distinguishable."""
        client = _StubClient(None, not_modified=True)
        outcome = await LeverAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.is_authoritative_empty is False

    async def test_a_304_keeps_the_etag_that_earned_it(self) -> None:
        client = _StubClient(None, not_modified=True)
        outcome = await LeverAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.etag == 'W/"abc"'

    async def test_the_stored_etag_reaches_the_client(self) -> None:
        client = _StubClient(_board_payload())
        await LeverAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert client.seen_etags == ['W/"abc"']
        assert client.seen_urls == [BOARD_URL.format(token="alloy")]

    async def test_no_etag_is_sent_on_a_first_poll(self) -> None:
        client = _StubClient(_board_payload())
        await LeverAdapter(client=client).fetch_board(BOARD)

        assert client.seen_etags == [None]

    async def test_a_200_reports_the_new_etag_for_storage(self) -> None:
        client = _StubClient(_board_payload(), etag='W/"fresh"')
        outcome = await LeverAdapter(client=client).fetch_board(BOARD)

        assert outcome.not_modified is False
        assert outcome.etag == 'W/"fresh"'

    async def test_every_fetched_posting_is_also_listed(self) -> None:
        """Single-phase provider: the two sets describe the same postings.

        Asserted rather than assumed. Freshness ages against `listed`, so a
        Lever adapter that forgot to populate it would age every posting it had
        just successfully fetched and close the entire board in three polls.
        """
        client = _StubClient(_board_payload())
        outcome = await LeverAdapter(client=client).fetch_board(BOARD)

        assert len(outcome.listed) > 0
        assert outcome.listed_source_job_ids == tuple(j.source_job_id for j in outcome.jobs)

    async def test_listed_postings_carry_no_timestamp(self) -> None:
        """Lever publishes `createdAt` and no updated-at field. Inventing one
        from createdAt would make an old posting look freshly changed forever."""
        client = _StubClient(_board_payload())
        outcome = await LeverAdapter(client=client).fetch_board(BOARD)

        assert all(p.source_updated_at is None for p in outcome.listed)

    async def test_an_empty_board_lists_nothing_and_is_authoritative(self) -> None:
        client = _StubClient([])
        outcome = await LeverAdapter(client=client).fetch_board(BOARD)

        assert outcome.ok is True
        assert outcome.not_modified is False
        assert outcome.listed == ()
        assert outcome.is_authoritative_empty is True

    async def test_a_failure_still_reports_ok_false(self) -> None:
        client = _StubClient(SourceUnavailableError("boom", http_status=503))
        outcome = await LeverAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.ok is False
        assert outcome.not_modified is False
        assert outcome.is_authoritative_empty is False


class TestAdapterMetadata:
    def test_it_is_single_phase(self) -> None:
        """Lever's board response carries every posting in full — 6,373
        characters of `description` on the first alloy posting, measured
        2026-08-02 — so there is nothing a second request could add."""
        assert LeverAdapter(client=None).is_two_phase is False

    def test_it_declares_a_parser_version(self) -> None:
        """ADR 0007: a stored ETag is only valid for the parser that earned it."""
        assert LeverAdapter(client=None).parser_version
