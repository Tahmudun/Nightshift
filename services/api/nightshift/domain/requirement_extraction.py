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
EXTRACTOR_VERSION = "m3a.2"

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
    # Harvested 2026-08-05, governs 2 labeled postings. Anthropic's Fellows
    # postings write "Candidates must be: Fluent in Python programming" several
    # hundred characters below a "Strong candidates may also have" heading, so
    # without this phrase the *preferred* heading went on governing a sentence
    # that says "must". It cost twice — a required-technology false negative and
    # a wrong necessity — which is why heading vocabulary was the lever worth
    # pulling before the long tail of skills.
    r"candidates must be",
    # Harvested 2026-08-05 at M3b Task 5, governs 15 labeled postings — every
    # Anthropic posting in the corpus, which appends a "Logistics / Minimum
    # education: ... / Required field of study: ..." block to all of them.
    #
    # It is the *last* heading before the degree sentence, so without it the
    # degree came out `mentioned` and the reading said `none`: a posting whose
    # own words are "Minimum education: Bachelor's degree" was read as requiring
    # no degree at all. Six of the sixty, all from one employer's boilerplate.
    r"minimum education",
    r"required field of study",
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
#:
#: **Closers do not have to prove themselves, unlike ambiguous requirement
#: headings, and that asymmetry was measured rather than left to taste.** The
#: worksheet applies :func:`_looks_like_a_heading` to its closers, so matching it
#: here was the obvious tidy-up; routing these through :func:`_heading_matches`
#: changes nothing, because none of them is in :data:`_AMBIGUOUS_HEADINGS`.
#: Marking the three that plausibly occur mid-prose — "compensation", "benefits",
#: "please note" — does change the numbers, and not for the better:
#:
#:     as written        precision 0.847  recall 0.861  necessity 0.915
#:     closers proving   precision 0.829  recall 0.877  necessity 0.910
#:
#: It buys two true positives for three false ones and gives back necessity.
#: Precision is the figure that matters most here — a technology wrongly called
#: required is a false gap in the explanation, which is a visible lie — so this
#: stays as it is. Recorded because the next reader will notice the same
#: asymmetry and should not have to re-run the experiment.
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

#: Heading patterns whose words occur in ordinary prose, so a bare match is not
#: enough. Keyed by the pattern string as written above, not by the text matched,
#: because these are regexes rather than literals.
#:
#: **This list and the rule below are ported from
#: ``scripts/make_label_worksheet.py``**, which has demanded the same proof since
#: the worksheet's first real run — where *30 of 60* excerpts anchored inside
#: prose. The extractor was graded against an answer key built with that rule
#: while using a looser one itself, and the gap is not academic: Databricks
#: 8290810002 says "requirements, when we ingest terabytes per second", and that
#: sentence opened a `required` block governing the rest of the posting,
#: including "an engineering culture born from Apache Spark" — which the human
#: labeled a nice-to-have, and which the extractor reported as required.
_AMBIGUOUS_HEADINGS = frozenset(
    {
        r"requirements",
        r"qualifications",
        r"you have",
        r"you should have",
        r"about you",
        r"required",
        r"preferred",
        r"desirable",
        r"pluses",
    }
)

#: How far past a heading phrase to look for its colon, abandoned at any sentence
#: terminator. The heading vocabulary stores stems — "you might thrive" for "You
#: might thrive in this role if you:" — so the colon can sit a clause away.
_COLON_LOOKAHEAD = 80


def _colon_follows(text: str, end: int) -> bool:
    """A colon within :data:`_COLON_LOOKAHEAD`, before any sentence terminator."""
    for char in text[end : end + _COLON_LOOKAHEAD]:
        if char == ":":
            return True
        if char in ".!?;":
            return False
    return False


#: What may sit immediately before a heading. The first six are the worksheet's;
#: the brackets are this module's addition and were measured rather than
#: supposed. Databricks writes ``[Preferred] Experience using ... Apache Spark``,
#: and with brackets absent from this set that heading failed its own proof, the
#: preferred block never opened, and Apache Spark was reported as required on two
#: postings — the exact false gap the proof rule was added to remove. Applied to
#: ``scripts/make_label_worksheet.py`` too, so the two rules stay the same rule.
_HEADING_OPENERS = ".;!?•|[("


def _looks_like_a_heading(text: str, start: int, end: int) -> bool:
    """A colon follows, it is capitalised, or it opens a sentence.

    The same three tests ``make_label_worksheet.py`` applies, deliberately —
    a rule that disagrees with the one used to build the answer key would be
    graded against evidence gathered under different assumptions.
    """
    written_in_capitals = text[start:end].isupper()
    preceding = text[:start].rstrip()
    opens_a_sentence = not preceding or preceding[-1] in _HEADING_OPENERS
    return _colon_follows(text, end) or written_in_capitals or opens_a_sentence


