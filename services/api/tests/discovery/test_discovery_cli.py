"""The discovery CLI's safety properties.

Not "does it print the right thing" — the interesting assertions here are all
about what each command *refuses* to do. `approve` is one typo away from
editing a committed file that decides which employers this product can ever
see, so the defaults are the feature.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nightshift.discovery.candidates import load_candidates, save_candidates
from nightshift.discovery.cli import main
from nightshift.discovery.models import Candidate, CandidateFile, Verdict

TODAY_ISH = "2026"


def _registry(path: Path, boards: list[dict[str, object]] | None = None) -> Path:
    path.write_text(yaml.safe_dump({"boards": boards or []}))
    return path


def _live_named(token: str, name: str) -> Candidate:
    from datetime import date

    return Candidate(
        ats="ashby",
        token=token,
        verdict=Verdict.LIVE_NAMED,
        company_name=name,
        posting_count=4,
        nyc_posting_count=2,
        first_seen=date(2026, 8, 2),
        last_validated=date(2026, 8, 2),
        source="crawl_index",
    )


class TestDiscover:
    def test_reads_the_committed_fixture_with_no_network(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The default path is offline by construction. If this ever needs a
        network the offline `make demo` guarantee is gone."""
        candidates = tmp_path / "candidates.yaml"
        code = main(
            [
                "--candidates",
                str(candidates),
                "--registry",
                str(_registry(tmp_path / "r.yaml")),
                "discover",
                "--provider",
                "ashby",
            ]
        )
        assert code == 0
        file = load_candidates(candidates)
        assert len(file.candidates) > 0
        assert {c.ats for c in file.candidates} == {"ashby"}

    def test_harvested_candidates_start_unvalidated_not_approvable(self, tmp_path: Path) -> None:
        """Harvesting is not evidence a board exists. A token that arrived
        `live_named` straight from a URL list would walk into the registry
        without anybody ever asking the provider anything."""
        candidates = tmp_path / "candidates.yaml"
        main(
            [
                "--candidates",
                str(candidates),
                "--registry",
                str(_registry(tmp_path / "r.yaml")),
                "discover",
                "--provider",
                "ashby",
            ]
        )
        file = load_candidates(candidates)
        assert all(c.verdict is not Verdict.LIVE_NAMED for c in file.candidates)

    def test_is_idempotent(self, tmp_path: Path) -> None:
        candidates = tmp_path / "candidates.yaml"
        registry = _registry(tmp_path / "r.yaml")
        argv = [
            "--candidates",
            str(candidates),
            "--registry",
            str(registry),
            "discover",
            "--provider",
            "ashby",
        ]
        main(argv)
        first = candidates.read_text()
        main(argv)
        assert candidates.read_text() == first

    def test_lever_is_refused_by_name_with_the_reason(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An empty harvest would read as "no Lever boards exist". The reason
        is structural (ADR 0006) and the operator has to be told which."""
        code = main(
            [
                "--candidates",
                str(tmp_path / "c.yaml"),
                "--registry",
                str(_registry(tmp_path / "r.yaml")),
                "discover",
                "--provider",
                "lever",
            ]
        )
        assert code == 2
        assert "CCBot" in capsys.readouterr().err

    def test_live_refuses_without_the_kill_switch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OUTBOUND_HTTP_ENABLED", "false")
        from nightshift.config import get_settings

        get_settings.cache_clear()
        code = main(
            [
                "--candidates",
                str(tmp_path / "c.yaml"),
                "--registry",
                str(_registry(tmp_path / "r.yaml")),
                "discover",
                "--provider",
                "ashby",
                "--live",
            ]
        )
        get_settings.cache_clear()
        assert code == 2
        assert "OUTBOUND_HTTP_ENABLED" in capsys.readouterr().err


class TestApprove:
    def test_is_dry_run_by_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The whole point of the command's shape. A destructive-looking target
        should need an extra word before it edits a committed file."""
        candidates = tmp_path / "candidates.yaml"
        save_candidates(CandidateFile(candidates=(_live_named("acme", "Acme"),)), candidates)
        registry = _registry(tmp_path / "r.yaml")
        before = registry.read_text()

        code = main(["--candidates", str(candidates), "--registry", str(registry), "approve"])

        assert code == 0
        assert registry.read_text() == before
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert "Acme" in out

    def test_write_promotes_and_says_who_commits(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        candidates = tmp_path / "candidates.yaml"
        save_candidates(CandidateFile(candidates=(_live_named("acme", "Acme"),)), candidates)
        registry = _registry(tmp_path / "r.yaml")

        code = main(
            ["--candidates", str(candidates), "--registry", str(registry), "approve", "--write"]
        )

        assert code == 0
        boards = yaml.safe_load(registry.read_text())["boards"]
        assert [b["token"] for b in boards] == ["acme"]
        assert "commit it yourself" in capsys.readouterr().out

    def test_reports_what_it_is_holding_rather_than_only_what_it_will_take(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """I6, applied to a report: a summary that only lists the approvable
        set hides the size of the queue nobody is working through."""
        from datetime import date

        held = Candidate(
            ats="ashby",
            token="mystery",
            verdict=Verdict.LIVE_UNNAMED,
            posting_count=10,
            first_seen=date(2026, 8, 2),
            last_validated=date(2026, 8, 2),
            source="crawl_index",
        )
        candidates = tmp_path / "candidates.yaml"
        save_candidates(CandidateFile(candidates=(held,)), candidates)

        main(
            [
                "--candidates",
                str(candidates),
                "--registry",
                str(_registry(tmp_path / "r.yaml")),
                "approve",
            ]
        )

        out = capsys.readouterr().out
        assert "held for individual review" in out
        assert "live_unnamed" in out

    def test_an_unnameable_board_is_not_promoted_even_with_write(self, tmp_path: Path) -> None:
        """The gate, exercised through the command a human actually types
        rather than through the function under it."""
        from datetime import date

        junk = Candidate(
            ats="ashby",
            token="a3c41b8b71eff8c4",
            verdict=Verdict.LIVE_UNNAMED,
            posting_count=10,
            first_seen=date(2026, 8, 2),
            last_validated=date(2026, 8, 2),
            source="crawl_index",
        )
        candidates = tmp_path / "candidates.yaml"
        save_candidates(CandidateFile(candidates=(junk,)), candidates)
        registry = _registry(tmp_path / "r.yaml")

        main(["--candidates", str(candidates), "--registry", str(registry), "approve", "--write"])

        assert yaml.safe_load(registry.read_text())["boards"] == []


class TestValidate:
    def test_refuses_without_the_kill_switch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OUTBOUND_HTTP_ENABLED", "false")
        from nightshift.config import get_settings

        get_settings.cache_clear()
        code = main(
            [
                "--candidates",
                str(tmp_path / "c.yaml"),
                "--registry",
                str(_registry(tmp_path / "r.yaml")),
                "validate",
            ]
        )
        get_settings.cache_clear()
        assert code == 2
        assert "OUTBOUND_HTTP_ENABLED" in capsys.readouterr().err


def test_no_command_is_scheduled() -> None:
    """A1 and ADR 0006: discovery is a decision somebody makes, not a cron
    entry. Asserted against the worker's schedule rather than by reading the
    CLI, because that is where an accidental entry would actually appear."""
    from nightshift.workers import main as worker_main

    source = Path(worker_main.__file__).read_text()
    assert "discovery" not in source.lower()


def test_a_withheld_collision_is_named_not_silently_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two candidates naming one employer are held — but an operator reading a
    report they are simply missing from will conclude the board was never
    discovered. The report has to say why it is not offering them."""
    candidates = tmp_path / "candidates.yaml"
    save_candidates(
        CandidateFile(
            candidates=(_live_named("Abridge", "Abridge"), _live_named("abridge", "Abridge"))
        ),
        candidates,
    )

    main(
        [
            "--candidates",
            str(candidates),
            "--registry",
            str(_registry(tmp_path / "r.yaml")),
            "approve",
        ]
    )

    out = capsys.readouterr().out
    assert "withheld" in out
    assert "same employer" in out
    assert "Abridge" in out
