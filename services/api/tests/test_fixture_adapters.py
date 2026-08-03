"""The three fixture adapters that make ``make demo`` work offline. ADR 0004.

These had no tests until M1d, and M1d is what proved they needed them. Twice:

* They override ``fetch_board`` themselves, so when ``FetchOutcome`` grew the
  *listed* set they silently reported boards that listed nothing — which ages
  every seeded posting and closes the demo corpus three seeds later.
* ``FixtureGreenhouseAdapter`` subclasses the real Greenhouse adapter, which
  became two-phase. It inherited ``is_two_phase = True`` along with a
  ``fetch_full_board`` that reaches for an HTTP client this adapter
  deliberately does not have, so ``make seed`` would have crashed.

Neither is visible from the unit tests of the real adapters, and neither would
have failed anything until a human ran ``make demo``. That is the gap this file
closes: the offline path is a product surface, not a test convenience.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightshift.adapters.base import BoardRef, JobSourceAdapter, TwoPhaseJobSourceAdapter
from nightshift.cli import (
    ASHBY_FIXTURE_DIR,
    FIXTURE_DIR,
    LEVER_FIXTURE_DIR,
    FixtureAshbyAdapter,
    FixtureGreenhouseAdapter,
    FixtureLeverAdapter,
)
from nightshift.db.base import SourceType

GREENHOUSE_BOARD = BoardRef(company="Datadog", ats="greenhouse", token="datadog")
LEVER_BOARD = BoardRef(company="Alloy", ats="lever", token="alloy")
ASHBY_BOARD = BoardRef(company="Ramp", ats="ashby", token="ramp")


def _adapters() -> list[tuple[str, object, BoardRef]]:
    return [
        (
            "greenhouse",
            FixtureGreenhouseAdapter(FIXTURE_DIR / "datadog_board.json"),
            GREENHOUSE_BOARD,
        ),
        ("lever", FixtureLeverAdapter(LEVER_FIXTURE_DIR / "alloy_board.json"), LEVER_BOARD),
        ("ashby", FixtureAshbyAdapter(ASHBY_FIXTURE_DIR / "ramp_board.json"), ASHBY_BOARD),
    ]


@pytest.mark.parametrize(("name", "adapter", "board"), _adapters(), ids=lambda v: str(v)[:20])
class TestEveryFixtureAdapter:
    async def test_it_reads_its_committed_recording(
        self, name: str, adapter: object, board: BoardRef
    ) -> None:
        outcome = await adapter.fetch_board(board)  # type: ignore[attr-defined]

        assert outcome.ok is True
        assert len(outcome.jobs) > 0, f"{name} fixture produced no postings"

    async def test_everything_it_returns_is_also_listed(
        self, name: str, adapter: object, board: BoardRef
    ) -> None:
        """The M1d regression. A fixture adapter reporting jobs but no listing
        looks to freshness like a board that listed nothing, so every seeded
        posting takes a miss on each `make seed` and the offline demo corpus
        closes itself out from under the Operate page — with no error anywhere.
        """
        outcome = await adapter.fetch_board(board)  # type: ignore[attr-defined]

        assert outcome.listed_source_job_ids == tuple(j.source_job_id for j in outcome.jobs)
        assert outcome.is_authoritative_empty is False

    def test_it_is_single_phase(self, name: str, adapter: object, board: BoardRef) -> None:
        """The recording *is* the whole board, so there is no second phase.

        Greenhouse is the one that can get this wrong by inheritance: the real
        adapter is two-phase, and inheriting that flag sends the pipeline to a
        `fetch_full_board` that needs an HTTP client this adapter does not have.
        """
        assert adapter.is_two_phase is False  # type: ignore[attr-defined]

    def test_it_cannot_reach_the_network(self, name: str, adapter: object, board: BoardRef) -> None:
        """I7, structurally. These are constructed with no client at all, so a
        flipped kill switch cannot turn the offline demo into a live fetch."""
        assert adapter._client is None  # type: ignore[attr-defined]

    def test_it_is_labelled_as_a_fixture_in_the_data(
        self, name: str, adapter: object, board: BoardRef
    ) -> None:
        """ADR 0004: every job it creates must be traceable to a recording
        rather than being indistinguishable from live data."""
        assert adapter.source_type is SourceType.FIXTURE  # type: ignore[attr-defined]
        assert adapter.source_name.endswith("_fixture")  # type: ignore[attr-defined]

    def test_it_still_satisfies_the_adapter_protocol(
        self, name: str, adapter: object, board: BoardRef
    ) -> None:
        assert isinstance(adapter, JobSourceAdapter)

    async def test_normalization_is_the_real_code_path(
        self, name: str, adapter: object, board: BoardRef
    ) -> None:
        """ADR 0004's whole point: only the bytes' origin differs from
        production. If these overrode `normalize` too, the demo would be
        exercising nothing."""
        outcome = await adapter.fetch_board(board)  # type: ignore[attr-defined]
        normalized = adapter.normalize(outcome.jobs[0], board)  # type: ignore[attr-defined]

        assert normalized.title
        assert normalized.company_name == board.company
        assert normalized.description_hash


class TestTheGreenhouseFixtureSpecifically:
    """It is the only one subclassing an adapter whose behaviour changed."""

    def test_it_does_not_inherit_the_two_phase_capability_check(self) -> None:
        """`isinstance` against the two-phase Protocol is structural, so this
        adapter still answers True — it inherits the methods. The flag is what
        the pipeline gates on, and the flag is what must be False here."""
        adapter = FixtureGreenhouseAdapter(FIXTURE_DIR / "datadog_board.json")

        assert isinstance(adapter, TwoPhaseJobSourceAdapter), (
            "inherited from the real adapter — this is why the flag, not the "
            "Protocol, is what the pipeline gates on"
        )
        assert adapter.is_two_phase is False

    async def test_an_unreadable_fixture_is_a_failure_not_an_empty_board(
        self, tmp_path: Path
    ) -> None:
        """I3 reaches the demo path too. A missing recording must not read as a
        board with no postings, or a broken checkout would close the corpus."""
        adapter = FixtureGreenhouseAdapter(tmp_path / "does-not-exist.json")
        outcome = await adapter.fetch_board(GREENHOUSE_BOARD)

        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False

    async def test_the_recording_it_reads_is_the_committed_one(self) -> None:
        """Guards the fixture as well as the adapter: `make demo`'s corpus size
        is quoted in PROGRESS, and a silently truncated recording would change
        it without changing any code."""
        payload = json.loads((FIXTURE_DIR / "datadog_board.json").read_text())
        adapter = FixtureGreenhouseAdapter(FIXTURE_DIR / "datadog_board.json")
        outcome = await adapter.fetch_board(GREENHOUSE_BOARD)

        assert len(outcome.jobs) == len(payload["jobs"])
