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
    "what we're looking for",
    "who we're looking for",
    "what you'll need",
    "what you will need",
    "what you'll bring",
    "what we look for",
    "you should have",
    "who you are",
    "requirements",
    "qualifications",
    "nice to have",
    "nice to haves",
    "bonus points",
    "you have",
    "about you",
)

_HEADING_ALTERNATION = "|".join(
    re.escape(h) for h in sorted(_REQUIREMENT_HEADINGS, key=len, reverse=True)
)


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

    Once HTML is stripped to a single run, a real heading is one of:

    * followed by a colon      ``Qualities that make great candidates:``
    * written in capitals      ``WHAT YOU'LL NEED``
    * opening a sentence       ``... team. Requirements Proficiency in ...``

    A heading word sitting mid-clause after a comma matches none of the three.
    """
    positions: list[int] = []
    for match in re.finditer(_HEADING_ALTERNATION, text, re.I):
        start, end = match.span()
        followed_by_colon = text[end : end + 2].lstrip().startswith(":")
        written_in_capitals = match.group(0).isupper()
        preceding = text[:start].rstrip()
        opens_a_sentence = not preceding or preceding[-1] in ".;!?•|"
        if followed_by_colon or written_in_capitals or opens_a_sentence:
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
        key in lowered and pattern.search(title)
        for key, pattern in _MISLEADING_FOR_ITS_REASON
    )


def plain_text(raw: str) -> str:
    text = html.unescape(html.unescape(raw or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


#: Marks an excerpt that had no heading to anchor on, so a labeler can see the
#: tool is guessing rather than quietly reading a guess as evidence.
NO_HEADING_NOTICE = "[no requirements heading found — showing the end of the posting] "


def requirements_excerpt(text: str, *, window: int = 1200) -> str:
    """The region where requirements live, capped, never the whole document.

    Starts at the earliest *genuine* heading (see :func:`_heading_positions`)
    and runs ``window`` characters, which keeps the preferred section in frame —
    it almost always follows the required one and it is the section that matters
    most to label.

    With no heading it returns the **tail**, not the whole text. Two reasons,
    both measured: the first version returned everything and produced excerpts
    up to 8,000 characters, which nobody reads; and in these postings the
    requirements sit near the end, after the company blurb. The tail is prefixed
    with :data:`NO_HEADING_NOTICE` because an unmarked fallback is a silent
    guess presented as evidence.
    """
    positions = _heading_positions(text)
    if positions:
        return text[positions[0] : positions[0] + window]
    if len(text) <= window:
        return text
    return NO_HEADING_NOTICE + text[-window:]


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
            bp
            for bp in entries
            if not _is_about_rather_than_an_instance(reason, bp[1]["title"])
        ]
        if keep:
            entries[:] = keep

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
        key["boards"][board][pid] = prior.get(pid) or blank_label(
            pid, posting["title"]
        )
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
