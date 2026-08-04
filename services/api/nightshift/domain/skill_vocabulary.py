"""The committed skill vocabulary, and the matcher that reads it.

``command-center.md`` §6.1: a resume may propose a skill only when the term
matches this file exactly or by alias. Never free text. That rule is what makes
"the extractor proposed Python" checkable rather than a matter of trust.

Two precision rules, both deliberate, both costing recall:

* **Word boundaries.** "github.com" does not contain the skill Git.
* **Case sensitivity for skills that are also English words.** "Go", "Rust",
  "Express", "Excel" and "R" match only in the case the vocabulary declares. A
  resume written entirely in lower case loses those, and a lost skill is one
  click away on the manual form — a fabricated one is an invariant violation.

Nothing here reads a resume or writes a row. It answers one question: where in
this string does a known skill appear?
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# `parents[4]`, matching `domain/registry.py`. `parents[3]` is `services/`, and
# the resulting path resolves to nothing — which is a crash in the best case and
# a silently empty vocabulary in the worst. M1c's plan made the same mistake.
DEFAULT_VOCABULARY_PATH = Path(__file__).resolve().parents[4] / "data" / "skills.yaml"

#: A one-character term matches half of everything. Only entries that opt in
#: with ``minimum_length_override: true`` may be this short, and they must also
#: be case-sensitive — "R" is a language, "r" is a letter.
_MINIMUM_TERM_LENGTH = 2


@dataclass(frozen=True, slots=True)
class SkillMatch:
    canonical_name: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class _Term:
    canonical_name: str
    pattern: re.Pattern[str]
    length: int


class SkillVocabulary:
    def __init__(
        self, *, version: str, terms: list[_Term], canonical_names: tuple[str, ...]
    ) -> None:
        self.version = version
        self.canonical_names = canonical_names
        # Longest first: "Machine Learning" must win over any term inside it,
        # and "PostgreSQL" over its own alias "postgres".
        self._terms = sorted(terms, key=lambda term: term.length, reverse=True)

    def match(self, text: str) -> list[SkillMatch]:
        """Every non-overlapping vocabulary term in ``text``, in reading order.

        One match per canonical name — the first occurrence. A resume listing
        Python four times has one Python skill, and the span points at the first
        place it can be shown to the person confirming it.
        """
        claimed: list[tuple[int, int]] = []
        found: dict[str, SkillMatch] = {}
        for term in self._terms:
            for hit in term.pattern.finditer(text):
                start, end = hit.span()
                if any(
                    start < taken_end and taken_start < end for taken_start, taken_end in claimed
                ):
                    continue
                claimed.append((start, end))
                if term.canonical_name not in found:
                    found[term.canonical_name] = SkillMatch(
                        canonical_name=term.canonical_name, char_start=start, char_end=end
                    )
        return sorted(found.values(), key=lambda match: (match.char_start, match.canonical_name))


def _compile(term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    # `\b` is wrong beside a non-word character: `\bC++\b` can never match,
    # because there is no word boundary after `+`. Lookarounds on word
    # characters do the same job for every term shape, punctuation included.
    escaped = re.escape(term)
    pattern = rf"(?<![0-9A-Za-z_]){escaped}(?![0-9A-Za-z_])"
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def parse_vocabulary(raw: dict[str, Any]) -> SkillVocabulary:
    """Build a vocabulary from already-loaded YAML. Raises on a sloppy entry."""
    version = str(raw["version"])
    terms: list[_Term] = []
    canonical: list[str] = []
    for entry in raw["skills"]:
        name = str(entry["name"])
        canonical.append(name)
        case_sensitive = bool(entry.get("case_sensitive", False))
        allow_short = bool(entry.get("minimum_length_override", False))
        for term in [name, *(str(alias) for alias in entry.get("aliases", []))]:
            if len(term) < _MINIMUM_TERM_LENGTH:
                if not allow_short:
                    raise ValueError(
                        f"{term!r} is too short to match precisely; declare "
                        "minimum_length_override if it is really a skill"
                    )
                if not case_sensitive:
                    raise ValueError(f"{term!r} is short and must also be case-sensitive")
            terms.append(
                _Term(
                    canonical_name=name,
                    pattern=_compile(term, case_sensitive=case_sensitive),
                    length=len(term),
                )
            )
    return SkillVocabulary(version=version, terms=terms, canonical_names=tuple(canonical))


@lru_cache(maxsize=4)
def load_vocabulary(path: Path | None = None) -> SkillVocabulary:
    """Cached: the file is source data and does not change inside a process."""
    resolved = path or DEFAULT_VOCABULARY_PATH
    return parse_vocabulary(yaml.safe_load(resolved.read_text(encoding="utf-8")))
