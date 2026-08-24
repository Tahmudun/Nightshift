# M5 — The Open Hand: the four criteria, walked

`CLAUDE.md` §6 gives M5 four acceptance criteria. The four slices — M5a, M5b,
M5c, M5d — each walked their own, and the milestone's were never walked as a
set. This is that walk, done on `main` at `079749b` after PR #21 merged.

**One of the four failed, and the failure is the reason this document is worth
having.** The map half of criterion 2 had been true in the way a thing is true
when nobody has checked it: a captured posting did reach the map, and the map
had no way of knowing it was captured. It is fixed here, tested three ways, and
each test was watched fail before it was believed.

**The gates, on the final tree.** `make acceptance` **exits 0**: `test-e2e` 32
collected / **30 passed**, `verify` **all checks passed**, `test-e2e-seeded`
**93 passed, 1 skipped** — up from 92, the new one being the browser test that
closes criterion 2.

> **On the word "sabotage" below.** Every new guard in this walk was broken on
> purpose, run, and watched go red, with the exact failure message recorded. A
> test that has never failed is a test nobody has any reason to trust — the
> lesson `m5c-claude-desktop` recorded and this walk applies rather than
> restates.

---

## Criterion 1 — two users cannot see each other's data, proved by a test shown able to fail

**Met.** `services/api/tests/test_two_users_cannot_see_each_other.py`, **94 tests,
all passing**, and shown able to fail twice.

The test does not spot-check three routes. It reads the application's own route
table out of its OpenAPI schema and requires every route to carry a
classification, so a route added in a later milestone with no isolation decision
turns CI red rather than passing quietly. Two independent guards are asserted
separately: the default-deny wiring in `main.py`, and the per-route ownership
filters. The universal assertion is a substring scan of the whole response body
for any UUID belonging to the other person — not a field check, because a field
check only inspects the fields somebody thought of.

### Sabotage A — the ownership filter

Removed `Application.user_id == user_id` from the single loader in
`api/routes/applications.py:79`, the helper whose docstring reads *"One loader,
so no route can forget the user filter (A3)."*

**7 of 94 failed.** The leak scan on the read:

```
AssertionError: GET /applications/{application_id} returned 200 and its body
contains identifiers belonging to the other person:
['22e31130-b552-47c7-876b-dee28e0435ae']
```

and — worse, and the reason the write cases are in the suite at all — a write
that *succeeded* against another person's record:

```
AssertionError: POST /applications/{application_id}/interviews answered 201 for
a record belonging to somebody else. 404 is the correct answer: 200 is a leak,
and 403 confirms the record exists, which is itself B's business.
```

That second one is not a disclosure, it is an unauthorised write, and only the
enumeration found it: a suite that checked "can A read B's application?" would
have reported one failure and left six.

### Sabotage B — the default-deny wiring

Replaced `app.include_router(router, dependencies=[protected])` with
`app.include_router(router)` in `api/main.py:93`.

**12 of the 43 protected routes answered a stranger**, and *which* twelve is the
finding:

```
AssertionError: GET /jobs answered an anonymous request with 200: {"items":[…
AssertionError: GET /companies answered an anonymous request with 200: {"items":[…
AssertionError: GET /stats answered an anonymous request with 200: …
```

The other thirty-one still 401'd, because their handlers declare `CurrentUserId` and
would refuse on their own. So the router-level guard is load-bearing for exactly
the shared-corpus routes — `/jobs`, `/companies`, `/registry`, `/stats` and the
rest — which have no user parameter to protect them and would otherwise be the
quiet exception. ADR 0037's argument, measured.

Both sabotages reverted; the tree is clean and the suite is back to **94 passed**.

---

## Criterion 2 — a pasted posting appears on the map with a capture badge; pasting it twice creates no duplicate

**The second half was met. The first half was not, and is now.**

### Idempotence — met before this walk

