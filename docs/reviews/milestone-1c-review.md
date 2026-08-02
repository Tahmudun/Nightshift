# M1c review — board discovery

**Date:** 2026-08-02
**Branch:** `m1c-board-discovery`, six tasks, commits `1723d65`…`152d920`
**Scope:** `nightshift/discovery/`, `PoliteClient.get_text`, `GET /coverage`,
`/analyze/coverage`, five `make` targets.

At close: **600 Python tests** (from 493 at branch start), 42 web unit, **16
seeded browser tests** (from 11). `make check` green; `make test-e2e-seeded`
green against a real seeded stack.

This review looks for the failure modes the plan named — a validator that
classifies everything `unreachable` when a provider changes shape, an approval
path trickable by a hand-edited candidate file, token extraction admitting a
path traversal, rate-limit behaviour across thousands of tokens, and a coverage
page claiming completeness it has not earned — plus what actually went wrong.

---

## 1. What the milestone claims, and the evidence

| M1 criterion | Status | Evidence |
|---|---|---|
| 10 — Discovery yields candidates from a committed crawl fixture, deterministically | **Verified** | `tokens_from_cdx` against `ashby_cc_main_2026_30.jsonl`: 400 rows → 23 distinct tokens, `test_is_deterministic_and_sorted` asserts same-input/same-output and sorted order. `make discover` is idempotent (`test_is_idempotent`) |
| 11 — A live-but-unnameable board cannot reach bulk approval | **Verified** | `test_a_live_but_unnameable_board_cannot_be_bulk_approved` (verdict) and `test_an_unnameable_board_is_not_promoted_even_with_write` (through the command). Mutation-checked twice: token-fallback in `_resolve_name` fails 1 test; dropping the verdict filter in `approvable` fails 8 |
| 12 — The coverage page names what is *not* covered | **Verified** | Four structural blind spots by id, 5 browser tests including one asserting the section contains no `<details>` and its text is visible unexpanded |

Criterion 13 (`304 Not Modified`) is **M1d** and remains unclaimed.

---

## 2. The five named risks

**A validator that classifies everything `unreachable` when a provider changes
shape.** Real, and partly by design — a 200 with an unexpected shape *must* be
`unreachable`, because "no jobs" is the one conclusion we cannot draw from it
(`test_a_200_with_the_wrong_shape_is_unreachable_not_empty`). The danger is the
silent-mass-failure version: a provider changes its envelope and 2,000 boards
go `unreachable` in one sweep with nothing saying why. **Not mitigated.** Each
candidate carries a `notes` string naming the shape it got, but nothing
aggregates them, and nothing alerts on "this sweep classified 98% unreachable".
Recorded below as the first thing M1d should add.

**An approval path trickable by a hand-edited candidate file.** The candidate
file is committed and hand-editable by design, so this deserved real attention.
Three doors are shut: the model refuses a `live_named` candidate with no name
and a `live_unnamed` one that carries a name (`TestModelRefusesNonsense`), so a
name cannot be pencilled onto an unnamed board without changing the verdict too;
`promote` treats an existing `(ats, token)` as present and adds nothing, so a
hand-added duplicate cannot re-enable a `disabled` board
(`test_never_re_enables_a_board_a_human_disabled`); and the token regex rejects
path traversal at the candidate door as well as the registry one. **What is
*not* defended:** somebody editing `verdict: live_unnamed` to `live_named` and
adding a name. That is indistinguishable from a legitimate manual approval,
which is what ADR 0005 says a human is for, and the diff is the review. Named
here so the boundary is explicit rather than assumed.

**Token extraction admitting a path traversal.** Two layers. `tokens_from_cdx`
takes path segment 1 of a parsed URL, so `..` cannot survive `urlsplit` as a
segment containing a slash; and `Candidate` rejects anything outside
`^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` before the file is written
(`test_a_token_that_could_escape_a_url_is_rejected`, covering `../etc`, `a/b`,
`a?b`, `a#b`, `""`). A bare `..` would be caught by the leading-character class.
The exact-host check (`test_a_url_on_another_host_is_ignored`) closes the
adjacent hole where `evil.jobs.ashbyhq.com.attacker.test` contributes a token.

**Rate-limit behaviour across thousands of tokens.** Exercised for real at 23
tokens / 44 requests, not at 2,605. `PoliteClient`'s existing limiter paced it
and `SOURCE_REQUESTS_PER_SECOND=0.8` was used by hand. **Two real findings:**
an empty board costs one request rather than two, verified in production (`abe`
and `0x`), which matters at scale; and `cmd_validate` saves the candidate file
after *every* board, so an interrupted sweep keeps its verdicts — at 2,605
candidates that is 2,605 rewrites of a growing YAML file, which is O(n²) work
and will need batching. Recorded, not fixed.

**A coverage page claiming completeness it has not earned.** The strongest part
of the milestone. No percentage exists anywhere — asserted in the summary
(`test_reports_no_percentage_of_the_market`), in the text report, and in the
browser (`expect(body).not.toMatch(/\d+(\.\d+)?%/)`). `count=None` renders
"unknown" and survives serialisation as null, mutation-checked by typing the
field `int = 0`, which fails the route test. Three gaps report real numbers so
the column is not uniformly "unknown".

