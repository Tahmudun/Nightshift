"""The one corpus-wide number M3b must drive to zero, asserted as an equality.

Description -> extraction -> reading -> gate, over all 60 labeled postings and a
set of profiles. For every `ineligible` verdict, the **labels** are checked
independently: does what the human recorded about that posting support a hard
block for this person? Where they do not, the pipeline has invented one.

`matching.md` §3.3: a wrong `ineligible` removes an opportunity from the user's
world and reports nothing. Not a rate, not a floor — zero, as an equality.

**This is the exact shape of a test M3a shipped vacuous for a whole milestone.**
`test_no_nice_to_have_is_ever_reported_as_required` reported 0 violations from
its first run to its last, because it compared raw strings and could not see
that `Apache Spark` and `Spark` are the same technology. It was at zero the way
a test that cannot fail is at zero. So the first thing below is a deliberately
broken gate pushed through this machinery, and the count it produces.
"""

from __future__ import annotations

from typing import Any

import pytest

from nightshift.db.base import EligibilityState, WorkAuthorization
from nightshift.domain.eligibility import SeekerProfile, evaluate
from nightshift.domain.eligibility_labels import PostingLabel, load_answer_key
from nightshift.domain.eligibility_reading import DEGREE_ORDER, read_posting
from nightshift.domain.requirement_extraction import extract_requirements
from nightshift.domain.skill_vocabulary import load_vocabulary
from tests.test_requirement_extraction_against_the_answer_key import _corpus_postings

#: Deliberately varied, and every one is a real kind of person this product is
#: for. The undergraduate is the one that matters most: A13's whole concern is
#: a system that quietly hides roles from somebody early in their career.
PROFILES: dict[str, SeekerProfile] = {
    "a 2027 undergraduate, enrolled, needing sponsorship": SeekerProfile(
        graduation_year=2027,
        degree="bachelors",
        is_enrolled=True,
        years_experience=0,
        work_authorization=WorkAuthorization.NEEDS_SPONSORSHIP,
    ),
    "a 2024 graduate with two years and a green card": SeekerProfile(
        graduation_year=2024,
        degree="bachelors",
        is_enrolled=False,
        years_experience=2,
        work_authorization=WorkAuthorization.PERMANENT_RESIDENT,
    ),
    "a PhD with eight years, a citizen": SeekerProfile(
        graduation_year=2018,
        degree="phd",
        is_enrolled=False,
        years_experience=8,
        work_authorization=WorkAuthorization.US_CITIZEN,
    ),
    #: The profile A13's escape hatch exists for. Most `+equivalent` postings in
    #: the corpus ask for a bachelor's, so a bachelor's holder cannot detect a
    #: gate that ignores the hatch — they clear the bar either way. This person
    #: does not, and is exactly who "or equivalent experience" is addressed to.
    "a self-taught engineer with no degree and four years": SeekerProfile(
        degree="none",
        is_enrolled=False,
        years_experience=4,
        work_authorization=WorkAuthorization.US_CITIZEN,
    ),
    "somebody who has filled in nothing": SeekerProfile(),
}


def _labels_support_a_hard_block(label: PostingLabel, profile: SeekerProfile) -> list[str]:
    """Reasons the *human's own labels* justify blocking this person.

    Written from the answer key rather than from `eligibility.py`, on purpose.
    If it called the gate it would agree with the gate by construction and this
    file would assert nothing — which is precisely how M3a's version came to be
    vacuous. Any disagreement between the two is a finding.
    """
    reasons: list[str] = []

    # Degree. `+equivalent` is A13's escape hatch and can never justify a block.
    if label.degree != "none" and not label.has_degree_equivalence:
        required = label.degree
        if profile.degree is not None and DEGREE_ORDER.index(profile.degree) < DEGREE_ORDER.index(
            required
        ):
            reasons.append(f"degree: posting wants {required}, person has {profile.degree}")

    # Graduation window.
    if label.graduation_window != "not_stated" and profile.graduation_year is not None:
        window = label.graduation_window
        if window.startswith("through-"):
            earliest, latest = 0, int(window.removeprefix("through-"))
        else:
            lo, _, hi = window.partition("-")
            earliest, latest = int(lo), int(hi)
        if not earliest <= profile.graduation_year <= latest:
            reasons.append(
                f"graduation: posting wants {window}, person has {profile.graduation_year}"
            )

    # Enrollment.
    if label.enrollment_required == "yes" and profile.is_enrolled is False:
        reasons.append("enrollment: posting requires it, person is not enrolled")

    # Authorization. Both halves must be explicit.
    if (
        label.sponsorship == "not_offered"
        and profile.work_authorization == WorkAuthorization.NEEDS_SPONSORSHIP
    ):
        reasons.append("authorization: posting does not sponsor, person needs it")

    # Years is deliberately absent: it may never hard-block (see `_years_rule`),
    # so a years shortfall can never justify an `ineligible` here either.
    return reasons


