"""Promote reviewed candidates into the board registry (ADR 0005).

Pure file work. No network, no database, and — asserted by a test — no version
control. A1 says nothing writes to `board-registry.yaml` automatically; this
module is run by a human typing a command, and the human reads the resulting
diff and commits it themselves. An approval step that commits on their behalf
is not a review.

Only `live_named` candidates are promoted in bulk. `live_unnamed`,
`name_collision`, `empty` and `unreachable` are held for individual attention
and stay in the candidate file, where the next discovery run re-validates them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from nightshift.discovery.models import Candidate, CandidateFile, Verdict

# services/api/nightshift/discovery/approve.py -> repo root, matching the
# arithmetic domain/registry.py does from the same depth.
DEFAULT_REGISTRY = Path(__file__).resolve().parents[4] / "data" / "board-registry.yaml"


def approvable(
    file: CandidateFile, *, registry_tokens: frozenset[tuple[str, str]]
) -> list[Candidate]:
    """Candidates eligible for bulk promotion, NYC-producing boards first.

    The verdict check is the gate. It is deliberately a single equality against
    `LIVE_NAMED` rather than a set of exclusions: a new verdict added later
    defaults to *not* approvable, which is the safe direction.

    `registry_tokens` holds `(ats, token)` pairs, not bare tokens — `ramp` is a
    real board on both Lever and Ashby, and comparing tokens alone would hold a
    genuinely different employer's board forever.
    """
    return sorted(
        (
            candidate
            for candidate in file.candidates
            if candidate.verdict is Verdict.LIVE_NAMED and candidate.key not in registry_tokens
        ),
        key=_review_order,
    )


def _review_order(candidate: Candidate) -> tuple[int, str]:
    """NYC-producing boards first, then alphabetically by employer.

    Shared by `approvable` and `approval_report` so the list a human reads and
    the list that gets promoted cannot drift into two different orders.
    """
    return (-candidate.nyc_posting_count, candidate.company_name or "")


#: Wide enough for the longest real employer name seen so far, narrow enough
#: that a line still fits a standard terminal. Names are truncated rather than
#: allowed to overflow, because an overflowing name pushes the token out of
#: alignment and the token is the thing a human is actually checking.
_NAME_WIDTH = 34
_TOKEN_WIDTH = 26


def approval_report(candidates: list[Candidate]) -> str:
    """A human-readable summary, ordered so review effort lands where it matters.

    Boards that produced an NYC posting come first (board-discovery.md §6), so
    the tail can be skimmed rather than read. The ordering is applied here
    rather than assumed of the caller: the header says "NYC-producing first",
    and a report that says so while listing something else is worse than one
    that does not say it. An empty list says so in words — a blank output
    reads as a crash.
    """
    if not candidates:
        return "no candidates are eligible for bulk approval"

    lines = [
        f"{len(candidates)} candidate(s) eligible for bulk approval, NYC-producing first:",
        "",
        f"{'employer':<{_NAME_WIDTH}} {'ats':<11} {'token':<{_TOKEN_WIDTH}} "
        f"{'posts':>6} {'nyc':>5}  verdict",
    ]
    lines.extend(
        f"{(candidate.company_name or ''):<{_NAME_WIDTH}.{_NAME_WIDTH}} {candidate.ats:<11} "
        f"{candidate.token:<{_TOKEN_WIDTH}.{_TOKEN_WIDTH}} {candidate.posting_count:>6} "
        f"{candidate.nyc_posting_count:>5}  {candidate.verdict.value}"
        for candidate in sorted(candidates, key=_review_order)
    )
    return "\n".join(lines)


def _leading_comment(text: str) -> str:
    """The comment block at the top of the registry file, verbatim.

    `yaml.safe_dump` cannot round-trip comments, and the registry's header is
    the only place the rules about `dead` entries and the meaning of
    `verified_at` are written down. Rewriting the file without it would delete
    the documentation of the file being edited — quietly, on the first run.
    """
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#") or not line.strip():
            kept.append(line)
        else:
            break
    return "".join(kept)


def promote(
    file: CandidateFile, *, registry_path: Path | None = None, today: date
) -> tuple[int, list[Candidate]]:
    """Append approved candidates to the registry. Additive, never destructive.

    Existing entries are read and rewritten unchanged, including `dead` and
    `disabled` ones — A1 keeps those in the file so they surface on the source
    health page. Rebuilding the registry from candidates alone would delete
    curated history and silently un-disable boards a human had turned off; and
    because an existing `(ats, token)` is treated as already present, discovery
    re-finding a disabled board adds nothing rather than overruling the human.

    Writes nothing at all when there is nothing to approve, so the working tree
    stays clean after a no-op run and nobody is asked to review an empty diff.
    """
    target = registry_path or DEFAULT_REGISTRY
    text = target.read_text() if target.exists() else ""
    raw = yaml.safe_load(text) if text else {}
    boards: list[dict[str, Any]] = list((raw or {}).get("boards") or [])
    existing = {(str(entry.get("ats")), str(entry.get("token"))) for entry in boards}

    approved = approvable(file, registry_tokens=frozenset(existing))
    if not approved:
        return 0, []

    for candidate in approved:
        boards.append(
            {
                "company": candidate.company_name,
                "ats": candidate.ats,
                "token": candidate.token,
                "added": today.isoformat(),
                "verified_at": candidate.last_validated.isoformat(),
                "status": "active",
                # Derived from the postings the validator actually parsed, not
                # asserted by hand. board-discovery.md §16 expects this field to
                # be deleted once M1d computes tiers from the database.
                "nyc_presence": candidate.nyc_posting_count > 0,
                "notes": (
                    f"Discovered by {candidate.source} and approved in bulk on "
                    f"{today.isoformat()} (ADR 0005). {candidate.posting_count} posting(s) "
                    f"at validation, {candidate.nyc_posting_count} naming NYC."
                ),
            }
        )

    target.write_text(
        _leading_comment(text)
        + yaml.safe_dump({"boards": boards}, sort_keys=False, allow_unicode=True, width=88)
    )
    return len(approved), approved
