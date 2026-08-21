# M5c — the MCP server, and the four things a tool description has to say

> Plan. Branch `m5c-the-open-hand`, off `main` at `1ab2bd9` (PR #18 merged at
> `414117c`, CI green at `06725d6`, no open PR).
>
> Required reading first: `AMENDMENTS` A16 ("the insight that shapes the
> re-cut"); ADR 0037 §1 and §3; `nightshift/api/deps.py` in full — its
> docstrings name M5c twice and both times they are load-bearing;
> `CLAUDE.md` §1 invariants I1, I2, I3, I4, I5.

## What M5c is

M5a made a pasted posting into a tracked job. M5b made Nightshift somebody's
rather than everybody's. **M5c is the rung the rest of the product hangs from**,
and that is A16's claim rather than this plan's:

> Four separate-looking asks — reading LinkedIn/Indeed, "link the app to
> Claude", AI rejection analysis, and a voice assistant — are **one MCP server**
> exposing this domain to Claude. Built once, the other three are configuration
> and UI.

It is also why the AI in this product is free. Nightshift never calls a model.
The user's own Claude is the model; Nightshift supplies deterministic evidence
and Claude narrates it. A server-side inference path is deferred until there is
revenue to cover it, and nothing in this milestone moves that line.

### The one sentence that governs every decision below

**A tool description is not documentation. It is the last place an invariant
can be enforced.**

Every prior milestone could hold I1 and I4 in a database constraint, a type, or
a test. This one cannot. If `get_job` hands back `location_confidence:
"city_only"` and the description does not say what that licenses a reader to
claim, Claude will write *"this role is at 620 8th Avenue"* — fluently,
confidently, and in violation of the invariant this project has protected for
five milestones. The schema stops a coordinate from arriving bare. Only the
description stops it from being *read* as a street address.

That is a new failure class for this repository and it is worth naming before
task 1: **the output can be correct and the reading of it false.**

---

## 1. The architecture, and the one call worth arguing about

### The MCP server is a client of the API. It never touches the database.

`nightshift/mcp/` may import `httpx`. It may not import `nightshift.db.session`,
`get_db_session`, or any model. This is not tidiness.

M5b's whole achievement was making isolation **structural** rather than
conventional — `require_session` is attached once, in `main.py`, so a route is
protected because it exists rather than because its handler remembered to
declare a parameter. `deps.py` says so in as many words:

> A route added in M5c, M8 or M13 is behind a session because it exists, and
> opening one is a deliberate edit to `main.py` that shows up in a diff.

A second door into the domain — one that opens a session, queries `Job`, and
filters by `user_id` because the author remembered to — would reintroduce
exactly the hole M5b closed, in the milestone immediately after it closed it.
Every rule this product has (I5's two-step, capture scoping, default-deny) lives
at the HTTP boundary. The MCP server goes through that boundary like any other
client.

`deps.py` already anticipated this and it is the second place M5c is named:

> The cookie is how a browser actually carries the token, but a bearer token is
> the form a non-browser client — `scripts/verify.py`, and M5c's MCP server —
> can use.

**The cost is one HTTP hop to localhost.** It buys one place where isolation can
be wrong, and that place already has an enumerating test standing over it.

**Task 2 makes this checkable rather than remembered**: a test that imports
`nightshift.mcp` and fails if `nightshift.db` appears anywhere in its module
graph. An architectural rule nothing enforces is a comment.

### Transport: stdio

Claude Desktop launches the server as a subprocess and speaks JSON-RPC over its
standard input and output. No port, no certificate, no public URL, no OAuth.

This is not the transport a deployed server would use — Streamable HTTP is, and
`mcp` 2.0.0 supports it. It is the right one **today** for a reason that is
recorded rather than assumed: Q2 and Q10 were both answered on 2026-08-21 with
*"future concerns, I want things polished first"*, which puts the domain, the
certificate and the email sender at M7. A remote connector needs all three plus
OAuth 2.1. stdio needs none of them and keeps `make demo` offline, which has
been a hard requirement since M0.

**Design so the later change is additive.** The tools are plain functions that
know nothing about their transport; only the entry point binds stdio. Adding
Streamable HTTP at M7 is a second entry point, not a rewrite.

### The credential: sessions grow a name, not a new table

The subprocess must prove who it is, from a config file, with no browser and
nobody to prompt. Three options were considered:

| | Cost |
|---|---|
| Paste a browser session token into the config | Expires in 30 days and **breaks silently** — the user sees "the tool stopped working", not "your token expired" |
| A new `user_api_tokens` table | A second identity-resolution path. Two places to get isolation wrong, where M5b spent the whole milestone getting it to one |
| **`user_sessions` grows `origin` and `label`** ← chosen | One migration, two columns, one resolve path |

**The third is chosen because the two things are the same thing.** A session is
a proven identity with a lifetime. An MCP token is a proven identity with a
longer lifetime and a name. `create_session` already takes `lifetime` as a
parameter. `resolve_session` already exists and is already the only function
that answers "who is this".

- `origin` — a PG enum, `browser | mcp`. Not a bare string (§7).
- `label` — nullable text, `"claude desktop — laptop"`. What makes a revocation
  list readable rather than a column of UUIDs.
- MCP tokens get a **one-year** lifetime rather than thirty days, because
  re-pasting a config file quarterly is how a person stops using a feature.

**What this deliberately does not do**, stated so it is not mistaken for an
oversight: an MCP token has exactly the same power as a browser session. It is
not scoped, not read-only, not restricted by tool. Scoped tokens are a real
feature and they are not this milestone — the honest mitigation at one user on
one machine is **revocability and visibility**, which `label` buys and a scope
system would not improve. A token that sits in a plaintext file on your own disk
is at your machine's trust level; a second table pretending it is weaker would
be a lie told in a schema.

---

## 2. What Claude may do, and what it may not

I5 is *"suggest, surface, confirm"*. Written as an architecture rather than a
promise:

| Claude can | Claude cannot |
|---|---|
| Search and read jobs, every location carrying its confidence | **Confirm a captured posting** |
| Explain a match: components, penalties, `ruleset_version`, evidence | Change an application stage |
| Read the application pipeline and its history | Promote an inferred profile fact |
| Paste a posting → creates a **pending proposal** | Apply, email, or modify a résumé |

**The table is the rule, not the build list.** Saving a job sits on the
permitted side — I5 governs the *irreversible* and unsaving is a click — and it
is still **not built in this slice**, because it was not among the four families
chosen on 2026-08-21. A permission is not a deliverable; if task 5's walk wants
it, §6 says where that correction goes.

### The capture rule, which is the one that matters

`capture_posting` creates the same `pending` row the paste form creates and
returns the URL where a person confirms it. **It never confirms.** There is no
`confirm_capture` tool and task 4 adds a test that fails if one appears.

The argument for a confirm tool is that Claude Desktop shows the user an
approval dialog before any tool call, so a human *did* approve. **That argument
is wrong and the difference is the whole of M5a.** Approving "call
`confirm_capture`" is not reviewing a parsed job title, a company name and a
location string. `capture.py` already says what is at stake:

> a one-shot endpoint that parses and commits in the same request […] makes the
> parser's reading indistinguishable from a person's decision, at exactly the
> point where the difference decides whether a job lands on the right building.

An MCP confirm tool is that one-shot endpoint with an extra process in the
middle. The two-step is the feature; it does not get an exception because the
caller is fluent.

---

## 3. What a tool returns, and the four things the description has to say

Every result is structured, and every qualifier travels **with** the value it
qualifies rather than in a footnote the model may not read.

### I1 — a location is never a bare coordinate

```
"location": {
  "text": "New York, NY",
  "confidence": "city_only",
  "coordinates": null,
  "means": "The posting names a city and no address. Nightshift does not know
            where this role sits and will not place it on a building."
}
```

The `means` field is not padding. It is the enforcement, restated per row where
a model reading one result cannot miss it. Five values, five sentences, written
once in one module and asserted against `location_confidence`'s enum so a new
member cannot ship without one.

### I4 — a score is never a bare number

`explain_match` returns components, penalties, `ruleset_version` and evidence
rows, or it returns nothing. There is no `score` field on any other tool's
output — a job in `search_jobs` carries its match score **only** alongside a
pointer to `explain_match`, because *"a bare number in the UI is a bug"* and a
tool result is a UI.

### I2 — an inferred fact is labelled where it is read

Anything `inferred_pending_confirmation` says so in its own object. Claude may
report it as unconfirmed and may not report it as fact.

### I3 — an outage is not an empty result

**This is the one that will actually happen**, because Claude Desktop launches
the MCP server whether or not `make dev` is running. If the API is unreachable
and `search_jobs` returns `[]`, Claude says *"there are no backend internships
open"* — which is I3's exact failure ("a source returning an error is not
evidence a job closed") on a new surface.

So: an unreachable API is a **tool error**, never an empty list, and its message
names the cause and the fix — *"Nightshift's API is not reachable at
http://localhost:8000. Start it with `make dev`."* Task 3 tests this against a
closed port and asserts the tool raises rather than returns.

### The stdio trap, recorded before it costs a day

**On stdio transport, anything written to stdout corrupts the protocol.** The
transport *is* stdout. One stray `print`, one structlog handler pointed at the
default stream, and the connection dies in a way whose symptom is "Claude
Desktop says the server failed" with nothing useful anywhere.

`configure_logging()` is called by the API and the CLI both. Task 2 gives the
MCP entry point its own configuration that pins every stream to **stderr**, and
a test that captures stdout across a full tool call and asserts it contains
nothing but protocol frames. Ruff's `T20` already bans `print` in library code;
this is the case where that lint has teeth.

---

## 4. Tasks

Each ends runnable and testable. Commits are scoped (`feat(mcp): …`).

### Task 1 — the credential

- Migration: `session_origin` PG enum (`browser`, `mcp`); `user_sessions.origin`
  (not null, default `browser`) and `user_sessions.label` (nullable). Reversible
  and tested both directions (§7).
- `create_session` takes `origin` and `label`; `MCP_TOKEN_LIFETIME = 365 days`
  as a named constant beside `SESSION_LIFETIME`, not an argument at a call site.
- `nightshift tokens` — `--create --label`, `--list`, `--revoke <id>`. Prints
  the token **once**, then the `claude_desktop_config.json` block to paste.
- Tests: a browser session and an MCP token resolve through the same
  `resolve_session`; `--list` never prints a token or a hash; revoking an MCP
  token leaves browser sessions alone, and the reverse.

### Task 2 — the server, the transport, and the guard rails

- `mcp>=2.0` in `pyproject.toml` — **then `make constraints`, in the same
  commit.** This is the two-step with no local signal that went red on PR #18
  (`argon2-cffi`, run 1). It has now cost this project one CI run; it does not
  get to cost a second.
- `nightshift/mcp/`: `client.py` (the authenticated `httpx` client), `server.py`
  (`MCPServer` and the tool functions), `__main__.py` (the stdio entry point and
  its stderr-pinned logging).
- One tool only — `whoami`, returning the signed-in account — so the whole path
  is provable before any domain surface rides on it.
- Tests: an in-memory MCP client completes the handshake, lists tools, calls
  `whoami`, and gets the account the token belongs to; **the import guard**
  (`nightshift.db` absent from `nightshift.mcp`'s module graph); **the stdout
  guard**. Each shown able to fail.

### Task 3 — the read tools

`search_jobs`, `get_job`, `list_applications`, `explain_match` — all four
families, as chosen on 2026-08-21.

- The result shapes of §3, and the `means` table as one pure function.
- Tests: every location result carries a confidence and a `means`; no tool but
  `explain_match` returns a score; a closed port raises rather than returns
  empty; another user's application is invisible through the MCP surface, using
  M5b's enumerating pattern rather than one spot check.

### Task 4 — capture

- `capture_posting` → a `pending` row and the confirm URL.
- Tests: the tool creates nothing confirmed; **no tool named `confirm` exists**,
  asserted over the registered tool list so a future addition trips it; pasting
  the same posting twice creates no duplicate (M5's acceptance names this).

### Task 5 — the connection, walked in Claude Desktop

The acceptance criterion is *"Claude Desktop connects and captures a posting end
to end"*, which is a live integration and cannot be a unit test.

- `docs/runbooks/mcp-claude-desktop.md`: mint, paste, restart, verify.
- Walk it, capture evidence, and record what breaks. **Expect this task to find
  something the tests could not** — every milestone in this project that first
  met a real client did.

### Task 6 — ADR 0038, the review, and the docs

- **ADR 0038** owes three decisions and their rejected alternatives: the server
  as an API client, the token as a session rather than a table, and why there is
  no confirm tool.
- `docs/reviews/milestone-5c-review.md`, hunting the failure classes `CLAUDE.md`
  §5 names, plus this milestone's own: **a tool whose output is correct and
  whose description permits a false reading.**
- `docs/PROGRESS.md`, and `docs/spec/AMENDMENTS.md` if A16's "built once, the
  other three are configuration" turns out to be optimistic.

---

## 5. What this plan does not build, deliberately

- **M5d — assisted capture from LinkedIn and Indeed.** It rides on this server
  and is the next slice. Nothing here reaches a third-party site.
- **M5e — the address proposal ladder.** Also rides on this server; sequenced
  after M5c for exactly that reason.
- **Scoped or read-only tokens.** §1 says why.
- **A Streamable HTTP transport, a Desktop Extension (`.mcpb`), or anything
  needing a public URL.** M7, with the deploy, per Q2.
- **Resources and prompts** — MCP has both; this milestone exposes tools only.
  A resource is the right shape for "the corpus" eventually and there is no
  concrete need today (`CLAUDE.md` §8).

## 6. The risk this plan is most likely to be wrong about

**That the tool set is the right one.** Four families were chosen from a list I
proposed, and a tool surface is only really testable by using it. If task 5's
walk shows that the useful question is one these four cannot answer, the
correction belongs in this milestone rather than in a follow-up — a tool nobody
reaches for is a mock that passes its tests (I7).
