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

## 2. Defects found and fixed inside this branch

All three were found before the code was committed, and all three are the same
kind of mistake: **a guard that would have passed for a reason unrelated to
the thing it guards.**

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
- **No e2e coverage of `/operate/capture`.** There is none today either — the
  four specs in `apps/web/e2e/` are all city. The review screen is covered by
  thirteen component tests and by the walk, and a first capture spec is worth
  writing; it is a gap this review states rather than one it closes.
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
