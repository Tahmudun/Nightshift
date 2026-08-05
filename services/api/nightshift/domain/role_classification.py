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

from nightshift.db.base import RoleFamily, Seniority

#: Bumped when a rule changes. Stored beside a classification so a moved number
#: can be attributed to the rules rather than to the corpus.
CLASSIFIER_VERSION = "m3b.1"

InternshipName = Literal["yes", "no", "unclear"]


@dataclass(frozen=True)
class RoleClassification:
    role_family: RoleFamily
    seniority: Seniority
    is_internship: InternshipName
    #: Why, in the classifier's own words — the matched phrase and where it was
    #: found. I4's habit applied to a label rather than a score: a value with no
    #: inspectable reason is one nobody can argue with.
    family_reason: str
    seniority_reason: str


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


def _classify_family(title: str, description: str) -> tuple[RoleFamily, str]:
    if m := _NOT_TECH_TITLE.search(title):
        return RoleFamily.NOT_TECH, f"title says {m.group(0)!r}"
    for family, pattern in _FAMILY_TITLE_RULES:
        if m := pattern.search(title):
            # The description can still veto a tech family, and only in the one
            # direction: towards `not_tech`. A description may not *promote* a
            # business title into an engineering family, because these
            # descriptions all talk about technology and most of them at length.
            if d := _NOT_TECH_DESCRIPTION.search(description):
                return RoleFamily.NOT_TECH, f"description says {d.group(0)!r}"
            return family, f"title says {m.group(0)!r}"
    return RoleFamily.UNCLEAR, "no family rule matched the title"


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


def classify_role(
    title: str, *, description: str = "", years: int | None = None
) -> RoleClassification:
    """Classify one posting. Pure, and takes no ORM object.

    `years` comes from `eligibility_reading.PostingReading.min_years_experience`
    rather than being re-read here, so the number the gate uses and the number
    the level rule uses cannot diverge.
    """
    family, family_reason = _classify_family(title, description)
    seniority, seniority_reason = _classify_seniority(title, years)
    return RoleClassification(
        role_family=family,
        seniority=seniority,
        is_internship=_classify_internship(title),
        family_reason=family_reason,
        seniority_reason=seniority_reason,
    )