def _heading_matches(pattern: str, text: str) -> list[tuple[int, int]]:
    """Every occurrence of `pattern` that genuinely opens a section.

    A distinctive phrase is taken at its word; an ambiguous one must prove
    itself. Requiring proof of the distinctive ones was measured on the
    worksheet and cost three real postings.
    """
    spans = [(m.start(), m.end()) for m in re.finditer(pattern, text, re.I)]
    if pattern not in _AMBIGUOUS_HEADINGS:
        return spans
    return [(start, end) for start, end in spans if _looks_like_a_heading(text, start, end)]


#: A13's escape hatch. **Missing one of these is the dangerous direction**: it
#: turns "or an equivalent combination of education, training, and/or
#: experience" into a hard degree requirement, and a hard degree requirement is
#: an `ineligible` for somebody the employer would have hired.
#:
#: `an?` was added at M3b Task 5 because Anthropic writes "Bachelor's degree **or
#: an equivalent** combination" on every one of its 15 postings in the corpus and
#: the original pattern required "or equivalent" adjacently. Harvested rather
#: than guessed: `or\s+(?:an?\s+)?equivalent` matches 23 of the 60 postings
#: against the narrow form's 8.
_EQUIVALENCE = re.compile(r"\bor\s+(?:an?\s+)?(?:have\s+)?equivalent\b", re.I)

#: The RIGHT SINGLE QUOTATION MARK is deliberate and load-bearing, so RUF001 is
#: suppressed rather than obeyed — the same call, for the same reason, as the EN
#: DASH in `_graduation_windows`. **Akuna, Anthropic and IMC type the curly
#: apostrophe** in "Bachelor's degree", because that is what a rich-text editor
#: produces, and an ASCII-only pattern matched none of it.
#:
#: Measured before the fix: 21 of the 26 degree errors against the answer key
#: were postings whose degree sentence this could not see at all. Two came out
#: `phd` against a labeled `bachelors`, from a sentence reading "Pursuing a
#: bachelor's, master's, or Ph.D." — `Ph.D` is the one spelling in that list
#: with no apostrophe in it, so it was the only proposal and won by default.
#: That is the dangerous direction: a posting open to a bachelor's graduate
#: reading as a doctorate requirement.
#:
#: Normalising the text to ASCII first would have worked and was rejected: every
#: proposal carries character offsets into `jobs.description_text`, and rewriting
#: the string the offsets point at is how a span comes to quote something the
#: posting never said. U+2019 happens to be one character wide, so the offsets
#: would have survived — but the rule is not "when the replacement is the same
#: width", and the next such fix would not be.
#: The bare two-letter abbreviations must prove themselves, and IMC's
#: Administrative Assistant posting is why. `m\.?s\.?` matched the `MS` in **MS
#: Office**, the reading came out `masters`, and the gate hard-blocked a
#: bachelor's graduate from a role the answer key labels `degree: none`. Found by
#: `test_no_posting_is_wrongly_reported_ineligible` on its first run — a false
#: positive that would merely have cost precision at M3a became a person being
#: told they cannot apply.
#:
#: Two constraints together, because either alone is not enough:
#:
#: - **Case-sensitive** via `(?-i:...)`. These boards are trading firms and
#:   `\bms\b` under `re.I` matches the milliseconds in "5 ms in latency". The
#:   same call `skills.yaml` already makes for `Go`, `Rust`, `React` and
#:   `Outlook`.
#: - **A degree context must follow** — a slash, "in", "or", or "degree". "MS
#:   Office" has none of them; "BS/MS in Finance" and "Pursuing a BS/MS/PhD"
#:   have all they need.
#:
#: The spelled-out and dotted forms (`Bachelor's`, `B.S.`, `MSc`) are
#: unambiguous on their own and keep matching without either constraint.
#: A comma counts **only when another degree abbreviation follows it**. IMC
#: writes "BS, MS preferably in business, economics or STEM", where the comma is
#: doing the same job the slash does in "BS/MS". Allowing a bare comma would let
#: "MS, Word, Excel" back in, which is the false positive this whole constraint
#: exists to keep out.
_ABBREVIATION_NEEDS = (
    r"(?=\s*(?:/|,\s*(?-i:BS|MS|BA|BSc|MSc|PhD|Ph\.D)\b|\bin\b|\bor\b|\bdegree\b))"
)

