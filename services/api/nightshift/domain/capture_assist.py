"""What the reader's Claude is allowed to say about a posting it read.

M5d / ADR 0039 §2. ``domain/capture.py`` has a parser that reads lines and is
biased hard toward declining; its docstring explains why, and the asymmetry it
names — *a blank field costs four seconds, a wrong field costs a building* — is
unchanged by this module.

What is new is a **second proposer**. ADR 0039 §1 forbids this server loading a
LinkedIn or Indeed page, so the only party that has actually seen the posting
rendered is the reader's own Claude. It knows which string is the employer. The
line parser is guessing from position, and on prose it declines everything.

So the assistant may propose. It gets no more authority than the parser, only
different failure modes, and one of its failure modes is new and severe:

    the parser can misread the text
    the assistant can produce a company that was never in the text at all

A misread is bounded by what was pasted. An invention is not, and in a review
form the two are indistinguishable — both arrive as a pre-filled field beside a
label. That is the whole reason this module exists.

## The rule

**A field the assistant proposes must appear, verbatim, in the text the reader
pasted.** Whitespace-collapsed and case-insensitive; nothing else is forgiven.
Quote, do not paraphrase.

It is the same guarantee ``resume_extractions`` gets from its span trigger —
*no accepted fact that is not literally in the document* — reached with a
substring test instead of a trigger, because a capture is one short form
reviewed against text the person pasted seconds ago rather than dozens of
facts accepted individually.

The rule is deliberately strict and it will refuse correct answers. "NYC" for
"New York, NY" is right and is refused, because a gate with an exception for
values that look right is the model's judgement again wearing a check's
clothes. What the strictness buys is that **a reader looking at an
assistant-proposed field can find it in the text below the form**, every time,
with no exceptions to remember.

## What it does not do

It does not decide whether the value is *correct* — "Ramp" appearing in the
text does not make Ramp the employer, and a posting naming a customer will let
that customer through. The confirmation step is still what makes a company
real. This narrows the failure from *anything the model can say* to *something
on the page*, and that is all it claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

#: The fields an assistant may point at, sorted because ``rejected`` is stored
#: and compared. ``employment_type`` is absent on purpose: it is derived from
#: the title by ``employment_type_for_title``, and it is an enum rather than a
#: quote, so there would be nothing on the page for it to point at.
ASSIST_FIELDS: tuple[str, ...] = ("company_name", "location_text", "title")

#: Same caps as the parser's, for the same reason. A title is a short noun
#: phrase; quoting the whole posting into the field is quoting, and useless.
_MAX_CHARS: dict[str, int] = {
    "title": 200,
    "company_name": 100,
    "location_text": 200,
}

_WHITESPACE = re.compile(r"\s+")


def _flatten(value: str) -> str:
    """Collapse every run of whitespace and casefold.

    Line breaks are the common difference between what a model sends and what
    the page held — a title wraps, and the model unwraps it. Refusing over a
    newline would make this rule about typography rather than about honesty.
    """
    return _WHITESPACE.sub(" ", value).strip().casefold()


def quotable(raw_text: str, value: str | None) -> bool:
    """Is ``value`` literally present in ``raw_text``?

    Public and named so the gate is findable and the sabotage is one line:
    make this return ``True`` and every test in
    ``tests/test_capture_assist.py`` goes red.
    """
    if value is None:
        return False
    flat = _flatten(value)
    if not flat:
        return False
    return flat in _flatten(raw_text)


@dataclass(frozen=True, slots=True)
class AssistantProposal:
    """What the assistant says it read. Every field may be None."""

    title: str | None = None
    company_name: str | None = None
    location_text: str | None = None


@dataclass(frozen=True, slots=True)
class AssistantReading:
    """What survived the gate, and what did not.

    ``rejected`` holds **field names only, never the refused values**. Storing
    the value would put a hallucinated company name in the database, which is
    the thing this module exists to keep out of it. What is worth keeping is
    how often the rule bites, and a name is enough for that.
    """

    accepted: AssistantProposal
    rejected: tuple[str, ...]


def read_assistant(raw_text: str, proposal: AssistantProposal) -> AssistantReading:
    """Accept the fields that are quotes and name the ones that are not.

    A field that was never offered is not a refusal. A field that arrives blank
    is not a proposal. Both come back as ``None`` in ``accepted`` and neither
    appears in ``rejected`` — the list is for fields the assistant asserted and
    this function turned down, because that is the only diagnostic there will
    ever be for whether the gate is set too tight.
    """
    accepted = AssistantProposal()
    rejected: list[str] = []

    for field in ASSIST_FIELDS:
        offered: str | None = getattr(proposal, field)
        if offered is None or not offered.strip():
            continue
        if len(offered) > _MAX_CHARS[field] or not quotable(raw_text, offered):
            rejected.append(field)
            continue
        accepted = replace(accepted, **{field: offered.strip()})

    return AssistantReading(accepted=accepted, rejected=tuple(sorted(rejected)))


__all__ = [
    "ASSIST_FIELDS",
    "AssistantProposal",
    "AssistantReading",
    "quotable",
    "read_assistant",
]
