"""Board registry loading and validation.

The registry is source data (A1), and a typo in it is a board that silently never
gets polled. These tests exist because that failure is invisible: nothing errors,
you just quietly stop seeing a company's jobs.

The committed file is validated too, not only synthetic ones — a registry that
parses in a test but not in production would be a strange kind of useless.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nightshift.domain.registry import (
    DEFAULT_REGISTRY_PATH,
    BoardEntry,
    BoardRegistry,
    BoardStatus,
    load_registry,
)


def write_registry(tmp_path: Path, boards: list[dict[str, object]]) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"boards": boards}))
    return path


BASE_ENTRY: dict[str, object] = {
    "company": "Datadog",
    "ats": "greenhouse",
    "token": "datadog",
    "added": "2026-07-29",
    "status": "active",
    "nyc_presence": True,
}


class TestTheCommittedRegistry:
    """The real file, as shipped."""

    def test_loads_and_validates(self) -> None:
        registry = load_registry()
        assert len(registry.boards) >= 1

    #: The boards a human wrote by hand, before discovery existed. The closed
    #: set below covers exactly these, and nothing else, on purpose.
    CURATED = frozenset(
        {
            ("greenhouse", "datadog"),
            ("greenhouse", "stripe"),
            ("lever", "alloy"),
            ("ashby", "ramp"),
        }
    )

    def test_the_hand_curated_boards_are_exactly_these(self) -> None:
        """Closed-set check over the boards a human wrote by hand.

        This used to enumerate *every* pollable board. That stopped scaling the
        moment the registry began being filled by a pipeline (ADR 0005): at a
        few hundred entries the list is a rubber stamp, and a control nobody
        performs is worse than a weaker one that runs.

        What still matters is that a board a human deliberately turned off
        cannot come back silently. `Stripe` sits at `status: disabled` and
        nothing else in this file would catch it turning `active`.
        """
        pollable = {(e.ats, e.token) for e in load_registry().pollable()}
        assert pollable & self.CURATED == {
            ("greenhouse", "datadog"),
            ("lever", "alloy"),
            ("ashby", "ramp"),
        }, "a hand-curated board changed status without this test being updated"

    def test_every_other_pollable_board_records_how_it_got_there(self) -> None:
        """A board that reached `active` without going through ADR 0005's
        approval gate has no audit trail, and a hand-added one is exactly what
        the gate exists to prevent. The provenance is in `notes`, written by
        `promote`, so this fails for a board somebody typed in directly."""
        for entry in load_registry().pollable():
            if (entry.ats, entry.token) in self.CURATED:
                continue
            assert entry.notes and "ADR 0005" in entry.notes, (
                f"{entry.ats}:{entry.token} is pollable but records no approval"
            )

    def test_stripe_is_still_disabled(self) -> None:
        """Named separately from the set check above, because this is the case
        that motivated having one: its note reads "enable once the freshness and
        closure state machine lands", and M1d is that milestone. Enabling it is
        a human's decision, not a side effect of finishing the work."""
        stripe = load_registry().by_token("greenhouse", "stripe")
        assert stripe is not None
        assert stripe.status is BoardStatus.DISABLED

    def test_datadogs_m0_board_is_still_pollable(self) -> None:
        """A6: M0's one board must keep resolving as M1 adds breadth around it."""
        tokens = {(entry.ats, entry.token) for entry in load_registry().pollable()}
        assert ("greenhouse", "datadog") in tokens

    def test_the_first_lever_board_added_in_m1a_is_pollable(self) -> None:
        """M1a: Lever is the second provider behind the adapter Protocol."""
        tokens = {(entry.ats, entry.token) for entry in load_registry().pollable()}
        assert ("lever", "alloy") in tokens

    def test_the_first_ashby_board_added_in_m1a_is_pollable(self) -> None:
        """M1a: Ashby is the third and, for now, last provider behind the adapter Protocol."""
        tokens = {(entry.ats, entry.token) for entry in load_registry().pollable()}
        assert ("ashby", "ramp") in tokens

    def test_every_entry_records_when_a_human_verified_it(self) -> None:
        for board in load_registry().boards:
            assert board.verified_at is not None, f"{board.company} has no verified_at"

    def test_the_file_is_where_the_code_expects_it(self) -> None:
        assert DEFAULT_REGISTRY_PATH.exists()
        assert DEFAULT_REGISTRY_PATH.name == "board-registry.yaml"


