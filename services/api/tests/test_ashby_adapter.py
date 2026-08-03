"""Ashby adapter tests, driven by the committed board recording.

The load-bearing test here is test_is_remote_does_not_mean_remote. On the
recorded board, postings at the New York office carry isRemote: true. Mapping
that field onto remote_policy would relabel the company's entire headquarters
as remote, and every one of those jobs is one a New York user is looking for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.adapters.ashby import (
    BOARD_URL,
    AshbyAdapter,
    _extract_salary,
    _map_employment_type,
)
from nightshift.adapters.base import BoardRef, RawJob, SourceUnavailableError
from nightshift.adapters.http import ConditionalResponse
from nightshift.db.base import EmploymentType, LocationConfidence

FIXTURES = Path(__file__).parent / "fixtures" / "ashby"
BOARD = BoardRef(company="Ramp", ats="ashby", token="ramp", nyc_presence=True)


def _board_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "ramp_board.json").read_text())


def _raw_jobs() -> list[RawJob]:
    return [
        RawJob(
            source_job_id=str(job["id"]),
            source_company_key=BOARD.token,
            canonical_url=job.get("jobUrl"),
            payload=job,
        )
        for job in _board_payload()["jobs"]
    ]


@pytest.fixture
def adapter() -> AshbyAdapter:
    # No client: normalize() is pure and must not need one. An adapter that
    # cannot be constructed without a client cannot be unit-tested offline.
    return AshbyAdapter(client=None)


def test_normalizes_every_recorded_posting(adapter: AshbyAdapter) -> None:
    for raw in _raw_jobs():
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.title
        assert normalized.description_hash


def test_the_payload_contains_no_company_name(adapter: AshbyAdapter) -> None:
    """board-discovery.md §3, asserted rather than trusted.

    The batch-approval gate in ADR 0005 turns on 'the provider told us who this
    is'. If Ashby ever starts publishing a name, this test fails and the
    approval design should be revisited — which is the point of asserting it.
    """
    for job in _board_payload()["jobs"]:
        assert not [k for k in job if "compan" in k.lower() or "organi" in k.lower()]


def test_company_name_comes_from_the_registry(adapter: AshbyAdapter) -> None:
    normalized = adapter.normalize(_raw_jobs()[0], BOARD)
    assert normalized.company_name == "Ramp"


def test_is_remote_does_not_mean_remote(adapter: AshbyAdapter) -> None:
    """A posting at the New York office is not a remote posting.

    On the recorded board these carry isRemote: true, which appears to mean
    'remote candidates considered' rather than 'this job is remote'. Taking it
    at face value would relabel the headquarters.
    """
    office_with_remote_flag = [
        raw
        for raw in _raw_jobs()
        if raw.payload.get("isRemote") and "New York" in str(raw.payload.get("location"))
    ]
    assert office_with_remote_flag, "fixture lost the case — re-record per Task 2 step 3"
    assert len(office_with_remote_flag) == 10, "expected 10 of 12 postings at the NY office"

    for raw in office_with_remote_flag:
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.remote_policy != "remote"
        primary = normalized.locations[0]
        assert primary.city == "New York"
        assert primary.confidence is LocationConfidence.CITY_ONLY


def test_hq_annotation_does_not_become_the_city(adapter: AshbyAdapter) -> None:
    cities = {loc.city for raw in _raw_jobs() for loc in adapter.normalize(raw, BOARD).locations}
    assert "NY (HQ)" not in cities
    assert "New York" in cities


def test_secondary_locations_each_get_a_row(adapter: AshbyAdapter) -> None:
    """A2: multi-location postings produce multiple job_locations rows."""
    multi = [raw for raw in _raw_jobs() if raw.payload.get("secondaryLocations")]
    assert multi, "fixture has no multi-location posting — re-record"
    assert len(multi) == 9, "expected 9 of 12 postings to carry secondaryLocations"
    for raw in multi:
        normalized = adapter.normalize(raw, BOARD)
        expected = {raw.payload["location"]} | {
            s["location"] for s in raw.payload["secondaryLocations"]
        }
        assert len(normalized.locations) == len(expected), raw.source_job_id
        assert normalized.locations[0].raw_text == raw.payload["location"]


def test_single_location_posting_produces_exactly_one_row(adapter: AshbyAdapter) -> None:
    """The other 3 of 12 postings have no secondaryLocations at all."""
    single = [raw for raw in _raw_jobs() if not raw.payload.get("secondaryLocations")]
    assert single, "fixture has no single-location posting — re-record"
    for raw in single:
        normalized = adapter.normalize(raw, BOARD)
        assert len(normalized.locations) == 1


def test_internship_employment_type_from_real_data(adapter: AshbyAdapter) -> None:
    """Closes the M0 'Not real yet' row.

    The Datadog board had zero internship postings, so that branch was covered
    only by synthetic unit tests. This board has a real one.
    """
    interns = [
        adapter.normalize(raw, BOARD)
        for raw in _raw_jobs()
        if raw.payload.get("employmentType") == "Intern"
    ]
    assert interns, "fixture lost the internship posting — re-record per Task 2 step 3"
    for normalized in interns:
        assert normalized.employment_type is EmploymentType.INTERNSHIP


def test_full_time_employment_type_from_real_data(adapter: AshbyAdapter) -> None:
    full_time = [
        adapter.normalize(raw, BOARD)
        for raw in _raw_jobs()
        if raw.payload.get("employmentType") == "FullTime"
    ]
    assert full_time, "fixture lost its full-time postings — re-record"
    for normalized in full_time:
        assert normalized.employment_type is EmploymentType.FULL_TIME


class TestEmploymentTypeMapping:
    """Synthetic values, and labelled as such.

    The recorded Ramp board only ever states "FullTime" or "Intern" (verified
    against the full 12-posting fixture). "Contract", "PartTime", and
    "Temporary" have no real posting on this board to exercise them, so they
    are tested against the mapping function directly rather than through a
    fabricated payload — inventing a "real" recorded contract posting would be
    exactly the mock masquerading as product that I7 forbids.
    """

    @pytest.mark.parametrize(
        "raw_value,expected",
        [
            ("FullTime", EmploymentType.FULL_TIME),
            ("PartTime", EmploymentType.PART_TIME),
            ("Intern", EmploymentType.INTERNSHIP),
            ("Contract", EmploymentType.CONTRACT),
            ("Temporary", EmploymentType.TEMPORARY),
            # TEMPORARY and CONTRACT are distinct values on the domain enum;
            # nothing here should collapse one onto the other.
        ],
    )
    def test_classifies_the_known_vocabulary(
        self, raw_value: str, expected: EmploymentType
    ) -> None:
        assert _map_employment_type(raw_value) is expected

    def test_unstated_is_unknown_not_a_plausible_default(self) -> None:
        """A13: eligibility-adjacent guessing belongs to M3, with an eval set."""
        assert _map_employment_type(None) is EmploymentType.UNKNOWN
        assert _map_employment_type("Freelance") is EmploymentType.UNKNOWN


def test_salary_period_is_year_for_annually_priced_postings(adapter: AshbyAdapter) -> None:
    """Greenhouse states no period and gets None. Ashby states one per component.

    Most of this board prices annually in USD, so those postings get
    salary_period == "year" honestly — A10's rule is "store what the source
    gives you", and here the source gives an interval. The intern (priced
    monthly) and the Canada posting (priced in CAD) are covered by their own
    tests below rather than folded in here.
    """
    annual_usd = [
        adapter.normalize(raw, BOARD)
        for raw in _raw_jobs()
        if raw.payload.get("compensation", {}).get("compensationTiers")
        and raw.payload.get("employmentType") != "Intern"
        and raw.payload.get("location") != "Remote (Canada)"
    ]
    assert annual_usd, "fixture has no annually priced USD posting — re-record"
    for normalized in annual_usd:
        assert normalized.salary_min is not None
        assert normalized.salary_period == "year"
        assert normalized.salary_currency == "USD"


def test_intern_salary_is_priced_monthly_not_relabelled_as_yearly(adapter: AshbyAdapter) -> None:
    """The intern's compensation component states '1 MONTH', not '1 YEAR'.

    A10's rule cuts both ways: hardcoding "year" company-wide would relabel a
    monthly stipend as an annual salary, which is exactly the kind of
    invented precision I1's sibling rule for pay would forbid.
    """
    interns = [raw for raw in _raw_jobs() if raw.payload.get("employmentType") == "Intern"]
    assert interns, "fixture lost the internship posting — re-record"
    for raw in interns:
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.salary_min is not None
        assert normalized.salary_period == "month"


def test_salary_currency_reflects_what_the_source_states_not_always_usd(
    adapter: AshbyAdapter,
) -> None:
    """One posting on this board is priced in CAD. Assuming USD company-wide
    would misstate its actual pay."""
    non_usd_raw = [
        raw
        for raw in _raw_jobs()
        if any(
            component.get("currencyCode") not in (None, "USD")
            for tier in raw.payload.get("compensation", {}).get("compensationTiers", [])
            for component in tier.get("components", [])
        )
    ]
    assert non_usd_raw, "fixture lost its non-USD posting — re-record"
    for raw in non_usd_raw:
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.salary_currency == "CAD"
        assert normalized.salary_period == "year"


def test_salary_min_max_pin_to_the_specific_salary_component(adapter: AshbyAdapter) -> None:
    """Real-data pin: salary_min/salary_max equal the *specific* Salary
    component's figures for every priced posting, not merely "some value
    over 1000". A bug that read the wrong Salary-typed component (e.g. the
    wrong tier on `b9568fb8`, which carries two) would fail this.

    This test alone cannot prove the compensationType=="Salary" filter
    matters, because every non-Salary component on this board has
    minValue: null — see test_extract_salary_skips_a_priced_equity_component
    below for the case that actually exercises the filter.
    """
    for raw in _raw_jobs():
        tiers = raw.payload.get("compensation", {}).get("compensationTiers") or []
        expected: dict[str, Any] | None = None
        for tier in tiers:
            for component in tier.get("components", []):
                if component.get("compensationType") == "Salary":
                    expected = component
                    break
            if expected is not None:
                break

        normalized = adapter.normalize(raw, BOARD)
        if expected is None:
            assert normalized.salary_min is None
            continue
        assert normalized.salary_min == expected["minValue"]
        assert normalized.salary_max == expected["maxValue"]


def test_extract_salary_skips_a_priced_equity_component_before_the_salary_component() -> None:
    """Synthetic, and labelled as such.

    Every non-Salary component on the recorded board has minValue: null, so
    real-data assertions cannot distinguish "the compensationType == 'Salary'
    filter is doing the work" from "the null-value guard is doing the work" —
    deleting the filter and rerunning the suite leaves all 26 original tests
    green, because the loop just falls through the null equity component to
    the Salary one regardless. This payload puts a *priced* EquityCashValue
    ahead of the Salary component so the two guards can be told apart: with
    the filter, this returns the Salary figures; without it, it returns the
    equity figures instead.
    """
    payload = {
        "compensation": {
            "compensationTiers": [
                {
                    "components": [
                        {
                            "compensationType": "EquityCashValue",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 999000,
                            "maxValue": 999000,
                        },
                        {
                            "compensationType": "Salary",
                            "interval": "1 YEAR",
                            "currencyCode": "USD",
                            "minValue": 120000,
                            "maxValue": 150000,
                        },
                    ]
                }
            ]
        }
    }
    minimum, maximum, currency, period = _extract_salary(payload)
    assert (minimum, maximum) == (120000, 150000)
    assert currency == "USD"
    assert period == "year"


def test_company_name_cannot_be_derived_from_the_token(adapter: AshbyAdapter) -> None:
    """A stronger company-name check than test_company_name_comes_from_the_registry.

    That test uses BOARD.company == "Ramp" against BOARD.token == "ramp", so
    a bug that derived the name from the token via `.title()` would pass it
    undetected. This board's company name cannot be produced by transforming
    its token, so only reading `board.company` can satisfy the assertion.
    """
    board = BoardRef(
        company="Ramp Business Corporation",
        ats="ashby",
        token="ramp",
        nyc_presence=True,
    )
    normalized = AshbyAdapter(client=None).normalize(_raw_jobs()[0], board)
    assert normalized.company_name == "Ramp Business Corporation"


def test_source_updated_at_is_none_because_ashby_has_no_such_field(
    adapter: AshbyAdapter,
) -> None:
    for job in _board_payload()["jobs"]:
        assert not [k for k in job if "update" in k.lower() or "modif" in k.lower()]
    assert adapter.normalize(_raw_jobs()[0], BOARD).source_updated_at is None


def test_normalization_is_deterministic(adapter: AshbyAdapter) -> None:
    """M1 acceptance: same fixture in, byte-identical output, twice."""
    first = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    second = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    assert first == second


class TestInvariantI3:
    """A source telling us nothing must be distinguishable from a source
    telling us there is nothing."""

    async def test_populated_board_is_ok(self) -> None:
        adapter = AshbyAdapter(client=_StubClient(_board_payload()))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert outcome.jobs
        assert len(outcome.jobs) == 12
        assert outcome.is_authoritative_empty is False

    async def test_empty_jobs_array_is_authoritatively_empty(self) -> None:
        adapter = AshbyAdapter(client=_StubClient({"apiVersion": 1, "jobs": []}))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert outcome.jobs == ()
        assert outcome.is_authoritative_empty is True

    async def test_missing_jobs_key_is_not_read_as_empty(self) -> None:
        adapter = AshbyAdapter(client=_StubClient({"apiVersion": 1}))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False

    async def test_unreachable_board_is_not_ok(self) -> None:
        from nightshift.adapters.base import SourceUnavailableError

        adapter = AshbyAdapter(client=_StubClient(SourceUnavailableError("timeout")))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False

    async def test_wrong_shape_is_not_read_as_empty(self) -> None:
        """Ashby returns an object with a jobs array. A list at the top level
        means something changed upstream, and "no jobs" is the one conclusion
        we must not draw from it."""
        adapter = AshbyAdapter(client=_StubClient([]))
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
    """M1d: Ashby revalidates. Measured 2026-08-02 against the live `ramp`
    board — it serves `W/"job-board:291499f3..."` and answers 304.
    """

    async def test_a_304_yields_not_modified_and_describes_no_postings(self) -> None:
        client = _StubClient(None, not_modified=True)
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.ok is True
        assert outcome.not_modified is True
        assert outcome.jobs == ()
        assert outcome.listed == ()
        assert outcome.http_status == 304

    async def test_a_304_is_not_an_empty_board(self) -> None:
        """Ashby's empty-board case is a 200 carrying `{"jobs": []}` — real, and
        recorded in M1c as `ashby_0x_empty_board.json`. These must not collapse.
        """
        client = _StubClient(None, not_modified=True)
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.is_authoritative_empty is False

    async def test_a_304_keeps_the_etag_that_earned_it(self) -> None:
        client = _StubClient(None, not_modified=True)
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.etag == 'W/"abc"'

    async def test_the_stored_etag_reaches_the_client(self) -> None:
        client = _StubClient(_board_payload())
        await AshbyAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert client.seen_etags == ['W/"abc"']
        assert client.seen_urls == [BOARD_URL.format(token=BOARD.token)]

    async def test_no_etag_is_sent_on_a_first_poll(self) -> None:
        client = _StubClient(_board_payload())
        await AshbyAdapter(client=client).fetch_board(BOARD)

        assert client.seen_etags == [None]

    async def test_a_200_reports_the_new_etag_for_storage(self) -> None:
        client = _StubClient(_board_payload(), etag='W/"fresh"')
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD)

        assert outcome.not_modified is False
        assert outcome.etag == 'W/"fresh"'

    async def test_every_fetched_posting_is_also_listed(self) -> None:
        """Single-phase provider: the two sets describe the same postings.

        Freshness ages against `listed`, so an adapter that forgot to populate
        it would age every posting it had just fetched and close the board.
        """
        client = _StubClient(_board_payload())
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD)

        assert len(outcome.listed) > 0
        assert outcome.listed_source_job_ids == tuple(j.source_job_id for j in outcome.jobs)

    async def test_listed_postings_carry_no_timestamp(self) -> None:
        """Ashby publishes `publishedAt` and no updated-at field. Treating a
        publication date as a modification date would make every posting look
        changed on the poll after it appeared, and never again."""
        client = _StubClient(_board_payload())
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD)

        assert all(p.source_updated_at is None for p in outcome.listed)

    async def test_an_empty_board_lists_nothing_and_is_authoritative(self) -> None:
        client = _StubClient({"jobs": []})
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD)

        assert outcome.ok is True
        assert outcome.listed == ()
        assert outcome.is_authoritative_empty is True

    async def test_a_failure_still_reports_ok_false(self) -> None:
        client = _StubClient(SourceUnavailableError("boom", http_status=503))
        outcome = await AshbyAdapter(client=client).fetch_board(BOARD, etag='W/"abc"')

        assert outcome.ok is False
        assert outcome.not_modified is False
        assert outcome.is_authoritative_empty is False


class TestAdapterMetadata:
    def test_it_is_single_phase(self) -> None:
        """Ashby's board response carries every posting in full — 7,332
        characters of `descriptionHtml` on the first ramp posting, measured
        2026-08-02 — so there is nothing a second request could add."""
        assert AshbyAdapter(client=None).is_two_phase is False

    def test_it_declares_a_parser_version(self) -> None:
        assert AshbyAdapter(client=None).parser_version
