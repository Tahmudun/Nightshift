"""What this system can see, and — the part that matters — what it cannot.

`board-discovery.md` §11: *a missing coverage number is worse than a low one*.
The M1 acceptance criterion is not that a coverage page exists, nor that it
reports a high number. It is that the page **names what is not covered**. So
the blind spots below are a committed, enumerated list rather than something
assembled from whatever happened to be measurable.

Two rules hold everything here together.

**There is no denominator.** Nobody knows how many tech jobs open in New York,
so no function here returns a percentage of the market. A number like "we cover
73% of NYC tech hiring" would be arithmetic performed on a figure nobody has —
the confident-sounding fabrication I6 exists to prevent. The page reports what
it counted and names what it could not.

**`count=None` is a feature.** For most of these gaps the size is genuinely
unknown: we cannot count the NYC employers using Workday without enumerating
NYC employers, which is the problem we are trying to solve. Reporting `0` there
would be a lie of exactly the kind this module exists to avoid, so the count is
`None` and the page renders the word "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass

from nightshift.discovery.models import CandidateFile, Verdict
from nightshift.domain.registry import BoardRegistry, BoardStatus


@dataclass(frozen=True)
class BlindSpot:
    """One thing this system cannot see, and why."""

    id: str
    title: str
    explanation: str
    #: None when the size of the gap is genuinely unknown. Never 0 as a stand-in.
    count: int | None = None


@dataclass(frozen=True)
class CoverageSummary:
    boards_total: int
    boards_pollable: int
    boards_by_ats: dict[str, int]
    boards_by_status: dict[str, int]
    boards_with_nyc_presence: int
    candidates_by_verdict: dict[str, int]
    candidates_total: int
    blind_spots: list[BlindSpot]


#: The gaps that exist regardless of how discovery went. Each is structural —
#: a reason this system cannot see something — rather than a backlog item, and
#: each says which. "We have not got round to it" and "this is impossible by
#: the provider's own rules" are different disclosures and read differently to
#: somebody deciding whether to trust the corpus.
STRUCTURAL_BLIND_SPOTS: tuple[BlindSpot, ...] = (
    BlindSpot(
        id="lever_undiscovered",
        title="Lever boards cannot be discovered from the crawl archive",
        explanation=(
            "jobs.lever.co/robots.txt disallows CCBot, the Common Crawl crawler, so no "
            "Lever job page is in the archive and none ever will be (ADR 0006). This is "
            "not a backlog item — the archive is structurally blind here. Lever boards "
            "have to be found by probing an employer's own careers page, which needs a "
            "list of employer domains this repository does not yet have. Lever boards "
            "therefore enter the registry only by hand."
        ),
    ),
    BlindSpot(
        id="workday_icims_taleo",
        title="Workday, iCIMS and Taleo are not read at all",
        explanation=(
            "Three large enterprise applicant-tracking systems, deliberately deferred "
            "past this milestone (board-discovery.md §2). No adapter exists, so every "
            "opening at an employer using one is invisible to this system — including, "
            "disproportionately, big banks, insurers and older institutions, which is "
            "much of New York's employment. The size of this gap is unknown: counting "
            "it would mean enumerating NYC employers, which is the problem itself."
        ),
    ),
    BlindSpot(
        id="no_public_board",
        title="Employers with no public job board",
        explanation=(
            "Roles filled through referrals, recruiters, university pipelines or a "
            "hiring manager's inbox never appear on any board and are unreachable by "
            "any amount of discovery. This system can only see hiring that was "
            "published somewhere machine-readable, and a meaningful share of early- "
            "career hiring in New York is not."
        ),
    ),
    BlindSpot(
        id="aggregator_only",
        title="Postings that exist only on an aggregator",
        explanation=(
            "LinkedIn and Indeed are rejected as sources with reasons recorded in "
            "board-discovery.md §9 — their terms forbid it and their listings cannot be "
            "traced to a first-party record, which would break the guarantee that every "
            "canonical job traces to a raw source record. A role posted only there is "
            "one this system will not carry."
        ),
    ),
    BlindSpot(
        id="own_careers_system",
        title="Employers running their own careers system",
        explanation=(
            "Meta, Apple, Google, Amazon, Microsoft and Bloomberg do not use "
            "Greenhouse, Lever or Ashby. Each runs a bespoke careers site with no "
            "public API, so every opening at them is invisible here. Probed "
            "2026-08-04: `meta`, `facebook`, `metaplatforms` and `apple` return 404 "
            "across all three provider endpoints, twelve of twelve. This is not the "
            "Workday gap above — those are three shared enterprise systems one "
            "adapter could read; these are one-off sites, one per employer. "
            "Two different situations sit inside this row and they are different "
            "disclosures. Meta's robots.txt prohibits automated collection without "
            "written permission and Google's disallows its job results by name, so "
            "both are refused sources under the first-party-only rule and no future "
            "milestone changes that. Amazon's robots.txt disallows only /internal "
            "and jobs.apple.com serves none at all; neither refuses. Those two are "
            "simply not built, which is a decision still open rather than one "
            "already made against us. Whether to read them is a job for a later ADR, "
            "answered per employer rather than per category, and robots.txt is not "
            "the terms of service — those need reading separately."
        ),
    ),
)


def coverage_summary(*, candidates: CandidateFile, registry: BoardRegistry) -> CoverageSummary:
    """Count what is known and attach the list of what is not.

    Every count here is of something this system actually holds — registry rows
    and candidate rows. None of them is an estimate of the world.
    """
    by_ats: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for board in registry.boards:
        by_ats[board.ats] = by_ats.get(board.ats, 0) + 1
        by_status[board.status.value] = by_status.get(board.status.value, 0) + 1

    by_verdict = {
        verdict.value: sum(1 for c in candidates.candidates if c.verdict is verdict)
        for verdict in Verdict
    }

    # Two gaps whose size we *do* know, stated as numbers precisely because the
    # structural ones cannot be. A page where every count reads "unknown"
    # teaches a reader to skip the column.
    measured = (
        BlindSpot(
            id="candidates_awaiting_review",
            title="Discovered boards not yet in the registry",
            explanation=(
                "Boards discovery has found and validated but which no human has "
                "approved. They are not polled and their postings are not in the "
                "corpus. Only a live board whose employer the provider actually named "
                "is eligible for bulk approval (ADR 0005); everything else waits for "
                "individual attention."
            ),
            count=sum(1 for c in candidates.candidates if c.verdict is not Verdict.UNVALIDATED)
            - by_verdict[Verdict.LIVE_NAMED.value],
        ),
        BlindSpot(
            id="candidates_never_probed",
            title="Harvested tokens nobody has checked yet",
            explanation=(
                "Tokens taken from the crawl index that no provider has been asked "
                "about. A token in a URL archive is not evidence a board exists, so "
                "these are counted separately from boards we tried and failed to "
                "reach — claiming a failure that never happened would misreport the "
                "health of the pipeline."
            ),
            count=by_verdict[Verdict.UNVALIDATED.value],
        ),
        BlindSpot(
            id="registry_boards_not_polled",
            title="Registry boards that are not being polled",
            explanation=(
                "Entries marked dead, moved or disabled. They stay in the registry on "
                "purpose (A1) so they surface for review, and their previously-found "
                "jobs keep their state rather than being closed by their absence (I3)."
            ),
            count=sum(1 for b in registry.boards if b.status is not BoardStatus.ACTIVE),
        ),
    )

    return CoverageSummary(
        boards_total=len(registry.boards),
        boards_pollable=len(registry.pollable()),
        boards_by_ats=by_ats,
        boards_by_status=by_status,
        boards_with_nyc_presence=sum(1 for b in registry.boards if b.nyc_presence),
        candidates_by_verdict=by_verdict,
        candidates_total=len(candidates.candidates),
        blind_spots=[*STRUCTURAL_BLIND_SPOTS, *measured],
    )


def format_coverage(summary: CoverageSummary) -> str:
    """The same report as text, for the CLI.

    "What is not covered" comes second and is never abbreviated — it is the
    section the milestone is judged on, and a terminal report that truncated it
    would be the command-line version of hiding it below the fold.
    """
    lines = [
        "COVERED",
        f"  registry boards      {summary.boards_total} "
        f"({summary.boards_pollable} polled, {summary.boards_with_nyc_presence} NYC)",
        f"  by provider          {summary.boards_by_ats or '—'}",
        f"  by status            {summary.boards_by_status or '—'}",
        f"  candidates           {summary.candidates_total}",
    ]
    lines.extend(
        f"    {verdict:<16} {count}"
        for verdict, count in summary.candidates_by_verdict.items()
        if count
    )
    lines += ["", "NOT COVERED"]
    for spot in summary.blind_spots:
        shown = "unknown" if spot.count is None else str(spot.count)
        lines.append(f"  [{shown}] {spot.title}")
        lines.append(f"        {spot.explanation}")
    lines += [
        "",
        "No percentage is reported. There is no denominator: nobody knows how many",
        "tech jobs open in New York, so a coverage percentage would be invented.",
    ]
    return "\n".join(lines)
