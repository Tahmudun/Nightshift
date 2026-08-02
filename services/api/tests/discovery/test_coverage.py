"""The coverage report, and the blind spots it is required to name.

`board-discovery.md` §11: "A missing coverage number is worse than a low one."
The M1 acceptance criterion is not that the page reports coverage — it is that
it names what is *not* covered. So that is what these tests assert.

Most of these run against the pure summary rather than the route, because the
thing under test is what the report is willing to say, and that is a property
of the module rather than of HTTP. The route tests exist to prove the same
guarantees survive serialisation, which is where a nullable count is most
likely to quietly become a zero.
"""

from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from nightshift.api.main import create_app
from nightshift.discovery.coverage import (
    STRUCTURAL_BLIND_SPOTS,
    coverage_summary,
    format_coverage,
)
from nightshift.discovery.models import Candidate, CandidateFile, Verdict
from nightshift.domain.registry import get_registry, load_registry

# The blind spots §11 requires by name. Each is a real gap with a real reason,
# and a coverage page that omits one is claiming a completeness it does not have.
REQUIRED_BLIND_SPOTS = {
    "lever_undiscovered",
    "workday_icims_taleo",
    "no_public_board",
    "aggregator_only",
}


def _candidates() -> CandidateFile:
    return CandidateFile(
        candidates=(
            Candidate(
                ats="ashby",
                token="named",
                verdict=Verdict.LIVE_NAMED,
                company_name="Named Co",
                posting_count=4,
                nyc_posting_count=1,
                first_seen=date(2026, 8, 2),
                last_validated=date(2026, 8, 2),
                source="crawl_index",
            ),
            Candidate(
                ats="ashby",
                token="mystery",
                verdict=Verdict.LIVE_UNNAMED,
                posting_count=10,
                first_seen=date(2026, 8, 2),
                last_validated=date(2026, 8, 2),
                source="crawl_index",
            ),
            Candidate(
                ats="ashby",
                token="fresh",
                verdict=Verdict.UNVALIDATED,
                first_seen=date(2026, 8, 2),
                last_validated=date.min,
                source="crawl_index",
            ),
        )
    )


def _summary() -> object:
    return coverage_summary(candidates=_candidates(), registry=get_registry())


class TestItNamesWhatIsNotCovered:
    """The acceptance criterion, asserted four ways."""

    def test_names_every_required_blind_spot(self) -> None:
        named = {spot.id for spot in _summary().blind_spots}  # type: ignore[attr-defined]
        missing = REQUIRED_BLIND_SPOTS - named
        assert not missing, f"the coverage report hides these gaps: {sorted(missing)}"

    def test_every_blind_spot_explains_itself(self) -> None:
        """An id nobody can read is not a disclosure."""
        for spot in _summary().blind_spots:  # type: ignore[attr-defined]
            assert len(spot.explanation) > 40, spot.id

    def test_the_lever_gap_states_the_structural_reason(self) -> None:
        """Not "we haven't got round to Lever" — Common Crawl *cannot* see it,
        by Lever's own robots.txt, and it never will (ADR 0006). Those are
        different disclosures to somebody deciding whether to trust the corpus.
        """
        lever = next(s for s in STRUCTURAL_BLIND_SPOTS if s.id == "lever_undiscovered")
        assert "ccbot" in lever.explanation.lower() or "robots" in lever.explanation.lower()

    def test_the_structural_gaps_do_not_claim_a_size_they_cannot_know(self) -> None:
        """`count=None`, never 0. Counting NYC employers on Workday would mean
        enumerating NYC employers, which is the problem itself — and a 0 there
        reads as "no gap"."""
        for spot in STRUCTURAL_BLIND_SPOTS:
            assert spot.count is None, f"{spot.id} claims a count it cannot have"


class TestItRefusesToInventANumber:
    def test_reports_no_percentage_of_the_market(self) -> None:
        """There is no denominator. Nobody knows how many NYC tech jobs exist,
        so a coverage percentage would be a fabricated statistic — exactly the
        confident-sounding number I6 forbids."""
        summary = _summary()
        assert not any("percent" in field for field in vars(summary)), (
            "a percentage of the whole market has no denominator"
        )

    def test_the_text_report_says_why_there_is_no_percentage(self) -> None:
        """Omitting the number is necessary but not sufficient: a reader who
        expected one has to be told it was withheld deliberately."""
        text = format_coverage(_summary())  # type: ignore[arg-type]
        assert "no denominator" in text.lower()

    def test_a_measured_gap_reports_its_real_size(self) -> None:
        """Non-vacuity for the null-count rule above: if everything were None,
        `count` would be decorative and this test would fail."""
        summary = _summary()
        probed = next(
            s
            for s in summary.blind_spots  # type: ignore[attr-defined]
            if s.id == "candidates_never_probed"
        )
        assert probed.count == 1


class TestCandidateBreakdown:
    def test_is_broken_down_by_verdict_not_collapsed_to_one_number(self) -> None:
        """A single "pending" number would hide that live_unnamed candidates
        need a human and empty ones do not."""
        summary = _summary()
        assert set(summary.candidates_by_verdict) >= {  # type: ignore[attr-defined]
            "live_named",
            "live_unnamed",
            "name_collision",
            "empty",
            "unreachable",
        }

    def test_never_probed_is_counted_apart_from_unreachable(self) -> None:
        """The distinction Task 4 added. Collapsing them would report failures
        that never happened."""
        by_verdict = _summary().candidates_by_verdict  # type: ignore[attr-defined]
        assert by_verdict["unvalidated"] == 1
        assert by_verdict["unreachable"] == 0

    def test_a_verdict_with_no_candidates_is_reported_as_zero_not_omitted(self) -> None:
        """An absent key renders as a blank cell, which reads as "no data"
        rather than "none of these"."""
        by_verdict = _summary().candidates_by_verdict  # type: ignore[attr-defined]
        assert set(by_verdict) == {v.value for v in Verdict}


class TestTheCommittedRegistryIsReportedHonestly:
    def test_disabled_boards_are_counted_as_not_polled(self) -> None:
        """The registry's own `stripe` entry is `disabled`. A coverage report
        that counted every registry row as covered would overstate reach by
        exactly the boards somebody deliberately turned off."""
        registry = load_registry()
        summary = coverage_summary(candidates=CandidateFile(), registry=registry)
        assert summary.boards_pollable <= summary.boards_total
        not_polled = next(s for s in summary.blind_spots if s.id == "registry_boards_not_polled")
        assert not_polled.count == summary.boards_total - summary.boards_pollable


@pytest.mark.asyncio
async def test_the_route_serves_it_all_including_the_nulls() -> None:
    """The route needs no database — coverage is a question about which boards
    exist, not about what has been ingested — so it is exercised directly.

    The null counts are the assertion that matters here: a serialiser that
    coerced `None` to `0` would turn "we cannot know" into "there is no gap",
    silently, on the one page whose job is to admit ignorance.
    """
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/coverage")

    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["boards"]["by_ats"], dict)
    assert REQUIRED_BLIND_SPOTS <= {spot["id"] for spot in body["blind_spots"]}
    assert set(body["candidates"]) >= {
        "live_named",
        "live_unnamed",
        "name_collision",
        "empty",
        "unreachable",
    }

    lever = next(s for s in body["blind_spots"] if s["id"] == "lever_undiscovered")
    assert lever["count"] is None, "an unknown size must survive serialisation as null"

    assert "percent_of_market" not in body
    assert "coverage_percent" not in body
