"""Dedupe against a real database: candidate generation, merging, provenance.

The invariant under test is that a merge never loses a source link. A canonical
job is *derived* from raw records, so losing an edge does not lose data — it
loses the path to it, and a job nobody can trace back to a posting is exactly
what M1's acceptance criterion forbids.

Postings here are real recorded Lever payloads with their identifiers and, where
a scenario needs it, their titles changed. Building them by hand would have
risked asserting against a shape no board produces; changing an id is not a
claim about the source, and each variant says which field it altered and why.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, NormalizedSourceJob, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import SourceType
from nightshift.db.models import (
    Job,
    JobEmbedding,
    JobLocation,
    JobMergeEvent,
    JobSourceLink,
    SourceJobRecord,
)
from nightshift.domain.ingestion import IngestionStats, get_or_create_source, ingest_boards
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)
NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _first_posting() -> dict[str, Any]:
    """One real recorded Lever posting, deep-copied so variants cannot alias."""
    board = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    return copy.deepcopy(board[0])


def _variant(**changes: Any) -> dict[str, Any]:
    """A copy of the recorded posting with named fields changed.

    Only `id`, `hostedUrl` and `text` are ever changed, and every call site
    says which and why. The description, location and commitment come through
    untouched, so the dedupe decision is made on the real payload's content.
    """
    posting = _first_posting()
    posting.update(changes)
    return posting


class _StubAdapter:
    """The real adapter with only its network call replaced."""

    def __init__(self, postings: list[dict[str, Any]]) -> None:
        self._inner = LeverAdapter(client=None)
        self._postings = postings
        self.source_name = self._inner.source_name
        self.source_type = self._inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return FetchOutcome(
            board=board,
            ok=True,
            http_status=200,
            jobs=tuple(
                RawJob(
                    source_job_id=str(posting["id"]),
                    source_company_key=board.token,
                    canonical_url=posting.get("hostedUrl"),
                    payload=posting,
                )
                for posting in self._postings
            ),
        )

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        return self._inner.normalize(raw_job, board)


async def _ingest(
    session: AsyncSession, postings: list[dict[str, Any]]
) -> tuple[Any, IngestionStats]:
    source = await get_or_create_source(
        session, name="lever_merge_test", source_type=SourceType.ATS_LEVER
    )
    return await ingest_boards(session, _StubAdapter(postings), [BOARD], source=source, now=NOW)


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# Two postings that differ only in identity: a re-published requisition.
DUPLICATE_PAIR = [
    _variant(id="dup-1", hostedUrl="https://jobs.lever.co/alloy/dup-1"),
    _variant(id="dup-2", hostedUrl="https://jobs.lever.co/alloy/dup-2"),
]


async def test_two_postings_with_identical_content_become_one_job(
    db_session: AsyncSession,
) -> None:
    await _ingest(db_session, DUPLICATE_PAIR)
    assert await _count(db_session, Job) == 1
    # Both raw records are kept. Dedupe collapses the canonical view, never the
    # evidence underneath it.
    assert await _count(db_session, SourceJobRecord) == 2


async def test_a_merge_keeps_every_source_link(db_session: AsyncSession) -> None:
    """M1 acceptance: every canonical job traces to at least one raw record —
    and after a merge, to all of them."""
    await _ingest(db_session, DUPLICATE_PAIR)
    assert await _count(db_session, JobSourceLink) == 2

    job = (await db_session.execute(select(Job))).scalars().one()
    links = (
        (await db_session.execute(select(JobSourceLink).where(JobSourceLink.job_id == job.id)))
        .scalars()
        .all()
    )
    assert len(links) == 2
    assert {link.link_reason for link in links} == {"sole_source_record", "identical_content"}


async def test_a_merge_writes_an_audit_row_with_its_evidence(
    db_session: AsyncSession,
) -> None:
    """I4's spirit: the merge stores what decided it, not only that it happened."""
    await _ingest(db_session, DUPLICATE_PAIR)
    event = (await db_session.execute(select(JobMergeEvent))).scalars().one()
    assert event.reason == "identical_content"
    assert event.ruleset_version == "1"
    assert 0.0 < float(event.match_confidence) <= 1.0
    assert event.loser_snapshot["normalized_title"]
    assert event.winner_job_id != event.loser_job_id


async def test_the_merged_job_no_longer_exists_but_is_still_named(
    db_session: AsyncSession,
) -> None:
    """The loser row is gone, so its id survives only on the audit row. That is
    why job_merge_events.loser_job_id carries no foreign key."""
    await _ingest(db_session, DUPLICATE_PAIR)
    event = (await db_session.execute(select(JobMergeEvent))).scalars().one()
    survivor = (
        await db_session.execute(select(Job.id).where(Job.id == event.loser_job_id))
    ).scalar_one_or_none()
    assert survivor is None


