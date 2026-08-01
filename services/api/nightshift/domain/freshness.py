"""The closure state machine (PRODUCT-SPEC §7.4, ADR 0009).

Pure by design: this module takes observations and returns a verdict. It never
touches a session, so every branch of a four-state machine with two thresholds
is cheap to assert, and the database applier in :mod:`nightshift.domain.ingestion`
stays a translation layer with no policy in it.

Invariant I3 is the reason for that shape. This function is only ever called
with observations from a board that *answered* — a failed fetch produces no
observation at all — so there is no code path here that can close a job because
a request failed. The guard is structural rather than conditional, which is the
strongest form available: you cannot pass this function an outage.

``possibly_stale`` and ``unverified`` are not two words for the same doubt:

* ``possibly_stale`` — the board answered and this job was not in the answer.
  That is evidence about the job.
* ``unverified`` — the board did not answer. That is evidence about the
  *source*, and none whatever about the job.

Only the first can ever reach ``closed``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from nightshift.db.base import JobStatus

# ADR 0009. Both closure conditions are required, and they are a pair on
# purpose: a miss count alone stops meaning anything once ADR 0007 gives
# different boards different poll rates (three misses is three hours on the hot
# tier and three days on the warm one), and elapsed time alone would close a
# job on a board nobody re-checked. Together they read as "we looked at least
# three times, spread over at least a week, and it was gone every time".
MISSES_BEFORE_STALE = 3
DAYS_ABSENT_BEFORE_CLOSED = 7
DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED = 14

# Bumped whenever a threshold or a transition changes, so a change in closure
# behaviour is attributable rather than mysterious.
CLOSURE_RULESET_VERSION = "1"


@dataclass(frozen=True, slots=True)
class RecordObservation:
    """What one source record looked like after the most recent poll."""

    consecutive_misses: int
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class ClosureDecision:
    """A verdict and the sentence that explains it.

    The reason is stored on ``job_status_events.reason`` and is what a human
    reads when asking why a job disappeared, so it is written for that reader
    rather than for a log parser.
    """

    status: JobStatus
    reason: str


def decide_job_status(
    *,
    current: JobStatus,
    records: Sequence[RecordObservation],
    board_last_success_at: datetime | None,
    now: datetime,
) -> ClosureDecision:
    """Decide what state a canonical job should be in.

    Order matters and each step depends on the one above:

    1. If the board has not answered in a fortnight we know nothing about the
       job, whatever its counters say — those counters were recorded before we
       lost contact and are no longer current evidence.
    2. If any source still lists it, it is open. A job described by two boards
       is gone only when both stop listing it.
    3. Absence closes it only when both ADR 0009 conditions hold.
    """
    unverified_after = timedelta(days=DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED)
    if board_last_success_at is None or now - board_last_success_at >= unverified_after:
        return ClosureDecision(
            JobStatus.UNVERIFIED,
            f"no successful poll of this board in {DAYS_WITHOUT_POLL_BEFORE_UNVERIFIED} days",
        )

    if not records:
        # Unreachable in practice: every job reaches at least one source record
        # through job_source_links. If it ever happens, "we know nothing" is the
        # honest answer and closing would be a fabrication.
        return ClosureDecision(JobStatus.UNVERIFIED, "job has no source records")

    if any(record.consecutive_misses == 0 for record in records):
        if current is JobStatus.CLOSED:
            return ClosureDecision(JobStatus.OPEN, "listed again after being closed")
        return ClosureDecision(JobStatus.OPEN, "listed at the most recent poll")

    # Every source is missing it. `min` rather than `max`: the weakest evidence
    # governs, so one recently-added source that has only missed it once keeps
    # the job open until that source has looked three times too.
    misses = min(record.consecutive_misses for record in records)
    last_seen = max(record.last_seen_at for record in records)
    absent_for = now - last_seen

    if misses < MISSES_BEFORE_STALE:
        return ClosureDecision(
            JobStatus.OPEN,
            f"missing from {misses} poll(s), fewer than the {MISSES_BEFORE_STALE} required",
        )

    if absent_for >= timedelta(days=DAYS_ABSENT_BEFORE_CLOSED):
        return ClosureDecision(
            JobStatus.CLOSED,
            f"missing from {misses} consecutive polls over {absent_for.days} days",
        )

    return ClosureDecision(
        JobStatus.POSSIBLY_STALE,
        f"missing from {misses} consecutive polls, but only {absent_for.days} days "
        f"since it was last listed ({DAYS_ABSENT_BEFORE_CLOSED} required to close)",
    )
