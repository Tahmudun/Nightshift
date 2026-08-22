"""The two rules that make the MCP server safe, as tests rather than comments.

Both are architectural, both are invisible at runtime until they are violated
badly, and both are the kind of rule a later milestone breaks by accident while
adding a feature. ADR 0038.

**Neither of these tests can run in-process**, and that is the point of the
subprocess machinery below rather than an inconvenience to work around:

* the import guard reads ``sys.modules``, and pytest has already imported most
  of this codebase before the first test runs — checked in-process it would
  pass unconditionally, which is worse than not having it;
* the stdout guard is about a real file descriptor, and the in-memory transport
  the protocol tests use does not touch one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]

# Long enough for a cold interpreter to import the package on a loaded machine,
# short enough that a hung server fails the suite rather than stalling CI.
STARTUP_TIMEOUT = 30


def _fresh_python(code: str, **popen: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT,
        **popen,  # type: ignore[arg-type]
    )


def test_the_mcp_package_never_reaches_the_database() -> None:
    """§1: the MCP server is a client of the API, not a second door into it.

    M5b made isolation **structural** — `require_session` is attached once in
    `main.py`, so a route is protected because it exists rather than because
    its handler remembered to declare a parameter. A second path into the
    domain, one that opens a session and filters by `user_id` because the
    author remembered to, would reintroduce exactly the hole M5b closed.

    So `nightshift.mcp` goes through HTTP like any other client, and this test
    is what makes that a rule rather than an intention.

    **`nightshift.db.base` is deliberately allowed.** It holds enums, a
    declarative base and no engine and no sessionmaker: `shapes.py` imports
    `LocationConfidence` both to key the confidence table and to *reject* a
    confidence value the domain does not know, which is how I1 becomes
    checkable here. The enums are a vocabulary; the engine and the tables are
    the door.

    **This test imported the wrong module until 2026-08-21**, and the version
    that did is worth recording. It imported `nightshift.mcp` — the package
    `__init__`, which imports nothing at all — so it observed an empty module
    graph and passed. It would have passed with `server.py` opening a session
    and querying `jobs` directly. Found by profiling the real server's startup
    while closing M5c's Claude Desktop deviation, not by review: the process
    Claude Desktop launches had `sqlalchemy` in it the whole time, and the
    guard against that said otherwise.

    It now imports `nightshift.mcp.__main__` — **the module that actually
    runs** — and the ban list changed to match what is true rather than what
    read well. `sqlalchemy` was on it, and could not have been: `db.base` is
    allowed and `db.base` imports `sqlalchemy` on its first line. A ban that
    the allowed import contradicts is not a rule, it is a sentence. What is
    checkable, and is what §1 actually protects, is that **no `nightshift.db`
    module other than `base` is reachable** — a session, a model, or a new
    module holding either, all fail this.
    """
    result = _fresh_python(
        "import sys, json;"
        " import nightshift.mcp.__main__;"
        " banned = {'nightshift.db.session', 'nightshift.db.models'};"
        " db = {m for m in sys.modules if m.startswith('nightshift.db')};"
        " print(json.dumps({'banned': sorted(banned & set(sys.modules)),"
        " 'db': sorted(db)}))"
    )

    assert result.returncode == 0, result.stderr
    reached = json.loads(result.stdout)

    assert reached["banned"] == [], (
        f"nightshift.mcp imported {reached['banned']}. It must reach Nightshift "
        "over HTTP, not through the database — see ADR 0038 §1."
    )
    assert reached["db"] == ["nightshift.db", "nightshift.db.base"], (
        f"nightshift.mcp reached {reached['db']}. Only `nightshift.db.base` is "
        "allowed, and only for its enums — see ADR 0038 §1."
    )


def test_the_stdio_server_writes_only_protocol_to_stdout() -> None:
    """§3's trap: on stdio the transport **is** stdout.

    One stray `print`, one logging handler left on the default stream, and the
    JSON-RPC framing is corrupt. The symptom is Claude Desktop reporting that
    the server failed, with nothing useful in any log a person thinks to open,
    so this is worth a subprocess and a real pipe.

    The server is driven far enough to answer `initialize`, which is the point
    by which configuration, logging setup and the whole import graph have run —
    the places a stray write actually comes from.
    """
    request = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {},
                    "clientInfo": {"name": "boundary-test", "version": "0"},
                },
            }
        )
        + "\n"
    )

    result = subprocess.run(
        [sys.executable, "-m", "nightshift.mcp"],
        cwd=API_ROOT,
        input=request,
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT,
        env={
            "PATH": "/usr/bin:/bin",
            "NIGHTSHIFT_API_URL": "http://127.0.0.1:9",
            "NIGHTSHIFT_MCP_TOKEN": "nsk_not_a_real_token_and_never_used_here",
            # No database is reachable and none should be wanted. If the server
            # ever grows a `session_scope` call, it fails here rather than in
            # somebody's Claude Desktop.
            "NIGHTSHIFT_ENV": "test",
        },
    )

    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:  # pragma: no cover - the failure this guards
            pytest.fail(
                f"non-protocol output on stdout would corrupt the transport: {line!r}\n"
                f"stderr was:\n{result.stderr}"
            )
        assert frame.get("jsonrpc") == "2.0", f"stdout carried non-JSON-RPC JSON: {line!r}"

    assert result.stdout.strip(), (
        "the server answered nothing at all — it should have replied to initialize.\n"
        f"stderr was:\n{result.stderr}"
    )


def test_the_entry_point_refuses_to_start_without_a_token() -> None:
    """A misconfigured server must fail loudly, on stderr, and stop.

    The alternative — starting anyway and failing at the first tool call — is
    worse than useless: Claude Desktop shows the server as connected, the
    person asks a question, and the answer is an authentication error with no
    hint that the config file is the problem.
    """
    result = subprocess.run(
        [sys.executable, "-m", "nightshift.mcp"],
        cwd=API_ROOT,
        input="",
        capture_output=True,
        text=True,
        timeout=STARTUP_TIMEOUT,
        env={"PATH": "/usr/bin:/bin", "NIGHTSHIFT_API_URL": "http://127.0.0.1:9"},
    )

    assert result.returncode != 0
    assert "NIGHTSHIFT_MCP_TOKEN" in result.stderr
    assert result.stdout.strip() == "", "even a startup failure must not write to stdout"
