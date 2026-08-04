"""The answer key: what each corpus posting *requires*, as a human read it.

`docs/architecture/matching.md` §3.1 decided this labels the posting rather than
a verdict for a particular person. A verdict bakes in a graduation date and an
authorization status, both of which change; when they change every label goes
silently wrong while continuing to pass.

Nothing here imports the ORM. The answer key is fixture data and the grader is a
test — neither may reach the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# NOTE: `parents[2]` from this file (nightshift/domain/eligibility_labels.py) is
# services/api — that is where tests/fixtures/eligibility/labels.yaml lives.
# parents[3] would land one directory too high, at services/. Verified by hand
# per CLAUDE.md's warning about off-by-one parents[N] mistakes in this repo.
ANSWER_KEY_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "eligibility" / "labels.yaml"
)

#: The sentinel `make_label_worksheet.py` writes into every blank field.
UNLABELED = "TO_LABEL"

_DEGREE_BASE = ("none", "bachelors", "masters", "phd")
DEGREE_VALUES: frozenset[str] = frozenset(
    [*_DEGREE_BASE, *(f"{d}+equivalent" for d in _DEGREE_BASE)]
)


class PostingLabel(BaseModel):
    """One posting's stated requirements. Never a verdict about a person."""

    model_config = ConfigDict(frozen=True)

    title: str
    is_internship: Literal["yes", "no", "unclear"]
    graduation_window: str
    enrollment_required: Literal["yes", "no", "not_stated"]
    degree: str
    min_years_experience: int | None = None
    required_tech: list[str] = Field(default_factory=list)
    mentioned_not_required: list[str] = Field(default_factory=list)
    sponsorship: Literal["offered", "not_offered", "not_stated"]
    note: str = ""

    @property
    def has_degree_equivalence(self) -> bool:
        """A13's escape hatch. Must resolve to `uncertain`, never `ineligible`."""
        return self.degree.endswith("+equivalent")

    @model_validator(mode="after")
    def _check(self) -> PostingLabel:
        if self.degree not in DEGREE_VALUES:
            raise ValueError(f"degree {self.degree!r} not in {sorted(DEGREE_VALUES)}")
        overlap = {t.casefold() for t in self.required_tech} & {
            t.casefold() for t in self.mentioned_not_required
        }
        if overlap:
            raise ValueError(
                f"{sorted(overlap)} is in both required_tech and "
                "mentioned_not_required; a metric computed against that scores "
                "either answer as correct"
            )
        return self


class AnswerKey(BaseModel):
    boards: dict[str, dict[str, PostingLabel]]


def unlabeled(key_text: str) -> list[str]:
    """Every field still reading TO_LABEL, as `board/posting/field`, sorted.

    Reads the raw YAML rather than the parsed model on purpose: `TO_LABEL` is a
    valid string and several fields are typed `str`, so a partly-filled key
    parses cleanly. This is the only thing that can tell the difference.
    """
    raw: dict[str, Any] = yaml.safe_load(key_text) or {}
    missing: list[str] = []
    for board, postings in (raw.get("boards") or {}).items():
        for posting_id, label in (postings or {}).items():
            for field, value in (label or {}).items():
                if value == UNLABELED:
                    missing.append(f"{board}/{posting_id}/{field}")
    return sorted(missing)


def _coerce(label: dict[str, Any]) -> dict[str, Any]:
    """`not_stated` is how a human writes "the posting does not say"."""
    out = dict(label)
    if out.get("min_years_experience") in ("not_stated", "", None):
        out["min_years_experience"] = None
    return out


def load_answer_key(path: Path | None = None) -> AnswerKey:
    raw = yaml.safe_load((path or ANSWER_KEY_PATH).read_text()) or {}
    boards = {
        board: {
            pid: PostingLabel.model_validate(_coerce(label))
            for pid, label in (postings or {}).items()
        }
        for board, postings in (raw.get("boards") or {}).items()
    }
    return AnswerKey(boards=boards)
