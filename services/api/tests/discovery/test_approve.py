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


class TestPromotionPreservesTheFile:
    """`promote` says "additive, never destructive" and, until M1d, was only
    additive in the *data*.

    It rebuilt the document with `yaml.safe_dump`, which cannot round-trip
    comments. `_leading_comment` saved the header — so the author knew — but
    everything between entries was deleted. The first real `--write` in this
    project's history removed ten lines of rationale, including the note on the
    `Stripe` entry reading "enable once the freshness and closure state machine
    lands", which is a message to the milestone that eventually read it.

    M1c could not have caught this. It deliberately never wrote to the registry
    and cited byte-identity as evidence of restraint.
    """

    def _registry_with_comments(self, tmp_path: Path) -> Path:
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(
            "# Header. The schema documentation lives here.\n"
            "#   status  active | dead | moved | disabled\n"
            "\n"
            "boards:\n"
            "  # Why Datadog: NYC HQ, and its location strings are the messiest\n"
            "  # available, which is useful for a project whose first invariant\n"
            "  # is about not fabricating locations.\n"
            "  - company: Datadog\n"
            "    ats: greenhouse\n"
            "    token: datadog\n"
            "    added: 2026-07-29\n"
            "    verified_at: 2026-07-29\n"
            "    status: active\n"
            "    nyc_presence: true\n"
            "\n"
            "  # Disabled until the closure state machine lands.\n"
            "  - company: Stripe\n"
            "    ats: greenhouse\n"
            "    token: stripe\n"
            "    added: 2026-07-29\n"
            "    verified_at: 2026-07-29\n"
            "    status: disabled\n"
            "    nyc_presence: true\n"
        )
        return registry

    def test_every_existing_byte_survives(self, tmp_path: Path) -> None:
        """The strongest statement of "additive": the old file is a prefix of
        the new one. Not "the data is equivalent" — identical bytes."""
        registry = self._registry_with_comments(tmp_path)
        before = registry.read_text()

        count, _ = promote(
            CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY
        )
        after = registry.read_text()

        assert count == 1
        assert after.startswith(before), "promotion must append, never rewrite"

    def test_the_rationale_between_entries_survives(self, tmp_path: Path) -> None:
        """Named specifically rather than checked by length, so a future
        renderer that preserves *some* comments still fails here."""
        registry = self._registry_with_comments(tmp_path)
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)
        after = registry.read_text()

        assert "Why Datadog" in after
        assert "Disabled until the closure state machine lands." in after
        assert "not fabricating locations" in after

    def test_existing_dates_are_not_requoted(self, tmp_path: Path) -> None:
        """A round trip parses `2026-07-29` into a date and dumps it back
        unquoted, while new entries were written as strings — leaving one file
        with two conventions and a diff full of unrelated churn."""
        registry = self._registry_with_comments(tmp_path)
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)

        assert "added: 2026-07-29\n" in registry.read_text()

    def test_the_result_still_parses_as_yaml(self, tmp_path: Path) -> None:
        """Appending text rather than dumping a document means the renderer has
        to produce valid YAML by itself. Prove it round-trips."""
        registry = self._registry_with_comments(tmp_path)
        promote(
            CandidateFile(candidates=(_candidate(company_name="Acme"),)),
            registry_path=registry,
            today=TODAY,
        )

        loaded = yaml.safe_load(registry.read_text())
        assert [b["token"] for b in loaded["boards"]] == ["datadog", "stripe", "acme"]
        assert loaded["boards"][-1]["company"] == "Acme"
        assert loaded["boards"][-1]["status"] == "active"

    def test_a_disabled_board_stays_disabled(self, tmp_path: Path) -> None:
        """The property the whole file exists to protect. Appending must not
        re-enable a board a human turned off."""
        registry = self._registry_with_comments(tmp_path)
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)

        loaded = yaml.safe_load(registry.read_text())
        stripe = next(b for b in loaded["boards"] if b["token"] == "stripe")
        assert stripe["status"] == "disabled"

    @pytest.mark.parametrize(
        "name",
        [
            "O'Reilly Media",
            "Acme: The Company",
            'Say "Hello"',
            "Foo #1",
            "Bar & Co, Inc.",
            "Café Ltd",
            "- leading dash",
            "{braces}",
        ],
    )
    def test_an_awkward_company_name_cannot_corrupt_the_file(
        self, tmp_path: Path, name: str
    ) -> None:
        """Rendering text by hand makes quoting this function's problem. A
        company name is provider-supplied data, and a colon or an apostrophe in
        one must not be able to break the file that decides what gets polled.
        """
        registry = self._registry_with_comments(tmp_path)
        promote(
            CandidateFile(candidates=(_candidate(company_name=name),)),
            registry_path=registry,
            today=TODAY,
        )

        loaded = yaml.safe_load(registry.read_text())
        assert loaded["boards"][-1]["company"] == name

    def test_nothing_is_written_when_nothing_is_approved(self, tmp_path: Path) -> None:
        """A no-op run must leave the working tree clean, so nobody is asked to
        review an empty diff."""
        registry = self._registry_with_comments(tmp_path)
        before = registry.read_text()

        count, _ = promote(
            CandidateFile(candidates=(_candidate(verdict=Verdict.EMPTY, company_name=None),)),
            registry_path=registry,
            today=TODAY,
        )

        assert count == 0
        assert registry.read_text() == before

    def test_promoting_twice_adds_the_board_once(self, tmp_path: Path) -> None:
        """Idempotence across separate invocations: the second run sees the
        board already present and appends nothing."""
        registry = self._registry_with_comments(tmp_path)
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)
        after_first = registry.read_text()

        count, _ = promote(
            CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY
        )

        assert count == 0
        assert registry.read_text() == after_first

    def test_a_file_with_no_trailing_newline_still_appends_cleanly(self, tmp_path: Path) -> None:
        """An editor that strips the final newline must not produce a file whose
        last existing line and first new line run together."""
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(
            "boards:\n"
            "  - company: Datadog\n"
            "    ats: greenhouse\n"
            "    token: datadog\n"
            "    added: 2026-07-29\n"
            "    status: active\n"
            "    nyc_presence: true"  # no trailing newline, deliberately
        )
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)

        loaded = yaml.safe_load(registry.read_text())
        assert len(loaded["boards"]) == 2

    def test_it_matches_the_indentation_the_file_already_uses(self, tmp_path: Path) -> None:
        """YAML accepts list items at column zero and indented under the key,
        but not both in one sequence. The committed registry uses two spaces and
        `yaml.safe_dump` writes zero, so imposing either one corrupts whichever
        file disagrees."""
        flush = tmp_path / "flush.yaml"
        flush.write_text(yaml.safe_dump({"boards": [{"ats": "greenhouse", "token": "datadog"}]}))
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=flush, today=TODAY)
        assert len(yaml.safe_load(flush.read_text())["boards"]) == 2

        indented = tmp_path / "indented.yaml"
        indented.write_text(
            "boards:\n  - ats: greenhouse\n    token: datadog\n    status: active\n"
        )
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=indented, today=TODAY)
        assert len(yaml.safe_load(indented.read_text())["boards"]) == 2

    def test_an_empty_registry_is_written_rather_than_appended_to(self, tmp_path: Path) -> None:
        """`boards: []` is a flow sequence, and block items cannot be appended
        to one. There are no entries to preserve in that case, so writing the
        file is safe — and it is the only case where that is true."""
        registry = tmp_path / "empty.yaml"
        registry.write_text("# Header survives.\nboards: []\n")

        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)

        text = registry.read_text()
        assert "# Header survives." in text
        assert [b["token"] for b in yaml.safe_load(text)["boards"]] == ["acme"]

    def test_a_registry_that_does_not_exist_yet_is_created(self, tmp_path: Path) -> None:
        registry = tmp_path / "brand-new.yaml"

        count, _ = promote(
            CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY
        )

        assert count == 1
        assert [b["token"] for b in yaml.safe_load(registry.read_text())["boards"]] == ["acme"]
