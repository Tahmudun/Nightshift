"""One answer per eligibility dimension, resolved from a posting's proposals.

`requirement_extraction` finds every requirement it can point at and returns
them all — three degree proposals, two years-of-experience figures, four
graduation years. The gate needs one answer per dimension, and the answer key
holds one label per dimension. This module is the step between, and it is the
only place the resolution rules live so the grader and the gate cannot disagree
about what a posting requires.

**The values here are deliberately the answer key's vocabulary** — `not_stated`,
`bachelors+equivalent`, `through-2028` — rather than a second spelling of the
same ideas. A grader that has to translate between two vocabularies is a grader
that can be wrong in a direction nobody checks, which is exactly the defect
M3a.1 found in `score_sets`.

Nothing here imports the ORM, for the same reason `eligibility_labels` does not:
this gets graded by a test, and a grader that needs a database is a grader that
gets skipped.

Every resolution rule below breaks a tie in the direction that produces fewer
hard blocks. A13: a wrong `ineligible` is the worst output this engine can
produce, and these rules are the first place that choice gets made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from nightshift.domain.requirement_extraction import RequirementProposal

#: The reading's version, distinct from `EXTRACTOR_VERSION`. The extractor can
#: find the same proposals while these rules resolve them differently, and a
#: stored verdict must be able to say which of the two moved.
READING_VERSION = "m3b.1"

#: `Final`, so mypy narrows it to the literal and the two `Literal` return types
#: below accept it. Without the annotation it widens to `str` and both
#: `_resolve_*` functions fail to typecheck — which is the type system noticing
#: that a stringly-typed sentinel is not the same thing as a member of a closed
#: vocabulary.
NOT_STATED: Final = "not_stated"

#: Lowest first. A posting asking for a bachelor's and preferring a master's
#: requires a bachelor's, so the lowest *required* degree is the answer.
DEGREE_ORDER: tuple[str, ...] = ("none", "bachelors", "masters", "phd")

EnrollmentName = Literal["yes", "no", "not_stated"]
SponsorshipName = Literal["offered", "not_offered", "not_stated"]


@dataclass(frozen=True)
class PostingReading:
    """What a posting requires, one value per dimension.

    Field-for-field comparable with :class:`~nightshift.domain.
    eligibility_labels.PostingLabel`, minus the technology lists (graded since
    M3a) and minus `is_internship`, `role_family` and `seniority`, which no rule
    produces yet — they arrive with the classifier.
    """

    degree: str
    graduation_window: str
    min_years_experience: int | None
    enrollment_required: EnrollmentName
    sponsorship: SponsorshipName

    #: Every proposal that contributed, kept so a blocker can quote the posting.
    #: The gate never re-reads the description; it reads these.
    evidence: tuple[RequirementProposal, ...] = ()


def _required(proposals: list[RequirementProposal], kind: str) -> list[RequirementProposal]:
    return [p for p in proposals if p.kind == kind and p.necessity == "required"]


def _resolve_degree(
    proposals: list[RequirementProposal],
) -> tuple[str, tuple[RequirementProposal, ...]]:
    """The **lowest** required degree, `+equivalent` when that one offers it.

    Lowest rather than highest, and the difference is a person's opportunities.
    "Bachelor's degree required, Master's preferred" states one requirement and
    one preference; reading the master's as the requirement would block every
    bachelor's graduate from a role explicitly open to them.

    A degree named only under a preferred heading yields `none`. That is not the
    extractor being lax — the posting genuinely does not require a degree, and
    `RequirementNecessity` exists so this distinction is mechanical rather than
    a judgement made here.

    `+equivalent` is A13's escape hatch and it rides on the winning proposal
    alone. Attaching it from any proposal in the posting would let a preferred
    "PhD or equivalent" soften a hard bachelor's requirement that says nothing
    of the kind.
    """
    candidates = _required(proposals, "degree")
    if not candidates:
        return "none", ()
    lowest = min(candidates, key=lambda p: DEGREE_ORDER.index(p.value))
    # Every proposal naming that same level, so a posting stating it twice
    # quotes whichever sentence the reader lands on first.
    contributing = tuple(p for p in candidates if p.value == lowest.value)
    equivalent = any(p.has_equivalence for p in contributing)
    return f"{lowest.value}+equivalent" if equivalent else lowest.value, contributing


def _resolve_graduation_window(
    proposals: list[RequirementProposal],
) -> tuple[str, tuple[RequirementProposal, ...]]:
    """The widest window any proposal states, or `not_stated`.

    Widest, not narrowest, and for the same reason the degree rule takes the
    lowest: a posting naming 2026 in one sentence and 2027-2028 in another is
    open to all three years, and narrowing it invents a blocker.

    **`through-YYYY` cannot be produced here, and the first version of this
    function pretended otherwise.** That is the answer key's form for an
    open-ended window — "graduating by December 2028", no lower bound — and it
    is 5 of the 60 labels. The first draft tested the words `through|by|before`
    against `RequirementProposal.raw_text`, which for these proposals is the
    matched year and nothing else: `"2027"`, or `"2027-2028"`. The branch could
    never fire, so it was a rule that looked like a decision and was dead code.
    Deleted rather than left in, since removing it changed no number.

    Producing the distinction needs the words *around* the year, which only the
    extractor has. That is Task 5's, not a grader's, and until then these five
    postings read as a closed single-year window and are wrong in the direction
    of a narrower window than the posting states — the direction that invents
    blockers. Recorded in PROGRESS rather than left for the review to find.
    """
    candidates = [p for p in proposals if p.kind == "graduation_window"]
    if not candidates:
        return NOT_STATED, ()
    years: list[int] = []
    for p in candidates:
        years.extend(int(y) for y in re.findall(r"20\d{2}", p.value))
    if not years:
        return NOT_STATED, ()
    return f"{min(years)}-{max(years)}", tuple(candidates)


def _resolve_years(
    proposals: list[RequirementProposal],
) -> tuple[int | None, tuple[RequirementProposal, ...]]:
    """The **smallest** required figure, or `None` for "the posting does not say".

    Smallest because a posting asking for "2+ years of engineering experience"
    and "5+ years of options market making" states one floor to clear and one
    specialism; taking the larger turns a role open to a two-year engineer into
    a blocker.

    `None` is not zero and the two must never merge. Zero is a posting that says
    "no experience required"; `None` is a posting that says nothing, and the
    gate treats them differently — one passes, the other cannot decide.
    """
    candidates = _required(proposals, "years_experience")
    if not candidates:
        return None, ()
    smallest = min(candidates, key=lambda p: int(p.value))
    return int(smallest.value), (smallest,)


def _resolve_enrollment(
    proposals: list[RequirementProposal],
) -> tuple[EnrollmentName, tuple[RequirementProposal, ...]]:
    """`yes` when a required heading governs an enrollment phrase, else `not_stated`.

    **This can never return `no`, and that is a stated gap rather than an
    oversight.** A posting saying "you need not be enrolled" is vanishingly
    rare; the extractor has no rule for it and inventing one against a corpus
    that does not contain the case would be fitting to nothing. The answer key
    labels `no` on 20-odd postings, so this rule's ceiling is visible in its
    grade the moment anybody looks — which is the point of grading it.
    """
    if _required(proposals, "enrollment"):
        return "yes", tuple(_required(proposals, "enrollment"))
    return NOT_STATED, ()


def _resolve_sponsorship(
    proposals: list[RequirementProposal],
) -> tuple[SponsorshipName, tuple[RequirementProposal, ...]]:
    """`offered` beats `not_offered` when a posting somehow says both.

    A tie is not arbitrary here. "We do not sponsor H-1B visas for this role,
    but we do sponsor OPT extensions" is one sentence containing both, and
    resolving it to `not_offered` tells somebody they cannot apply for a role
    that says it will help them. The other error tells them to apply for
    something that will not work out, which they discover in a conversation
    rather than never.
    """
    offered = [
        p for p in proposals if p.kind == "authorization" and p.value == "sponsorship_offered"
    ]
    if offered:
        return "offered", tuple(offered)
    refused = [p for p in proposals if p.kind == "authorization" and p.value == "no_sponsorship"]
    if refused:
        return "not_offered", tuple(refused)
    return NOT_STATED, ()


def read_posting(proposals: list[RequirementProposal]) -> PostingReading:
    """Resolve a posting's proposals into one answer per dimension."""
    degree, degree_evidence = _resolve_degree(proposals)
    window, window_evidence = _resolve_graduation_window(proposals)
    years, years_evidence = _resolve_years(proposals)
    enrollment, enrollment_evidence = _resolve_enrollment(proposals)
    sponsorship, sponsorship_evidence = _resolve_sponsorship(proposals)
    return PostingReading(
        degree=degree,
        graduation_window=window,
        min_years_experience=years,
        enrollment_required=enrollment,
        sponsorship=sponsorship,
        evidence=(
            *degree_evidence,
            *window_evidence,
            *years_evidence,
            *enrollment_evidence,
            *sponsorship_evidence,
        ),
    )
