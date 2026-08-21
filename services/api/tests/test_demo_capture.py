"""`make seed` plants one captured posting, so the demo shows the path.

M5a's second half. The capture route works, the badge renders, and until now
neither could be seen without a person opening `/operate/capture` and pasting
something. A feature nobody can reach from `make demo` is indistinguishable
from an unbuilt one — the same argument M4c Task 5 made about the lifecycle
marks, and the reason the seed already plants an application at every stage.

**Where the paste comes from is the whole design of this.** It is not typed
here. It is a real Greenhouse posting this repo already committed — Jump
Trading's campus AI research internship, recorded verbatim on 2026-08-04 for
the M3a eligibility corpus — rendered the way a person copying that job page
would have got it. So the demo's captured job carries a real title, a real
employer, a real location and real requirement text, and the only thing this
module reconstructs is the *layout* of a clipboard.

The alternative was inventing a posting, and it fails I7 in the way that is
hardest to see later: a fabricated job sitting in a corpus of real ones, with
nothing on the page marking which it is.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.cli import (
    DEMO_CAPTURE_RECORDING,
    DEMO_CAPTURE_SOURCE_JOB_ID,
    demo_capture,
    seed_demo_capture,
    source_label,
)
from nightshift.db.base import CaptureStatus, EmploymentType, SourceType
from nightshift.db.models import CapturedPosting, Job, Source, User
from nightshift.domain.capture import CAPTURE_SOURCE_NAME, employment_type_for_title, propose
from tests.conftest import requires_db

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _recorded_posting() -> dict[str, Any]:
    payload = json.loads(DEMO_CAPTURE_RECORDING.read_text())
    jobs = [job for job in payload["jobs"] if str(job["id"]) == DEMO_CAPTURE_SOURCE_JOB_ID]
    assert len(jobs) == 1, (
        f"the demo capture names posting {DEMO_CAPTURE_SOURCE_JOB_ID}, which is no "
        f"longer in {DEMO_CAPTURE_RECORDING.name}"
    )
    return dict(jobs[0])


# --------------------------------------------------------------------------
# The paste. No database — this is a rendering of a committed recording.
# --------------------------------------------------------------------------


def test_the_paste_is_the_recorded_posting_and_not_something_typed_here() -> None:
    """Every fact in the clipboard traces to the recording, verbatim.

    Asserted field by field against the recording rather than against a golden
    string: a golden string would keep passing while the recording underneath
    it changed, which is the one failure this test exists to catch.
    """
    recorded = _recorded_posting()
    capture = demo_capture()

    assert capture.title == recorded["title"]
    assert capture.company_name == recorded["company_name"]
    assert capture.location_text == recorded["location"]["name"]
    assert capture.source_url == recorded["absolute_url"]

    lines = capture.raw_text.splitlines()
    assert lines[0] == recorded["title"]
    assert recorded["company_name"] in lines[1]
    assert recorded["location"]["name"] in lines[1]


def test_the_paste_carries_the_posting_body_as_text_rather_than_as_markup() -> None:
    """A person's clipboard holds what the page rendered, not its source.

    Greenhouse serves `content` as escaped HTML. Pasting that verbatim would
    put `&lt;p&gt;` into a job description and — worse — into the description
    hash that gives the posting its identity, so the same opening captured
    from the rendered page would be a different job.
    """
    body = demo_capture().raw_text
    assert "&lt;" not in body and "&amp;" not in body
    assert "<p>" not in body and "<div" not in body
    # A verbatim sentence from the recording, chosen because it is the kind of
    # fact this product exists to surface (A13, and M3's authorization gate).
    assert "We accept students eligible for CPT/OPT" in body


def test_the_parser_reads_the_demo_paste_without_help() -> None:
    """`propose` against real posting text, not a paste written to suit it.

    Every other parser test in `test_capture.py` uses a hand-written paste,
    which proves the rules and proves nothing about the shape real text
    arrives in. This is the one case where the input was recorded from a board
    rather than composed alongside the assertion.
    """
    capture = demo_capture()
    proposal = propose(capture.raw_text)
    assert proposal.title == capture.title
    assert proposal.company_name == capture.company_name


def test_the_products_own_detector_agrees_the_demo_capture_is_an_internship() -> None:
    """The confirmed employment type is stated, and this is what stops it lying.

    `seed_demo_capture` confirms `internship` as a *person's* decision, so it
    is a literal rather than a call to the detector — a confirmation that
    re-ran the parser would not be a confirmation. This asserts the two agree,
    so a change to either goes red here instead of seeding a demo whose only
    internship is filed as full-time.
    """
    capture = demo_capture()
    assert capture.employment_type is EmploymentType.INTERNSHIP
    assert employment_type_for_title(capture.title) is EmploymentType.INTERNSHIP


# --------------------------------------------------------------------------
# The seeding. These need a database.
# --------------------------------------------------------------------------


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test", display_name="Seed User")
    session.add(user)
    await session.flush()
    return user


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_seeding_leaves_a_confirmed_capture_and_a_job_that_says_it_was_captured(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    await seed_demo_capture(db_session, user.id, now=NOW)

    capture = (await db_session.execute(select(CapturedPosting))).scalar_one()
    assert capture.status is CaptureStatus.CONFIRMED
    assert capture.decided_at == NOW
    assert capture.job_id is not None

    # I7's whole point: the job exists and is *marked*. A captured posting that
    # reached `jobs` attributed to a board would be indistinguishable from a
    # polled one, which is the failure the badge exists to prevent.
    source = (
        await db_session.execute(select(Source).where(Source.name == CAPTURE_SOURCE_NAME))
    ).scalar_one()
    assert source.source_type is SourceType.MANUAL_CAPTURE

    job = (await db_session.execute(select(Job).where(Job.id == capture.job_id))).scalar_one()
    assert job.title == demo_capture().title
    assert job.employment_type is EmploymentType.INTERNSHIP


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_seeding_twice_leaves_one_capture_and_one_job(db_session: AsyncSession) -> None:
    """`make seed` is run again by `reset-db`, `demo` and `acceptance`.

    `persist_source_job` already makes the *job* idempotent, so without a guard
    the visible damage is a `captured_postings` table that grows by one row per
    seed — a capture queue full of things nobody pasted, which is a lie about
    who did what.
    """
    user = await _a_user(db_session)
    await seed_demo_capture(db_session, user.id, now=NOW)
    await seed_demo_capture(db_session, user.id, now=NOW)

    captures = (
        await db_session.execute(select(func.count()).select_from(CapturedPosting))
    ).scalar_one()
    jobs = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert captures == 1
    assert jobs == 1


# --------------------------------------------------------------------------
# What the seed's own summary calls it.
# --------------------------------------------------------------------------


def test_the_seed_summary_labels_every_source_type_and_never_calls_a_capture_live() -> None:
    """The summary's label was a binary, and a third kind of source broke it.

    `fixture if source_type is FIXTURE else "live"` was true while there were
    exactly two kinds. A captured posting is the *least* live thing in the
    table — nothing re-reads it, which is the whole reason the job page carries
    a badge saying so — and the binary printed it as a live feed, next to
    `greenhouse`, in the one readout a developer scans after every seed.

    Exhaustive over the enum rather than a case per kind: the failure was a
    branch that had no answer for a new member, so the assertion that matters
    is that every member has one.
    """
    labels = {source_type: source_label(source_type) for source_type in SourceType}
    assert set(labels) == set(SourceType)
    assert all(label for label in labels.values())
    assert labels[SourceType.MANUAL_CAPTURE] != labels[SourceType.ATS_GREENHOUSE]
    assert "live" not in labels[SourceType.MANUAL_CAPTURE]
