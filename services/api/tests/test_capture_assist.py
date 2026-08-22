"""The rule that lets a language model propose a field without being trusted.

M5d. The parser in ``domain/capture.py`` reads lines; the reader's Claude has
read the actual page. On a LinkedIn posting the second one is far better, and
the desktop walk proved the first one declines everything when handed prose.

The danger is exact: **a model's proposal and a parser's proposal look
identical in a review form, and only one of them can invent a company that was
never on the page.** So the assistant's fields are stored apart, labelled, and
gated by one deterministic rule — quote, do not paraphrase.

Every test below is the rule from one side. The sabotage that turns the whole
file red is making ``quotable`` return ``True``.
"""

from __future__ import annotations

import pytest

from nightshift.domain.capture_assist import (
    ASSIST_FIELDS,
    AssistantProposal,
    quotable,
    read_assistant,
)

RAW = """Staff Backend Engineer
Ramp · New York, NY (Hybrid)
2 days ago · 34 applicants

About the job
Build payment infrastructure. Python and Postgres.
"""


def test_a_quoted_field_is_accepted() -> None:
    reading = read_assistant(RAW, AssistantProposal(title="Staff Backend Engineer"))
    assert reading.accepted.title == "Staff Backend Engineer"
    assert reading.rejected == ()


def test_a_field_that_is_not_in_the_text_is_refused() -> None:
    """The whole point. The text contains no Stripe and never will."""
    reading = read_assistant(RAW, AssistantProposal(company_name="Stripe"))
    assert reading.accepted.company_name is None
    assert reading.rejected == ("company_name",)


def test_whitespace_and_case_do_not_decide_it() -> None:
    """A model that re-wraps a line has still quoted it.

    Line breaks are the common case: "Staff Backend Engineer" sits on one line
    here, and on a real page it can wrap. Refusing over a newline would make
    the rule about typography rather than about honesty.
    """
    reading = read_assistant(RAW, AssistantProposal(title="staff   backend\nengineer"))
    assert reading.accepted.title == "staff   backend\nengineer"
    assert reading.rejected == ()


def test_a_paraphrase_is_refused_even_when_it_is_correct() -> None:
    """ "NYC" is the right answer and it is not on the page.

    This is the test that decides whether the rule is a rule. A gate with an
    exception for values that look right is not a gate — it is the model's
    judgement again, wearing a check's clothes.
    """
    reading = read_assistant(RAW, AssistantProposal(location_text="NYC"))
    assert reading.accepted.location_text is None
    assert reading.rejected == ("location_text",)


def test_a_narrower_quote_is_still_a_quote() -> None:
    """ "New York, NY" is a substring of "New York, NY (Hybrid)" and is fine.

    Trimming is not paraphrasing. The reader can see both strings side by side
    with the raw text under them, and the shorter one is what the location
    parser wants anyway.
    """
    reading = read_assistant(RAW, AssistantProposal(location_text="New York, NY"))
    assert reading.accepted.location_text == "New York, NY"
    assert reading.rejected == ()


def test_an_absent_field_is_not_a_refusal() -> None:
    """Nothing offered is nothing to refuse, and the two must not be conflated.

    A field the model never mentioned and a field it got wrong look the same
    in the stored row — both null. ``rejected`` is what tells them apart, and
    it is the only diagnostic there will ever be for how often the rule bites.
    """
    reading = read_assistant(RAW, AssistantProposal())
    assert reading.rejected == ()
    assert reading.accepted == AssistantProposal()


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_a_blank_field_is_not_a_proposal(blank: str) -> None:
    reading = read_assistant(RAW, AssistantProposal(title=blank))
    assert reading.accepted.title is None
    assert reading.rejected == ()


def test_a_quote_the_length_of_a_paragraph_is_refused() -> None:
    """Quoting the whole posting into the title field is quoting, and useless.

    The parser has the same caps for the same reason: a title is a short noun
    phrase, and seeding the form with a paragraph is worse than seeding it
    with nothing.
    """
    body = "x" * 400
    reading = read_assistant(f"Some job\n{body}", AssistantProposal(title=body))
    assert reading.accepted.title is None
    assert reading.rejected == ("title",)


def test_rejections_are_reported_in_a_stable_order() -> None:
    """Sorted, because this list is stored and compared in tests and diffs."""
    reading = read_assistant(
        RAW,
        AssistantProposal(title="Head of Nothing", company_name="Stripe", location_text="Mars"),
    )
    assert reading.rejected == ("company_name", "location_text", "title")
    assert reading.accepted == AssistantProposal()


def test_quotable_is_the_whole_gate_and_is_public() -> None:
    """Named and exported so the sabotage is one line and the rule is findable."""
    assert quotable(RAW, "Ramp") is True
    assert quotable(RAW, "Stripe") is False
    assert quotable(RAW, None) is False


def test_the_field_list_matches_what_a_person_confirms() -> None:
    """Three fields, and the fourth is deliberately absent.

    ``employment_type`` is derived from the title by
    ``employment_type_for_title`` and is not a free-text quote, so there is
    nothing for the assistant to point at. Letting it propose one would put an
    enum in a field whose entire gate is "does this string appear in the text".
    """
    assert ASSIST_FIELDS == ("company_name", "location_text", "title")
