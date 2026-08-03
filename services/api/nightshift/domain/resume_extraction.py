"""Reading a resume for things it can *prove*, and refusing the rest.

``command-center.md`` §6.1 decided the shape of this module over both an LLM and
a no-parsing form: rules, deterministic, $0, no key. Every proposal carries the
character span it came from, so the confirmation screen highlights the literal
words rather than asking anyone to trust a summary.

**Recall is traded for precision on purpose.** "5 years of experience" and
"passionate self-starter" yield nothing. So does a graduation date outside an
education section, a date with no cue beside it, and any skill that is not in
``data/skills.yaml``. A missed skill costs one click on the manual form; an
invented one is invariant I2 failing, which is the worst outcome available to
this project.

Nothing here writes anything, and this module may not import the ORM — that is
a test (``test_the_extractor_cannot_reach_the_database``), not a convention. It
is the only path by which a bug in these rules could reach a confirmed fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nightshift.domain.skill_vocabulary import SkillVocabulary, load_vocabulary

#: Bumped whenever the rules change. Stored on every row this module produces,
#: so a proposal can always be traced to the rules that made it.
EXTRACTOR_VERSION = "m2c.1"

ProposalKind = Literal["skill", "graduation", "degree", "school", "project"]

#: Section headings, lower-cased and stripped of punctuation. A line is a
#: heading only if it matches one of these *entirely* — "Education" is a
#: heading, "Education has always mattered to me" is a sentence.
_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "education": ("education", "academics", "academic background"),
    "skills": ("skills", "technical skills", "technologies", "tools", "languages and tools"),
    "projects": ("projects", "personal projects", "selected projects", "side projects"),
    "experience": ("experience", "work experience", "employment", "professional experience"),
}

#: Longest first, so "Bachelor of Science" is proposed rather than a bare "B.S."
#: that happens to appear later on the same line.
_DEGREES: tuple[str, ...] = (
    "Bachelor of Science",
    "Bachelor of Arts",
    "Bachelor of Engineering",
    "Master of Science",
    "Master of Arts",
    "Master of Engineering",
    "Doctor of Philosophy",
    "Associate of Science",
    "Associate of Arts",
    "B.S.",
    "B.A.",
    "M.S.",
    "M.A.",
    "Ph.D.",
    "PhD",
    "BSc",
    "MSc",
)

_SCHOOL_KEYWORDS: tuple[str, ...] = ("University", "College", "Institute of Technology", "Academy")

_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MONTH_YEAR = re.compile(
    r"(?<![0-9A-Za-z])(?P<month>"
    + "|".join(sorted(_MONTHS, key=len, reverse=True))
    + r")\.?\s+(?P<year>20\d{2})(?![0-9])",
    re.IGNORECASE,
)
_BARE_YEAR = re.compile(r"(?<![0-9])(?P<year>20\d{2})(?![0-9])")

#: A date is only a graduation date beside one of these words. "2027" alone is
#: a number on a page, and a degree line's date is as often the start of the
#: programme as its end.
_GRADUATION_CUES = re.compile(r"graduat|expected|class of|anticipated", re.IGNORECASE)

# The en dash and the bullet glyphs are deliberate, not a typo an autoformatter
# should fix: word processors substitute them silently, so a resume exported
# from Word bullets and separates with en and em dashes rather than hyphens.
# Dropping them here would make the extractor blind to the commonest resume
# in existence.
_BULLET = re.compile(r"^\s*[-*•–●]\s+")  # noqa: RUF001

#: What separates a name from its trailing detail on one line:
#: "Hunter College, CUNY - New York, NY" and "Cafe Queue - TypeScript, React".
_NAME_TAIL = re.compile(r"\s*(?:[,|–—]|\s-\s|\(|·)")  # noqa: RUF001


@dataclass(frozen=True, slots=True)
class Proposal:
    kind: ProposalKind
    value: dict[str, object]
    char_start: int
    char_end: int
    quoted_text: str

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "value": self.value,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "quoted_text": self.quoted_text,
        }


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    position = 0
    for line in text.split("\n"):
        spans.append((position, position + len(line)))
        position += len(line) + 1
    return spans


def _heading_key(line: str) -> str | None:
    stripped = re.sub(r"[^a-z ]", "", line.strip().lower()).strip()
    if not stripped or len(stripped) > 40:
        return None
    for key, aliases in _SECTION_ALIASES.items():
        if stripped in aliases:
            return key
    return None


def find_sections(text: str) -> dict[str, tuple[int, int]]:
    """Character spans for each recognised section, heading line excluded.

    A section runs from the end of its heading to the start of the next
    heading, or to the end of the document. An **unrecognised** heading does not
    end a section — it is just a line inside it. That is the conservative
    reading: a stray "Awards" must not truncate Education and lose a degree.
    """
    headings: list[tuple[str, int, int]] = []
    for start, end in _line_spans(text):
        key = _heading_key(text[start:end])
        if key is not None:
            headings.append((key, start, end))

    sections: dict[str, tuple[int, int]] = {}
    for position, (key, _, heading_end) in enumerate(headings):
        next_start = headings[position + 1][1] if position + 1 < len(headings) else len(text)
        sections[key] = (min(heading_end + 1, next_start), next_start)
    return sections


def _lines_within(text: str, span: tuple[int, int]) -> list[tuple[int, int]]:
    return [(start, end) for start, end in _line_spans(text) if span[0] <= start < span[1]]


def _name_end(text: str, start: int, end: int) -> int:
    """Where a name stops and its trailing detail begins, on one line."""
    line = text[start:end]
    cut = _NAME_TAIL.search(line)
    return start + (cut.start() if cut else len(line.rstrip()))


def _propose_degree(text: str, span: tuple[int, int]) -> Proposal | None:
    section = text[span[0] : span[1]]
    for degree in _DEGREES:
        found = section.find(degree)
        if found != -1:
            start = span[0] + found
            end = start + len(degree)
            return Proposal(
                kind="degree",
                value={"degree": degree},
                char_start=start,
                char_end=end,
                quoted_text=text[start:end],
            )
    return None


def _propose_school(text: str, span: tuple[int, int]) -> Proposal | None:
    for start, end in _lines_within(text, span):
        line = text[start:end]
        if not any(keyword in line for keyword in _SCHOOL_KEYWORDS):
            continue
        name_start = start + (len(line) - len(line.lstrip()))
        name_end = _name_end(text, start, end)
        if name_end <= name_start:
            continue
        return Proposal(
            kind="school",
            value={"school": text[name_start:name_end]},
            char_start=name_start,
            char_end=name_end,
            quoted_text=text[name_start:name_end],
        )
    return None


def _propose_graduation(text: str, span: tuple[int, int]) -> Proposal | None:
    """A month and a year. Never a day — a resume does not say one (I1)."""
    for start, end in _lines_within(text, span):
        line = text[start:end]
        has_cue = bool(_GRADUATION_CUES.search(line))
        has_degree = any(degree in line for degree in _DEGREES)
        if not (has_cue or has_degree):
            continue

        month_year = _MONTH_YEAR.search(line)
        if month_year is not None:
            found_start = start + month_year.start()
            found_end = start + month_year.end()
            return Proposal(
                kind="graduation",
                value={
                    "year": int(month_year.group("year")),
                    "month": _MONTHS[month_year.group("month").lower()],
                },
                char_start=found_start,
                char_end=found_end,
                quoted_text=text[found_start:found_end],
            )

        if not has_cue:
            # A bare year beside a degree is as often the start of a programme
            # as its end. Only an explicit cue promotes one.
            continue
        bare = _BARE_YEAR.search(line)
        if bare is not None:
            found_start = start + bare.start()
            found_end = start + bare.end()
            return Proposal(
                kind="graduation",
                value={"year": int(bare.group("year")), "month": None},
                char_start=found_start,
                char_end=found_end,
                quoted_text=text[found_start:found_end],
            )
    return None


def _propose_projects(text: str, span: tuple[int, int]) -> list[Proposal]:
    """A heading line with at least one bullet under it. Both are the evidence."""
    proposals: list[Proposal] = []
    lines = _lines_within(text, span)
    index = 0
    while index < len(lines):
        start, end = lines[index]
        line = text[start:end]
        if not line.strip() or _BULLET.match(line):
            index += 1
            continue

        bullets: list[tuple[int, int]] = []
        cursor = index + 1
        while cursor < len(lines):
            bullet_start, bullet_end = lines[cursor]
            bullet_line = text[bullet_start:bullet_end]
            if _BULLET.match(bullet_line):
                bullets.append((bullet_start, bullet_end))
                cursor += 1
                continue
            if not bullet_line.strip() and bullets:
                cursor += 1
                continue
            break

        if not bullets:
            index += 1
            continue

        block_end = bullets[-1][1]
        evidence = "\n".join(text[b_start:b_end].strip() for b_start, b_end in bullets)
        proposals.append(
            Proposal(
                kind="project",
                value={"name": text[start : _name_end(text, start, end)], "evidence": evidence},
                char_start=start,
                char_end=block_end,
                quoted_text=text[start:block_end],
            )
        )
        index = cursor
    return proposals


def extract_proposals(text: str, *, vocabulary: SkillVocabulary | None = None) -> list[Proposal]:
    """Everything this resume can prove, in reading order.

    Deterministic: the same text always yields the same list, in the same order,
    with the same spans. That is asserted by
    ``test_the_same_text_twice_gives_byte_identical_proposals`` and is the same
    property the adapter fixture suites hold for job payloads.
    """
    vocabulary = vocabulary or load_vocabulary()
    sections = find_sections(text)
    proposals: list[Proposal] = []

    education = sections.get("education")
    if education is not None:
        for candidate in (
            _propose_degree(text, education),
            _propose_school(text, education),
            _propose_graduation(text, education),
        ):
            if candidate is not None:
                proposals.append(candidate)

    projects = sections.get("projects")
    if projects is not None:
        proposals.extend(_propose_projects(text, projects))

    for match in vocabulary.match(text):
        proposals.append(
            Proposal(
                kind="skill",
                value={"name": match.canonical_name, "vocabulary_version": vocabulary.version},
                char_start=match.char_start,
                char_end=match.char_end,
                quoted_text=text[match.char_start : match.char_end],
            )
        )

    return sorted(
        proposals, key=lambda proposal: (proposal.char_start, proposal.char_end, proposal.kind)
    )
