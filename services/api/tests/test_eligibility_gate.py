"""The gate, one rule at a time, and all six of A13's hard cases by name.

`matching.md` §8: every eligibility rule has a fixture, and a rule with no case
exercising it is a rule with no test.

These are fixtures rather than a metric, deliberately. The gate is a pure
function of (posting reading x profile); grading it over the corpus would
measure the extractor and the rules at once and attribute nothing to either.
The corpus-level number that *does* belong to this milestone is the
wrong-ineligible count, and it lives in
`test_no_posting_is_wrongly_reported_ineligible.py`.

**The direction under test throughout is A13's**: a wrong `ineligible` deletes
an opportunity from somebody's world and reports nothing. Most of what follows
asserts that some plausible-looking input does *not* produce one.
"""

from __future__ import annotations

import pytest

from nightshift.db.base import EligibilityState, WorkAuthorization
from nightshift.domain.eligibility import SeekerProfile, evaluate
from nightshift.domain.eligibility_reading import PostingReading
from nightshift.domain.requirement_extraction import RequirementProposal


def reading(**overrides: object) -> PostingReading:
    """A posting that asks for nothing, plus whatever the case is about.

    Defaulting to "requires nothing" rather than to a filled-in posting is the
    point: every field a case does not mention is one the posting is silent
    about, so each test exercises exactly one rule and a failure names it.
    """
    base: dict[str, object] = {
        "degree": "none",
        "graduation_window": "not_stated",
        "min_years_experience": None,
        "enrollment_required": "not_stated",
        "sponsorship": "not_stated",
        "evidence": (),
    }
    return PostingReading(**{**base, **overrides})  # type: ignore[arg-type]


NOBODY = SeekerProfile()
"""A profile with nothing filled in — the state every user starts in."""


# ---------------------------------------------------------------------------
# The empty profile. This is the first thing a new user sees, and getting it
# wrong would block them out of the entire product on day one.
# ---------------------------------------------------------------------------


def test_a_posting_that_asks_for_nothing_is_eligible_for_a_person_who_says_nothing() -> None:
    verdict = evaluate(reading(), NOBODY)
    assert verdict.state is EligibilityState.ELIGIBLE
    assert verdict.blockers == ()
    assert verdict.unknowns == ()


def test_an_empty_profile_is_never_ineligible_however_demanding_the_posting() -> None:
    """Every rule at once, against a person who has told us nothing.

    Not one of these may block. A profile with no data is not a profile that
    fails a requirement — it is one we cannot check, and the difference is the
    whole of invariant I2.
    """
    demanding = reading(
        degree="phd",
        graduation_window="2020-2021",
        min_years_experience=15,
        enrollment_required="yes",
        sponsorship="not_offered",
    )
    verdict = evaluate(demanding, NOBODY)

    assert verdict.state is EligibilityState.UNCERTAIN
    assert verdict.blockers == ()
    assert {u.dimension for u in verdict.unknowns} == {
        "degree",
        "graduation_window",
        "years_experience",
        "enrollment",
        "authorization",
    }


def test_every_unknown_names_the_profile_field_that_would_resolve_it() -> None:
    """An unknown is an action, not a rejection, and it has to point somewhere.

    "Complete your profile" is not an action. "Tell us your graduation year" is.
    """
    verdict = evaluate(reading(graduation_window="2026-2027"), NOBODY)
    assert [(u.dimension, u.profile_field) for u in verdict.unknowns] == [
        ("graduation_window", "graduation_year")
    ]


# ---------------------------------------------------------------------------
# A13's six hard cases, by name.
# ---------------------------------------------------------------------------


def test_a13_an_intern_posting_demanding_three_years_does_not_block_a_student() -> None:
    """A13's first case: a posting titled "Intern" containing "3+ years required".

    The employer has written two contradictory things in one document. The
    resolution is that a years shortfall may never hard-block — it reaches
    `likely_ineligible` and stops there — so the student still sees the role,
    still sees the gap, and decides.
    """
    verdict = evaluate(
        reading(min_years_experience=3, enrollment_required="yes"),
        SeekerProfile(years_experience=0, is_enrolled=True),
    )
    assert verdict.state is EligibilityState.LIKELY_INELIGIBLE
    assert verdict.state is not EligibilityState.INELIGIBLE
    assert [b.dimension for b in verdict.blockers] == ["years_experience"]
    assert verdict.blockers[0].outcome == "soft_blocks"


def test_a13_a_graduation_window_stated_in_prose_still_gates_on_the_year() -> None:
    """A13's second case. The prose is the extractor's problem; by the time it
    reaches here it is a window, and the gate's job is to compare honestly."""
    inside = evaluate(reading(graduation_window="2026-2027"), SeekerProfile(graduation_year=2027))
    outside = evaluate(reading(graduation_window="2026-2027"), SeekerProfile(graduation_year=2024))
    assert inside.state is EligibilityState.ELIGIBLE
    assert outside.state is EligibilityState.INELIGIBLE


