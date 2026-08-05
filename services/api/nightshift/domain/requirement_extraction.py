"""Reading a job posting for what it can *prove* it asks for.

The mirror of `resume_extraction`, and the same trade: rules, deterministic, no
model, no key. Every proposal carries the character span it came from, so the
job page shows the sentence rather than asking anyone to trust a summary.

The single behaviour worth understanding before changing anything here is
`necessity_at`. A technology under "nice to have" is `preferred` and must never
become a gap — see `docs/architecture/matching.md` §3.2 for the posting that
motivated it.

Nothing here imports the ORM; `test_the_extractor_does_not_import_the_orm` is
what keeps that true.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nightshift.domain.skill_vocabulary import SkillVocabulary, load_vocabulary

#: Bumped whenever the rules change. Stored on every row this module produces.
EXTRACTOR_VERSION = "m3a.1"

RequirementKindName = Literal[
    "degree",
    "graduation_window",
    "years_experience",
    "technology",
    "authorization",
    "enrollment",
    "role_level",
]
NecessityName = Literal["required", "preferred", "mentioned"]


@dataclass(frozen=True)
class RequirementProposal:
    kind: RequirementKindName
    value: str
    raw_text: str
    char_start: int
    char_end: int
    necessity: NecessityName
    has_equivalence: bool = False


#: Headings that open a *required* block. Matched case-insensitively anywhere in
#: the text, because ATS descriptions are one long run of HTML with no reliable
#: line structure once the tags are stripped.
_REQUIRED_HEADINGS = (
    r"what you'?ll need",
    r"what you will need",
    r"minimum qualifications",
    r"basic qualifications",
    r"requirements",
    r"who you are",
    r"qualifications",
    r"you have",
)

#: Headings that open a *preferred* block. Checked first where both could match,
#: since "preferred qualifications" contains "qualifications".
_PREFERRED_HEADINGS = (
    r"preferred qualifications",
    r"nice to haves?",
    r"bonus points",
    r"it'?s a plus",
    r"pluses",
    r"we'?d love to see",
    r"desirable",
)

_EQUIVALENCE = re.compile(r"\bor\s+(?:have\s+)?equivalent\b", re.I)

_DEGREE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("phd", r"\b(ph\.?\s?d\.?|doctorate|doctoral degree)\b"),
    ("masters", r"\b(master'?s(?:\s+degree)?|m\.?s\.?c?\.?|m\.eng\.?)\b"),
    ("bachelors", r"\b(bachelor'?s(?:\s+degree)?|b\.?s\.?c?\.?|b\.?a\.?|b\.eng\.?)\b"),
)


def _heading_spans(text: str) -> list[tuple[int, NecessityName]]:
    """Every heading occurrence with the necessity it opens, in document order.

    **A required heading nested inside a preferred one is discarded**, and that
    rule is the whole reason this returns spans rather than offsets. "Preferred
    qualifications" contains the bare word "qualifications", which is itself a
    required heading; the inner match starts ten characters later, so it is the
    *last* heading before everything in the preferred block. Without this rule a
    posting's entire preferred section is read as required — measured on
    "Minimum qualifications ... Preferred qualifications ... Kubernetes", where
    Kubernetes came out `required` — and every technology in it becomes a gap
    the candidate does not actually have. That is the exact failure `necessity`
    exists to prevent, arriving through the heading vocabulary instead of
    through the ranking.
    """
    preferred: list[tuple[int, int]] = []
    for pattern in _PREFERRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            preferred.append((m.start(), m.end()))

    found: list[tuple[int, NecessityName]] = [(start, "preferred") for start, _ in preferred]
    for pattern in _REQUIRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            if any(start <= m.start() < end for start, end in preferred):
                continue
            found.append((m.start(), "required"))

    # A preferred heading still wins at the same offset, for any pair the
    # containment rule above does not separate.
    best: dict[int, NecessityName] = {}
    for offset, necessity in found:
        if necessity == "preferred" or offset not in best:
            best[offset] = necessity
    return sorted(best.items())


def necessity_at(text: str, position: int) -> NecessityName:
    """Which heading governs `position`.

    Text before any heading is `mentioned` — an "about us" paragraph naming a
    stack is not an ask. The one exception is a posting with no headings at all,
    where everything is `mentioned` rather than promoted by guesswork.
    """
    governing: NecessityName = "mentioned"
    for offset, necessity in _heading_spans(text):
        if offset <= position:
            governing = necessity
        else:
            break
    return governing


def _sentence_around(text: str, position: int) -> str:
    start = max(text.rfind(".", 0, position), text.rfind(";", 0, position)) + 1
    end = text.find(".", position)
    return text[start : end if end != -1 else len(text)]


#: Strongest first. A technology named in prose and again under a requirements
#: heading is one ask, and the heading is what the posting means by it.
_NECESSITY_RANK: dict[NecessityName, int] = {
    "required": 3,
    "preferred": 2,
    "mentioned": 1,
}


def _technologies(text: str, vocabulary: SkillVocabulary) -> list[RequirementProposal]:
    """One proposal per technology, carrying its strongest occurrence.

    Uses ``match_all`` rather than ``match``: the latter keeps only the first
    occurrence per name, which for a posting means an "about us" mention can
    hide the requirement further down. See `skill_vocabulary.match_all`.
    """
    best: dict[str, RequirementProposal] = {}
    for match in vocabulary.match_all(text):
        necessity = necessity_at(text, match.char_start)
        candidate = RequirementProposal(
            kind="technology",
            value=match.canonical_name,
            raw_text=text[match.char_start : match.char_end],
            char_start=match.char_start,
            char_end=match.char_end,
            necessity=necessity,
        )
        incumbent = best.get(match.canonical_name)
        if incumbent is None or (_NECESSITY_RANK[necessity] > _NECESSITY_RANK[incumbent.necessity]):
            best[match.canonical_name] = candidate
    return list(best.values())


def _degrees(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    claimed: list[range] = []
    for value, pattern in _DEGREE_PATTERNS:  # phd first, so it wins the sentence
        for m in re.finditer(pattern, text, re.I):
            if any(m.start() in r for r in claimed):
                continue
            claimed.append(range(m.start(), m.end()))
            out.append(
                RequirementProposal(
                    kind="degree",
                    value=value,
                    raw_text=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    necessity=necessity_at(text, m.start()),
                    has_equivalence=bool(_EQUIVALENCE.search(_sentence_around(text, m.start()))),
                )
            )
    return out


def _graduation_windows(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    # The EN DASH in this alternation is deliberate and load-bearing, so RUF001
    # is suppressed rather than obeyed: it is what Akuna and IMC actually type.
    # "Graduating between December 2027 [en dash] August 2028" is a real line in
    # the recorded corpus, which carries 11 such dashes. Normalising this to a
    # hyphen would match the character we wish they had used, and nothing else.
    ranged = re.compile(r"\b(20\d{2})\s*(?:-|–|to|and)\s*(20\d{2})\b")  # noqa: RUF001
    for m in ranged.finditer(text):
        if not re.search(r"graduat", text[max(0, m.start() - 90) : m.start()], re.I):
            continue
        out.append(
            RequirementProposal(
                kind="graduation_window",
                value=f"{m.group(1)}-{m.group(2)}",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    claimed = [range(p.char_start, p.char_end) for p in out]
    for m in re.finditer(r"\b(20\d{2})\b", text):
        if any(m.start() in r for r in claimed):
            continue
        if not re.search(r"graduat", text[max(0, m.start() - 90) : m.start()], re.I):
            continue
        out.append(
            RequirementProposal(
                kind="graduation_window",
                value=f"{m.group(1)}-{m.group(1)}",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def _years_of_experience(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in re.finditer(r"\b(\d{1,2})\s*\+?\s*years?\b", text, re.I):
        window = text[m.end() : m.end() + 40].lower()
        if "experience" not in window:
            continue
        out.append(
            RequirementProposal(
                kind="years_experience",
                value=m.group(1),
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def _enrollment(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in re.finditer(r"\bcurrently (?:pursuing|enrolled|studying)\b", text, re.I):
        out.append(
            RequirementProposal(
                kind="enrollment",
                value="required",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def _authorization(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in re.finditer(r"\b(?:will not|unable to|do not|cannot)\s+sponsor\w*\b", text, re.I):
        out.append(
            RequirementProposal(
                kind="authorization",
                value="no_sponsorship",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    for m in re.finditer(r"\b(?:we|will)\s+(?:do\s+)?sponsor\w*\b", text, re.I):
        out.append(
            RequirementProposal(
                kind="authorization",
                value="sponsorship_offered",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def extract_requirements(
    text: str, *, vocabulary: SkillVocabulary | None = None
) -> list[RequirementProposal]:
    """Every requirement the rules can point at, in document order.

    Recall is traded for precision, as in `resume_extraction`: a requirement
    described in words the vocabulary does not carry yields nothing, and that
    gap is measured in `test_requirement_extraction_against_the_answer_key.py`
    rather than assumed away.
    """
    if not text:
        return []
    vocab = vocabulary if vocabulary is not None else load_vocabulary()
    proposals = [
        *_technologies(text, vocab),
        *_degrees(text),
        *_graduation_windows(text),
        *_years_of_experience(text),
        *_enrollment(text),
        *_authorization(text),
    ]
    return sorted(proposals, key=lambda p: (p.char_start, p.kind, p.value))
