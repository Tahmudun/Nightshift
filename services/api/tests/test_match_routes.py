"""The score crossing into a response, and the row that must never cross.

M3c Task 9. `test_scoring.py` grades the arithmetic, `test_matching_golden.py`
pins it, and `test_match_recompute.py` checks it survives a round trip through
Postgres. None of those can see the half this file is about: what the browser is
handed, and what it is not.

Three properties, and each one has a plausible implementation that fails it:

* **A stale row reads as not-yet-computed.** `match_results` legitimately holds
  several rows for one pair — §4.2 keeps old versions so a bump can be compared
  against what it replaced — so a route that takes the newest row, or the only row
  it finds, serves exactly the rows the version filter exists to refuse. That
  implementation passes every other test in this file.
* **The breakdown is complete or the response is not a score.** Six components,
  each with its evidence, its weight, and whether it could be assessed at all. I4
  is a claim about the breakdown, not about the total, so a response carrying
  `overall_score` and five components is the invariant failing while looking fine.
* **Nothing is recomputed on read.** Every number comes off the stored row. A
  serialiser that re-runs the scorer to fill in a field it could not find is the
  second derivation `matching.posting_for` is written about, and here it would
  produce a breakdown that can disagree with the total above it.

Each file under tests/ defines its own `client` fixture rather than sharing one,
because the override covers `current_user_id` as well as the session — the same
reason `test_job_requirement_routes.py` records.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.base import (
    EvidenceSource,
    JobTextField,
    LocationConfidence,
    MatchComponent,
    ProficiencyLevel,
    RemotePolicy,
    RemotePreference,
    ResolutionMethod,
    SkillSourceType,
)
from nightshift.db.models import (
    Job,
    JobLocation,
    MatchComponentAssessment,
    MatchEvidence,
    MatchResult,
    User,
    UserSkill,
)
from nightshift.db.session import get_db_session
from nightshift.domain import matching
from nightshift.domain.eligibility import evaluate, profile_from_user
from nightshift.domain.eligibility_reading import read_posting
from nightshift.domain.ingestion import sync_requirements
from nightshift.domain.matching_weights import load_weights
from nightshift.domain.requirement_extraction import RequirementProposal
from nightshift.domain.scoring import DEFERRED_COMPONENTS, WEIGHT_NAME
from tests.conftest import make_job_with_text, requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

#: Long enough that skill overlap, the missing-requirement penalty and role
#: relevance are all live, so the response under test has a breakdown worth
#: asserting about rather than six zeroes.
DESCRIPTION = (
    "About the role. We are hiring for our core team in New York. "
    "Requirements: strong Python, experience with PostgreSQL, and familiarity with Docker. "
    "Nice to have: Kubernetes."
)

TODAY = datetime(2026, 8, 9, tzinfo=UTC).date()


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    """Somebody with a confirmed skill and stated preferences.

    All three of `preferred_roles`, `preferred_locations` and the confirmed skill
    matter: without them role relevance, location and skill overlap are all
    unassessable or zero, and a response of six blanks would satisfy most of the
    assertions below without exercising anything.
    """
    row = User(
        email=f"match-route-{uuid.uuid4().hex[:12]}@example.test",
        display_name="Test User",
        years_experience=1,
        preferred_roles=["software engineer"],
        preferred_locations=["New York"],
        remote_preference=RemotePreference.HYBRID,
    )
    db_session.add(row)
    await db_session.flush()
    db_session.add(
        UserSkill(
            user_id=row.id,
            name="Python",
            normalized_name="python",
            skill_id="Python",
            proficiency_level=ProficiencyLevel.UNSPECIFIED,
            source_type=SkillSourceType.MANUAL,
        )
    )
    await db_session.flush()
    loaded = await matching._load_user(db_session, row.id)
    assert loaded is not None
    return loaded


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession, user: User) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _user() -> uuid.UUID:
        return user.id

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[current_user_id] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def job(db_session: AsyncSession) -> Job:
    """A posting with its requirements extracted, as ingestion would leave it.

    A `job_locations` row and a `remote_policy` are both part of the fixture, not
    decoration: the location component compares those two against the person's
    stated preferences, and without them it is unassessable — which would make
    `test_an_exempt_component_carries_what_it_compared` pass by never reaching the
    thing it is about.
    """
    row = await make_job_with_text(db_session, DESCRIPTION)
    row.title = "Software Engineer"
    row.source_published_at = datetime.now(tz=UTC) - timedelta(days=2)
    row.remote_policy = RemotePolicy.HYBRID
    db_session.add(
        JobLocation(
            job_id=row.id,
            raw_text="New York, NY",
            city="New York",
            state="NY",
            country="US",
            # I1: no coordinates, so the confidence says so. The location
            # component reads the city and never a point (§9, "coordinates are
            # M4"), so `city_only` is the honest value and enough for the score.
            location_confidence=LocationConfidence.CITY_ONLY,
            resolution_method=ResolutionMethod.SOURCE_TEXT_PARSE,
            is_primary=True,
        )
    )
    await sync_requirements(db_session, row)
    await db_session.flush()
    return row


async def _score(db_session: AsyncSession, user: User, job: Job) -> MatchResult:
    stored = await matching.score_pair(
        db_session, user=user, job=job, weights=load_weights(), as_of=TODAY
    )
    assert stored is not None
    await db_session.flush()
    return stored


async def _detail(client: AsyncClient, job: Job) -> dict[str, Any]:
    response = await client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


# ---------------------------------------------------------------------------
# A stored score reaches the page, decomposed
# ---------------------------------------------------------------------------


async def test_a_stored_score_reaches_the_job_detail(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    stored = await _score(db_session, user, job)

    match = (await _detail(client, job))["match"]
    assert match is not None
    assert match["overall_score"] == stored.overall_score
    assert match["assessed_out_of"] == stored.assessed_out_of
    assert match["penalty_score"] == stored.penalty_score
    assert match["ruleset_version"] == load_weights().ruleset_version
    assert match["model_version"] is None


async def test_the_response_carries_all_six_components_with_their_weights(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """I4 is a claim about the breakdown. Five components is the invariant failing.

    `weight` is asserted against `data/matching.yaml` rather than against a
    literal: it is what the page renders the points *out of*, and a component
    shown as 18 out of the wrong number is a bar that misreports how well the
    person did on it.
    """
    stored = await _score(db_session, user, job)
    weights = load_weights()

    components = (await _detail(client, job))["match"]["components"]
    assert [row["component"] for row in components] == [c.value for c in MatchComponent]

    by_name = {row["component"]: row for row in components}
    for component in MatchComponent:
        row = by_name[component.value]
        assert row["weight"] == weights.weight(WEIGHT_NAME[component])
        assert row["points"] == getattr(stored, matching.COMPONENT_SCORE_COLUMNS[component])
        assert row["points"] <= row["weight"]
        assert row["why"].strip()


async def test_a_positive_component_carries_the_evidence_behind_it(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """The database refuses a positive component with no evidence row; this is
    the other half — that the rows reach the response rather than being dropped
    by the serialiser, which no database guard can see."""
    await _score(db_session, user, job)

    components = (await _detail(client, job))["match"]["components"]
    scoring = [row for row in components if row["points"] > 0]
    assert scoring, "the fixture must produce at least one positive component"
    for row in scoring:
        assert row["evidence"], f"{row['component']} scored {row['points']} with no evidence"


async def test_a_person_claim_quotes_both_sides_in_the_response(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """§2.1 at the boundary: the two spans that make a claim about somebody
    auditable have to survive serialisation, or the page can only paraphrase."""
    await _score(db_session, user, job)

    components = (await _detail(client, job))["match"]["components"]
    person_claims = [
        evidence
        for row in components
        if row["component"] in {"role", "skill", "project"}
        for evidence in row["evidence"]
    ]
    assert person_claims, "the fixture must produce at least one claim about the person"
    for evidence in person_claims:
        assert evidence["job_span_text"]
        assert evidence["user_span_text"]
        assert evidence["job_span_field"] in {"title", "description_text"}
        assert evidence["proposed_by"] == "rule"


async def test_a_quoted_span_is_a_literal_substring_of_the_field_it_names(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """§7.2's first equality, checked on what the browser actually receives.

    The database trigger already refuses a span that does not quote its field, so
    this is not a second copy of that guard — it is the assertion that the offsets
    and the text stay together through serialisation. The page highlights against
    these numbers, and an offset that drifted by one underlines the wrong words
    while looking entirely plausible.
    """
    await _score(db_session, user, job)

    detail = await _detail(client, job)
    substrate = {"title": detail["title"], "description_text": detail["description_text"]}
    quoted = [
        evidence
        for row in detail["match"]["components"]
        for evidence in row["evidence"]
        if evidence["job_span_text"] is not None
    ]
    assert quoted, "the fixture must produce at least one quoted span"
    for evidence in quoted:
        text = substrate[evidence["job_span_field"]]
        assert (
            text[evidence["job_char_start"] : evidence["job_char_end"]] == evidence["job_span_text"]
        )


async def test_an_exempt_component_carries_what_it_compared(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """§2.1 exempts location, freshness and priority from quoting a person — not
    from being inspectable. Without `compared` the page shows a number for those
    three with nothing behind it, which is I4 with a smaller blast radius."""
    await _score(db_session, user, job)

    components = {
        row["component"]: row for row in (await _detail(client, job))["match"]["components"]
    }
    location = components["location"]
    assert location["evidence"], "the fixture must make location assessable"
    for evidence in location["evidence"]:
        assert evidence["user_span_text"] is None
        assert evidence["compared"], "an exempt component records what it weighed"


# ---------------------------------------------------------------------------
# §5.1.1 — zero and unassessable are different answers
# ---------------------------------------------------------------------------


async def test_a_terse_posting_names_what_could_not_be_assessed_and_why(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """The response distinguishes the two things the score columns cannot.

    A posting naming no required technology makes skill overlap and project
    evidence unassessable, and both store `0` — the same `0` a component that
    genuinely found nothing stores. §5.1.1 turns on telling those apart, and the
    denominator cannot: several subsets of the six weights sum to the same number,
    so `assessed_out_of` names how much was assessed and never which.
    """
    terse = await make_job_with_text(
        db_session, "We are hiring. Come and work with a friendly team in New York."
    )
    terse.title = "Software Engineer"
    terse.source_published_at = datetime.now(tz=UTC) - timedelta(days=2)
    await sync_requirements(db_session, terse)
    await db_session.flush()
    await _score(db_session, user, terse)

    match = (await _detail(client, terse))["match"]
    by_name = {row["component"]: row for row in match["components"]}

    assert by_name["skill"]["assessable"] is False
    assert by_name["skill"]["points"] == 0
    assert "no required technologies" in by_name["skill"]["why"]
    assert by_name["project"]["assessable"] is False

    # And not everything, or the distinction is untested: freshness read a real
    # publication date off this posting and is assessable at zero-or-more.
    assert by_name["freshness"]["assessable"] is True

    # The denominator agrees with the rows, which is what the ranked list sorts on.
    assert match["assessed_out_of"] == sum(
        row["weight"] for row in match["components"] if row["assessable"]
    )
    assert match["assessed_out_of"] < 100
    assert match["fraction"] == pytest.approx(match["overall_score"] / match["assessed_out_of"])


async def test_a_pair_nothing_could_be_assessed_on_has_a_null_fraction(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`null`, never `0.0`. Zero sorts a posting last as though it had been
    measured and found wanting; null says nobody could measure it.

    Reached with an empty profile against a posting with no technologies, no
    publication date and no readable level — five pairs in the committed corpus
    reach the same state, so this is a real row rather than a contrived one.
    """
    stranger = User(email=f"empty-{uuid.uuid4().hex[:12]}@example.test")
    db_session.add(stranger)
    await db_session.flush()
    loaded = await matching._load_user(db_session, stranger.id)
    assert loaded is not None

    bare = await make_job_with_text(db_session, "We are hiring. Apply if interested.")
    bare.title = "Associate"
    bare.source_published_at = None
    await sync_requirements(db_session, bare)
    await db_session.flush()
    stored = await _score(db_session, loaded, bare)
    assert stored.assessed_out_of == 0, "this fixture must reach an empty denominator"

    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _stranger() -> uuid.UUID:
        return stranger.id

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[current_user_id] = _stranger
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        match = (await _detail(http, bare))["match"]
    app.dependency_overrides.clear()

    assert match["assessed_out_of"] == 0
    assert match["fraction"] is None
    assert match["overall_score"] == 0