def test_a13_an_open_ended_window_does_not_block_someone_who_graduated_earlier() -> None:
    """`through-2028` has no lower bound, so 2019 is inside it.

    The rule that reads an open window as a closed one blocks every experienced
    applicant to a "graduating by 2028" posting, which is the opposite of what
    that posting is saying.
    """
    verdict = evaluate(
        reading(graduation_window="through-2028"), SeekerProfile(graduation_year=2019)
    )
    assert verdict.state is EligibilityState.ELIGIBLE


def test_a13_an_experience_requirement_under_preferred_never_reaches_the_gate() -> None:
    """A13's third case, and it is settled one layer up rather than here.

    `_resolve_years` only considers proposals whose necessity is `required`, so
    a years figure sitting under "Preferred qualifications" never becomes
    `min_years_experience` at all. Asserted from the reading side, because a
    test that constructed the reading by hand would assert nothing about the
    thing that actually prevents it.
    """
    from nightshift.domain.eligibility_reading import read_posting

    preferred_only = read_posting(
        [
            RequirementProposal(
                kind="years_experience",
                value="8",
                raw_text="8 years",
                char_start=10,
                char_end=17,
                necessity="preferred",
            )
        ]
    )
    assert preferred_only.min_years_experience is None
    assert evaluate(preferred_only, SeekerProfile(years_experience=1)).state is (
        EligibilityState.ELIGIBLE
    )


def test_a13_bachelors_or_equivalent_is_uncertain_and_never_ineligible() -> None:
    """A13's fourth case, quoted in the amendment itself.

    "You hold a PhD in Computer Science... (or have equivalent experience)". A
    rule that matches `phd` and stops has permanently removed that role from a
    self-taught engineer's world. `has_equivalence` has been stored since M3a
    for exactly this and until now was read by nothing.
    """
    verdict = evaluate(reading(degree="phd+equivalent"), SeekerProfile(degree="bachelors"))
    assert verdict.state is EligibilityState.UNCERTAIN
    assert verdict.blockers == ()

    # ...and the same posting without the escape hatch does block.
    strict = evaluate(reading(degree="phd"), SeekerProfile(degree="bachelors"))
    assert strict.state is EligibilityState.INELIGIBLE


def test_a13_a_multi_level_posting_is_not_a_case_this_corpus_can_support() -> None:
    """A13's fifth case: "Software Engineer I/II" spanning an eligibility boundary.

    **This fixture is constructed, not drawn from a recorded payload**, and that
    is stated rather than hidden. `matching.md` §3.6 measured it: a posting
    spanning an eligibility boundary is absent from eight of the nine boards, so
    the answer key can say least about the case A13 calls hardest.

    What the gate can do is not invent a boundary the reading did not give it.
    A posting read as requiring 2 years does not become a 5-year posting because
    its title says "I/II", and the reading takes the *lowest* stated figure for
    exactly this reason.
    """
    spanning = reading(min_years_experience=2)
    assert evaluate(spanning, SeekerProfile(years_experience=2)).state is (
        EligibilityState.ELIGIBLE
    )


def test_a13_a_return_offer_internship_gates_on_enrollment_not_on_the_title() -> None:
    """A13's sixth case. The gate never reads a title — only what was extracted."""
    verdict = evaluate(
        reading(enrollment_required="yes"), SeekerProfile(is_enrolled=False, graduation_year=2024)
    )
    assert verdict.state is EligibilityState.INELIGIBLE
    assert [b.dimension for b in verdict.blockers] == ["enrollment"]


# ---------------------------------------------------------------------------
# Authorization — the rule with the highest cost of being wrong.
# ---------------------------------------------------------------------------


def test_unspecified_authorization_is_not_a_claim_and_never_blocks() -> None:
    """`unspecified` is the column default and most users' day-one value.

    Reading it as "needs sponsorship" would block every one of them out of every
    posting that says it does not sponsor, silently, before they have typed
    anything.
    """
    verdict = evaluate(reading(sponsorship="not_offered"), NOBODY)
    assert verdict.state is EligibilityState.UNCERTAIN
    assert verdict.blockers == ()


@pytest.mark.parametrize(
    "authorization",
    [
        WorkAuthorization.US_CITIZEN,
        WorkAuthorization.PERMANENT_RESIDENT,
        WorkAuthorization.OTHER_AUTHORIZED,
    ],
)
def test_a_no_sponsorship_posting_passes_anyone_who_does_not_need_it(
    authorization: WorkAuthorization,
) -> None:
    verdict = evaluate(
        reading(sponsorship="not_offered"), SeekerProfile(work_authorization=authorization)
    )
    assert verdict.state is EligibilityState.ELIGIBLE


