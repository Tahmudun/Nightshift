#!/usr/bin/env python3
"""Turn the recorded corpus into a blank relevance key and a readable worksheet.

`docs/architecture/matching.md` §7.3 and QUESTIONS Q5: M3 can prove the ranking
is *stable* and cannot prove it is *good*, because whether a role is a good role
for somebody is not a property of the posting. This script produces the only
thing that can close that gap — thirty postings for the human to sort into three
buckets.

    make worksheets

Writes two files:
    services/api/tests/fixtures/relevance/ratings.yaml   the blank key
    docs/labeling/relevance-worksheet.md                 what a human reads

Re-running preserves anything already filled in.

**Two things distinguish this from `make_label_worksheet.py`**, and both come
from the same fact: an eligibility label has a right answer and a relevance
rating does not.

1. **The file carries the profile the ratings were made against.** A rating is
   meaningless without one — "poor" from a first-year student and "poor" from a
   staff engineer are different claims about the same posting. M3d scores the
   corpus against this block rather than against whatever is in the database on
   the day it runs, which also keeps the grading a pure function.
2. **The selection is stratified by employer, not by eligibility shape.** M3a
   needed one posting per rule. Ranking needs a spread of things to sort, and
   thirty near-identical quant internships would produce thirty identical
   ratings and a metric that measures nothing.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
RATINGS = ROOT / "services" / "api" / "tests" / "fixtures" / "relevance" / "ratings.yaml"
WORKSHEET = ROOT / "docs" / "labeling" / "relevance-worksheet.md"


def _label_worksheet() -> Any:
    """The M3a generator, imported rather than copied.

    The excerpt logic there was built against this same corpus and corrected
    four times by measuring it (see its `_heading_positions` docstring). A
    second copy would drift, and a labeler cannot tell a drifted excerpt from a
    good one — which is the failure that whole module exists to prevent.
    """
    path = ROOT / "scripts" / "make_label_worksheet.py"
    spec = importlib.util.spec_from_file_location("make_label_worksheet", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_label_worksheet"] = module
    spec.loader.exec_module(module)
    return module


#: How many postings the worksheet asks for. Q5 promised "roughly thirty" and
#: "roughly twenty minutes", and those two numbers have to stay consistent with
#: each other: forty seconds a posting is a snap judgement, which is what a
#: relevance rating should be.
WORKSHEET_TARGET = 30

#: The three buckets. No fourth, no ordering within a bucket, no score — Q5.
#: A scale with more resolution than the judgement behind it invents precision.
RATING_VALUES = ("good", "acceptable", "poor")

#: What an unfilled field says. Same sentinel as the eligibility key.
TO_RATE = "TO_RATE"

#: The profile block. Every key mirrors something the product already stores or
#: will store, so M3d can hand it to `domain/scoring.py` unchanged.
PROFILE_FIELDS = (
    "graduation",
    "degree",
    "years_experience",
    "skills",
    "preferred_roles",
    "preferred_locations",
)

#: How much of the posting the worksheet shows. Deliberately a quarter of the
#: eligibility worksheet's window: that one asked for nine facts read out of the
#: text, this one asks "would you want this", and the title plus the first few
#: requirements answers it. Excerpts nobody finishes reading are excerpts that
#: get rated from the title anyway, without the reader noticing they did.
EXCERPT_WINDOW = 600

#: Strips the parts of a title that vary between otherwise identical postings.
#: Point72 posts the same Academy internship for Hong Kong, Japan and Singapore;
#: Jump posts the same Campus AI Research Engineer role four times. Rating the
#: same job three times costs three of the thirty and teaches nothing.
_TITLE_NOISE = re.compile(
    r"\b(20\d\d|summer|fall|winter|spring|intern(ship)?s?|program(me)?|"
    r"full[- ]?time|part[- ]?time|remote|hybrid|new grad|graduate|campus|"
    r"junior|senior|staff|principal|lead|associate|i{1,3}|iv|v)\b|[^a-z ]",
    re.I,
)

#: A short trailing dash clause is a location or a team, not a different job:
#: "Account Director - Tokyo", "... Internship Program - Hong Kong". Applied
#: only when deciding whether two titles are the same job — never to what the
#: worksheet displays, which always shows the posting's real title.
#: All three dashes are deliberate, not a typo: IMC and Old Mission write their
#: titles with the typographic ones, so a hyphen alone would miss them.
_TRAILING_QUALIFIER = re.compile(r"\s[-–—]\s[\w' ]{1,24}$")  # noqa: RUF001

#: Postings that are not a role. A talent community, an open submission form and
#: a recruiting event have nothing to be a good or poor fit *for*, so a rating on
#: one is a coin flip recorded as a judgement.
_NOT_A_JOB = re.compile(
    r"talent community|general submission|expression of interest|"
    r"talent (pool|network)|trading challenge|sneak peek",
    re.I,
)

_TECHNICAL = re.compile(
    r"\b(engineer|engineering|developer|software|data|machine learning|ml|ai|"
    r"research|scientist|security|infrastructure|platform|hardware|asic|fpga|"
    r"quant|quantitative|trader|trading|architect|sre|devops|systems|network|"
    r"product manag(er|ement)|program manag(er|ement))\b",
    re.I,
)

_EARLY_CAREER = re.compile(
    r"\b(intern|interns|internship|campus|new grad|graduate|university|"
    r"early career|academy|fellow|fellows|apprentice|student|entry level)\b",
    re.I,
)

#: Tested **before** the other two, so "University Recruiter" is a recruiting job
#: rather than an early-career one and "Compensation Manager" is not an engineer
#: for containing no engineering word by luck.
_NON_TECHNICAL = re.compile(
    r"\b(recruit(er|ing|ment)|talent|sourcer|account executive|account director|"
    r"sales|marketing|communications|compliance|legal|counsel|audit|accounting|"
    r"accounts payable|compensation|benefits|payroll|people|human resources|hr|"
    r"immigration|mobility|office|receptionist|administrative|executive assistant|"
    r"aml|kyc|onboarding|business development|partnership)\b",
    re.I,
)

#: The four buckets, in the order the worksheet fills them.
#:
#: **This stratification is the difference between a measurement and a
#: formality.** The first version round-robined by employer only and drew
#: alphabetically inside each: thirty postings of which four were engineering
#: and the rest were accountants, receptionists and AML analysts. Every one of
#: those is a `poor`, a ranker that sorts them last is not thereby good, and the
#: metric would have flattered itself in exactly the way §7.3 warns about.
#:
#: The split that carries the measurement is the first two. Sorting an
#: accountant below a software engineer is easy; sorting an early-career backend
#: role above a staff-level one for a student is the judgement being graded, and
#: it only exists in the set if both are in it.
#: The four buckets and how many of the thirty each is worth. Shares rather than
#: an even split, because the buckets are not equally informative: the ranking
#: has to be right about roles this person might plausibly want, and it has to be
#: caught if it is wrong about roles nobody would. Twelve and nine buy the first;
#: six and three are enough for the second.
#:
#: A bucket that cannot fill its share spills into the next one, so the worksheet
#: is thirty postings whatever the corpus holds.
_BUCKETS: tuple[tuple[str, int], ...] = (
    ("technical_early", 12),
    ("technical_experienced", 9),
    ("non_technical", 6),
    ("other", 3),
)

_BUCKET_NAMES = tuple(name for name, _ in _BUCKETS)


def title_stem(title: str) -> str:
    """What two postings share when they are the same job in different clothes."""
    trimmed = _TRAILING_QUALIFIER.sub("", title.strip())
    return " ".join(_TITLE_NOISE.sub(" ", trimmed.casefold()).split())


def bucket_of(title: str) -> str:
    """Which of :data:`_BUCKETS` a posting falls in, by title alone.

    By title alone on purpose. The description would classify better and would
    also make the worksheet's composition depend on the excerpt logic, which is
    the thing the worksheet exists to put in front of a human — a selection that
    quietly changes when an unrelated regex is tuned is a selection nobody can
    reason about.

    This is a sampling aid and nothing else. **No rating, score or component
    ever reads it**, so a title it buckets wrongly costs one slot in a worksheet
    and cannot reach a `match_result`.
    """
    if _NON_TECHNICAL.search(title):
        return "non_technical"
    if _TECHNICAL.search(title):
        return "technical_early" if _EARLY_CAREER.search(title) else "technical_experienced"
    return "other"


def select_for_rating(
    postings: list[tuple[str, dict[str, Any]]],
    *,
    target: int = WORKSHEET_TARGET,
    has_requirements: Any = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Pick ``target`` postings spread across employers *and* role shapes.

    Two axes, because one was demonstrably not enough (see ``_BUCKETS``):
    employer and role shape. Each bucket is filled round-robin across the boards
    up to its share — twelve, nine, six, three — so thirty postings arrive with
    something to sort rather than thirty of the same thing.

    Within a board, one posting per :func:`title_stem`, and postings whose
    requirements can actually be shown come first: no reason to spend one of
    thirty on Akuna's "Talent Community" blurb, which has no role in it.

    Deterministic: same corpus in, same thirty out, so regenerating never
    reshuffles what the human has already worked through.
    """
    cells: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    seen_stems: set[tuple[str, str]] = set()
    for board, posting in sorted(postings, key=lambda bp: (bp[0], bp[1]["title"], bp[1]["id"])):
        if _NOT_A_JOB.search(posting["title"]):
            continue
        stem = (board, title_stem(posting["title"]))
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        cells.setdefault((bucket_of(posting["title"]), board), []).append((board, posting))

    if has_requirements is not None:
        for entries in cells.values():
            entries.sort(key=lambda bp: not has_requirements(bp[1]["text"]))

    boards = sorted({board for _, board in cells})
    by_bucket: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    spill = 0
    for bucket, share in _BUCKETS:
        want = min(share + spill, target - sum(len(v) for v in by_bucket.values()))
        taken: list[tuple[str, dict[str, Any]]] = []
        depth = 0
        while len(taken) < want:
            added = False
            for board in boards:
                if len(taken) >= want:
                    break
                entries = cells.get((bucket, board), [])
                if depth >= len(entries):
                    continue
                taken.append(entries[depth])
                added = True
            if not added:
                break  # this bucket is exhausted; its remainder spills below
            depth += 1
        by_bucket[bucket] = taken
        spill = want - len(taken)

    # Interleaved for reading, not for selection. Filling bucket by bucket
    # produces twelve engineering roles followed by six recruiters, and by number
    # twenty a reader is stamping `poor` on a run rather than judging a posting.
    ordered: list[tuple[int, int, tuple[str, dict[str, Any]]]] = []
    for index, name in enumerate(_BUCKET_NAMES):
        for rank, entry in enumerate(by_bucket.get(name, [])):
            ordered.append((rank, index, entry))
    return [entry for _, _, entry in sorted(ordered, key=lambda row: (row[0], row[1]))]