# ---------------------------------------------------------------------------
# The stale row, which is what this task is named for
# ---------------------------------------------------------------------------


async def test_a_pair_with_no_stored_score_reads_as_not_yet_computed(
    client: AsyncClient, job: Job
) -> None:
    """Null, and the rest of the detail response is unaffected.

    The page has one honest sentence for this, and the assertion that matters is
    the second one: a missing score must not take the job page down with it, or
    every posting the sweep has not reached yet is unreadable.
    """
    detail = await _detail(client, job)
    assert detail["match"] is None
    assert detail["title"] == "Software Engineer"
    assert detail["requirements"], "the rest of the response still renders"


async def test_a_score_at_an_older_ruleset_version_is_not_served(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """The task's own criterion: a stale row reads as not-yet-computed.

    Not as a score with a staleness badge, and not as a score at all. §4.2's
    reason is that a number produced by arithmetic that no longer exists is not a
    worse score — the components underneath it were weighed differently, and the
    evidence offsets were taken against rules that have moved.
    """
    stored = await _score(db_session, user, job)
    stored.ruleset_version = "0+1999-01-01.1"
    await db_session.flush()

    assert (await _detail(client, job))["match"] is None


async def test_the_current_version_is_served_beside_a_stale_one_that_scores_higher(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """The test the plausible implementation fails, and it fails silently.

    §4.2 keeps old-version rows on purpose, so this pair really does have two
    rows. A route reaching for the newest, or the highest-scoring, or the first
    row it finds returns the stale one — and there is nothing on the page to
    suggest it.

    The stale row is given an explicitly later `created_at` and a higher
    `overall_score`, so each of those shortcuts picks it *deterministically*.
    Writing it second is not enough and this test was measured making that
    mistake: `created_at` defaults to `now()`, which is the transaction timestamp
    and identical for every row written in one transaction, so an
    `ORDER BY created_at DESC` mutation returned the correct row about as often as
    the wrong one. A test that catches a bug half the time is a flake in whichever
    direction it lands.
    """
    current = await _score(db_session, user, job)
    real_score = current.overall_score
    assert real_score < 100, "the fixture needs room for a higher stale score"

    stale = MatchResult(
        user_id=user.id,
        job_id=job.id,
        overall_score=100,
        assessed_out_of=100,
        eligibility_status=current.eligibility_status,
        role_score=100,
        skill_score=0,
        project_evidence_score=0,
        location_score=0,
        freshness_score=0,
        priority_score=0,
        penalty_score=0,
        ruleset_version="0+1999-01-01.1",
        created_at=datetime.now(tz=UTC) + timedelta(days=1),
    )
    # A well-formed row in every other respect, so the only thing that can keep it
    # out of the response is its version.
    stale.evidence = [
        MatchEvidence(
            component=MatchComponent.ROLE,
            points=100,
            job_span_text=job.title,
            job_span_field=JobTextField.TITLE,
            job_char_start=0,
            job_char_end=len(job.title),
            user_span_text="software engineer",
            proposed_by=EvidenceSource.RULE,
        )
    ]
    stale.assessments = [
        MatchComponentAssessment(component=component, assessable=True, why="a stale reason")
        for component in MatchComponent
    ]
    db_session.add(stale)
    await db_session.flush()

    match = (await _detail(client, job))["match"]
    assert match is not None
    assert match["ruleset_version"] == load_weights().ruleset_version
    assert match["overall_score"] == real_score


async def test_another_person_s_score_is_not_served(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """The score is per (person, posting). A route filtering on `job_id` alone
    returns whichever row it happens to find first, and on a single-user
    development database that is indistinguishable from correct."""
    stranger = User(email=f"stranger-{uuid.uuid4().hex[:12]}@example.test")
    db_session.add(stranger)
    await db_session.flush()
    loaded = await matching._load_user(db_session, stranger.id)
    assert loaded is not None
    await _score(db_session, loaded, job)

    assert (await _detail(client, job))["match"] is None


# ---------------------------------------------------------------------------
# The two things beside the number
# ---------------------------------------------------------------------------


async def test_the_stored_eligibility_state_agrees_with_the_live_verdict(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """Two derivations of one verdict, shown to agree.

    §5.2 keeps `eligibility_status` on `match_results` because the ranked list's
    bands are built from it, while the job page also computes the full verdict on
    read for its blockers and unknowns. Two sources for one claim is a defect
    unless something checks them, and the page shows both at once.
    """
    await _score(db_session, user, job)
    detail = await _detail(client, job)

    live = evaluate(
        read_posting(
            [
                RequirementProposal(
                    kind=row.kind.value,
                    value=row.value,
                    raw_text=row.raw_text,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    necessity=row.necessity.value,
                    has_equivalence=row.has_equivalence,
                )
                for row in sorted(job.requirements, key=lambda r: (r.char_start, r.char_end))
            ]
        ),
        profile_from_user(user),
    )
    assert detail["eligibility"]["state"] == live.state.value
    assert detail["match"]["eligibility_status"] == live.state.value


async def test_the_two_deferred_components_are_named_rather_than_scored(
    client: AsyncClient, db_session: AsyncSession, user: User, job: Job
) -> None:
    """§5.1: *"deferred, and named on the page"*.

    Ten points of PRODUCT-SPEC §8.2 that this score does not contain. Omitted
    they are an invisible gap; named with a reason they are a decision a reader
    can check against the total.
    """
    await _score(db_session, user, job)

    deferred = (await _detail(client, job))["match"]["deferred_components"]
    assert {row["name"] for row in deferred} == {row.name for row in DEFERRED_COMPONENTS}
    for row in deferred:
        assert row["weight"] > 0
        assert row["blocked_on"].strip()
        assert row["reason"].strip()
