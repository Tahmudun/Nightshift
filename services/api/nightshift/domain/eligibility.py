"""The deterministic eligibility gate: what a posting requires, met by a person.

The first thing in this system that makes a claim about somebody. Everything
before it made claims about the world — this board listed these jobs, this
posting names these locations — which are checkable against a recorded payload.
A verdict is different in kind, and there is no payload to check it against.

**A13, and it governs every line below: a wrong `ineligible` is the worst
output this engine can produce.** Every other error is visible next to its own
explanation. A wrong `ineligible` deletes an opportunity from somebody's world
and reports nothing; they never learn it existed. So every rule here breaks ties
away from blocking, and the module is arranged so that doing the *unsafe* thing
requires writing a new branch rather than forgetting one.

Pure, and importing no ORM — the same rule `eligibility_labels` and
`eligibility_reading` follow. It takes a `PostingReading` and a `SeekerProfile`
and returns a verdict; nothing here reads a database, and nothing here reads
`jobs.description_text` either. The spans it quotes were stored at extraction
time, so a blocker can always show the posting's own words.

Nothing is stored. `match_results` is M3c's table (`matching.md` §4.2), and a
stored verdict goes stale the moment a person edits their graduation year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nightshift.db.base import EligibilityState, WorkAuthorization
from nightshift.domain.eligibility_reading import DEGREE_ORDER, PostingReading
from nightshift.domain.requirement_extraction import RequirementProposal

#: Bumped when a rule changes. `matching.md` §4.2 composes this with the
#: reading's and the extractor's versions onto every stored verdict at M3c.
GATE_VERSION = "m3b.1"

#: What one rule concluded about one dimension.
#:
#: `blocks` requires two things at once — the posting states the requirement
#: under a **required** heading, *and* the person's **confirmed** profile
#: contradicts it. Either half missing is `cannot_tell`. That is invariant I2
#: doing the work: an inferred fact never blocks anybody, because an inferred
#: fact is not a fact.
Outcome = Literal["passes", "blocks", "soft_blocks", "cannot_tell", "not_applicable"]

#: The dimensions a rule can speak about. `seniority` is deliberately absent:
#: `matching.md` §5.1 makes a seniority mismatch a score *penalty*, which is
#: M3c. A senior title is not a legal barrier, and treating one as a blocker is
#: precisely the wrong-`ineligible` A13 ranks worst.
Dimension = Literal[
    "degree", "graduation_window", "years_experience", "enrollment", "authorization"
]


@dataclass(frozen=True)
class SeekerProfile:
    """Only confirmed facts (invariant I2).

    Every field is optional and `None` means "this person has not told us",
    which is a different thing from a negative answer and never resolves to one.
    Built from `users` columns that `domain/profile.py` is the sole writer of;
    nothing inferred reaches here, and `test_nothing_infers.py` is what keeps
    that true one layer up.
    """

    graduation_year: int | None = None
    graduation_month: int | None = None
    #: The highest degree held or in progress, from `DEGREE_ORDER`.
    degree: str | None = None
    work_authorization: WorkAuthorization = WorkAuthorization.UNSPECIFIED
    years_experience: int | None = None
    #: Whether the person is currently enrolled in a degree programme.
    is_enrolled: bool | None = None


@dataclass(frozen=True)
class Blocker:
    """One reason a posting might not be open to this person, with its evidence.

    I4's rule applied to a verdict rather than a score: the dimension, the
    posting's own words and where they are, what the profile says, and one
    sentence a human reads. A bare state with no breakdown is a bug.
    """

    dimension: Dimension
    outcome: Outcome
    #: The posting's words. `None` only when the *absence* of a statement is the
    #: finding, which happens for no rule today and is typed for M3c's sake.
    posting_says: str | None
    posting_span: tuple[int, int] | None
    profile_says: str
    why: str


@dataclass(frozen=True)
class Unknown:
    """A profile field whose absence stopped a rule from deciding.

    Kept separate from `Blocker` because they mean opposite things to a person.
    A blocker says "this posting is probably not for you"; an unknown says "tell
    us one more thing and we can answer". Rendering them the same way turns an
    action into a rejection.
    """

    dimension: Dimension
    #: The `users` column to ask for, so the UI can link to the right field.
    profile_field: str
    why: str


@dataclass(frozen=True)
class EligibilityVerdict:
    state: EligibilityState
    blockers: tuple[Blocker, ...]
    unknowns: tuple[Unknown, ...]
    gate_version: str = GATE_VERSION


def _evidence(reading: PostingReading, kind: str) -> RequirementProposal | None:
    for proposal in reading.evidence:
        if proposal.kind == kind:
            return proposal
    return None


def _quote(reading: PostingReading, kind: str) -> tuple[str | None, tuple[int, int] | None]:
    proposal = _evidence(reading, kind)
    if proposal is None:
        return None, None
    return proposal.raw_text, (proposal.char_start, proposal.char_end)


# ---------------------------------------------------------------------------
# The rules. Each returns (outcome, why), and each is asked exactly once.
# ---------------------------------------------------------------------------


def _degree_rule(reading: PostingReading, profile: SeekerProfile) -> tuple[Outcome, str]:
    """A13's escape hatch is the first thing checked, and it always wins.

    "Bachelor's degree **or equivalent experience**" is not a hard blocker, and
    a rule that matches `bachelors` and stops has permanently removed that role
    from somebody's world. `+equivalent` therefore demotes what would have been
    a block to `cannot_tell` — never to a pass, because the posting did ask for
    something, and never to a block, because it said the degree is not the only
    way in.
    """
    required = reading.degree
    if required == "none":
        return "passes", "the posting requires no degree"

    if required.endswith("+equivalent"):
        return (
            "cannot_tell",
            "the posting accepts equivalent experience in place of the degree, "
            "which is not something this system can assess",
        )

    if profile.degree is None:
        return "cannot_tell", "the posting states a degree requirement and your profile has none"

    held = DEGREE_ORDER.index(profile.degree)
    asked = DEGREE_ORDER.index(required)
    if held >= asked:
        return "passes", f"the posting asks for a {required} and your profile says {profile.degree}"
    return (
        "blocks",
        f"the posting requires a {required} and your profile says {profile.degree}",
    )


def _graduation_rule(reading: PostingReading, profile: SeekerProfile) -> tuple[Outcome, str]:
    """A window is a range of years, and being outside it is a real blocker.

    The one care needed: `through-YYYY` is an open-ended window with no lower
    bound, so graduating *earlier* than it is inside it, not outside. Reading an
    open window as a closed one blocks every experienced applicant to a
    "graduating by 2028" posting, which is the opposite of what that posting
    says.

    That is not hypothetical. This branch was written before the extractor could
    produce the form, and on its first corpus run the gate blocked a 2024
    graduate from Akuna's "Must be graduating August 2027 **or prior**" —
    because the reading had flattened it to the single year 2027. The extractor
    now makes the distinction (`_is_open_ended`) and the reading preserves it.
    """
    window = reading.graduation_window
    if window == "not_stated":
        return "passes", "the posting states no graduation window"
    if profile.graduation_year is None:
        return (
            "cannot_tell",
            f"the posting wants a graduation date in {window} and your profile has none",
        )

    if window.startswith("through-"):
        latest = int(window.removeprefix("through-"))
        earliest = 0
    else:
        earliest_text, _, latest_text = window.partition("-")
        earliest, latest = int(earliest_text), int(latest_text)

    if earliest <= profile.graduation_year <= latest:
        return "passes", f"you graduate in {profile.graduation_year}, inside {window}"
    return (
        "blocks",
        f"the posting wants a graduation date in {window} and yours is {profile.graduation_year}",
    )


def _years_rule(reading: PostingReading, profile: SeekerProfile) -> tuple[Outcome, str]:
    """A years shortfall never hard-blocks. It is the softest rule here.

    Deliberate, and it is the rule most likely to be argued with. "5+ years" is
    a wish far more often than a rule — employers hire below their stated
    minimum constantly, and nothing about a years figure is checkable the way a
    graduation date is. A13's first hard case is a posting titled "Intern" that
    says "3+ years of experience required", which is the same employer writing
    two contradictory things in one document.

    So this returns `soft_blocks`, which reaches `likely_ineligible` and never
    `ineligible`. The person still sees the posting, still sees the gap, and
    decides for themselves.
    """
    required = reading.min_years_experience
    if required is None:
        return "passes", "the posting states no experience minimum"
    if profile.years_experience is None:
        return (
            "cannot_tell",
            f"the posting asks for {required}+ years and your profile does not say",
        )
    if profile.years_experience >= required:
        return (
            "passes",
            f"the posting asks for {required}+ years and your profile says "
            f"{profile.years_experience}",
        )
    return (
        "soft_blocks",
        f"the posting asks for {required}+ years and your profile says {profile.years_experience}",
    )


def _enrollment_rule(reading: PostingReading, profile: SeekerProfile) -> tuple[Outcome, str]:
    """Enrollment is checkable and categorical, so it may hard-block.

    Unlike years, this is not a matter of degree: an internship that requires
    you to be a registered student is closed to somebody who graduated two years
    ago, and saying so is useful rather than discouraging.
    """
    if reading.enrollment_required != "yes":
        return "passes", "the posting does not require you to be enrolled"
    if profile.is_enrolled is None:
        return (
            "cannot_tell",
            "the posting requires current enrollment and your profile does not say",
        )
    if profile.is_enrolled:
        return "passes", "the posting requires current enrollment and you are enrolled"
    return "blocks", "the posting requires current enrollment and your profile says you are not"


def _authorization_rule(reading: PostingReading, profile: SeekerProfile) -> tuple[Outcome, str]:
    """The rule with the highest cost of being wrong, so it blocks least.

    It hard-blocks in exactly one situation: the posting says in writing that it
    does not sponsor, **and** the person has said they need sponsorship. Both
    halves are explicit statements — one quoted from the posting, one typed by
    the person — and that is the only configuration where "this will not work"
    is a fact rather than a guess.

    `unspecified` is the default `work_authorization` and it is not a claim.
    Reading it as "needs sponsorship" would silently block every user who has
    not filled in that field, which is most of them on day one.
    """
    if reading.sponsorship != "not_offered":
        return "passes", "the posting does not rule out sponsorship"
    if profile.work_authorization == WorkAuthorization.UNSPECIFIED:
        return (
            "cannot_tell",
            "the posting does not sponsor and your profile does not state your "
            "authorization status",
        )
    if profile.work_authorization == WorkAuthorization.NEEDS_SPONSORSHIP:
        return (
            "blocks",
            "the posting states it does not sponsor and your profile says you need sponsorship",
        )
    return "passes", "the posting does not sponsor, and your profile says you do not need it"


#: The profile field each rule asks for when it cannot decide, so an `unknown`
#: can link somewhere useful instead of saying "fill in your profile".
_ASKS_FOR: dict[Dimension, str] = {
    "degree": "degree",
    "graduation_window": "graduation_year",
    "years_experience": "years_experience",
    "enrollment": "is_enrolled",
    "authorization": "work_authorization",
}

_RULES: tuple[tuple[Dimension, str, object], ...] = (
    ("degree", "degree", _degree_rule),
    ("graduation_window", "graduation_window", _graduation_rule),
    ("years_experience", "years_experience", _years_rule),
    ("enrollment", "enrollment", _enrollment_rule),
    ("authorization", "authorization", _authorization_rule),
)


def evaluate(reading: PostingReading, profile: SeekerProfile) -> EligibilityVerdict:
    """One verdict, its blockers and its unknowns.

    The composition runs in exactly one direction and the order is the rule:

        any blocks       -> ineligible
        else any soft    -> likely_ineligible
        else any cannot  -> uncertain
        else                eligible

    There is no branch producing `likely_eligible` and that is not an omission.
    It would mean "every rule passed, but one of them leaned on something we are
    not certain of" — and no rule here passes on an uncertain input; each returns
    `cannot_tell` instead. Inventing a fifth state that no rule can reach would
    be shape with no use, and the enum keeps the member because PRODUCT-SPEC
    §8.3 names it and M3c's score components may earn it.
    """
    blockers: list[Blocker] = []
    unknowns: list[Unknown] = []
    outcomes: list[Outcome] = []

    for dimension, evidence_kind, rule in _RULES:
        outcome, why = rule(reading, profile)  # type: ignore[operator]
        outcomes.append(outcome)
        if outcome in ("blocks", "soft_blocks"):
            says, span = _quote(reading, evidence_kind)
            blockers.append(
                Blocker(
                    dimension=dimension,
                    outcome=outcome,
                    posting_says=says,
                    posting_span=span,
                    profile_says=_profile_summary(dimension, profile),
                    why=why,
                )
            )
        elif outcome == "cannot_tell":
            unknowns.append(
                Unknown(dimension=dimension, profile_field=_ASKS_FOR[dimension], why=why)
            )

    if "blocks" in outcomes:
        state = EligibilityState.INELIGIBLE
    elif "soft_blocks" in outcomes:
        state = EligibilityState.LIKELY_INELIGIBLE
    elif "cannot_tell" in outcomes:
        state = EligibilityState.UNCERTAIN
    else:
        state = EligibilityState.ELIGIBLE

    return EligibilityVerdict(state=state, blockers=tuple(blockers), unknowns=tuple(unknowns))


def _profile_summary(dimension: Dimension, profile: SeekerProfile) -> str:
    """What the person's own data says, for the blocker to show beside the quote."""
    if dimension == "degree":
        return profile.degree or "not stated"
    if dimension == "graduation_window":
        return str(profile.graduation_year) if profile.graduation_year else "not stated"
    if dimension == "years_experience":
        return (
            f"{profile.years_experience} years"
            if profile.years_experience is not None
            else "not stated"
        )
    if dimension == "enrollment":
        if profile.is_enrolled is None:
            return "not stated"
        return "enrolled" if profile.is_enrolled else "not enrolled"
    return profile.work_authorization.value


