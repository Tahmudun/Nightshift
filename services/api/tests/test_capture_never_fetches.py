"""The one rule that makes M5d legal: we do not load the page.

``board-discovery.md`` §9 answered LinkedIn and Indeed with *no* — a blanket
``Disallow: /`` and a partner-only API respectively — and ``CLAUDE.md`` §8
forbids scraping anything that asks not to be scraped. M5d does not reopen
that. It reaches those postings the only way that is honest: **the reader is
already looking at the page, and the reader's own Claude reads it for them.**
Nightshift receives text and a URL, stores both, and dereferences neither.

``captured_postings.source_url`` has carried the comment *"Never fetched — see
the class note"* since M5a. This module is that comment with teeth, and it is
here rather than later because M5d is the milestone where a reader starts
handing this server job-board URLs by the dozen.

Two guards, because neither covers the other and both have stated limits.

**The transport guard** replaces httpx's real transports with one that raises,
then drives paste → read → confirm and asserts all three succeed. It does not
block a raw socket or a subprocess. It does not need to: ``CLAUDE.md`` §7 says
nothing outside ``adapters/`` imports httpx directly, so httpx is the shape an
accidental fetch would actually take.

**The source guard** reads the capture modules' syntax trees and asserts no
string literal outside a docstring names a job board. That is the half a
transport patch cannot see — a URL assembled at import time, a constant waiting
for someone to use it — and it is also what a raw-socket fetch would need.

Both were shown able to fail before this file was committed; the sabotage that
turns each one red is written above it.
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import nightshift
from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.models import User
from nightshift.db.session import get_db_session
from tests.conftest import requires_db

# Marks are applied per-test rather than at module level: two of the four
# tests here read syntax trees and need neither a database nor an event loop,
# and a module-level asyncio mark on a sync test is a warning pytest is right
# to raise.

#: A real LinkedIn job URL's shape. Never requested, by the whole point of
#: this module — it is here to be *stored* and to be the thing the transport
#: guard would catch if anything went and got it.
LINKEDIN_URL = "https://www.linkedin.com/jobs/view/4012345678/"

INDEED_URL = "https://www.indeed.com/viewjob?jk=abc123def456"

PASTE = """Staff Backend Engineer
Ramp · New York, NY (Hybrid)