`test_capture.py::test_capturing_the_same_posting_twice_creates_one_job`,
`capture_paste`'s fingerprint index (`ix_captured_postings_user_id_fingerprint`,
migration 0027), and `e2e-seeded/capture.spec.ts::a paste is a proposal, and
pasting it twice is still one proposal`. Nothing was owed here.

### The map — not met, and found by looking rather than by reading

PROGRESS flagged this half as *"the part most likely to be assumed rather than
seen"*. It was right.

**What was actually true.** The confirmed capture in the dev database — a real
Jump Trading internship, captured through Claude Desktop and confirmed by hand —
did reach `/city/signals`:

```
$ curl -s .../city/signals | …
counts: {'building': 20, 'area': 0, 'unresolved': 12, 'total': 32}
captured job present: True
  placement.kind            'unresolved'
  placement.location_confidence  'unknown'
```

Unresolved and floating, which is I1 behaving exactly as designed — its employer
has no confirmed office, so the map refuses to put it on a building.

**What was not true.** The `CitySignalOut` payload carried no provenance field
at all. Nothing downstream could distinguish that role from the thirty-one a
poller found, and `CityDetail.tsx` — the only thing the map says about a
selected role — had no badge. The `added by hand` badge existed on
`/explore/jobs/[id]` and nowhere else: **one click away, which is not the map.**

Worse than the missing badge, the panel told a reader something false. For every
role, captured or polled, it printed:

> First seen by ingestion 3 days ago.

Ingestion never saw the captured one. A person pasted it, and nothing re-reads
it, so that date does not mean what the same words mean one row above.

### The fix

1. **`CitySignalOut.captured: bool`** (`api/schemas.py`), computed by
   `_captured()` in `api/routes/city.py` — one grouped query over
   `JobSourceLink → SourceJobRecord → Source` for `manual_capture`, the same
   join `/jobs/{id}` already uses for its own badge. **Recorded fact, not
   inference**, which is the line ADR 0039 §5 draws: *whether* a posting arrived
   by hand is written down; *which website* it came from is not, and the map
   claims only the first.
2. **`citySignalSchema.captured: z.boolean()`** — required, not defaulted.
   A default would let the server drop the field and the map would render every
   captured role as polled, silently and forever.
3. **The badge in `CityDetail.tsx`**, gold, with the same words as `JobDetail`,
   and the "first seen" line replaced for a capture with *"Pasted in and
   confirmed … Nothing re-reads it, so it will not age or close on its own."*

### The evidence, at three levels

| Level | Test | Shown able to fail by |
|---|---|---|
| API, real DB | `test_city_routes.py::test_a_captured_role_reaches_the_map_saying_it_was_added_by_hand` | hard-wiring `captured=True` |
| Component | `CityDetail.test.tsx::a role somebody pasted in says so, on the map` (3 tests) | rendering the badge unconditionally |
| Browser, real corpus | `e2e-seeded/city.spec.ts::a posting somebody pasted in is on the map, and the map says so` | the polled control in the same run |

**Every one of them carries a polled control**, because that is the assertion
that catches the likeliest regression. A badge rendered unconditionally passes
the captured case and puts "added by hand" on the whole corpus. The API
sabotage proves the control works:

```
AssertionError: roles nobody pasted came back marked as added by hand:
['Enterprise Account Executive', 'Senior Customer Success Manager',
 'Senior Customer Success Manager', 'Customer Success Manager',
 'Mid-Market Account Executive', … ]
```

and the component sabotage:

```
AssertionError: expected <span …(2)></span> to be null
```

A fourth guard, in `schemas.test.ts`, refuses a signal that does not say whether
it was pasted in — so the server and the client cannot drift apart without Zod
saying so.

**The browser test is the one that closes the criterion**, because it is the
only one that runs the two halves against each other through a real payload, a
real Zod parse and a real page — the confirmed capture `make seed` plants
through `create_capture` and `confirm_capture`:

```
✓ 35 [chromium] › e2e-seeded/city.spec.ts:1029:5 ›
     a posting somebody pasted in is on the map, and the map says so (8.8s)
```