class TestValidation:
    def test_rejects_an_unknown_ats(self) -> None:
        with pytest.raises(ValidationError):
            BoardEntry.model_validate({**BASE_ENTRY, "ats": "workday"})

    def test_rejects_an_unknown_field(self) -> None:
        """extra='forbid': a misspelled key must not be silently ignored."""
        with pytest.raises(ValidationError):
            BoardEntry.model_validate({**BASE_ENTRY, "nyc_presense": True})

    def test_rejects_a_duplicate_token_for_the_same_ats(self) -> None:
        """Two entries for one board would poll it twice and double-count its jobs."""
        with pytest.raises(ValidationError, match="duplicate board entries"):
            BoardRegistry.model_validate({"boards": [BASE_ENTRY, dict(BASE_ENTRY)]})

    def test_allows_the_same_token_on_different_providers(self) -> None:
        """Board slugs are namespaced per ATS; 'stripe' on two providers is fine."""
        registry = BoardRegistry.model_validate(
            {"boards": [BASE_ENTRY, {**BASE_ENTRY, "ats": "lever"}]}
        )
        assert len(registry.boards) == 2

    @pytest.mark.parametrize(
        "token",
        [
            "../../etc/passwd",
            "datadog/jobs",
            "datadog?x=1",
            "data dog",
            "datadog#frag",
            "",
        ],
    )
    def test_rejects_a_token_that_could_escape_a_url_path(self, token: str) -> None:
        """The token is interpolated straight into a request URL."""
        with pytest.raises(ValidationError):
            BoardEntry.model_validate({**BASE_ENTRY, "token": token})

    @pytest.mark.parametrize("token", ["datadog", "acme-corp", "acme_corp", "acme.corp", "a1b2"])
    def test_accepts_the_token_shapes_providers_actually_use(self, token: str) -> None:
        assert BoardEntry.model_validate({**BASE_ENTRY, "token": token}).token == token

    def test_strips_surrounding_whitespace_from_a_token(self) -> None:
        assert BoardEntry.model_validate({**BASE_ENTRY, "token": "  datadog "}).token == "datadog"

    def test_a_missing_file_names_itself(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="must be committed"):
            load_registry(tmp_path / "nope.yaml")

    def test_a_file_without_a_boards_key_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "registry.yaml"
        path.write_text(yaml.safe_dump({"entries": []}))
        with pytest.raises(ValueError, match="top-level 'boards' list"):
            load_registry(path)


class TestPollability:
    @pytest.mark.parametrize(
        "status,pollable",
        [("active", True), ("dead", False), ("moved", False), ("disabled", False)],
    )
    def test_only_active_boards_are_polled(self, status: str, pollable: bool) -> None:
        entry = BoardEntry.model_validate({**BASE_ENTRY, "status": status})
        assert entry.is_pollable is pollable

    def test_a_dead_entry_stays_in_the_registry(self, tmp_path: Path) -> None:
        """I3-adjacent: a dead board surfaces for review; it does not disappear,
        and it does not close the jobs it previously produced."""
        path = write_registry(
            tmp_path,
            [BASE_ENTRY, {**BASE_ENTRY, "token": "gone", "company": "Gone", "status": "dead"}],
        )
        registry = load_registry(path)
        assert len(registry.boards) == 2
        assert len(registry.pollable()) == 1
        assert registry.by_token("greenhouse", "gone") is not None

    def test_nyc_boards_are_polled_first(self, tmp_path: Path) -> None:
        """A1: nyc_presence is used to prioritise polls."""
        path = write_registry(
            tmp_path,
            [
                {**BASE_ENTRY, "token": "elsewhere", "company": "Elsewhere", "nyc_presence": False},
                {**BASE_ENTRY, "token": "nycco", "company": "NYC Co", "nyc_presence": True},
            ],
        )
        assert [b.token for b in load_registry(path).pollable()] == ["nycco", "elsewhere"]

    def test_poll_order_is_deterministic(self, tmp_path: Path) -> None:
        """A run must be reproducible, and a failure attributable to a fixed order."""
        boards = [
            {**BASE_ENTRY, "token": t, "company": t, "nyc_presence": False}
            for t in ("zebra", "alpha", "mango")
        ]
        registry = load_registry(write_registry(tmp_path, boards))
        assert [b.token for b in registry.pollable()] == ["alpha", "mango", "zebra"]

    def test_filters_by_ats(self, tmp_path: Path) -> None:
        path = write_registry(tmp_path, [BASE_ENTRY, {**BASE_ENTRY, "ats": "lever"}])
        registry = load_registry(path)
        assert len(registry.pollable(ats="greenhouse")) == 1
        assert len(registry.pollable(ats="ashby")) == 0

    def test_to_ref_carries_what_the_adapter_needs(self) -> None:
        ref = BoardEntry.model_validate(BASE_ENTRY).to_ref()
        assert (ref.company, ref.ats, ref.token, ref.nyc_presence) == (
            "Datadog",
            "greenhouse",
            "datadog",
            True,
        )


def test_status_default_is_active() -> None:
    entry = BoardEntry.model_validate({k: v for k, v in BASE_ENTRY.items() if k != "status"})
    assert entry.status is BoardStatus.ACTIVE