def profile_from_user(user: object) -> SeekerProfile:
    """Build a gate profile from a `users` row.

    A free function taking `object` rather than a method on the model, because
    this module may not import the ORM — the same rule that keeps it gradeable
    by a test with no database. The caller passes the row; only attribute reads
    happen here.

    **Every field is copied, never derived.** `graduation_year` is right there
    and `years_experience` could be guessed from it with one subtraction, which
    is precisely the inference invariant I2 forbids and precisely the one that
    would look reasonable in review.
    """
    return SeekerProfile(
        graduation_year=getattr(user, "graduation_year", None),
        graduation_month=getattr(user, "graduation_month", None),
        degree=_degree_of(getattr(user, "degree", None)),
        work_authorization=getattr(user, "work_authorization", WorkAuthorization.UNSPECIFIED),
        years_experience=getattr(user, "years_experience", None),
        is_enrolled=getattr(user, "is_enrolled", None),
    )


def _degree_of(text: str | None) -> str | None:
    """`users.degree` is free text a person typed; the gate needs a level.

    Returns `None` — "we cannot tell" — for anything unrecognised, which is the
    safe direction: an unreadable degree string must never become a level low
    enough to block somebody, and must never become one high enough to pass them
    either. `None` reaches `cannot_tell` and the person is asked.

    **Whole words only.** A substring test for "bs" matches "jobs" and "ba"
    matches "database", which is the same defect that made `react` a required
    technology on eight postings at M3a.1. Checked highest-first, so "BS/MS" is
    a master's rather than a bachelor's — the person's *highest* level is what
    a requirement is compared against.
    """
    if not text:
        return None
    for level, pattern in (
        ("phd", r"\b(?:ph\.?\s?d|doctorate|doctoral)\b"),
        ("masters", r"\b(?:master'?s?|masters|m\.?sc|m\.?s|m\.?eng|mba)\b"),
        ("bachelors", r"\b(?:bachelor'?s?|bachelors|b\.?sc|b\.?s|b\.?a|b\.?eng|undergraduate)\b"),
    ):
        if re.search(pattern, text, re.I):
            return level
    return None