---

## 3. What actually went wrong, and what caught it

Five defects. **Four of the five were found by running something, not by
reading it** — which is the same pattern M1a and M1b recorded, now three
milestones running.

1. **The design's central example board is dead.** `a3c41b8b71eff8c4` — the
   live-but-unnameable board the whole approval gate is designed around — now
   404s and is absent from the July 2026 crawl index in a range the committed
   slice covers. Found by probing it before recording. What replaced it is
   stronger: Ashby serves **HTTP 200 with `<title>Jobs</title>`** for any token
   that does not exist, so the unnameable page is now a recording rather than
   the hand-written stub the plan specified.
2. **Two candidates naming one employer both reached the approval report.**
   `Abridge` and `abridge`, 42 postings each. Found by `make registry-approve`
   on real validated data. `name_collision` compares against the *registry*, so
   it is structurally blind to a collision inside one batch. Fixed; both are
   held, and the report says so.
3. **Harvested tokens were recorded as `unreachable`.** Found by reading the
   first real `make discover` output. That claims we tried and failed against
   boards nobody had contacted, and the coverage page would have reported 23
   failures that never happened. Fixed by adding an `unvalidated` verdict.
4. **`test_validation_never_raises` was vacuous.** Its stub route key matched
   no URL, so the stub raised "no route" and the test passed without ever
   reaching the branch it exists to cover. Found by reading the plan's test
   before running it — the one of the five caught by reading.
5. **The plan's repo-root arithmetic was off by one** (`parents[3]` is
   `services/`), which would have written `services/data/board-candidates.yaml`
   while approval read an empty file from the correct path. A silent split, not
   a crash.

Two further plan defects, both self-contradictions: Task 4's test built a
candidate violating Task 2's own `nyc ≤ total` rule, and Task 4's
`approval_report` promised an ordering it did not apply.

---

## 4. Weaknesses carried forward

Ranked. The first two are the ones M1d should not inherit unnoticed.

1. **No mass-failure signal.** A provider changing its envelope classifies every
   board `unreachable` and nothing says so louder than a per-candidate note. A
   sweep should refuse to persist, or at least shout, when the unreachable rate
   crosses a threshold — the same shape as I3's "a source outage is not
   evidence", one level up.
2. **`cmd_validate` rewrites the whole candidate file per board.** Correct and
   interruption-safe at 23; O(n²) at 2,605.
3. **Discovery has only ever run against Ashby.** `PROVIDER_PATTERNS` includes
   Greenhouse and the code paths exist, but no Greenhouse crawl fixture is
   recorded, so `make discover --provider greenhouse` is untested against real
   data. Greenhouse validation *is* tested, on the recorded `6sense` board.
4. **The crawl slice is 400 rows.** It yields 23 tokens spanning `0g`…`abridge`
   — the alphabetical head of one provider. The design's 2,605 figure is not
   re-measured here and this plan never claimed it. Common Crawl's index 504s at
   `limit=6000`, so a full harvest needs paging that does not exist yet.
5. **`scripts/record_crawl_fixture.py` cannot run on this host.** It uses
   `urllib`, which has no certifi bundle here and fails TLS verification. Task
   3's recorder goes through `PoliteClient` and works; the crawl recorder should
   move onto it.
6. **`get_text`'s 256 KB cap silently truncates a CDX response.** The CLI warns
   when a live harvest hits the cap, but the cap is a board-page number applied
   to an index response, and the two want different limits.
7. **No `careers_probe.py`.** Lever stays undiscoverable, deliberately — see
   below.

---

## 5. What was deliberately not built

**The careers-page probe for Lever**, and with it any ability to discover a
Lever board at all. It needs a list of employer domains to start from, and
nothing in this repository has one; building a domain-guessing heuristic would
be exactly the fabrication this milestone exists to prevent. The consequence is
carried honestly rather than hidden: `lever_undiscovered` is the first blind
spot on the coverage page, it states the structural reason (CCBot is disallowed
by Lever's own robots.txt), and a browser test asserts it reaches the screen.

**The community-snapshot source**, for the same reason.

**Any registry change.** `data/board-registry.yaml` is byte-identical to its
state at branch start, verified by `git diff cf48719..HEAD`. 19 boards are
eligible for approval and the report prints them; promoting thousands of
employers is a product decision for the human, and the plan's job was to prove
the pipeline works, not to fill the registry.

---

## 6. Verdict

The three M1c acceptance criteria are met with evidence, and the two gates the
milestone exists for — a live-but-unnameable board cannot be bulk-approved, and
the coverage page names its blind spots — are both mutation-checked rather than
merely tested.

The honest summary of the milestone is that **the design's numbers aged in six
weeks and the pipeline's own output was what noticed.** The example board is
gone, the duplicate-token case was real and unhandled, and the "not yet checked"
state did not exist. None of those were visible from the code.

M1c is complete. M1 is not: M1d owns polling, the `304` criterion, and the two
weaknesses at the top of §4.
