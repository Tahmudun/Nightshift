"""``FetchOutcome``'s I3 guarantees, including the two M1d adds.

Three different things carry no jobs: a failed fetch, a genuinely empty board,
and a ``304 Not Modified``. Only one of them — the empty board — is evidence
that postings closed. Conflating the other two with it is the most destructive
single bug available in this system, because it does not error and it does not
show up until the closure thresholds elapse.

The second addition is the *listed* versus *fetched* distinction. Greenhouse
polls in two phases (ADR 0007): the listing names every posting, and only the
ones that changed get their content fetched. ``listed`` is what freshness ages
against; ``jobs`` is what normalization runs over. Collapsing those closes every
unchanged posting on every Greenhouse board — see
``docs/architecture/conditional-polling.md`` §4.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nightshift.adapters.base import BoardRef, FetchOutcome, ListedPosting, RawJob

BOARD = BoardRef(company="Acme", ats="greenhouse", token="acme")


def _raw(job_id: str) -> RawJob:
    return RawJob(source_job_id=job_id, source_company_key="acme", payload={"id": job_id})


def _listed(job_id: str, updated_at: datetime | None = None) -> ListedPosting:
    return ListedPosting(source_job_id=job_id, source_updated_at=updated_at)


class TestNotModified:
    def test_a_304_is_not_an_authoritative_empty_board(self) -> None:
        """The M1d bug, stated as an assertion.

        A 304 is a success carrying no jobs, and so is an empty board. Under the
        pre-M1d definition — `ok and not jobs` — the first reads as the second,
        and every posting on every unchanged board closes.
        """
        outcome = FetchOutcome(board=BOARD, ok=True, not_modified=True, etag='W/"abc"')
        assert outcome.is_authoritative_empty is False

    def test_a_genuinely_empty_board_still_is_one(self) -> None:
        """The guard must not be satisfied by never trusting anything. A board
        that answered and has no postings is a real, different fact."""
        outcome = FetchOutcome(board=BOARD, ok=True, http_status=200)
        assert outcome.is_authoritative_empty is True

    def test_a_failed_fetch_is_not_authoritative_empty(self) -> None:
        outcome = FetchOutcome(board=BOARD, ok=False, error="timeout")
        assert outcome.is_authoritative_empty is False

    def test_a_304_cannot_carry_jobs(self) -> None:
        """Belt and braces: the confusion cannot even be expressed.

        A 304 has no body, so an adapter returning postings beside it has a bug,
        and every downstream guard would be reasoning about a state that cannot
        physically occur.
        """
        with pytest.raises(ValidationError):
            FetchOutcome(board=BOARD, ok=True, not_modified=True, jobs=(_raw("1"),))

    def test_a_304_cannot_carry_listed_postings(self) -> None:
        with pytest.raises(ValidationError):
            FetchOutcome(board=BOARD, ok=True, not_modified=True, listed=(_listed("1"),))

    def test_a_304_keeps_its_etag(self) -> None:
        """It is still the valid one — it is what earned the 304 — and the poll
        state writer stores it back unchanged."""
        outcome = FetchOutcome(board=BOARD, ok=True, not_modified=True, etag='W/"abc"')
        assert outcome.etag == 'W/"abc"'

    def test_not_modified_defaults_to_false(self) -> None:
        """Every FetchOutcome built before M1d, and every one built by a plain
        200 path, must read as modified without saying so."""
        assert FetchOutcome(board=BOARD, ok=True).not_modified is False


class TestListedVersusFetched:
    def test_listed_ids_are_exposed_for_freshness(self) -> None:
        outcome = FetchOutcome(
            board=BOARD,
            ok=True,
            listed=(_listed("1", datetime(2026, 8, 1, tzinfo=UTC)), _listed("2")),
        )
        assert outcome.listed_source_job_ids == ("1", "2")

    def test_listed_may_exceed_fetched(self) -> None:
        """Greenhouse phase 2: ten postings listed, one changed and fetched."""
        outcome = FetchOutcome(
            board=BOARD,
            ok=True,
            jobs=(_raw("1"),),
            listed=tuple(_listed(str(n)) for n in range(1, 11)),
        )
        assert len(outcome.listed_source_job_ids) == 10
        assert len(outcome.jobs) == 1

    def test_a_board_with_listings_but_no_fetches_is_not_authoritative_empty(self) -> None:
        """Phase 1 named ten postings; phase 2 fetched none because nothing
        changed. That is the *normal* state of a healthy Greenhouse board, and
        it is emphatically not an empty one."""
        outcome = FetchOutcome(board=BOARD, ok=True, jobs=(), listed=(_listed("1"),))
        assert outcome.is_authoritative_empty is False

    def test_listed_defaults_to_empty(self) -> None:
        assert FetchOutcome(board=BOARD, ok=True).listed == ()

    def test_listed_preserves_the_order_the_board_gave(self) -> None:
        """Not sorted here. Determinism is the adapter's job and is asserted on
        the normalized output; re-ordering at this layer would hide a provider
        that started returning postings in a different order each poll."""
        outcome = FetchOutcome(
            board=BOARD, ok=True, listed=(_listed("c"), _listed("a"), _listed("b"))
        )
        assert outcome.listed_source_job_ids == ("c", "a", "b")

    def test_a_listed_posting_may_have_no_timestamp(self) -> None:
        """Lever and Ashby publish none, measured 2026-08-02. They need none —
        their board response already carries every posting in full, so there is
        no second fetch for a timestamp to gate."""
        assert _listed("1").source_updated_at is None


class TestImmutability:
    def test_the_outcome_is_frozen(self) -> None:
        outcome = FetchOutcome(board=BOARD, ok=True, jobs=(_raw("1"),))
        with pytest.raises(ValidationError):
            outcome.ok = False  # type: ignore[misc]

    def test_a_listed_posting_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            _listed("1").source_job_id = "2"  # type: ignore[misc]
