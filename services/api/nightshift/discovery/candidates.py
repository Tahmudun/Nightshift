"""Reading and writing `data/board-candidates.yaml`.

Pure file work — no network, no database. The file is committed and a human
reads it as a git diff, which is why everything here sorts deterministically:
an unordered write reshuffles the whole file on every run, and a diff nobody
can read is a review step that becomes a rubber stamp.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from nightshift.discovery.models import Candidate, CandidateFile

# services/api/nightshift/discovery/candidates.py -> repo root, the same
# arithmetic `domain/registry.py` does from the same depth.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PATH = _REPO_ROOT / "data" / "board-candidates.yaml"

_HEADER = """\
# Discovered board candidates — written by `make discover`, read by
# `make registry-approve`. Committed on purpose: the diff is the review.
#
# NOTHING HERE IS IN THE REGISTRY YET. Promotion happens only when a human runs
# `make registry-approve`, and only `live_named` candidates are promoted in
# bulk (ADR 0005). Everything else waits for individual attention.
#
# No candidate is ever deleted by the pipeline. `empty` means a live board with
# no open roles and `unreachable` means we could not check — neither is
# evidence the board is worthless, and both become approvable the moment they
# return named postings.
"""


def load_candidates(path: Path | None = None) -> CandidateFile:
    """Read the candidate file. A missing file is empty, not an error."""
    target = path or DEFAULT_PATH
    if not target.exists():
        return CandidateFile()
    raw = yaml.safe_load(target.read_text()) or {}
    return CandidateFile.model_validate(raw)


def save_candidates(file: CandidateFile, path: Path | None = None) -> None:
    """Write the candidate file, sorted by (ats, token)."""
    target = path or DEFAULT_PATH
    ordered = sorted(file.candidates, key=lambda candidate: candidate.key)
    payload = {
        "candidates": [
            candidate.model_dump(mode="json", exclude_none=True) for candidate in ordered
        ]
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _HEADER + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=88)
    )


def merge_candidate(file: CandidateFile, candidate: Candidate) -> CandidateFile:
    """Insert or update by ``(ats, token)``, preserving the original discovery date.

    Update rather than append: appending would grow the file without bound and
    make the approval report count one board several times. ``first_seen`` is
    when we found it, not when we last looked at it.
    """
    existing = {item.key: item for item in file.candidates}
    previous = existing.get(candidate.key)
    if previous is not None:
        candidate = candidate.model_copy(update={"first_seen": previous.first_seen})
    existing[candidate.key] = candidate
    return CandidateFile(candidates=tuple(sorted(existing.values(), key=lambda c: c.key)))
