# M3a — the corpus, the answer key, and requirement extraction

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task by task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record nine real ATS boards, get ~60 of their postings hand-labeled by a
human for what each one *requires*, and build a rules-based requirement extractor
that is graded against those labels from its first commit.

**Architecture:** Requirement extraction mirrors M2c's resume extractor exactly —
rules, no model, and every proposal carries the character span it came from, so a
requirement is always traceable to the sentence that produced it. The new
`job_requirements` table gets the same span-quoting trigger `resume_extractions`
has. The answer key is a committed YAML file keyed by board token and posting id,
so a label always points at a payload in the same commit.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Alembic, Pydantic v2, pytest.
Next.js + Zod on the web side. No new dependencies.

## Global Constraints

- **Read `docs/architecture/matching.md` first.** It is the design this plan
  implements; where the two disagree, the design wins and this plan is wrong.
- **No new dependency, no model, no LLM, no API key.** M3a is rules only.
- **The answer key is committed before any extraction rule is written.**
  Tasks 1–3 then a human gate, then Task 4 onward. `matching.md` §1.1 is the
  reason and it is not a preference.
- **Every requirement quotes its span.** `start_char` / `end_char` into
  `jobs.description_text`, refused by trigger if the span does not quote the text.
- **When a rule cannot decide, it produces nothing.** Never a default, never a
  guess. `matching.md` §3.3.
- **`necessity` is required | preferred | mentioned.** A technology under "nice
  to haves" is `preferred` and must never become a gap.
