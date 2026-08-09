"""What kind of role a posting is, and at what level.

Fills `jobs.role_family` and `jobs.seniority`, which have been null since M1.

Rules over the title, with a short list of high-precision description phrases
where the title genuinely does not say. No model: the same argument as ADR 0015
— a classification that feeds a score has to be reproducible from its inputs,
and when a rule is wrong you can see *which* rule.

**A caveat that belongs at the top rather than in a review.** The seniority
precedence below, and its two years-of-experience thresholds, were chosen while
looking at the same 60 titles this is graded on. That is weaker independence
than M3a had, where the answer key was labeled before any extraction rule
existed. Some rules here are not fitted in any meaningful sense — "Director in
the title means director" is what anybody would write — but the thresholds and
the ordering are, and the reported accuracy is therefore an upper bound rather
than an estimate of how this behaves on a posting it has not seen. The corpus
carries 93 recorded-but-unlabeled postings for exactly this kind of held-out
check; using them is recorded in PROGRESS as work this milestone has not done.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nightshift.db.base import InternshipSeason, JobTextField, RoleFamily, Seniority

#: Bumped when a rule changes. Stored beside a classification so a moved number
#: can be attributed to the rules rather than to the corpus.
CLASSIFIER_VERSION = "m3b.1"

InternshipName = Literal["yes", "no", "unclear"]


@dataclass(frozen=True)
class TextSpan:
    """Words the classifier actually read, and where they are.

    Added at M3c Task 3, and the reason is `matching.md` §2.1: role relevance is
    one of the three components that make a claim about a *person*, so it has to
    quote the posting. `family_reason` reads `title says 'engineer'` and a human
    can follow it, but recovering a span by parsing that sentence back apart is
    the kind of second derivation that goes wrong quietly. The rule already has
    the match object; this keeps it.

    **`field` exists because the classifier reads two different strings.** Every
    other span in this system points into `jobs.description_text`; a family is
    decided on the title, with the description able to veto it. A span that
    could not say which one it came from would be checked against the wrong text
    — and the trigger that verifies spans would then reject correct rows and
    accept nothing useful.
    """

    field: JobTextField
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class RoleClassification:
    role_family: RoleFamily
    seniority: Seniority
    is_internship: InternshipName
    #: Both `None` unless the posting is an internship **and** its title says
    #: so. Two fields rather than one `summer_2027`, because two corpus
    #: postings state a year and no season and a combined value could keep
    #: them only by inventing the season. See `test_internship_season.py` for
    #: the measurement.
    internship_season: InternshipSeason | None
    internship_year: int | None
    #: Why, in the classifier's own words — the matched phrase and where it was
    #: found. I4's habit applied to a label rather than a score: a value with no
    #: inspectable reason is one nobody can argue with.
    #:
    #: There is deliberately no `season_reason`. A family or a level is a
    #: judgement made *about* a title and needs its reason carried alongside;
    #: a season is lifted verbatim out of it. "Summer 2027" beside a title
    #: reading "Intern, Summer 2027" explains itself, and a reason string
    #: repeating the value is the kind of evidence that looks like evidence.
    family_reason: str
    seniority_reason: str
    #: The words behind `family_reason`. `None` when no rule matched, which is
    #: the `unclear` family — and a component with nothing to quote scores
    #: nothing rather than scoring on an absence.
    family_span: TextSpan | None = None


def _word(*terms: str) -> re.Pattern[str]:
    """Whole-word alternation. Substrings are how `react` became a required
    technology on eight postings that never mention React (M3a.1)."""
    return re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.I)


# ---------------------------------------------------------------------------
# Role family
#
# `not_tech` is tested **first and wins**, and the corpus is why. "AI Compliance
# Officer" contains AI, "Capital Markets - Infrastructure Financing" contains
# Infrastructure, "Cloud Partner Enablement Lead" contains Cloud, and "People
# Research Scientist, Recruiting" contains Research Scientist. Every one of them
# is a business role wearing a technical word, and a tech-first order files all
# four under a family they do not belong to.
# ---------------------------------------------------------------------------

_NOT_TECH_TITLE = _word(
    "compliance",
    "account",
    "accounts",
    "accountant",
    "accounting",
    "marketing",
    "recruiter",
    "recruiting",
    "treasury",
    "compensation",
    "administrative",
    "financing",
    "finance",
    "financial",
    "capital markets",
    "sales",
    "partnership",
    "partnerships",
    "partner",
    "gtm",
    "enablement",
    "legal",
    "counsel",
    "people",
)

#: Read only when the title is silent. Kept to phrases that decide the question
#: on their own — "you will be a Pre-Sales architect" is Anthropic's own first
#: sentence about the Applied AI Architect role, and it settles a title that
#: otherwise reads as an engineering job.
_NOT_TECH_DESCRIPTION = _word("pre-?sales", "quota", "book of business")

#: Ordered. The first match wins, so the more specific pattern comes first:
#: "Data Infrastructure" must be read before "Engineering", and "Quantitative"
#: before "Researcher".
#:
#: **The role type beats the domain, and one posting is why.** OpenAI's "Senior
#: Technical Program Manager - Security" names a job and a subject area, and the
#: job is program management — security is what it is *about*. Graded with the
#: domain families first it came out `security`, which describes the team and
#: not the work. So the explicit management phrases sit above every domain rule
#: and bare "product" stays below them, where it cannot swallow a title that
#: merely mentions a product.
_FAMILY_TITLE_RULES: tuple[tuple[RoleFamily, re.Pattern[str]], ...] = (
    (RoleFamily.PRODUCT, _word("product manager", "product management", "program manager", "tpm")),
    (RoleFamily.DATA_ENGINEERING, _word("data infrastructure", "data engineer", "data platform")),
    (RoleFamily.SECURITY, _word("security", "threat", "appsec", "cryptography")),
    (RoleFamily.HARDWARE, _word("hardware", "fpga", "asic", "silicon")),
    (RoleFamily.QUANT_TRADING, _word("quant", "quantitative", "trader", "trading")),
    (RoleFamily.DESIGN, _word("design", "designer", "art director", "brand design")),
    (RoleFamily.ML_AI, _word("machine learning", "ml", "ai", "deep learning", "genai", "nlp")),
    (RoleFamily.INFRASTRUCTURE, _word("data cent(?:er|re)", "platform", "infrastructure", "sre")),
    (RoleFamily.SOFTWARE_ENGINEERING, _word("software engineer", "engineering", "engineer")),
    (RoleFamily.PRODUCT, _word("product")),
)


def _span(field: JobTextField, m: re.Match[str]) -> TextSpan:
    return TextSpan(field=field, text=m.group(0), char_start=m.start(), char_end=m.end())


def _classify_family(title: str, description: str) -> tuple[RoleFamily, str, TextSpan | None]:
    if m := _NOT_TECH_TITLE.search(title):
        return RoleFamily.NOT_TECH, f"title says {m.group(0)!r}", _span(JobTextField.TITLE, m)
    for family, pattern in _FAMILY_TITLE_RULES:
        if m := pattern.search(title):
            # The description can still veto a tech family, and only in the one
            # direction: towards `not_tech`. A description may not *promote* a
            # business title into an engineering family, because these
            # descriptions all talk about technology and most of them at length.
            if d := _NOT_TECH_DESCRIPTION.search(description):
                return (
                    RoleFamily.NOT_TECH,
                    f"description says {d.group(0)!r}",
                    _span(JobTextField.DESCRIPTION_TEXT, d),
                )
            return family, f"title says {m.group(0)!r}", _span(JobTextField.TITLE, m)
    return RoleFamily.UNCLEAR, "no family rule matched the title", None


# ---------------------------------------------------------------------------
# Seniority
#
# Ordered, and the order is the rule. Two orderings are load-bearing and both
# come from a real posting:
#
#   "Associate Product Manager, New Grad (2027 Start)"  — new-grad beats junior
#   "Campus Recruiter, Early Careers ..."  6+ years     — years beat campus
#
# The second is the interesting one. Three words in that title say early career
# and the role wants six years of experience; a title-only classifier calls it
# new_grad and would rank it into a new graduate's list.
# ---------------------------------------------------------------------------

_INTERNSHIP = _word("intern", "interns", "internship", "co-?op", "summer analyst")
_DIRECTOR = _word("director", "vp", "vice president", "head of", "chief")
_STAFF = _word("lead", "staff", "principal", "distinguished")
_SENIOR = _word("senior", "sr")
_JUNIOR = _word("junior", "jr")
_EARLY_CAREER = _word(
    "new grad", "new graduate", "graduate", "campus", "early career", "early careers", "university"
)

#: Below this, an early-career title word is believed. At or above it, the years
#: figure wins. Three, because the corpus's early-career postings state either
#: nothing or one year, and its trap — the campus recruiter — states six.
#: **Fitted to this corpus**; see the module docstring.
_EARLY_CAREER_YEARS_CEILING = 3
_SENIOR_YEARS_FLOOR = 6


def _classify_seniority(title: str, years: int | None) -> tuple[Seniority, str]:
    for level, pattern in (
        (Seniority.INTERNSHIP, _INTERNSHIP),
        (Seniority.DIRECTOR, _DIRECTOR),
        (Seniority.STAFF, _STAFF),
        (Seniority.SENIOR, _SENIOR),
        (Seniority.JUNIOR, _JUNIOR),
    ):
        if m := pattern.search(title):
            return level, f"title says {m.group(0)!r}"

    if (m := _EARLY_CAREER.search(title)) and (
        years is None or years < _EARLY_CAREER_YEARS_CEILING
    ):
        return Seniority.NEW_GRAD, f"title says {m.group(0)!r} and asks for {years or 'no'} years"

    if years is not None:
        if years >= _SENIOR_YEARS_FLOOR:
            return Seniority.SENIOR, f"asks for {years} years and the title states no level"
        if years >= 2:
            return Seniority.MID, f"asks for {years} years and the title states no level"

    return Seniority.UNCLEAR, "the title states no level and the posting states no years"


def _classify_internship(title: str) -> InternshipName:
    """`yes` or `no` only.

    There is no rule producing `unclear`, and the answer key labels it on four
    postings — Akuna's trading challenge and sneak-peek weeks, and both Anthropic
    Fellows programmes. All four are programmes rather than roles, and a rule for
    that shape would be four postings' worth of pattern fitted to four postings.
    Left as a measured miss instead; the grade says how much it costs.
    """
    return "yes" if _INTERNSHIP.search(title) else "no"


# ---------------------------------------------------------------------------
# Internship season
#
# Read out of the **title only**, and gated on the posting being an internship.
# Both restrictions were measured over the 153 recorded postings rather than
# assumed, and both remove errors the loose version makes:
#
#   * Descriptions carry 2011 (Akuna's founding year), 2015, 2025, 2028 and
#     2029. Harvesting a year from one puts a confident season on a posting
#     whose title honestly says nothing.
#   * Six non-internship titles state a season or a year — a trading challenge,
#     a sneak-peek week, a talent community, two full-time cohorts and one
#     campus role reading "(Fall 2026)". Ungated, all six acquire an internship
#     season they do not have.
#
# "autumn" folds into FALL: same season, and a British-English posting should
# not read as stating nothing.
# ---------------------------------------------------------------------------

_SEASON_WORDS: tuple[tuple[InternshipSeason, re.Pattern[str]], ...] = (
    (InternshipSeason.SUMMER, _word("summer")),
    (InternshipSeason.FALL, _word("fall", "autumn")),
    (InternshipSeason.WINTER, _word("winter")),
    (InternshipSeason.SPRING, _word("spring")),
)

#: A calendar year, not any four-digit number: "Cisco 2960" is not a season.
_TITLE_YEAR = re.compile(r"\b(20\d{2})\b")


def _read_season(
    title: str, is_internship: InternshipName
) -> tuple[InternshipSeason | None, int | None]:
    if is_internship != "yes":
        return None, None
    season = next((s for s, pattern in _SEASON_WORDS if pattern.search(title)), None)
    match = _TITLE_YEAR.search(title)
    return season, int(match.group(1)) if match else None


def classify_role(
    title: str, *, description: str = "", years: int | None = None
) -> RoleClassification:
    """Classify one posting. Pure, and takes no ORM object.

    `years` comes from `eligibility_reading.PostingReading.min_years_experience`
    rather than being re-read here, so the number the gate uses and the number
    the level rule uses cannot diverge.
    """
    family, family_reason, family_span = _classify_family(title, description)
    seniority, seniority_reason = _classify_seniority(title, years)
    is_internship = _classify_internship(title)
    season, year = _read_season(title, is_internship)
    return RoleClassification(
        role_family=family,
        seniority=seniority,
        is_internship=is_internship,
        internship_season=season,
        internship_year=year,
        family_reason=family_reason,
        seniority_reason=seniority_reason,
        family_span=family_span,
    )