About the job
Build payment infrastructure. Python and Postgres.
"""

#: Every module the capture request path can reach that we own. Not the whole
#: package: this is the path a ``POST /capture`` actually executes, and a guard
#: that scanned everything would be asserting about the Greenhouse adapter,
#: which fetches boards on purpose.
CAPTURE_PATH_MODULES = (
    "api/routes/capture.py",
    "domain/capture.py",
)

#: Hosts that answered "do not crawl us" and were believed.
BOARD_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com")


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Capture Reader")
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


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every real httpx request raise, and report what tried.

    Patches the *transports* rather than ``AsyncClient.send`` on purpose: the
    test client in this module is itself an ``httpx.AsyncClient``, over an
    ``ASGITransport`` that never reaches either of these. Patching ``send``
    would break the test's own plumbing and the guard would be asserting about
    itself.
    """
    attempted: list[str] = []

    async def refuse_async(self: object, request: httpx.Request, **kwargs: object) -> object:
        attempted.append(str(request.url))
        raise AssertionError(f"the capture path reached the network: {request.url}")

    def refuse_sync(self: object, request: httpx.Request, **kwargs: object) -> object:
        attempted.append(str(request.url))
        raise AssertionError(f"the capture path reached the network: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse_sync)
    return attempted


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_the_capture_path_never_dereferences_a_source_url(
    client: AsyncClient, no_network: list[str]
) -> None:
    """Paste, read and confirm a LinkedIn posting with the network unplugged.

    **Sabotage that turns this red** — in ``domain/capture.py``'s
    ``create_capture``::

        async with httpx.AsyncClient() as http:
            await http.get(source_url)

    fails with ``AssertionError: the capture path reached the network:
    https://www.linkedin.com/jobs/view/4012345678/``.

    Confirmation is included rather than stopping at the paste because it is
    the step that runs the whole ingestion pipeline — normalization, locations,
    embedding, requirements, dedupe — on a row whose ``canonical_url`` is a
    LinkedIn link. That is the plausible place for a fetch to appear later,
    and it is not covered by testing ``POST /capture`` alone.
    """
    created = await client.post("/capture", json={"raw_text": PASTE, "source_url": LINKEDIN_URL})
    assert created.status_code == 201, created.text
    capture_id = created.json()["id"]
    assert created.json()["source_url"] == LINKEDIN_URL

    read = await client.get(f"/capture/{capture_id}")
    assert read.status_code == 200, read.text

    confirmed = await client.post(
        f"/capture/{capture_id}/confirm",
        json={
            "title": "Staff Backend Engineer",
            "company_name": "Ramp",
            "location_text": "New York, NY",
            "employment_type": "full_time",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"

    assert attempted_nothing(no_network)


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_an_indeed_url_is_stored_and_left_alone(
    client: AsyncClient, no_network: list[str]
) -> None:
    """The same guard for the other host, because §9 named two of them."""
    created = await client.post("/capture", json={"raw_text": PASTE, "source_url": INDEED_URL})
    assert created.status_code == 201, created.text
    assert created.json()["source_url"] == INDEED_URL
    assert attempted_nothing(no_network)


def attempted_nothing(attempted: list[str]) -> bool:
    """Readable in the assertion and precise in the failure."""
    assert attempted == [], f"the capture path requested {attempted}"
    return True


def _package_root() -> Path:
    return Path(nightshift.__file__).resolve().parent


def _literal_strings(tree: ast.AST) -> list[str]:
    """Every string constant except the ones that are documentation.

    Comments never reach the AST at all, so they need no exclusion. Docstrings
    do, and this module's own docstring names both hosts — a guard that could
    not tell prose from a URL would forbid explaining itself.
    """
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node not in docstrings
    ]


def _is_fetchable(value: str) -> bool:
    """Is this literal a job-board **address**, as opposed to a job-board name?

    The distinction was forced by this guard firing on real code, and it is a
    better rule for having been.

    The first version flagged any literal containing a board host. Then M5d
    added ``capture_origin``, which has to *recognise* one — a table of
    registrable domains, used to label a capture "From LinkedIn" — and the
    guard went red on it. Recognising a host is the opposite of fetching one,
    so a guard that cannot tell them apart forbids the honest use along with
    the dangerous one, and the pressure is then to weaken the guard rather
    than to fix the code.

    So the rule is now about **shape**: a bare registrable domain is a name,
    and anything carrying a scheme, an authority prefix or a path is an
    address. ``"linkedin.com"`` passes; ``"https://www.linkedin.com"``,
    ``"//www.linkedin.com/jobs"`` and ``"www.linkedin.com/jobs/view/1"`` do
    not.

    **The narrowing is real and is not free.** ``BASE = "linkedin.com"``
    followed by ``httpx.get("https://" + BASE)`` now slips past this guard.
    That is the transport guard's half of the job, and it catches it at
    runtime — which is the whole reason there are two of them with their
    limits written down rather than one that claims to cover everything.
    """
    lowered = value.lower()
    for host in BOARD_HOSTS:
        index = lowered.find(host)
        while index != -1:
            before = lowered[:index]
            after = lowered[index + len(host) :]
            if before.endswith(("//", "://", "@")) or after.startswith(("/", ":")):
                return True
            index = lowered.find(host, index + 1)
    return "://" in lowered and any(host in lowered for host in BOARD_HOSTS)


@pytest.mark.parametrize("relative", CAPTURE_PATH_MODULES)
def test_no_capture_module_names_a_job_board_as_a_target(relative: str) -> None:
    """No string literal in the capture path is a job-board **address**.

    **Sabotage that turns this red** — add to ``domain/capture.py``::

        BOARD_BASE = "https://www.linkedin.com"

    fails with ``domain/capture.py holds a job-board address in a string
    literal: ['https://www.linkedin.com']``.

    This is the half the transport guard cannot see. A fetch that has not been
    written yet leaves no request to intercept, but it leaves the URL sitting
    in a constant, and that is the moment to catch it rather than after
    somebody wires it up.
    """
    path = _package_root() / relative
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = [value for value in _literal_strings(tree) if _is_fetchable(value)]
    assert offenders == [], f"{relative} holds a job-board address in a string literal: {offenders}"


@pytest.mark.parametrize(
    ("literal", "fetchable"),
    [
        ("https://www.linkedin.com", True),
        ("https://www.linkedin.com/jobs/view/1", True),
        ("//www.linkedin.com/jobs", True),
        ("www.linkedin.com/jobs/view/1", True),
        ("linkedin.com:443", True),
        ("https://api.indeed.com/ads/apisearch", True),
        # The honest uses, which the first version of this guard forbade.
        ("linkedin.com", False),
        ("indeed.com", False),
        ("From LinkedIn", False),
        ("https://boards.greenhouse.io/ramp/jobs/1", False),
    ],
)
def test_the_guard_can_tell_a_board_address_from_a_board_name(
    literal: str, fetchable: bool
) -> None:
    """The rule itself, tested apart from the modules it is applied to.

    Written because narrowing a guard is the moment it most easily stops
    guarding anything, and "it still passes on the current code" is not
    evidence either way — the current code is what made it narrow.
    """
    assert _is_fetchable(literal) is fetchable
