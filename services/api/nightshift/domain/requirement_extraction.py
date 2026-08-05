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
#:
#: **Everything below the first block was measured on the recorded corpus, not
#: imagined**, by the same route `scripts/make_label_worksheet.py` built its
#: list. Graded at m3a.1 with the imagined list alone, 43 of 103 missed required
#: technologies were ones the extractor had *found* and then filed under the
#: wrong necessity, because the heading above them was not a heading it knew.
#: Akuna writes "Qualities that make great candidates" and never the word
#: "requirements"; that phrase alone governs 13 of the 60 labeled postings.
_REQUIRED_HEADINGS = (
    r"requirements for this role",
    r"what you'?ll need",
    r"what you will need",
    r"minimum qualifications",
    r"basic qualifications",
    r"requirements",
    r"who you are",
    r"qualifications",
    r"you have",
    # Measured, with the count of labeled postings each governs.
    r"what we look for",  # 7, Databricks
    r"your skills and experience",  # 7, IMC
    r"you might thrive",  # 5, OpenAI
    r"you may be a good fit if you",  # 3, Anthropic
    r"skills you'?ll need",  # 3, Jump
    r"who we'?re looking for",
    r"what we'?re looking for",
    r"the ideal candidate is",
    r"what you'?ll bring",
    r"you should have",
    r"who should apply",
    r"about you",
    r"required",
)

#: Headings that open a required block **only when nothing harder opened one
#: first**, and a preferred block otherwise.
#:
#: Akuna is the whole reason this category exists, and the corpus settles it
#: rather than intuition. "Qualities that make great candidates" governs 13 of
#: the 60 labeled postings. In the 11 with no other requirements heading it
#: carries the real asks, and the human labeled C++, Linux and Python required
#: from it. In the 2 that also say "Requirements for this role" — both
#: internships, where that harder heading carries graduation, GPA and work
#: authorization — the human labeled `required_tech` **empty** and put
#: Kubernetes and AWS under `mentioned_not_required`.
#:
#: So the same phrase means "these are the requirements" in one posting and
#: "these would be nice" in another, and what distinguishes them is whether the
#: posting already said the harder thing.
_SOFT_REQUIRED_HEADINGS = (r"qualities that make great candidates",)

#: Headings that open a *preferred* block. A required heading nested inside one
#: of these is discarded — see :func:`_heading_spans`, which is what lets
#: "additional qualities that make great candidates" beat the required heading
#: sitting inside it.
_PREFERRED_HEADINGS = (
    r"preferred qualifications",
    r"nice to haves?",
    r"bonus points",
    r"it'?s a plus",
    r"pluses",
    r"we'?d love to see",
    r"desirable",
    # Measured on the corpus, same as above.
    r"additional qualities that make great candidates",
    r"additional experience we value",
    r"strong candidates may also have",
    r"additional qualities",
    r"preferred",
)

#: Headings after which nothing is an ask any more, returning necessity to
#: `mentioned`. Measured: OpenAI's "Developer Productivity" posting ends its
#: requirements and then says "As technical context: ... some core technologies
#: we build with include Terraform, Buildkite, Postgres, Cosmos DB, Kafka,
#: Python, and FastAPI" — five technologies the human filed as
#: `mentioned_not_required` and which the last heading, several hundred
#: characters above, was still calling required. The rest are the compensation
#: and boilerplate closers `scripts/make_label_worksheet.py` already validated
#: against this corpus.
_CLOSER_HEADINGS = (
    r"as technical context",
    r"about (?:us|the company|openai|akuna|databricks|anthropic)",
    r"annual salary",
    r"base salary",
    r"pay range transparency",
    r"compensation",
    r"benefits",
    r"equal (?:employment )?opportunity",
    r"pay transparency",
    r"how to apply",
    r"application process",
    r"please note",
)