@pytest.fixture(scope="module")
def verdicts() -> list[dict[str, Any]]:
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()
    rows: list[dict[str, Any]] = []
    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            reading = read_posting(
                extract_requirements(postings[board][posting_id], vocabulary=vocab)
            )
            for who, profile in PROFILES.items():
                rows.append(
                    {
                        "where": f"{board.replace('_eligibility', '')}/{posting_id}",
                        "who": who,
                        "label": label,
                        "profile": profile,
                        "verdict": evaluate(reading, profile),
                    }
                )
    return rows


def test_no_posting_is_wrongly_reported_ineligible(verdicts: list[dict[str, Any]]) -> None:
    """Zero, as an equality. The number this milestone exists to hold down."""
    wrong = [
        f"{row['where']} x {row['who']}: gate blocked on "
        f"{[b.dimension for b in row['verdict'].blockers]} but the labels support nothing"
        for row in verdicts
        if row["verdict"].state is EligibilityState.INELIGIBLE
        and not _labels_support_a_hard_block(row["label"], row["profile"])
    ]
    assert wrong == [], wrong


def test_this_check_can_fail(verdicts: list[dict[str, Any]]) -> None:
    """A deliberately broken gate, pushed through the same machinery.

    Without this the assertion above is a claim about the gate *and* a claim
    about the checker, and only one of them is being tested. M3a shipped a
    violation count stuck at zero for a milestone because nobody made the second
    claim.

    The break is realistic rather than absurd: a gate that treats `+equivalent`
    as a plain degree requirement, which is the single most likely regression
    here and the exact failure A13 names.

    **The profile has to be the one without a degree**, and the first version of
    this test got that wrong — it used a bachelor's holder, the break produced
    zero wrong ineligibles, and the test failed for its own reason rather than
    the gate's. Most `+equivalent` postings in the corpus ask for a bachelor's,
    so a bachelor's holder clears the bar whether the hatch is honoured or not
    and cannot see the difference. The person the hatch is addressed to is the
    one with no degree at all.
    """
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()
    no_degree_holder = PROFILES["a self-taught engineer with no degree and four years"]

    would_be_wrong = 0
    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            if not label.has_degree_equivalence:
                continue
            reading = read_posting(
                extract_requirements(postings[board][posting_id], vocabulary=vocab)
            )
            # The break: strip the escape hatch and re-run.
            stripped = type(reading)(
                degree=reading.degree.removesuffix("+equivalent"),
                graduation_window=reading.graduation_window,
                min_years_experience=reading.min_years_experience,
                enrollment_required=reading.enrollment_required,
                sponsorship=reading.sponsorship,
                evidence=reading.evidence,
            )
            broken = evaluate(stripped, no_degree_holder)
            if broken.state is EligibilityState.INELIGIBLE and not _labels_support_a_hard_block(
                label, no_degree_holder
            ):
                would_be_wrong += 1

    assert would_be_wrong > 0, (
        "removing A13's equivalence escape hatch produced no wrong ineligibles, "
        "so the check above cannot distinguish a working gate from a broken one"
    )


def test_the_corpus_actually_exercises_the_gate(verdicts: list[dict[str, Any]]) -> None:
    """A gate that answered `uncertain` to everything would pass every assertion
    in this file. `matching.md` §3.3 says so directly: perfect precision and
    worthless.

    So the states the corpus actually produces are printed and asserted to be
    more than one. This is the guard against the *other* failure — the one that
    looks like caution and is really silence.
    """
    seen = {row["verdict"].state for row in verdicts}
    assert len(seen) > 1, f"the gate produced only {seen} across the whole corpus"
    assert EligibilityState.ELIGIBLE in seen, "nothing came out eligible; the gate is not deciding"


def test_report_the_distribution(verdicts: list[dict[str, Any]], capsys: Any) -> None:
    """Always passes. Run with `-s`."""
    from collections import Counter

    with capsys.disabled():
        postings = len({row["where"] for row in verdicts})
        print(f"\n  eligibility verdicts, {postings} postings x {len(PROFILES)} profiles\n")
        for who in PROFILES:
            counts = Counter(row["verdict"].state.value for row in verdicts if row["who"] == who)
            line = "  ".join(f"{state} {n}" for state, n in sorted(counts.items()))
            print(f"  {who:<52} {line}")
        print()
