"""Loading and validating ``data/board-registry.yaml``.

The registry is source data, so it is validated like anything else crossing a
boundary: a typo in the ATS name or a duplicated token is a startup error naming
the offending entry, not a board that silently never gets polled.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from nightshift.adapters.base import BoardRef

# services/api/nightshift/domain/registry.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "data" / "board-registry.yaml"


class BoardStatus(StrEnum):
    ACTIVE = "active"
    DEAD = "dead"
    MOVED = "moved"
    DISABLED = "disabled"


class BoardEntry(BaseModel):
    """One registry row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(min_length=1)
    ats: Literal["greenhouse", "lever", "ashby"]
    token: str = Field(min_length=1)
    added: date
    verified_at: date | None = None
    status: BoardStatus = BoardStatus.ACTIVE
    nyc_presence: bool = False
    notes: str = ""

    @field_validator("token")
    @classmethod
    def _token_is_url_safe(cls, value: str) -> str:
        """A token goes straight into a URL path; reject anything that could escape it."""
        cleaned = value.strip()
        if not cleaned or not all(ch.isalnum() or ch in "-_." for ch in cleaned):
            raise ValueError(
                f"board token {value!r} must be alphanumeric with - _ . only "
                "(it is interpolated into a request URL)"
            )
        return cleaned

    @property
    def is_pollable(self) -> bool:
        """Only ``active`` entries are polled.

        ``dead`` deliberately stays in the file and out of the poll set: it
        surfaces for human review, and its previously-produced jobs keep their
        state (I3).
        """
        return self.status is BoardStatus.ACTIVE

    def to_ref(self) -> BoardRef:
        return BoardRef(
            company=self.company, ats=self.ats, token=self.token, nyc_presence=self.nyc_presence
        )


class BoardRegistry(BaseModel):
    model_config = ConfigDict(frozen=True)

    boards: tuple[BoardEntry, ...]

    @field_validator("boards")
    @classmethod
    def _tokens_unique_per_ats(cls, boards: tuple[BoardEntry, ...]) -> tuple[BoardEntry, ...]:
        """Two entries for the same board would poll it twice and double-count its jobs."""
        duplicates = [
            key for key, count in Counter((b.ats, b.token) for b in boards).items() if count > 1
        ]
        if duplicates:
            listed = ", ".join(f"{ats}:{token}" for ats, token in duplicates)
            raise ValueError(f"duplicate board entries in registry: {listed}")
        return boards

    def pollable(self, ats: str | None = None) -> list[BoardEntry]:
        """Boards to poll, NYC-presence first (A1: used to prioritise polls).

        Sorted deterministically so an ingestion run is reproducible and a
        failure is always attributable to the same board ordering.
        """
        entries = [b for b in self.boards if b.is_pollable and (ats is None or b.ats == ats)]
        return sorted(entries, key=lambda b: (not b.nyc_presence, b.ats, b.token))

    def by_token(self, ats: str, token: str) -> BoardEntry | None:
        for board in self.boards:
            if board.ats == ats and board.token == token:
                return board
        return None


def load_registry(path: Path | None = None) -> BoardRegistry:
    """Parse and validate the registry file."""
    registry_path = path or DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        raise FileNotFoundError(
            f"board registry not found at {registry_path} — it is source data and must be committed"
        )
    raw = yaml.safe_load(registry_path.read_text()) or {}
    if not isinstance(raw, dict) or "boards" not in raw:
        raise ValueError(f"{registry_path} must contain a top-level 'boards' list")
    return BoardRegistry.model_validate(raw)


@lru_cache(maxsize=1)
def get_registry() -> BoardRegistry:
    """Cached registry for the running process."""
    return load_registry()