def blank_rating(number: int, board: str, posting: dict[str, Any]) -> dict[str, Any]:
    """One entry, keys in reading order rather than alphabetical.

    ``n`` is the worksheet's number for this posting, and it is here so the two
    files can be worked through side by side without counting. The list is
    written in worksheet order for the same reason.
    """
    return {
        "n": number,
        "board": board,
        "id": posting["id"],
        "title": posting["title"],
        "rating": TO_RATE,
        "note": "",
    }


#: Written above the key, because a file a human edits should say what it is.
_RATINGS_PREAMBLE = f"""# Relevance ratings — QUESTIONS Q5, docs/labeling/relevance-worksheet.md
#
# `rating` is one of: {" / ".join(RATING_VALUES)}. Replace every {TO_RATE}.
# `profile` is who the ratings were made by; without it a rating means nothing.
# Regenerate with `make worksheets` — it preserves everything already filled in.
"""


_HEADER = """# Relevance worksheet — twenty minutes, thirty postings

> Fill in `services/api/tests/fixtures/relevance/ratings.yaml`.
> This is QUESTIONS Q5. It is the only thing in this project that can measure
> whether the ranking is any *good*, as opposed to merely stable.

## What to do

**First, the profile block at the top of the file — once, about two minutes.**
Every rating below is a judgement made by a particular person, and without this
block M3d cannot tell a ranking that is wrong from a ranking that was scored
against an empty profile.

```yaml
rated_on: 2026-08-09           # today
profile:
  graduation: 2027-05          # year and month, or `not_stated`
  degree: bachelors            # none / bachelors / masters / phd
  years_experience: 1          # a whole number, internships included
  skills: [Python, TypeScript] # names from data/skills.yaml where they exist
  preferred_roles: [backend engineer, data engineer]
  preferred_locations: [New York, remote]
```

Nothing here is inferred from anything and nothing is copied out of the app —
invariant I2 means a qualification comes from you or it does not exist. If a
field does not apply, write `not_stated` rather than a plausible number.

**Then rate the thirty postings — one word each.**

| Rating | Means |
|---|---|
| `good` | You would open this and consider applying |
| `acceptable` | You would not be annoyed to see it in a list |
| `poor` | Wrong role, wrong level, or not for you |

Rate on **fit, not on your odds.** A role you would love and are underqualified
for is `good`. Whether you *can* apply is the eligibility gate's question, it is
already answered separately, and `matching.md` §5.2 forbids it from ever
becoming points — so answering it here would be measuring the wrong thing twice.

The ratings file lists the same thirty postings **in this order**, each with an
`n` matching the number below, so the two can be worked through side by side:

```yaml
- n: 1
  board: akunacapital_eligibility
  id: '8018880'
  title: Hardware Engineer Intern, Summer 2027
  rating: good        # <- the only line you change
  note: ''
```

`note` is optional and exists only for the ones that were hard to call. Skip it.

**Do not tie-break, do not rank, do not agonise.** Forty seconds each. A first
reaction is the thing being measured; a considered second opinion is not what
the ranked list will be judged against by a person scrolling it.

The excerpt under each posting is short on purpose — it is the requirements
section, cut at 600 characters. If it says `[no requirements heading found]` the
tool could not locate one, and you are looking at a guess: rate from the title
or skip it with a note.

---
"""


