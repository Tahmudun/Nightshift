"""Classifying a discovered token into one of five verdicts.

The load-bearing test is `test_a_live_but_unnameable_board_cannot_be_bulk_approved`.
A board can return HTTP 200 with well-formed postings — every automated
liveness check passes it — while nothing anywhere says who the employer is. It
is the single case that stops the approval gate becoming decorative.

**What changed between the design and this recording, on 2026-08-02.**
`board-discovery.md` §6 names `a3c41b8b71eff8c4` as that case: at design time it
returned 200 with ten well-formed postings under a machine-generated token. It
no longer exists — its API endpoint 404s, and it is absent from the July 2026
crawl index in a range the committed slice covers, so it is gone rather than
transiently missing.

What survived is better evidence than a single dead token. Ashby serves
**HTTP 200 with the bare title `Jobs`** for any token that does not exist, which
is recorded verbatim in `ashby_unnameable_page.html`. So the unnameable page is
a real, reproducible shape rather than a hypothetical, and the verdict test pairs
it with a real live board payload. The plan this task came from stubbed that page
with hand-written HTML; a recording is strictly stronger.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from nightshift.adapters.base import SourceUnavailableError
from nightshift.discovery.models import Verdict
from nightshift.discovery.validate import extract_ashby_name, validate_token

FIXTURES = Path(__file__).parent.parent / "fixtures"
TODAY = date(2026, 8, 2)


class _StubClient:
    """Replaces the network, not the module under test.

    Keyed by URL substring so one stub can serve a board *and* a board page,
    which is what Ashby validation actually needs. The longest matching
    fragment wins, so `/boards/6sense` and `/boards/6sense/jobs` can coexist
    without the result depending on dict insertion order.
    """

    def __init__(self, routes: dict[str, Any]) -> None:
        self._routes = routes
        self.requested: list[str] = []

    def _match(self, url: str) -> Any:
        self.requested.append(url)
        matches = [fragment for fragment in self._routes if fragment in url]
        if not matches:
            raise SourceUnavailableError(f"no stub route for {url}", http_status=404)
        result = self._routes[max(matches, key=len)]
        if isinstance(result, Exception):
            raise result
        return result

    async def get_json(self, url: str) -> Any:
        return self._match(url)

    async def get_text(self, url: str) -> str:
        result = self._match(url)
        return result if isinstance(result, str) else json.dumps(result)


def _load(*parts: str) -> Any:
    return json.loads(FIXTURES.joinpath(*parts).read_text())


def _text(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text()


class TestAshbyNameExtraction:
    def test_resolves_the_real_company_name(self) -> None:
        """board-discovery.md §13: `0g` must resolve to "0g Labs", not "0g".

        A test that accepted the token would pass against a suffix-stripping
        bug and prove nothing.
        """
        assert extract_ashby_name(_text("discovery", "ashby_0g_page.html")) == "0g Labs"

    def test_a_real_recorded_unnameable_page_yields_none(self) -> None:
        """The recorded 200-with-title-`Jobs` page Ashby serves for a token that
        does not exist. None routes the candidate to manual review, which is the
        safe direction; returning the token would be I2."""
        assert extract_ashby_name(_text("discovery", "ashby_unnameable_page.html")) is None

    def test_strips_the_jobs_suffix_ashby_appends(self) -> None:
        assert extract_ashby_name("<title>Acme Corp Jobs</title>") == "Acme Corp"

    def test_a_page_with_no_title_yields_none(self) -> None:
        assert extract_ashby_name("<html><body>nothing</body></html>") is None

    def test_a_title_that_is_only_the_suffix_yields_none(self) -> None:
        assert extract_ashby_name("<title>Jobs</title>") is None

    def test_a_company_actually_called_jobs_survives(self) -> None:
        """Suffix stripping must not eat a real name. "Jobs Jobs" is the page
        Ashby would serve for an employer named Jobs, and reducing it to None
        would lose a real board to a cosmetic rule."""
        assert extract_ashby_name("<title>Jobs Jobs</title>") == "Jobs"


class TestVerdicts:
    async def test_greenhouse_name_comes_from_the_board_endpoint(self) -> None:
        client = _StubClient(
            {
                "/boards/6sense/jobs": _load("discovery", "greenhouse_6sense_jobs.json"),
                "/boards/6sense": _load("discovery", "greenhouse_6sense_meta.json"),
            }
        )
        candidate = await validate_token(
            client, ats="greenhouse", token="6sense", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_NAMED
        assert candidate.company_name == "6sense"

    async def test_ashby_name_comes_from_the_board_page(self) -> None:
        client = _StubClient(
            {
                "posting-api/job-board/0g": _load("discovery", "ashby_0g_board.json"),
                "jobs.ashbyhq.com/0g": _text("discovery", "ashby_0g_page.html"),
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="0g", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_NAMED
        assert candidate.company_name == "0g Labs"
        assert candidate.company_name != "0g", "the token is not the name (I2)"

    async def test_a_live_but_unnameable_board_cannot_be_bulk_approved(self) -> None:
        """The case the whole approval gate exists for.

        A live board with real postings, whose page does not name an employer.
        Every automated liveness check passes it. Only the name requirement
        catches it, and only because the name has to come from somewhere real.

        Both halves are recordings: a live Ashby board, and the page Ashby
        really serves when a token names nothing.
        """
        board = _load("discovery", "ashby_0g_board.json")
        assert len(board["jobs"]) >= 1, "fixture lost its postings; it proves nothing empty"
        client = _StubClient(
            {
                "posting-api/job-board/0g": board,
                "jobs.ashbyhq.com/0g": _text("discovery", "ashby_unnameable_page.html"),
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="0g", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_UNNAMED
        assert candidate.company_name is None
        assert candidate.posting_count >= 1, "it is live — that is what makes it dangerous"

    async def test_a_name_already_in_the_registry_is_a_collision(self) -> None:
        """Not a rejection: it is either a duplicate board or two genuinely
        different employers, and only a human can say which.

        Measured on 2026-08-02: the crawl slice holds both `Abridge` and
        `abridge`, two Ashby tokens whose pages give the same employer name.
        Case-variant duplicate tokens are real, not theoretical.
        """
        client = _StubClient(
            {
                "/boards/6sense/jobs": _load("discovery", "greenhouse_6sense_jobs.json"),
                "/boards/6sense": _load("discovery", "greenhouse_6sense_meta.json"),
            }
        )
        candidate = await validate_token(
            client,
            ats="greenhouse",
            token="6sense",
            today=TODAY,
            known_names=frozenset({"6sense"}),
        )
        assert candidate.verdict is Verdict.NAME_COLLISION
        assert candidate.company_name == "6sense", "a collision still records who it collided with"

    async def test_an_empty_lever_board_is_empty_not_unreachable(self) -> None:
        """I3's distinction, at the discovery layer. M1a recorded the `plaid`
        empty board specifically so this branch has a real payload."""
        client = _StubClient({"postings/plaid": _load("lever", "plaid_empty_board.json")})
        candidate = await validate_token(
            client, ats="lever", token="plaid", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.EMPTY
        assert candidate.posting_count == 0

    async def test_an_empty_ashby_board_is_empty_not_unreachable(self) -> None:
        """The same distinction on a second provider, because the payload shape
        differs: Lever's empty board is `[]`, Ashby's is `{"jobs": []}`. A check
        written against one shape can read the other as malformed."""
        client = _StubClient(
            {"posting-api/job-board/0x": _load("discovery", "ashby_0x_empty_board.json")}
        )
        candidate = await validate_token(
            client, ats="ashby", token="0x", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.EMPTY
        assert candidate.posting_count == 0

    async def test_an_empty_board_costs_no_name_lookup(self) -> None:
        """There is nothing to approve, so the extra request would be waste
        repeated across every dormant board in the registry."""
        client = _StubClient(
            {"posting-api/job-board/0x": _load("discovery", "ashby_0x_empty_board.json")}
        )
        await validate_token(client, ats="ashby", token="0x", today=TODAY, known_names=frozenset())
        assert len(client.requested) == 1

    async def test_a_404_is_unreachable_not_empty(self) -> None:
        """Collapsing these two is exactly the I3 violation ADR 0003 exists to
        prevent, one level up from listings."""
        client = _StubClient({"postings/ramp": SourceUnavailableError("HTTP 404", http_status=404)})
        candidate = await validate_token(
            client, ats="lever", token="ramp", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE
        assert candidate.posting_count == 0

    async def test_a_timeout_is_unreachable(self) -> None:
        client = _StubClient({"postings/slow": SourceUnavailableError("timeout")})
        candidate = await validate_token(
            client, ats="lever", token="slow", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE

    async def test_a_200_with_the_wrong_shape_is_unreachable_not_empty(self) -> None:
        """A provider that changes its payload shape has told us nothing about
        whether the board has jobs, and "no jobs" is the one conclusion we must
        not draw from it."""
        client = _StubClient({"posting-api/job-board/weird": {"postings": []}})
        candidate = await validate_token(
            client, ats="ashby", token="weird", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE

    async def test_a_junk_element_inside_a_live_board_does_not_kill_the_sweep(self) -> None:
        """`{"jobs": [null, {...}]}` is a live board with one bad element. The
        list shape is checked; its contents are whatever the provider sent."""
        client = _StubClient(
            {
                "posting-api/job-board/mixed": {
                    "jobs": [None, {"location": "New York, NY"}],
                    "apiVersion": "1",
                },
                "jobs.ashbyhq.com/mixed": "<title>Mixed Jobs</title>",
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="mixed", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_NAMED
        assert candidate.posting_count == 2
        assert candidate.nyc_posting_count == 1

    async def test_validation_never_raises(self) -> None:
        """A discovery run over thousands of tokens must not stop at the first
        bad one. The route fragment matches the URL on purpose — a stub that
        missed would raise SourceUnavailableError instead and this test would
        pass without ever reaching the branch it is about."""
        client = _StubClient({"job-board/explodes": RuntimeError("something unexpected")})
        candidate = await validate_token(
            client, ats="ashby", token="explodes", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE
        assert "RuntimeError" in (candidate.notes or "")

    async def test_a_failed_name_lookup_does_not_lose_the_board(self) -> None:
        """The board is live and we know it. Losing the postings because a
        second request failed would throw away what we did learn."""
        client = _StubClient(
            {
                "posting-api/job-board/0g": _load("discovery", "ashby_0g_board.json"),
                "jobs.ashbyhq.com/0g": SourceUnavailableError("HTTP 503", http_status=503),
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="0g", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_UNNAMED
        assert candidate.posting_count >= 1


class TestNycCounting:
    async def test_counts_nyc_postings_from_parsed_locations(self) -> None:
        """board-discovery.md §8: NYC-ness is read off the postings by the
        parser, never declared. M1d's hot tier reads this number."""
        client = _StubClient(
            {
                "posting-api/job-board/ramp": _load("ashby", "ramp_board.json"),
                "jobs.ashbyhq.com/ramp": "<title>Ramp Jobs</title>",
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="ramp", today=TODAY, known_names=frozenset()
        )
        assert candidate.nyc_posting_count > 0
        assert candidate.nyc_posting_count <= candidate.posting_count

    async def test_a_board_with_no_nyc_postings_counts_zero(self) -> None:
        """Non-vacuity for the test above: a counter that returned
        `posting_count` would pass it and fail this one."""
        client = _StubClient(
            {
                "posting-api/job-board/0g": _load("discovery", "ashby_0g_board.json"),
                "jobs.ashbyhq.com/0g": _text("discovery", "ashby_0g_page.html"),
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="0g", today=TODAY, known_names=frozenset()
        )
        assert candidate.posting_count >= 1
        assert candidate.nyc_posting_count == 0


async def test_ashby_costs_one_extra_request_and_only_at_discovery_time() -> None:
    """The name lookup is per *candidate*, not per poll. If it ever leaked into
    polling it would double the request count against Ashby forever."""
    client = _StubClient(
        {
            "posting-api/job-board/0g": _load("discovery", "ashby_0g_board.json"),
            "jobs.ashbyhq.com/0g": _text("discovery", "ashby_0g_page.html"),
        }
    )
    await validate_token(client, ats="ashby", token="0g", today=TODAY, known_names=frozenset())
    assert len(client.requested) == 2


async def test_greenhouse_costs_one_extra_request_too_but_not_an_html_one() -> None:
    """Greenhouse states the name in its own API, so discovery never fetches a
    Greenhouse page. If it started to, that would be a silent doubling of load
    on a provider that did not need it."""
    client = _StubClient(
        {
            "/boards/6sense/jobs": _load("discovery", "greenhouse_6sense_jobs.json"),
            "/boards/6sense": _load("discovery", "greenhouse_6sense_meta.json"),
        }
    )
    await validate_token(
        client, ats="greenhouse", token="6sense", today=TODAY, known_names=frozenset()
    )
    assert len(client.requested) == 2
    assert not any("boards.greenhouse.io" in url for url in client.requested)


async def test_an_unknown_ats_is_refused_loudly() -> None:
    """A typo in a provider name must not silently classify every board as
    unreachable and quietly empty the registry."""
    with pytest.raises(ValueError, match="unknown ats"):
        await validate_token(
            _StubClient({}), ats="workday", token="x", today=TODAY, known_names=frozenset()
        )


async def test_an_unknown_ats_is_refused_before_any_request() -> None:
    """Loudly *and* without touching the network — otherwise a typo becomes a
    sweep of thousands of pointless requests to a URL template that is wrong."""
    client = _StubClient({})
    with pytest.raises(ValueError):
        await validate_token(client, ats="workday", token="x", today=TODAY, known_names=frozenset())
    assert client.requested == []
