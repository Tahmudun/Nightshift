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
from nightshift.domain.companies import normalize_company_name

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
    eligible = [
        candidate
        for candidate in file.candidates
        if candidate.verdict is Verdict.LIVE_NAMED and candidate.key not in registry_tokens
    ]
    colliding = _names_claimed_more_than_once(eligible)
    return sorted(
        (candidate for candidate in eligible if _name_key(candidate) not in colliding),
        key=_review_order,
    )


def _name_key(candidate: Candidate) -> str | None:
    """The candidate's employer identity, or None if it has no usable one.

    Same normalisation the validator uses for the registry collision check, so
    the two cannot disagree about whether two names are one employer.
    """
    if not candidate.company_name:
        return None
    try:
        return normalize_company_name(candidate.company_name)
    except ValueError:
        return None


def _names_claimed_more_than_once(candidates: list[Candidate]) -> set[str]:
    """Employer names claimed by two or more candidates in the same batch.

    The `name_collision` verdict is decided at validation time against names
    already in the **registry**, so it cannot see two candidates in the *same
    batch* naming one employer — and that is not hypothetical. The recorded
    crawl slice yields both `Abridge` and `abridge`: two Ashby tokens, one
    employer, 42 postings each. Promoting both would put two rows in the
    registry for one company, poll the same board twice, and hand dedupe 42
    duplicate jobs to merge back together.

    Neither side wins. Both are held, because whether these are one employer
    with two board slugs or two genuinely different companies is exactly the
    judgement ADR 0005 reserves for a human.
    """
    seen: dict[str, int] = {}
    for candidate in candidates:
        key = _name_key(candidate)
        if key is not None:
            seen[key] = seen.get(key, 0) + 1
    return {name for name, count in seen.items() if count > 1}


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

    **Literally appended**, not rewritten. Existing bytes are untouched, so the
    old file is a prefix of the new one and the diff a human reviews is pure
    additions — which is what ADR 0005's batch approval assumes it is reviewing.

    That wording used to be aspirational. Until M1d this function rebuilt the
    document with ``yaml.safe_dump``, which cannot round-trip comments: it was
    additive in the *data* and destructive of everything a human had written
    down. The first real ``--write`` in this project's history deleted ten lines
    of rationale from between the entries, including a note on the ``Stripe``
    entry reading "enable once the freshness and closure state machine lands" —
    a message to the milestone that eventually read it, deleted by approving
    nineteen unrelated boards. ``_leading_comment`` had saved the header, so the
    limitation was known; only the consequence was not.

    ``dead`` and ``disabled`` entries survive for free now, rather than by being
    carefully re-serialised — A1 keeps those in the file so they surface on the
    source health page. An existing ``(ats, token)`` still counts as present, so
    discovery re-finding a disabled board adds nothing rather than overruling
    the human who disabled it.

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

    indent = _sequence_indent(text)
    rendered = "".join(
        _render_entry(_entry_for(candidate, today), indent) for candidate in approved
    )

    if not boards:
        # An empty or absent registry. There is nothing between entries to
        # preserve, and appending block items after `boards: []` — the shape
        # `yaml.safe_dump` writes for an empty list — is not valid YAML. So this
        # one case writes the file rather than extending it, keeping whatever
        # header comment was there.
        target.write_text(_leading_comment(text) + "boards:\n" + rendered.lstrip("\n"))
        return len(approved), approved

    with target.open("a", encoding="utf-8") as handle:
        # An editor that strips the final newline would otherwise run the last
        # existing line into the first new one.
        if text and not text.endswith("\n"):
            handle.write("\n")
        handle.write(rendered)

    return len(approved), approved


def _entry_for(candidate: Candidate, today: date) -> dict[str, Any]:
    """One registry entry, in the field order the file already uses."""
    return {
        "company": candidate.company_name,
        "ats": candidate.ats,
        "token": candidate.token,
        "added": today.isoformat(),
        "verified_at": candidate.last_validated.isoformat(),
        "status": "active",
        # Derived from the postings the validator actually parsed, not asserted
        # by hand. board-discovery.md §16 expects this field to be deleted now
        # that M1d computes tiers from the database; nothing in the polling path
        # reads it, and a test asserts that.
        "nyc_presence": candidate.nyc_posting_count > 0,
        "notes": (
            f"Discovered by {candidate.source} and approved in bulk on "
            f"{today.isoformat()} (ADR 0005). {candidate.posting_count} posting(s) "
            f"at validation, {candidate.nyc_posting_count} naming NYC."
        ),
    }


def _sequence_indent(text: str) -> str:
    """How far the existing file indents its list items, verbatim.

    YAML accepts both ``- company:`` at column zero and ``  - company:`` under
    the key, but **not both in one sequence** — mixing them is a parse error.
    The hand-written registry uses two spaces; ``yaml.safe_dump`` writes zero.
    Rather than pick one and corrupt whichever file disagrees, match what is
    already there.

    Two spaces when the file has no list items yet to copy from, because that is
    what the committed registry uses and what a human editing it will expect.
    """
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("- ") and not stripped.startswith("- #"):
            return line[: len(line) - len(stripped)]
    return "  "


def _render_entry(entry: dict[str, Any], indent: str = "  ") -> str:
    """Render one board as YAML text, to be appended to the file as it stands.

    **Appending rather than re-dumping the document is the whole point.**
    ``yaml.safe_dump`` cannot round-trip comments, and the registry's rationale
    lives in them — including, when this was written, a note on the ``Stripe``
    entry addressed to the milestone that eventually read it. Rewriting the file
    deleted that quietly, on the first real run, while the docstring above still
    said "additive, never destructive". It was additive in the data and
    destructive in everything a human had written down.

    The cost of appending is that quoting becomes this function's problem, so
    every scalar goes through ``yaml.safe_dump`` rather than an f-string. A
    company name is provider-supplied text: an apostrophe, a colon, a leading
    dash or a ``#`` must not be able to corrupt the file that decides which
    boards get polled.
    """
    lines = ["\n"]
    for index, (key, value) in enumerate(entry.items()):
        scalar = yaml.safe_dump(
            value, default_flow_style=True, width=10**6, allow_unicode=True
        ).strip()
        if scalar.endswith("..."):
            # safe_dump of a bare scalar can append a document-end marker.
            scalar = scalar[:-3].strip()
        prefix = f"{indent}- " if index == 0 else f"{indent}  "
        lines.append(f"{prefix}{key}: {scalar}\n")
    return "".join(lines)