def main() -> int:
    worksheet = _label_worksheet()
    existing: dict[str, Any] = {}
    if RATINGS.exists():
        existing = yaml.safe_load(RATINGS.read_text()) or {}

    prior_profile = existing.get("profile") or {}
    prior_ratings = {
        (entry.get("board"), str(entry.get("id"))): entry
        for entry in (existing.get("ratings") or [])
    }

    lines = [_HEADER]
    ratings: list[dict[str, Any]] = []
    counter = 0
    selected = select_for_rating(
        worksheet.all_postings(), has_requirements=worksheet.has_requirements_heading
    )
    for board, posting in selected:
        counter += 1
        pid = posting["id"]
        entry = blank_rating(counter, board, posting)
        prior = prior_ratings.get((board, pid))
        if prior is not None:
            entry["rating"] = prior.get("rating", TO_RATE)
            entry["note"] = prior.get("note", "")
        ratings.append(entry)
        excerpt = worksheet.requirements_excerpt(posting["text"], window=EXCERPT_WINDOW)
        lines += [
            f"## [{counter}] {board.removesuffix('_eligibility')} — {posting['title']}",
            "",
            f"`{board}` / `{pid}`",
            "",
            "> " + excerpt.replace("\n", " "),
            "",
        ]

    # Two dumps rather than one, so `profile` sits at the top of the file where
    # the worksheet says it does. `sort_keys=False` throughout: these files are
    # read by a person before they are read by a test.
    head = {
        "rated_on": existing.get("rated_on") or TO_RATE,
        "profile": {field: prior_profile.get(field, TO_RATE) for field in PROFILE_FIELDS},
    }
    body = {"ratings": ratings}
    RATINGS.parent.mkdir(parents=True, exist_ok=True)
    RATINGS.write_text(
        _RATINGS_PREAMBLE
        + yaml.safe_dump(head, sort_keys=False, allow_unicode=True)
        + "\n"
        + yaml.safe_dump(body, sort_keys=False, allow_unicode=True)
    )
    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    WORKSHEET.write_text("\n".join(lines))

    print(f"{counter} postings -> {RATINGS}")
    print(f"worksheet -> {WORKSHEET}")
    if counter < WORKSHEET_TARGET:
        print(
            f"WARNING: corpus yielded only {counter}, below the {WORKSHEET_TARGET} "
            "target — do not pad; report it"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
