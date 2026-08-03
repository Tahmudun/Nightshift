"""Hot/warm tier derivation. M1d, ADR 0007.

A board is ``hot`` because of what its postings said, never because someone
ticked ``nyc_presence`` in the registry YAML. That is the whole point of
deriving it: the flag is a human's guess made once, and the postings are the
current truth.

Both directions are tested. A tier that can only be entered is a tier that
eventually contains everything, and "everything hourly" is the request volume
ADR 0007 exists to avoid.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import BoardTier, JobStatus, LocationConfidence, SourceType
from nightshift.db.models import Job
from nightshift.db.types import utcnow
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.tiers import NYC_WINDOW, derive_tier
from tests.conftest import requires_db

BOARD = BoardRef(company="Acme", ats="lever", token="acme")


def _posting(job_id: str, *, title: str, location: str) -> RawJob:
    """A Lever-shaped posting. Normalized by the real adapter, so the real
    location parser decides whether it is NYC — not this test."""
    return RawJob(
        source_job_id=job_id,
        source_company_key="acme",
        canonical_url=f"https://jobs.lever.co/acme/{job_id}",
        payload={
            "id": job_id,
            "text": title,
            "descriptionPlain": f"About {title}. " * 20,
            "hostedUrl": f"https://jobs.lever.co/acme/{job_id}",
            "categories": {"location": location, "allLocations": [location]},
            "createdAt": 1_750_000_000_000,
        },
    )


class _StubAdapter:
    source_name = "lever"
    source_type = SourceType.ATS_LEVER
    parser_version = "1"
    is_two_phase = False

    def __init__(self, postings: tuple[RawJob, ...]) -> None:
        self._inner = LeverAdapter(client=None)
        self._postings = postings

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        return FetchOutcome(board=board, ok=True, jobs=self._postings, http_status=200)

    def normalize(self, raw_job: RawJob, board: BoardRef) -> object:
        return self._inner.normalize(raw_job, board)


async def _ingest(
    session: AsyncSession, postings: tuple[RawJob, ...], *, now: object = None
) -> object:
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    await ingest_boards(session, _StubAdapter(postings), [BOARD], source=source, now=now)
    return source


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestDerivingATier:
    async def test_a_board_with_an_open_nyc_posting_is_hot(self, db_session: AsyncSession) -> None:
        source = await _ingest(
            db_session, (_posting("1", title="Engineer", location="New York, NY"),)
        )

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.HOT

    async def test_a_board_with_no_nyc_postings_is_warm(self, db_session: AsyncSession) -> None:
        source = await _ingest(
            db_session, (_posting("1", title="Engineer", location="Austin, TX"),)
        )

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.WARM

    async def test_a_board_with_no_postings_at_all_is_warm(self, db_session: AsyncSession) -> None:
        """A board nobody has ingested must not default to hourly — that would
        make every newly approved board hot on the strength of no evidence."""
        source = await get_or_create_source(
            db_session, name="lever_test", source_type=SourceType.ATS_LEVER
        )
        tier = await derive_tier(
            db_session, source_id=source.id, token="never-polled", now=utcnow()
        )
        assert tier is BoardTier.WARM

    async def test_one_nyc_posting_among_many_is_enough(self, db_session: AsyncSession) -> None:
        """The threshold is one. A company's *first* NYC role is exactly the
        event the product promises to catch the day it happens."""
        source = await _ingest(
            db_session,
            (
                _posting("1", title="Engineer", location="Austin, TX"),
                _posting("2", title="Designer", location="Berlin, Germany"),
                _posting("3", title="Analyst", location="Brooklyn, NY"),
            ),
        )

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.HOT

    async def test_every_borough_counts(self, db_session: AsyncSession) -> None:
        """Queens is New York City. A definition that only knows "New York"
        would demote an employer hiring in four of the five boroughs."""
        source = await _ingest(
            db_session, (_posting("1", title="Engineer", location="Queens, NY"),)
        )

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.HOT

    async def test_a_remote_posting_is_not_an_nyc_posting(self, db_session: AsyncSession) -> None:
        """Ashby marks 33 postings at its New York office `isRemote: true`
        (measured in M1a), so remoteness carries no location claim either way.
        The location parser decides; the tier reads what it decided."""
        source = await _ingest(db_session, (_posting("1", title="Engineer", location="Remote"),))

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.WARM


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestDemotion:
    async def test_a_board_whose_nyc_posting_closed_long_ago_demotes(
        self, db_session: AsyncSession
    ) -> None:
        """The direction that is easy to forget. A tier that can only be
        entered eventually contains every board, and "everything hourly" is the
        request volume ADR 0007 exists to avoid."""
        source = await _ingest(
            db_session, (_posting("1", title="Engineer", location="New York, NY"),)
        )
        job = (await db_session.execute(_all_jobs())).scalars().one()
        job.status = JobStatus.CLOSED
        job.last_seen_at = utcnow() - NYC_WINDOW - timedelta(days=1)
        # The schema refuses a closed job with no closed_at, which is the
        # constraint doing its job — a closure with no date is unauditable.
        job.closed_at = job.last_seen_at
        await db_session.flush()

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.WARM

    async def test_a_recently_closed_nyc_posting_still_counts(
        self, db_session: AsyncSession
    ) -> None:
        """An employer who closed an NYC role last week is still an NYC
        employer. Demoting instantly means missing their next posting by up to
        a day, which is the promise this whole design is about."""
        source = await _ingest(
            db_session, (_posting("1", title="Engineer", location="New York, NY"),)
        )
        job = (await db_session.execute(_all_jobs())).scalars().one()
        job.status = JobStatus.CLOSED
        job.last_seen_at = utcnow() - timedelta(days=7)
        job.closed_at = job.last_seen_at
        await db_session.flush()

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.HOT

    async def test_an_open_nyc_posting_keeps_a_board_hot_however_old(
        self, db_session: AsyncSession
    ) -> None:
        """A long-open role is still a role. The window is about how recently
        we had evidence, and an open posting is evidence now."""
        source = await _ingest(
            db_session, (_posting("1", title="Engineer", location="New York, NY"),)
        )
        job = (await db_session.execute(_all_jobs())).scalars().one()
        job.last_seen_at = utcnow() - timedelta(days=365)
        await db_session.flush()

        tier = await derive_tier(db_session, source_id=source.id, token="acme", now=utcnow())
        assert tier is BoardTier.HOT


class TestTheRegistryFlagIsNotConsulted:
    """ADR 0007: tier membership is computed from ingestion results and stored
    in the database, never hand-edited in the registry YAML.

    `board-discovery.md` §16 anticipates deleting `nyc_presence` entirely. These
    keep that a later cleanup rather than a behaviour change.

    Both inspect *code* with docstrings stripped, not raw source text. A test
    that greps prose fails the moment a comment explains why the thing it
    forbids is forbidden — which is exactly what happened when these were first
    written, and would have pushed the explanation out of the module to keep the
    test quiet.
    """

    def test_no_polling_module_reads_nyc_presence(self) -> None:
        from nightshift.domain import polling, tiers

        for module in (polling, tiers):
            assert "nyc_presence" not in _code_of(module), (
                f"{module.__name__} consults the registry flag; the tier must come "
                "from what the postings said"
            )

    def test_the_nyc_definition_has_exactly_one_home(self) -> None:
        """Two definitions of "is this NYC" is how the coverage page and the
        tiers start disagreeing about the same board."""
        from nightshift.domain import tiers

        code = _code_of(tiers).casefold()
        for borough in ("brooklyn", "staten island", "manhattan"):
            assert borough not in code, (
                "the borough list belongs in domain.locations and must be imported, "
                f"but {borough!r} appears in tiers.py's own code"
            )

    def test_the_shared_definition_is_the_one_the_parser_uses(self) -> None:
        """Imported rather than copied, so widening it in one place widens it
        everywhere — including `ParsedLocation.is_nyc`, which the discovery
        validator and the coverage page both go through."""
        from nightshift.domain import tiers
        from nightshift.domain.locations import NYC_CITY_NAMES, ParsedLocation

        assert tiers.NYC_CITY_NAMES is NYC_CITY_NAMES
        for name in NYC_CITY_NAMES:
            assert ParsedLocation(
                raw_text=name,
                city=name.title(),
                state="New York",
                country="United States",
                confidence=LocationConfidence.CITY_ONLY,
                is_primary=True,
            ).is_nyc, f"{name!r} is in the shared set but is_nyc rejects it"


def _code_of(module: object) -> str:
    """A module's source with every docstring removed.

    So a test forbidding a *reference* to something cannot be tripped by a
    comment explaining why the reference is forbidden.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))  # type: ignore[arg-type]
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _all_jobs() -> object:
    from sqlalchemy import select

    return select(Job)
