# M5c review — the MCP server

Written 2026-08-21, on `m5c-the-open-hand`, with tasks 1–4 built and task 5
half-walked. **The milestone is not complete**: its acceptance criterion is a
person connecting Claude Desktop and having a conversation, and no part of that
can be a test in this repository. What follows reviews what exists.

`CLAUDE.md` §5 names the failure classes a review must hunt: hallucinated
certainty, silent data loss, wrong merges, race conditions, retry storms, GPU
leaks, unbounded render work, mobile gesture conflicts, accessibility gaps,
privacy overreach, tests that assert nothing. Two of those are live here, and
this milestone adds one of its own.

---

## 1. The one that is new, and the one that shaped everything

**A tool result can be correct and its reading false.**

Every earlier milestone had a renderer downstream. A React component shows what
it is given; shipping `location_confidence: "city_only"` as a string was enough,
because a designer decided what that string looks like and a person reads a
badge. Here the consumer is a language model that will paraphrase, summarise,
and answer a follow-up question forty minutes later from a compressed memory of
the result.

**A field a model cannot interpret is a field it will interpret anyway.** Handed
`{"city": "New York", "location_confidence": "city_only"}` and asked "where is
this job?", the fluent answer is a neighbourhood or an address. That is I1
broken with every value in the payload correct.

So this milestone's enforcement is prose, and the prose is reviewed as code:
every location carries a `means` sentence, the table of them is asserted
exhaustive over `LocationConfidence`, and the tool descriptions state what a
value licenses a reader to claim. `tests/test_mcp_shapes.py` holds the
structure; **nothing here can hold the reading**, which is why task 5 needs a
human and why this review cannot close the milestone.

## 2. Defects found and fixed

### 2.1 A closed listing presented as an open role — found by reading, not running

`search_jobs`'s description said *"Search open New York technology jobs"*.
`GET /jobs` applies a status filter **only when given one**, and the tool passed
none, so it returned every status including `closed`. A reader asking for
backend roles would have been handed listings that no longer exist, described as
available.

This is I3's shape — a closed listing is not a live one — arriving through a
description that made a promise the implementation did not keep.

**The live walk could not have found it, and that is the reviewable part.** The
seeded corpus is 32 jobs and all 32 are `open`. The stdio walk in
`milestone-5c-stdio-walk.md` exercised `search_jobs` against real data and could
not have produced a single closed row. **This is the third time in one milestone
that a corpus which cannot produce a failure failed to test the guard against
it** — see 2.2 — and M4c recorded the same lesson a milestone ago.

Fixed: `status` is a parameter defaulting to `"open"`, the description says so
and says how to ask for closed ones, `get_job` warns that it answers for any
status, and `test_search_does_not_return_closed_jobs_by_default` builds the
closed job the corpus cannot supply. It asserts both directions — the closed job
is absent by default and **present when asked for** — because I3 forbids
presenting a closed role as open, not knowing about one.

### 2.2 Tests that asserted nothing, found by sabotage

`test_mcp_read_tools.py`'s guards walk tool results looking for a leaked score
or a bare coordinate. `db_session` truncates, so `search_jobs` returned
`{"jobs": []}` — and **a walk over an empty list finds nothing**. Sabotaging
`job_summary` to emit `"score": 78` left the file green.

This is `CLAUDE.md` §7's *"a test that cannot fail is not a test"*, and it was
caught only because every guard in this milestone was deliberately sabotaged
rather than assumed. Fixed by a `corpus` fixture that plants a job, two
locations and an application; the same sabotage now goes red.

**Worth generalising:** six guards were written and six were sabotaged. One of
the six was inert. A one-in-six rate is an argument for sabotaging every guard
rather than the ones that look risky.

### 2.3 `job_summary` read a field the API does not serialise

`job["company"]["name"]` against a `CompanyOut` that carries `canonical_name`.
A `KeyError` on every search — surfaced the moment the corpus fixture made a
real response reach the code, and invisible to every test before it.

## 3. Findings that were not defects