- **TODOs carry a milestone:** `TODO(M3b): ...`. A bare `TODO` is a lint failure.
- **`make check` before every commit.** Conventional commits, scoped.
- **Migrations reversible and tested both directions**, and `alembic check` must
  report no drift.

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/record_fixture.py` | **Modify.** Add `--profile eligibility` selectors |
| `scripts/make_label_worksheet.py` | **Create.** Corpus → blank answer key + human-readable worksheet |
| `services/api/tests/fixtures/eligibility/*.json` | **Create.** Nine recorded boards |
| `services/api/tests/fixtures/eligibility/labels.yaml` | **Create.** The answer key (human-written) |
| `services/api/nightshift/domain/eligibility_labels.py` | **Create.** Load and validate the answer key |
| `services/api/nightshift/domain/requirement_extraction.py` | **Create.** The extractor. Must not import the ORM |
| `services/api/nightshift/db/models.py` | **Modify.** `JobRequirement` |
| `services/api/nightshift/db/base.py` | **Modify.** `RequirementKind`, `RequirementNecessity` |
| `services/api/migrations/versions/*_job_requirements.py` | **Create.** Table, enums, span trigger |
| `services/api/nightshift/domain/ingestion.py` | **Modify.** Extract on job create/update |
| `services/api/nightshift/api/routes/jobs.py` | **Modify.** Requirements on job detail |
| `services/api/nightshift/api/schemas.py` | **Modify.** `JobRequirementOut` |
| `services/api/nightshift/discovery/coverage.py` | **Modify.** The fifth blind spot |
| `apps/web/src/lib/schemas.ts` | **Modify.** Zod for requirements |
| `apps/web/src/components/JobRequirements.tsx` | **Create.** Render, grouped by necessity |

---

## Task 1: Eligibility selectors for the recorder

The existing Greenhouse selectors in `scripts/record_fixture.py` choose postings by
*location shape* — that was M1's concern (invariant I1). M3a needs postings chosen
for *eligibility shape*, which is a different set entirely. Both live in the same
script behind a `--profile` flag.

**Files:**
- Modify: `scripts/record_fixture.py`
- Test: `services/api/tests/test_record_fixture_selectors.py` (create)

**Interfaces:**
- Produces: `ELIGIBILITY_SELECTORS: list[tuple[str, Callable[[dict], bool], int]]`
  and `curate(jobs, selectors)` — the existing `curate` gains a second parameter.
- Produces: `_content_text(job: dict[str, Any]) -> str` — HTML stripped, entities
  unescaped, whitespace collapsed. Greenhouse puts the description in `content`
  as escaped HTML.

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_record_fixture_selectors.py`:

```python
"""The eligibility selectors, exercised against the committed Datadog payload.

A selector that matches nothing is a selector that will silently contribute no
postings to the corpus, and the corpus is the answer key. These tests are how
that stays visible.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_recorder() -> Any:
    """Import scripts/record_fixture.py, which is not a package module."""
    spec = importlib.util.spec_from_file_location(
        "record_fixture", ROOT / "scripts" / "record_fixture.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["record_fixture"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recorder() -> Any:
    return _load_recorder()


def test_content_text_strips_html_and_unescapes_entities(recorder: Any) -> None:
    job = {"content": "&lt;p&gt;Bachelor&#39;s degree&lt;/p&gt;"}
    assert recorder._content_text(job) == "Bachelor's degree"


def test_content_text_collapses_whitespace(recorder: Any) -> None:
    job = {"content": "&lt;li&gt;3+   years\n\n  of experience&lt;/li&gt;"}
    assert recorder._content_text(job) == "3+ years of experience"


def test_every_eligibility_selector_has_a_reason_and_a_limit(recorder: Any) -> None:
    for why, predicate, limit in recorder.ELIGIBILITY_SELECTORS:
        assert why and isinstance(why, str)
        assert callable(predicate)
        assert limit >= 1


def test_the_phd_selector_matches_the_datadog_research_posting(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """The posting that motivated the `+equivalent` label field.

    Its text reads "You hold a PhD in Computer Science... (or have equivalent
    experience)", which is `matching.md` §3.2's worked example.
    """
    jobs = greenhouse_board_payload["jobs"]
    matched = [j for j in jobs if recorder._mentions_doctorate(j)]
    assert [j["title"] for j in matched] == [
        "AI Research Scientist - Datadog AI Research (DAIR)"
    ]


def test_the_equivalence_selector_matches_the_same_posting(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    jobs = greenhouse_board_payload["jobs"]
    matched = [j["title"] for j in jobs if recorder._mentions_equivalence(j)]
    assert "AI Research Scientist - Datadog AI Research (DAIR)" in matched


def test_curate_never_returns_the_same_posting_twice(
    recorder: Any, greenhouse_board_payload: dict[str, Any]
) -> None:
    """Two selectors can match one posting; the fixture must not duplicate it."""
    jobs = greenhouse_board_payload["jobs"]
    picked, reasons = recorder.curate(jobs, recorder.ELIGIBILITY_SELECTORS)
    ids = [j["id"] for j in picked]
    assert len(ids) == len(set(ids))
    assert set(reasons) == {str(i) for i in ids}
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/test_record_fixture_selectors.py -v
```

Expected: FAIL — `AttributeError: module 'record_fixture' has no attribute '_content_text'`.

- [ ] **Step 3: Implement the selectors**

In `scripts/record_fixture.py`, after the existing `GREENHOUSE_SELECTORS`:

```python
def _content_text(job: dict[str, Any]) -> str:
    """Greenhouse ships the description as escaped HTML inside `content`.

    Unescaped twice on purpose: the payload is HTML-escaped, and the HTML it
    decodes to contains its own entities (`&amp;nbsp;` is common).
    """
    raw = job.get("content") or ""
    text = html.unescape(html.unescape(str(raw)))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _mentions_doctorate(job: dict[str, Any]) -> bool:
    return bool(re.search(r"\b(ph\.?d|doctorate)\b", _content_text(job), re.I))


def _mentions_equivalence(job: dict[str, Any]) -> bool:
    """"or equivalent experience" — the escape hatch A13 names by hand."""
    return bool(re.search(r"\bor\s+(have\s+)?equivalent\b", _content_text(job), re.I))


#: Words that make a "sponsor" an immigration statement rather than a sales one.
_IMMIGRATION_CONTEXT = (
    r"visa|immigration|work(?:ing)? authorai?[sz]ation|work permit|right to work|"
    r"h-?1-?b|green card|employment eligibility|citizenship"
)


def _mentions_sponsorship(job: dict[str, Any]) -> bool:
    """Visa sponsorship, not "executive sponsor for strategic customers".

    A bare `\\bsponsor\\b` was the first version and it was wrong on real data:
    Datadog's "Area Vice President, Sales Engineering" says *"Serve as an
    executive sponsor for strategic customers"* and was selected as this
    board's sole sponsorship exemplar. A corpus whose one example of a shape is
    the wrong shape is worse than one with a hole, because the hole is recorded
    in `coverage_not_available_on_this_board` and the wrong example is not.

    Either an explicit sponsorship phrase, or "sponsor" sharing a sentence with
    immigration vocabulary.
    """
    text = _content_text(job)
    if re.search(r"\b(visa|immigration)\s+sponsor", text, re.I):
        return True
    if re.search(r"sponsorship\s+(is|are)?\s*(not\s+)?(available|offered|provided)", text, re.I):
        return True
    for sentence in re.split(r"(?<=[.;!?])\s+", text):
        if re.search(r"\bsponsor(ship|ing|ed|s)?\b", sentence, re.I) and re.search(
            _IMMIGRATION_CONTEXT, sentence, re.I
        ):
            return True
    return False


def _states_graduation_year(job: dict[str, Any]) -> bool:
    """A graduation window stated numerically — "graduating in 2027"."""
    text = _content_text(job)
    return bool(re.search(r"graduat\w*[^.]{0,60}\b20\d{2}\b", text, re.I))


def _states_years_of_experience(job: dict[str, Any]) -> bool:
    return bool(re.search(r"\b\d{1,2}\s*\+?\s*years?\b", _content_text(job), re.I))


def _has_preferred_section(job: dict[str, Any]) -> bool:
    """The section whose contents must never become a gap."""
    return bool(
        re.search(
            r"(nice[- ]to[- ]have|bonus points|preferred qualifications|"
            r"pluses|it'?s a plus)",
            _content_text(job),
            re.I,
        )
    )


def _title_matches(job: dict[str, Any], pattern: str) -> bool:
    return bool(re.search(pattern, job.get("title", ""), re.I))


#: Chosen for *eligibility* shape. The existing GREENHOUSE_SELECTORS choose for
#: location shape, which was M1's invariant (I1) and is a different question.
#: Every reason here names a case AMENDMENTS A13 lists as genuinely hard.
ELIGIBILITY_SELECTORS: list[tuple[str, Callable[[dict[str, Any]], bool], int]] = [
    ("internship in the title",
     lambda j: _title_matches(j, r"\b(intern|internship|co-?op)\b"), 3),
    ("new grad / university programme in the title",
     lambda j: _title_matches(j, r"\b(new ?grad|university|campus|early career)\b"), 2),
    ("a graduation year stated numerically",
     _states_graduation_year, 3),
    ("sponsorship stated in writing",
     _mentions_sponsorship, 2),
    ("a doctorate named as a requirement",
     _mentions_doctorate, 2),
    ("'or equivalent experience' — the A13 escape hatch",
     _mentions_equivalence, 2),
    ("a numeric years-of-experience requirement",
     _states_years_of_experience, 3),
    ("a preferred / nice-to-have section, whose contents are not gaps",
     _has_preferred_section, 3),
    ("senior or above in the title — the seniority mismatch case",
     lambda j: _title_matches(j, r"\b(senior|staff|principal|lead|director|vp)\b"), 2),
    ("multi-level posting spanning an eligibility boundary",
     lambda j: _title_matches(j, r"\b(i{1,3}|1|2|3)\s*/\s*(i{1,3}|1|2|3)\b"), 1),
    ("non-engineering role at a technical employer",
     lambda j: not _title_matches(
         j, r"\b(engineer|developer|scientist|researcher|swe|programmer)\b"), 2),
]
```

Change `curate` to take the selector list, keeping the existing behaviour:

```python
def curate(
    jobs: list[dict[str, Any]],
    selectors: list[tuple[str, Callable[[dict[str, Any]], bool], int]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    selectors = selectors if selectors is not None else GREENHOUSE_SELECTORS
    picked: list[dict[str, Any]] = []
    chosen_ids: set[Any] = set()
    reasons: dict[str, str] = {}
    for why, predicate, limit in selectors:
        found = 0
        for job in jobs:
            if found >= limit:
                break
            if job.get("id") in chosen_ids or not predicate(job):
                continue
            picked.append(job)
            chosen_ids.add(job["id"])
            reasons[str(job["id"])] = why
            found += 1
    return picked, reasons
```

Add `import html` at the top if it is not already there, and wire the flag in
`main()`:

```python
    parser.add_argument(
        "--profile",
        choices=("locations", "eligibility"),
        default="locations",
        help="which selector set to curate with (greenhouse only)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="fixture subdirectory (default: the provider name)",
    )
```

and where Greenhouse is curated:

```python
    if args.provider == "greenhouse":
        jobs = payload.get("jobs") or []
        selectors = (
            ELIGIBILITY_SELECTORS if args.profile == "eligibility"
            else GREENHOUSE_SELECTORS
        )
        fixture_body_jobs, reasons = curate(jobs, selectors)
        missing = unmatched_shapes(jobs, selectors)
```

`missing` becomes the `coverage_not_available_on_this_board` list, which is the
existing meta contract — a shape no posting on the board has is recorded rather
than silently dropped.

**It must be computed from the predicates, not from `reasons`.** Add:

```python
def unmatched_shapes(
    jobs: list[dict[str, Any]],
    selectors: list[tuple[str, Callable[[dict[str, Any]], bool], int]],
) -> list[str]:
    """Shapes no posting on this board has at all.

    Deliberately **not** `[why for why, _, _ in selectors if why not in
    reasons.values()]`, which was this plan's first version and which lies.
    `curate` is greedy and first-claim-wins: when one posting satisfies two
    selectors, the earlier one takes it and the later one contributes nothing —
    so the later shape is reported absent from a board that demonstrably has it.

    Measured on the committed Datadog fixture: job 6572669, the AI Research
    Scientist posting this plan cites in §3.2 as the "PhD or equivalent
    experience" worked example, matches both `_mentions_doctorate` and
    `_mentions_equivalence`. Doctorate is listed first, so recording that board
    wrote *"'or equivalent experience' — the A13 escape hatch"* into the
    board's "could not demonstrate" list — for a board whose text contains that
    exact phrase.

    A coverage list that reports a gap where there is none teaches its reader
    to stop believing it, which costs more than having no list.
    """
    return [why for why, predicate, _ in selectors if not any(predicate(j) for j in jobs)]
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
cd services/api && .venv/bin/pytest tests/test_record_fixture_selectors.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Prove a selector can fail**

Temporarily change `_mentions_doctorate`'s regex to `r"\bmasters\b"`. Run the
suite. `test_the_phd_selector_matches_the_datadog_research_posting` must go red.
Revert.

- [ ] **Step 6: Commit**

```bash
make check
git add scripts/record_fixture.py services/api/tests/test_record_fixture_selectors.py
git commit -m "feat(fixtures): select postings by eligibility shape, not location"
```

---

## Task 2: Record the nine boards

Human-invoked, needs the network, run once. Nine boards, all confirmed live on
2026-08-04.

**Files:**
- Create: `services/api/tests/fixtures/eligibility/*.json` and `*.meta.json`
- Test: `services/api/tests/test_fixture_provenance.py` (modify — it already
  asserts every fixture has a meta file; extend it to the new directory)

- [ ] **Step 1: Record all nine**

```bash
for t in janestreet jumptrading imc databricks anthropic point72 akunacapital oldmissioncapital; do
  python scripts/record_fixture.py greenhouse "$t" \
      --profile eligibility --out-dir eligibility --name "${t}_eligibility"
done
python scripts/record_fixture.py ashby openai \
    --profile eligibility --out-dir eligibility --name openai_eligibility --limit 8
```

Ashby and Lever keep their existing shape reducers — they curate by
`(location, employmentType)` and there is no eligibility variant for them in this
task. OpenAI is in the corpus for ATS spread, not for selector coverage.

- [ ] **Step 2: Read what you actually got**

```bash
python - <<'PY'
import json, pathlib
total = 0
for p in sorted(pathlib.Path("services/api/tests/fixtures/eligibility").glob("*.meta.json")):
    meta = json.loads(p.read_text())
    body = json.loads(p.with_name(p.name.replace(".meta", "")).read_text())
    jobs = body["jobs"] if isinstance(body, dict) else body
    total += len(jobs)
    print(f"{p.stem:34} {len(jobs):3} kept of {meta['provenance']['full_response_job_count']:4}"
          f"   gaps: {meta.get('coverage_not_available_on_this_board')}")
print("total postings:", total)
PY
```

**Do not proceed until `total` is at least 55.** A13 asks for at least 50 and the
plan targets ~60. If a board contributed nothing, its `gaps` list says which
selectors missed, and that is the signal to widen a selector — not to lower the
target.

- [ ] **Step 3: Extend the provenance test to the new directory**

`services/api/tests/test_fixture_provenance.py` already walks the fixture tree.
Confirm it covers `eligibility/` by running it; if it hard-codes the three
provider directories, add `eligibility` to that tuple.

```bash
cd services/api && .venv/bin/pytest tests/test_fixture_provenance.py -v
```

- [ ] **Step 4: Commit**

```bash
make check
git add services/api/tests/fixtures/eligibility services/api/tests/test_fixture_provenance.py
git commit -m "test(fixtures): record nine boards for the eligibility corpus"
```

---

## Task 3: The worksheet generator

Turns the corpus into two artefacts: a blank answer key for a human to fill in,
and a readable worksheet showing only the part of each posting where requirements
live. A 5,800-character description is not something anyone will read sixty times.

**Files:**
- Create: `scripts/make_label_worksheet.py`
- Create: `services/api/tests/test_label_worksheet.py`

**Interfaces:**
- Produces: `requirements_excerpt(text: str, *, window: int = 1200) -> str`
- Produces: `blank_label(posting_id: str, title: str) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_label_worksheet.py`:

```python
"""The worksheet generator.

The excerpt is the only part of a posting a human will read, so a bug here does
not produce a wrong label — it produces a label made from the wrong evidence,
which is worse because it looks identical.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def worksheet() -> Any:
    spec = importlib.util.spec_from_file_location(
        "make_label_worksheet", ROOT / "scripts" / "make_label_worksheet.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_label_worksheet"] = module
    spec.loader.exec_module(module)
    return module


def test_the_excerpt_starts_at_the_requirements_heading(worksheet: Any) -> None:
    text = (
        "ABOUT US We are a company. " * 20
        + "WHAT YOU'LL NEED Proficiency in Kotlin. "
        + "NICE TO HAVES Experience with React."
    )
    excerpt = worksheet.requirements_excerpt(text)
    assert excerpt.startswith("WHAT YOU'LL NEED")
    assert "Proficiency in Kotlin" in excerpt


def test_the_excerpt_keeps_the_preferred_section(worksheet: Any) -> None:
    """The nice-to-have section is the single most important thing to label.

    An excerpt that stops at the required list would produce an answer key with
    an empty `mentioned_not_required` for every posting, and that field is the
    difference between a usable product and one that reports nine false gaps.
    """
    text = "WHAT YOU'LL NEED Kotlin. NICE TO HAVES React, TypeScript, Flask."
    excerpt = worksheet.requirements_excerpt(text)
    assert "NICE TO HAVES" in excerpt
    assert "Flask" in excerpt


def test_the_excerpt_falls_back_to_the_whole_text_when_no_heading_matches(
    worksheet: Any,
) -> None:
    """No heading is not a reason to show nothing. It is a reason to show all."""
    text = "We want someone who can write Kotlin and has shipped an app."
    assert worksheet.requirements_excerpt(text) == text


def _posting(pid: str, title: str, reason: str) -> dict[str, Any]:
    return {"id": pid, "title": title, "reason": reason, "text": "REQUIREMENTS Python."}


def test_selection_covers_every_reason_before_deepening_any(worksheet: Any) -> None:
    """Round-robin across shapes, not the first N in file order.

    Taking postings in file order would hand back sixty postings from three
    boards with whole eligibility shapes missing, and the answer key would be
    blind to exactly the cases A13 calls hard.
    """
    postings = [("b1", _posting(f"a{i}", f"Engineer {i}", "internship")) for i in range(50)]
    postings += [("b2", _posting("z1", "Researcher", "doctorate"))]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert "doctorate" in {p["reason"] for _, p in picked}


def test_a_reason_with_one_example_still_contributes(worksheet: Any) -> None:
    """A shape with a single instance is the one most likely to be got wrong."""
    postings = [("b1", _posting(f"a{i}", f"Engineer {i}", "internship")) for i in range(100)]
    postings += [("b2", _posting("solo", "Research Scientist", "doctorate"))]
    picked = worksheet.select_for_labeling(postings, target=60)
    assert ("b2", postings[-1][1]) in picked


def test_recruiting_roles_are_skipped(worksheet: Any) -> None:
    """"Campus Recruiter" matched the new-grad selector on a real board.

    It is a job recruiting new grads, not a job for one. Labeling it teaches
    the answer key nothing about new-grad eligibility.
    """
    postings = [
        ("b1", _posting("1", "Campus Recruiter", "new grad")),
        ("b1", _posting("2", "University Recruiter", "new grad")),
        ("b1", _posting("3", "Software Engineer, New Grad", "new grad")),
    ]
    picked = worksheet.select_for_labeling(postings, target=3)
    assert [p["title"] for _, p in picked] == ["Software Engineer, New Grad"]


def test_a_reason_made_entirely_of_recruiting_roles_still_contributes(
    worksheet: Any,
) -> None:
    """Dropping every posting under a reason would delete the shape silently.

    Better a weak example the human can mark odd in `note` than a shape that
    vanishes without appearing anywhere.
    """
    postings = [("b1", _posting("1", "Campus Recruiter", "new grad"))]
    picked = worksheet.select_for_labeling(postings, target=5)
    assert len(picked) == 1


def test_selection_is_deterministic(worksheet: Any) -> None:
    """Regenerating must not reshuffle what a human has already worked through."""
    postings = [
        ("b2", _posting("9", "B", "internship")),
        ("b1", _posting("3", "A", "doctorate")),
        ("b1", _posting("1", "C", "internship")),
    ]
    first = worksheet.select_for_labeling(postings, target=3)
    second = worksheet.select_for_labeling(list(reversed(postings)), target=3)
    assert [p["id"] for _, p in first] == [p["id"] for _, p in second]


def test_selection_never_pads_past_the_corpus(worksheet: Any) -> None:
    postings = [("b1", _posting("1", "Engineer", "internship"))]
    assert len(worksheet.select_for_labeling(postings, target=60)) == 1


def test_no_posting_is_selected_twice(worksheet: Any) -> None:
    postings = [("b1", _posting(str(i), f"Engineer {i}", "internship")) for i in range(80)]
    picked = worksheet.select_for_labeling(postings, target=60)
    keys = [(b, p["id"]) for b, p in picked]
    assert len(keys) == len(set(keys)) == 60


def test_a_blank_label_has_every_field_and_no_value(worksheet: Any) -> None:
    label = worksheet.blank_label("abc123", "Software Engineer Internship")
    assert label["title"] == "Software Engineer Internship"
    for field in (
        "is_internship",
        "graduation_window",
        "enrollment_required",
        "degree",
        "min_years_experience",
        "required_tech",
        "mentioned_not_required",
        "sponsorship",
        "note",
    ):
        assert field in label, field
    assert label["is_internship"] == "TO_LABEL"
    assert label["required_tech"] == "TO_LABEL"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/test_label_worksheet.py -v
```

Expected: FAIL — the script does not exist.

- [ ] **Step 3: Write the generator**

`scripts/make_label_worksheet.py`:

```python
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
_REQUIREMENT_HEADINGS = (
    "preferred qualifications",
    "minimum qualifications",
    "basic qualifications",
    "what you'll need",
    "what you will need",
    "what we're looking for",
    "who you are",
    "requirements",
    "qualifications",
    "nice to have",
    "nice to haves",
    "bonus points",
    "you have",
    "about you",
)

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

#: Titles that match an eligibility selector but are not the thing it is for.
#: "Campus Recruiter" and "University Recruiter" matched "new grad / university
#: programme in the title" on the real boards — those are jobs recruiting new
#: grads, not jobs for them. Measured, not guessed: 3 of that selector's 8 hits.
_NOT_ENTRY_LEVEL = re.compile(
    r"\b(recruit(er|ing|ment)|talent|sourcer|university relations|campus relations)\b",
    re.I,
)


def plain_text(raw: str) -> str:
    text = html.unescape(html.unescape(raw or ""))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def requirements_excerpt(text: str, *, window: int = 1200) -> str:
    """The region where requirements live, or the whole text if none is found.

    Starts at the *earliest* requirement heading and runs `window` characters,
    which is what keeps the preferred section in frame — it almost always
    follows the required one, and it is the section that matters most to label.
    """
    lowered = text.lower()
    starts = [lowered.find(h) for h in _REQUIREMENT_HEADINGS]
    found = [s for s in starts if s >= 0]
    if not found:
        return text
    start = min(found)
    return text[start : start + window]


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
    * **Titles matching ``_NOT_ENTRY_LEVEL`` are skipped** unless dropping one
      would empty its reason. "Campus Recruiter" matched the new-grad selector
      on a real board; it is a job recruiting new grads, not a job for one, and
      labeling it teaches the answer key nothing about new-grad eligibility.

    Deterministic: same corpus in, same 60 out, so regenerating the worksheet
    never reshuffles what a human has already worked through.
    """
    by_reason: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for board, posting in postings:
        by_reason.setdefault(posting["reason"], []).append((board, posting))

    for entries in by_reason.values():
        entries.sort(key=lambda bp: (bp[0], bp[1]["id"]))
        keep = [bp for bp in entries if not _NOT_ENTRY_LEVEL.search(bp[1]["title"])]
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
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
cd services/api && .venv/bin/pytest tests/test_label_worksheet.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Generate the worksheet**

```bash
python scripts/make_label_worksheet.py
```

- [ ] **Step 6: Prove re-running preserves work**

```bash
python - <<'PY'
import yaml, pathlib
p = pathlib.Path("services/api/tests/fixtures/eligibility/labels.yaml")
d = yaml.safe_load(p.read_text())
board = sorted(d["boards"])[0]
pid = sorted(d["boards"][board])[0]
d["boards"][board][pid]["is_internship"] = "no"
p.write_text(yaml.safe_dump(d, sort_keys=True, allow_unicode=True))
print("set a label on", board, pid)
PY
python scripts/make_label_worksheet.py
python - <<'PY'
import yaml, pathlib
d = yaml.safe_load(pathlib.Path(
    "services/api/tests/fixtures/eligibility/labels.yaml").read_text())
board = sorted(d["boards"])[0]
pid = sorted(d["boards"][board])[0]
assert d["boards"][board][pid]["is_internship"] == "no", "regeneration ate a label"
print("preserved")
PY
```

Expected: `preserved`. Revert that one label to `TO_LABEL` afterwards.

- [ ] **Step 7: Commit**

```bash
make check
git add scripts/make_label_worksheet.py services/api/tests/test_label_worksheet.py \
        services/api/tests/fixtures/eligibility/labels.yaml docs/labeling
git commit -m "feat(matching): generate the eligibility labeling worksheet"
```

---

## HUMAN GATE

**Stop here.** Tahmudun fills in
`services/api/tests/fixtures/eligibility/labels.yaml`, reading
`docs/labeling/eligibility-worksheet.md`. Roughly 60 postings, 60–90 minutes.

Task 4 does not need the labels and can be built during the gate. **Tasks 6 and 7
must not start until the labels are committed** — that is `matching.md` §1.1 and
it is the reason this plan is ordered as it is.

---

## Task 4: The answer key's schema and loader

Buildable during the gate. Validates the key and refuses a partial one, so
"labeling is finished" is a command rather than a belief.

**Files:**
- Create: `services/api/nightshift/domain/eligibility_labels.py`
- Create: `services/api/tests/test_eligibility_labels.py`

**Interfaces:**
- Produces: `class PostingLabel(BaseModel)` with fields `title: str`,
  `is_internship: Literal["yes","no","unclear"]`,
  `graduation_window: str`, `enrollment_required: Literal["yes","no","not_stated"]`,
  `degree: str`, `min_years_experience: int | None`,
  `required_tech: list[str]`, `mentioned_not_required: list[str]`,
  `sponsorship: Literal["offered","not_offered","not_stated"]`, `note: str`
- Produces: `class AnswerKey(BaseModel)` with `boards: dict[str, dict[str, PostingLabel]]`
- Produces: `load_answer_key(path: Path | None = None) -> AnswerKey`
- Produces: `unlabeled(key_text: str) -> list[str]` — `"board/posting_id/field"`
  for every field still reading `TO_LABEL`
- Produces: `DEGREE_VALUES: frozenset[str]`

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_eligibility_labels.py`:

```python
"""The answer key's own guards.

A label that parses but says nothing is the failure this file exists to catch:
`TO_LABEL` is a valid string, so without an explicit check a half-filled key
would load cleanly and every metric computed against it would be quietly wrong.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nightshift.domain.eligibility_labels import (
    AnswerKey,
    PostingLabel,
    load_answer_key,
    unlabeled,
)

_COMPLETE = {
    "title": "Software Engineer Internship, Android",
    "is_internship": "yes",
    "graduation_window": "2026-2028",
    "enrollment_required": "yes",
    "degree": "bachelors",
    "min_years_experience": None,
    "required_tech": ["Kotlin"],
    "mentioned_not_required": ["React", "TypeScript"],
    "sponsorship": "not_stated",
    "note": "",
}


def test_a_complete_label_parses() -> None:
    label = PostingLabel.model_validate(_COMPLETE)
    assert label.required_tech == ["Kotlin"]
    assert label.min_years_experience is None


def test_a_degree_may_carry_the_equivalence_suffix() -> None:
    """A13: "PhD or equivalent experience" is not a hard blocker."""
    label = PostingLabel.model_validate({**_COMPLETE, "degree": "phd+equivalent"})
    assert label.degree == "phd+equivalent"
    assert label.has_degree_equivalence is True


def test_a_degree_without_the_suffix_does_not_claim_equivalence() -> None:
    label = PostingLabel.model_validate({**_COMPLETE, "degree": "phd"})
    assert label.has_degree_equivalence is False


def test_an_unknown_degree_is_refused() -> None:
    with pytest.raises(ValidationError):
        PostingLabel.model_validate({**_COMPLETE, "degree": "postdoc"})


def test_a_technology_may_not_appear_in_both_lists() -> None:
    """Required and merely-mentioned are exclusive. Both would make the
    precision metric meaningless, since either answer would score."""
    with pytest.raises(ValidationError):
        PostingLabel.model_validate(
            {**_COMPLETE, "required_tech": ["Kotlin"], "mentioned_not_required": ["Kotlin"]}
        )


def test_unlabeled_reports_every_field_still_saying_to_label() -> None:
    text = """
boards:
  janestreet_eligibility:
    "42":
      title: Software Engineer
      is_internship: TO_LABEL
      graduation_window: not_stated
      enrollment_required: TO_LABEL
      degree: none
      min_years_experience: not_stated
      required_tech: []
      mentioned_not_required: []
      sponsorship: not_stated
      note: ""
"""
    assert unlabeled(text) == [
        "janestreet_eligibility/42/enrollment_required",
        "janestreet_eligibility/42/is_internship",
    ]


def _labeling_state() -> tuple[int, int]:
    """(fields still unlabeled, postings in the key). Cheap, and read twice."""
    from nightshift.domain.eligibility_labels import ANSWER_KEY_PATH

    if not ANSWER_KEY_PATH.exists():
        return (0, 0)
    remaining = len(unlabeled(ANSWER_KEY_PATH.read_text()))
    key = load_answer_key() if remaining == 0 else None
    total = sum(len(v) for v in key.boards.values()) if key else 0
    return (remaining, total)


_REMAINING, _POSTINGS = _labeling_state()

#: The gate tests skip — with a reason naming the shortfall — while the human
#: is still labeling, and activate by themselves the moment the key is filled
#: in. Decided 2026-08-04 rather than leaving them red: a red suite for however
#: long labeling takes destroys "is `make check` green" as a usable signal, and
#: this project's whole discipline rests on that question having an answer.
#:
#: A skip that could go stale is worse than a red test, so
#: `test_the_skip_condition_is_honest` below asserts the condition itself.
skip_until_labeled = pytest.mark.skipif(
    _REMAINING > 0,
    reason=f"answer key incomplete: {_REMAINING} fields still say TO_LABEL",
)


def test_the_skip_condition_is_honest() -> None:
    """Never skipped. Asserts the two gate tests skip for a real reason.

    Without this, a bug in `unlabeled` that returned `[]` on a blank key would
    silently un-skip both gates and they would pass over nothing at all.
    """
    from nightshift.domain.eligibility_labels import ANSWER_KEY_PATH

    assert ANSWER_KEY_PATH.exists(), "the answer key file is missing entirely"
    remaining, _ = _labeling_state()
    if remaining == 0:
        # Labeling is done: prove the checker can still see an unlabeled field.
        assert unlabeled("boards: {b: {'1': {is_internship: TO_LABEL}}}") == [
            "b/1/is_internship"
        ]


@skip_until_labeled
def test_the_committed_answer_key_is_complete() -> None:
    """The gate. Skipped while labeling is in progress; then it must hold."""
    from nightshift.domain.eligibility_labels import ANSWER_KEY_PATH

    remaining = unlabeled(ANSWER_KEY_PATH.read_text())
    assert remaining == [], f"{len(remaining)} fields still unlabeled, e.g. {remaining[:5]}"


@skip_until_labeled
def test_the_committed_answer_key_parses_and_is_big_enough() -> None:
    """A13 asks for at least 50 real postings."""
    key = load_answer_key()
    total = sum(len(v) for v in key.boards.values())
    assert total >= 50, f"answer key holds {total} postings, A13 requires 50"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/test_eligibility_labels.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the loader**

`services/api/nightshift/domain/eligibility_labels.py`:

```python
"""The answer key: what each corpus posting *requires*, as a human read it.

`docs/architecture/matching.md` §3.1 decided this labels the posting rather than
a verdict for a particular person. A verdict bakes in a graduation date and an
authorization status, both of which change; when they change every label goes
silently wrong while continuing to pass.

Nothing here imports the ORM. The answer key is fixture data and the grader is a
test — neither may reach the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ANSWER_KEY_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "eligibility"
    / "labels.yaml"
)

#: The sentinel `make_label_worksheet.py` writes into every blank field.
UNLABELED = "TO_LABEL"

_DEGREE_BASE = ("none", "bachelors", "masters", "phd")
DEGREE_VALUES: frozenset[str] = frozenset(
    [*_DEGREE_BASE, *(f"{d}+equivalent" for d in _DEGREE_BASE)]
)


class PostingLabel(BaseModel):
    """One posting's stated requirements. Never a verdict about a person."""

    model_config = ConfigDict(frozen=True)

    title: str
    is_internship: Literal["yes", "no", "unclear"]
    graduation_window: str
    enrollment_required: Literal["yes", "no", "not_stated"]
    degree: str
    min_years_experience: int | None = None
    required_tech: list[str] = Field(default_factory=list)
    mentioned_not_required: list[str] = Field(default_factory=list)
    sponsorship: Literal["offered", "not_offered", "not_stated"]
    note: str = ""

    @property
    def has_degree_equivalence(self) -> bool:
        """A13's escape hatch. Must resolve to `uncertain`, never `ineligible`."""
        return self.degree.endswith("+equivalent")

    @model_validator(mode="after")
    def _check(self) -> PostingLabel:
        if self.degree not in DEGREE_VALUES:
            raise ValueError(f"degree {self.degree!r} not in {sorted(DEGREE_VALUES)}")
        overlap = {t.casefold() for t in self.required_tech} & {
            t.casefold() for t in self.mentioned_not_required
        }
        if overlap:
            raise ValueError(
                f"{sorted(overlap)} is in both required_tech and "
                "mentioned_not_required; a metric computed against that scores "
                "either answer as correct"
            )
        return self


class AnswerKey(BaseModel):
    boards: dict[str, dict[str, PostingLabel]]


def unlabeled(key_text: str) -> list[str]:
    """Every field still reading TO_LABEL, as `board/posting/field`, sorted.

    Reads the raw YAML rather than the parsed model on purpose: `TO_LABEL` is a
    valid string and several fields are typed `str`, so a partly-filled key
    parses cleanly. This is the only thing that can tell the difference.
    """
    raw: dict[str, Any] = yaml.safe_load(key_text) or {}
    missing: list[str] = []
    for board, postings in (raw.get("boards") or {}).items():
        for posting_id, label in (postings or {}).items():
            for field, value in (label or {}).items():
                if value == UNLABELED:
                    missing.append(f"{board}/{posting_id}/{field}")
    return sorted(missing)


def _coerce(label: dict[str, Any]) -> dict[str, Any]:
    """`not_stated` is how a human writes "the posting does not say"."""
    out = dict(label)
    if out.get("min_years_experience") in ("not_stated", "", None):
        out["min_years_experience"] = None
    return out


def load_answer_key(path: Path | None = None) -> AnswerKey:
    raw = yaml.safe_load((path or ANSWER_KEY_PATH).read_text()) or {}
    boards = {
        board: {pid: PostingLabel.model_validate(_coerce(label))
                for pid, label in (postings or {}).items()}
        for board, postings in (raw.get("boards") or {}).items()
    }
    return AnswerKey(boards=boards)
```

- [ ] **Step 4: Run the tests**

```bash
cd services/api && .venv/bin/pytest tests/test_eligibility_labels.py -v
```

Expected: **7 passed, 2 skipped** — the two gate tests skip with a reason naming
how many fields are still unlabeled, and `test_the_skip_condition_is_honest`
passes, which is what stops the skip from being a place things hide.

`make check` must be **green**. If it is red, the skip marks are wrong; fix them
rather than lowering anything.

- [ ] **Step 5: Prove the gate actually closes**

The skip is only trustworthy if the tests really run once labeling is done.
Verify with a throwaway complete key:

```bash
python - <<'PY'
import pathlib, yaml
p = pathlib.Path("services/api/tests/fixtures/eligibility/labels.yaml")
backup = p.read_text()
p.write_text(yaml.safe_dump({"boards": {"probe": {"1": {
    "title": "T", "is_internship": "no", "graduation_window": "not_stated",
    "enrollment_required": "not_stated", "degree": "none",
    "min_years_experience": "not_stated", "required_tech": [],
    "mentioned_not_required": [], "sponsorship": "not_stated", "note": ""}}}}))
pathlib.Path("/tmp/labels.bak").write_text(backup)
PY
cd services/api && .venv/bin/pytest tests/test_eligibility_labels.py -v
```

Expected: the two gate tests now **run**, and `..._is_big_enough` **fails** with
`answer key holds 1 postings, A13 requires 50`. That failure is the proof the
gate is load-bearing. Restore:

```bash
cp /tmp/labels.bak services/api/tests/fixtures/eligibility/labels.yaml
```

- [ ] **Step 6: Commit**

```bash
make check   # must be green
git add services/api/nightshift/domain/eligibility_labels.py \
        services/api/tests/test_eligibility_labels.py
git commit -m "feat(matching): load and validate the eligibility answer key"
```

Record in the commit body that two tests skip until labeling completes, that the
skip reason names the shortfall, and that `test_the_skip_condition_is_honest` is
what keeps the skip from going stale.

---

## Task 5: `job_requirements` — the table, the enums, the span trigger

**Files:**
- Modify: `services/api/nightshift/db/base.py` (two enums)
- Modify: `services/api/nightshift/db/models.py` (`JobRequirement`)
- Create: `services/api/migrations/versions/<rev>_job_requirements.py`
- Create: `services/api/tests/test_job_requirement_models.py`

**Interfaces:**
- Produces: `RequirementKind` — `degree`, `graduation_window`, `years_experience`,
  `technology`, `authorization`, `enrollment`, `role_level`
- Produces: `RequirementNecessity` — `required`, `preferred`, `mentioned`
- Produces: `JobRequirement` with `job_id`, `kind`, `value`, `raw_text`,
  `char_start`, `char_end`, `necessity`, `has_equivalence`, `extractor_version`

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_job_requirement_models.py`:

```python
"""The span trigger, and the constraints around it.

`resume_extractions` has the same guard for the same reason: a requirement
nobody can trace back to a sentence is not auditable, and one whose span quotes
different words than it claims is worse than none at all.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import RequirementKind, RequirementNecessity
from nightshift.db.models import JobRequirement

pytestmark = pytest.mark.asyncio


async def _job_with_text(session: AsyncSession, text: str) -> object:
    """Build a canonical job carrying `text` as its description.

    Uses the same helper the other model tests use; see
    `tests/test_models_canonical_spine.py` for the company/source setup it
    needs, and reuse it rather than duplicating a second builder.
    """
    from tests.test_models_canonical_spine import make_job  # existing helper

    job = await make_job(session, description_text=text)
    return job


async def test_a_requirement_quoting_its_span_is_accepted(
    db_session: AsyncSession,
) -> None:
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start,
            char_end=start + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    await db_session.flush()


async def test_a_span_that_quotes_the_wrong_words_is_refused(
    db_session: AsyncSession,
) -> None:
    """One character of drift and the highlight disagrees with the claim."""
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start + 1,          # off by one
            char_end=start + 1 + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    with pytest.raises(DBAPIError, match="does not quote"):
        await db_session.flush()


async def test_a_span_running_past_the_description_is_refused(
    db_session: AsyncSession,
) -> None:
    text = "Kotlin."
    job = await _job_with_text(db_session, text)
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=0,
            char_end=9999,
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    with pytest.raises(DBAPIError, match="runs past"):
        await db_session.flush()


async def test_an_inverted_span_is_refused(db_session: AsyncSession) -> None:
    text = "Kotlin."
    job = await _job_with_text(db_session, text)
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=6,
            char_end=2,
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

- [ ] **Step 2: Run it and watch it fail**

```bash
make up && make migrate
cd services/api && .venv/bin/pytest tests/test_job_requirement_models.py -v
```

Expected: FAIL — `ImportError: cannot import name 'RequirementKind'`.

- [ ] **Step 3: Add the enums**

In `services/api/nightshift/db/base.py`, beside the other `StrEnum`s:

```python
class RequirementKind(enum.StrEnum):
    """What a posting is asking for. Each value is something a rule can find.

    Deliberately absent: anything about culture, drive, or "passion". A rule
    cannot find those and a score built on them would be taste wearing a
    number's clothes.
    """

    DEGREE = "degree"
    GRADUATION_WINDOW = "graduation_window"
    YEARS_EXPERIENCE = "years_experience"
    TECHNOLOGY = "technology"
    AUTHORIZATION = "authorization"
    ENROLLMENT = "enrollment"
    ROLE_LEVEL = "role_level"


class RequirementNecessity(enum.StrEnum):
    """How hard the ask is. `matching.md` §4.1: this is the column the product
    turns on.

    Only ``required`` may produce a missing-requirement penalty or appear as a
    gap. Ramp's Android internship lists nine technologies under "nice to
    haves"; treating those as required reports nine false gaps against a
    candidate who is fully qualified.
    """

    REQUIRED = "required"
    PREFERRED = "preferred"
    MENTIONED = "mentioned"
```

- [ ] **Step 4: Add the model**

In `services/api/nightshift/db/models.py`, importing the two new enums from
`nightshift.db.base` in the existing import block:

```python
class JobRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What a posting asks for, and the characters where it says so.

    **Invariant I2 does not govern this table**, though it looks like it should.
    I2 is about claims regarding a *person's* qualifications, which is why
    `resume_extractions` proposes and never confirms. A job requirement is a
    claim about a *posting*, checkable against a payload committed in the same
    repository. It needs no confirmation step.

    It still quotes its span, enforced by trigger, because a requirement nobody
    can trace back to a sentence is not auditable — and the job page shows the
    sentence rather than asking anyone to trust a summary.
    """

    __tablename__ = "job_requirements"
    __table_args__ = (
        Index("ix_job_requirements_job_id", "job_id"),
        # The extractor emits one row per (kind, value, span). A second run over
        # unchanged text must not double the rows.
        UniqueConstraint(
            "job_id", "kind", "value", "char_start", name="uq_job_requirements_span"
        ),
        CheckConstraint("char_start >= 0", name="char_start_is_not_negative"),
        CheckConstraint("char_end > char_start", name="span_runs_forwards"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[RequirementKind] = mapped_column(
        _enum(RequirementKind, "requirement_kind"), nullable=False
    )
    #: Normalized: a skill name from `data/skills.yaml`, a year range, an integer
    #: as a string. `raw_text` is what the posting actually said.
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_text: Mapped[str] = mapped_column(String(500), nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    necessity: Mapped[RequirementNecessity] = mapped_column(
        _enum(RequirementNecessity, "requirement_necessity"), nullable=False
    )
    #: "or equivalent experience". A13: this is not a hard blocker, and M3b's
    #: gate must resolve it to `uncertain` rather than `ineligible`.
    has_equivalence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)

    job: Mapped[Job] = relationship(back_populates="requirements")
```

Add `Boolean` to the `sqlalchemy` import list, and on `Job`:

```python
    requirements: Mapped[list[JobRequirement]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
```

- [ ] **Step 5: Generate the migration and fix what autogenerate gets wrong**

```bash
make migrate  # ensure head is current first
cd services/api && alembic revision --autogenerate -m "job requirements"
```

**Four known autogenerate defects in this repo — check each, every time:**

1. It emits `nightshift.db.types.UTCDateTime` with **no import**. Four migrations
   have hit this. Add `from nightshift.db.types import UTCDateTime` or replace
   with `sa.DateTime(timezone=True)`.
2. It emits **no `DROP TYPE`** on downgrade, leaving the two new enums behind.
   Add both to the downgrade, following `20260803_1800_application_tracking.py`.
3. It does not emit table constraints for a table it is only *altering* — not an
   issue here since `job_requirements` is created whole, but verify both
   `CheckConstraint`s made it in.
4. `op.add_column` does not create an enum type the way `create_table` does. Not
   an issue here for the same reason; noted so it is not rediscovered.

Then append the span trigger to `upgrade()`, modelled on
`nightshift_resume_span_must_quote_the_text`:

```python
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_requirement_span_must_quote_the_text()
        RETURNS trigger AS $$
        DECLARE
            source_text text;
        BEGIN
            SELECT description_text INTO source_text FROM jobs WHERE id = NEW.job_id;
            IF source_text IS NULL THEN
                RAISE EXCEPTION 'job % has no description text', NEW.job_id;
            END IF;
            IF NEW.char_end > length(source_text) THEN
                RAISE EXCEPTION
                    'span [%,%) runs past the % characters of job %',
                    NEW.char_start, NEW.char_end, length(source_text), NEW.job_id;
            END IF;
            IF substring(source_text FROM NEW.char_start + 1
                         FOR NEW.char_end - NEW.char_start) <> NEW.raw_text THEN
                RAISE EXCEPTION
                    'span [%,%) does not quote the job description',
                    NEW.char_start, NEW.char_end;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER job_requirements_span_must_quote "
        "BEFORE INSERT OR UPDATE ON job_requirements "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_requirement_span_must_quote_the_text()"
    )
```

and to `downgrade()`, before the table drop:

```python
    op.execute("DROP TRIGGER IF EXISTS job_requirements_span_must_quote ON job_requirements")
    op.execute("DROP FUNCTION IF EXISTS nightshift_requirement_span_must_quote_the_text()")
```

- [ ] **Step 6: Test the migration in both directions**

```bash
cd services/api && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
alembic check    # must report no drift
```

- [ ] **Step 7: Run the model tests**

```bash
cd services/api && .venv/bin/pytest tests/test_job_requirement_models.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Prove the trigger is load-bearing**

```sql
DROP TRIGGER job_requirements_span_must_quote ON job_requirements;
```

Re-run the file: `test_a_span_that_quotes_the_wrong_words_is_refused` and
`test_a_span_running_past_the_description_is_refused` must both go red. Restore
with `make reset-db`.

- [ ] **Step 9: Commit**

```bash
make check
git add services/api/nightshift/db/base.py services/api/nightshift/db/models.py \
        services/api/migrations/versions services/api/tests/test_job_requirement_models.py
git commit -m "feat(matching): add job_requirements, with a span it cannot lie about"
```

---

## Task 6: The requirement extractor

**Do not start until the answer key is committed.** `matching.md` §1.1.

**Files:**
- Create: `services/api/nightshift/domain/requirement_extraction.py`
- Create: `services/api/tests/test_requirement_extraction.py`

**Interfaces:**
- Consumes: `SkillVocabulary`, `SkillMatch`, `load_vocabulary` from
  `nightshift.domain.skill_vocabulary`. `SkillMatch` carries `canonical_name`,
  `char_start`, `char_end`.
- Produces (in `skill_vocabulary.py`): `SkillVocabulary.match_all(text) -> list[SkillMatch]`
  — see Step 0, which must be done first
- Produces: `EXTRACTOR_VERSION: str` — `"m3a.1"`
- Produces: `@dataclass(frozen=True) class RequirementProposal` with `kind: str`,
  `value: str`, `raw_text: str`, `char_start: int`, `char_end: int`,
  `necessity: str`, `has_equivalence: bool`
- Produces: `extract_requirements(text: str, *, vocabulary: SkillVocabulary | None = None) -> list[RequirementProposal]`
- Produces: `necessity_at(text: str, position: int) -> str`

- [ ] **Step 0: `SkillVocabulary.match` is wrong for a job posting. Add `match_all` first.**

**Read `services/api/nightshift/domain/skill_vocabulary.py:64` before writing
anything.** `match()` returns **one match per canonical name — the first
occurrence only**. Its docstring says why, and for a resume it is right: a person
listing Python four times has one Python skill.

**For a job posting it silently destroys the thing M3a is graded on.** A posting
whose "about us" blurb says *"we are a Python shop"* and whose requirements
section later says *"proficiency in Python"* yields exactly one match — the first
— so `necessity_at` reports `mentioned` and the required instance is gone. The
extractor would under-report required technologies on precisely the postings the
answer key measures, and the failure would surface in Task 7 as a mediocre recall
number that looks like a tuning problem rather than a lost occurrence.

Add a second method; do not change `match()`, which M2c depends on.

In `skill_vocabulary.py`:

```python
    def match_all(self, text: str) -> list[SkillMatch]:
        """Every non-overlapping vocabulary term, including repeats.

        The difference from :meth:`match` is deliberate and load-bearing. That
        one keeps the first occurrence per name, which is right for a resume:
        one person, one skill, one span to confirm. A job posting is the other
        case — the same technology under "about us" and again under "what
        you'll need" is two different claims, and which section it sits in is
        the whole question (`matching.md` §4.1). Collapsing them would answer
        that question with whichever came first.
        """
        claimed: list[tuple[int, int]] = []
        found: list[SkillMatch] = []
        for term in self._terms:
            for hit in term.pattern.finditer(text):
                start, end = hit.span()
                if any(
                    start < taken_end and taken_start < end
                    for taken_start, taken_end in claimed
                ):
                    continue
                claimed.append((start, end))
                found.append(
                    SkillMatch(
                        canonical_name=term.canonical_name,
                        char_start=start,
                        char_end=end,
                    )
                )
        return sorted(found, key=lambda m: (m.char_start, m.canonical_name))
```

Add to `services/api/tests/test_skill_vocabulary.py`:

```python
def test_match_all_keeps_every_occurrence_and_match_keeps_one() -> None:
    """The distinction the requirement extractor depends on."""
    vocab = load_vocabulary()
    text = "We are a Python shop. REQUIREMENTS Proficiency in Python."
    assert len(vocab.match(text)) == 1
    both = [m for m in vocab.match_all(text) if m.canonical_name == "Python"]
    assert len(both) == 2
    assert both[0].char_start < both[1].char_start


def test_match_all_still_refuses_overlapping_terms() -> None:
    """"Tailwind CSS" must not also yield a bare "CSS" inside it."""
    vocab = load_vocabulary()
    names = [m.canonical_name for m in vocab.match_all("We use Tailwind CSS here.")]
    assert names == ["Tailwind CSS"]


def test_every_match_all_span_quotes_the_text() -> None:
    vocab = load_vocabulary()
    text = "REQUIREMENTS Python, Kotlin, and Rust. NICE TO HAVES Python."
    for m in vocab.match_all(text):
        assert text[m.char_start : m.char_end].casefold() != ""
```

Run them, watch the first fail with `AttributeError: 'SkillVocabulary' object
has no attribute 'match_all'`, implement, watch them pass, and confirm M2c is
untouched:

```bash
cd services/api && .venv/bin/pytest tests/test_skill_vocabulary.py tests/test_resume_extraction.py -v
```

Commit this separately — it is a change to an M2c module and deserves its own
reviewable diff:

```bash
git add services/api/nightshift/domain/skill_vocabulary.py \
        services/api/tests/test_skill_vocabulary.py
git commit -m "feat(skills): add match_all, which keeps repeated occurrences"
```

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_requirement_extraction.py`:

```python
"""The extractor's rules, each with a fixture, per CLAUDE.md §7.

The single most important behaviour in this file is that a technology under a
"nice to have" heading comes out `preferred`. Everything else here is ordinary
parsing; that one is the difference between a product that reports real gaps and
one that reports nine false ones.
"""

from __future__ import annotations

from nightshift.domain.requirement_extraction import (
    EXTRACTOR_VERSION,
    extract_requirements,
    necessity_at,
)


def _values(proposals: list, kind: str, necessity: str | None = None) -> set[str]:
    return {
        p.value
        for p in proposals
        if p.kind == kind and (necessity is None or p.necessity == necessity)
    }


def test_a_required_technology_is_required() -> None:
    text = "WHAT YOU'LL NEED Proficiency in Kotlin for Android development."
    assert _values(extract_requirements(text), "technology", "required") == {"Kotlin"}


def test_a_nice_to_have_technology_is_preferred_not_required() -> None:
    """The Ramp internship case, and the reason `necessity` exists."""
    text = (
        "WHAT YOU'LL NEED Proficiency in Kotlin. "
        "NICE TO HAVES Experience with web apps (React, TypeScript). "
        "Experience with backend technologies (Python, Flask, SQL)."
    )
    proposals = extract_requirements(text)
    assert _values(proposals, "technology", "required") == {"Kotlin"}
    assert {"React", "TypeScript", "Python", "SQL"} <= _values(
        proposals, "technology", "preferred"
    )
    assert not _values(proposals, "technology", "required") & {"React", "Python"}


def test_a_bonus_points_heading_is_also_preferred() -> None:
    text = "REQUIREMENTS Python. Bonus Points: Experience with CUDA and PyTorch."
    proposals = extract_requirements(text)
    assert _values(proposals, "technology", "required") == {"Python"}
    assert "PyTorch" in _values(proposals, "technology", "preferred")


def test_a_technology_outside_any_heading_is_only_mentioned() -> None:
    """Prose about the stack is not a requirement."""
    text = "ABOUT US We are a Python shop and we love it here."
    assert _values(extract_requirements(text), "technology", "mentioned") == {"Python"}
    assert _values(extract_requirements(text), "technology", "required") == set()


def test_the_strongest_occurrence_of_a_technology_wins() -> None:
    """The case `SkillVocabulary.match` would have got wrong.

    "Python" appears twice: once in prose, once under a requirements heading.
    One posting asking for Python once is the truth, and the span shown must be
    the one that justifies calling it required.
    """
    text = "ABOUT US We are a Python shop. REQUIREMENTS Proficiency in Python."
    python = [
        p for p in extract_requirements(text)
        if p.kind == "technology" and p.value == "Python"
    ]
    assert len(python) == 1
    assert python[0].necessity == "required"
    assert python[0].char_start == text.rindex("Python")


def test_required_beats_preferred_for_the_same_technology() -> None:
    text = "REQUIREMENTS Python. NICE TO HAVES Python and React."
    python = [
        p for p in extract_requirements(text)
        if p.kind == "technology" and p.value == "Python"
    ]
    assert len(python) == 1
    assert python[0].necessity == "required"


def test_preferred_beats_mentioned_for_the_same_technology() -> None:
    text = "ABOUT US A React shop. NICE TO HAVES Experience with React."
    react = [
        p for p in extract_requirements(text)
        if p.kind == "technology" and p.value == "React"
    ]
    assert len(react) == 1
    assert react[0].necessity == "preferred"


def test_a_graduation_window_is_read_as_a_range() -> None:
    text = (
        "WHAT YOU'LL NEED Currently pursuing a B.S. in Computer Science, with an "
        "expected graduation date between 2026 - 2028"
    )
    assert _values(extract_requirements(text), "graduation_window") == {"2026-2028"}


def test_a_single_graduation_year_is_read_as_a_one_year_window() -> None:
    text = "REQUIREMENTS Graduating in 2027 with a degree in a technical field."
    assert _values(extract_requirements(text), "graduation_window") == {"2027-2027"}


def test_a_years_of_experience_requirement_is_read_as_an_integer() -> None:
    text = "REQUIREMENTS 3+ years of experience building backend services."
    assert _values(extract_requirements(text), "years_experience") == {"3"}


def test_a_doctorate_is_read_as_a_degree() -> None:
    text = "WHO YOU ARE You hold a PhD in Computer Science or a related field"
    assert _values(extract_requirements(text), "degree") == {"phd"}


def test_or_equivalent_experience_sets_the_equivalence_flag() -> None:
    """A13: this is not a hard blocker, and the flag is how M3b learns that."""
    text = (
        "WHO YOU ARE You hold a PhD in Computer Science, with deep expertise "
        "in generative modeling (or have equivalent experience)"
    )
    degrees = [p for p in extract_requirements(text) if p.kind == "degree"]
    assert len(degrees) == 1
    assert degrees[0].value == "phd"
    assert degrees[0].has_equivalence is True


def test_a_degree_with_no_equivalence_clause_does_not_claim_one() -> None:
    text = "WHO YOU ARE You hold a PhD in Computer Science."
    degrees = [p for p in extract_requirements(text) if p.kind == "degree"]
    assert degrees[0].has_equivalence is False


def test_current_enrollment_is_its_own_kind() -> None:
    text = "WHAT YOU'LL NEED Currently pursuing a B.S. or higher in Computer Science"
    assert extract_requirements(text) and _values(
        extract_requirements(text), "enrollment"
    ) == {"required"}


def test_every_proposal_quotes_the_characters_it_points_at() -> None:
    """The property the database trigger enforces, asserted before it gets there."""
    text = (
        "WHAT YOU'LL NEED Proficiency in Kotlin. 3+ years of experience. "
        "NICE TO HAVES React and Python."
    )
    proposals = extract_requirements(text)
    assert proposals
    for p in proposals:
        assert text[p.char_start : p.char_end] == p.raw_text, p


def test_nothing_is_proposed_for_prose_with_no_requirements() -> None:
    text = "We are a fast-paced team that values high agency and high urgency."
    assert extract_requirements(text) == []


def test_the_extractor_does_not_import_the_orm() -> None:
    """The same guard `resume_extraction` carries, for the same reason: this is
    the only path by which a parsing bug could reach a stored row."""
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parents[1]
        / "nightshift"
        / "domain"
        / "requirement_extraction.py"
    ).read_text()
    assert "from nightshift.db" not in source
    assert "import nightshift.db" not in source


def test_the_version_is_stamped() -> None:
    assert EXTRACTOR_VERSION == "m3a.1"


def test_necessity_at_reports_the_governing_heading() -> None:
    text = "REQUIREMENTS Kotlin. NICE TO HAVES React."
    assert necessity_at(text, text.index("Kotlin")) == "required"
    assert necessity_at(text, text.index("React")) == "preferred"
    assert necessity_at(text, 0) == "required"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/test_requirement_extraction.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the extractor**

`services/api/nightshift/domain/requirement_extraction.py`:

```python
"""Reading a job posting for what it can *prove* it asks for.

The mirror of `resume_extraction`, and the same trade: rules, deterministic, no
model, no key. Every proposal carries the character span it came from, so the
job page shows the sentence rather than asking anyone to trust a summary.

The single behaviour worth understanding before changing anything here is
`necessity_at`. A technology under "nice to have" is `preferred` and must never
become a gap — see `docs/architecture/matching.md` §3.2 for the posting that
motivated it.

Nothing here imports the ORM; `test_the_extractor_does_not_import_the_orm` is
what keeps that true.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nightshift.domain.skill_vocabulary import SkillVocabulary, load_vocabulary

#: Bumped whenever the rules change. Stored on every row this module produces.
EXTRACTOR_VERSION = "m3a.1"

RequirementKindName = Literal[
    "degree",
    "graduation_window",
    "years_experience",
    "technology",
    "authorization",
    "enrollment",
    "role_level",
]
NecessityName = Literal["required", "preferred", "mentioned"]


@dataclass(frozen=True)
class RequirementProposal:
    kind: RequirementKindName
    value: str
    raw_text: str
    char_start: int
    char_end: int
    necessity: NecessityName
    has_equivalence: bool = False


#: Headings that open a *required* block. Matched case-insensitively anywhere in
#: the text, because ATS descriptions are one long run of HTML with no reliable
#: line structure once the tags are stripped.
_REQUIRED_HEADINGS = (
    r"what you'?ll need",
    r"what you will need",
    r"minimum qualifications",
    r"basic qualifications",
    r"requirements",
    r"who you are",
    r"qualifications",
    r"you have",
)

#: Headings that open a *preferred* block. Checked first where both could match,
#: since "preferred qualifications" contains "qualifications".
_PREFERRED_HEADINGS = (
    r"preferred qualifications",
    r"nice to haves?",
    r"bonus points",
    r"it'?s a plus",
    r"pluses",
    r"we'?d love to see",
    r"desirable",
)

_EQUIVALENCE = re.compile(r"\bor\s+(?:have\s+)?equivalent\b", re.I)

_DEGREE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("phd", r"\b(ph\.?\s?d\.?|doctorate|doctoral degree)\b"),
    ("masters", r"\b(master'?s(?:\s+degree)?|m\.?s\.?c?\.?|m\.eng\.?)\b"),
    ("bachelors", r"\b(bachelor'?s(?:\s+degree)?|b\.?s\.?c?\.?|b\.?a\.?|b\.eng\.?)\b"),
)


def _heading_spans(text: str) -> list[tuple[int, NecessityName]]:
    """Every heading occurrence with the necessity it opens, in document order."""
    found: list[tuple[int, NecessityName]] = []
    for pattern in _PREFERRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            found.append((m.start(), "preferred"))
    for pattern in _REQUIRED_HEADINGS:
        for m in re.finditer(pattern, text, re.I):
            found.append((m.start(), "required"))
    # A preferred heading wins at the same offset: "preferred qualifications"
    # and "qualifications" both match there, and the longer one is the truth.
    best: dict[int, NecessityName] = {}
    for offset, necessity in found:
        if necessity == "preferred" or offset not in best:
            best[offset] = necessity
    return sorted(best.items())


def necessity_at(text: str, position: int) -> NecessityName:
    """Which heading governs `position`.

    Text before any heading is `mentioned` — an "about us" paragraph naming a
    stack is not an ask. The one exception is a posting with no headings at all,
    where everything is `mentioned` rather than promoted by guesswork.
    """
    governing: NecessityName = "mentioned"
    for offset, necessity in _heading_spans(text):
        if offset <= position:
            governing = necessity
        else:
            break
    return governing


def _sentence_around(text: str, position: int) -> str:
    start = max(text.rfind(".", 0, position), text.rfind(";", 0, position)) + 1
    end = text.find(".", position)
    return text[start : end if end != -1 else len(text)]


#: Strongest first. A technology named in prose and again under a requirements
#: heading is one ask, and the heading is what the posting means by it.
_NECESSITY_RANK: dict[NecessityName, int] = {
    "required": 3,
    "preferred": 2,
    "mentioned": 1,
}


def _technologies(
    text: str, vocabulary: SkillVocabulary
) -> list[RequirementProposal]:
    """One proposal per technology, carrying its strongest occurrence.

    Uses ``match_all`` rather than ``match``: the latter keeps only the first
    occurrence per name, which for a posting means an "about us" mention can
    hide the requirement further down. See `skill_vocabulary.match_all`.
    """
    best: dict[str, RequirementProposal] = {}
    for match in vocabulary.match_all(text):
        necessity = necessity_at(text, match.char_start)
        candidate = RequirementProposal(
            kind="technology",
            value=match.canonical_name,
            raw_text=text[match.char_start : match.char_end],
            char_start=match.char_start,
            char_end=match.char_end,
            necessity=necessity,
        )
        incumbent = best.get(match.canonical_name)
        if incumbent is None or (
            _NECESSITY_RANK[necessity] > _NECESSITY_RANK[incumbent.necessity]
        ):
            best[match.canonical_name] = candidate
    return list(best.values())


def _degrees(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    claimed: list[range] = []
    for value, pattern in _DEGREE_PATTERNS:  # phd first, so it wins the sentence
        for m in re.finditer(pattern, text, re.I):
            if any(m.start() in r for r in claimed):
                continue
            claimed.append(range(m.start(), m.end()))
            out.append(
                RequirementProposal(
                    kind="degree",
                    value=value,
                    raw_text=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    necessity=necessity_at(text, m.start()),
                    has_equivalence=bool(
                        _EQUIVALENCE.search(_sentence_around(text, m.start()))
                    ),
                )
            )
    return out


def _graduation_windows(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    ranged = re.compile(r"\b(20\d{2})\s*(?:-|–|to|and)\s*(20\d{2})\b")
    for m in ranged.finditer(text):
        if not re.search(r"graduat", text[max(0, m.start() - 90) : m.start()], re.I):
            continue
        out.append(
            RequirementProposal(
                kind="graduation_window",
                value=f"{m.group(1)}-{m.group(2)}",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    claimed = [range(p.char_start, p.char_end) for p in out]
    for m in re.finditer(r"\b(20\d{2})\b", text):
        if any(m.start() in r for r in claimed):
            continue
        if not re.search(r"graduat", text[max(0, m.start() - 90) : m.start()], re.I):
            continue
        out.append(
            RequirementProposal(
                kind="graduation_window",
                value=f"{m.group(1)}-{m.group(1)}",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def _years_of_experience(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in re.finditer(r"\b(\d{1,2})\s*\+?\s*years?\b", text, re.I):
        window = text[m.end() : m.end() + 40].lower()
        if "experience" not in window:
            continue
        out.append(
            RequirementProposal(
                kind="years_experience",
                value=m.group(1),
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def _enrollment(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in re.finditer(r"\bcurrently (?:pursuing|enrolled|studying)\b", text, re.I):
        out.append(
            RequirementProposal(
                kind="enrollment",
                value="required",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def _authorization(text: str) -> list[RequirementProposal]:
    out: list[RequirementProposal] = []
    for m in re.finditer(
        r"\b(?:will not|unable to|do not|cannot)\s+sponsor\w*\b", text, re.I
    ):
        out.append(
            RequirementProposal(
                kind="authorization",
                value="no_sponsorship",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    for m in re.finditer(r"\b(?:we|will)\s+(?:do\s+)?sponsor\w*\b", text, re.I):
        out.append(
            RequirementProposal(
                kind="authorization",
                value="sponsorship_offered",
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                necessity=necessity_at(text, m.start()),
            )
        )
    return out


def extract_requirements(
    text: str, *, vocabulary: SkillVocabulary | None = None
) -> list[RequirementProposal]:
    """Every requirement the rules can point at, in document order.

    Recall is traded for precision, as in `resume_extraction`: a requirement
    described in words the vocabulary does not carry yields nothing, and that
    gap is measured in `test_requirement_extraction_against_the_answer_key.py`
    rather than assumed away.
    """
    if not text:
        return []
    vocab = vocabulary if vocabulary is not None else load_vocabulary()
    proposals = [
        *_technologies(text, vocab),
        *_degrees(text),
        *_graduation_windows(text),
        *_years_of_experience(text),
        *_enrollment(text),
        *_authorization(text),
    ]
    return sorted(proposals, key=lambda p: (p.char_start, p.kind, p.value))
```

- [ ] **Step 4: Run the tests**

```bash
cd services/api && .venv/bin/pytest tests/test_requirement_extraction.py -v
```

Expected: 19 passed. Where a test fails, fix the rule — **not the test** — unless
the test asserts something the posting does not actually say, in which case fix
the test and record why in the commit body.

- [ ] **Step 5: Mutation-check the strongest-occurrence rule**

Change `_NECESSITY_RANK` so `mentioned` outranks `required`. Run the file.
`test_the_strongest_occurrence_of_a_technology_wins`,
`test_required_beats_preferred_for_the_same_technology` and
`test_preferred_beats_mentioned_for_the_same_technology` must all go red. Revert.

- [ ] **Step 6: Mutation-check the necessity rule**

Make `necessity_at` return `"required"` unconditionally. Run the file.
`test_a_nice_to_have_technology_is_preferred_not_required`,
`test_a_bonus_points_heading_is_also_preferred` and
`test_a_technology_outside_any_heading_is_only_mentioned` must all go red. If any
of them passes, that test cannot fail and is worth more attention than the rule.
Revert.

- [ ] **Step 7: Commit**

```bash
make check
git add services/api/nightshift/domain/requirement_extraction.py \
        services/api/tests/test_requirement_extraction.py
git commit -m "feat(matching): extract what a posting requires, with its span"
```

---

## Task 7: Grade the extractor against the answer key

The task this whole milestone is arranged around.

**Files:**
- Create: `services/api/tests/test_requirement_extraction_against_the_answer_key.py`
- Create: `services/api/nightshift/domain/extraction_metrics.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Score` with `precision: float`,
  `recall: float`, `true_positives: int`, `false_positives: int`,
  `false_negatives: int`
- Produces: `score_sets(predicted: set[str], expected: set[str]) -> Score`

- [ ] **Step 1: Write the metric and its test**

`services/api/nightshift/domain/extraction_metrics.py`:

```python
"""Precision and recall, defined once so two graders cannot disagree.

Reported separately and never averaged into one number: an extractor that
proposes nothing has perfect precision, and one that proposes everything has
perfect recall. A single figure hides both failures.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        """Of what was proposed, how much was right. 1.0 when nothing was."""
        proposed = self.true_positives + self.false_positives
        return 1.0 if proposed == 0 else self.true_positives / proposed

    @property
    def recall(self) -> float:
        """Of what was there, how much was found. 1.0 when there was nothing."""
        present = self.true_positives + self.false_negatives
        return 1.0 if present == 0 else self.true_positives / present


def score_sets(predicted: set[str], expected: set[str]) -> Score:
    lowered_pred = {p.casefold() for p in predicted}
    lowered_exp = {e.casefold() for e in expected}
    return Score(
        true_positives=len(lowered_pred & lowered_exp),
        false_positives=len(lowered_pred - lowered_exp),
        false_negatives=len(lowered_exp - lowered_pred),
    )
```

Add to `services/api/tests/test_extraction_metrics.py`:

```python
from nightshift.domain.extraction_metrics import score_sets


def test_a_perfect_match_scores_one_on_both() -> None:
    s = score_sets({"Kotlin"}, {"Kotlin"})
    assert (s.precision, s.recall) == (1.0, 1.0)


def test_proposing_nothing_has_perfect_precision_and_no_recall() -> None:
    """The reason the two are never averaged."""
    s = score_sets(set(), {"Kotlin", "Python"})
    assert s.precision == 1.0
    assert s.recall == 0.0


def test_proposing_everything_has_perfect_recall_and_poor_precision() -> None:
    s = score_sets({"Kotlin", "Python", "Rust"}, {"Kotlin"})
    assert s.recall == 1.0
    assert s.precision == pytest.approx(1 / 3)


def test_matching_is_case_insensitive() -> None:
    assert score_sets({"kotlin"}, {"Kotlin"}).precision == 1.0
```

- [ ] **Step 2: Write the grader**

`services/api/tests/test_requirement_extraction_against_the_answer_key.py`:

```python
"""The extractor, graded against sixty postings a human labeled by hand.

`docs/architecture/matching.md` §1.1: the answer key was committed before these
rules were written, so this measures the rules rather than the choice of
examples.

The floors below are **measured, not chosen**. Run the reporting test, read the
numbers, set each floor just under what the extractor actually achieves, and
raise them as it improves. A floor picked before measuring is either
unreachable or vacuous, and there is no way to tell which from the outside.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.domain.eligibility_labels import load_answer_key
from nightshift.domain.extraction_metrics import Score, score_sets
from nightshift.domain.requirement_extraction import extract_requirements
from nightshift.domain.skill_vocabulary import load_vocabulary

CORPUS = Path(__file__).resolve().parent / "fixtures" / "eligibility"

#: Measured on the committed corpus at m3a.1. Update alongside a rule change,
#: and never downward without a sentence in the commit saying what regressed.
REQUIRED_TECH_PRECISION_FLOOR = 0.0   # set from Step 3's output
REQUIRED_TECH_RECALL_FLOOR = 0.0      # set from Step 3's output
NECESSITY_ACCURACY_FLOOR = 0.0        # set from Step 3's output


def _description(job: dict[str, Any]) -> str:
    import html
    import re

    raw = (
        job.get("content")
        or job.get("descriptionPlain")
        or job.get("descriptionHtml")
        or job.get("description")
        or ""
    )
    text = html.unescape(html.unescape(str(raw)))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _corpus_postings() -> dict[str, dict[str, str]]:
    """board -> posting id -> description text."""
    out: dict[str, dict[str, str]] = {}
    for path in sorted(CORPUS.glob("*.json")):
        if path.name.endswith(".meta.json") or path.name == "labels.yaml":
            continue
        body = json.loads(path.read_text())
        jobs = body["jobs"] if isinstance(body, dict) else body
        out[path.stem] = {str(j.get("id")): _description(j) for j in jobs}
    return out


@pytest.fixture(scope="module")
def graded() -> dict[str, Any]:
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()

    tech_tp = tech_fp = tech_fn = 0
    necessity_right = necessity_total = 0
    misses: list[str] = []

    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings.get(board, {}).get(posting_id)
            assert text is not None, f"{board}/{posting_id} labeled but not in corpus"
            proposals = extract_requirements(text, vocabulary=vocab)

            predicted_required = {
                p.value for p in proposals
                if p.kind == "technology" and p.necessity == "required"
            }
            s = score_sets(predicted_required, set(label.required_tech))
            tech_tp += s.true_positives
            tech_fp += s.false_positives
            tech_fn += s.false_negatives
            if s.false_negatives:
                misses.append(
                    f"{board}/{posting_id}: missed "
                    f"{sorted(set(label.required_tech) - predicted_required)}"
                )

            # Necessity accuracy: of the technologies the human placed in
            # either list, how many did the extractor put in the right one.
            for tech in label.required_tech:
                necessity_total += 1
                necessity_right += int(
                    tech.casefold() in {t.casefold() for t in predicted_required}
                )
            predicted_preferred = {
                p.value.casefold() for p in proposals
                if p.kind == "technology" and p.necessity == "preferred"
            }
            for tech in label.mentioned_not_required:
                necessity_total += 1
                necessity_right += int(
                    tech.casefold() not in {t.casefold() for t in predicted_required}
                )

    return {
        "tech": Score(tech_tp, tech_fp, tech_fn),
        "necessity_accuracy": (
            1.0 if necessity_total == 0 else necessity_right / necessity_total
        ),
        "necessity_total": necessity_total,
        "misses": misses,
    }


def test_report_the_numbers(graded: dict[str, Any], capsys: Any) -> None:
    """Always passes. Prints what the extractor actually does, so the floors
    below are set from measurement rather than from hope.

    Run with `-s` to read it.
    """
    tech: Score = graded["tech"]
    with capsys.disabled():
        print(
            f"\n  required technology  precision {tech.precision:.3f}"
            f"  recall {tech.recall:.3f}"
            f"  (tp {tech.true_positives} fp {tech.false_positives} "
            f"fn {tech.false_negatives})"
        )
        print(
            f"  necessity accuracy   {graded['necessity_accuracy']:.3f}"
            f"  over {graded['necessity_total']} labeled technologies"
        )
        for miss in graded["misses"][:15]:
            print(f"    {miss}")


def test_required_technology_precision_holds(graded: dict[str, Any]) -> None:
    """Precision matters more than recall here: a technology wrongly called
    required becomes a false gap in the explanation, which is a visible lie."""
    assert graded["tech"].precision >= REQUIRED_TECH_PRECISION_FLOOR


def test_required_technology_recall_holds(graded: dict[str, Any]) -> None:
    assert graded["tech"].recall >= REQUIRED_TECH_RECALL_FLOOR


def test_necessity_accuracy_holds(graded: dict[str, Any]) -> None:
    assert graded["necessity_accuracy"] >= NECESSITY_ACCURACY_FLOOR


def test_no_nice_to_have_is_ever_reported_as_required(
    graded: dict[str, Any],
) -> None:
    """The one assertion with no floor, because the honest floor is zero.

    A technology the human put under "nice to have" appearing as `required` is
    the failure that produces nine false gaps against a qualified candidate.
    """
    key = load_answer_key()
    postings = _corpus_postings()
    vocab = load_vocabulary()
    violations: list[str] = []
    for board, labels in key.boards.items():
        for posting_id, label in labels.items():
            text = postings[board][posting_id]
            required = {
                p.value.casefold()
                for p in extract_requirements(text, vocabulary=vocab)
                if p.kind == "technology" and p.necessity == "required"
            }
            for tech in label.mentioned_not_required:
                if tech.casefold() in required:
                    violations.append(f"{board}/{posting_id}: {tech}")
    assert violations == [], violations
```

- [ ] **Step 3: Measure, then set the floors**

```bash
cd services/api && .venv/bin/pytest tests/test_requirement_extraction_against_the_answer_key.py::test_report_the_numbers -s
```

Read the three figures. Set each floor in the module constants to just below the
measured value — two decimal places, rounded down. **Record the measured numbers
in the commit body**, so a future reader can see whether a floor was ever
lowered.

If `test_no_nice_to_have_is_ever_reported_as_required` reports violations, that
is a rule defect and not a floor to lower. Fix `necessity_at` or the heading
lists in Task 6, and re-measure.

- [ ] **Step 4: Run the whole file**

```bash
cd services/api && .venv/bin/pytest tests/test_requirement_extraction_against_the_answer_key.py tests/test_extraction_metrics.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
make check
git add services/api/nightshift/domain/extraction_metrics.py \
        services/api/tests/test_extraction_metrics.py \
        services/api/tests/test_requirement_extraction_against_the_answer_key.py
git commit -m "test(matching): grade requirement extraction against the answer key"
```

---

## Task 8: Extract during ingestion, and backfill

**Files:**
- Modify: `services/api/nightshift/domain/ingestion.py`
- Create: `services/api/tests/test_requirement_ingestion.py`

**Interfaces:**
- Produces: `async def sync_requirements(session: AsyncSession, job: Job) -> int`
  — replaces a job's requirements from its current `description_text`, returns
  the row count. Idempotent.

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_requirement_ingestion.py`:

```python
"""Requirements follow the description, and re-ingestion does not multiply them."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.models import JobRequirement
from nightshift.domain.ingestion import sync_requirements

pytestmark = pytest.mark.asyncio

_TEXT = "WHAT YOU'LL NEED Proficiency in Kotlin. NICE TO HAVES React."


async def _count(session: AsyncSession, job_id: object) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(JobRequirement)
                .where(JobRequirement.job_id == job_id)
            )
        ).scalar_one()
    )


async def test_syncing_twice_produces_the_same_rows(db_session: AsyncSession) -> None:
    """M1's idempotency criterion, applied to a new table."""
    from tests.test_models_canonical_spine import make_job

    job = await make_job(db_session, description_text=_TEXT)
    first = await sync_requirements(db_session, job)
    await db_session.flush()
    second = await sync_requirements(db_session, job)
    await db_session.flush()
    assert first == second
    assert await _count(db_session, job.id) == first


async def test_changing_the_description_replaces_the_requirements(
    db_session: AsyncSession,
) -> None:
    """Stale spans point at characters that have moved. They must not survive."""
    from tests.test_models_canonical_spine import make_job

    job = await make_job(db_session, description_text=_TEXT)
    await sync_requirements(db_session, job)
    await db_session.flush()

    job.description_text = "REQUIREMENTS Proficiency in Python."
    await sync_requirements(db_session, job)
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(JobRequirement).where(JobRequirement.job_id == job.id)
        )
    ).scalars().all()
    assert {r.value for r in rows if r.kind == "technology"} == {"Python"}
    for row in rows:
        assert job.description_text[row.char_start : row.char_end] == row.raw_text


async def test_a_job_with_no_description_gets_no_requirements(
    db_session: AsyncSession,
) -> None:
    """Not an error, and not a zero-requirement claim either — just no rows."""
    from tests.test_models_canonical_spine import make_job

    job = await make_job(db_session, description_text=None)
    assert await sync_requirements(db_session, job) == 0
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/test_requirement_ingestion.py -v
```

Expected: FAIL — `ImportError: cannot import name 'sync_requirements'`.

- [ ] **Step 3: Implement**

In `services/api/nightshift/domain/ingestion.py`:

```python
async def sync_requirements(session: AsyncSession, job: Job) -> int:
    """Replace a job's requirements from its current description text.

    Delete-then-insert rather than a diff, deliberately. Spans are offsets into
    `description_text`; when that text changes, every surviving row points at
    characters that have moved, and the trigger would reject some while letting
    others through with a plausible-looking wrong quote. Replacing wholesale is
    the only version with no half-state.
    """
    await session.execute(
        delete(JobRequirement).where(JobRequirement.job_id == job.id)
    )
    text = job.description_text
    if not text:
        return 0
    proposals = extract_requirements(text)
    for proposal in proposals:
        session.add(
            JobRequirement(
                job_id=job.id,
                kind=RequirementKind(proposal.kind),
                value=proposal.value,
                raw_text=proposal.raw_text,
                char_start=proposal.char_start,
                char_end=proposal.char_end,
                necessity=RequirementNecessity(proposal.necessity),
                has_equivalence=proposal.has_equivalence,
                extractor_version=EXTRACTOR_VERSION,
            )
        )
    return len(proposals)
```

Call it where a canonical job's description is written — find the function that
sets `description_text` during merge and call `sync_requirements` after it, in
the same transaction. Add `delete` to the SQLAlchemy imports.

- [ ] **Step 4: Run the tests**

```bash
cd services/api && .venv/bin/pytest tests/test_requirement_ingestion.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Backfill the seeded corpus and confirm end to end**

```bash
make reset-db
python - <<'PY'
import asyncio
from sqlalchemy import select, func
from nightshift.db.session import session_scope
from nightshift.db.models import Job, JobRequirement
from nightshift.domain.ingestion import sync_requirements

async def main() -> None:
    async with session_scope() as s:
        jobs = (await s.execute(select(Job))).scalars().all()
        total = 0
        for job in jobs:
            total += await sync_requirements(s, job)
        await s.commit()
        rows = (await s.execute(select(func.count()).select_from(JobRequirement))).scalar_one()
        print(f"{len(jobs)} jobs -> {total} proposals, {rows} rows stored")

asyncio.run(main())
PY
```

The two counts must agree. If `rows` is lower, the trigger rejected something and
the exception was swallowed somewhere — find it before continuing.

- [ ] **Step 6: Commit**

```bash
make check
git add services/api/nightshift/domain/ingestion.py \
        services/api/tests/test_requirement_ingestion.py
git commit -m "feat(ingestion): extract requirements when a description lands"
```

---

## Task 9: Serve requirements on job detail

**Files:**
- Modify: `services/api/nightshift/api/schemas.py`
- Modify: `services/api/nightshift/api/routes/jobs.py`
- Create: `services/api/tests/test_job_requirement_routes.py`

**Interfaces:**
- Produces: `class JobRequirementOut(BaseModel)` — `kind: RequirementKind`,
  `value: str`, `raw_text: str`, `char_start: int`, `char_end: int`,
  `necessity: RequirementNecessity`, `has_equivalence: bool`
- Produces: `JobDetailOut.requirements: list[JobRequirementOut]`
- Produces: `JobDetailOut.requirements_extractor_version: str | None`

- [ ] **Step 1: Write the failing test**

`services/api/tests/test_job_requirement_routes.py`:

```python
"""The route, and the property the page depends on.

Each file under tests/ defines its own `client` fixture rather than sharing one:
the override covers `current_user_id` as well as the session, so the suite does
not depend on `make seed` having run. Copy the pattern from
`tests/test_queue_routes.py` rather than importing it.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_job_detail_returns_requirements_grouped_by_necessity(
    client, seeded_job_with_requirements
) -> None:
    response = await client.get(f"/jobs/{seeded_job_with_requirements.id}")
    assert response.status_code == 200
    body = response.json()
    necessities = {r["necessity"] for r in body["requirements"]}
    assert "required" in necessities


async def test_every_returned_span_quotes_the_returned_description(
    client, seeded_job_with_requirements
) -> None:
    """Re-asserted at the API boundary, not only in the database.

    The trigger guarantees the row is honest about the text in `jobs`. This
    guarantees the *response* is internally consistent, which is what the
    browser highlights against — a one-character shift in serialisation turns
    this red and nothing else would.
    """
    body = (await client.get(f"/jobs/{seeded_job_with_requirements.id}")).json()
    text = body["description_text"]
    assert body["requirements"]
    for requirement in body["requirements"]:
        start, end = requirement["char_start"], requirement["char_end"]
        assert text[start:end] == requirement["raw_text"], requirement


async def test_a_job_with_no_description_returns_an_empty_list_not_null(
    client, seeded_job_without_description
) -> None:
    body = (await client.get(f"/jobs/{seeded_job_without_description.id}")).json()
    assert body["requirements"] == []
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/test_job_requirement_routes.py -v
```

Expected: FAIL — `KeyError: 'requirements'`.

- [ ] **Step 3: Implement**

In `schemas.py`, beside `JobDetailOut`:

```python
class JobRequirementOut(BaseModel):
    """One thing a posting asks for, and the characters where it says so.

    `raw_text` plus the offsets are what the page highlights. Serialising the
    offsets without the text — or the text without the offsets — would let the
    two drift, and the highlight would quietly point somewhere else.
    """

    kind: RequirementKind
    value: str
    raw_text: str
    char_start: int
    char_end: int
    necessity: RequirementNecessity
    has_equivalence: bool
```

and on `JobDetailOut`:

```python
    requirements: list[JobRequirementOut] = Field(default_factory=list)
    #: Which rules produced them. Null when nothing has been extracted, which
    #: the page states rather than rendering an empty requirements section —
    #: "this posting asks for nothing" and "we have not read it" differ.
    requirements_extractor_version: str | None = None
```

In `routes/jobs.py`, eager-load the relationship on the detail query
(`selectinload(Job.requirements)`) and map the rows into the schema, ordered by
`char_start`.

- [ ] **Step 4: Run the tests**

```bash
cd services/api && .venv/bin/pytest tests/test_job_requirement_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
make check
git add services/api/nightshift/api services/api/tests/test_job_requirement_routes.py
git commit -m "feat(api): return what a posting requires, with its spans"
```

---

## Task 10: The job page shows what a posting requires

**Files:**
- Modify: `apps/web/src/lib/schemas.ts`
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/components/JobRequirements.tsx`
- Create: `apps/web/src/components/JobRequirements.test.tsx`
- Modify: the job detail page under `apps/web/src/app/`
- Modify: `services/api/tests/test_enum_parity.py`

**Interfaces:**
- Produces: `requirementKindSchema`, `requirementNecessitySchema`,
  `jobRequirementSchema` in `schemas.ts`
- Produces: `<JobRequirements requirements={...} descriptionText={...} extractorVersion={...} />`

- [ ] **Step 1: Add both enums to the parity guard first**

In `services/api/tests/test_enum_parity.py`, add `RequirementKind` and
`RequirementNecessity` to the mapping it walks. Run it:

```bash
cd services/api && .venv/bin/pytest tests/test_enum_parity.py -v
```

Expected: FAIL — the TypeScript side does not have them yet. This is the only
test in the repo that reads both languages, and two of the last four milestones
found a hand-transcribed defect here. Adding it before the TypeScript is what
makes it do its job.

- [ ] **Step 2: Write the Zod schemas**

In `apps/web/src/lib/schemas.ts`:

```ts
export const requirementKindSchema = z.enum([
  'degree',
  'graduation_window',
  'years_experience',
  'technology',
  'authorization',
  'enrollment',
  'role_level',
]);

export const requirementNecessitySchema = z.enum([
  'required',
  'preferred',
  'mentioned',
]);

export const jobRequirementSchema = z.object({
  kind: requirementKindSchema,
  value: z.string(),
  raw_text: z.string(),
  char_start: z.number().int().nonnegative(),
  char_end: z.number().int().nonnegative(),
  necessity: requirementNecessitySchema,
  has_equivalence: z.boolean(),
});

export type JobRequirement = z.infer<typeof jobRequirementSchema>;
```

Extend the job detail schema with `requirements` and
`requirements_extractor_version`.

- [ ] **Step 3: Run the parity guard again**

```bash
cd services/api && .venv/bin/pytest tests/test_enum_parity.py -v
```

Expected: pass. **If it fails, the transcription is wrong** — read the Python
enum values by printing them rather than by eye. That is exactly how M2c's
defect was found.

- [ ] **Step 4: Write the component test**

`apps/web/src/components/JobRequirements.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { JobRequirements } from './JobRequirements';
import { jobRequirementSchema } from '../lib/schemas';

const DESCRIPTION = "WHAT YOU'LL NEED Proficiency in Kotlin. NICE TO HAVES React.";

// Parsed through the real schema, because M2c shipped a component test fed
// data the API cannot produce — the exact row its schema exists to refuse.
const required = jobRequirementSchema.parse({
  kind: 'technology',
  value: 'Kotlin',
  raw_text: 'Kotlin',
  char_start: DESCRIPTION.indexOf('Kotlin'),
  char_end: DESCRIPTION.indexOf('Kotlin') + 'Kotlin'.length,
  necessity: 'required',
  has_equivalence: false,
});

const preferred = jobRequirementSchema.parse({
  kind: 'technology',
  value: 'React',
  raw_text: 'React',
  char_start: DESCRIPTION.indexOf('React'),
  char_end: DESCRIPTION.indexOf('React') + 'React'.length,
  necessity: 'preferred',
  has_equivalence: false,
});

describe('JobRequirements', () => {
  it('separates what is required from what is merely preferred', () => {
    render(
      <JobRequirements
        requirements={[required, preferred]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    const requiredSection = screen.getByRole('region', { name: /required/i });
    expect(requiredSection).toHaveTextContent('Kotlin');
    expect(requiredSection).not.toHaveTextContent('React');
  });

  it('quotes the sentence each requirement came from', () => {
    render(
      <JobRequirements
        requirements={[required]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    expect(screen.getByText(/Proficiency in Kotlin/)).toBeInTheDocument();
  });

  it('says nothing has been read rather than showing an empty list', () => {
    render(
      <JobRequirements
        requirements={[]}
        descriptionText={DESCRIPTION}
        extractorVersion={null}
      />,
    );
    expect(screen.getByText(/not been read/i)).toBeInTheDocument();
  });

  it('distinguishes an empty result from an unread posting', () => {
    render(
      <JobRequirements
        requirements={[]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    expect(screen.getByText(/no requirements this system could read/i)).toBeInTheDocument();
  });

  it('marks a degree carrying an equivalence clause', () => {
    const phd = jobRequirementSchema.parse({
      kind: 'degree',
      value: 'phd',
      raw_text: 'PhD',
      char_start: 0,
      char_end: 3,
      necessity: 'required',
      has_equivalence: true,
    });
    render(
      <JobRequirements
        requirements={[phd]}
        descriptionText="PhD in Computer Science or equivalent experience"
        extractorVersion="m3a.1"
      />,
    );
    expect(screen.getByText(/or equivalent/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run it and watch it fail**

```bash
make test-web
```

Expected: FAIL — component does not exist.

- [ ] **Step 6: Write the component**

`apps/web/src/components/JobRequirements.tsx`. Requirements:

- Three groups, in order: **Required**, **Preferred**, **Mentioned**. Each is a
  `<section>` with an accessible name, so the test's `getByRole('region')` works.
- Under each requirement, the sentence it came from, sliced out of
  `descriptionText` around the span — never re-derived, never summarised.
- A requirement with `has_equivalence` carries a visible "or equivalent" marker.
- `extractorVersion === null` renders "this posting has not been read yet".
  A non-null version with no rows renders "no requirements this system could
  read". **These are different statements and the component must not merge
  them** — the first is our gap, the second is a fact about the posting.
- `paper*` tokens for text, `ink*` for surfaces, per CLAUDE.md §7. Add a
  contrast assertion to `colour-contrast.test.ts` for any new token.

- [ ] **Step 7: Run the tests**

```bash
make test-web
```

Expected: 5 new tests passing.

- [ ] **Step 8: Render it on the job page**

Add `<JobRequirements />` to the job detail page, below the description. Remove
"requirement extraction" from that page's deferred-field list if it appears
there — M2c's and M2d's reviews both found a "not built yet" list that had gone
stale in the one direction nobody checks.

```bash
grep -rn "requirement" apps/web/src/app --include=*.tsx
```

- [ ] **Step 9: Commit**

```bash
make check
git add apps/web/src services/api/tests/test_enum_parity.py
git commit -m "feat(web): show what a posting requires, quoting its own words"
```

---

## Task 11: The fifth coverage blind spot

**Files:**
- Modify: `services/api/nightshift/discovery/coverage.py`
- Modify: `services/api/tests/discovery/` — the coverage test file

- [ ] **Step 1: Write the failing test**

Add to the existing coverage test file:

```python
def test_the_blind_spots_name_employers_with_their_own_careers_system() -> None:
    """Measured 2026-08-04: `meta`, `facebook`, `metaplatforms` and `apple`
    return 404 on all three ATS endpoints — twelve of twelve.

    The four original blind spots do not cover this. `workday_icims_taleo` is
    about a different set of systems, and `no_public_board` is about hiring that
    was never published. Meta has a very public job board; it is simply not on
    an ATS this system reads. A reader of that page would reasonably conclude
    big tech is covered, and it is not.
    """
    summary = _summary_for_test()
    spot = next(s for s in summary.blind_spots if s.id == "own_careers_system")
    text = spot.explanation.lower()
    for employer in ("meta", "apple", "google", "amazon"):
        assert employer in text
    # The two situations are different disclosures and must not be merged.
    assert "robots.txt" in text
    assert "not built" in text or "unbuilt" in text
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/api && .venv/bin/pytest tests/discovery -v -k careers_system
```

Expected: FAIL — `StopIteration`.

- [ ] **Step 3: Add the blind spot**

In `STRUCTURAL_BLIND_SPOTS` in `coverage.py`:

```python
    BlindSpot(
        id="own_careers_system",
        title="Employers running their own careers system",
        explanation=(
            "Meta, Apple, Google, Amazon, Microsoft and Bloomberg do not use "
            "Greenhouse, Lever or Ashby. Each runs a bespoke careers site with "
            "no public API, so every opening at them is invisible here. "
            "Measured 2026-08-04: `meta`, `facebook`, `metaplatforms` and "
            "`apple` return 404 across all three provider endpoints, twelve of "
            "twelve. This is not the Workday gap above — those are three "
            "shared enterprise systems an adapter could read; these are "
            "one-off sites. Two different situations sit inside this row and "
            "they are different disclosures. Meta's robots.txt prohibits "
            "automated collection without written permission and Google's "
            "disallows its job results by name, so both are refused sources "
            "under the first-party-only rule and no future milestone changes "
            "that. Amazon's robots.txt disallows only /internal and "
            "jobs.apple.com serves none at all; neither refuses, and neither "
            "is built. Whether to read the second group is a decision for a "
            "later ADR, answered per employer rather than per category, and "
            "robots.txt is not the terms of service — those need reading "
            "separately."
        ),
    ),
```

- [ ] **Step 4: Run the tests**

```bash
cd services/api && .venv/bin/pytest tests/discovery -v
```

Expected: pass, including the existing count assertions — **update any test
asserting exactly four structural blind spots.**

- [ ] **Step 5: Look at the page**

```bash
make up && make migrate && make seed && make dev
```

Open `/analyze/coverage`. The new row must read as an honest disclosure rather
than an apology.

- [ ] **Step 6: Commit**

```bash
make check
git add services/api/nightshift/discovery/coverage.py services/api/tests/discovery
git commit -m "feat(coverage): name the employers who run their own careers system"
```

---

## Task 12: The browser walk, `make acceptance`, ADR, review, PROGRESS

**Files:**
- Create: `apps/web/e2e-seeded/requirements.spec.ts`
- Modify: `scripts/verify.py`
- Create: `docs/adr/0015-requirements-are-extracted-with-spans.md`
- Create: `docs/reviews/milestone-3a-review.md`
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: Write the browser test**

`apps/web/e2e-seeded/requirements.spec.ts`. It must:

- Open a seeded job with a description.
- Assert the Required section exists and names at least one technology.
- **Assert the quoted sentence for one requirement appears verbatim on the
  page**, and that the quoted text is a substring of the rendered description.
  That assertion is the criterion, not a proxy for it.
- Assert that a technology under a preferred heading is **not** in the Required
  section.
- **Normalise on entry, not only on exit.** M2b's pipeline test could not run
  twice because it tidied up on the way out and assumed a clean start. This test
  reads state and adapts rather than assuming.

- [ ] **Step 2: Add `check_job_requirements` to `scripts/verify.py`**

Follow `check_daily_queue`'s shape: compare **before and after** rather than
against an absolute state. Asserting "this job has 4 requirements" passes
vacuously on a fresh database and fails on a developer's own. Assert instead:

```
✓ the job detail answers                       HTTP 200
✓ requirements carry an extractor version
✓ every span quotes the description it points at
✓ no preferred technology appears as required
✓ a description change replaces the requirements   n -> m
✓ the job is left as it was found                  nothing is left behind
```

- [ ] **Step 3: Run the three commands**

```bash
make check
make acceptance
make test-e2e
```

**All three, separately.** `make test-e2e` is the degraded-path suite and needs
the API *down* — the opposite stack state from acceptance, so neither aggregate
target can run it. Four of this project's CI failures were caught by exactly that
gap. Record the counts you read from the output, not the counts you expect.

- [ ] **Step 4: Run `make acceptance` three times back to back**

That is the idempotency evidence rather than a hope about it.

- [ ] **Step 5: Write ADR 0015**

`docs/adr/0015-requirements-are-extracted-with-spans.md`. Record: rules over a
model; the span requirement and why the trigger rather than a convention; why I2
does not govern `job_requirements` even though it looks like it should; and the
`necessity` three-way split with the Ramp posting as the worked example.

- [ ] **Step 6: Write the review**

`docs/reviews/milestone-3a-review.md`, per CLAUDE.md §5. Actively look for:
hallucinated certainty, silent data loss, tests that assert nothing, spans that
can drift, and any "not built yet" list that has gone stale. Count how many
findings were in code that reported success — eight consecutive milestones have
recorded that number and it is the most useful line in these reviews.

- [ ] **Step 7: Update PROGRESS**

Record: the measured extraction precision, recall and necessity accuracy from
Task 7; how many postings the answer key holds; what the corpus could not
demonstrate (the `coverage_not_available_on_this_board` union); and under **Not
real yet** — the eligibility gate, the score, and everything else in
`matching.md` §9.

- [ ] **Step 8: Commit and push**

```bash
make check
git add docs apps/web/e2e-seeded scripts/verify.py
git commit -m "docs(m3a): record the answer key, its numbers, and what it found"
git push -u origin m3a-answer-key
```

- [ ] **Step 9: Before opening the PR, check the invariant**

```bash
git diff <last-commit-CI-executed>..HEAD --stat   # must list nothing outside docs/
```

If it shows a file under `apps/`, `services/`, `infra/`, `data/` or the Makefile,
the recorded results do not cover the branch and the three commands must run
again.

---

## Self-review

**Spec coverage** — `matching.md` §1's M3a row asks for four things: the recorded
corpus (Tasks 1–2), the labeling worksheet and answer key (Tasks 3–4 plus the
gate), requirement extraction (Tasks 5–8), and the job page showing what a
posting requires (Tasks 9–10). §3.6's fifth blind spot is Task 11. §3.2's label
shape is implemented field-for-field in Tasks 3 and 4. §4.1's table matches Task
5 column for column.

**Deferred to M3b, correctly** — the eligibility gate itself, role-family and
seniority classification, and the `uncertain` resolution of `+equivalent`. Task 5
stores `has_equivalence` so M3b has it; nothing in M3a reads it beyond the tests.

**The one interface this plan did not read from source turned out to be a
defect, not a naming slip.** The first draft called `vocabulary.find_all` and
assumed it returned every occurrence. The real method is `match`, and it returns
**one match per canonical name**. For a resume that is correct and deliberate;
for a job posting it means an "about us" mention hides the requirement further
down, and required-technology recall would have been silently depressed on
exactly the postings Task 7 grades. It would have read as a tuning problem.
Task 6 Step 0 now adds `match_all` alongside it, with the resolution rule
(strongest necessity wins) and three tests that fail if the ranking inverts.
Every other cross-task interface here was read from source.

**The two red tests in Task 4 are intentional** and stay red until the human gate
closes. A plan that hid them would produce a suite that goes green while the
answer key is empty, which is the failure this milestone exists to prevent.
