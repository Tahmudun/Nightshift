"""The closure state machine, as a table of cases.

ADR 0009 fixes the thresholds: three consecutive misses AND seven elapsed days
to close, fourteen days without a successful poll to become unverified. The
cases below are organised around the two ways this function can be wrong —
closing a job that is open, and failing to close one that is gone — because
those failures are not symmetric. Closing a live job hides an opening the user
never learns about; keeping a dead one wastes a click.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    return RecordObservation(consecutive_misses=misses, last_seen_at=NOW - timedelta(days=days_ago))


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
        """A job described by two boards is only gone when both stop listing it.

        This is the rule that makes closure depend on dedupe, and the reason
        the two are one milestone.
        """
        assert _decide([_seen(0, misses=0), _seen(30, misses=40)]) is JobStatus.OPEN

    def test_old_but_still_listed_is_open_not_stale(self) -> None:
        """Age is not absence. A role posted a year ago and still on the board
        is open, and a freshness rule that confuses the two would close the
        long-running listings that are often the real openings."""
        assert _decide([_seen(365, misses=0)]) is JobStatus.OPEN


class TestBecomesStale:
    def test_three_misses_recently(self) -> None:
        assert _decide([_seen(1, misses=3)]) is JobStatus.POSSIBLY_STALE

    def test_three_misses_and_six_days_is_still_only_stale(self) -> None:
        """Both conditions are required, and six days is not seven."""
        assert _decide([_seen(6, misses=3)]) is JobStatus.POSSIBLY_STALE


class TestBecomesClosed:
    def test_three_misses_and_seven_days(self) -> None:
        assert _decide([_seen(7, misses=3)]) is JobStatus.CLOSED

    def test_all_sources_missing_and_long_gone(self) -> None:
        assert _decide([_seen(9, misses=5), _seen(9, misses=5)]) is JobStatus.CLOSED

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
        """Invariant I3, asserted directly and without a time limit.

        A source outage cannot close a job no matter how long the source stays
        down. This is the single most important assertion in the file: every
        other rule here is a policy choice, and this one is not.
        """
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

    def test_silence_outranks_a_miss_count(self) -> None:
        """A job with three stale misses on a board that has since gone silent
        is unverified, not stale: the misses were counted before we lost
        contact and are no longer current evidence."""
        assert _decide([_seen(30, misses=3)], polled_days_ago=20) is JobStatus.UNVERIFIED


class TestReopening:
    def test_a_closed_job_seen_again_reopens(self) -> None:
        """Reposts are ordinary. Refusing to reopen would leave the system
        permanently wrong about a job that is demonstrably available."""
        assert _decide([_seen(0, misses=0)], current=JobStatus.CLOSED) is JobStatus.OPEN

    def test_a_closed_job_still_missing_stays_closed(self) -> None:
        assert _decide([_seen(30, misses=30)], current=JobStatus.CLOSED) is JobStatus.CLOSED

    def test_reopening_says_so_in_the_reason(self) -> None:
        """The reason is the only human-readable trace of a reopen, since
        closed_at is nulled by it."""
        decision = decide_job_status(
            current=JobStatus.CLOSED,
            records=[_seen(0)],
            board_last_success_at=NOW,
            now=NOW,
        )
        assert decision.status is JobStatus.OPEN
        assert "closed" in decision.reason


class TestEdges:
    def test_a_job_with_no_records_is_unverified_not_closed(self) -> None:
        """Should be unreachable — every job has at least one link. If it ever
        happens, "we know nothing" is the honest answer and closing would be a
        fabrication."""
        assert _decide([]) is JobStatus.UNVERIFIED

    def test_every_decision_carries_a_reason_that_fits_the_column(self) -> None:
        """I4's spirit: no bare verdict. The reason reaches
        job_status_events.reason, which is String(200)."""
        for records, current in (
            ([_seen(0)], JobStatus.OPEN),
            ([_seen(1, misses=3)], JobStatus.OPEN),
            ([_seen(7, misses=3)], JobStatus.POSSIBLY_STALE),
            ([_seen(0)], JobStatus.CLOSED),
            ([], JobStatus.OPEN),
        ):
            decision = decide_job_status(
                current=current, records=records, board_last_success_at=NOW, now=NOW
            )
            assert decision.reason
            assert len(decision.reason) <= 200


class TestThresholdsAreTheOnesTheAdrFixed:
    """If these change, ADR 0009 is out of date and must be superseded first.

    The test exists because the thresholds are a product decision the human
    made, not an implementation detail an engineer may retune quietly.
    """

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
