"""M5's most important test: two people, one database, no leaks.

M5's acceptance criterion is *"two users cannot see each other's data, proved
by a test shown able to fail."* This is that test, and its shape is the whole
argument.

**Why it enumerates rather than lists cases.** A test that checks "user A
cannot read user B's application" proves one route. It proves nothing about the
other forty-one, and nothing at all about the route somebody adds in M5c. So
this module reads the application's own route table out of its OpenAPI schema
and requires **every** route to be accounted for. A route with no entry in
:data:`CASES` fails :func:`test_every_route_is_classified` — adding an endpoint
without deciding what isolation means for it turns CI red rather than passing
quietly.

**Two independent guards, tested separately.**

1. :func:`test_every_protected_route_refuses_an_anonymous_request` — the
   default-deny wiring in `main.py`. Tested behaviourally, by making the
   request and reading the status, not by inspecting which dependency is
   attached to which router.
2. :func:`test_no_route_leaks_the_other_persons_data` — the filters themselves.
   Every route is called **as A, with B's identifiers**, and B's UUIDs must not
   appear anywhere in the response body.

**The universal assertion is a substring scan of the whole response.** Not a
field-by-field check, because a field-by-field check only inspects the fields
somebody thought of. If any UUID belonging to B appears anywhere in what A is
handed — top level, nested, inside an evidence blob, in an error message — that
is a leak, and the scan finds it without knowing the shape of the response.

**This module must not use ``dependency_overrides`` for the identity
dependency, and does not.** It signs in over HTTP the way a person would.
Overriding `current_user_id` here would test the route filters against a stub
of the very thing the milestone built, which is CLAUDE.md §8's "writing tests
that mock the thing under test" wearing a security hat.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.main import create_app
from nightshift.db.base import (
    ApplicationStage,
    CaptureStatus,
    JobStatus,
    ProficiencyLevel,
    ResumeSourceKind,
    ResumeVariant,
    SkillSourceType,
)
from nightshift.db.models import (
    Application,
    CapturedPosting,
    Company,
    Job,
    Resume,
    User,
    UserProject,
    UserSkill,
)
from nightshift.db.session import get_db_session
from nightshift.domain.identity import set_password
from tests.conftest import requires_db

#: `asyncio` is applied per test rather than to the module, because two of the
#: assertions below are synchronous — they read the route table, not the
#: database — and a module-wide async mark makes pytest warn about each.
pytestmark = [requires_db]
_async = pytest.mark.asyncio(loop_scope="session")

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
PASSWORD = "a-password-long-enough"


# ---------------------------------------------------------------------------
# The classification. Every route in the application appears exactly once.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """What isolation means for one route.

    ``kind`` decides the extra assertion beyond the universal leak scan:

    ``open``
        Answers an anonymous request on purpose. Only `/health` and `/auth`.
    ``owned``
        The path names a record. Asked for B's, A must get **404** — not 403,
        because "you may not have this" confirms the record exists, and its
        existence is itself B's business.
    ``listing``
        A collection scoped to the caller. A's copy must not contain B's rows,
        which the leak scan already checks; there is no status to assert beyond
        200.
    ``global``
        Serves the shared corpus rather than anybody's records, so there is
        nothing to isolate. **The ``reason`` is required** — a route lands here
        because somebody argued it should, not because it was easier.
    ``writes``
        Creates or changes a record. The row it produces must be attributed to
        A; asserted by reading A's own listing afterwards.
    """

    kind: Literal["open", "owned", "listing", "global", "writes"]
    reason: str = ""
    #: Request body for a write, if the route needs one to get past validation.
    payload: dict[str, Any] | None = None
    #: Status codes tolerated beyond the kind's default. Used where a route
    #: legitimately rejects the *shape* of a probe before it ever reaches a
    #: filter — a 422 is not a leak.
    also_allow: tuple[int, ...] = ()


_CORPUS = "serves the shared corpus, which is global exactly as `jobs` is — nothing to scope"

CASES: dict[tuple[str, str], Case] = {
    # -- open ---------------------------------------------------------------
    ("GET", "/health"): Case("open", "must answer while the database is down"),
    ("GET", "/health/live"): Case("open", "liveness, by definition unauthenticated"),
    ("POST", "/auth/sign-in"): Case("open", "how a request stops being anonymous"),
    ("POST", "/auth/token"): Case("open", "the same, for a client with no cookie jar"),
    ("POST", "/auth/sign-out"): Case("open", "idempotent; a 401 would trap a stale cookie"),
    ("GET", "/auth/me"): Case("listing", "the caller's own identity and nobody else's"),
    # -- the shared corpus --------------------------------------------------
    ("GET", "/jobs"): Case("global", _CORPUS),
    ("GET", "/jobs/admin"): Case("global", _CORPUS),
    ("GET", "/jobs/{job_id}"): Case("global", _CORPUS + "; the leak scan covers its saved state"),
    ("GET", "/jobs/{job_id}/history"): Case("global", _CORPUS),
    ("GET", "/companies"): Case("global", _CORPUS),
    ("GET", "/companies/{company_id}"): Case("global", _CORPUS),
    ("GET", "/city/signals"): Case("global", _CORPUS),
    ("GET", "/coverage"): Case("global", "counts the corpus; names no person"),
    ("GET", "/sources"): Case("global", "ingestion machinery, not anybody's records"),
    ("GET", "/boards"): Case("global", "ingestion machinery, not anybody's records"),
    ("GET", "/registry"): Case("global", "ingestion machinery, not anybody's records"),
    ("GET", "/ingestion-runs"): Case("global", "ingestion machinery, not anybody's records"),
    ("GET", "/stats"): Case("global", "corpus counts; names no person"),
    # -- listings scoped to the caller --------------------------------------
    ("GET", "/applications"): Case("listing"),
    ("GET", "/capture"): Case("listing"),
    ("GET", "/resumes"): Case("listing"),
    ("GET", "/profile"): Case("listing"),
    ("GET", "/queue"): Case("listing"),
    ("GET", "/matches"): Case("listing"),
    # -- records named in the path ------------------------------------------
    ("GET", "/applications/{application_id}"): Case("owned"),
    ("PATCH", "/applications/{application_id}"): Case("owned", payload={"priority": "high"}),
    ("PATCH", "/applications/{application_id}/stage"): Case(
        "owned", payload={"to_stage": "applied"}
    ),
    ("POST", "/applications/{application_id}/archive"): Case("owned"),
    ("POST", "/applications/{application_id}/restore"): Case("owned"),
    ("POST", "/applications/{application_id}/notes"): Case("owned", payload={"body": "probe"}),
    ("POST", "/applications/{application_id}/interviews"): Case(
        "owned", payload={"scheduled_for": "2026-08-20T12:00:00Z", "body": "probe"}
    ),
    ("GET", "/capture/{capture_id}"): Case("owned"),
    ("POST", "/capture/{capture_id}/confirm"): Case(
        "owned", payload={"title": "Probe", "company_name": "Probe Inc."}
    ),
    ("POST", "/capture/{capture_id}/discard"): Case("owned"),
    ("GET", "/resumes/{resume_id}"): Case("owned"),
    ("PATCH", "/resumes/{resume_id}"): Case("owned", payload={"label": "probe"}),
    ("DELETE", "/resumes/{resume_id}"): Case("owned"),
    ("POST", "/resumes/{resume_id}/confirm"): Case(
        "owned", payload={"decisions": [{"extraction_id": str(uuid.uuid4()), "decision": "reject"}]}
    ),
    ("DELETE", "/profile/skills/{skill_id}"): Case("owned"),
    ("DELETE", "/profile/projects/{project_id}"): Case("owned"),
    # -- writes -------------------------------------------------------------
    ("POST", "/applications"): Case("writes", payload={"job_id": None}),
    ("POST", "/capture"): Case("writes", payload={"raw_text": "Probe Engineer\nProbe Inc."}),
    ("PATCH", "/profile"): Case("writes", payload={"display_name": "A"}),
    ("POST", "/profile/skills"): Case(
        "writes", payload={"name": "probe-skill", "proficiency_level": "intermediate"}
    ),
    ("POST", "/profile/projects"): Case("writes", payload={"name": "probe-project"}),
    ("POST", "/resumes/paste"): Case(
        "writes", payload={"text": "Probe Person\nEngineer\n", "name": "probe"}
    ),
    # A multipart upload cannot be probed with a JSON body, and the isolation
    # question it would answer — "is the row attributed to the caller?" — is
    # the same one `/resumes/paste` answers through the same domain function.
    ("POST", "/resumes/upload"): Case(
        "global", "multipart; attribution shares `/resumes/paste`'s code path"
    ),
}


# ---------------------------------------------------------------------------
# Two people, and everything one of them owns.
# ---------------------------------------------------------------------------


@dataclass
class Person:
    user: User
    email: str
    #: Every UUID this person owns. The leak scan looks for these strings.
    owned_ids: list[uuid.UUID]
    #: Filled in for B, so a path can be built naming one of their records.
    path_values: dict[str, uuid.UUID]


async def _populate(session: AsyncSession, label: str, job: Job) -> Person:
    """Create one person and one row in every user-owned table."""
    user = User(email=f"{label}-{uuid.uuid4()}@example.test", display_name=f"Person {label}")
    session.add(user)
    await session.flush()
    await set_password(session, user.id, PASSWORD)

    application = Application(
        user_id=user.id,
        job_id=job.id,
        current_stage=ApplicationStage.SAVED,
    )
    capture = CapturedPosting(
        user_id=user.id,
        raw_text=f"{label} pasted this posting",
        status=CaptureStatus.PENDING,
        parser_version="test",
    )
    resume = Resume(
        user_id=user.id,
        name=f"{label} resume",
        variant_type=ResumeVariant.GENERAL_SWE,
        source_kind=ResumeSourceKind.PASTE,
        parsed_text=f"{label} resume text",
        content_hash=uuid.uuid4().hex,
    )
    skill = UserSkill(
        user_id=user.id,
        name=f"{label}-skill",
        normalized_name=f"{label}-skill",
        proficiency_level=ProficiencyLevel.INTERMEDIATE,
        source_type=SkillSourceType.MANUAL,
    )
    project = UserProject(user_id=user.id, name=f"{label}-project")
    session.add_all([application, capture, resume, skill, project])
    await session.flush()

    return Person(
        user=user,
        email=user.email,
        owned_ids=[
            user.id,
            application.id,
            capture.id,
            resume.id,
            skill.id,
            project.id,
        ],
        path_values={
            "application_id": application.id,
            "capture_id": capture.id,
            "resume_id": resume.id,
            "skill_id": skill.id,
            "project_id": project.id,
        },
    )


@pytest_asyncio.fixture(loop_scope="session")
async def shared_job(db_session: AsyncSession) -> Job:
    """One job both people saved. Global data, and a control for the scan.

    Both applications point at it, so a route that echoes a job id is not a
    leak and the scan must not treat it as one — which is exactly why the scan
    looks for *record* ids rather than for any id at all.
    """
    company = Company(canonical_name="Shared Inc.", normalized_name=str(uuid.uuid4()))
    db_session.add(company)
    await db_session.flush()
    job = Job(
        company_id=company.id,
        title="Software Engineer",
        normalized_title="software engineer",
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db_session.add(job)
    await db_session.flush()
    return job


@pytest_asyncio.fixture(loop_scope="session")
async def people(db_session: AsyncSession, shared_job: Job) -> tuple[Person, Person]:
    a = await _populate(db_session, "a", shared_job)
    b = await _populate(db_session, "b", shared_job)
    return a, b


@pytest_asyncio.fixture(loop_scope="session")
async def anonymous(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A client with no session. Only `get_db_session` is overridden.

    `current_user_id` is deliberately **not** overridden anywhere in this
    module — see the module docstring.
    """
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def _sign_in(client: AsyncClient, person: Person) -> AsyncClient:
    response = await client.post(
        "/auth/sign-in", json={"email": person.email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


@pytest_asyncio.fixture(loop_scope="session")
async def as_a(
    db_session: AsyncSession, people: tuple[Person, Person]
) -> AsyncIterator[AsyncClient]:
    """A client signed in as person A, through the real front door."""
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        await _sign_in(http, people[0])
        yield http
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# The tests.
# ---------------------------------------------------------------------------


def _routes() -> list[tuple[str, str]]:
    """Every (method, path) the application publishes, from its own schema."""
    spec = create_app().openapi()
    return sorted(
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
        if method in {"get", "post", "patch", "put", "delete"}
    )


def test_every_route_is_classified() -> None:
    """No route may exist without a decision about what isolation means for it.

    This is the assertion that makes the rest of the module durable. Without
    it, adding a route in M5c and forgetting to isolate it produces a green
    suite — the failure mode M2's review named and M5a's review named again: a
    green test sitting on top of a surface nobody checked.
    """
    published = set(_routes())
    classified = set(CASES)

    unclassified = published - classified
    assert not unclassified, (
        "these routes have no isolation case — add one to CASES, choosing a kind "
        f"deliberately rather than picking 'global' to make this pass: {sorted(unclassified)}"
    )

    stale = classified - published
    assert not stale, f"CASES names routes that no longer exist: {sorted(stale)}"


def test_the_only_uncovered_routes_are_fastapis_own_docs() -> None:
    """A stated limit, recorded in code rather than only in prose.

    `_routes()` reads the OpenAPI schema, and FastAPI's own `/docs`,
    `/redoc`, `/openapi.json` and the OAuth redirect are not *in* that schema —
    so the enumeration above cannot see them and does not cover them. They are
    open, and they describe the API's shape rather than anybody's data.

    That is tolerable while nothing is deployed and it is sloppy in public, so
    it belongs with M7's first deploy beside HTTPS and the `secure` cookie
    flag. This test exists so the set cannot grow quietly: a fifth open,
    unenumerated route added by an upgrade or by us fails here.
    """
    app = create_app()
    schema_paths = set(app.openapi()["paths"])
    unenumerated = {
        route.path
        for route in app.routes
        if getattr(route, "path", None) and route.path not in schema_paths
    }

    assert unenumerated == {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }, (
        "the set of routes outside the OpenAPI schema changed. Every route in it is "
        f"open and untested by this module: {sorted(unenumerated)}"
    )


def test_every_global_case_states_a_reason() -> None:
    """`global` is the kind that turns off the leak check, so it costs a sentence."""
    silent = [
        route for route, case in CASES.items() if case.kind == "global" and not case.reason.strip()
    ]
    assert not silent, f"a route is only 'global' if somebody argued it: {sorted(silent)}"


@_async
@pytest.mark.parametrize(
    ("method", "path"),
    [route for route, case in CASES.items() if case.kind != "open"],
)
async def test_every_protected_route_refuses_an_anonymous_request(
    anonymous: AsyncClient,
    people: tuple[Person, Person],
    method: str,
    path: str,
) -> None:
    """Default-deny, tested by asking rather than by reading `main.py`.

    Before M5b a route was protected because its handler happened to declare
    ``CurrentUserId``. This asserts the property directly: with no session, the
    answer is 401 and never data.
    """
    _, b = people
    case = CASES[(method, path)]
    url = _fill(path, b)

    response = await anonymous.request(method, url, json=case.payload)

    assert response.status_code == 401, (
        f"{method} {path} answered an anonymous request with "
        f"{response.status_code}: {response.text[:400]}"
    )


@_async
@pytest.mark.parametrize(
    ("method", "path"),
    [route for route, case in CASES.items() if case.kind == "open"],
)
async def test_every_open_route_actually_answers_anonymously(
    anonymous: AsyncClient,
    people: tuple[Person, Person],
    method: str,
    path: str,
) -> None:
    """The other half of default-deny, and it is not symmetric with the first.

    Only routes classified `open` are exempted from the 401 assertion. Without
    this, a route marked `open` by mistake — one that in fact requires a
    session — passes every test in the module while being unreachable to the
    person who needs it, and `/auth/sign-in` is the route where that failure is
    a locked front door.

    A 401 is the failure. Any other status, including a validation error for a
    deliberately empty probe body, means the route was reached.
    """
    _, b = people
    case = CASES[(method, path)]
    url = _fill(path, b)

    response = await anonymous.request(method, url, json=case.payload)

    assert response.status_code != 401, (
        f"{method} {path} is classified `open` — {case.reason} — but it refused an "
        f"anonymous request. Either the classification is wrong or the route is."
    )


@_async
@pytest.mark.parametrize(
    ("method", "path"),
    [route for route, case in CASES.items() if case.kind in {"owned", "listing", "global"}],
)
async def test_no_route_leaks_the_other_persons_data(
    as_a: AsyncClient,
    people: tuple[Person, Person],
    method: str,
    path: str,
) -> None:
    """Signed in as A, ask for B's things. Nothing of B's may come back."""
    _, b = people
    case = CASES[(method, path)]
    url = _fill(path, b)

    response = await as_a.request(method, url, json=case.payload)
    _assert_no_leak(response, b, method, path)

    if case.kind == "owned":
        allowed = (404, *case.also_allow)
        assert response.status_code in allowed, (
            f"{method} {path} answered {response.status_code} for a record belonging to "
            f"somebody else. 404 is the correct answer: 200 is a leak, and 403 confirms "
            f"the record exists, which is itself B's business. Body: {response.text[:400]}"
        )


@_async
@pytest.mark.parametrize(
    ("method", "path"),
    [route for route, case in CASES.items() if case.kind == "writes"],
)
async def test_a_write_is_attributed_to_the_caller(
    as_a: AsyncClient,
    people: tuple[Person, Person],
    shared_job: Job,
    method: str,
    path: str,
) -> None:
    """A write by A creates A's row, and A's response never names B."""
    _, b = people
    case = CASES[(method, path)]
    payload = dict(case.payload or {})
    if payload.get("job_id", "sentinel") is None:
        payload["job_id"] = str(shared_job.id)

    response = await as_a.request(method, path, json=payload)

    assert response.status_code < 400, (
        f"{method} {path} rejected a well-formed write from a signed-in caller: "
        f"{response.status_code} {response.text[:400]}"
    )
    _assert_no_leak(response, b, method, path)


def _fill(path: str, person: Person) -> str:
    """Substitute this person's own record ids into a path template."""
    filled = path
    for name, value in person.path_values.items():
        filled = filled.replace("{" + name + "}", str(value))
    # Any placeholder left is a global id (`job_id`, `company_id`) that no
    # person owns. A random UUID is the right probe: the route must behave the
    # same whether or not the row exists, and a 404 for a nonexistent job is
    # not an isolation failure.
    while "{" in filled:
        head, _, rest = filled.partition("{")
        _, _, tail = rest.partition("}")
        filled = f"{head}{uuid.uuid4()}{tail}"
    return filled


def _assert_no_leak(response: Response, other: Person, method: str, path: str) -> None:
    """The universal assertion: none of ``other``'s UUIDs appear in the body.

    A substring scan and not a field check, because a field check only inspects
    the fields somebody thought of. This finds a leaked id nested inside an
    evidence blob or spelled into an error message just as readily as one at the
    top level.
    """
    body = response.text
    leaked = [str(owned) for owned in other.owned_ids if str(owned) in body]
    assert not leaked, (
        f"{method} {path} returned {response.status_code} and its body contains "
        f"identifiers belonging to the other person: {leaked}. Body: {body[:600]}"
    )