It asserts the role is in the instance buffer (on the map at all), that the
panel carries the badge, that it says *"Pasted in and confirmed"* rather than
*"First seen by ingestion"*, and then selects a polled role on the same page and
requires the badge to be absent.

---

## Criterion 3 — no parsed fact is stored as confirmed without a user action

**Met, at three levels, and one of them is new.**

**The database.** `ck_captured_postings_confirmed_rows_carry_a_job` and
`ck_captured_postings_decided_rows_carry_a_time` make the pairing structural:
a `pending` row cannot carry a job and a `confirmed` row cannot lack one.
`test_capture.py::test_the_schema_refuses_a_pending_capture_that_carries_a_job`
asserts it by watching the database raise, which is the level no code path can
route around.

**The application.** `test_a_capture_creates_no_job_until_it_is_confirmed`:
after a paste, `status` is `pending`, `job_id` is `None`, `decided_at` is `None`,
the proposal is stored, and `Job` count is `0`. Every parsed field lives in a
`proposed_*` column and confirmation takes *the reader's* values, not the
parser's — ADR 0039 §2 — so a bad parse stays diagnosable after the correction
has overwritten it in every other sense.

**The interface.** The form has three exits, not two. `Decide later`
(`CapturePosting.tsx:457`) exists because *"an unsure person pressed for a
decision is exactly who accepts a wrong employer"*, and all four seeded e2e
tests leave by it.

### What was missing: the surface most likely to erode

`capture_posting`'s tool description tells the model *"You cannot confirm it
yourself. There is no tool for that, and its absence is deliberate."* **Prose is
not a guard.** Nothing in the suite would have noticed a `confirm_capture` tool
added in a later milestone by somebody reading the review queue as a chore
rather than as the consent step.

Two tests now close that, in `test_mcp_server.py`, in the shape M5b established:

- `test_every_tool_is_classified_and_none_of_them_decides` — enumerates the
  registered tools and requires each to be filed as `reads` or `proposes`.
  **There is deliberately no third kind**; adding one means editing a comment
  that says so, which is an argument somebody has to make in a diff.
- `test_the_capture_tool_tells_the_model_it_cannot_confirm` — a surface can be
  correct and still mislead. A tool that writes only `pending` rows but is
  described so a model announces *"I've added it to Nightshift"* leaves the
  reader believing a decision was made that was not.

Both sabotaged:

```
AssertionError: these tools have no entry in `_TOOL_KINDS` — add one, and note
that 'decides' is not an available kind (I5): ['get_job']

AssertionError: assert 'cannot confirm it yourself' in "save a job posting the
reader found somewhere nightshift does not ingest — …"
```

---

## Criterion 4 — Claude Desktop connects and captures a posting end to end

**Met, twice, by walks already recorded.**

`docs/reviews/milestone-5c-desktop-walk.md` closed the client deviation: real
Claude Desktop, its own config file, its restart cycle and its error surface —
and found a runbook defect that destroyed data on the way.
`docs/reviews/milestone-5d-walk.md` is the end-to-end one: a real LinkedIn
posting captured in Claude Desktop on 2026-08-24, appearing in the review queue
on a screen the browser had never created it from, confirmed by a person, and
reaching the corpus through the ordinary pipeline — `employment_type`
`internship`, `remote_policy` `on_site`, one `job_locations` row, corpus 32 → 33.

**Its stated limit stands and is not re-argued here.** The reader's report that
the model led with the corpus check and called the capture a proposal is
recorded as their report, because the transcript was not captured. Capturing it
costs nothing during and is unrecoverable after.

---

---

## The gate that could not be run, and why — a trap worth naming

`make acceptance` failed at `test-e2e` with **all six tests in
`e2e/city-acceptance.spec.ts` red**, each waiting ninety seconds for a `Reset
view` button that never appeared. None of it was the code.

**It was not a flake, and the first instinct was wrong.** PROGRESS already
records this file flaking on this machine under parallelism, so "known flake"
was the available explanation and it was available too cheaply. Two things
ruled it out: the failures were *all six*, not a shifting subset, and they
reproduced at `--workers=1`.

