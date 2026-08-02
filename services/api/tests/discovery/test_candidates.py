"""The candidate file: what discovery writes and approval reads.

The rule this file exists to enforce is that **no candidate is ever discarded**
(board-discovery.md §6). A company between hiring rounds returns an empty
board; a provider having a bad morning returns a timeout. Neither is evidence
the board is worthless, and dropping either would recreate one level up the
mistake I3 forbids at the listing level — treating absence of data as data.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nightshift.discovery.candidates import (
    load_candidates,
    merge_candidate,
    save_candidates,
)
from nightshift.discovery.models import Candidate, CandidateFile, Verdict


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "ats": "ashby",
        "token": "0g",
        "verdict": Verdict.LIVE_NAMED,
        "company_name": "0g Labs",
        "posting_count": 4,
        "nyc_posting_count": 0,
        "first_seen": date(2026, 8, 2),
        "last_validated": date(2026, 8, 2),
        "source": "crawl_index",
    }
    return Candidate(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_round_trips_through_yaml(tmp_path: Path) -> None:
    path = tmp_path / "candidates.yaml"
    original = CandidateFile(candidates=(_candidate(),))
    save_candidates(original, path)
    assert load_candidates(path) == original


def test_an_absent_file_is_empty_not_an_error(tmp_path: Path) -> None:
    """The first discovery run has no file to read yet."""
    assert load_candidates(tmp_path / "nope.yaml").candidates == ()


def test_re_validating_updates_in_place_rather_than_appending() -> None:
    """Identity is (ats, token). Appending would grow the file without bound
    and make the approval report count one board several times."""
    file = CandidateFile(candidates=(_candidate(posting_count=4),))
    merged = merge_candidate(file, _candidate(posting_count=9))
    assert len(merged.candidates) == 1
    assert merged.candidates[0].posting_count == 9


def test_re_validating_preserves_the_original_first_seen() -> None:
    """`first_seen` is when we discovered it, not when we last looked."""
    file = CandidateFile(candidates=(_candidate(first_seen=date(2026, 7, 1)),))
    merged = merge_candidate(file, _candidate(first_seen=date(2026, 8, 2)))
    assert merged.candidates[0].first_seen == date(2026, 7, 1)


def test_the_same_token_on_two_providers_is_two_candidates() -> None:
    """`ramp` is a live board on both Lever and Ashby (M1a recorded both)."""
    file = CandidateFile(candidates=(_candidate(ats="ashby", token="ramp"),))
    merged = merge_candidate(file, _candidate(ats="lever", token="ramp"))
    assert len(merged.candidates) == 2


class TestNothingIsEverDiscarded:
    def test_an_empty_board_is_kept(self) -> None:
        candidate = _candidate(verdict=Verdict.EMPTY, company_name=None, posting_count=0)
        file = merge_candidate(CandidateFile(), candidate)
        assert len(file.candidates) == 1

    def test_an_unreachable_board_is_kept(self) -> None:
        candidate = _candidate(verdict=Verdict.UNREACHABLE, company_name=None, posting_count=0)
        file = merge_candidate(CandidateFile(), candidate)
        assert len(file.candidates) == 1

    def test_a_board_that_recovers_is_upgraded_not_duplicated(self) -> None:
        """The point of keeping them: an empty board becomes approvable the
        moment it returns named postings."""
        file = merge_candidate(
            CandidateFile(),
            _candidate(verdict=Verdict.EMPTY, company_name=None, posting_count=0),
        )
        file = merge_candidate(file, _candidate(verdict=Verdict.LIVE_NAMED))
        assert len(file.candidates) == 1
        assert file.candidates[0].verdict is Verdict.LIVE_NAMED


class TestUnvalidatedIsDistinctFromUnreachable:
    """A harvested token nobody has probed is not a board we failed to reach.

    Collapsing the two would make the coverage page report failures that never
    happened — the reporting version of treating absence of data as data.
    """

    def test_they_are_different_verdicts(self) -> None:
        assert Verdict.UNVALIDATED is not Verdict.UNREACHABLE

    def test_an_unvalidated_candidate_needs_no_name(self) -> None:
        candidate = _candidate(verdict=Verdict.UNVALIDATED, company_name=None, posting_count=0)
        assert candidate.verdict is Verdict.UNVALIDATED

    def test_a_probe_result_replaces_it_rather_than_adding_a_row(self) -> None:
        file = merge_candidate(
            CandidateFile(),
            _candidate(verdict=Verdict.UNVALIDATED, company_name=None, posting_count=0),
        )
        file = merge_candidate(file, _candidate(verdict=Verdict.LIVE_NAMED))
        assert len(file.candidates) == 1
        assert file.candidates[0].verdict is Verdict.LIVE_NAMED


class TestModelRefusesNonsense:
    def test_a_named_verdict_requires_a_name(self) -> None:
        """The whole approval gate rests on this field being trustworthy."""
        with pytest.raises(ValueError, match="live_named requires a company_name"):
            _candidate(verdict=Verdict.LIVE_NAMED, company_name=None)

    def test_an_unnamed_verdict_must_not_carry_a_name(self) -> None:
        """Otherwise a name could be filled in by hand and the candidate would
        still be routed to manual review while looking approvable."""
        with pytest.raises(ValueError, match="live_unnamed must not carry"):
            _candidate(verdict=Verdict.LIVE_UNNAMED, company_name="Invented Ltd")

    def test_a_token_that_could_escape_a_url_is_rejected(self) -> None:
        """The token is interpolated into a provider URL. registry.py already
        rejects these; the candidate file is the earlier door."""
        for bad in ("../etc", "a/b", "a?b", "a#b", ""):
            with pytest.raises(ValueError):
                _candidate(token=bad)

    def test_counts_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError):
            _candidate(posting_count=-1)

    def test_nyc_count_cannot_exceed_the_total(self) -> None:
        """It is a subset by construction. A violation means the validator is
        counting two different things, and the tier assignment in M1d reads
        this number."""
        with pytest.raises(ValueError, match="nyc_posting_count"):
            _candidate(posting_count=2, nyc_posting_count=5)


def test_the_file_is_written_sorted_for_a_reviewable_diff(tmp_path: Path) -> None:
    """A human reads this file as a git diff. Unsorted output would reshuffle
    on every run and make the diff unreadable, which is how a review step
    becomes a rubber stamp."""
    path = tmp_path / "candidates.yaml"
    file = CandidateFile(
        candidates=(
            _candidate(ats="ashby", token="zebra"),
            _candidate(ats="ashby", token="alpha"),
            _candidate(ats="greenhouse", token="beta"),
        )
    )
    save_candidates(file, path)
    text = path.read_text()
    assert text.index("alpha") < text.index("zebra")
    assert text.index("zebra") < text.index("beta")  # ats sorts before token