_DEGREE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("phd", r"\b(ph\.?\s?d\.?|doctorate|doctoral degree)\b"),
    (
        "masters",
        r"\b(master['’]?s(?:\s+degree)?|m\.\s?s\.?c?\.?|m\.eng\.?"  # noqa: RUF001
        r"|(?-i:MSc)|(?-i:MS)" + _ABBREVIATION_NEEDS + r")\b",
    ),
    (
        "bachelors",
        r"\b(bachelor['’]?s(?:\s+degree)?|b\.\s?s\.?c?\.?|b\.\s?a\.?|b\.eng\.?"  # noqa: RUF001
        r"|(?-i:BSc)|(?-i:BS|BA)" + _ABBREVIATION_NEEDS + r")\b",
    ),
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
        preferred.extend(_heading_matches(pattern, text))

    def _nested_in_preferred(start: int) -> bool:
        return any(left <= start < right for left, right in preferred)

    found: list[tuple[int, NecessityName]] = [(start, "preferred") for start, _ in preferred]

    hard_required: list[int] = []
    for pattern in _REQUIRED_HEADINGS:
        for start, _end in _heading_matches(pattern, text):
            if _nested_in_preferred(start):
                continue
            hard_required.append(start)
            found.append((start, "required"))

    # A soft heading is required only when nothing harder opened a block first.
    earliest_hard = min(hard_required, default=None)
    for pattern in _SOFT_REQUIRED_HEADINGS:
        for start, _end in _heading_matches(pattern, text):
            if _nested_in_preferred(start):
                continue
            softened = earliest_hard is not None and earliest_hard < start
            found.append((start, "preferred" if softened else "required"))

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


#: "or prior" and friends, which turn a single year into a window with no lower
#: bound. These follow the year: "Must be graduating August 2027 or prior".
_OPEN_ENDED_AFTER = re.compile(r"^\W{0,3}or\s+(?:prior|earlier|before|sooner|previously)\b", re.I)

#: ...and these precede it: "graduating by December 2028", "through 2029".
_OPEN_ENDED_BEFORE = re.compile(
    r"\b(?:by|through|before|prior\s+to|no\s+later\s+than|on\s+or\s+before)\b[^.;]{0,25}$", re.I
)


def _is_open_ended(text: str, start: int, end: int) -> bool:
    """Whether a graduation year is a ceiling rather than a single year.

    **This distinction is a wrong-`ineligible` waiting to happen, and it was
    one.** Akuna's Junior Quantitative Developer posting says "Must be
    graduating August 2027 or prior". Read as the single year 2027, the gate
    blocked a 2024 graduate from a role whose own words say they qualify —
    caught by `test_no_posting_is_wrongly_reported_ineligible` on its first run,
    against real corpus text and a realistic profile.

    M3b Task 5 recorded this gap and deferred it as an accuracy problem worth 5
    of 60 labels. It was not an accuracy problem. The gate is what turned the
    5 labels into a person being told they cannot apply.

    Both sides of the year are checked because employers write it both ways, and
    the "before" pattern is anchored to the end of the preceding text so that a
    stray "by" three sentences earlier cannot reach it.
    """
    after = text[end : end + 20]
    if _OPEN_ENDED_AFTER.match(after):
        return True
    before = text[max(0, start - 40) : start]
    return bool(_OPEN_ENDED_BEFORE.search(before))


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
        if _is_open_ended(text, m.start(), m.end()):
            out.append(
                RequirementProposal(
                    kind="graduation_window",
                    value=f"through-{m.group(1)}",
                    raw_text=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    necessity=necessity_at(text, m.start()),
                )
            )
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


#: Broadened at M3b Task 5, from `currently (pursuing|enrolled|studying)`.
#: That required the word "currently" and **10 of the 11 postings the answer key
#: labels `enrollment_required: yes` do not use it**. They write:
#:
#:     Requirements for this role: Pursuing a bachelor's, master's, or Ph.D.
#:     What we look for: Pursuing a bachelor's or master's in computer science
#:     Your Skills and Experience: Current university student graduating between
#:
#: "Pursuing" alone is not enough and is not used alone here — "pursuing
#: excellence" and "pursuing opportunities" are ordinary description prose. It
#: is anchored to a degree word immediately after, which is the same
#: prove-itself discipline `_looks_like_a_heading` applies to headings and for
#: the same reason: an unanchored word that appears in prose will match prose.
_ENROLLMENT = re.compile(
    r"\b(?:"
    r"currently\s+(?:pursuing|enrolled|studying)"
    r"|pursuing\s+(?:a|an|your)?\s*"
    r"(?:bachelor|master|ph\.?\s?d|doctora|degree|bs\b|ms\b|undergraduate|graduate)"
    r"|current(?:ly)?\s+(?:university|college|full-?time)?\s*student"
    r"|enrolled\s+in\s+(?:a|an|your)"
    r")",
    re.I,
)


def _enrollment(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in _ENROLLMENT.finditer(text):
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
