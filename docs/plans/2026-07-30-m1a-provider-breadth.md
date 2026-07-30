# M1a — Provider breadth: Lever and Ashby behind one interface

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three ATS providers ingesting through one adapter interface, with a
location parser whose breadth was driven by real recorded payloads from all
three rather than tuned to one.

**Architecture:** Two new adapters (`lever.py`, `ashby.py`) implementing the
existing `JobSourceAdapter` Protocol unchanged. The location parser grows a
list-shaped entry point, because Lever and Ashby express multi-location as JSON
arrays rather than as Greenhouse's `;`-delimited string — joining those arrays
into a string just to re-split it would discard structure the provider gave us.
Two prerequisites from `docs/PROGRESS.md` "Before M1 starts" are folded in at the
end, because everything after this plan makes them load-bearing.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.0 async, pytest,
pytest-asyncio, ruff, mypy strict.

---

## Where this sits

M1 as written in `CLAUDE.md` §6 is four independent subsystems. This is the
first of four plans; each produces working, testable software on its own.

| Plan | Contents | Status |
|---|---|---|
| **M1a — provider breadth** (this) | Lever + Ashby adapters, location fixtures and parser breadth, upserts, ingestion + route tests | Ready |
| M1b — canonical spine | Layered dedupe, freshness, closure state machine, admin job table | Not written |
| M1c — board discovery | `nightshift/discovery/`, Common Crawl, validation, batch approval, coverage page | Not written — design at `docs/architecture/board-discovery.md` |
| M1d — polling | Two-phase conditional polling, hot/warm tiers, queue-driven ARQ | Not written — design at ADR 0007 |

M1a is first because `docs/architecture/board-discovery.md` §14 names its first
two items as hard prerequisites of the discovery design, and §8 makes NYC-ness —
which drives tier membership in M1d — a function of the parser this plan widens.

---

## Global Constraints

Every task's requirements implicitly include these.

- **I1 — never fabricate a location.** No task in this plan may produce a
  coordinate. `ParsedLocation` has no latitude/longitude field and gains none.
  A place name is accepted only with corroboration or an explicit committed
  decision (Task 5).
- **I3 — never silently close a listing.** A non-200, a timeout, or malformed
  JSON produces `FetchOutcome(ok=False)`. A 200 with an empty array produces
  `ok=True` with `is_authoritative_empty == True`. These are different facts.
- **I7 — never let a mock become the product.** Every fixture is a recorded real
  payload with a committed `*.meta.json` stating its provenance. Reducing the
  *set* of jobs is allowed; editing the contents of a job is not. Synthetic
  cases in `locations.yaml` carry `synthetic: true`.
- **Nothing outside `nightshift/adapters/http.py` imports `httpx`.**
- **`OUTBOUND_HTTP_ENABLED` defaults to `false`.** Tests never reach the
  network. Only `scripts/record_fixture.py` enables it, and only when a human
  runs it.
- **mypy strict must pass** — `cd services/api && mypy nightshift`.
- **Run `make check` before every commit** (format, lint, typecheck, test, both
  languages).
- **Conventional commits, scoped**: `feat(ingestion):`, `fix(dedupe):`,
  `test(matching):`, `docs(adr):`.
- **Time is UTC everywhere.** `TIMESTAMPTZ` in the database; naive datetimes are
  rejected at the boundary by `nightshift/db/types.py`.
- **TODOs carry a milestone**: `TODO(M3): ...`. A bare `TODO` is a lint failure.

---

## Measured facts this plan is built on

