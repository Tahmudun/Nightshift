"""Which season an internship is for, read from the title and nowhere else.

Every case below is a title from the recorded corpus except the two marked
constructed, and the shape of the two columns was decided by measuring it
rather than by taste.

**The measurement, over all 153 recorded postings.** 19 are internships by
title. Of those:

    a season in the title        8 / 19     every one of them "Summer"
    a year in the title         10 / 19
    both                         8 / 19
    neither                      7 / 19

**That is what rules out a single `summer_2027` column.** Two postings state a
year and no season -- Old Mission's *"Software Engineer 2027 Internship Program
(June Start)"* and Point72's *"2026 Warsaw MI Data Web Scraping Internship"* --
and a combined value can hold them only by inventing a season or by discarding
the year. Both are things this project does not do to a fact it was given. So:
two nullable columns, and null keeps meaning the posting did not say.

The M3b plan predicted "4 of 5 internships state a season in the title". That
was read off the five internships in the *answer key*; across the whole corpus
it is 8 of 19, and the plan's shape question came out differently because of it.

The en dashes in the titles below are the employers' own and are kept verbatim,
with `noqa: RUF001` rather than a hyphen substitution. A test asserting against
a title nobody wrote is a test about a posting that does not exist -- and it was
exactly a typographic character standing in for its ASCII lookalike that cost
this project 21 of 26 degree errors at Task 5.
"""

from __future__ import annotations

import pytest

from nightshift.db.base import InternshipSeason
from nightshift.domain.role_classification import classify_role


def season_of(title: str, description: str = "") -> tuple[InternshipSeason | None, int | None]:
    result = classify_role(title, description=description)
    return result.internship_season, result.internship_year


# ---------------------------------------------------------------------------
# What the corpus states
# ---------------------------------------------------------------------------


def test_a_title_stating_both_yields_both() -> None:
    assert season_of("Hardware Engineer Intern, Summer 2027") == (InternshipSeason.SUMMER, 2027)


def test_a_parenthesised_season_reads_the_same_way() -> None:
    """Databricks writes it in brackets; Akuna writes it after a comma."""
    assert season_of("Product Management Intern (Summer 2027)") == (InternshipSeason.SUMMER, 2027)


def test_a_leading_year_is_found_as_readily_as_a_trailing_one() -> None:
    """Point72 puts the year first, which a rule anchored to the end would miss."""
    assert season_of("2027 Point72 Academy Investment Analyst Summer Internship Program") == (
        InternshipSeason.SUMMER,
        2027,
    )


def test_a_year_without_a_season_keeps_the_year() -> None:
    """The case that decided there are two columns rather than one.

    Old Mission states 2027 and a June start and never uses a season word.
    Reading "June" as summer would be an inference about an employer's calendar;
    discarding the 2027 would be throwing away the one thing they did say.
    """
    assert season_of("Software Engineer – 2027 Internship Program (June Start)") == (  # noqa: RUF001
        None,
        2027,
    )


def test_a_season_without_a_year_keeps_the_season() -> None:
    """Constructed — the corpus has no example, and the column shape has to
    hold it anyway, because the reverse case is real and both are the same
    argument."""
    assert season_of("Summer Analyst Internship") == (InternshipSeason.SUMMER, None)


def test_a_title_stating_neither_yields_neither() -> None:
    """IMC's, and six more like it. Null is "the posting did not say"."""
    assert season_of("Hardware Engineer Intern") == (None, None)


# ---------------------------------------------------------------------------
# What must not be read
# ---------------------------------------------------------------------------


def test_the_description_is_never_read_for_a_year() -> None:
    """Measured, not supposed. The years in these descriptions are 2011 (Akuna's
    founding), 2015, 2025, 2028 and 2029 — a founding date, a fund launch and a
    graduation horizon. Harvesting one would put a confident wrong season on a
    posting whose title is honest about saying nothing."""
    description = "Akuna Capital was founded in 2011. Graduating by 2029? Apply for summer."

    assert season_of("Hardware Engineer Intern", description) == (None, None)


@pytest.mark.parametrize(
    "title",
    [
        # All six non-internship titles in the corpus that carry a season or a
        # year. Reading any of them as an internship season would be wrong, and
        # the third is the sharpest: 2027 is when that person starts work.
        "Akuna Capital's 2026 Virtual Quant Trading Challenge",
        "Expression of Interest: 2027 Trading Sneak Peek Weeks",
        "Associate Product Manager, New Grad (2027 Start)",
        "2027 EU Campus Programme Talent Community",
        "Campus AI/ML Researcher (Fall 2026)",
        "Point72 Academy Investment Analyst Program for Upcoming Graduates (2027 – HK)",  # noqa: RUF001
    ],
)
def test_a_posting_that_is_not_an_internship_never_acquires_a_season(title: str) -> None:
    """The gate on `is_internship`, and it is load-bearing on six real postings.

    "Campus AI/ML Researcher (Fall 2026)" is the one that costs something: it
    states a term and a year plainly, and the answer key labels it
    `is_internship: no` with the labeler's reason written beside it — *"campus
    role, so is_internship is no"*. Fall 2026 is when that cohort starts, not a
    season a person can apply for an internship in. Following the label over the
    title is the whole reason the answer key was committed first.
    """
    assert season_of(title) == (None, None)


def test_a_year_in_the_title_is_taken_at_face_value() -> None:
    """Constructed, and it pins a rule that was written and then deleted.

    The first version refused a year outside a plausible hiring window, so that
    "Summer Intern, Class of 2011 Reunion" could not claim a 2011 season. Two
    things killed it. It guards nothing observed — all ten years stated in
    corpus internship titles are 2026 or 2027, and the implausible ones (2011,
    2015, 2029) are all in *descriptions*, which this rule already refuses to
    read. And "plausible" can only mean "near now", which would make the same
    posting classify differently next year and break M3's determinism criterion
    for a case nobody has seen.

    So a year in an internship title is believed. The rule that earns its keep
    is the one above it: the year has to be in the title.
    """
    assert season_of("Summer Intern, Class of 2011 Reunion Programme") == (
        InternshipSeason.SUMMER,
        2011,
    )


# ---------------------------------------------------------------------------
# The coverage gap, asserted rather than commented
# ---------------------------------------------------------------------------


def test_the_rule_is_not_fitted_to_summer() -> None:
    """Constructed, and the reason it exists is a gap rather than a case.

    Every season this corpus states is "Summer" — 8 of 8. So the corpus can
    never show that `fall`, `winter` and `spring` are readable, and an enum with
    three values nothing has been seen to produce is the "shape with no use"
    this milestone has twice rejected. The difference here is that the *rule*
    reaches them; only the corpus does not. This is what says so.
    """
    assert season_of("Software Engineering Co-op, Fall 2027") == (InternshipSeason.FALL, 2027)
    assert season_of("Spring 2028 Data Science Internship") == (InternshipSeason.SPRING, 2028)
    assert season_of("Winter 2027 Trading Internship") == (InternshipSeason.WINTER, 2027)
