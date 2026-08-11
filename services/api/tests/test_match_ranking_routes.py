"""The ranked list: bands that are headings, and an order that is the fraction.

M3c Task 10, `matching.md` §5.3 and §5.1.1. Three claims, and each one has an
implementation that looks right and fails it:

* **The order is the fraction, never the total.** `assessed_out_of` is not always
  100, so `ORDER BY overall_score DESC` is the obvious clause and it puts a 45/100
  above a 40/50. Nothing on the page looks wrong when it does — both numbers are
  real, and only their comparison is a lie.
* **The band is a heading and never points.** §5.2 forbids an eligibility state
  from reaching the arithmetic, so a list that sorts `ineligible` down by
  subtracting from its score satisfies every ordering assertion below while
  breaking the one invariant this milestone is about.
* **What could not be ranked is counted, not dropped.** A ranked list covering 12
  of 31 open postings renders identically to one covering all 31.

Rows are built by hand rather than scored, because the point is the ordering and
a real scorer cannot be asked for a 40/50 and a 45/100 on demand.
`test_match_routes.py` is where the serialisation of a genuinely computed score is
checked.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.base import (
    EligibilityState,
    EvidenceSource,
    JobStatus,
    JobTextField,
    MatchComponent,
    PenaltyName,
)
from nightshift.db.models import (
    Job,
    MatchComponentAssessment,
    MatchEvidence,
    MatchPenalty,
    MatchResult,
    User,
)
from nightshift.db.session import get_db_session
from nightshift.domain.matching import BAND_ORDER
from nightshift.domain.matching_weights import load_weights
from nightshift.domain.scoring import coverage_weighted_fraction, score_fraction
from tests.conftest import make_job_with_text, requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

DESCRIPTION = "We need strong Python and PostgreSQL for a team in New York."

#: Which components are left unassessable to reach a given denominator, and the
#: points that then fit under it. Written out rather than computed so the
#: arithmetic a test depends on is visible in the test — the weights are 20, 30,
#: 20, 10, 10, 10, and `0018`'s trigger ties the denominator to exactly this.
_UNASSESSABLE_FOR = {
    100: (),
    # Added at M3d Task 6, and both are real denominators from the rated corpus
    # rather than convenient ones: 80 and 20 are what a posting naming no
    # projects and a posting naming almost nothing actually produce.
    80: (MatchComponent.PROJECT,),
    50: (MatchComponent.SKILL, MatchComponent.PROJECT),
    20: (
        MatchComponent.SKILL,
        MatchComponent.PROJECT,
        MatchComponent.LOCATION,
        MatchComponent.FRESHNESS,
        MatchComponent.PRIORITY,
    ),
    0: tuple(MatchComponent),
}


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"ranking-{uuid.uuid4().hex[:12]}@example.test")
    db_session.add(row)
    await db_session.flush()
    return row


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


async def _job(db_session: AsyncSession) -> Job:
    return await make_job_with_text(db_session, DESCRIPTION)


def _quoted(result: MatchResult, component: MatchComponent, points: int) -> MatchEvidence:
    """A person-claim evidence row that quotes the posting at real offsets.

    The quoting trigger reads the field and checks the characters, so the span has
    to be true of the text rather than plausible — which is the point of the
    trigger and the reason this helper exists instead of a literal.
    """
    start = DESCRIPTION.index("Python")
    return MatchEvidence(
        match_result_id=result.id,
        component=component,
        points=points,
        job_span_text="Python",
        job_span_field=JobTextField.DESCRIPTION_TEXT,
        job_char_start=start,
        job_char_end=start + len("Python"),
        user_span_text="Python",
        proposed_by=EvidenceSource.RULE,
    )


async def _store(
    db_session: AsyncSession,
    *,
    user: User,
    job: Job,
    overall: int,
    out_of: int,
    state: EligibilityState,
    ruleset: str | None = None,
) -> MatchResult:
    """One stored score with the total and denominator this test needs.

    Points go to `role` and `skill` because those are the two the evidence guard
    has something to check; the split is arbitrary and the fraction is not.
    """
    unassessable = _UNASSESSABLE_FOR[out_of]
    role = min(overall, 20)
    skill = overall - role
    result = MatchResult(
        user_id=user.id,
        job_id=job.id,
        overall_score=overall,
        assessed_out_of=out_of,
        eligibility_status=state,
        role_score=role,
        skill_score=skill,
        project_evidence_score=0,
        location_score=0,
        freshness_score=0,
        priority_score=0,
        penalty_score=0,
        ruleset_version=ruleset or load_weights().ruleset_version,
    )
    result.assessments = [
        MatchComponentAssessment(
            component=component,
            assessable=component not in unassessable,
            why="a reason this test does not depend on",
        )
        for component in MatchComponent
    ]
    result.penalties = [
        MatchPenalty(
            name=name,
            points=0,
            applicable=False,
            why="a reason this test does not depend on",
        )
        for name in PenaltyName
    ]
    db_session.add(result)
    await db_session.flush()
    for component, points in ((MatchComponent.ROLE, role), (MatchComponent.SKILL, skill)):
        if points:
            db_session.add(_quoted(result, component, points))
    await db_session.flush()
    return result


async def _ranking(client: AsyncClient) -> dict[str, Any]:
    response = await client.get("/matches")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _band(body: dict[str, Any], state: EligibilityState) -> dict[str, Any]:
    return next(row for row in body["bands"] if row["state"] == state.value)


# ---------------------------------------------------------------------------
# The bands
# ---------------------------------------------------------------------------


async def test_all_five_bands_are_present_even_when_empty(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """§3.3's promise — an ineligible posting is shown and dimmed, never hidden —
    is only checkable if the heading is there to be empty."""
    await _store(
        db_session,
        user=user,
        job=await _job(db_session),
        overall=40,
        out_of=50,
        state=EligibilityState.ELIGIBLE,
    )

    body = await _ranking(client)
    assert [row["state"] for row in body["bands"]] == [state.value for state in BAND_ORDER]
    assert _band(body, EligibilityState.INELIGIBLE)["items"] == []


async def test_an_ineligible_posting_is_banded_below_and_keeps_its_score(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """§5.2: the state sits beside the number and is never inside it.

    The ineligible posting here scores higher than the eligible one, so a list
    that had folded the verdict into the arithmetic would show it with a reduced
    total — or above, if it had not folded it in anywhere. Both facts are asserted
    because only the pair distinguishes a band from a penalty.
    """
    strong = await _job(db_session)
    weak = await _job(db_session)
    await _store(
        db_session,
        user=user,
        job=strong,
        overall=45,
        out_of=50,
        state=EligibilityState.INELIGIBLE,
    )
    await _store(
        db_session, user=user, job=weak, overall=10, out_of=100, state=EligibilityState.ELIGIBLE
    )

    body = await _ranking(client)
    blocked = _band(body, EligibilityState.INELIGIBLE)["items"]
    assert [row["job"]["id"] for row in blocked] == [str(strong.id)]
    assert blocked[0]["match"]["overall_score"] == 45
    assert blocked[0]["match"]["fraction"] == pytest.approx(0.9)
    assert [row["job"]["id"] for row in _band(body, EligibilityState.ELIGIBLE)["items"]] == [
        str(weak.id)
    ]


# ---------------------------------------------------------------------------
# The order inside a band
# ---------------------------------------------------------------------------


async def test_the_order_is_the_fraction_and_not_the_total(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """The headline claim, and the one `ORDER BY overall_score DESC` gets wrong.

    40 out of 50 is a better match than 45 out of 100, and a list sorted on the
    stored totals puts them the other way round while both numbers on the page
    stay true.
    """
    terse = await _job(db_session)
    verbose = await _job(db_session)
    await _store(
        db_session, user=user, job=terse, overall=40, out_of=50, state=EligibilityState.ELIGIBLE
    )
    await _store(
        db_session,
        user=user,
        job=verbose,
        overall=45,
        out_of=100,
        state=EligibilityState.ELIGIBLE,
    )

    items = _band(await _ranking(client), EligibilityState.ELIGIBLE)["items"]
    assert [row["job"]["id"] for row in items] == [str(terse.id), str(verbose.id)]
    assert items[0]["match"]["overall_score"] < items[1]["match"]["overall_score"]


async def test_a_pair_nothing_could_be_assessed_on_sorts_last_in_its_band(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """A null fraction is neither best nor worst, and Postgres' default for
    `DESC` is `NULLS FIRST` — so without the explicit clause the pair nobody
    could score leads the list.

    It keeps its band: the eligibility verdict on it is real. What it has nothing
    to say about is the ordering, and it is counted so the page can mark it rather
    than print it as the worst match found.
    """
    scored = await _job(db_session)
    unscorable = await _job(db_session)
    await _store(
        db_session, user=user, job=unscorable, overall=0, out_of=0, state=EligibilityState.UNCERTAIN
    )
    await _store(
        db_session, user=user, job=scored, overall=5, out_of=100, state=EligibilityState.UNCERTAIN
    )

    band = _band(await _ranking(client), EligibilityState.UNCERTAIN)
    assert [row["job"]["id"] for row in band["items"]] == [str(scored.id), str(unscorable.id)]
    assert band["items"][1]["match"]["fraction"] is None
    assert band["unassessed"] == 1
    assert (await _ranking(client))["unassessed_sort_last"] is True


# ---------------------------------------------------------------------------
# What is not in the list
# ---------------------------------------------------------------------------


async def test_an_unscored_posting_is_counted_rather_than_ranked(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """A ranked list covering 12 of 31 postings renders identically to one
    covering all 31. The count is the only thing that says which it is."""
    scored = await _job(db_session)
    await _job(db_session)
    await _job(db_session)
    await _store(
        db_session, user=user, job=scored, overall=40, out_of=50, state=EligibilityState.ELIGIBLE
    )

    body = await _ranking(client)
    assert body["total"] == 1
    assert body["not_yet_scored"] == 2


async def test_a_score_at_an_older_ruleset_version_is_not_ranked(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """§4.2: a number produced by arithmetic that no longer exists is not a worse
    score, it is not a score.

    It reaches the list as `not_yet_scored`, which is what the sweep will do about
    it, rather than being silently absent from both the rows and the counts.
    """
    job = await _job(db_session)
    await _store(
        db_session,
        user=user,
        job=job,
        overall=40,
        out_of=50,
        state=EligibilityState.ELIGIBLE,
        ruleset="0+ancient",
    )

    body = await _ranking(client)
    assert body["total"] == 0
    assert body["not_yet_scored"] == 1
    assert body["ruleset_version"] == load_weights().ruleset_version


async def test_a_closed_posting_is_neither_ranked_nor_counted(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """`pending_pairs`' rule, applied to the read side.

    A closed posting in `not_yet_scored` would be a permanent backlog the sweep
    never clears, because the sweep does not score closed jobs either — a number
    that only ever goes up and means nothing.
    """
    closed = await _job(db_session)
    closed.status = JobStatus.CLOSED
    # `ck_jobs_closed_at_matches_status` refuses a closed job with no closure
    # timestamp, which is M1's closure machine keeping the two facts together.
    closed.closed_at = datetime.now(tz=UTC)
    await db_session.flush()

    body = await _ranking(client)
    assert body["total"] == 0
    assert body["not_yet_scored"] == 0


async def test_another_person_s_scores_are_not_ranked(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """`match_results` is keyed by person and this route takes the user from the
    request, so the failure mode is a query that forgets the predicate — which
    returns a full, plausible, entirely wrong list."""
    stranger = User(email=f"stranger-{uuid.uuid4().hex[:12]}@example.test")
    db_session.add(stranger)
    await db_session.flush()
    job = await _job(db_session)
    await _store(
        db_session,
        user=stranger,
        job=job,
        overall=40,
        out_of=50,
        state=EligibilityState.ELIGIBLE,
    )

    body = await _ranking(client)
    assert body["total"] == 0
    # And it is still an open posting nobody has scored *for this person*.
    assert body["not_yet_scored"] == 1


# ---------------------------------------------------------------------------
# What the list says about itself
# ---------------------------------------------------------------------------


async def test_every_ranked_row_carries_its_whole_breakdown(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """I4 applies to a row in a list exactly as it applies to a detail page.

    The cheap ranked list is a title and a number, and it is the one shape the
    invariant forbids outright.
    """
    await _store(
        db_session,
        user=user,
        job=await _job(db_session),
        overall=40,
        out_of=50,
        state=EligibilityState.ELIGIBLE,
    )

    row = _band(await _ranking(client), EligibilityState.ELIGIBLE)["items"][0]
    assert len(row["match"]["components"]) == len(MatchComponent)
    assert len(row["match"]["penalties"]) == len(PenaltyName)
    assert row["match"]["deferred_components"]


async def test_the_ten_deferred_points_are_named_on_the_list_too(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """§5.1's two deferrals, on the surface where one total is compared against
    another — which is the moment the points nobody scored matter most."""
    body = await _ranking(client)
    assert {row["name"] for row in body["deferred_components"]} == {
        "company_preference",
        "application_urgency",
    }


async def test_a_barely_assessed_posting_does_not_outrank_a_thoroughly_assessed_one(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """M3d Task 6, and review §2.10 measured rather than argued.

    6 out of 20 is 30% and 14 out of 80 is 17.5%, so the plain fraction puts the
    first one higher — on a posting where four fifths of the score could not be
    assessed at all. Both numbers are true and neither is comparable to the
    other, which is the whole of §2.10: a ratio of incomparable denominators is
    not a total order.

    These are the real figures from the rated corpus. Under the plain fraction an
    Employee Experience Specialist (Receptionist) rated `poor` ranked **fifth**,
    above four postings rated `good`; weighting by coverage moves it below them.

    The weight is `sqrt(assessed_out_of / 100)`, chosen by measurement and not by
    taste — see `matching.md` §5.3 for the leave-one-out figures and for why the
    exponent is not pinned harder than the data supports.
    """
    thorough = await _job(db_session)
    barely = await _job(db_session)
    await _store(
        db_session, user=user, job=thorough, overall=14, out_of=80, state=EligibilityState.ELIGIBLE
    )
    await _store(
        db_session, user=user, job=barely, overall=6, out_of=20, state=EligibilityState.ELIGIBLE
    )

    items = _band(await _ranking(client), EligibilityState.ELIGIBLE)["items"]

    assert [row["job"]["id"] for row in items] == [str(thorough.id), str(barely.id)]
    # The displayed fraction is unchanged and still reads "of what could be
    # assessed" — the ordering is weighted, the printed number is not. A reader
    # therefore sees 17% above 30%, which is why the response names its ordering.
    assert items[0]["match"]["fraction"] < items[1]["match"]["fraction"]


async def test_the_sql_ordering_is_the_documented_key(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """The SQL clause and `scoring.coverage_weighted_fraction` are one key.

    M3d Task 8's finding. The arithmetic in §5.3 had four implementations by the
    end of Task 6 — `coverage_weighted_rank`'s SQL, `verify.py`'s recomputation
    from the wire, `matching.spec.ts`, and the ranking-quality grader — and Task
    6 updated exactly one of them. Two of the other three went red and were
    repaired at Task 7. The fourth reported a number for an ordering this system
    had stopped serving, in the direction that flatters, and no test could see it
    because the two keys agree on most pairs.

    So this asserts what none of the four asserted: that the order Postgres
    returns is the order the Python definition gives, over rows chosen to make
    the plausible wrong keys visibly wrong.

    The four denominators are the ones `UNASSESSABLE_FOR` can build, and the
    totals are chosen so that the coverage-weighted order, the plain-fraction
    order and the raw-total order are three *different* permutations of the same
    four rows. The first draft of this test used rounder numbers on which the raw
    order happened to coincide with the right one, and its third assertion
    therefore passed while proving nothing — which is the failure this whole file
    of findings is about, committed once more on the way to writing it down.

    No total exceeds what `store_score` can place on components the denominator
    leaves assessable: it fills `role` to 20 and puts the rest on `skill`, so a
    50 has to stay at or under 20 and a 100 may go to 50.
    """
    stored = {}
    for name, overall, out_of in (("a", 45, 100), ("c", 31, 80), ("b", 20, 50), ("d", 18, 20)):
        job = await _job(db_session)
        await _store(
            db_session,
            user=user,
            job=job,
            overall=overall,
            out_of=out_of,
            state=EligibilityState.ELIGIBLE,
        )
        stored[name] = (job, overall, out_of)

    served = [
        row["job"]["id"]
        for row in _band(await _ranking(client), EligibilityState.ELIGIBLE)["items"]
    ]

    def order_by(key: Any) -> list[str]:
        return [
            str(job.id)
            for job, overall, out_of in sorted(
                stored.values(), key=lambda row: -(key(row[1], row[2]) or -1.0)
            )
        ]

    assert served == order_by(coverage_weighted_fraction)
    # Non-vacuity, and it is the whole reason these four rows have these numbers:
    # a corpus on which the wrong keys agree with the right one would make the
    # assertion above pass under the ordering this test exists to forbid.
    assert served != order_by(score_fraction)
    assert served != order_by(lambda overall, _out_of: float(overall))