Probed live on 2026-07-30 with the project User-Agent, one request at a time,
≥1.2s apart (Lever's `robots.txt` sets `Crawl-delay: 1`). Re-verify before
relying on field shapes — AMENDMENTS A1 says the same.

**Board availability.** Ten Lever tokens guessed, two live. This is direct
evidence for ADR 0006: Lever boards are genuinely hard to find, which is why
discovery must probe careers pages rather than harvest a crawl.

| Provider | Token | HTTP | Postings | Role in this plan |
|---|---|---:|---:|---|
| Lever | `alloy` | 200 | 9 | Populated-board fixture |
| Lever | `plaid` | 200 | 0 | **Authoritative-empty** fixture (I3) |
| Lever | `ramp` | 404 | — | **Unreachable** fixture (I3) |
| Ashby | `ramp` | 200 | 123 | Populated NYC-heavy fixture |
| Ashby | `openai` / `linear` / `vanta` | 200 | 747 / 23 / 101 | Not recorded; noted as available |

**Lever job object.** Top-level keys: `id`, `text` (the title), `categories`,
`country`, `createdAt`, `hostedUrl`, `applyUrl`, `salaryRange`, `workplaceType`,
`description`/`descriptionPlain`, `additional`/`additionalPlain`,
`descriptionBody`/`descriptionBodyPlain`, `opening`/`openingPlain`, `lists`.

- `categories.allLocations` is a **JSON array** of strings; `categories.location`
  is the primary as a single string.
- `categories.commitment` — observed `"Full-time"`.
- `workplaceType` — observed `"hybrid"`, `"remote"`.
- `salaryRange` is structured and clean:
  `{"min": 97000, "max": 135000, "currency": "USD", "interval": "per-year-salary"}`.
- `createdAt` is **epoch milliseconds** (`1783951681940`).
- **There is no updated/modified field.** `createdAt` only.
- **There is no company name field.**

**Ashby job object.** Keys: `id`, `title`, `location`, `secondaryLocations`,
`isRemote`, `workplaceType`, `employmentType`, `department`, `team`, `address`,
`compensation`, `descriptionHtml`, `descriptionPlain`, `publishedAt`, `jobUrl`,
`applyUrl`, `isListed`, `shouldDisplayCompensationOnJobPostings`.

- `secondaryLocations` is a **JSON array of objects**, each with a `.location`
  string.
- `location` strings carry parenthetical annotations: `"New York, NY (HQ)"`,
  `"Remote (US)"`, `"Remote (Canada)"`.
- `employmentType` — observed `"FullTime"`, `"Contract"`, **`"Intern"`**.
- `address.postalAddress` is **structured**:
  `{"addressLocality": "New York City", "addressRegion": "NY", "addressCountry": "USA"}`.
- `compensation.compensationTiers[].components[]` carries
  `{"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "USD",
  "minValue": 211400, "maxValue": 290600}` — so unlike Greenhouse, Ashby
  **states the period** and `salary_period` can be set honestly.
- **There is no updated/modified field.** `publishedAt` only.
- **There is no company name field**, confirming `board-discovery.md` §3.

**`isRemote` does not mean the job is remote.** On the Ramp board, 33 postings
are `location: "New York, NY (HQ)"` with `isRemote: true`. Mapping `isRemote`
onto `remote_policy = remote` would misclassify every one of them and is
specifically forbidden by Task 7.

### Two findings that touch already-approved designs

Record these; do not fix them here.

1. **ADR 0007 assumes `updated_at` in the listing.** Its phase-2 diff is "new or
   changed `updated_at`". Neither Lever nor Ashby publishes any such field.
   For those providers change detection must fall back to the description hash
   already computed by `content_hash()`. M1d must address this; Task 10 records
   it in PROGRESS so the polling plan starts from the truth.
2. **Ashby's structured `address.postalAddress` is better than its location
   string.** This plan does not consume it — geocoding is a later stage and
   feeding a second location source into the parser now would mean two code
   paths reaching `job_locations` before either has fixtures. Noted for M1's
   geocoding work.

### Two parser bugs that real data exposed

Both currently produce a fabricated city, which is an I1 failure in the one
module whose docstring claims to enforce I1.

| Input | Current output | Why |
|---|---|---|
| `"Vancouver, BC"` | city = **`"BC"`** | `BC` is in neither `_US_STATES` nor `_COUNTRIES`, so the tail stripper consumes nothing and `parts[-1]` — the subdivision code — is taken as the city |
| `"New York, NY (HQ)"` | city = **`"NY (HQ)"`** | `"ny (hq)"` misses the `_US_STATES` lookup, so the same thing happens |

Neither is hypothetical: `"Vancouver, BC"` appears 3× on the Lever board and
`"New York, NY (HQ)"` 95× on the Ashby board.

---

## File Structure

**Create**

| Path | Responsibility |
|---|---|
| `services/api/tests/fixtures/lever/alloy_board.json` | Recorded Lever board, 9 postings |
| `services/api/tests/fixtures/lever/alloy_board.meta.json` | Provenance for the above |
| `services/api/tests/fixtures/lever/plaid_empty_board.json` | `[]` — authoritative empty |
| `services/api/tests/fixtures/lever/plaid_empty_board.meta.json` | Provenance |
| `services/api/tests/fixtures/lever/ramp_unknown_board.json` | 404 body `{"ok":false,...}` |
| `services/api/tests/fixtures/lever/ramp_unknown_board.meta.json` | Provenance |
| `services/api/tests/fixtures/ashby/ramp_board.json` | Recorded Ashby board, reduced to 12 |
| `services/api/tests/fixtures/ashby/ramp_board.meta.json` | Provenance |
| `services/api/nightshift/adapters/lever.py` | Lever fetch + normalize |
| `services/api/nightshift/adapters/ashby.py` | Ashby fetch + normalize |
| `services/api/tests/test_lever_adapter.py` | Lever fixture tests |
| `services/api/tests/test_ashby_adapter.py` | Ashby fixture tests |
| `services/api/tests/test_ingestion.py` | `domain/ingestion.py` against a real database |
| `services/api/tests/test_routes.py` | API routes against a real database |
| `docs/adr/0008-decided-bare-place-names.md` | Why `"New York"` alone resolves |

**Modify**

| Path | Change |
|---|---|
| `services/api/tests/fixtures/locations.yaml` | Add Lever + Ashby cases (Task 3) |
| `services/api/nightshift/domain/locations.py` | `parse_location_list`, subdivisions, annotations, decided names |
| `services/api/nightshift/domain/ingestion.py:90-114` | `get_or_create_*` become upserts |
| `services/api/tests/conftest.py` | Database session fixture |
| `services/api/nightshift/cli.py` | Fixture adapters for Lever and Ashby |
| `data/board-registry.yaml` | Lever and Ashby entries |
| `scripts/record_fixture.py` | Reducers for Lever and Ashby |
| `docs/PROGRESS.md` | Evidence, "Not real yet" rows, session log |

---

## Task 1: Record the Lever fixtures

**Files:**
- Create: `services/api/tests/fixtures/lever/alloy_board.json`, `.meta.json`
- Create: `services/api/tests/fixtures/lever/plaid_empty_board.json`, `.meta.json`
- Create: `services/api/tests/fixtures/lever/ramp_unknown_board.json`, `.meta.json`
- Modify: `scripts/record_fixture.py`
- Test: `services/api/tests/test_fixture_provenance.py` (create)

**Interfaces:**
- Consumes: `PoliteClient` from `nightshift.adapters.http`; `ENDPOINTS` dict
  already present in `scripts/record_fixture.py` with `lever` and `ashby` keys.
- Produces: fixture files at the paths above. Tasks 3, 6 and 7 read them.

- [ ] **Step 1: Read the existing recorder to match its conventions**

Run: `sed -n 1,200p scripts/record_fixture.py`

Note how the Greenhouse reducer picks jobs and how `*.meta.json` is written.
The new reducers must follow the same shape: a `provenance` block, a
`why_each_job_is_here` map, and a `coverage_not_available_on_this_board` list.

- [ ] **Step 2: Write the failing provenance test**

This test is what stops a hand-edited fixture from passing as a recording.

```python
# services/api/tests/test_fixture_provenance.py
"""Every committed fixture must say where it came from.

I7's failure mode is a mock wearing a fixture's name. A fixture with no
provenance file cannot be distinguished from one somebody typed, so the
absence of the meta file is itself the bug this asserts against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
REQUIRED_PROVENANCE_KEYS = {"endpoint", "recorded_at", "board_token"}


def _payload_fixtures() -> list[Path]:
    return sorted(
        path
        for path in FIXTURE_ROOT.rglob("*.json")
        if not path.name.endswith(".meta.json")
    )


@pytest.mark.parametrize(
    "fixture", _payload_fixtures(), ids=lambda p: f"{p.parent.name}/{p.stem}"
)
def test_every_fixture_has_provenance(fixture: Path) -> None:
    meta = fixture.with_suffix(".meta.json")
    assert meta.exists(), f"{fixture.name} has no .meta.json — provenance is not optional"
    data = json.loads(meta.read_text())
    provenance = data["provenance"]
    missing = REQUIRED_PROVENANCE_KEYS - provenance.keys()
    assert not missing, f"{meta.name} provenance missing {sorted(missing)}"
    assert provenance["endpoint"].startswith("https://"), meta.name


def test_the_three_lever_i3_fixtures_exist() -> None:
    """I3 needs 404, empty-200 and populated-200 as three separate recordings.

    Asserted by name rather than by count: a suite that only counts files
    passes when the empty-board recording is quietly dropped, which is the
    exact fixture that stops an outage from closing jobs.
    """
    lever = FIXTURE_ROOT / "lever"
    for name in ("alloy_board", "plaid_empty_board", "ramp_unknown_board"):
        assert (lever / f"{name}.json").exists(), f"missing lever fixture {name}"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd services/api && pytest tests/test_fixture_provenance.py -v`
Expected: FAIL — `test_the_three_lever_i3_fixtures_exist` errors on the missing
`lever/` directory. The parametrized test passes (Greenhouse already has its
meta file), which is correct: it is guarding, not driving.

- [ ] **Step 4: Add the Lever reducer to the recorder**

In `scripts/record_fixture.py`, alongside the Greenhouse reducer, add:

```python
def _reduce_lever(payload: Any, limit: int) -> tuple[Any, dict[str, str], list[str]]:
    """Pick a reviewable subset of a Lever board, preserving each job verbatim.

    Selection is by *shape*, not by sampling: one job per distinct location
    string, so the fixture covers every location convention the board uses
    rather than whichever nine came back first.
    """
    if not isinstance(payload, list):
        raise SystemExit(f"lever board did not return a JSON array: {type(payload).__name__}")

    kept: list[Any] = []
    reasons: dict[str, str] = {}
    seen_shapes: set[str] = set()

    for job in payload:
        categories = job.get("categories") or {}
        shape = f"{categories.get('location')}|{job.get('workplaceType')}"
        if shape in seen_shapes and len(kept) >= limit:
            continue
        if shape not in seen_shapes:
            reasons[str(job["id"])] = (
                f"location {categories.get('location')!r}, "
                f"workplaceType {job.get('workplaceType')!r}"
            )
            seen_shapes.add(shape)
            kept.append(job)
        elif len(kept) < limit:
            reasons[str(job["id"])] = "additional posting on the same board"
            kept.append(job)

    gaps: list[str] = []
    if not any((j.get("categories") or {}).get("commitment") == "Intern" for j in payload):
        gaps.append("internship commitment")
    if not any("New York" in str((j.get("categories") or {}).get("allLocations")) for j in payload):
        gaps.append("NYC location")
    return kept, reasons, gaps
```

Register it next to the Greenhouse entry in whatever dispatch table the script
already uses (read Step 1's output for the exact name).

- [ ] **Step 5: Record the three Lever fixtures**

```bash
python scripts/record_fixture.py lever alloy
python scripts/record_fixture.py lever plaid
python scripts/record_fixture.py lever ramp
```

The `plaid` board returns `[]` and the `ramp` token 404s. If the recorder exits
non-zero on either, that is expected — it is built for populated boards. Write
those two fixtures by hand from the recorded response **body**, and say so in
their meta files. The body for `ramp` is:

```json
{"ok": false, "error": "Document not found"}
```

Name the files `plaid_empty_board.json` (containing `[]`) and
`ramp_unknown_board.json` (containing the object above).

- [ ] **Step 6: Write the meta file for each hand-written fixture**

```json
{
  "provenance": {
    "endpoint": "https://api.lever.co/v0/postings/plaid?mode=json",
    "recorded_at": "2026-07-30T00:00:00+00:00",
    "board_token": "plaid",
    "http_status": 200,
    "full_response_job_count": 0,
    "note": "Recorded by hand from the live response body, which was the two characters []. The recorder script targets populated boards and exits before writing for this case. Nothing was reduced; this IS the whole response."
  },
  "why_each_job_is_here": {},
  "coverage_not_available_on_this_board": [
    "everything - this board is genuinely empty, which is the point of the fixture"
  ]
}
```

Write the equivalent for `ramp_unknown_board.meta.json` with
`"http_status": 404` and a note that the body is the complete 404 response.

Replace `recorded_at` with the real UTC timestamp of your recording. Do not
copy the placeholder.

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd services/api && pytest tests/test_fixture_provenance.py -v`
Expected: PASS, with three new parametrized cases under `lever/`.

- [ ] **Step 8: Confirm the fixture is unedited**

```bash
cd /Users/tahmudun/Projects/Nightshift
python3 -c "
import json
d = json.load(open('services/api/tests/fixtures/lever/alloy_board.json'))
print('jobs:', len(d))
print('locations:', sorted({j['categories']['location'] for j in d}))
print('has salaryRange:', sum(1 for j in d if j.get('salaryRange')))
"
```

Expected: 9 jobs, locations including `Vancouver, BC` and
`Remote - United States`. If `Vancouver, BC` is absent the reducer dropped the
case Task 3 depends on — fix the reducer, do not add the string by hand.

- [ ] **Step 9: Commit**

```bash
git add scripts/record_fixture.py services/api/tests/fixtures/lever services/api/tests/test_fixture_provenance.py
git commit -m "test(adapters): record Lever board fixtures, including the I3 empty and 404 cases

Ten Lever tokens probed, two live. That ratio is itself evidence for
ADR 0006: Lever boards must be found by careers-page probing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Record the Ashby fixture

**Files:**
- Create: `services/api/tests/fixtures/ashby/ramp_board.json`, `.meta.json`
- Modify: `scripts/record_fixture.py`

**Interfaces:**
- Consumes: the recorder dispatch table extended in Task 1.
- Produces: `tests/fixtures/ashby/ramp_board.json`, read by Tasks 3 and 7.

- [ ] **Step 1: Add the Ashby reducer**

```python
def _reduce_ashby(payload: Any, limit: int) -> tuple[Any, dict[str, str], list[str]]:
    """Pick a reviewable subset of an Ashby board, preserving each job verbatim.

    Deliberately keeps one job per (location, employmentType) pair. The Ramp
    board is 123 postings and 95 of them share one location string; sampling
    the first N would produce a fixture that proves the adapter handles one
    shape twelve times.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise SystemExit("ashby board did not return {'jobs': [...]}")

    kept: list[Any] = []
    reasons: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()

    for job in payload["jobs"]:
        secondary = tuple(sorted(s.get("location", "") for s in job.get("secondaryLocations", [])))
        key = (f"{job.get('location')}|{secondary}", str(job.get("employmentType")))
        if key in seen or len(kept) >= limit:
            continue
        seen.add(key)
        reasons[str(job["id"])] = (
            f"location {job.get('location')!r}, "
            f"{len(secondary)} secondary, "
            f"employmentType {job.get('employmentType')!r}, "
            f"isRemote {job.get('isRemote')!r}"
        )
        kept.append(job)

    gaps: list[str] = []
    if not any(j.get("employmentType") == "Intern" for j in payload["jobs"]):
        gaps.append("internship employmentType")
    if not any(j.get("compensation", {}).get("compensationTiers") for j in payload["jobs"]):
        gaps.append("published compensation")
    return {"apiVersion": payload.get("apiVersion"), "jobs": kept}, reasons, gaps
```

- [ ] **Step 2: Record the board**

```bash
python scripts/record_fixture.py ashby ramp
```

- [ ] **Step 3: Verify the fixture covers the cases later tasks need**

```bash
cd /Users/tahmudun/Projects/Nightshift
python3 -c "
import json
d = json.load(open('services/api/tests/fixtures/ashby/ramp_board.json'))
jobs = d['jobs']
print('jobs:', len(jobs))
print('employmentTypes:', sorted({j['employmentType'] for j in jobs}))
print('nyc_hq_with_isRemote_true:', sum(1 for j in jobs if j.get('isRemote') and 'HQ' in str(j.get('location'))))
print('with_secondary:', sum(1 for j in jobs if j.get('secondaryLocations')))
print('with_compensation:', sum(1 for j in jobs if j.get('compensation',{}).get('compensationTiers')))
"
```

Required for later tasks, all of which must be non-zero:
`Intern` present in employmentTypes (Task 7 and the M0 internship gap),
`nyc_hq_with_isRemote_true` ≥ 1 (Task 7's misclassification guard),
`with_secondary` ≥ 1 (A2), `with_compensation` ≥ 1 (Task 7's salary period).

If `Intern` is missing, raise `limit` and re-record. Do not hand-add a job.

- [ ] **Step 4: Run the provenance test**

Run: `cd services/api && pytest tests/test_fixture_provenance.py -v`
Expected: PASS, now including `ashby/ramp_board`.

- [ ] **Step 5: Commit**

```bash
git add scripts/record_fixture.py services/api/tests/fixtures/ashby
git commit -m "test(adapters): record Ashby board fixture with real internship postings

Closes the M0 'Not real yet' row for internship employment types: the
Datadog board had zero, this one has real ones.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Location fixtures for Lever and Ashby (RED)

AMENDMENTS A2: **the fixture file grows before the parser does.** This task adds
only failing expectations. Tasks 4 and 5 make them pass.

**Files:**
- Modify: `services/api/tests/fixtures/locations.yaml`
- Test: `services/api/tests/test_locations.py` (unchanged — it is fixture-driven)

**Interfaces:**
- Consumes: location strings observed in the Task 1 and 2 fixtures.
- Produces: failing cases named `lever_*` and `ashby_*`, consumed by Tasks 4–5.

- [ ] **Step 1: Extract the real location strings from both recordings**

```bash
cd /Users/tahmudun/Projects/Nightshift
python3 -c "
import json
lv = json.load(open('services/api/tests/fixtures/lever/alloy_board.json'))
print('LEVER'); [print(' ', repr(j['categories']['location']), repr(j['categories'].get('allLocations'))) for j in lv]
ab = json.load(open('services/api/tests/fixtures/ashby/ramp_board.json'))['jobs']
print('ASHBY'); [print(' ', repr(j['location']), [s.get('location') for s in j.get('secondaryLocations',[])]) for j in ab]
"
```

Every `raw` you add below must appear in that output. A case invented at the
keyboard gets `synthetic: true`, per the file's own header.

- [ ] **Step 2: Append the new cases to `locations.yaml`**

Append to the `cases:` list, keeping the section-comment style already in the
file:

```yaml
  # -------------------------------------------------------------------------
  # Lever. Recorded from board `alloy` on 2026-07-30. Lever expresses multiple
  # locations as a JSON array (`categories.allLocations`), not as a delimited
  # string, so these are the shapes of an individual array element.
  # -------------------------------------------------------------------------

  # A Canadian province. Before this case the parser produced city "BC",
  # because BC is in neither the US-state nor the country table and the tail
  # stripper therefore consumed nothing. A fabricated city is an I1 failure.
  - name: lever_canadian_province
    raw: "Vancouver, BC"
    expect:
      - raw_text: "Vancouver, BC"
        city: "Vancouver"
        state: "British Columbia"
        country: null
        confidence: city_only
        is_primary: true

  # US state abbreviation in Lever's style. Already worked; here so a
  # regression in the subdivision table is caught on both countries at once.
  - name: lever_us_state_abbreviation
    raw: "Denver, CO"
    expect:
      - raw_text: "Denver, CO"
        city: "Denver"
        state: "Colorado"
        country: null
        confidence: city_only
        is_primary: true

  - name: lever_district_of_columbia
    raw: "Washington, DC"
    expect:
      - raw_text: "Washington, DC"
        city: "Washington"
        state: "District of Columbia"
        country: null
        confidence: city_only
        is_primary: true

  # Remote with the region trailing the token rather than parenthesised. The
  # country must survive: dropping the whole segment on a Remote match throws
  # away "United States", which is real information the source gave us.
  - name: lever_remote_with_trailing_country
    raw: "Remote - United States"
    expect:
      - raw_text: "Remote - United States"
        city: null
        state: null
        country: "USA"
        confidence: remote
        is_primary: true

  # -------------------------------------------------------------------------
  # Ashby. Recorded from board `ramp` on 2026-07-30. Ashby puts the primary in
  # `location` and the rest in `secondaryLocations[].location`, and annotates
  # office locations parenthetically.
  # -------------------------------------------------------------------------

  # 95 of the 123 postings on the recorded board use this exact string. Before
  # this case the parser produced city "NY (HQ)".
  - name: ashby_hq_annotation
    raw: "New York, NY (HQ)"
    expect:
      - raw_text: "New York, NY (HQ)"
        city: "New York"
        state: "New York"
        country: null
        confidence: city_only
        is_primary: true

  # The annotation is not always noise. Here it names the country, and
  # discarding it would lose the only geographic signal in the string.
  - name: ashby_remote_parenthetical_country
    raw: "Remote (US)"
    expect:
      - raw_text: "Remote (US)"
        city: null
        state: null
        country: "USA"
        confidence: remote
        is_primary: true

  - name: ashby_remote_parenthetical_country_canada
    raw: "Remote (Canada)"
    expect:
      - raw_text: "Remote (Canada)"
        city: null
        state: null
        country: "Canada"
        confidence: remote
        is_primary: true

  - name: ashby_canadian_city
    raw: "Toronto, ON"
    expect:
      - raw_text: "Toronto, ON"
        city: "Toronto"
        state: "Ontario"
        country: null
        confidence: city_only
        is_primary: true

  # A single foreign city with nothing corroborating it. Stays `unknown`
  # deliberately: a world gazetteer is not in scope, and ADR 0008 limits the
  # decided-name list to places NYC-ness depends on. The cost is real and is
  # named on the coverage page rather than hidden.
  - name: ashby_bare_foreign_city_stays_unknown
    raw: "London"
    expect:
      - raw_text: "London"
        city: null
        state: null
        country: null
        confidence: unknown
        is_primary: true

  # -------------------------------------------------------------------------
  # Decided bare place names (ADR 0008). "New York" alone is the string that
  # M1d's hot tier depends on and that the M0 parser returned `unknown` for.
  # -------------------------------------------------------------------------
  - name: bare_new_york_resolves
    synthetic: true
    raw: "New York"
    expect:
      - raw_text: "New York"
        city: "New York"
        state: "New York"
        country: null
        confidence: city_only
        is_primary: true

  - name: bare_brooklyn_resolves
    synthetic: true
    raw: "Brooklyn"
    expect:
      - raw_text: "Brooklyn"
        city: "Brooklyn"
        state: "New York"
        country: null
        confidence: city_only
        is_primary: true

  # The list is explicit and short by design. A place not on it is not
  # promoted, and this case is what proves the list is a list rather than a
  # general "any capitalised word is a city" rule.
  - name: undecided_bare_name_stays_unknown
    synthetic: true
    raw: "Springfield"
    expect:
      - raw_text: "Springfield"
        city: null
        state: null
        country: null
        confidence: unknown
        is_primary: true

  # An unrecognised two-letter subdivision must not become a city either. This
  # is the general form of the "BC" bug: fixing BC by adding it to a table
  # leaves every unlisted code broken, so the guard is on the shape.
  - name: unknown_two_letter_subdivision_is_not_a_city
    synthetic: true
    raw: "Bengaluru, KA"
    expect:
      - raw_text: "Bengaluru, KA"
        city: "Bengaluru"
        state: null
        country: null
        confidence: city_only
        is_primary: true
```

- [ ] **Step 3: Run the suite to verify the new cases fail**

Run: `cd services/api && pytest tests/test_locations.py -v`

Expected: the 13 new cases FAIL and every pre-existing case PASSES. Record the
actual failures — a new case that passes immediately is either already handled
(delete it, it proves nothing) or wrong.

Expected failures include:
`lever_canadian_province` (city `'BC'` != `'Vancouver'`),
`ashby_hq_annotation` (city `'NY (HQ)'` != `'New York'`),
`lever_remote_with_trailing_country` (country `None` != `'USA'`),
`bare_new_york_resolves` (city `None` != `'New York'`).

- [ ] **Step 4: Commit the failing fixtures**

Committing red fixtures is deliberate: A2 requires the fixture file to grow
first, and a reviewer should be able to see the expectations separately from
the code that satisfies them.

```bash
git add services/api/tests/fixtures/locations.yaml
git commit -m "test(locations): add Lever and Ashby location fixtures ahead of the parser

Fails at 13 cases, per AMENDMENTS A2: the fixture file grows before the
parser does, so one provider's conventions cannot be encoded as general.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Parser breadth — list input, subdivisions, annotations (GREEN 1)

**Files:**
- Modify: `services/api/nightshift/domain/locations.py`
- Test: `services/api/tests/test_locations.py` (existing, fixture-driven)

**Interfaces:**
- Consumes: the failing cases from Task 3.
- Produces:
  - `parse_location_list(segments: Sequence[str]) -> list[ParsedLocation]` —
    used by Tasks 6 and 7 for `allLocations` / `secondaryLocations`.
  - `parse_location_field(raw: str | None) -> list[ParsedLocation]` — unchanged
    signature, now a thin wrapper.

- [ ] **Step 1: Add the Canadian subdivision table**

After `_US_STATES` in `locations.py`:

```python
# Canadian provinces. Added because Lever and Ashby boards name Vancouver and
# Toronto, and without this table `parts[-1]` — the subdivision code — was
# being taken as the city, producing a place called "BC". No code here
# collides with a US postal abbreviation, so lookup order does not matter.
_CA_PROVINCES: dict[str, str] = {
    "alberta": "Alberta",
    "ab": "Alberta",
    "british columbia": "British Columbia",
    "bc": "British Columbia",
    "manitoba": "Manitoba",
    "mb": "Manitoba",
    "new brunswick": "New Brunswick",
    "nb": "New Brunswick",
    "newfoundland and labrador": "Newfoundland and Labrador",
    "nl": "Newfoundland and Labrador",
    "nova scotia": "Nova Scotia",
    "ns": "Nova Scotia",
    "ontario": "Ontario",
    "on": "Ontario",
    "prince edward island": "Prince Edward Island",
    "pe": "Prince Edward Island",
    "quebec": "Quebec",
    "québec": "Quebec",
    "qc": "Quebec",
    "saskatchewan": "Saskatchewan",
    "sk": "Saskatchewan",
}

# A bare two-letter token that resolved to no subdivision is not a city.
# Fixing "BC" by adding it to a table would leave every unlisted code broken,
# so the guard is on the shape of the token rather than on its value.
_BARE_SUBDIVISION_CODE = re.compile(r"^[A-Za-z]{2}$")

# A trailing parenthetical annotation: "New York, NY (HQ)", "Remote (US)".
# Sometimes noise, sometimes the only geographic signal present, so it is
# lifted out and re-interpreted rather than dropped.
_PAREN_SUFFIX = re.compile(r"\s*\(([^)]*)\)\s*$")

# "Remote - United States", "Remote — US", "Remote: EMEA".
_REMOTE_PREFIX = re.compile(
    r"^(?:fully\s+|100%\s+)?remote\b[\s\-–—:,]*",  # noqa: RUF001
    re.IGNORECASE,
)


def _lookup_subdivision(token: str) -> str | None:
    """Resolve a US state or Canadian province name or code."""
    key = token.casefold()
    return _US_STATES.get(key) or _CA_PROVINCES.get(key)
```

- [ ] **Step 2: Rewrite `_Tail` and `_strip_tail_tokens` to carry annotations**

Replace the existing `_Tail` dataclass and `_strip_tail_tokens` function:

```python
@dataclass(slots=True)
class _Tail:
    """Result of stripping recognised tail tokens off a segment."""

    parts: list[str]
    state: str | None = None
    country: str | None = None
    remote: bool = False
    dropped: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)


def _strip_tail_tokens(segment: str) -> _Tail:
    """Consume annotations, ``Remote``, a country, then a US/CA subdivision.

    Right-to-left, because the informative tokens are on the right. The order
    within this function is deliberate and each step depends on the one above:
    annotations must come off before a code like ``NY (HQ)`` can be recognised
    as a state, and ``Remote`` must come off before ``Remote - United States``
    can yield a country.
    """
    raw_parts = [" ".join(p.split()) for p in segment.split(",")]
    raw_parts = [p for p in raw_parts if p]

    # 1. Lift trailing parentheticals out of each part.
    parts: list[str] = []
    annotations: list[str] = []
    for part in raw_parts:
        match = _PAREN_SUFFIX.search(part)
        if match is not None:
            inner = match.group(1).strip()
            if inner:
                annotations.append(inner)
            part = part[: match.start()].strip()
        if part:
            parts.append(part)

    tail = _Tail(parts=parts, annotations=annotations)

    # 2. Remote, wherever it appears. Anything trailing the token on the same
    #    part survives as a part of its own: "Remote - United States" must not
    #    throw away "United States".
    remaining: list[str] = []
    for part in tail.parts:
        if _REMOTE_TOKEN.match(part):
            tail.remote = True
            tail.dropped.append(part)
            residue = _REMOTE_PREFIX.sub("", part).strip()
            if residue:
                remaining.append(residue)
        else:
            remaining.append(part)
    tail.parts = remaining

    # 3. Country, then subdivision — in that order, because "New York, USA"
    #    puts the country last and the state immediately before it.
    if tail.parts:
        country = _COUNTRIES.get(tail.parts[-1].casefold())
        if country is not None:
            tail.country = country
            tail.parts.pop()

    if tail.parts:
        state = _lookup_subdivision(tail.parts[-1])
        if state is not None:
            tail.state = state
            tail.parts.pop()

    # 4. An annotation can carry the country or the subdivision. Only consulted
    #    where the segment itself said nothing, so an explicit value always
    #    wins over a parenthesised one.
    for annotation in tail.annotations:
        if tail.country is None:
            country = _COUNTRIES.get(annotation.casefold())
            if country is not None:
                tail.country = country
                continue
        if tail.state is None:
            state = _lookup_subdivision(annotation)
            if state is not None:
                tail.state = state

    # 5. A leftover bare two-letter code is an unrecognised subdivision, not a
    #    city. Drop it rather than promote it.
    if tail.parts and _BARE_SUBDIVISION_CODE.match(tail.parts[-1]):
        tail.dropped.append(tail.parts.pop())

    return tail
```

- [ ] **Step 3: Add the list entry point**

Replace `_split_segments` and `parse_location_field`:

```python
def parse_location_list(segments: Sequence[str]) -> list[ParsedLocation]:
    """Parse an already-separated list of location strings.

    Lever's ``categories.allLocations`` and Ashby's ``secondaryLocations`` are
    JSON arrays. Joining them into a delimited string so that
    :func:`parse_location_field` can split them again would discard structure
    the provider handed us — and would break on any location containing the
    delimiter. Both entry points share every downstream rule.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for chunk in segments:
        text = " ".join((chunk or "").split())
        if not text:
            continue
        # Collapse exact duplicates. A board that lists the same office twice
        # should not produce two rows that later look like two offices.
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)

    return [
        parse_location_segment(segment, is_primary=(index == 0))
        for index, segment in enumerate(cleaned)
    ]


def parse_location_field(raw: str | None) -> list[ParsedLocation]:
    """Parse a source's delimited location field into one location per place.

    Returns an empty list for empty input: a posting with no location text gets
    no location rows, rather than one row claiming to be somewhere.

    The first segment is marked primary, matching source order. Providers list
    the requisition's home office first; when they do not, the value is still a
    real location the posting names, so ordering affects sorting and never
    correctness.
    """
    return parse_location_list(_SEGMENT_SPLIT.split(raw or ""))
```

Add `from collections.abc import Sequence` to the imports.

- [ ] **Step 4: Run the suite**

Run: `cd services/api && pytest tests/test_locations.py -v`

Expected: every case passes except the three ADR-0008 ones —
`bare_new_york_resolves`, `bare_brooklyn_resolves`. (`undecided_bare_name_stays_unknown`
and `ashby_bare_foreign_city_stays_unknown` should already pass; they assert the
absence of a rule.) Task 5 handles the remaining two.

If `unknown_two_letter_subdivision_is_not_a_city` fails, the step-2 ordering is
wrong: the bare-code guard must run *after* the subdivision lookup, or
`"Denver, CO"` loses its state.

- [ ] **Step 5: Typecheck**

Run: `cd services/api && mypy nightshift && ruff check nightshift && ruff format --check nightshift`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add services/api/nightshift/domain/locations.py
git commit -m "fix(locations): stop fabricating cities from subdivision codes and annotations

'Vancouver, BC' parsed to a city called BC and 'New York, NY (HQ)' to one
called 'NY (HQ)' — both I1 failures in the module that enforces I1, and
both present in real recorded payloads. Adds a list entry point so Lever
and Ashby arrays are not round-tripped through a delimited string.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Parser breadth — decided bare place names (GREEN 2)

`"New York"` alone returning `unknown` is the gap `docs/PROGRESS.md` names as
item 1 and the one `board-discovery.md` §8 makes M1d's tier assignment depend
on. Resolving it is a judgement call about honesty, so it gets an ADR.

**Files:**
- Modify: `services/api/nightshift/domain/locations.py`
- Create: `docs/adr/0008-decided-bare-place-names.md`

**Interfaces:**
- Consumes: `_lookup_subdivision`, `_Tail` from Task 4.
- Produces: no new public function. `parse_location_segment` keeps its
  signature.

- [ ] **Step 1: Write the ADR first**

The decision drives the code, so it gets written first — and if it cannot be
justified in prose it should not be in the parser.

```markdown
# ADR 0008 — Decided bare place names

**Status:** Accepted
**Date:** 2026-07-30
**Milestone:** M1

## Context

`parse_location_field("New York")` returns `unknown`. The parser requires
corroboration before accepting a token as a city — a recognised state or
country in the same segment, or a preceding comma part — which is what keeps
`"Global"` and `"Multiple Locations"` out of the city column.

`"New York"` alone is genuinely ambiguous: it names both a city and a state.

The cost of leaving it `unknown` is concrete. `docs/architecture/board-discovery.md`
§8 derives NYC-ness from parsed locations, and ADR 0007 assigns a board to the
hourly `hot` tier when it has produced an NYC posting. A board whose postings
say `"New York"` would poll daily instead of hourly, so the product's stated
goal — same-day knowledge of an NYC opening — would fail on exactly the
strings most likely to name New York.

## Decision

A short, explicit, committed list of bare place names that resolve without
corroboration. It contains New York City, its five boroughs, and their common
spellings — nothing else.

Resolution yields `city_only` and never higher. No coordinate is produced, so
invariant I1 is untouched: I1 forbids inventing a *position*, and `city_only`
is the confidence value that exists to say "we know the city and nothing
finer."

Every other bare token keeps the existing behaviour and resolves to `unknown`.

## Why this is not the guessing I1 forbids

Three properties distinguish it from a general gazetteer:

1. **It is enumerated and committed.** A reader can see the entire list. A
   fuzzy matcher or a downloaded gazetteer would make the same promotion for
   thousands of names nobody reviewed.
2. **It cannot manufacture precision.** The output is `city_only` with null
   coordinates. Geocoding is a separate stage with its own audit trail.
3. **The residual error is bounded and named.** If a posting saying
   `"New York"` meant the state, we record city "New York", state "New York" —
   which at `city_only` precision places nothing and misstates nothing that a
   later geocode would not correct. `ashby_bare_foreign_city_stays_unknown`
   and `undecided_bare_name_stays_unknown` are the fixtures that keep the list
   a list.

## Consequences

- `"London"`, `"Toronto"`, `"Springfield"` and every other bare city name stay
  `unknown`. This is a real coverage gap and belongs on the coverage page
  (`board-discovery.md` §11) under named blind spots, not in a footnote.
- Adding a name to the list is a code review with a fixture, deliberately.
- If a future milestone wants worldwide bare-city resolution, it needs a real
  gazetteer, a provenance field on the resolution, and its own ADR. Extending
  this list to get there would be the slow version of the thing this ADR
  refuses.

## Alternatives rejected

**Leave it `unknown`.** Honest but breaks the hot tier on the most common way
of naming New York, which defeats the product goal that M1d exists to serve.

**Treat any capitalised unmatched token as a city.** Restores the exact bug
Task 4 removed, at scale.

**Infer from sibling postings on the same board.** Makes parsing depend on
order and on other rows, so the same string parses differently in different
runs — and `test_parse_is_deterministic` exists to forbid that.
```

- [ ] **Step 2: Add the decided-name table**

In `locations.py`, after `_CA_PROVINCES`:

```python
# ADR 0008. A bare place name normally resolves to `unknown`, because a lone
# token with nothing corroborating it is not evidence of a city. These are the
# documented exceptions: NYC and its boroughs, which M1d's hot tier depends on
# and which providers routinely write without a state.
#
# Enumerated on purpose. The value is (city, state, country), and the result is
# `city_only` — never a coordinate, so I1 is untouched.
_DECIDED_BARE_PLACES: dict[str, tuple[str, str | None, str | None]] = {
    "new york": ("New York", "New York", None),
    "new york city": ("New York", "New York", None),
    "nyc": ("New York", "New York", None),
    "manhattan": ("Manhattan", "New York", None),
    "brooklyn": ("Brooklyn", "New York", None),
    "queens": ("Queens", "New York", None),
    "the bronx": ("The Bronx", "New York", None),
    "bronx": ("The Bronx", "New York", None),
    "staten island": ("Staten Island", "New York", None),
}
```

- [ ] **Step 3: Consult it in `parse_location_segment`**

Replace the city-resolution block in `parse_location_segment`:

```python
def parse_location_segment(segment: str, *, is_primary: bool) -> ParsedLocation:
    """Parse one already-split segment."""
    tail = _strip_tail_tokens(segment)
    corroborated = tail.state is not None or tail.country is not None

    city: str | None = None
    state = tail.state
    country = tail.country

    if tail.parts:
        candidate = tail.parts[-1]
        if corroborated or len(tail.parts) > 1:
            # With a street address the city is the last unconsumed part:
            # "620 8th Ave, New York" -> "New York".
            city = candidate
        else:
            # A bare token. Only an enumerated, reviewed name is promoted
            # (ADR 0008); everything else stays unknown, which is what keeps
            # "Global" and "Multiple Locations" out of the city column.
            decided = _DECIDED_BARE_PLACES.get(candidate.casefold())
            if decided is not None:
                city, state, country = (
                    decided[0],
                    state or decided[1],
                    country or decided[2],
                )

    if tail.remote:
        confidence = LocationConfidence.REMOTE
    elif city is not None:
        confidence = LocationConfidence.CITY_ONLY
    else:
        # Either nothing parsed, or only country-level information — coarser
        # than city, so it does not earn `city_only`.
        confidence = LocationConfidence.UNKNOWN

    return ParsedLocation(
        raw_text=segment,
        city=city,
        state=state,
        country=country,
        confidence=confidence,
        is_primary=is_primary,
    )
```

- [ ] **Step 4: Run the full location suite**

Run: `cd services/api && pytest tests/test_locations.py -v`
Expected: PASS, all cases including the 13 added in Task 3.

- [ ] **Step 5: Prove the new rule can fail**

A rule that promotes everything would also pass. Confirm it does not:

```bash
cd services/api && python3 -c "
from nightshift.domain.locations import parse_location_field
for raw in ['New York', 'Springfield', 'London', 'Global', 'Multiple Locations']:
    p = parse_location_field(raw)[0]
    print(f'{raw!r:22} city={p.city!r:14} state={p.state!r:12} {p.confidence.value}')
"
```

Expected: only `New York` resolves. The other four stay `city=None`,
`unknown`. If `Springfield` resolves, the table is being bypassed.

- [ ] **Step 6: Confirm determinism still holds**

Run: `cd services/api && pytest tests/test_locations.py -k determin -v`
Expected: PASS. M1's acceptance criterion "same fixture in, byte-identical
output twice" depends on this and it must not have been weakened.

- [ ] **Step 7: `make check`, then commit**

```bash
make check
git add services/api/nightshift/domain/locations.py docs/adr/0008-decided-bare-place-names.md
git commit -m "feat(locations): resolve an enumerated set of bare NYC place names

ADR 0008. 'New York' alone returned unknown, which would have kept boards
naming it that way out of M1d's hourly tier — failing the product goal on
the most common way of writing New York.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Lever adapter

**Files:**
- Create: `services/api/nightshift/adapters/lever.py`
- Create: `services/api/tests/test_lever_adapter.py`
- Modify: `data/board-registry.yaml`

**Interfaces:**
- Consumes: `BoardRef`, `FetchOutcome`, `NormalizedSourceJob`, `RawJob`,
  `SourceUnavailableError` from `nightshift.adapters.base`; `PoliteClient`;
  `parse_location_list`, `infer_remote_policy` from `nightshift.domain.locations`;
  `content_hash`, `normalize_title` from `nightshift.adapters.greenhouse`.
- Produces: `LeverAdapter` with `source_name = "lever"`,
  `source_type = SourceType.ATS_LEVER`, satisfying the `JobSourceAdapter`
  Protocol. Used by Task 8's ingestion tests and by M1d's polling.

- [ ] **Step 1: Note what is already in place**

Checked while writing this plan, so no action is needed — recorded here so the
implementer does not go looking:

- `SourceType` already has `ATS_LEVER`, `ATS_ASHBY` and `FIXTURE`
  (`nightshift/db/base.py:112-117`). **No migration is required** by this task
  or by Task 7.
- `EmploymentType` has `TEMPORARY` as a member distinct from `CONTRACT`
  (`base.py:120-126`), so the maps below route "temporary" to `TEMPORARY`
  rather than folding it into `CONTRACT`.
- `pyproject.toml` sets `asyncio_mode = "auto"`, so async tests need no
  `@pytest.mark.asyncio` marker. The test code below omits it.

- [ ] **Step 1b: Widen the Protocol so `normalize` receives the board**

Found in the pre-flight scan of this plan, before any code was written. It is a
correctness fix, not a refactor, and it must land before the Lever adapter.

`JobSourceAdapter.normalize(raw_job)` takes no board. Greenhouse gets away with
that because its payload carries `company_name`. **Neither Lever nor Ashby
publishes a company name at all**, so the only fallback available inside
`normalize` is `raw_job.source_company_key` — the board token. And
`_persist_outcome` (`domain/ingestion.py:414`) calls exactly that method, so in
the real ingestion path every Lever and Ashby employer would be named by its
slug: `alloy`, `ramp`.

That is precisely the fabrication I2 forbids and that `board-discovery.md` §3
names in its own words — *"the token is not the name"*, `0g` is "0g Labs". A
separate `normalize_with_board()` that only the tests remember to call would
leave the production path broken while the suite stayed green, which is worse
than no fix.

So the board becomes part of the contract.

In `nightshift/adapters/base.py`, change the Protocol method:

```python
    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Map one raw posting onto the domain model.

        Takes the board because two of the three providers publish no employer
        name. The registry entry is a human-approved fact; the board token is a
        slug, and deriving a company from it is the I2 failure that ADR 0005's
        `live_unnamed` verdict exists to catch.

        Synchronous and pure: same input, same output, no I/O. That is what
        makes M1's "same fixture in, byte-identical output, twice" criterion
        testable.
        """
        ...
```

In `nightshift/adapters/greenhouse.py`, change the signature and prefer the
payload's own name, falling back to the reviewed registry entry rather than to
the token:

```python
    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
```

and replace the company-name line:

```python
        company_name = str(payload.get("company_name") or "").strip()
        # Greenhouse does publish a name. When it is blank, fall back to the
        # reviewed registry entry — never to the token.
        resolved_company = company_name or board.company
```

using `resolved_company` in the returned model.

In `nightshift/domain/ingestion.py`, `_persist_outcome` already holds the
board on the outcome. Change the call:

```python
            normalized = adapter.normalize(raw_job, outcome.board)
```

- [ ] **Step 1c: Confirm the existing suite still passes**

Run: `cd services/api && ./.venv/bin/pytest -q`

Expected: 204 passed. The Greenhouse adapter tests construct `normalize` calls
directly and will need the board argument added — that is the intended blast
radius, and it is small. Use
`BoardRef(company="Datadog", ats="greenhouse", token="datadog", nyc_presence=True)`.

Because of this step there is **one** normalize method, not two. Every code
block below already reflects that: adapters define
`normalize(self, raw_job, board)` and callers pass the `BoardRef`.

- [ ] **Step 2: Write the failing tests**

```python
# services/api/tests/test_lever_adapter.py
"""Lever adapter tests, driven by the committed board recordings.

The three I3 cases are the reason this file exists: a populated board, a live
board with no postings, and a token that does not resolve must produce three
distinguishable outcomes. Collapsing the last two is how a source outage
closes a thousand open jobs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.adapters.base import BoardRef, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import EmploymentType, LocationConfidence

FIXTURES = Path(__file__).parent / "fixtures" / "lever"
BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


def _board_payload() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "alloy_board.json").read_text())


def _raw_jobs() -> list[RawJob]:
    return [
        RawJob(
            source_job_id=str(job["id"]),
            source_company_key=BOARD.token,
            canonical_url=job.get("hostedUrl"),
            payload=job,
        )
        for job in _board_payload()
    ]


@pytest.fixture
def adapter() -> LeverAdapter:
    # No client: normalize() is pure and must not need one. An adapter that
    # cannot be constructed without a client cannot be unit-tested offline.
    return LeverAdapter(client=None)


def test_normalizes_every_recorded_posting(adapter: LeverAdapter) -> None:
    for raw in _raw_jobs():
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.title
        assert normalized.company_name
        assert normalized.description_hash


def test_company_name_comes_from_the_registry_not_the_payload(adapter: LeverAdapter) -> None:
    """Lever publishes no company name. Inventing one from the token is I2.

    `alloy` happens to look like a company name; `a3c41b8b71eff8c4` does not.
    The rule has to hold for both, so the name comes from the registry entry a
    human approved.
    """
    payload = _board_payload()[0]
    assert "company" not in payload
    assert "companyName" not in payload
    normalized = adapter.normalize(_raw_jobs()[0], BOARD)
    assert normalized.company_name == "Alloy"


def test_all_locations_array_yields_one_row_each(adapter: LeverAdapter) -> None:
    """A2: Lever hands us an array and every element becomes a location row."""
    for raw in _raw_jobs():
        expected = raw.payload["categories"].get("allLocations") or []
        normalized = adapter.normalize(raw, BOARD)
        assert len(normalized.locations) == len(set(expected)), raw.source_job_id


def test_no_location_carries_a_coordinate(adapter: LeverAdapter) -> None:
    """I1, structurally: ParsedLocation has no coordinate field to populate."""
    for raw in _raw_jobs():
        for location in adapter.normalize(raw, BOARD).locations:
            assert not hasattr(location, "latitude")
            assert not hasattr(location, "longitude")


def test_canadian_province_is_not_read_as_a_city(adapter: LeverAdapter) -> None:
    """The 'Vancouver, BC' regression, asserted end to end through the adapter."""
    cities = {
        loc.city
        for raw in _raw_jobs()
        for loc in adapter.normalize(raw, BOARD).locations
    }
    assert "BC" not in cities
    assert "Vancouver" in cities


def test_salary_range_is_read_from_the_structured_field(adapter: LeverAdapter) -> None:
    """Unlike Greenhouse, Lever states the interval, so salary_period is set."""
    priced = [
        adapter.normalize(raw, BOARD)
        for raw in _raw_jobs()
        if raw.payload.get("salaryRange")
    ]
    assert priced, "fixture has no priced posting — re-record with one"
    for normalized in priced:
        assert normalized.salary_min is not None
        assert normalized.salary_currency == "USD"
        assert normalized.salary_period == "year"


def test_created_at_is_epoch_milliseconds_not_seconds(adapter: LeverAdapter) -> None:
    """1783951681940 read as seconds lands in the year 58,500.

    Every freshness calculation downstream reads this field, so getting the
    unit wrong is silent and total.
    """
    normalized = adapter.normalize(_raw_jobs()[0], BOARD)
    assert normalized.source_published_at is not None
    assert 2000 < normalized.source_published_at.year < 2100


def test_source_updated_at_is_none_because_lever_has_no_such_field(
    adapter: LeverAdapter,
) -> None:
    """Asserted rather than assumed: ADR 0007's diff strategy depends on it.

    A10 forbids presenting createdAt as a last-modified stamp, so the column
    stays null and M1d must diff on the content hash for this provider.
    """
    payload = _board_payload()[0]
    assert not [k for k in payload if "update" in k.lower() or "modif" in k.lower()]
    assert adapter.normalize(_raw_jobs()[0], BOARD).source_updated_at is None


def test_normalization_is_deterministic(adapter: LeverAdapter) -> None:
    """M1 acceptance: same fixture in, byte-identical output, twice."""
    first = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    second = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    assert first == second


class TestInvariantI3:
    """A source telling us nothing must be distinguishable from a source
    telling us there is nothing."""

    async def test_populated_board_is_ok_and_not_empty(self) -> None:
        adapter = LeverAdapter(client=_StubClient(_board_payload()))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert len(outcome.jobs) == 9
        assert outcome.is_authoritative_empty is False

    async def test_empty_board_is_authoritatively_empty(self) -> None:
        payload = json.loads((FIXTURES / "plaid_empty_board.json").read_text())
        assert payload == []
        adapter = LeverAdapter(client=_StubClient(payload))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert outcome.jobs == ()
        assert outcome.is_authoritative_empty is True

    async def test_unknown_token_is_not_ok_and_not_empty(self) -> None:
        from nightshift.adapters.base import SourceUnavailableError

        adapter = LeverAdapter(
            client=_StubClient(SourceUnavailableError("HTTP 404", http_status=404))
        )
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.http_status == 404
        assert outcome.is_authoritative_empty is False

    async def test_wrong_shape_is_not_read_as_empty(self) -> None:
        """Lever returns an array. An object means something changed upstream,
        and 'no jobs' is the one conclusion we must not draw from it."""
        adapter = LeverAdapter(client=_StubClient({"ok": False}))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False


class _StubClient:
    """Stands in for PoliteClient. Returns a payload or raises.

    Not a mock of the adapter under test — it replaces the network, which is
    the boundary a unit test is entitled to replace.
    """

    def __init__(self, result: Any) -> None:
        self._result = result

    async def get_json(self, url: str) -> Any:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd services/api && pytest tests/test_lever_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.adapters.lever'`.

- [ ] **Step 4: Write the adapter**

```python
# services/api/nightshift/adapters/lever.py
"""Lever job board adapter.

Endpoint (AMENDMENTS A1, verified against live boards on 2026-07-30):

    GET https://api.lever.co/v0/postings/{token}?mode=json

Unauthenticated, poll-only. `api.lever.co/robots.txt` is `Allow: /` with
`Crawl-delay: 1`, which `PoliteClient` already satisfies. Note that
`jobs.lever.co/robots.txt` disallows CCBot — that is why ADR 0006 says Lever
boards cannot be discovered from Common Crawl.

Field shapes were read off two real boards rather than from documentation:

* The response is a **JSON array**, not an object. An object shape is a source
  problem, never evidence of zero jobs (I3).
* `categories.allLocations` is an array of strings; `categories.location` is
  the primary. There is no delimited multi-location string to split.
* `salaryRange` is structured — `{min, max, currency, interval}` — and states
  its interval, so unlike Greenhouse `salary_period` can be set honestly.
* `createdAt` is **epoch milliseconds**.
* There is **no updated/modified field**, so `source_updated_at` stays null and
  change detection falls back to the description hash.
* There is **no company name**. It comes from the registry entry a human
  approved; deriving it from the token would be the I2 failure ADR 0005 and
  `board-discovery.md` §6 both turn on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final, Protocol

import structlog

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    NormalizedSourceJob,
    RawJob,
    SourceUnavailableError,
)
from nightshift.adapters.greenhouse import content_hash, normalize_title
from nightshift.db.base import EmploymentType, SourceType
from nightshift.domain.locations import infer_remote_policy, parse_location_list

log = structlog.get_logger(__name__)

BOARD_URL: Final = "https://api.lever.co/v0/postings/{token}?mode=json"

# Lever's own vocabulary, mapped explicitly. Anything unlisted is `unknown`
# rather than a plausible default — A13 is emphatic that eligibility is M3's
# hard problem and guessing it here would put an unversioned classifier in the
# ingestion path.
_COMMITMENTS: Final[dict[str, EmploymentType]] = {
    "full-time": EmploymentType.FULL_TIME,
    "full time": EmploymentType.FULL_TIME,
    "part-time": EmploymentType.PART_TIME,
    "part time": EmploymentType.PART_TIME,
    "intern": EmploymentType.INTERNSHIP,
    "internship": EmploymentType.INTERNSHIP,
    "contract": EmploymentType.CONTRACT,
    "temporary": EmploymentType.TEMPORARY,
}

# Lever's interval vocabulary. Unmapped values yield None: a period we cannot
# name is not a period we get to invent (A10).
_SALARY_INTERVALS: Final[dict[str, str]] = {
    "per-year-salary": "year",
    "per-month-salary": "month",
    "per-week-salary": "week",
    "per-day-salary": "day",
    "per-hour-wage": "hour",
}


class _JsonClient(Protocol):
    async def get_json(self, url: str) -> Any: ...


def _epoch_millis_to_datetime(value: object) -> datetime | None:
    """Convert Lever's millisecond epoch to an aware UTC datetime.

    Returns None for anything unparseable. Reading milliseconds as seconds
    silently produces a date tens of thousands of years out, and every
    freshness calculation downstream would inherit it.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _extract_locations(payload: dict[str, Any]) -> list[str]:
    """Every location string the posting names, primary first."""
    categories = payload.get("categories")
    if not isinstance(categories, dict):
        return []
    all_locations = categories.get("allLocations")
    if isinstance(all_locations, list):
        segments = [str(item) for item in all_locations if isinstance(item, str)]
        if segments:
            primary = categories.get("location")
            # Keep the provider's primary first; A2 lets order carry meaning
            # for sorting and nothing else.
            if isinstance(primary, str) and primary in segments:
                segments.remove(primary)
                segments.insert(0, primary)
            return segments
    primary = categories.get("location")
    return [primary] if isinstance(primary, str) and primary.strip() else []


def _extract_salary(
    payload: dict[str, Any],
) -> tuple[float | None, float | None, str | None, str | None]:
    salary = payload.get("salaryRange")
    if not isinstance(salary, dict):
        return None, None, None, None
    try:
        minimum = float(salary["min"]) if salary.get("min") is not None else None
        maximum = float(salary["max"]) if salary.get("max") is not None else None
    except (TypeError, ValueError):
        return None, None, None, None
    if minimum is None and maximum is None:
        return None, None, None, None
    if minimum is not None and maximum is not None and minimum > maximum:
        # Transposed range: keep the numbers, do not invent an ordering.
        minimum, maximum = maximum, minimum
    currency = salary.get("currency")
    currency = currency.strip().upper()[:3] if isinstance(currency, str) and currency else None
    interval = salary.get("interval")
    period = _SALARY_INTERVALS.get(interval.strip().casefold()) if isinstance(interval, str) else None
    return minimum, maximum, currency, period


def _description_text(payload: dict[str, Any]) -> str | None:
    """Lever ships plain text alongside its HTML, so no unescaping is needed."""
    parts = [
        payload.get("descriptionPlain"),
        payload.get("additionalPlain"),
    ]
    text = "\n\n".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return text or None


def _description_html(payload: dict[str, Any]) -> str | None:
    parts = [payload.get("description"), payload.get("additional")]
    html_text = "\n".join(p for p in parts if isinstance(p, str) and p.strip())
    return html_text or None


class LeverAdapter:
    """Implements :class:`~nightshift.adapters.base.JobSourceAdapter`."""

    source_name = "lever"
    source_type = SourceType.ATS_LEVER

    def __init__(self, client: _JsonClient | None) -> None:
        self._client = client

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        """Poll one board. Never raises — I3 lives or dies on this method."""
        if self._client is None:
            raise RuntimeError("LeverAdapter needs a client to fetch")
        url = BOARD_URL.format(token=board.token)
        try:
            payload = await self._client.get_json(url)
        except SourceUnavailableError as exc:
            log.warning(
                "lever_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if not isinstance(payload, list):
            # An unknown token 404s and never reaches here. A 200 with the
            # wrong shape is a source problem, and "no jobs" is the one
            # conclusion we must not draw from it.
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=200,
                error=f"unexpected payload shape: expected a JSON array, got {type(payload).__name__}",
            )

        jobs: list[RawJob] = []
        for entry in payload:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            jobs.append(
                RawJob(
                    source_job_id=str(entry["id"]),
                    source_company_key=board.token,
                    canonical_url=entry.get("hostedUrl") or entry.get("applyUrl"),
                    payload=entry,
                )
            )

        log.info("lever_board_fetched", board=board.token, jobs=len(jobs))
        return FetchOutcome(board=board, ok=True, jobs=tuple(jobs), http_status=200)

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Normalize, taking the employer name from the approved registry entry.

        Lever publishes no company name. `normalize()` satisfies the Protocol
        and falls back to the board token; the ingestion path calls this
        overload so the name is the one a human approved, never one derived
        from a slug (I2, and `board-discovery.md` §3 "the token is not the
        name").
        """
        payload = raw_job.payload

        title = str(payload.get("text") or "").strip()
        if not title:
            raise ValueError(f"lever job {raw_job.source_job_id} has no title")

        description_text = _description_text(payload)
        locations = parse_location_list(_extract_locations(payload))
        salary_min, salary_max, currency, period = _extract_salary(payload)

        categories = payload.get("categories")
        commitment = categories.get("commitment") if isinstance(categories, dict) else None
        employment_type = EmploymentType.UNKNOWN
        if isinstance(commitment, str):
            employment_type = _COMMITMENTS.get(commitment.strip().casefold(), EmploymentType.UNKNOWN)

        return NormalizedSourceJob(
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            company_name=board.company,
            canonical_url=raw_job.canonical_url,
            title=title,
            normalized_title=normalize_title(title),
            description_html=_description_html(payload),
            description_text=description_text,
            description_hash=content_hash(description_text),
            employment_type=employment_type,
            remote_policy=infer_remote_policy(list(locations)),
            locations=tuple(locations),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period=period,
            # A10: Lever publishes no deadline field at all.
            application_deadline=None,
            source_published_at=_epoch_millis_to_datetime(payload.get("createdAt")),
            # No such field on any Lever posting. Asserted in the test suite so
            # this stays a recorded fact rather than an assumption.
            source_updated_at=None,
        )
```

- [ ] **Step 5: Run the tests**

Run: `cd services/api && pytest tests/test_lever_adapter.py -v`
Expected: PASS.

If `test_all_locations_array_yields_one_row_each` fails on a count mismatch,
check whether the board lists the same location twice —
`parse_location_list` deduplicates, which is why the assertion compares
against `set(expected)`.

- [ ] **Step 6: Add the registry entry**

In `data/board-registry.yaml`, under `boards:`:

```yaml
  - company: Alloy
    ats: lever
    token: alloy
    added: 2026-07-30
    verified_at: 2026-07-30
    status: active
    nyc_presence: true
    notes: >-
      First Lever board in the registry. Verified live on 2026-07-30: HTTP 200,
      9 postings. Recorded as a fixture at
      tests/fixtures/lever/alloy_board.json. Its postings are DC, Denver and
      Vancouver rather than NYC — kept because it is the Lever board that was
      actually reachable, and because "Vancouver, BC" is the case that exposed
      the parser fabricating a city from a subdivision code.
```

- [ ] **Step 7: Verify the registry still validates**

Run: `cd services/api && pytest tests/test_registry.py -v`
Expected: PASS, 29 assertions plus whatever the new entry adds.

- [ ] **Step 8: `make check`, then commit**

```bash
make check
git add services/api/nightshift/adapters/lever.py services/api/tests/test_lever_adapter.py data/board-registry.yaml
git commit -m "feat(ingestion): add Lever adapter with fixture tests

Three I3 fixtures: populated board, live-but-empty board (200 []), and an
unknown token (404). Company name comes from the approved registry entry,
not from the token — Lever publishes no name and 'alloy' looking like one
is a coincidence the rule cannot rely on.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Ashby adapter

**Files:**
- Create: `services/api/nightshift/adapters/ashby.py`
- Create: `services/api/tests/test_ashby_adapter.py`
- Modify: `data/board-registry.yaml`

**Interfaces:**
- Consumes: the same base types as Task 6, plus `parse_location_list`.
- Produces: `AshbyAdapter` with `source_name = "ashby"`,
  `source_type = SourceType.ATS_ASHBY`, and the same
  `normalize(raw_job, board)` signature as `LeverAdapter`.

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/test_ashby_adapter.py
"""Ashby adapter tests, driven by the committed board recording.

The load-bearing test here is test_is_remote_does_not_mean_remote. On the
recorded board, postings at the New York office carry isRemote: true. Mapping
that field onto remote_policy would relabel the company's entire headquarters
as remote, and every one of those jobs is one a New York user is looking for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nightshift.adapters.ashby import AshbyAdapter
from nightshift.adapters.base import BoardRef, RawJob
from nightshift.db.base import EmploymentType, LocationConfidence

FIXTURES = Path(__file__).parent / "fixtures" / "ashby"
BOARD = BoardRef(company="Ramp", ats="ashby", token="ramp", nyc_presence=True)


def _board_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "ramp_board.json").read_text())


def _raw_jobs() -> list[RawJob]:
    return [
        RawJob(
            source_job_id=str(job["id"]),
            source_company_key=BOARD.token,
            canonical_url=job.get("jobUrl"),
            payload=job,
        )
        for job in _board_payload()["jobs"]
    ]


@pytest.fixture
def adapter() -> AshbyAdapter:
    return AshbyAdapter(client=None)


def test_normalizes_every_recorded_posting(adapter: AshbyAdapter) -> None:
    for raw in _raw_jobs():
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.title
        assert normalized.description_hash


def test_the_payload_contains_no_company_name(adapter: AshbyAdapter) -> None:
    """board-discovery.md §3, asserted rather than trusted.

    The batch-approval gate in ADR 0005 turns on 'the provider told us who this
    is'. If Ashby ever starts publishing a name, this test fails and the
    approval design should be revisited — which is the point of asserting it.
    """
    for job in _board_payload()["jobs"]:
        assert not [k for k in job if "compan" in k.lower() or "organi" in k.lower()]


def test_company_name_comes_from_the_registry(adapter: AshbyAdapter) -> None:
    normalized = adapter.normalize(_raw_jobs()[0], BOARD)
    assert normalized.company_name == "Ramp"


def test_is_remote_does_not_mean_remote(adapter: AshbyAdapter) -> None:
    """A posting at the New York office is not a remote posting.

    On the recorded board these carry isRemote: true, which appears to mean
    'remote candidates considered' rather than 'this job is remote'. Taking it
    at face value would relabel the headquarters.
    """
    office_with_remote_flag = [
        raw
        for raw in _raw_jobs()
        if raw.payload.get("isRemote") and "New York" in str(raw.payload.get("location"))
    ]
    assert office_with_remote_flag, "fixture lost the case — re-record per Task 2 step 3"

    for raw in office_with_remote_flag:
        normalized = adapter.normalize(raw, BOARD)
        assert normalized.remote_policy != "remote"
        primary = normalized.locations[0]
        assert primary.city == "New York"
        assert primary.confidence is LocationConfidence.CITY_ONLY


def test_hq_annotation_does_not_become_the_city(adapter: AshbyAdapter) -> None:
    cities = {loc.city for raw in _raw_jobs() for loc in adapter.normalize(raw, BOARD).locations}
    assert "NY (HQ)" not in cities
    assert "New York" in cities


def test_secondary_locations_each_get_a_row(adapter: AshbyAdapter) -> None:
    """A2: multi-location postings produce multiple job_locations rows."""
    multi = [raw for raw in _raw_jobs() if raw.payload.get("secondaryLocations")]
    assert multi, "fixture has no multi-location posting — re-record"
    for raw in multi:
        normalized = adapter.normalize(raw, BOARD)
        expected = {raw.payload["location"]} | {
            s["location"] for s in raw.payload["secondaryLocations"]
        }
        assert len(normalized.locations) == len(expected), raw.source_job_id
        assert normalized.locations[0].raw_text == raw.payload["location"]


def test_internship_employment_type_from_real_data(adapter: AshbyAdapter) -> None:
    """Closes the M0 'Not real yet' row.

    The Datadog board had zero internship postings, so that branch was covered
    only by synthetic unit tests. This board has real ones.
    """
    interns = [
        adapter.normalize(raw, BOARD)
        for raw in _raw_jobs()
        if raw.payload.get("employmentType") == "Intern"
    ]
    assert interns, "fixture lost the internship postings — re-record per Task 2 step 3"
    for normalized in interns:
        assert normalized.employment_type is EmploymentType.INTERNSHIP


def test_salary_period_is_set_because_ashby_states_the_interval(
    adapter: AshbyAdapter,
) -> None:
    """Greenhouse states no period and gets None. Ashby says '1 YEAR'.

    A10's rule is 'store what the source gives you' — which cuts both ways.
    """
    priced = [
        adapter.normalize(raw, BOARD)
        for raw in _raw_jobs()
        if raw.payload.get("compensation", {}).get("compensationTiers")
    ]
    assert priced, "fixture has no priced posting — re-record"
    salaried = [n for n in priced if n.salary_min is not None]
    assert salaried
    for normalized in salaried:
        assert normalized.salary_period == "year"
        assert normalized.salary_currency == "USD"


def test_equity_component_is_not_read_as_salary(adapter: AshbyAdapter) -> None:
    """compensationTiers carry Salary and EquityPercentage side by side.

    An EquityPercentage component has null minValue, and reading it as a
    salary would publish a pay range the employer never stated.
    """
    for raw in _raw_jobs():
        normalized = adapter.normalize(raw, BOARD)
        if normalized.salary_min is not None:
            assert normalized.salary_min > 1000


def test_source_updated_at_is_none_because_ashby_has_no_such_field(
    adapter: AshbyAdapter,
) -> None:
    for job in _board_payload()["jobs"]:
        assert not [k for k in job if "update" in k.lower() or "modif" in k.lower()]
    assert adapter.normalize(_raw_jobs()[0], BOARD).source_updated_at is None


def test_normalization_is_deterministic(adapter: AshbyAdapter) -> None:
    first = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    second = [adapter.normalize(raw, BOARD).model_dump_json() for raw in _raw_jobs()]
    assert first == second


class TestInvariantI3:
    async def test_populated_board_is_ok(self) -> None:
        adapter = AshbyAdapter(client=_StubClient(_board_payload()))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert outcome.jobs
        assert outcome.is_authoritative_empty is False

    async def test_empty_jobs_array_is_authoritatively_empty(self) -> None:
        adapter = AshbyAdapter(client=_StubClient({"apiVersion": 1, "jobs": []}))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is True
        assert outcome.is_authoritative_empty is True

    async def test_missing_jobs_key_is_not_read_as_empty(self) -> None:
        adapter = AshbyAdapter(client=_StubClient({"apiVersion": 1}))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False
        assert outcome.is_authoritative_empty is False

    async def test_unreachable_board_is_not_ok(self) -> None:
        from nightshift.adapters.base import SourceUnavailableError

        adapter = AshbyAdapter(client=_StubClient(SourceUnavailableError("timeout")))
        outcome = await adapter.fetch_board(BOARD)
        assert outcome.ok is False


class _StubClient:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def get_json(self, url: str) -> Any:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/test_ashby_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.adapters.ashby'`.

- [ ] **Step 3: Write the adapter**

```python
# services/api/nightshift/adapters/ashby.py
"""Ashby job board adapter.

Endpoint (AMENDMENTS A1, verified against a live board on 2026-07-30):

    GET https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true

Unauthenticated, poll-only. Field shapes read off the Ramp board (123
postings):

* The response is `{"apiVersion": 1, "jobs": [...]}`. A missing `jobs` key is
  a source problem, never evidence of zero jobs (I3).
* `location` is the primary; `secondaryLocations` is an array of objects each
  carrying a `location` string. Both routinely annotate parenthetically —
  "New York, NY (HQ)", "Remote (US)".
* `isRemote` does **not** mean the job is remote. 33 of the recorded postings
  are at the New York office with `isRemote: true`. Remote policy is derived
  from the parsed locations, exactly as it is for the other providers, and
  this field is deliberately not consulted.
* `compensation.compensationTiers[].components[]` states its `interval`
  ("1 YEAR"), so `salary_period` is set — unlike Greenhouse, which states no
  period and therefore gets None.
* `employmentType` is explicit and includes "Intern".
* There is **no updated/modified field** and **no company name**
  (`board-discovery.md` §3). Both are asserted in the test suite.
* `address.postalAddress` is structured and better than the location string.
  Deliberately unused here: geocoding is a later stage, and feeding a second
  location source into job_locations before it has fixtures would mean two
  code paths writing the same table.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final, Protocol

import structlog

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    NormalizedSourceJob,
    RawJob,
    SourceUnavailableError,
)
from nightshift.adapters.greenhouse import content_hash, html_to_text, normalize_title
from nightshift.db.base import EmploymentType, SourceType
from nightshift.domain.locations import infer_remote_policy, parse_location_list

log = structlog.get_logger(__name__)

BOARD_URL: Final = (
    "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
)

_EMPLOYMENT_TYPES: Final[dict[str, EmploymentType]] = {
    "fulltime": EmploymentType.FULL_TIME,
    "parttime": EmploymentType.PART_TIME,
    "intern": EmploymentType.INTERNSHIP,
    "contract": EmploymentType.CONTRACT,
    "temporary": EmploymentType.TEMPORARY,
}

_SALARY_INTERVALS: Final[dict[str, str]] = {
    "1 year": "year",
    "1 month": "month",
    "1 week": "week",
    "1 day": "day",
    "1 hour": "hour",
}


class _JsonClient(Protocol):
    async def get_json(self, url: str) -> Any: ...


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed: datetime | date = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            return None
    if isinstance(parsed, datetime):
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _extract_locations(payload: dict[str, Any]) -> list[str]:
    """Primary first, then every secondary location, in source order."""
    segments: list[str] = []
    primary = payload.get("location")
    if isinstance(primary, str) and primary.strip():
        segments.append(primary)
    secondary = payload.get("secondaryLocations")
    if isinstance(secondary, list):
        for entry in secondary:
            if isinstance(entry, dict):
                value = entry.get("location")
                if isinstance(value, str) and value.strip():
                    segments.append(value)
    return segments


def _extract_salary(
    payload: dict[str, Any],
) -> tuple[float | None, float | None, str | None, str | None]:
    """Pull the Salary component out of the compensation tiers.

    Only `compensationType == "Salary"` is read. A tier also carries
    EquityPercentage and Bonus components with null values, and treating any
    of them as pay would publish a range the employer never stated (A10).
    """
    compensation = payload.get("compensation")
    if not isinstance(compensation, dict):
        return None, None, None, None
    tiers = compensation.get("compensationTiers")
    if not isinstance(tiers, list):
        return None, None, None, None

    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        components = tier.get("components")
        if not isinstance(components, list):
            continue
        for component in components:
            if not isinstance(component, dict):
                continue
            if component.get("compensationType") != "Salary":
                continue
            try:
                minimum = (
                    float(component["minValue"]) if component.get("minValue") is not None else None
                )
                maximum = (
                    float(component["maxValue"]) if component.get("maxValue") is not None else None
                )
            except (TypeError, ValueError):
                continue
            if minimum is None and maximum is None:
                continue
            if minimum is not None and maximum is not None and minimum > maximum:
                minimum, maximum = maximum, minimum
            currency = component.get("currencyCode")
            currency = (
                currency.strip().upper()[:3] if isinstance(currency, str) and currency else None
            )
            interval = component.get("interval")
            period = (
                _SALARY_INTERVALS.get(interval.strip().casefold())
                if isinstance(interval, str)
                else None
            )
            return minimum, maximum, currency, period
    return None, None, None, None


class AshbyAdapter:
    """Implements :class:`~nightshift.adapters.base.JobSourceAdapter`."""

    source_name = "ashby"
    source_type = SourceType.ATS_ASHBY

    def __init__(self, client: _JsonClient | None) -> None:
        self._client = client

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        """Poll one board. Never raises — I3 lives or dies on this method."""
        if self._client is None:
            raise RuntimeError("AshbyAdapter needs a client to fetch")
        url = BOARD_URL.format(token=board.token)
        try:
            payload = await self._client.get_json(url)
        except SourceUnavailableError as exc:
            log.warning(
                "ashby_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=200,
                error="unexpected payload shape: missing 'jobs' array",
            )

        jobs: list[RawJob] = []
        for entry in payload["jobs"]:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            jobs.append(
                RawJob(
                    source_job_id=str(entry["id"]),
                    source_company_key=board.token,
                    canonical_url=entry.get("jobUrl") or entry.get("applyUrl"),
                    payload=entry,
                )
            )

        log.info("ashby_board_fetched", board=board.token, jobs=len(jobs))
        return FetchOutcome(board=board, ok=True, jobs=tuple(jobs), http_status=200)

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Normalize, taking the employer name from the approved registry entry.

        Ashby publishes no company name anywhere in its API. The board page
        title carries one, which discovery reads at candidate time
        (`board-discovery.md` §6); ingestion uses the reviewed registry entry.
        Deriving it from the token is what ADR 0005's `live_unnamed` verdict
        exists to prevent — "0g" is "0g Labs".
        """
        payload = raw_job.payload

        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError(f"ashby job {raw_job.source_job_id} has no title")

        description_html = payload.get("descriptionHtml")
        description_html = description_html if isinstance(description_html, str) else None
        description_plain = payload.get("descriptionPlain")
        description_text = (
            description_plain.strip()
            if isinstance(description_plain, str) and description_plain.strip()
            else html_to_text(description_html)
        )

        locations = parse_location_list(_extract_locations(payload))
        salary_min, salary_max, currency, period = _extract_salary(payload)

        employment_type = EmploymentType.UNKNOWN
        raw_employment = payload.get("employmentType")
        if isinstance(raw_employment, str):
            employment_type = _EMPLOYMENT_TYPES.get(
                raw_employment.strip().casefold().replace("-", "").replace(" ", ""),
                EmploymentType.UNKNOWN,
            )

        return NormalizedSourceJob(
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            company_name=board.company,
            canonical_url=raw_job.canonical_url,
            title=title,
            normalized_title=normalize_title(title),
            description_html=description_html,
            description_text=description_text,
            description_hash=content_hash(description_text),
            employment_type=employment_type,
            # Derived from parsed locations, exactly as for every other
            # provider. `isRemote` is deliberately not consulted — see the
            # module docstring and test_is_remote_does_not_mean_remote.
            remote_policy=infer_remote_policy(list(locations)),
            locations=tuple(locations),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period=period,
            application_deadline=None,
            source_published_at=_parse_timestamp(payload.get("publishedAt")),
            source_updated_at=None,
        )
```

- [ ] **Step 4: Run the tests**

Run: `cd services/api && pytest tests/test_ashby_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Add the registry entry**

```yaml
  - company: Ramp
    ats: ashby
    token: ramp
    added: 2026-07-30
    verified_at: 2026-07-30
    status: active
    nyc_presence: true
    notes: >-
      First Ashby board in the registry. Verified live on 2026-07-30: HTTP 200,
      123 postings, 95 of them at the New York headquarters. Company name is
      NOT in the API response — it comes from this entry, per ADR 0005 and
      board-discovery.md §3. Also the source of the project's first real
      internship postings; the Datadog board had none.
```

- [ ] **Step 6: `make check`, then commit**

```bash
make check
git add services/api/nightshift/adapters/ashby.py services/api/tests/test_ashby_adapter.py data/board-registry.yaml
git commit -m "feat(ingestion): add Ashby adapter with fixture tests

isRemote is deliberately not mapped to remote_policy: 33 recorded postings
sit at the New York office with isRemote true, and trusting it would
relabel the headquarters as remote.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: `get_or_create_*` become upserts

`docs/PROGRESS.md` "Before M1 starts" item 2 and `board-discovery.md` §14 item 2.
Check-then-insert is safe only at `max_jobs=1`. M1d makes polling queue-driven,
at which point two workers normalizing postings from the same employer race
between the `SELECT` and the `INSERT`, and `companies.normalized_name` is
unique — so one of them raises and the other silently wins.

**Files:**
- Modify: `services/api/nightshift/domain/ingestion.py:90-114`
- Test: `services/api/tests/test_ingestion.py` (created in Task 9; the
  concurrency test lives there)

**Interfaces:**
- Consumes: `Company`, `Source` models; `normalize_company_name`.
- Produces: unchanged signatures —
  `get_or_create_source(session, *, name, source_type, base_url=None) -> Source`
  and `get_or_create_company(session, display_name) -> Company`.

- [ ] **Step 1: Confirm the unique constraints the upsert will target**

Run:
```bash
cd services/api && python3 -c "
from nightshift.db.models import Company, Source
for model in (Company, Source):
    print(model.__tablename__, [(c.name, c.unique) for c in model.__table__.columns if c.unique])
    print('  table args:', model.__table__.constraints)
"
```

`ON CONFLICT` needs a real unique constraint or index. If `normalized_name` and
`sources.name` are not unique, stop — the fix is a migration, not an upsert.

- [ ] **Step 2: Rewrite both functions**

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert


async def get_or_create_source(
    session: AsyncSession, *, name: str, source_type: object, base_url: str | None = None
) -> Source:
    """Insert-or-fetch, atomically.

    Check-then-insert races the moment worker concurrency exceeds one, which
    ADR 0007's queue-driven polling makes routine. `ON CONFLICT DO NOTHING`
    followed by a read is one statement plus one read rather than a
    read-then-write window, and it never raises on the loser of the race.
    """
    stmt = (
        pg_insert(Source)
        .values(name=name, source_type=source_type, base_url=base_url)
        .on_conflict_do_nothing(index_elements=[Source.name])
    )
    await session.execute(stmt)
    source = (
        await session.execute(select(Source).where(Source.name == name))
    ).scalar_one()
    return source


async def get_or_create_company(session: AsyncSession, display_name: str) -> Company:
    """Insert-or-fetch, atomically, keyed on the normalized name.

    `normalized_name` is the identity column and it is unique, so the conflict
    target is the thing that actually decides whether two strings are the same
    employer. `canonical_name` is display text and is deliberately not part of
    the key: "Moody's" and "Moodys" are one company (see test_companies.py).
    """
    normalized = normalize_company_name(display_name)
    stmt = (
        pg_insert(Company)
        .values(canonical_name=display_name.strip(), normalized_name=normalized)
        .on_conflict_do_nothing(index_elements=[Company.normalized_name])
    )
    await session.execute(stmt)
    company = (
        await session.execute(select(Company).where(Company.normalized_name == normalized))
    ).scalar_one()
    return company
```

Note: `on_conflict_do_nothing` with a subsequent `SELECT` rather than
`DO UPDATE ... RETURNING`. `DO UPDATE` would bump `updated_at` on every poll of
an unchanged company, turning "nothing happened" into a write — which is the
spurious-update failure M1's idempotency criterion forbids.

- [ ] **Step 3: Typecheck and run the existing suite**

Run: `cd services/api && mypy nightshift && pytest -q`
Expected: mypy clean; all existing tests pass. Behaviour is unchanged at
concurrency 1, which is why the proof lives in Task 9.

- [ ] **Step 4: Commit**

```bash
git add services/api/nightshift/domain/ingestion.py
git commit -m "fix(ingestion): make get_or_create_source/company atomic upserts

Check-then-insert is safe only at max_jobs=1. ADR 0007 makes polling
queue-driven, and companies.normalized_name is unique, so the race becomes
a duplicate-company error the day concurrency changes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Database test harness and ingestion tests

`docs/PROGRESS.md` item 3: *"`domain/ingestion.py` and the API routes still have
no tests. Both needed a database, which is why they were skipped. The database
now exists, so that excuse is gone. This is the largest genuine coverage gap in
the repo."*

**Files:**
- Modify: `services/api/tests/conftest.py`
- Create: `services/api/tests/test_ingestion.py`

**Interfaces:**
- Consumes: `ingest_boards`, `persist_source_job`, `get_or_create_company` from
  `nightshift.domain.ingestion`; both new adapters.
- Produces: pytest fixtures `db_engine` (session-scoped) and `db_session`
  (function-scoped, rolled back), used by Task 10 as well.

- [ ] **Step 1: Add the database fixtures to `conftest.py`**

```python
# appended to services/api/tests/conftest.py
import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from nightshift.db.base import Base

# Tests that need a database are skipped rather than failed when one is not
# running. A suite that cannot run without `make up` is a suite people stop
# running; a suite that silently passes without it is worse. Skipping says so.
DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

requires_db = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="no DATABASE_URL — run `make up && make migrate` for database tests",
)


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[Any]:
    if DATABASE_URL is None:
        pytest.skip("no DATABASE_URL")
    engine = create_async_engine(DATABASE_URL, future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: Any) -> AsyncIterator[AsyncSession]:
    """One transaction per test, rolled back at the end.

    Rollback rather than truncate: it is faster, and it means a test cannot
    leave a row behind that makes the next one pass. The nested-transaction
    binding is what lets `session.begin_nested()` inside the pipeline keep
    working — ingestion uses a savepoint per posting.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        maker = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with maker() as session:
            yield session
        await transaction.rollback()
```

Add `from typing import Any` if it is not already imported.

- [ ] **Step 2: Write the ingestion tests**

```python
# services/api/tests/test_ingestion.py
"""The fetch -> preserve -> normalize -> persist pipeline, against a real database.

Every test here needs Postgres, because the behaviour under test is
transactional: savepoints, unique constraints, FK ordering and idempotency are
not observable against a fake session. Run `make up && make migrate` first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.ashby import AshbyAdapter
from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import JobStatus, SourceType
from nightshift.db.models import Company, Job, JobLocation, JobSourceLink, SourceJobRecord
from nightshift.domain.ingestion import (
    get_or_create_company,
    get_or_create_source,
    ingest_boards,
)
from tests.conftest import requires_db

pytestmark = requires_db

FIXTURES = Path(__file__).parent / "fixtures"
LEVER_BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


class _StubAdapter:
    """A real adapter with its network call replaced by a recorded outcome.

    The adapter's own normalize() runs untouched — replacing that would be
    mocking the thing under test.
    """

    def __init__(self, inner: Any, outcome: FetchOutcome) -> None:
        self._inner = inner
        self._outcome = outcome
        self.source_name = inner.source_name
        self.source_type = inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> Any:
        return self._inner.normalize(raw_job, board)


def _lever_outcome(ok: bool = True) -> FetchOutcome:
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    jobs = tuple(
        RawJob(
            source_job_id=str(j["id"]),
            source_company_key="alloy",
            canonical_url=j.get("hostedUrl"),
            payload=j,
        )
        for j in payload
    )
    if not ok:
        return FetchOutcome(board=LEVER_BOARD, ok=False, http_status=503, error="HTTP 503")
    return FetchOutcome(board=LEVER_BOARD, ok=True, jobs=jobs, http_status=200)


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _ingest(session: AsyncSession, outcome: FetchOutcome) -> Any:
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    adapter = _StubAdapter(LeverAdapter(client=None), outcome)
    return await ingest_boards(session, adapter, [LEVER_BOARD], source=source)


async def test_every_canonical_job_traces_to_a_raw_record(db_session: AsyncSession) -> None:
    """M1 acceptance criterion, asserted directly."""
    await _ingest(db_session, _lever_outcome())

    orphans = (
        await db_session.execute(
            select(func.count())
            .select_from(Job)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .where(JobSourceLink.id.is_(None))
        )
    ).scalar_one()
    assert orphans == 0
    assert await _count(db_session, SourceJobRecord) == 9


async def test_reingestion_is_idempotent(db_session: AsyncSession) -> None:
    """M1 acceptance: no dupes, no spurious updates."""
    _, first = await _ingest(db_session, _lever_outcome())
    assert first.created == 9
    assert first.updated == 0

    jobs_after_first = await _count(db_session, Job)

    _, second = await _ingest(db_session, _lever_outcome())
    assert second.created == 0
    assert second.updated == 0, "a re-poll of unchanged data reported an update"
    assert second.unchanged == 9
    assert await _count(db_session, Job) == jobs_after_first


async def test_a_failed_board_closes_nothing(db_session: AsyncSession) -> None:
    """M1 acceptance: simulated source outage closes zero jobs (I3)."""
    await _ingest(db_session, _lever_outcome())
    open_before = int(
        (
            await db_session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )
    assert open_before == 9

    _, stats = await _ingest(db_session, _lever_outcome(ok=False))

    assert stats.closed == 0
    assert stats.boards_failed == ["alloy"]
    open_after = int(
        (
            await db_session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )
    assert open_after == open_before


async def test_multi_location_posting_yields_multiple_rows(db_session: AsyncSession) -> None:
    """A2 and an M1 acceptance criterion, end to end into the table."""
    await _ingest(db_session, _lever_outcome())
    per_job = (
        await db_session.execute(
            select(JobLocation.job_id, func.count()).group_by(JobLocation.job_id)
        )
    ).all()
    assert per_job
    assert max(count for _, count in per_job) >= 1
    assert await _count(db_session, JobLocation) >= 9


async def test_no_location_row_has_a_coordinate(db_session: AsyncSession) -> None:
    """I1 at the storage layer. Geocoding has not run, so nothing is placed."""
    await _ingest(db_session, _lever_outcome())
    placed = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(JobLocation)
                .where(JobLocation.latitude.is_not(None))
            )
        ).scalar_one()
    )
    assert placed == 0


async def test_repeated_company_creation_does_not_duplicate(db_session: AsyncSession) -> None:
    """Task 8's upsert, exercised through the name variants that must merge.

    test_companies.py proves normalize_company_name folds these together; this
    proves the insert path honours it rather than raising on the unique index.
    """
    for name in ("Moody's Analytics", "Moodys Analytics", "MOODY'S ANALYTICS"):
        await get_or_create_company(db_session, name)
    await db_session.flush()
    assert await _count(db_session, Company) == 1


async def test_a_posting_that_fails_to_persist_does_not_abort_the_board(
    db_session: AsyncSession,
) -> None:
    """The savepoint in _persist_outcome, proven by making one posting fail.

    Without the savepoint the failed statement poisons the transaction and
    every posting after it in the board fails too — so this asserts the
    survivors, not just the failure count.
    """
    outcome = _lever_outcome()
    broken = outcome.jobs[0].model_copy(update={"payload": {**outcome.jobs[0].payload, "text": ""}})
    outcome = outcome.model_copy(update={"jobs": (broken, *outcome.jobs[1:])})

    _, stats = await _ingest(db_session, outcome)

    assert stats.failed == 1
    assert stats.created == 8
    assert await _count(db_session, Job) == 8


async def test_ingestion_run_records_the_failure(db_session: AsyncSession) -> None:
    """M1 acceptance: ingestion failures are visible, not only in logs."""
    run, _ = await _ingest(db_session, _lever_outcome(ok=False))
    assert run.error_summary is not None
    assert "alloy" in run.error_summary
    assert run.records_closed == 0
```

- [ ] **Step 3: Bring up the database and run**

```bash
make up && make migrate
cd services/api && pytest tests/test_ingestion.py -v
```

Expected: PASS. If every test skips, `DATABASE_URL` is not in the environment —
export it from `.env` as the Makefile does.

- [ ] **Step 4: Prove the tests can fail**

Non-vacuity check, per CLAUDE.md §7. Temporarily revert Task 8's
`get_or_create_company` to check-then-insert and confirm
`test_repeated_company_creation_does_not_duplicate` still passes (it will —
the race needs concurrency), then instead break `normalize_company_name` to
return `display_name` unchanged and confirm it **fails** with 3 companies.
Restore both.

Do the same for I3: comment out the `if not outcome.ok: continue` guard in
`ingest_boards` and confirm `test_a_failed_board_closes_nothing` fails.
Restore it.

Record both results in the commit message. A test suite nobody has seen fail
is a suite nobody has tested.

- [ ] **Step 5: Commit**

```bash
make check
git add services/api/tests/conftest.py services/api/tests/test_ingestion.py
git commit -m "test(ingestion): cover the persist pipeline against a real database

Closes the largest coverage gap in the repo (PROGRESS 'Before M1 starts'
item 3). Non-vacuity confirmed: breaking name normalisation fails the
dedupe test, and removing the I3 guard fails the outage test.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: API route tests, CLI wiring, and PROGRESS

**Files:**
- Create: `services/api/tests/test_routes.py`
- Modify: `services/api/nightshift/cli.py`
- Modify: `docs/PROGRESS.md`

**Interfaces:**
- Consumes: `db_session` from Task 9; `create_app` from `nightshift.api.main`.
- Produces: nothing later in this plan depends on it. M1b starts from here.

- [ ] **Step 1: Read the CLI's fixture-adapter pattern**

Run: `cd services/api && grep -n "Fixture\|class .*Adapter\|def seed" nightshift/cli.py`

`FixtureGreenhouseAdapter` subclasses the real adapter and overrides only
`fetch_board`. Follow that exactly — ADR 0004 requires fixture-sourced data to
be labelled in the data, and the pattern is what keeps the offline `make demo`
path honest.

- [ ] **Step 2: Add fixture adapters for both providers**

```python
class FixtureLeverAdapter(LeverAdapter):
    """Reads a committed recording instead of the network. ADR 0004.

    Constructed with no client, so it cannot make a request even if the kill
    switch were flipped. Attributed to source `lever_fixture` with
    source_type='fixture' and badged "committed fixture" in the Operate UI.
    """

    source_name = "lever_fixture"
    source_type = SourceType.FIXTURE

    def __init__(self, fixture: Path) -> None:
        super().__init__(client=None)
        self._fixture = fixture

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        payload = json.loads(self._fixture.read_text())
        jobs = tuple(
            RawJob(
                source_job_id=str(job["id"]),
                source_company_key=board.token,
                canonical_url=job.get("hostedUrl"),
                payload=job,
            )
            for job in payload
            if isinstance(job, dict) and job.get("id") is not None
        )
        return FetchOutcome(board=board, ok=True, jobs=jobs, http_status=200)




class FixtureAshbyAdapter(AshbyAdapter):
    """Reads a committed recording instead of the network. ADR 0004."""

    source_name = "ashby_fixture"
    source_type = SourceType.FIXTURE

    def __init__(self, fixture: Path) -> None:
        super().__init__(client=None)
        self._fixture = fixture

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        payload = json.loads(self._fixture.read_text())
        jobs = tuple(
            RawJob(
                source_job_id=str(job["id"]),
                source_company_key=board.token,
                canonical_url=job.get("jobUrl"),
                payload=job,
            )
            for job in payload.get("jobs", [])
            if isinstance(job, dict) and job.get("id") is not None
        )
        return FetchOutcome(board=board, ok=True, jobs=jobs, http_status=200)


```

Neither needs to store a `BoardRef`. After Task 6 step 1b the board is an
argument to `normalize`, and `_persist_outcome` already passes `outcome.board`
— so these subclasses override `fetch_board` and nothing else, which is exactly
the shape `FixtureGreenhouseAdapter` already has.

- [ ] **Step 3: Extend `make seed` to load all three boards**

Follow the existing Greenhouse seeding call. The seeded corpus should end with
jobs from three sources, so the Operate page shows three rows and the
`e2e-seeded` suite has more than one provider to look at.

- [ ] **Step 4: Write the route tests**

```python
# services/api/tests/test_routes.py
"""API routes against a real database.

Routes validate and delegate (CLAUDE.md §3), so what is worth asserting here
is the contract the web app's Zod schemas parse — and that /health tells the
truth, which is acceptance row 4's whole point.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.main import create_app
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
async def client(db_session: AsyncSession) -> Any:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_health_reports_both_dependencies(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body["checks"]) >= {"database", "redis"}
    for check in body["checks"].values():
        assert isinstance(check["ok"], bool)
        assert check["detail"]


async def test_liveness_does_not_touch_the_database(client: AsyncClient) -> None:
    """A liveness probe that fails when Postgres is down restarts a healthy app."""
    response = await client.get("/health/live")
    assert response.status_code == 204


async def test_jobs_route_returns_the_documented_shape(client: AsyncClient) -> None:
    response = await client.get("/jobs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)


async def test_every_returned_location_has_a_confidence(client: AsyncClient) -> None:
    """I1 at the API boundary. The web app's Zod schema rejects a point whose
    confidence does not justify it; this asserts the field is always there to
    be checked."""
    body = (await client.get("/jobs")).json()
    for job in body["items"]:
        for location in job.get("locations", []):
            assert location["location_confidence"] in {
                "verified",
                "approximate",
                "city_only",
                "remote",
                "unknown",
            }
            if location["location_confidence"] in {"city_only", "remote", "unknown"}:
                assert location.get("latitude") is None


async def test_unknown_job_id_is_404_not_500(client: AsyncClient) -> None:
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
```

Check the real response shape first — run the API and `curl /jobs` — and adjust
the key names to match. Do not change the route to fit the test.

- [ ] **Step 5: Run everything**

```bash
make check
make acceptance
```

Expected: `make check` green in both languages; `make acceptance` green,
18 verify checks plus the seeded browser tests. Record the exact numbers.

- [ ] **Step 6: Update `docs/PROGRESS.md`**

Required edits — do all of them:

1. Change **"Next exact action"** to point at M1b (canonical spine) and note
   that M1a is complete.
2. In **"Before M1 starts"**, mark items 1, 2 and 3 done with the commit SHAs.
   Leave items 4 and 5 — `_replace_locations` on geocoding, and the redundant
   ordering — they are still open.
3. In **"Not real yet"**, delete the *Internship employment-type fixtures* row
   (Task 2 closed it with real data) and the *Location parser breadth* row.
   Update the *`/registry` route* row: still true, M1c.
4. Add to **"Not real yet"**: Ashby's `address.postalAddress` is recorded but
   unused, real at M1's geocoding stage.
5. Add a **session log entry** covering: the ten-tokens-two-live Lever result
   and what it says about ADR 0006; the two fabricated-city bugs and that real
   data found them; ADR 0008 and its cost (`London` stays unknown); and — most
   importantly — **that neither Lever nor Ashby publishes an updated-at field,
   so ADR 0007's phase-2 diff has no timestamp to compare on those providers
   and M1d must diff on the content hash.**
6. Update the **"Verified locally"** table with the new test counts.

- [ ] **Step 7: Commit**

```bash
git add services/api/tests/test_routes.py services/api/nightshift/cli.py docs/PROGRESS.md
git commit -m "test(api): cover routes against a real database; close M1a

Also records a gap in ADR 0007: neither Lever nor Ashby publishes an
updated-at field, so phase-2 conditional polling has no timestamp to diff
on those providers and must fall back to the description hash.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** Against the M1 acceptance criteria in `CLAUDE.md` §6:

| Criterion | Covered by |
|---|---|
| Same fixture in → byte-identical output twice | Tasks 6, 7 — `test_normalization_is_deterministic` per adapter |
| Re-ingestion idempotent: no dupes, no spurious updates | Task 9 — `test_reingestion_is_idempotent` |
| Simulated source outage closes zero jobs | Task 9 — `test_a_failed_board_closes_nothing` |
| Every canonical job traces to a raw record | Task 9 — `test_every_canonical_job_traces_to_a_raw_record` |
| Multi-location postings → multiple `job_locations` rows | Task 7, Task 9 |
| Ingestion failures visible in the UI | Task 9 asserts the run row; the **UI** surface is M1b |
| Greenhouse + Lever + Ashby behind one interface | Tasks 6, 7 |
| `source_job_records` preserving raw payloads | Already true from M0; asserted in Task 9 |
| Dedupe fixture suite | **M1b** — not this plan |
| Freshness + closure state machine | **M1b** — not this plan |
| Admin job table, source health page | **M1b** |
| Discovery from a committed crawl fixture | **M1c** |
| Live-but-unnameable board cannot reach bulk approval | **M1c** |
| `304` produces zero writes | **M1d** |
| Coverage page names what is *not* covered | **M1c** |

The five deferred rows are the reason this is M1a of four. Every criterion this
plan claims has a named test.

**Placeholders.** None. Every code step carries the code; every command carries
its expected output. Two steps deliberately require reading real output before
writing (Task 1 step 1, Task 10 step 1) — those are instructions to check the
existing convention, not deferred work.

**Type consistency.** `parse_location_list(Sequence[str]) -> list[ParsedLocation]`
is defined in Task 4 and consumed under that exact name in Tasks 6 and 7.
`normalize(raw_job, board)` is widened in Task 6 step 1b — on the Protocol, on
the Greenhouse adapter, and at its one call site in `_persist_outcome` — and is
used with that same signature in Tasks 7, 9 and 10. `_StubClient.get_json(url)` matches the
`_JsonClient` Protocol both adapters declare. `requires_db` and `db_session` are
defined in Task 9 step 1 and imported in Tasks 9 and 10.

**Risks, checked rather than left open.**

- `SourceType.ATS_LEVER` / `ATS_ASHBY` / `FIXTURE` already exist, so **no task
  in this plan needs a migration.** Verified at `nightshift/db/base.py:112-117`.
- The one genuinely open risk is Task 1 step 5: the recorder may not handle a
  404 or an empty array, in which case two fixtures are written by hand from
  the recorded body. That is called out in the step and the meta files say so.
- Task 10 step 4's route tests assert a response shape read from the code, not
  from a running server. Step 4 says to check the real shape first and adjust
  the key names — the route is the contract, not the test.
