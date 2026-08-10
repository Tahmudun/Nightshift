#!/usr/bin/env python3
"""Turn the recorded corpus into a blank answer key and a readable worksheet.

`docs/architecture/matching.md` §1.1: the answer key is committed before any
matching rule exists. This script produces the thing a human fills in.

    python scripts/make_label_worksheet.py

Writes two files:
    services/api/tests/fixtures/eligibility/labels.yaml   the blank key
    docs/labeling/eligibility-worksheet.md                what a human reads

Re-running preserves any label already filled in. A human's forty minutes is not
something a script gets to overwrite.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "services" / "api" / "tests" / "fixtures" / "eligibility"
LABELS = CORPUS / "labels.yaml"
WORKSHEET = ROOT / "docs" / "labeling" / "eligibility-worksheet.md"

#: Longest first, so "preferred qualifications" wins over a bare "qualifications".
#: Every entry after the first block was found in the recorded corpus, not
#: imagined — "qualities that make great candidates" is Akuna's, and without it
#: sixteen of their postings anchored on compensation boilerplate instead.
_REQUIREMENT_HEADINGS = (
    "preferred qualifications",
    "minimum qualifications",
    "basic qualifications",
    "qualities that make great candidates",
    "you may be a good fit if you",
    "your skills and experience",
    "what we're looking for",
    "who we're looking for",
    "the ideal candidate is",
    "what you'll need",
    "what you will need",
    "what you'll bring",
    # Jump Trading's phrasing. Held back for one round on purpose, to see
    # whether those postings fell back honestly — they did not. They anchored
    # on "Bonus Points" instead and showed a labeler the optional list while
    # the required one sat above it, unshown. Falling back would have been the
    # better failure; showing the wrong section is the one that misleads.
    "skills you'll need",
    "skills you will need",
    "what we look for",
    "you should have",
    "who should apply",
    "you might thrive",
    "who you are",
    "requirements",
    "qualifications",
    "nice to have",
    "nice to haves",
    "bonus points",
    "you have",
    "about you",
    # Databricks writes a bare "Required:" / "Preferred:" pair. Safe only
    # because `_heading_positions` demands a colon, capitals, or a sentence
    # opening — "3 years is required." matches none of the three.
    "required",
    "preferred",
)

#: Headings whose words could plausibly occur mid-prose, so a bare match is not
#: enough. "the base salary depends on experience, qualifications, and skill
#: set" and "meet regulatory requirements by translating commitments" both
#: contain one of these and neither opens a requirements section.
_AMBIGUOUS_HEADINGS = frozenset(
    {"requirements", "qualifications", "you have", "required", "preferred", "about you"}
)

_HEADING_ALTERNATION = "|".join(
    re.escape(h) for h in sorted(_REQUIREMENT_HEADINGS, key=len, reverse=True)
)

#: How far past a heading phrase to look for its colon. The vocabulary stores
#: truncated stems — "you might thrive" for "You might thrive in this role if
#: you:" — so the colon can sit a clause away. Bounded, and abandoned at any
#: sentence terminator, so a heading word inside prose still finds nothing.
_COLON_LOOKAHEAD = 80


def _colon_follows(text: str, end: int) -> bool:
    """A colon within :data:`_COLON_LOOKAHEAD`, before any sentence terminator."""
    for char in text[end : end + _COLON_LOOKAHEAD]:
        if char == ":":
            return True
        if char in ".!?;":
            return False
    return False


def _heading_positions(text: str) -> list[int]:
    """Offsets where a requirement heading genuinely opens a section.

    A bare substring search is not enough, and the corpus proved it on the
    first real run: **30 of 60 worksheet excerpts anchored inside ordinary
    prose.** "This role is also eligible for... experience, qualifications, and
    skill set" is compensation boilerplate; "meet regulatory requirements by
    translating commitments" is a job duty. Both contain a heading word, and an
    excerpt anchored on either shows a human none of the posting's actual
    requirements while looking exactly like one that does. That is the failure
    this whole function exists to avoid — a label built from wrong evidence is
    indistinguishable from a good one.

    **A distinctive phrase is taken at its word.** "Minimum qualifications" and
    "you may be a good fit if you" cannot plausibly occur mid-sentence in a job
    posting; requiring further proof of them cost three real postings, which
    then showed a labeler "About Anthropic" boilerplate instead of the
    requirements sitting a few hundred characters earlier.

    **An ambiguous phrase must prove itself** — see :data:`_AMBIGUOUS_HEADINGS`.
    A bare "requirements" or "qualifications" is a word that appears in pay
    disclaimers and job duties, so it qualifies only when it is:

    * followed by a colon      ``Qualifications: 3+ years of ...``
    * written in capitals      ``REQUIREMENTS``
    * opening a sentence       ``... team. Requirements Proficiency in ...``

    The colon may sit a clause away rather than immediately after, because the
    vocabulary stores stems: ``you might thrive`` matches inside "You might
    thrive in this role if you:". :func:`_colon_follows` bounds that search and
    abandons it at a sentence terminator, so "meet regulatory requirements by
    translating commitments into engineering work." still finds nothing.
    """
    positions: list[int] = []
    for match in re.finditer(_HEADING_ALTERNATION, text, re.I):
        start, end = match.span()
        if match.group(0).casefold() not in _AMBIGUOUS_HEADINGS:
            positions.append(start)
            continue
        if _looks_like_a_heading(text, start, end):
            positions.append(start)
    return sorted(positions)


_LABEL_FIELDS = (
    "is_internship",
    "graduation_window",
    "enrollment_required",
    "degree",
    "min_years_experience",
    "required_tech",
    "mentioned_not_required",
    "sponsorship",
    "note",
)

#: How many postings the worksheet asks a human to label.
#:
#: Task 2 recorded 153 across nine boards — the per-board selector limits were
#: never capped across boards, so nine boards overshot the plan's stated ~60 by
#: two and a half times. Decided 2026-08-04: label a stratified 60; the other 93
#: stay committed and unlabeled, available if the metrics later look thin.
#:
#: A13's floor is 50. Sixty clears it with room for a few labels to be wrong.
WORKSHEET_TARGET = 60

#: Postings that satisfy a selector's *words* while being about the topic rather
#: than an instance of it. Both entries were measured on the real corpus, not
#: guessed, and both are the same mistake wearing different clothes: a job whose
#: subject matter is X matches every keyword a job that *states* X would.
#:
#:   * "Campus Recruiter" / "University Recruiter" matched the new-grad
#:     selector — 3 of its 8 hits across nine boards. Jobs recruiting new
#:     grads, not jobs for new grads.
#:   * "Immigration and Mobility Specialist" matched the sponsorship selector,
#:     on "advise on visa sponsorship considerations during the hiring
#:     process". A job administering sponsorship for employees, not a posting
#:     stating its own sponsorship policy toward an applicant.
#:
#: Keyed by reason rather than applied to every posting: an immigration
#: specialist posting is a perfectly good example of a *senior title* or a
#: *years-of-experience requirement*, and skipping it everywhere would throw
#: away real signal to fix one bad annotation.
_MISLEADING_FOR_ITS_REASON: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "new grad",
        re.compile(
            r"\b(recruit(er|ing|ment)|talent|sourcer|university relations"
            r"|campus relations|early careers)\b",
            re.I,
        ),
    ),
    (
        "sponsorship",
        re.compile(
            r"\b(immigration|mobility|visa|people ops|human resources|hr)\b",
            re.I,
        ),
    ),
)


def _is_about_rather_than_an_instance(reason: str, title: str) -> bool:
    """True when a posting matched its selector by subject, not by being one."""
    lowered = reason.casefold()
    return any(
        key in lowered and pattern.search(title) for key, pattern in _MISLEADING_FOR_ITS_REASON
    )


def plain_text(raw: str) -> str:
    text = html.unescape(html.unescape(raw or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


#: Marks an excerpt that had no heading to anchor on, so a labeler can see the
#: tool is guessing rather than quietly reading a guess as evidence.
#:
#: Two forms, one prefix. The prefix is what tests assert on, so a third form
#: cannot be added later without the guard noticing.
NO_HEADING_PREFIX = "[no requirements heading found"
NO_HEADING_TAIL = NO_HEADING_PREFIX + " — showing the end of the posting] "
NO_HEADING_WHOLE = NO_HEADING_PREFIX + " — showing the whole posting] "

#: Appended when the window cut the section short. Measured: Akuna's "Security
#: Engineer II" excerpt ends "...PowerShell, Python, or similar script" while
#: the posting goes on to name TCP/IP, DNS, HTTP/S and VPNs. A labeler filling
#: `required_tech` from that would under-report it and have no way to know.
TRUNCATED_SUFFIX = " […cut off — open the fixture for the rest]"

#: Headings that end a requirements section. Everything after one of these is
#: pay disclaimers, benefits and EEO boilerplate — never a requirement.
#:
#: This is what makes the window generous without recreating the wall of text.
#: Measured across the 60 selected postings: from the requirements heading to
#: the *end of the posting* is a median of 3,475 characters and a maximum of
#: 13,967. To the next closer below it is a median of **1,260**. Raising the
#: window alone would have dragged all that boilerplate back in.
#: A closer must look like a heading, by the same test a requirements heading
#: passes. Measured: OpenAI's "Account Director - Tokyo" says "benefits" inside
#: a requirement bullet, and a bare match there ended the section three
#: requirements early — with no truncation marker, because the section had
#: "ended". An excerpt that stops *before* the requirements is worse than one
#: that runs past them, and it looks identical to a complete one.
_SECTION_CLOSERS = re.compile(
    r"compensation|benefits|equal (employment )?opportunity|perks"
    r"|why (join|work)|our values|about (us|the company)"
    r"|the (expected )?(base )?(salary|pay)|we are an equal|pay transparency"
    r"|how to apply|interview process|life at|eeo|in accordance with"
    r"|annual salary range|total (pay|compensation)"
    # Anthropic's closing sections, which name themselves rather than saying
    # "benefits". Without some of these its postings had no closer at all and
    # the window became their only bound.
    #
    # **Four candidates were measured and rejected**, and the reason is the
    # most important thing in this file. Anthropic interleaves eligibility
    # facts with its boilerplate rather than putting them above it:
    #
    #     ... Location-based hybrid policy: ...
    #     Visa sponsorship: We do sponsor visas! ...
    #     Deadline to apply: None. ...  Annual Salary: $265,000 — $365,000
    #     Logistics  Minimum education: Bachelor's degree or an equivalent ...
    #
    # `Visa sponsorship` and `Minimum education` are two of the nine fields a
    # human is asked to label. Closing at `logistics`, `deadline to apply`,
    # `location-based hybrid` or `role-specific` cut them off **without a
    # truncation marker**, because as far as the code knew the section had
    # ended — 12 of 60 postings silently lost a degree requirement, a
    # sponsorship statement, or both.
    #
    # Measured across the 60:
    #     with all eight    truncated  6/60   silent loss 12/60
    #     with these four   truncated 12/60   silent loss  0/60
    #
    # Twelve marked truncations beat six marked plus twelve silent ones. A
    # labeler can act on "cut off — open the fixture"; they cannot act on a
    # missing degree requirement that looks like an absent one.
    r"|how we'?re different|come work with us"
    r"|we encourage you to apply|the salary range",
    re.I,
)

#: How far into a section to start looking for its closer. A requirements
#: heading and a compensation heading sometimes sit within a sentence of each
#: other in flattened HTML, and without this offset the excerpt would close
#: itself immediately.
_CLOSER_OFFSET = 200


#: What may sit immediately before a heading. The brackets were added when
#: `requirement_extraction.py` adopted this rule and found Databricks writing
#: ``[Preferred] Experience using ... Apache Spark``; without them that heading
#: failed its own proof. Kept identical in both files on purpose — the extractor
#: is graded against a key this script built, and two versions of "what counts as
#: a heading" would mean grading against evidence gathered under other rules.
_HEADING_OPENERS = ".;!?•|[("


def _looks_like_a_heading(text: str, start: int, end: int) -> bool:
    """The shared test: a colon follows, it is capitalised, or it opens a
    sentence. Used for requirement headings and for section closers alike —
    a word buried in a bullet is not a heading in either direction."""
    written_in_capitals = text[start:end].isupper()
    preceding = text[:start].rstrip()
    opens_a_sentence = not preceding or preceding[-1] in _HEADING_OPENERS
    return _colon_follows(text, end) or written_in_capitals or opens_a_sentence


def _section_end(body: str) -> int:
    """Where the requirements section stops, or ``len(body)`` if it does not."""
    position = _CLOSER_OFFSET
    while (match := _SECTION_CLOSERS.search(body, position)) is not None:
        if _looks_like_a_heading(body, match.start(), match.end()):
            return match.start()
        position = match.end()
    return len(body)


def requirements_excerpt(text: str, *, window: int = 2500) -> str:
    """The requirements section, bounded at its own end rather than by length.

    Starts at the earliest *genuine* heading (see :func:`_heading_positions`)
    and runs to whichever comes first: the next non-requirements section
    (:data:`_SECTION_CLOSERS`) or ``window`` characters. The preferred section
    stays in frame — it almost always follows the required one and is the part
    that matters most to label — while pay disclaimers and EEO boilerplate do
    not.

    **The section boundary is what lets the window be generous.** A 1,200-char
    window with no boundary marked 56 of 60 excerpts as cut, which makes the
    marker noise nobody reads; raising it alone would have dragged the
    boilerplate back in, since heading-to-end-of-posting runs to a median of
    3,475 characters and a maximum of 13,967. Cutting at the closer brings the
    median to 1,260, and at 2,500 only about 7 of 60 are still cut — a marker
    that means something when it appears.

    With no heading it returns the **tail**, not the whole text. Two reasons,
    both measured: the first version returned everything and produced excerpts
    up to 8,000 characters, which nobody reads; and in these postings the
    requirements sit near the end, after the company blurb.

    **Every no-heading result is marked, including a short one.** The short
    branch originally returned the text bare, on the reasoning that a reader
    can see a whole short posting for themselves. That was wrong, and one real
    posting shows why: Akuna's "Talent Community" blurb is 523 characters with
    no requirements section at all. Unmarked, it reads as though the blurb *is*
    the requirements — which is the precise failure this function exists to
    prevent, just at a smaller size. A short posting with nothing to find is
    exactly where a labeler most needs to be told nothing was found.
    """
    positions = _heading_positions(text)
    if positions:
        start = positions[0]
        body = text[start:]
        section_end = _section_end(body)
        end = min(section_end, window)
        excerpt = body[:end]
        if end < section_end:
            excerpt += TRUNCATED_SUFFIX
        return excerpt
    if len(text) <= window:
        return NO_HEADING_WHOLE + text
    return NO_HEADING_TAIL + text[-window:]


def blank_label(posting_id: str, title: str) -> dict[str, Any]:
    label: dict[str, Any] = {"title": title}
    for field in _LABEL_FIELDS:
        label[field] = "TO_LABEL"
    return label


def select_for_labeling(
    postings: list[tuple[str, dict[str, Any]]], *, target: int = WORKSHEET_TARGET
) -> list[tuple[str, dict[str, Any]]]:
    """Pick ``target`` postings covering every eligibility shape.

    Stratified by the *reason* each posting was recorded under, which is stored
    per posting in the board's ``.meta.json``. Round-robins across reasons
    rather than taking the first N: the corpus holds 153 postings and taking
    them in file order would hand back 153 postings from three boards, with
    whole shapes missing.

    Two rules beyond the round-robin:

    * **Every reason present in the corpus contributes at least one posting**,
      even reasons with only one example. A shape with one instance is exactly
      the shape most likely to be got wrong.
    * **Postings that matched their selector by subject rather than by being an
      instance of it are skipped**, unless dropping one would empty its reason.
      See ``_MISLEADING_FOR_ITS_REASON``: "Campus Recruiter" under new-grad,
      "Immigration and Mobility Specialist" under sponsorship. Labeling those
      teaches the answer key nothing about the shape they were recorded for.

    Deterministic: same corpus in, same 60 out, so regenerating the worksheet
    never reshuffles what a human has already worked through.
    """
    by_reason: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for board, posting in postings:
        by_reason.setdefault(posting["reason"], []).append((board, posting))

    for reason, entries in by_reason.items():
        entries.sort(key=lambda bp: (bp[0], bp[1]["id"]))
        keep = [
            bp for bp in entries if not _is_about_rather_than_an_instance(reason, bp[1]["title"])
        ]
        if keep:
            entries[:] = keep
        # Within a reason, prefer postings whose requirements can actually be
        # shown. The corpus holds 153 postings and the worksheet asks for 60,
        # so there is no reason to spend one of those 60 on a posting whose
        # excerpt is a marked "could not find it" — measured at 15 of 60 before
        # this line existed, a quarter of a person's time spent reading legal
        # boilerplate about returning laptops.
        #
        # A stable sort, so a reason with no excerptable posting still yields
        # its best available one rather than dropping the shape entirely.
        entries.sort(key=lambda bp: not _heading_positions(bp[1]["text"]))

    picked: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    depth = 0
    while len(picked) < target:
        added = False
        for reason in sorted(by_reason):
            if len(picked) >= target:
                break
            entries = by_reason[reason]
            if depth >= len(entries):
                continue
            board, posting = entries[depth]
            if (board, posting["id"]) in seen:
                continue
            seen.add((board, posting["id"]))
            picked.append((board, posting))
            added = True
        if not added:
            break  # corpus exhausted before the target; report it, do not pad
        depth += 1
    return picked


def all_postings() -> list[tuple[str, dict[str, Any]]]:
    """The corpus, for the other worksheet generator (M3c's relevance pass).

    A public name rather than a second reader of the fixture directory: both
    worksheets must be built from the same 153 postings, or a rating and a label
    can end up describing different jobs under the same id.
    """
    return _all_postings()


def has_requirements_heading(text: str) -> bool:
    """Whether an excerpt of ``text`` would show requirements or a marked guess."""
    return bool(_heading_positions(text))


def _all_postings() -> list[tuple[str, dict[str, Any]]]:
    """Every recorded posting, tagged with its board and its recorded reason."""
    out: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CORPUS.glob("*.json")):
        if path.name.endswith(".meta.json") or path.name == "labels.yaml":
            continue
        meta_path = path.with_name(path.stem + ".meta.json")
        reasons = (
            json.loads(meta_path.read_text()).get("why_each_job_is_here", {})
            if meta_path.exists()
            else {}
        )
        for posting in _postings(path):
            posting["reason"] = reasons.get(posting["id"], "unrecorded")
            out.append((path.stem, posting))
    return out


def _postings(path: Path) -> list[dict[str, Any]]:
    body = json.loads(path.read_text())
    jobs = body["jobs"] if isinstance(body, dict) else body
    out = []
    for job in jobs:
        out.append(
            {
                "id": str(job.get("id")),
                "title": str(job.get("title") or job.get("text") or ""),
                "text": plain_text(
                    job.get("content")
                    or job.get("descriptionPlain")
                    or job.get("descriptionHtml")
                    or job.get("description")
                    or ""
                ),
            }
        )
    return out


def main() -> int:
    existing: dict[str, Any] = {}
    if LABELS.exists():
        existing = yaml.safe_load(LABELS.read_text()) or {}

    key: dict[str, Any] = {"boards": {}}
    lines: list[str] = [
        "# Eligibility labeling worksheet",
        "",
        "Fill in `services/api/tests/fixtures/eligibility/labels.yaml`.",
        "Every field starts as `TO_LABEL`; replace each one.",
        "",
        "Field values:",
        "",
        "| Field | Values |",
        "|---|---|",
        "| `is_internship` | `yes` / `no` / `unclear` |",
        "| `graduation_window` | e.g. `2026-2028`, or `not_stated` |",
        "| `enrollment_required` | `yes` / `no` / `not_stated` |",
        "| `degree` | `none` / `bachelors` / `masters` / `phd`, optionally `+equivalent` |",
        "| `min_years_experience` | an integer, or `not_stated` |",
        "| `required_tech` | list of names, or `[]` |",
        "| `mentioned_not_required` | list of names, or `[]` |",
        "| `sponsorship` | `offered` / `not_offered` / `not_stated` |",
        "| `note` | free text — what made this one hard |",
        "",
        "**`mentioned_not_required` is the field that matters most.** Anything under",
        "*nice to have*, *bonus points* or *preferred qualifications* goes there, not",
        "in `required_tech`.",
        "",
        "**`+equivalent`** — if the degree line says *or equivalent experience*, write",
        "`phd+equivalent`. That must resolve to `uncertain`, never `ineligible`.",
        "",
        "---",
        "",
    ]

    counter = 0
    for board, posting in select_for_labeling(_all_postings()):
        key["boards"].setdefault(board, {})
        prior = (existing.get("boards") or {}).get(board, {})
        counter += 1
        pid = posting["id"]
        key["boards"][board][pid] = prior.get(pid) or blank_label(pid, posting["title"])
        lines += [
            f"## [{counter}] {board} — {posting['title']}",
            "",
            f"`{board}` / `{pid}`  ·  recorded because: {posting['reason']}",
            "",
            "> " + requirements_excerpt(posting["text"]).replace("\n", " "),
            "",
        ]

    LABELS.write_text(yaml.safe_dump(key, sort_keys=True, allow_unicode=True))
    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    WORKSHEET.write_text("\n".join(lines))
    total = len(_all_postings())
    print(f"{counter} of {total} recorded postings -> {LABELS}")
    print(f"worksheet -> {WORKSHEET}")
    if counter < WORKSHEET_TARGET:
        print(
            f"WARNING: corpus yielded only {counter}, below the {WORKSHEET_TARGET} "
            "target — do not pad; report it"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