**Postgres enforces I1 harder than this milestone assumed.**
`job_locations.confidence_matches_coordinates` requires a latitude for
`verified`/`approximate` and forbids one for `city_only`/`remote`/`unknown`. The
corpus fixture tried to plant the combination `shapes.py` defends against and
the INSERT was refused.

The defence is kept and **relabelled**: it was written as a last line and is
genuinely belt-and-braces. It stays because an MCP client will one day read a
response this repository did not serialise, and because a constraint elsewhere
is not a reason to hand a model a coordinate it must not read as an address.

**The first enum column added to an existing table.** Autogenerate emits
`sa.Enum` inside `add_column` without the `CREATE TYPE` before it, so migration
`0025` could not run at all in its first draft. `0023` and `0024` never met it
because `create_table` emits the type. Created and dropped by hand now.

## 4. Privacy and overreach, checked deliberately

`CLAUDE.md` §5 names privacy overreach, and this is the milestone where a
program outside Nightshift gains access to somebody's data — so it deserves more
than a glance.

- **No tool takes an identity argument.** Asserted over the registered tool list
  (`test_no_tool_takes_a_user_id_argument`), because a `user_id` parameter would
  let *the caller* choose whose data to read, and the caller is a model reading
  text written by strangers.
- **No tool takes an irreversible action.** Asserted over the tool list for
  `confirm`, `approve`, `accept`, `commit`, `apply`, `advance`, `stage`,
  `archive` — broader than today's vocabulary on purpose.
- **The MCP package cannot reach the database.** Enforced in a subprocess,
  because pytest has already imported the codebase and an in-process check would
  pass unconditionally.
- **Nothing is sent anywhere.** The server talks to `localhost` over stdio. No
  posting text, no profile, no application leaves the machine except into the
  reader's own Claude, at their own instigation.

**The one thing that is not mitigated, stated rather than glossed:** an MCP
token has the same power as a browser session and sits in a plaintext config
file. It is not scoped and not read-only. ADR 0038 §3 argues that revocability
somebody can aim is the honest mitigation at one user on one machine, and that a
second table pretending the credential is weaker would be a lie told in a
schema. **That argument gets weaker the moment a second person has an account**,
and it should be revisited with Q11's rate limiting rather than separately.

## 5. What is not built, and what is not proven

**Not built:** `get_profile` — and with it, I2 has no surface in this milestone.
The four tool families touch jobs, matches, applications and captures; inferred
facts live on the profile, and `UserSkill` is confirmed by construction. Whoever
builds `get_profile` inherits the labelling rule. `save_job` sits on the
permitted side of I5 and was not among the four families chosen.

**Not proven, and this is the gap that matters:**

| Claim | Evidence |
|---|---|
| The transport, handshake and tool discovery work | `milestone-5c-stdio-walk.md`, real subprocess and pipes |
| The bearer token authenticates against `require_session` | Same, `whoami` returning the seeded account |
| An outage is an error, not an empty list | Same, with the API genuinely stopped |
| A capture lands `pending` with no job | Same, verified by querying Postgres |
| A revoked token is refused | Same |
| **Claude Desktop connects** | **Nothing. Needs a person.** |
| **A model reading these descriptions says "address unknown" rather than inventing a street** | **Nothing, and nothing here can.** |

The last row is the milestone's actual acceptance criterion and the reason §1
exists. **A green suite here is evidence the plumbing works, not that the
product tells the truth.**

## 6. Process, recorded because it cost real time

**Three `make check` runs reported errors in unrelated suites and all three were
lock contention I caused** by running a background `pytest` and leaving a stale
dev stack against the same Postgres. PROGRESS already said *"a test run that
overlaps another test run is not evidence"*, and I read it only after the third.
The rule now sits at the top of "Next exact action" where it will be read first.

**`git checkout HEAD -- <file>` to undo a deliberate sabotage discards
uncommitted work in that file.** It cost two rewrites, of `identity.py` and
`cli.py`. Sabotage by copying the file aside, or commit before sabotaging.
