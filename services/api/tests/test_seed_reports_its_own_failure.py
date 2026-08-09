"""`make seed` must not exit 0 over an empty database.

Found on 2026-08-05 in the worst possible way. A model change landed before its
migration, every INSERT failed with `type "role_family" does not exist`,
`ingest_boards` counted all 31 postings into `stats.failed` — which is correct,
I3 says one bad posting may not kill a board — and the seed command printed
"seed complete" and exited 0 over a database with no jobs in it.

The counts were on screen the whole time. That is not enough. **CI's "Seed
loads" step reads the exit code and nothing else**, so a completely broken seed
was a green check, and `make demo` would have handed a developer an empty city
under a success message. `make acceptance` would have caught it — `verify.py`
indexes `jobs["items"][0]` and would have raised — but the CI seed step has no
such backstop and is the one that runs on every push.

This is the eighth time in this project something that reported success was
wrong, and the first where the reporter was the seed itself.
"""

from __future__ import annotations

import argparse
from typing import Any

import pytest

from nightshift import cli
from tests.conftest import requires_db


@requires_db
async def test_the_seed_exit_code_follows_whether_anything_persisted(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Both directions, and it has to be one test rather than two.

    `cmd_seed` reaches the database through `session_scope`, whose engine is
    cached at module level and bound to the event loop that first used it.
    pytest-asyncio gives each test its own loop
    (`asyncio_default_fixture_loop_scope = "function"`), so a *second* test in
    this file calling the seed dies with "Event loop is closed" before it can
    assert anything. Split into two tests, the first passes and the second is
    an infrastructure failure wearing a real test's name — which is worse than
    one test doing both.

    Both directions are needed and neither is decorative: a guard written as an
    unconditional `return 1` satisfies the failure case on its own, and the
    second half is what kills that mutation.

    Only the final count is replaced. Patching that rather than breaking the
    schema is deliberate — this failure already has two unrelated causes (a
    missing enum type, and orphaned `source_job_records` left by a careless
    truncate, both met the day it was written), so the test asserts the outcome
    and stays true whatever produced it.
    """
    monkeypatch.setattr(cli, "_canonical_job_count", _returning(0))
    assert await cli.cmd_seed(argparse.Namespace()) == 1
    assert "persisted no canonical jobs" in capsys.readouterr().err

    monkeypatch.setattr(cli, "_canonical_job_count", _returning(31))
    assert await cli.cmd_seed(argparse.Namespace()) == 0
    assert "seed complete" in capsys.readouterr().out


def _returning(count: int) -> Any:
    async def _count() -> int:
        return count

    return _count
