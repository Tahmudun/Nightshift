# M5d review — assisted capture from LinkedIn and Indeed

**Branch:** `m5d-assisted-capture`, off `main` at `0765381`.
**Plan:** `docs/plans/2026-08-22-m5d-assisted-capture.md`. **Decisions:** ADR 0039 §§1–4.

Written against `CLAUDE.md` §5's list — hallucinated certainty, silent data
loss, wrong merges, race conditions, retry storms, tests that assert nothing —
plus this milestone's own failure class, which is new and is the one worth
naming first:

> **A proposal that reads as a fact because of where it is rendered.**
>
> M5c's failure class was *a result that is correct and whose reading is
> false*, and it lived in tool descriptions. M5d's is a floor below that. A
> pre-filled input in a review form is a claim, and until this milestone there
> was exactly one thing it could be a claim by. Now there are two, they fail
> differently, and nothing about a filled-in box says which one filled it.

---

## 1. What was built

| Piece | Where | ADR |
|---|---|---|
| The never-fetch boundary, as two guards | `tests/test_capture_never_fetches.py` | §1 |
| The quoting rule | `domain/capture_assist.py` | §2 |
| `assistant_*` columns and refusal names | migration `0026` | §2 |
| Idempotence over a person's pending queue | `capture_paste`, migration `0027` | §3 |
| "Nightshift already has this" | `domain/capture_matches.py` | §4 |
| Provenance and origin on the review screen | `lib/capture.ts`, `CapturePosting.tsx` | §2 |
| The review queue, and a live corpus check on read-back | `CaptureQueue.tsx`, `GET /capture/{id}` | §3, §4 |

## 2. Defects found and fixed inside this branch

The first three were found before the code was committed, and all three are
the same kind of mistake: **a guard that would have passed for a reason
unrelated to the thing it guards.**

**2.4 to 2.6 were found after this review was first written**, by starting to
close the gap §4 states below and then by looking at the screen the gap was
about. They are a different kind of mistake and the more expensive one: not a
check that could not fail, but **a flow nobody had walked**. Every one of them
was one click away from anybody actually trying to review a posting Claude had
captured.

**2.1 — The transport guard patched the wrong layer.** Its first draft replaced
`httpx.AsyncClient.send`. The test client in that module *is* an
`httpx.AsyncClient`, so the guard would have broken its own plumbing and, once
worked around, would have been asserting about the test harness rather than the
capture path. Fixed by patching `AsyncHTTPTransport.handle_async_request` and
its sync twin, which `ASGITransport` never touches.

**2.2 — The URL matching rule limited before it filtered.** `_by_url`'s first
draft selected every job with a non-null `canonical_url`, limited to five, and
compared in Python. It found the right job only if that job happened to be
among the five most recently seen rows in the whole corpus. **It passed its
test**, because the fixture had two rows. Now SQL narrows on the host and path
and `normalize_url` decides. The failure and the reason it survived a test are
written into the function's docstring.

**2.3 — `capture_origin` matched with `in`.** `https://linkedin.com.evil.example/`
contains the string `linkedin.com`, and a review form labelling it *From
LinkedIn* would tell a reader a URL is trustworthy on the strength of an
attacker's subdomain. Now a suffix match on the parsed host. The lookalike case
is its own test rather than a parametrised row, because it is the only one that
goes red under the sabotage.

**2.4 — The review queue had no screen, and it is the worst defect in the
milestone.** `capture_posting` answers with `review_url` and the sentence *"the
reader confirms or discards it at `review_url`"*; the runbook said *"open
`/operate/capture` and decide"*; ADR 0039 §3 spends a section arguing about
what belongs on the queue. `/operate/capture` rendered a paste box and the one
proposal the current browser tab had just created. **A capture made through the
MCP server — the entire point of this milestone — had a row in the database, a
`pending` status, an origin of `linkedin`, and no way to be looked at.**

Three things kept it invisible, and they are worth separating because each one
looked like diligence at the time:

- **The API was complete.** `GET /capture?status=pending` shipped in M5a and
  `fetchCaptures` was written against it in the web client. It had no caller.
  A finished route and an unused client function read as *built* in every
  review that looks at the API and the components separately.
- **Every test began by pasting.** All thirteen component tests drove the form
  through `capturePosting`, which is the rare path. No test could observe a
  proposal the browser had not created, because none of them ever had one.
- **The walk that would have caught it is the human's**, and this review was
  written first — knowing, and saying in §6, that it is the weaker instrument.
  It is: the defect was one click away from anybody actually trying to review a
  posting Claude had captured.

Fixed with `components/CaptureQueue.tsx`, a live corpus check on `GET
/capture/{id}`, and a **Decide later** exit; recorded in ADR 0039 §3, and now
covered by `e2e-seeded/capture.spec.ts`, whose first test opens a proposal the
browser never created.

**2.5 — The review form showed no text to check the fields against**, and this
one was found by looking at a screenshot rather than by a test. The runbook has
said *"check every field against the text"* since it was written; there was no
text on the page. That was survivable while pasting was the only way in — the
posting was in the reader's own clipboard — and it is not survivable for a
capture made in Claude Desktop, where the person confirming never saw the
posting at all. **A confirmation with nothing to check against is the person's
name on the parser's reading**, which is precisely what the two steps exist to
prevent. `raw_text` was already on `CaptureOut`; it now renders beside the
fields.

