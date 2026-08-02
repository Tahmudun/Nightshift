"""Promotion from candidate to registry entry (ADR 0005).

A1 required per-entry human review. At 2,605 candidates that is a control
nobody performs, and an unperformed control is worse than a weaker one that
runs — because the documentation still claims the strong one. ADR 0005 moved it
to batch approval with typed exceptions, and these tests are what keep the
exceptions real.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pytest
import yaml

from nightshift.discovery.approve import approvable, approval_report, promote
from nightshift.discovery.models import Candidate, CandidateFile, Verdict

TODAY = date(2026, 8, 2)


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "ats": "ashby",
        "token": "acme",
        "verdict": Verdict.LIVE_NAMED,
        "company_name": "Acme",
        "posting_count": 3,
        "nyc_posting_count": 1,
        "first_seen": TODAY,
        "last_validated": TODAY,
        "source": "crawl_index",
    }
    return Candidate(**{**defaults, **overrides})  # type: ignore[arg-type]


def _registry_with(boards: list[dict[str, object]], path: Path) -> Path:
    path.write_text(yaml.safe_dump({"boards": boards}))
    return path


class TestOnlyLiveNamedReachesBulkApproval:
    @pytest.mark.parametrize(
        "verdict",
        [Verdict.LIVE_UNNAMED, Verdict.NAME_COLLISION, Verdict.EMPTY, Verdict.UNREACHABLE],
    )
    def test_every_other_verdict_is_held(self, verdict: Verdict) -> None:
        name = None if verdict is Verdict.LIVE_UNNAMED else "Acme"
        file = CandidateFile(candidates=(_candidate(verdict=verdict, company_name=name),))
        assert approvable(file, registry_tokens=frozenset()) == []

    def test_the_junk_board_cannot_be_promoted_by_approving_wholesale(self) -> None:
        """board-discovery.md §13's approval test, stated as it means it.

        Approving the entire report must still not promote a live_unnamed
        candidate. If this ever passes, the gate is decorative.
        """
        junk = _candidate(
            token="a3c41b8b71eff8c4",
            verdict=Verdict.LIVE_UNNAMED,
            company_name=None,
            posting_count=10,
        )
        good = _candidate(token="realco", company_name="Real Co")
        file = CandidateFile(candidates=(junk, good))
        promoted = approvable(file, registry_tokens=frozenset())
        assert [c.token for c in promoted] == ["realco"]

    def test_a_candidate_already_in_the_registry_is_not_promoted_twice(self) -> None:
        file = CandidateFile(candidates=(_candidate(),))
        assert approvable(file, registry_tokens=frozenset({("ashby", "acme")})) == []

    def test_the_same_token_on_another_provider_is_still_approvable(self) -> None:
        """Non-vacuity for the test above: a check that compared tokens alone
        would pass it and wrongly hold a genuinely different board. `ramp` is
        live on both Lever and Ashby."""
        file = CandidateFile(candidates=(_candidate(ats="lever", token="acme"),))
        assert len(approvable(file, registry_tokens=frozenset({("ashby", "acme")}))) == 1

    def test_an_unrecognised_verdict_would_not_be_approvable(self) -> None:
        """The gate is a single equality against LIVE_NAMED, not a set of
        exclusions, so a verdict added in a later milestone defaults to held.
        Asserted structurally: every verdict except LIVE_NAMED is refused."""
        for verdict in Verdict:
            if verdict is Verdict.LIVE_NAMED:
                continue
            name = None if verdict is Verdict.LIVE_UNNAMED else "Acme"
            file = CandidateFile(candidates=(_candidate(verdict=verdict, company_name=name),))
            assert approvable(file, registry_tokens=frozenset()) == [], verdict


class TestTheReport:
    def test_orders_nyc_boards_first(self) -> None:
        """§6: review effort lands on what matters and the tail can be skimmed.

        `posting_count` is raised alongside the NYC count on purpose — the
        model refuses a candidate whose NYC count exceeds its total, which is
        the rule that keeps this number meaning what M1d will read it as.
        """
        far = _candidate(token="far", company_name="Far Co", nyc_posting_count=0)
        near = _candidate(
            token="near", company_name="Near Co", posting_count=9, nyc_posting_count=7
        )
        report = approval_report([far, near])
        assert report.index("Near Co") < report.index("Far Co")

    def test_carries_every_field_the_human_needs_to_decide(self) -> None:
        report = approval_report([_candidate(company_name="Acme", posting_count=3)])
        for expected in ("Acme", "ashby", "acme", "3", "live_named"):
            assert expected in report

    def test_an_empty_report_says_so_rather_than_being_blank(self) -> None:
        """A blank output reads as a crash."""
        assert "no candidates" in approval_report([]).lower()

    def test_a_long_employer_name_does_not_hide_the_token(self) -> None:
        """The columns are fixed-width. A name that overflowed into the next
        column would make the token unreadable, and the token is what a human
        is actually checking."""
        long_name = "A" * 120
        report = approval_report([_candidate(company_name=long_name, token="distinctivetoken")])
        assert "distinctivetoken" in report
        assert len(max(report.splitlines(), key=len)) < 120


class TestPromotion:
    def test_writes_registry_entries_for_approved_candidates(self, tmp_path: Path) -> None:
        registry = _registry_with([], tmp_path / "board-registry.yaml")
        file = CandidateFile(candidates=(_candidate(company_name="Acme"),))

        count, promoted = promote(file, registry_path=registry, today=TODAY)

        assert count == 1
        assert [c.token for c in promoted] == ["acme"]
        written = yaml.safe_load(registry.read_text())["boards"]
        assert written[0]["company"] == "Acme"
        assert written[0]["token"] == "acme"
        assert written[0]["status"] == "active"
        assert written[0]["added"] == TODAY.isoformat()

    def test_nyc_presence_comes_from_parsed_postings_not_from_a_guess(self, tmp_path: Path) -> None:
        """A1 uses this field to prioritise polling. It is set from the count
        the validator read off the postings, so a board with zero NYC postings
        must not arrive claiming an NYC office."""
        registry = _registry_with([], tmp_path / "board-registry.yaml")
        promote(
            CandidateFile(
                candidates=(
                    _candidate(token="near", company_name="Near", nyc_posting_count=2),
                    _candidate(token="far", company_name="Far", nyc_posting_count=0),
                )
            ),
            registry_path=registry,
            today=TODAY,
        )
        written = {b["token"]: b for b in yaml.safe_load(registry.read_text())["boards"]}
        assert written["near"]["nyc_presence"] is True
        assert written["far"]["nyc_presence"] is False

    def test_never_removes_an_existing_entry(self, tmp_path: Path) -> None:
        """A1: `dead` entries stay in the file, and promotion is additive.
        Rewriting the file from candidates alone would delete curated history."""
        registry = _registry_with(
            [
                {
                    "company": "Datadog",
                    "ats": "greenhouse",
                    "token": "datadog",
                    "added": "2026-07-29",
                    "verified_at": "2026-07-29",
                    "status": "active",
                    "nyc_presence": True,
                }
            ],
            tmp_path / "board-registry.yaml",
        )
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)
        tokens = {b["token"] for b in yaml.safe_load(registry.read_text())["boards"]}
        assert "datadog" in tokens

    def test_never_re_enables_a_board_a_human_disabled(self, tmp_path: Path) -> None:
        """The sharp edge of an additive write. A `disabled` or `dead` board is
        a decision somebody made; discovery re-finding it must not quietly
        overturn that, and must not add a second row for the same board."""
        registry = _registry_with(
            [
                {
                    "company": "Acme",
                    "ats": "ashby",
                    "token": "acme",
                    "added": "2026-07-01",
                    "status": "disabled",
                    "nyc_presence": False,
                }
            ],
            tmp_path / "board-registry.yaml",
        )
        count, _ = promote(
            CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY
        )
        boards = yaml.safe_load(registry.read_text())["boards"]
        assert count == 0
        assert len(boards) == 1
        assert boards[0]["status"] == "disabled"

    def test_is_idempotent(self, tmp_path: Path) -> None:
        registry = _registry_with([], tmp_path / "board-registry.yaml")
        file = CandidateFile(candidates=(_candidate(),))

        promote(file, registry_path=registry, today=TODAY)
        first = registry.read_text()
        promote(file, registry_path=registry, today=TODAY)
        assert registry.read_text() == first

    def test_writes_nothing_when_there_is_nothing_to_approve(self, tmp_path: Path) -> None:
        """Not just idempotent in content — it must not touch the file at all,
        so `git status` after a no-op run is clean and a human is never asked to
        review a diff that says nothing."""
        registry = _registry_with([], tmp_path / "board-registry.yaml")
        before = registry.stat().st_mtime_ns
        count, _ = promote(
            CandidateFile(candidates=(_candidate(verdict=Verdict.EMPTY, company_name=None),)),
            registry_path=registry,
            today=TODAY,
        )
        assert count == 0
        assert registry.stat().st_mtime_ns == before

    def test_the_written_registry_still_loads(self, tmp_path: Path) -> None:
        """The registry has its own validation — path-traversal on the token,
        unique (ats, token). Writing something it refuses to load would break
        ingestion at the next poll rather than here."""
        from nightshift.domain.registry import load_registry

        registry = _registry_with([], tmp_path / "board-registry.yaml")
        promote(
            CandidateFile(candidates=(_candidate(), _candidate(token="beta", company_name="Beta"))),
            registry_path=registry,
            today=TODAY,
        )
        loaded = load_registry(registry)
        assert len(loaded.boards) == 2

    def test_the_real_registry_would_still_load_after_promotion(self, tmp_path: Path) -> None:
        """Against the committed file rather than a synthetic one, because the
        committed file has a header comment, real entries and a `disabled` row —
        none of which a hand-built two-line fixture exercises."""
        from nightshift.domain.registry import DEFAULT_REGISTRY_PATH, load_registry

        copy = tmp_path / "board-registry.yaml"
        copy.write_text(DEFAULT_REGISTRY_PATH.read_text())
        before = len(load_registry(copy).boards)

        promote(
            CandidateFile(candidates=(_candidate(token="newboard", company_name="New Board"),)),
            registry_path=copy,
            today=TODAY,
        )
        after = load_registry(copy)
        assert len(after.boards) == before + 1

    def test_the_registrys_own_header_comment_survives(self, tmp_path: Path) -> None:
        """yaml.safe_dump discards comments. The header is the file's
        documentation — the rules about `dead` entries and what `verified_at`
        means live there and nowhere else — so a promotion run that silently
        deleted it would remove the only explanation of the file it edits."""
        from nightshift.domain.registry import DEFAULT_REGISTRY_PATH

        copy = tmp_path / "board-registry.yaml"
        copy.write_text(DEFAULT_REGISTRY_PATH.read_text())
        promote(
            CandidateFile(candidates=(_candidate(token="newboard", company_name="New Board"),)),
            registry_path=copy,
            today=TODAY,
        )
        text = copy.read_text()
        assert text.startswith("# ATS board registry")
        assert "invariant I3" in text


def test_promotion_writes_the_file_and_nothing_else() -> None:
    """§5: nothing writes to board-registry.yaml automatically. The command
    writes it; a human reads the diff and commits. There is no git call here."""
    from nightshift.discovery import approve

    source = inspect.getsource(approve)
    assert "git" not in source.lower(), "approval must never commit on a human's behalf"


class TestTwoCandidatesForOneEmployer:
    """Found by running the real pipeline, not by reading the code.

    The recorded crawl slice yields both `Abridge` and `abridge` — two live
    Ashby tokens, one employer, 42 postings each. The `name_collision` verdict
    is decided against names already in the *registry*, so it is structurally
    unable to see a collision between two candidates in the same batch, and
    both walked into the approval report.
    """

    def test_two_tokens_naming_one_employer_are_both_held(self) -> None:
        file = CandidateFile(
            candidates=(
                _candidate(token="Abridge", company_name="Abridge"),
                _candidate(token="abridge", company_name="Abridge"),
            )
        )
        assert approvable(file, registry_tokens=frozenset()) == []

    def test_a_case_or_suffix_variant_still_counts_as_one_employer(self) -> None:
        """The comparison is on the normalised name, the same one the validator
        uses against the registry, so "Acme" and "Acme, Inc." are one employer
        here exactly as they would be there."""
        file = CandidateFile(
            candidates=(
                _candidate(token="acme", company_name="Acme"),
                _candidate(token="acme-inc", company_name="Acme, Inc."),
            )
        )
        assert approvable(file, registry_tokens=frozenset()) == []

    def test_holding_a_collision_does_not_hold_the_rest_of_the_batch(self) -> None:
        """Non-vacuity: a check that dropped everything on any collision would
        pass the two tests above and make bulk approval useless."""
        file = CandidateFile(
            candidates=(
                _candidate(token="Abridge", company_name="Abridge"),
                _candidate(token="abridge", company_name="Abridge"),
                _candidate(token="realco", company_name="Real Co"),
            )
        )
        assert [c.token for c in approvable(file, registry_tokens=frozenset())] == ["realco"]

    def test_two_different_employers_are_both_still_approvable(self) -> None:
        """The other direction. `normalize_company_name` is deliberately
        conservative — Meta and Metabase stay distinct — and this gate must not
        widen it into a fuzzy matcher that merges real, different companies."""
        file = CandidateFile(
            candidates=(
                _candidate(token="meta", company_name="Meta"),
                _candidate(token="metabase", company_name="Metabase"),
            )
        )
        assert len(approvable(file, registry_tokens=frozenset())) == 2

    def test_the_same_employer_on_two_providers_is_still_a_collision(self) -> None:
        """`ramp` is live on both Lever and Ashby. Two providers serving one
        employer's jobs is a real duplicate feed, and which to poll is a human's
        call, not a coin toss."""
        file = CandidateFile(
            candidates=(
                _candidate(ats="ashby", token="ramp", company_name="Ramp"),
                _candidate(ats="lever", token="ramp", company_name="Ramp"),
            )
        )
        assert approvable(file, registry_tokens=frozenset()) == []
