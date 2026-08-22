# M5d — Assisted capture from LinkedIn and Indeed

> **Executors:** tasks are checkboxes. Each ends in a runnable, testable state
> and its own commit. `CLAUDE.md` §5 governs; this plan does not override it.

**Goal:** Make the path *"I found this on LinkedIn"* → *"it is in my review
queue, correctly, once, and not a duplicate of a job Nightshift already has"*
work well enough that a person would choose it over typing.

**Architecture:** Nothing new is deployed and nothing new is fetched. M5c's MCP
server already carries `capture_posting`; M5d makes that one tool honest about
four things it currently is not — who read the page, whether the text has been
seen before, whether the corpus already holds the job, and where the reader
found it. The server's boundary with LinkedIn and Indeed stays exactly where
`board-discovery.md` §9 put it: **outside**.

**Tech stack:** no additions. FastAPI + SQLAlchemy + Alembic, the existing MCP
SDK server, Next.js for the review surface.

**Spec:** `AMENDMENTS` A16 (the re-cut, and the four-asks-are-one-server
insight), `docs/architecture/board-discovery.md` §9 (why LinkedIn and Indeed
are never crawled), ADR 0038 (the MCP server's shape), `docs/PROGRESS.md`
"Next exact action". Decisions taken here land in **ADR 0039**.

---

## Global constraints

- **Nightshift's server never issues a request to `linkedin.com`,
  `indeed.com`, or any host named in a `source_url`.** The reader's own browser
  and the reader's own Claude session are the only things that ever load those
  pages. This is `CLAUDE.md` §8 and `board-discovery.md` §9, and M5d is only
  legitimate because it does not bend it. Task 1 makes it a test.
- **User-initiated and session-bound, never a poller.** No schedule, no queue,
  no background task touches a captured URL. `PROGRESS.md` line 1445.
- **I1 holds through the side door.** `domain/capture.py`'s module docstring is
  the reason this milestone has a confirmation step at all: a misparsed
  employer becomes a real beacon on somebody else's building. Every field M5d
  adds is a *proposal* and none of them shortens the confirm step.
- **I2's shape, applied to job data.** Anything inferred is stored as a
  proposal and never promoted without an explicit user action. M5d adds a
  second proposer — the reader's Claude — and it gets no more authority than
  the parser, only different failure modes.
- **I7.** Every new field is real or absent. No field is populated with a
  plausible value to make a screenshot look complete.
- A guard must exercise the thing that runs. This is the lesson `m5c-claude-desktop`
  paid for twice; every test below names the sabotage that must turn it red.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `services/api/tests/test_capture_never_fetches.py` | **new.** The boundary, as a test | 1 |
| `docs/adr/0039-*.md` | **new.** The four decisions | 1, 6 |
| `services/api/nightshift/domain/capture_assist.py` | **new.** The assistant's proposals, and the quoting rule that gates them | 2 |
| `migrations/versions/*_capture_assist.py` | **new.** `assistant_*`, `assistant_rejected_fields` | 2 |
| `migrations/versions/*_capture_fingerprint.py` | **new.** `text_fingerprint` + backfill | 3 |
| `services/api/nightshift/domain/capture_matches.py` | **new.** "Nightshift already has this" | 4 |
| `services/api/nightshift/domain/capture.py` | modify: `create_capture` takes assistant fields and a fingerprint; `capture_origin` derived | 2, 3, 5 |
| `services/api/nightshift/api/routes/capture.py` | modify: accepts assistant fields, returns idempotently, returns matches | 2, 3, 4 |
| `services/api/nightshift/api/schemas.py` | modify: `CaptureIn`, `CaptureOut` | 2, 3, 4 |
| `services/api/nightshift/db/models.py` | modify: `CapturedPosting` columns | 2, 3 |
| `services/api/nightshift/mcp/server.py` | modify: `capture_posting` args + description | 2, 3, 4 |
| `services/api/nightshift/mcp/shapes.py` | modify: `capture_proposal` reports refusals, repeats, matches | 2, 3, 4 |
| `apps/web/src/components/CapturePosting.tsx` | modify: origin, provenance per field, duplicate candidates | 5 |
| `apps/web/src/lib/schemas.ts` | modify: the capture schema | 5 |
| `docs/reviews/milestone-5d-review.md` | **new** | 6 |
| `docs/runbooks/capturing-from-a-job-board.md` | **new.** What the reader actually does | 6 |

---

## Task 1 — The boundary, as a test rather than a comment

`captured_postings.source_url` carries the comment *"Never fetched — see the
class note."* Nothing enforces it, and M5d is the milestone where a reader
starts handing this server LinkedIn URLs by the dozen. A comment is the weakest
possible guard on the one rule that makes this milestone legal.

**Files:**
- Create: `services/api/tests/test_capture_never_fetches.py`
- Create: `docs/adr/0039-the-page-is-read-by-the-reader-not-by-us.md` (§1 only; the rest lands in task 6)

**Interfaces:** produces nothing importable. It constrains everything below it.

- [ ] **1.1** Write the failing test. It installs a transport that raises on any
      outbound HTTP, then drives the whole capture lifecycle — `POST /capture`
      with a LinkedIn `source_url`, `GET /capture/{id}`, `POST
      /capture/{id}/confirm` — and asserts all three succeed.

```python
async def test_the_capture_path_never_dereferences_a_source_url(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached: list[str] = []

    async def refuse(self: httpx.AsyncClient, request: httpx.Request, **kw: object) -> object:
        reached.append(str(request.url))
        raise AssertionError(f"the capture path reached the network: {request.url}")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)

    created = await client.post(
        "/capture",
        json={
            "raw_text": "Staff Software Engineer\nRamp · New York, NY (Hybrid)\nAbout the job…",
            "source_url": "https://www.linkedin.com/jobs/view/4012345678/",
        },
    )
    assert created.status_code == 201
    capture_id = created.json()["id"]
    assert (await client.get(f"/capture/{capture_id}")).status_code == 200
    confirmed = await client.post(
        f"/capture/{capture_id}/confirm",
        json={
            "title": "Staff Software Engineer",
            "company_name": "Ramp",
            "location_text": "New York, NY",
            "employment_type": "unknown",
        },
    )
    assert confirmed.status_code == 200
    assert reached == []
```

- [ ] **1.2** Run it. It should **pass** on today's code — this is a
      characterisation test, not a red-green cycle, and a test that starts
      green is worthless until its sabotage is shown. Run:
      `make test-py PYTEST_ARGS="tests/test_capture_never_fetches.py -v"`

- [ ] **1.3** Sabotage `create_capture` with a real fetch of `source_url` and
      watch the test go red. Record the failure message in the test's module
      docstring so a future reader knows the guard has teeth. Revert the
      sabotage.

- [ ] **1.4** Second test in the same file: no module reachable from the
      capture request path names a job-board host as a fetch target. An AST
      scan over `nightshift/api/routes/capture.py`, `nightshift/domain/capture.py`
      and (from task 2 on) its siblings, asserting no string literal contains
      `linkedin.com` or `indeed.com` outside a docstring or a comment. Sabotage:
      add `BOARD = "https://www.linkedin.com"` to `capture.py`, see it go red.

- [ ] **1.5** Write ADR 0039 §1 — *the page is read by the reader, not by us* —
      with the rejected alternative stated plainly: a server-side fetch of
      `source_url` would give a far better parse and is forbidden, and the
      reason is not squeamishness but `robots.txt` saying `Disallow: /`.

- [ ] **1.6** `make check`, commit.

```bash
git add services/api/tests/test_capture_never_fetches.py docs/adr/0039-*.md
git commit -m "test(capture): the boundary with LinkedIn, as a test rather than a comment"
```

---

## Task 2 — An assistant may point, not paraphrase

Today the only reader of the pasted text is a line-based parser, and the
desktop walk proved what it does with prose: it declines every field. That is
the correct behaviour and it is a bad experience. The reader's Claude has
already read the page properly; it should be allowed to say what it saw.

The danger is exact and worth naming: **a model's proposal and a parser's
proposal look identical in a review form, and only one of them can invent a
company that was never on the page.** So the assistant's fields are stored
apart, labelled, and gated by one deterministic rule:

> **A field the assistant proposes must appear, verbatim, in the text the
> reader pasted.** Whitespace-collapsed and case-insensitive; nothing else.
> Quote, do not paraphrase. A field that fails is refused, and the refusal is
> reported back so the model can quote properly instead of arguing.

This is the same guarantee `resume_extractions`' span trigger gives I2, reached
with a check constraint's worth of code instead of a trigger, because a capture
is one short form rather than dozens of independently-accepted facts.

**Files:**
- Create: `services/api/nightshift/domain/capture_assist.py`
- Create: `services/api/tests/test_capture_assist.py`
- Create: `services/api/migrations/versions/<rev>_capture_assist.py`
- Modify: `services/api/nightshift/db/models.py` (`CapturedPosting`)
- Modify: `services/api/nightshift/domain/capture.py` (`create_capture`)
- Modify: `services/api/nightshift/api/schemas.py`, `api/routes/capture.py`
- Modify: `services/api/nightshift/mcp/server.py`, `mcp/shapes.py`
- Test: `services/api/tests/test_capture_routes.py`, `tests/test_mcp_capture.py`

**Interfaces:**
- Produces:
  - `ASSIST_FIELDS: tuple[str, ...] = ("title", "company_name", "location_text")`
  - `@dataclass(frozen=True, slots=True) class AssistantProposal: title: str | None; company_name: str | None; location_text: str | None`
  - `@dataclass(frozen=True, slots=True) class AssistantReading: accepted: AssistantProposal; rejected: tuple[str, ...]`
  - `def quotable(raw_text: str, value: str | None) -> bool`
  - `def read_assistant(raw_text: str, proposal: AssistantProposal) -> AssistantReading`
- Consumes: nothing from task 1.

- [ ] **2.1** Write `tests/test_capture_assist.py` failing, covering the rule
      and its edges:

```python
RAW = "Staff Software Engineer\nRamp · New York, NY (Hybrid)\n2 days ago · 34 applicants"


def test_a_quoted_field_is_accepted() -> None:
    reading = read_assistant(RAW, AssistantProposal(title="Staff Software Engineer"))
    assert reading.accepted.title == "Staff Software Engineer"
    assert reading.rejected == ()


def test_a_field_that_is_not_in_the_text_is_refused() -> None:
    reading = read_assistant(RAW, AssistantProposal(company_name="Stripe"))
    assert reading.accepted.company_name is None
    assert reading.rejected == ("company_name",)


def test_whitespace_and_case_do_not_decide_it() -> None:
    reading = read_assistant(RAW, AssistantProposal(title="staff   software\nengineer"))
    assert reading.accepted.title == "staff   software\nengineer"


def test_a_paraphrase_is_a_refusal_even_when_it_is_right() -> None:
    # "New York, NY (Hybrid)" is on the page; "New York, NY" is the model
    # tidying up. Correct, and still refused: the rule is quotability, and a
    # rule with an exception for values that look right is not a rule.
    reading = read_assistant(RAW, AssistantProposal(location_text="New York"))
    assert reading.accepted.location_text == "New York"  # substring of "New York, NY"
    reading2 = read_assistant(RAW, AssistantProposal(location_text="NYC"))
    assert reading2.rejected == ("location_text",)


def test_an_empty_or_blank_field_is_not_a_proposal() -> None:
    assert read_assistant(RAW, AssistantProposal(title="   ")).accepted.title is None
    assert read_assistant(RAW, AssistantProposal(title="   ")).rejected == ()
```

- [ ] **2.2** Run: `make test-py PYTEST_ARGS="tests/test_capture_assist.py -v"`.
      Expect `ModuleNotFoundError: nightshift.domain.capture_assist`.

- [ ] **2.3** Implement `capture_assist.py`. `quotable` collapses runs of
      whitespace to single spaces, casefolds, and asks `value in raw`. Blank is
      not a proposal (no rejection recorded). Length caps mirror
      `capture.py`'s `_MAX_TITLE_CHARS` / `_MAX_COMPANY_CHARS`.

- [ ] **2.4** Run the tests green. Commit the pure module alone — it has no
      database in it and it is the whole argument of the task.

```bash
git commit -m "feat(capture): an assistant may point, not paraphrase"
```

- [ ] **2.5** Add the columns to `CapturedPosting` with docstrings that say why
      they are separate from `proposed_*`:
      `assistant_title`, `assistant_company_name`, `assistant_location_text`
      (nullable, same widths as their `proposed_*` twins) and
      `assistant_rejected_fields` (JSONB, server default `'[]'`, holding **field
      names only, never the refused values** — storing the value would put a
      hallucinated company name in the database, which is the thing being
      prevented).

- [ ] **2.6** `make migration m="capture assist proposals"`, review the
      autogenerated file, then `make migrate` and `make drift`. Test the
      downgrade explicitly: `alembic downgrade -1 && alembic upgrade head`.

- [ ] **2.7** `create_capture` gains `assistant: AssistantProposal | None = None`,
      calls `read_assistant`, and stores both halves. `CaptureIn` gains an
      optional `assistant` object; `CaptureOut` gains `assistant` and
      `assistant_rejected_fields`. Route tests: a capture with a quoted
      assistant title stores it; one with an unquoted company stores null and
      names `company_name` in the rejected list; the `proposed_*` columns are
      untouched either way.

- [ ] **2.8** MCP: `capture_posting` gains `title`, `company_name`,
      `location_text` as optional arguments. The description must say, in the
      model's own second person, that these are **quotes from the text, not
      readings of it**, that a value not present verbatim will be refused, and
      that a refusal is reported rather than silently dropped. `shapes.capture_proposal`
      grows `assistant_accepted`, `assistant_refused`, and a sentence in
      `what_just_happened` explaining that a refused field means the quote did
      not match, not that the capture failed.

- [ ] **2.9** `tests/test_mcp_capture.py`: a tool call passing a company name
      absent from the text comes back with `company_name` in
      `assistant_refused` and the capture still created. Sabotage: make
      `read_assistant` accept everything and watch it go red.

- [ ] **2.10** `make check`, commit.

---

## Task 3 — Pasting the same thing twice

M5's acceptance says *"pasting it twice creates no duplicate."* That is true of
**jobs** — `capture_source_job_id` is content-derived and
`test_capture.py::test_capturing_the_same_posting_twice_creates_one_job` proves
it. It is not true of **proposals**: two `POST /capture` calls make two pending
rows, and the reader reviews the same LinkedIn posting twice. M5d is the
milestone that makes this common, because a model that is unsure whether the
last call went through will call again.

**Files:**
- Create: `services/api/migrations/versions/<rev>_capture_fingerprint.py`
- Modify: `db/models.py`, `domain/capture.py`, `api/routes/capture.py`,
  `api/schemas.py`, `mcp/shapes.py`
- Test: `services/api/tests/test_capture_routes.py`

**Interfaces:**
- Produces: `def text_fingerprint(raw_text: str) -> str` in `domain/capture.py`
  — sha256 hex of the whitespace-collapsed, casefolded text, 64 chars.
- Consumes: nothing.

- [ ] **3.1** Failing route test:

```python
async def test_pasting_the_same_posting_twice_returns_the_same_proposal(
    client: AsyncClient,
) -> None:
    body = {"raw_text": "Staff Software Engineer\nRamp · New York, NY", "source_url": None}
    first = await client.post("/capture", json=body)
    second = await client.post("/capture", json={**body, "raw_text": body["raw_text"] + "\n\n"})

    assert first.status_code == 201
    assert second.status_code == 200          # existing, not created
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["already_existed"] is True

    listed = await client.get("/capture")
    assert listed.json()["total"] == 1
```

      Plus three that pin the edges: a **different** posting still creates a
      second row; a repeat after the first was **confirmed** creates a new
      pending row (the reader is capturing it again on purpose, and the corpus
      check in task 4 is what tells them why that is redundant); and **another
      user** pasting identical text gets their own row, because a shared id
      would be an isolation leak.

- [ ] **3.2** Run it; expect the second POST to return 201 with a new id.

- [ ] **3.3** Add `text_fingerprint` (String(64), nullable at first) plus
      `Index("ix_captured_postings_user_id_fingerprint", "user_id", "text_fingerprint")`.
      Migration backfills existing rows in a Python loop over
      `SELECT id, raw_text`, then `alter_column(nullable=False)`. Downgrade
      drops index then column. Test both directions.

- [ ] **3.4** `create_capture` computes the fingerprint and first looks for a
      `PENDING` row with the same `(user_id, text_fingerprint)`, returning it
      untouched when found. Return `(capture, created: bool)` rather than a
      bare capture, so the route can pick its status code and the caller cannot
      accidentally read "found" as "created".

- [ ] **3.5** Route returns 200 + `already_existed: true` on a repeat, 201
      otherwise. `shapes.capture_proposal` says it in words — *"this is the
      proposal created N minutes ago, not a second one"* — because a model
      told only `already_existed: true` will still report "captured!" twice.

- [ ] **3.6** `make check`, commit.

---

## Task 4 — "Nightshift already has this"

The corpus polls 2,605 board tokens. Most NYC tech postings a reader finds on
LinkedIn are **already in it**, ingested first-hand from the employer's own
board, with a match score and a location Nightshift trusts. Capturing such a
posting is worse than useless: it costs a review, and it produces a
lower-quality second record of a job already held.

So the capture response names what the corpus already holds — and, when it
cannot check, says that instead of implying an empty answer.

**Files:**
- Create: `services/api/nightshift/domain/capture_matches.py`
- Create: `services/api/tests/test_capture_matches.py`
- Modify: `api/routes/capture.py`, `api/schemas.py`, `mcp/server.py`, `mcp/shapes.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, slots=True) class CorpusMatch: job_id: uuid.UUID; title: str; company_name: str; status: JobStatus; reason: str; url: str | None`
  - `@dataclass(frozen=True, slots=True) class CorpusCheck: checked: bool; why_not: str | None; matches: tuple[CorpusMatch, ...]`
  - `async def check_corpus(session, *, title: str | None, company_name: str | None, source_url: str | None) -> CorpusCheck`
- Consumes: `normalize_company_name` (`domain/companies.py`), `normalize_title`
  (`adapters/greenhouse.py`), `normalize_url` (`domain/dedupe.py`).

**Two rules, both deterministic, both nameable in the response.** This is
advisory and it is not `dedupe.compare` — nothing is being merged, no
`job_merge_event` is written, and the reader decides. Reusing the merge
comparator would need an employment type, a location set and a description hash
that a paste does not honestly have.

  - `reason="same_company_and_title"` — normalized company name **and**
    normalized title both match an existing job.
  - `reason="same_url"` — `normalize_url(source_url)` matches a job's
    `canonical_url`. Rare from LinkedIn and free to check, and it is the one
    that fires when the reader pastes the employer's own ATS link.

**When title or company is unknown, `checked` is `False` and `why_not` says
which.** An empty `matches` list on an unchecked capture would read as "no
duplicates", which is the I3 failure — silence presented as evidence — in a new
place.

- [ ] **4.1** Failing tests in `test_capture_matches.py`, against jobs planted
      by the existing job factory: an exact company+title hit is returned with
      its status; a same-title-different-company job is not; a closed job **is**
      returned and carries `status="closed"` (a reader capturing a role that
      closed needs to know that above all else); an unparseable capture returns
      `checked=False, why_not="no company name was read from the text"`.

- [ ] **4.2** Run; expect `ModuleNotFoundError`.

- [ ] **4.3** Implement. One `select` joining `jobs` → `companies`, filtered on
      the normalized keys, limit 5, ordered by status (open first) then
      `updated_at desc`.

- [ ] **4.4** Wire into `POST /capture`'s response as `corpus_check`, computed
      from whichever proposal survived — the assistant's accepted field first,
      then the parser's, because the assistant read the actual page. Record
      that precedence in ADR 0039 §3; it is the one place an assistant value
      outranks a parser value, and it is safe because it only steers a *search*.

- [ ] **4.5** `shapes.capture_proposal` surfaces it, and `capture_posting`'s
      description tells the model to **lead with it**: if the corpus already
      holds the job, say so first, give the reader the existing job's id, and
      note that the proposal can be discarded. Add the sentence that stops the
      other failure: an unchecked result must not be reported as "no duplicates".

- [ ] **4.6** `tests/test_mcp_capture.py`: capturing text for a job already in
      the corpus returns a `corpus_check` naming it. Sabotage: return
      `matches=()` unconditionally and watch it go red.

- [ ] **4.7** `make check`, commit.

---

## Task 5 — The review surface says where it came from and who read it

Everything above is invisible until the form shows it. A reader looking at
`/operate/capture` must be able to answer three questions without leaving the
page: where did this come from, who proposed each field, and does Nightshift
already have it.

**Files:**
- Modify: `apps/web/src/components/CapturePosting.tsx`, `.test.tsx`
- Modify: `apps/web/src/lib/schemas.ts`
- Modify: `services/api/nightshift/domain/capture.py` (`capture_origin`),
  `api/routes/capture.py` (`origin` in `CaptureOut`)
- Test: `apps/web/e2e/` — extend the existing capture spec

**Interfaces:**
- Produces: `def capture_origin(source_url: str | None) -> str` returning
  `"linkedin" | "indeed" | "other" | "none"`. **Derived, never stored** — the
  same reasoning as `employment_type_for_title`: a column could disagree with
  the URL sitting beside it in the form.

- [ ] **5.1** `capture_origin` + unit tests, including
      `https://uk.linkedin.com/jobs/view/1` → `linkedin` (subdomain), and
      `https://linkedin.com.evil.example/` → `other` (suffix match on the
      registrable host, not `in` on the string). Sabotage: use `in` and watch
      the evil-host test go red.

- [ ] **5.2** `CaptureOut.origin`, schema updated on the web side.

- [ ] **5.3** Component test first, then the component: an origin chip
      (`From LinkedIn` / `From Indeed` / `From a link` / `Pasted text`); each
      pre-filled field labelled with its proposer (`read by Nightshift` /
      `quoted by Claude`); refused fields shown as a quiet note rather than an
      error, because a refusal is the guard working; and the corpus-check block
      — *"Nightshift already has this job"* with a link — above the form rather
      than below it, since it can make the whole form unnecessary.

- [ ] **5.4** Where the parser and the assistant disagree on a field, show both
      and pre-fill neither. A silent winner is the one outcome this whole
      design exists to prevent.

- [ ] **5.5** Colour tokens: any new chip goes through `paper*`/`ink*` and gains
      its assertion in `colour-contrast.test.ts` (`CLAUDE.md` §7).

- [ ] **5.6** `make check`, `make test-e2e-seeded`, commit.

---

## Task 6 — The walk, the review, the docs

- [ ] **6.1** Seed data: `make seed` plants one capture that came from LinkedIn
      with an assistant quote and one whose company the corpus already holds,
      so the two new surfaces are reachable from `make demo` without a person
      having something in their clipboard. (M5a set this precedent for exactly
      this reason.)
- [ ] **6.2** **The walk, in Claude Desktop, against a real LinkedIn job page
      the human is actually looking at.** Not a fixture. Record the transcript
      in `docs/reviews/milestone-5d-walk.md`: what the model quoted, what was
      refused, whether it led with the corpus check, and whether it described
      the capture as a proposal. The M5c walk found four defects that a green
      suite could not; this one is the same instrument pointed at new code.
- [ ] **6.3** `docs/runbooks/capturing-from-a-job-board.md` — the reader's own
      steps, including the account-mismatch foot-gun the desktop walk found
      (finding 5: the token's account and the browser session are independent).
      **Every command in it gets executed before it is written down.** The M5c
      branch shipped a runbook command that failed with `EOFError` every run.
- [ ] **6.4** ADR 0039, complete: §1 the boundary, §2 point-not-paraphrase, §3
      the assistant's precedence in the corpus check and why it is safe there
      only, §4 advisory matching rather than `dedupe.compare`. Rejected
      alternatives for each.
- [ ] **6.5** `docs/reviews/milestone-5d-review.md`, hunting `CLAUDE.md` §5's
      list plus this milestone's own failure class: **a proposal that reads as
      a fact because of where it is rendered.**
- [ ] **6.6** `docs/PROGRESS.md`. `make check`, `make acceptance`, push, PR,
      watch CI.

---

## What this plan deliberately does not build

- **Any fetch of a job board.** Task 1 exists to make that permanent.
- **A browser extension.** The reader's Claude already has a browser; Nightshift
  does not need one, and shipping one would put us back inside `robots.txt`'s
  jurisdiction.
- **A `confirm` tool.** ADR 0038 said why. M5d adds proposals; it does not add
  a way to approve them without a person.
- **Site-specific parsers for LinkedIn and Indeed page markup.** The assistant
  reads the page; a second, worse reader of the same page maintained against
  markup we are not allowed to fetch is a maintenance cost with no owner. If
  task 6's walk shows the assistant's quotes are unreliable, that verdict
  changes and the correction belongs in this milestone.
- **M5e's office exposure** — the `means` defect from the desktop walk §4.4.
  Its own slice, and it needs an API change.

## The risk this plan is most likely to be wrong about

**That quotability is the right gate.** It is strict, deterministic and easy to
test, and it may refuse so often that the assistant's proposals are useless —
a LinkedIn page shows "New York, NY (Hybrid)" and a model that writes "New
York, NY" gets refused for being tidy. If task 6's walk shows most fields
refused, the honest correction is not to loosen the rule quietly; it is to
change what the tool description asks the model to send, and if that fails, to
record in ADR 0039 that the gate was wrong and say what replaced it.