def test_the_one_configuration_that_blocks_on_authorization() -> None:
    """Both halves explicit: the posting says so in writing, the person said so.

    This is the only place in the gate where "this will not work" is a fact
    rather than a guess, and it is worth having exactly one test that says so.
    """
    verdict = evaluate(
        reading(sponsorship="not_offered"),
        SeekerProfile(work_authorization=WorkAuthorization.NEEDS_SPONSORSHIP),
    )
    assert verdict.state is EligibilityState.INELIGIBLE
    assert [b.dimension for b in verdict.blockers] == ["authorization"]


def test_an_f1_student_is_not_assumed_to_need_sponsorship() -> None:
    """`f1_student` and `needs_sponsorship` are different answers to different
    questions, and an F-1 student on OPT does not need sponsorship today.

    Inferring one from the other is the fabrication I2 forbids, in the field
    where being wrong is most consequential.
    """
    verdict = evaluate(
        reading(sponsorship="not_offered"),
        SeekerProfile(work_authorization=WorkAuthorization.F1_STUDENT),
    )
    assert verdict.state is not EligibilityState.INELIGIBLE


# ---------------------------------------------------------------------------
# The verdict's own shape.
# ---------------------------------------------------------------------------


def test_a_blocker_quotes_the_posting_and_carries_its_span() -> None:
    """I4: no claim without its evidence. The span comes from extraction time,
    so the gate can quote a posting it never read."""
    with_evidence = reading(
        degree="phd",
        evidence=(
            RequirementProposal(
                kind="degree",
                value="phd",
                raw_text="Ph.D.",
                char_start=120,
                char_end=125,
                necessity="required",
            ),
        ),
    )
    verdict = evaluate(with_evidence, SeekerProfile(degree="bachelors"))
    blocker = verdict.blockers[0]
    assert blocker.posting_says == "Ph.D."
    assert blocker.posting_span == (120, 125)
    assert blocker.profile_says == "bachelors"
    assert "requires a phd" in blocker.why


def test_a_hard_blocker_outranks_a_soft_one() -> None:
    """Both present: the state is `ineligible`, and **both** blockers are shown.

    Showing only the hard one would hide a second reason the person might want
    to know about, and this project's habit is to name everything it found.
    """
    verdict = evaluate(
        reading(degree="phd", min_years_experience=10),
        SeekerProfile(degree="bachelors", years_experience=1),
    )
    assert verdict.state is EligibilityState.INELIGIBLE
    assert {b.dimension for b in verdict.blockers} == {"degree", "years_experience"}


def test_a_blocker_outranks_an_unknown() -> None:
    """A known blocker with an unanswered question elsewhere is still ineligible.

    The unknown is still reported — resolving it may not change this verdict,
    but a person is entitled to see everything the gate could not settle.
    """
    verdict = evaluate(
        reading(degree="phd", graduation_window="2026-2027"), SeekerProfile(degree="bachelors")
    )
    assert verdict.state is EligibilityState.INELIGIBLE
    assert [b.dimension for b in verdict.blockers] == ["degree"]
    assert [u.dimension for u in verdict.unknowns] == ["graduation_window"]


def test_the_verdict_carries_its_ruleset_version() -> None:
    """M3's acceptance criterion: identical inputs plus identical version means
    identical output, which requires the version to travel with the answer."""
    assert evaluate(reading(), NOBODY).gate_version == "m3b.1"


def test_the_same_inputs_produce_the_same_verdict_twice() -> None:
    """No clock, no randomness, no I/O. Cheap to assert and the whole basis of
    the determinism criterion."""
    posting = reading(degree="masters", min_years_experience=4, sponsorship="not_offered")
    person = SeekerProfile(degree="bachelors", years_experience=2)
    assert evaluate(posting, person) == evaluate(posting, person)


def test_seniority_is_not_an_input_to_the_gate() -> None:
    """`matching.md` §5.1 makes a seniority mismatch a score penalty, M3c's.

    A senior title is not a legal barrier and treating one as a blocker is
    precisely the wrong-`ineligible` A13 ranks worst. Asserted by the absence of
    the field from the two dataclasses the gate consumes, so adding it means
    changing this test on purpose.
    """
    import dataclasses

    posting_fields = {f.name for f in dataclasses.fields(PostingReading)}
    profile_fields = {f.name for f in dataclasses.fields(SeekerProfile)}
    assert "seniority" not in posting_fields | profile_fields
    assert "role_family" not in posting_fields | profile_fields
