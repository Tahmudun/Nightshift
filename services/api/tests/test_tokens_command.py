"""`nightshift tokens` — the only way an MCP token comes into existence.

Registration is closed and so is this: there is no `POST /auth/tokens`, because
a route that mints a year-long credential is a route worth attacking, and the
person who needs one has a shell. `cmd_users` set that precedent in M5b and
this command follows it.

**Nothing here drives the whole command, and that is a finding rather than a
gap.** The first draft did, through a fixture that committed a real account so
`session_scope` could see it. It passed alone and **errored in the full suite**:
`session_scope`'s engine is cached at module level and bound to whichever event
loop touches it first, so a session-scoped fixture reaching it is a coin flip
depending on what ran before. `test_seed_reports_its_own_failure.py` documents
that hazard; this milestone met it.

The fix was not a cleverer fixture. It was noticing that the property worth
testing — **the token printed is the token stored** — is a property of a
formatter, and that a command which reads an account, calls `create_session`
and prints the result has nothing left to get wrong once each of those three is
tested. So `format_token_report` and `format_token_listing` are pure functions
tested here, `list_mcp_tokens` and `revoke_session_by_id` are domain functions
tested in `test_mcp_tokens.py`, and `cmd_tokens` is the composition.

That is `CLAUDE.md` §3 arriving by way of a broken test: a CLI command is as
much "validate and delegate" as a route handler is.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from nightshift.cli import _claude_desktop_block, format_token_listing, format_token_report
from nightshift.db.models import UserSession
from nightshift.domain.identity import TOKEN_PREFIX, IssuedSession, hash_token


def _issued() -> IssuedSession:
    """A minted session, exactly as `create_session` hands one back."""
    return IssuedSession(
        token=f"{TOKEN_PREFIX}v9Qh2Lm4Rt7Xz1Nb8Kd3Ps6Wc0Fj5Yg2Hn7Tv4Ql1",
        session_id=uuid.uuid4(),
        expires_at=datetime(2027, 8, 21, tzinfo=UTC),
    )


def _fake_row(label: str | None) -> UserSession:
    """A detached row. `format_token_listing` reads three attributes and no more."""
    row = UserSession()
    row.id = uuid.uuid4()
    row.label = label
    row.expires_at = datetime(2027, 8, 21, tzinfo=UTC)
    row.token_hash = "f" * 64
    return row


# --------------------------------------------------------------------------
# Minting
# --------------------------------------------------------------------------


def test_the_report_carries_the_minted_token_and_no_other() -> None:
    """The property a typo in an f-string would break, and nothing else would catch.

    The token appears **twice** on purpose — once on its own line to read, once
    inside the JSON to paste — and both must be the same string. A report that
    printed a different value in the block than above it would be a config file
    that authenticates as nobody, discovered at the far end of Claude Desktop's
    restart cycle.
    """
    issued = _issued()

    report = format_token_report(issued, email="you@example.test", api_url="http://localhost:8000")

    # Scanned with a regex rather than by splitting on whitespace: the second
    # copy lives inside JSON and is wrapped in quotes, so `startswith` misses
    # it and the test would pass while proving half of what it claims.
    printed = re.findall(rf"{TOKEN_PREFIX}[A-Za-z0-9_-]+", report)
    assert printed == [issued.token, issued.token], "the two copies must be the same token"

    block = json.loads(report[report.index("{") : report.rindex("}") + 1])
    assert block["mcpServers"]["nightshift"]["env"]["NIGHTSHIFT_MCP_TOKEN"] == issued.token


def test_the_report_says_the_token_cannot_be_recovered() -> None:
    """Only the SHA-256 reaches the database — `0024`'s decision.

    A person who assumes they can look it up again will not save it, and there
    is no path back. Saying so at the one moment it is on screen is the whole
    mitigation.
    """
    report = format_token_report(_issued(), email="you@example.test", api_url="http://x")

    assert "cannot be recovered" in report


def test_the_report_tells_you_how_to_end_it() -> None:
    """A credential you cannot find the id of is a credential you cannot revoke.

    Revocability is what this design offers *instead of* a short expiry (see
    `MCP_TOKEN_LIFETIME`), so the id has to be somewhere a person will still
    have it — which is the same screen as the token.
    """
    issued = _issued()

    report = format_token_report(issued, email="you@example.test", api_url="http://x")

    assert str(issued.session_id) in report
    assert "--revoke" in report


def test_the_config_block_points_at_this_interpreter() -> None:
    """The command Claude Desktop runs has to be a real path.

    `python -m nightshift.mcp` against whatever `python` resolves to in Claude
    Desktop's environment is not this virtualenv, and the failure mode is a
    server that never starts, with a message nobody sees.
    """
    block = json.loads(_claude_desktop_block("nsk_test", api_url="http://localhost:8000"))
    server = block["mcpServers"]["nightshift"]

    assert server["command"] == sys.executable
    assert server["args"] == ["-m", "nightshift.mcp"]
    assert server["env"]["NIGHTSHIFT_MCP_TOKEN"] == "nsk_test"
    assert server["env"]["NIGHTSHIFT_API_URL"] == "http://localhost:8000"


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


def test_the_listing_prints_neither_a_token_nor_a_hash() -> None:
    """The hash matters as much as the token: `resolve_session` looks up *by* it.

    A listing exists so somebody can choose which credential to end. Printing
    the secret would make it a second copy of every live credential, sitting in
    a terminal scrollback.
    """
    rows = [_fake_row("claude desktop"), _fake_row(None)]

    rendered = format_token_listing(rows, email="you@example.test")

    assert TOKEN_PREFIX not in rendered
    assert "f" * 64 not in rendered
    for row in rows:
        assert str(row.id) in rendered, "an id you cannot read is an id you cannot revoke"


def test_the_listing_names_an_unnamed_token_rather_than_leaving_a_gap() -> None:
    """`label` is nullable, and a blank column is how somebody revokes the wrong one."""
    rendered = format_token_listing([_fake_row(None)], email="you@example.test")

    assert "(unnamed)" in rendered


def test_an_empty_listing_says_so_rather_than_printing_a_header() -> None:
    rendered = format_token_listing([], email="you@example.test")

    assert "no live MCP tokens" in rendered
    assert "live MCP token(s)" not in rendered


# --------------------------------------------------------------------------
# The prefix, which is the secret scan's only handle on a leak
# --------------------------------------------------------------------------


def test_a_minted_token_starts_with_the_scanned_prefix() -> None:
    """`.gitleaks.toml` matches `nsk_` plus 40 characters.

    If the prefix ever changes here and not there, the scan goes silently blind
    to every credential this system mints — and a rule that matches nothing
    looks exactly like a rule with nothing to find.
    """
    issued = _issued()

    assert issued.token.startswith(TOKEN_PREFIX)
    assert len(issued.token) - len(TOKEN_PREFIX) >= 40


def test_hashing_covers_the_prefix_too() -> None:
    """The prefix is part of the token, not decoration around it.

    A hash taken after stripping it would make every token in the database
    collide with the same characters under a different prefix.
    """
    issued = _issued()

    assert hash_token(issued.token) != hash_token(issued.token.removeprefix(TOKEN_PREFIX))


def test_the_gitleaks_rule_matches_a_real_token() -> None:
    """The rule and the minted shape, checked against each other rather than assumed.

    The pattern is a literal here rather than parsed out of the TOML, and that
    is the point: this test must go red when somebody edits one side, and a
    test that reads the file it is checking cannot do that.
    """
    pattern = r"nsk_[A-Za-z0-9_-]{40,}"
    config = Path(__file__).resolve().parents[3] / ".gitleaks.toml"

    assert pattern in config.read_text(), "the rule in .gitleaks.toml no longer matches this test"
    assert re.search(pattern, _issued().token)
    assert not re.search(pattern, TOKEN_PREFIX), "the bare prefix must not trip the scan"