**2.6 — A queue row put its doubt on the wrong field.** It read *"Campus AI
Research Engineer (Intern) · two readings disagree"*, and the disagreement was
about the employer, not the title standing next to it. Both uncertain states
now name their field. Small, and the same family as everything else here: a
true sentence whose reading is false.

## 3. Hunting the standing failure classes

**Hallucinated certainty.** The one place M5d could introduce it is
`corpus_check`, and it is the reason `checked` exists as a separate field from
an empty `matches`. An unchecked capture rendering as *no duplicates* is I3's
failure — silence presented as evidence — moved from source outages to
duplicate detection. Three layers say so: the API sends `why_not`, the MCP
shape turns it into an instruction (*"do not tell the reader this posting is
new to Nightshift — nobody looked"*), and the web surface renders the sentence
rather than nothing. Each has a test.

**Silent data loss.** `capture_paste` returns an existing pending row
**unmodified** — the second call's `source_url` and quotes are discarded rather
than merged. That is a deliberate loss and it is the right one: the stored row
is what the reader is about to look at, and editing it under them while telling
them it already existed is two contradictory statements in one response. It is
recorded in ADR 0039 §3 rather than left as an accident. The information
actually destroyed is *the second paste's quotes*, and if a walk shows a model
routinely improving its quotes on a retry, that trade is worth revisiting.

**Wrong merges.** `check_corpus` merges nothing. No `job_merge_event`, no
`job_source_link`, no write of any kind — it is a read that produces a sentence.
The merge comparator was considered and rejected in §4 because it needs an
employment type, a location set and a description hash a paste does not
honestly have, and supplying invented ones to get an answer is the exact
failure this milestone is about.

**Race conditions.** One, and it is bounded. `capture_paste` looks up a pending
row and then inserts, inside one transaction; two simultaneous pastes of the
same text by the same person can both miss and both insert. The cost is one
duplicate row in one person's queue. A partial unique index was considered
(§3) and rejected because it converts the race into an `IntegrityError` the
route must catch and turn back into the existing row — the same lookup with a
worse error path.

**Retry storms.** M5d makes retries *cheaper*, which is the direction that
matters: a model unsure whether its call landed now gets the same proposal back
with a sentence telling it to stop. Nothing in this branch retries anything,
and nothing in it reaches the network at all — §1 is a test.

**Tests that assert nothing.** Every guard in this branch was sabotaged and
watched fail before it was believed, and the sabotage plus its exact failure
message is written into the test's own docstring. That is
`m5c-claude-desktop`'s lesson — *a guard must exercise the thing that runs* —
applied rather than restated, after that branch found an import guard that had
passed on an empty module graph for a whole milestone.

**Privacy overreach.** The refused value is never stored and never returned;
only the field name is. `text_fingerprint` is scoped to a person in the index
itself, and the isolation test's own fixture covers `/capture` — it caught the
NOT NULL column this branch added, which is a small proof that it is really
exercising the table.

## 4. What is deliberately not here

- **No site-specific parser for LinkedIn or Indeed markup.** A second, worse
  reader of a page we are not allowed to fetch, maintained against markup
  nobody here can see, is a cost with no owner. The assistant reads the page.
  If the walk shows its quotes are unreliable, that verdict changes.
- **No confirm tool.** ADR 0038 said why and M5d adds nothing to that argument.
- ~~**No e2e coverage of `/operate/capture`.**~~ **Closed, and closing it is
  what found 2.4.** `e2e-seeded/capture.spec.ts` is the first end-to-end
  coverage this screen has had: it reads the seeded pending capture back from
  the API, opens it from the queue, and asserts the two-reader disagreement,
  the refused quote and the corpus check against a real database. The lesson is
  the milestone's own, one level up — **thirteen tests that all start from the
  same setup step cannot see a flow that does not have it.**
- **M5e's `means` defect.** M5c's desktop walk §4.4 scoped it there. Untouched.

## 5. The risk this milestone is most likely to be wrong about

**That quotability is the right gate**, and it is stated here before the walk
rather than after it. The rule accepts "New York, NY" and "New York" out of
"New York, NY (Hybrid)" and refuses "NYC", and the line between those is not
obvious from outside. If most fields come back refused, the honest correction
is not to loosen the rule quietly — it is to change what the tool description
asks the model to send, and failing that, to record in ADR 0039 that the gate
was wrong and say what replaced it. `assistant_rejected_fields` exists so that
argument can be made from counts rather than from impressions.

## 6. What is owed

**The walk.** A real LinkedIn job page, open in a browser, captured through
Claude Desktop end to end, recorded in `docs/reviews/milestone-5d-walk.md`.
Not a fixture. The M5c walk found four defects that a green suite, a written
review and a live Claude Code walk had all missed; this review is written in
the knowledge that it is the weaker instrument of the two.

Four questions it has to answer:

1. Did the model quote, or paraphrase? How many fields were refused?
2. Did it lead with `already_in_nightshift` when the corpus held the job?
3. Did it call the capture a proposal, unprompted?
4. On a repeat call, did it say *already in your queue* or report a second
   capture?
5. Following `review_url`, was the capture findable without being told where to
   look? That question exists because the answer was *no* until 2.4 was fixed,
   and a walk is the only instrument that asks it.