**The page under test was the sign-in form.** Playwright's own error context
shows it — `heading "Sign in"`, an email box and a password box where New York
should be.

**The mechanism, measured rather than reasoned about:**

```
$ curl -o /dev/null -w "%{http_code}" localhost:3000/api/ns/auth/me   # API alive
401
$ curl -o /dev/null -w "%{http_code}" localhost:3100/api/ns/auth/me   # API absent
500
```

`SessionGate.tsx:63` is `if (isError) return <>{children}</>;` — *"an
unreachable API renders the application anyway"*, a decision made deliberately
in M5b and correct. So a **401** means "the API is up and you are nobody" and
gives you the sign-in form; a **500** means "there is no API" and gives you the
city. The degraded suite's whole premise, in its config's own words, is that
*"the API is deliberately absent"*.

**Nothing enforces that premise.** `playwright.config.ts` sets
`reuseExistingServer: !process.env.CI`, so locally the suite happily attaches to
a dev server that has an API behind it — and then every city test asserts
against a login screen. In CI there is no API, so CI is green and the trap is
invisible there.

**What was actually reachable here**: a `uvicorn` and a `next dev` left running
by an *earlier automated session* — `nohup`'d, orphaned, and serving
pre-change code. Stopping them:

```
$ npm exec -- playwright test e2e/city-acceptance.spec.ts --workers=2
  6 passed (1.9m)
```

**This is `CLAUDE.md` §4's F5 lesson arriving from the other side.** The rule
was written as *"a server you started by hand an hour ago will make a broken
target look like a passing one"*. Here it made a passing target look broken, for
an hour, in a way that mimicked a documented flake closely enough to be
explained away. Q8's advice — stop `make dev`, check `lsof -ti:3000 -ti:8000` —
is the right check and it is filed under the wrong problem: it is not only about
databases and competing pytest runs.

**It is worth fixing rather than remembering**, and it is not fixed here because
it is the e2e harness rather than M5. The shape: `test-e2e` should refuse to run
when something is listening on the API port, and say why. A gate whose result
depends on an invisible property of the machine is a gate that teaches people to
re-run it rather than read it — which is the exact sentence already in that
config, about workers.

---

## What this walk did not close

- **The confirm step's error surface.** A bare `Internal Server Error` from
  `api.ts:132` is what a reader gets when the confirm 500s, with no next step.
  M5d walk §3. Still owed.
- **Q8 now has a named culprit, and it is one line.** The question has been
  billed three times without the mechanism being pinned down, so: **the
  `db_session` fixture is innocent.** It truncates *inside* a transaction it
  rolls back (`conftest.py`'s own docstring says so, and it is true), and the
  dev rows survive it.

  What does not roll back is
  `tests/test_merge_concurrency.py::_cleanup`:

  ```python
  async with maker() as session, session.begin():
      await session.execute(text(f"TRUNCATE TABLE {', '.join(_INGESTION_TABLES)}"))
  ```

  `session.begin()` **commits**. That list is twenty-one tables and it includes
  `captured_postings`, `jobs`, `companies`, `company_locations` and
  `applications` — so every `make check` permanently destroys the confirmed
  captures, the hand-typed office addresses from Q7, and the application
  pipeline. The helper is not wrong to clean up after itself: it commits its
  fixtures deliberately, because the two contending sessions it tests have to
  see them, and it cannot use the rolled-back fixture for that reason. It is
  wrong to clean up with an unscoped `TRUNCATE` of the whole corpus when it
  created three rows it can name.

  This is a diagnosis, not a fix — Q8 asks the human a *separate test database*
  question, which is the better answer and theirs to make. But the next session
  should not have to re-find this.
- **Q11** (nothing rate-limits sign-in) and **Q9** (the sky) are open.
- **The beacon itself is not marked.** The badge is on the panel that describes
  a selected role, not on the mesh drawn in the field. A person scanning the
  city cannot see which roles were pasted in without selecting them. That is a
  visual-system question and it belongs with M6's field work, not here.