async def test_different_titles_stay_two_jobs(db_session: AsyncSession) -> None:
    """The direction that costs a user a job if it goes wrong.

    Identical description, identical location, identical everything except the
    title — which §7.5 says is never enough on its own to merge.
    """
    await _ingest(
        db_session,
        [
            _variant(
                id="t-1", hostedUrl="https://jobs.lever.co/alloy/t-1", text="Backend Engineer"
            ),
            _variant(
                id="t-2",
                hostedUrl="https://jobs.lever.co/alloy/t-2",
                text="Staff Backend Engineer",
            ),
        ],
    )
    assert await _count(db_session, Job) == 2
    assert await _count(db_session, JobMergeEvent) == 0


async def test_the_recorded_board_does_not_self_merge(db_session: AsyncSession) -> None:
    """Nine genuinely distinct postings must stay nine jobs.

    This is the regression that a too-eager matcher causes and that no
    synthetic pair would catch: real boards contain roles that look alike.
    """
    board = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    _, stats = await _ingest(db_session, board)
    assert stats.created == 9
    assert await _count(db_session, Job) == 9
    assert await _count(db_session, JobMergeEvent) == 0


async def test_re_ingesting_a_merged_board_is_idempotent(db_session: AsyncSession) -> None:
    """M1 acceptance: no dupes, no spurious updates — including after a merge.

    The failure this guards is a merge that re-fires on the second poll,
    churning the audit table and oscillating the canonical job.
    """
    await _ingest(db_session, DUPLICATE_PAIR)
    merges_after_first = await _count(db_session, JobMergeEvent)
    assert merges_after_first == 1

    _, stats = await _ingest(db_session, DUPLICATE_PAIR)
    assert stats.created == 0
    assert await _count(db_session, Job) == 1
    assert await _count(db_session, JobMergeEvent) == merges_after_first


async def test_every_job_still_traces_to_a_raw_record(db_session: AsyncSession) -> None:
    await _ingest(db_session, DUPLICATE_PAIR)
    orphans = (
        await db_session.execute(
            select(func.count())
            .select_from(Job)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .where(JobSourceLink.id.is_(None))
        )
    ).scalar_one()
    assert orphans == 0


async def test_an_embedding_is_stored_for_each_surviving_job(
    db_session: AsyncSession,
) -> None:
    """A5: model name and dimension on every row, so a model swap is a backfill."""
    await _ingest(db_session, DUPLICATE_PAIR)
    embeddings = (await db_session.execute(select(JobEmbedding))).scalars().all()
    assert len(embeddings) == await _count(db_session, Job)
    for embedding in embeddings:
        assert embedding.model_name == "BAAI/bge-small-en-v1.5"
        assert embedding.dimension == 384
        assert len(embedding.embedding) == 384


async def test_an_unchanged_repoll_does_not_re_embed(db_session: AsyncSession) -> None:
    """Embedding is keyed on the description hash. A re-poll of unchanged text
    must do no model work, or every poll pays for the whole corpus."""
    await _ingest(db_session, DUPLICATE_PAIR)
    before = (
        await db_session.execute(select(JobEmbedding.updated_at, JobEmbedding.source_hash))
    ).all()
    await _ingest(db_session, DUPLICATE_PAIR)
    after = (
        await db_session.execute(select(JobEmbedding.updated_at, JobEmbedding.source_hash))
    ).all()
    assert before == after


async def test_a_merge_absorbs_locations_the_winner_did_not_have(
    db_session: AsyncSession,
) -> None:
    """Silent data loss, found by probing rather than by reading.

    Two cross-posted listings of one role can name different sets of offices —
    one board says "Washington, DC", the other says "Washington, DC" and
    "Austin, TX". They share a location, so they merge; the loser is then
    deleted and its `job_locations` rows cascade away with it.

    The raw payload survives, so nothing is unrecoverable. But the canonical
    job then under-reports where the role actually is, and a user filtering for
    Austin would never see it — which defeats A2's "one row per location the
    posting names" at the exact moment two sources agree it is one job.
    """
    shared = _first_posting()["categories"]["allLocations"]
    a = _variant(id="loc-a", hostedUrl="https://jobs.lever.co/alloy/loc-a")
    b = _variant(id="loc-b", hostedUrl="https://jobs.lever.co/alloy/loc-b")
    b["categories"] = {**b["categories"], "allLocations": [*shared, "Austin, TX"]}

    await _ingest(db_session, [a, b])
    assert await _count(db_session, Job) == 1, "the pair did not merge; the test proves nothing"

    raw_texts = (await db_session.execute(select(JobLocation.raw_text))).scalars().all()
    assert any("Austin" in text for text in raw_texts), (
        f"the merge dropped a location only the loser named: {sorted(raw_texts)}"
    )

    # Exactly one primary. Absorbing rows must not produce two.
    primaries = (
        await db_session.execute(
            select(func.count()).select_from(JobLocation).where(JobLocation.is_primary.is_(True))
        )
    ).scalar_one()
    assert primaries == 1


async def test_absorbing_locations_does_not_duplicate_shared_ones(
    db_session: AsyncSession,
) -> None:
    """The control for the test above: a merge of two identical location sets
    must not end up with each office listed twice."""
    await _ingest(db_session, DUPLICATE_PAIR)
    rows = (await db_session.execute(select(JobLocation.raw_text))).scalars().all()
    assert len(rows) == len(set(rows)), f"duplicate location rows after merge: {sorted(rows)}"