#: An optionality marker in the *sentence* demotes a technology to `preferred`
#: however strong the heading above it was.
#:
#: This is the second way a nice-to-have becomes a false gap, and on this corpus
#: it was the commonest: 12 of 19 violations. A posting writes its optionality
#: inline rather than under its own heading — "VBA or Python programming skills
#: are a plus, but not required", "SQL is preferred but not required",
#: "Proficiency in a programming language is required (Java or C++ preferred)".
#: The heading above every one of those says required, and it is right about the
#: rest of its bullets; only the sentence knows about these.
_INLINE_OPTIONAL = re.compile(
    r"\b(?:is|are|as)\s+(?:a\s+|an\s+|strong(?:ly)?\s+|highly\s+)*"
    r"(?:plus|pluses|bonus|preferred|desired|desirable|nice to have)\b"
    r"|\bnot\s+required\b"
    r"|\bbut\s+not\s+necessary\b"
    r"|\ba\s+plus\b"
    r"|\bbonus\s+points\b"
    r"|\bpreferred\s*\)"
    r"|\bor\s+similar\s*\)",
    re.I,
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

    A **closer** returns necessity to `mentioned`, and a **soft** required
    heading opens a preferred block when a hard one already opened above it —
    see :data:`_CLOSER_HEADINGS` and :data:`_SOFT_REQUIRED_HEADINGS`.
    """
    preferred: list[tuple[int, int]] = []
    for pattern in _PREFERRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            preferred.append((m.start(), m.end()))

    def _nested_in_preferred(start: int) -> bool:
        return any(left <= start < right for left, right in preferred)

    found: list[tuple[int, NecessityName]] = [(start, "preferred") for start, _ in preferred]

    hard_required: list[int] = []
    for pattern in _REQUIRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            if _nested_in_preferred(m.start()):
                continue
            hard_required.append(m.start())
            found.append((m.start(), "required"))

    # A soft heading is required only when nothing harder opened a block first.
    earliest_hard = min(hard_required, default=None)
    for pattern in _SOFT_REQUIRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            if _nested_in_preferred(m.start()):
                continue
            softened = earliest_hard is not None and earliest_hard < m.start()
            found.append((m.start(), "preferred" if softened else "required"))

    for pattern in _CLOSER_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            found.append((m.start(), "mentioned"))

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


#: Where one bullet stops and the next begins, looking backwards. A closing
#: parenthesis is in this set and it is the character that matters most.
_CLAUSE_OPENS = ".;)•|!?"
#: The same, looking forwards. An *opening* parenthesis starts a new aside.
_CLAUSE_CLOSES = ".;(•|!?"

#: How far from a technology an optionality marker may sit and still be about
#: it. Measured on the corpus: widest genuine marker 46 characters, nearest
#: false one 200.
_CLAUSE_RADIUS = 70


def _clause_around(text: str, position: int) -> str:
    """The bullet `position` sits in — never the neighbouring ones.

    :func:`_sentence_around` is far too wide for this job, and one posting
    proves it. Flattened ATS descriptions run bullets together with no full
    stop between them, so a period-delimited "sentence" reached 400 characters
    across four separate asks in Akuna's "Software Engineer - C++":

        ... template metaprogramming a plus) Experience with Linux and
        Python required Understanding of data structures ...

    "a plus" belongs to the bullet about metaprogramming. Read at sentence
    width it demoted Linux and Python, which the very next word calls
    *required*, and cost three true positives on that posting alone. Stopping
    the backward scan at the closing parenthesis keeps each bullet's optionality
    to itself.

    **Bounded by distance as well as by punctuation**, because some stretches
    carry no punctuation at all. The same Akuna posting runs five asks together
    with nothing between them, ending "Familiarity with trading and trading
    systems is a plus" — 200 characters after "Linux and Python required", and
    still inside the same delimiter-free run. Every genuine inline marker in
    this corpus sits within 55 characters of the technology it qualifies; the
    widest is "Tableau, SQL, Python, or AI-assisted analytics is a strong plus"
    at 46. :data:`_CLAUSE_RADIUS` is set above that and below 200.
    """
    left = max(0, position - _CLAUSE_RADIUS)
    right = min(len(text), position + _CLAUSE_RADIUS)
    start = max((text.rfind(c, left, position) for c in _CLAUSE_OPENS), default=-1)
    start = left if start == -1 else start + 1
    ends = [pos for pos in (text.find(c, position, right) for c in _CLAUSE_CLOSES) if pos != -1]
    return text[start : min(ends) if ends else right]


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
        if necessity == "required" and _INLINE_OPTIONAL.search(
            _clause_around(text, match.char_start)
        ):
            necessity = "preferred"
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
