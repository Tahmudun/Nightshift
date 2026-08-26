"""The committed city gazetteer (ADR 0040).

`data/city-gazetteer.tsv` is built by `scripts/build_city_gazetteer.py` from a
GeoNames dump. Every judgement — the population floor, the ambiguity refusals —
was made at build time, so this module does no deciding. It reads a decided
list and answers lookups from it.

Two things it deliberately cannot do:

* **Return a coordinate.** The artifact has no latitude or longitude columns at
  all, so there is nothing here to leak one (I1).
* **Return a country or a state.** A posting that says `London` said `London`.
  Adding "United Kingdom" beside it would infer past the source, which is the
  habit `locations.py` exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_ARTIFACT = Path(__file__).resolve().parents[4] / "data" / "city-gazetteer.tsv"

_STATUS_RESOLVED = "resolved"
_STATUS_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class Gazetteer:
    """A loaded gazetteer: what it will decide, and what it refused to."""

    resolved: dict[str, str]
    ambiguous: frozenset[str]

    def lookup(self, token: str) -> str | None:
        """The display name for a bare token, or None.

        None covers both "not a city we ship" and "a city name too contested to
        choose", and the caller treats them the same way — as `unknown`. The
        difference is kept in `ambiguous` for the coverage page, which reports
        refusals as a number a reader can see rather than a silence.
        """
        return self.resolved.get(token.casefold())

    def refused(self, token: str) -> bool:
        """True where the gazetteer knows this name and declined to decide it."""
        return token.casefold() in self.ambiguous


def _parse(text: str) -> Gazetteer:
    resolved: dict[str, str] = {}
    ambiguous: set[str] = set()
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"malformed gazetteer row: {line!r}")
        key, status, display = parts
        if status == _STATUS_RESOLVED:
            if not display:
                raise ValueError(f"resolved row with no display name: {key!r}")
            resolved[key] = display
        elif status == _STATUS_AMBIGUOUS:
            ambiguous.add(key)
        else:
            raise ValueError(f"unknown gazetteer status {status!r} for {key!r}")
    return Gazetteer(resolved=resolved, ambiguous=frozenset(ambiguous))


@lru_cache(maxsize=1)
def gazetteer() -> Gazetteer:
    """The process-wide gazetteer, read once.

    Loaded eagerly on first use rather than at import so a test can point at a
    different artifact by clearing the cache, and so importing this module
    costs nothing in a process that never resolves a location.
    """
    return _parse(_ARTIFACT.read_text(encoding="utf-8"))


def load_from(path: Path) -> Gazetteer:
    """Read a gazetteer from an explicit path. For tests and the coverage job."""
    return _parse(path.read_text(encoding="utf-8"))
