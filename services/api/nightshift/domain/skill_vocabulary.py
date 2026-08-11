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
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
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
        self,
        *,
        version: str,
        terms: list[_Term],
        canonical_names: tuple[str, ...],
        demonstrates: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.version = version
        self.canonical_names = canonical_names
        self._demonstrates = demonstrates or {}
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

    @property
    def edges(self) -> Mapping[str, tuple[str, ...]]:
        """Every ontology edge at once, for a scorer that reads them all.

        Read-only: the scorer receives the vocabulary's own dictionary, and a
        caller that could mutate it would be editing the taxonomy for every
        other caller in the process, `load_vocabulary` being cached.
        """
        return MappingProxyType(self._demonstrates)

    def demonstrated_by(self, canonical_name: str) -> tuple[str, ...]:
        """The tools whose confirmed presence demonstrates ``canonical_name``.

        ADR 0018's ontology edge, and the alternative it was chosen over is the
        reason for its shape: a cosine score between two technology names
        measures topical relatedness, and ranks `Java` beside Python above
        `Machine Learning` beside PyTorch. This is a claim a human wrote into a
        versioned file and can be argued with in a pull request.

        **One hop, never a chain.** If A is demonstrated by B and B by C, C does
        not demonstrate A. Nothing here recurses, and
        `test_the_edge_is_one_hop_and_does_not_chain` is why it must not start:
        two edges written independently, each defensible, compose into a claim
        nobody made.

        Empty for a name the vocabulary carries no edge for, and for a name it
        has never heard of — those are the same answer on purpose, because a
        concept with no tools listed and a typo are indistinguishable *here* and
        `parse_vocabulary` is where the typo is caught.
        """
        return self._demonstrates.get(canonical_name, ())

    def canonical(self, term: str) -> str:
        """This vocabulary's name for ``term``, or ``term`` when it has none.

        **Only a match spanning the whole term counts**, and that restriction is
        the design rather than an optimisation. ``match_all`` finds vocabulary
        terms anywhere inside a string, so a substring rule would resolve
        ``Entra ID/Azure AD`` to ``Azure`` — it does contain the word — and
        quietly merge Microsoft's identity product into its cloud platform.
        Measured over the answer key, the substring rule collapses two distinct
        labels into one on ``akunacapital/8047104``; this one collapses none.

        A term the vocabulary has never heard of comes back unchanged, so a
        vocabulary gap stays visible instead of being resolved into a neighbour.

        This lived in `test_requirement_extraction_against_the_answer_key.py`
        until M3b Task 11, when the skill filter needed the same resolution in
        production. Leaving a copy behind would let the filter and the grader
        disagree about whether ``GCP`` and ``Google Cloud`` are the same
        technology — which is precisely the defect M3a.1 opened with, one layer
        down.
        """
        for hit in self.match_all(term):
            if hit.char_start == 0 and hit.char_end == len(term):
                return hit.canonical_name
        return term

    def match_all(self, text: str) -> list[SkillMatch]:
        """Every non-overlapping vocabulary term, including repeats.

        The difference from :meth:`match` is deliberate and load-bearing. That
        one keeps the first occurrence per name, which is right for a resume:
        one person, one skill, one span to confirm. A job posting is the other
        case — the same technology under "about us" and again under "what
        you'll need" is two different claims, and which section it sits in is
        the whole question (``matching.md`` §4.1). Collapsing them would answer
        that question with whichever came first.
        """
        claimed: list[tuple[int, int]] = []
        found: list[SkillMatch] = []
        for term in self._terms:
            for hit in term.pattern.finditer(text):
                start, end = hit.span()
                if any(
                    start < taken_end and taken_start < end for taken_start, taken_end in claimed
                ):
                    continue
                claimed.append((start, end))
                found.append(
                    SkillMatch(canonical_name=term.canonical_name, char_start=start, char_end=end)
                )
        return sorted(found, key=lambda match: (match.char_start, match.canonical_name))


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
    demonstrates: dict[str, tuple[str, ...]] = {}
    for entry in raw["skills"]:
        name = str(entry["name"])
        canonical.append(name)
        tools = tuple(str(tool) for tool in entry.get("demonstrated_by", []))
        if tools:
            if name in tools:
                raise ValueError(f"{name!r} cannot demonstrate itself")
            demonstrates[name] = tools
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
    # After the loop, because an edge may name a tool declared further down the
    # file and reading order is not a constraint anybody should have to know.
    known = set(canonical)
    for concept, tools in demonstrates.items():
        unknown = [tool for tool in tools if tool not in known]
        if unknown:
            raise ValueError(
                f"{concept!r} is demonstrated_by {unknown!r}, which "
                "this vocabulary does not carry — a name that resolves to "
                "nothing is an edge that silently never fires"
            )

    return SkillVocabulary(
        version=version,
        terms=terms,
        canonical_names=tuple(canonical),
        demonstrates=demonstrates,
    )


@lru_cache(maxsize=4)
def load_vocabulary(path: Path | None = None) -> SkillVocabulary:
    """Cached: the file is source data and does not change inside a process."""
    resolved = path or DEFAULT_VOCABULARY_PATH
    return parse_vocabulary(yaml.safe_load(resolved.read_text(encoding="utf-8")))
