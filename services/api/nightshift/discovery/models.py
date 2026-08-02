"""What a discovered board looks like before a human has approved it.

The verdicts are the whole design (board-discovery.md §6). Three of them route
to manual attention and two of them are *not rejections* — `empty` and
`unreachable` stay candidates and are re-validated on the next run, because a
company between hiring rounds and a provider having a bad morning are not
evidence that a board is worthless.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Verdict(StrEnum):
    """Exactly one applies to every candidate."""

    #: 200, at least one posting, and the provider told us the employer's name.
    #: The only verdict eligible for bulk approval (ADR 0005).
    LIVE_NAMED = "live_named"
    #: 200 with postings, but no resolvable employer name. Manual review.
    #: `a3c41b8b71eff8c4` is the recorded example and the reason the gate exists.
    LIVE_UNNAMED = "live_unnamed"
    #: The name normalises onto a company already in the registry. Manual review,
    #: because it is either a duplicate or two genuinely different employers.
    NAME_COLLISION = "name_collision"
    #: 200 with zero postings. Authoritative, not an error (ADR 0003).
    EMPTY = "empty"
    #: Non-200, timeout, or unparseable. Says nothing about the board.
    UNREACHABLE = "unreachable"


#: Same rule registry.py applies. The token is interpolated into a provider URL.
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class Candidate(BaseModel):
    """One discovered board, awaiting review."""

    model_config = ConfigDict(frozen=True)

    ats: str
    token: str
    verdict: Verdict
    #: Present only for LIVE_NAMED and NAME_COLLISION, and never derived from
    #: the token — Ashby's `0g` is "0g Labs" (I2).
    company_name: str | None = None
    posting_count: int = Field(default=0, ge=0)
    nyc_posting_count: int = Field(default=0, ge=0)
    first_seen: date
    last_validated: date
    #: Which front-end found it: crawl_index | careers_probe | community.
    source: str
    notes: str | None = None

    @field_validator("token")
    @classmethod
    def _token_is_url_safe(cls, value: str) -> str:
        if not _TOKEN.match(value):
            raise ValueError(f"token is not URL-safe: {value!r}")
        return value

    @model_validator(mode="after")
    def _name_matches_verdict(self) -> Candidate:
        """The approval gate reads `verdict` and trusts `company_name`.

        Letting the two disagree would allow a hand-edited name to sit on an
        unnamed candidate — approvable-looking and still routed to review, or
        worse, the reverse.
        """
        if self.verdict is Verdict.LIVE_NAMED and not self.company_name:
            raise ValueError("live_named requires a company_name")
        if self.verdict is Verdict.LIVE_UNNAMED and self.company_name:
            raise ValueError("live_unnamed must not carry a company_name")
        if self.nyc_posting_count > self.posting_count:
            raise ValueError(
                f"nyc_posting_count {self.nyc_posting_count} exceeds "
                f"posting_count {self.posting_count}"
            )
        return self

    @property
    def key(self) -> tuple[str, str]:
        """Identity. The same token can be a real board on two providers —
        `ramp` is live on both Lever and Ashby."""
        return (self.ats, self.token)


class CandidateFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: tuple[Candidate, ...] = ()
