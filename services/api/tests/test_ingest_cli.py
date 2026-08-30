"""`make ingest` must reach every board the registry lists.

The recorded gap, found on 2026-08-24: `cmd_ingest` hardcoded
`pollable(ats="greenhouse")` and reached **2 of 23 registered boards**, because
the registry is mostly Ashby. Two of the three adapters M1 built had no live CLI
entry point at all, and nothing said so — the command printed a successful run
over the two boards it could see.

**Nothing here enables outbound HTTP.** The first draft of this file did, to
exercise an argument-validation path, and the suite spent two minutes polling
live Greenhouse boards before it was killed. A test that flips the one guard
keeping `make demo` offline is not a test of the guard; it is a hole in it. The
`--ats` check therefore lives in argparse, where it is reachable without a
network and without a database.
"""

from __future__ import annotations

import argparse

import pytest

from nightshift.cli import cmd_ingest, main
from nightshift.domain.polling import ADAPTERS
from nightshift.domain.registry import get_registry


def test_every_registered_ats_has_an_adapter() -> None:
    """A registry row naming an ATS nothing can poll is a board nobody polls
    and nobody reports, which is the failure A1's registry exists to prevent."""
    registered = {entry.ats for entry in get_registry().pollable()}
    assert registered <= set(ADAPTERS), (
        f"registry has boards no adapter can poll: {sorted(registered - set(ADAPTERS))}"
    )


def test_the_registry_reaches_more_than_one_ats() -> None:
    """The control on the test above.

    `registered <= set(ADAPTERS)` is satisfied trivially by a registry holding
    one ATS, which is exactly the state the old command's bug was invisible in.
    """
    registered = {entry.ats for entry in get_registry().pollable()}
    assert len(registered) > 1, f"registry covers only {sorted(registered)}"


def test_both_internship_lists_are_registered_and_pollable() -> None:
    """the-hunt.md §5.2. Two lists, two sources, deliberately not collapsed into
    one: they overlap heavily, and merging them would hide which was right."""
    registered = {entry.ats for entry in get_registry().pollable()}
    assert {"simplify_list", "vansh_list"} <= registered


def test_an_unknown_ats_is_rejected_before_anything_runs() -> None:
    """A typo that polls nothing and exits 0 reads exactly like a quiet day."""
    with pytest.raises(SystemExit) as exit_info:
        main(["ingest", "--ats", "nonesuch"])
    assert exit_info.value.code != 0


async def test_ingest_refuses_to_reach_the_network_when_it_is_disabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The offline guarantee, at the one command that would break it.

    `make demo` from a clean clone must never reach a network, so the command
    exits non-zero and says what to set rather than quietly polling nothing.
    """
    from nightshift.config import get_settings

    monkeypatch.setattr(get_settings(), "outbound_http_enabled", False)
    code = await cmd_ingest(argparse.Namespace(ats=None))
    assert code == 1
    assert "OUTBOUND_HTTP_ENABLED" in capsys.readouterr().err
