# ADR 0038 — The Open Hand goes through its own front door

- **Status:** accepted
- **Date:** 2026-08-21
- **Milestone:** M5c
- **Relates to:** `CLAUDE.md` §1 (I1–I5), §2 ("Not yet: … LLM API"), §3, §8; AMENDMENTS A9, A16; ADR 0016 §2, ADR 0037; `nightshift/mcp/`, `nightshift/api/deps.py`, `nightshift/domain/identity.py`

## Context

A16 re-cut the milestones around one observation:

> Four separate-looking asks — reading LinkedIn/Indeed, "link the app to
> Claude", AI rejection analysis, and a voice assistant — are **one MCP server**
> exposing this domain to Claude. Built once, the other three are configuration
> and UI.

MCP — the Model Context Protocol — is a standard way for a desktop AI
application to call functions inside somebody else's software. Nightshift
defines a set of tools; Claude Desktop discovers them and can call them
mid-conversation.

**Nightshift does not call a model, and this ADR does not change that.**
`CLAUDE.md` §2 still lists "LLM API" under *not yet*. The model is the user's
own Claude subscription; this server supplies deterministic evidence and Claude
narrates it. That is why the AI in this product costs nothing to run, and a
server-side inference path stays deferred until there is revenue for it.

Three decisions had to be made before any code, and each had a plausible
alternative that this ADR rejects with a reason.

## Decision

### 1. The MCP server is a client of the API. It never touches the database.

`nightshift/mcp/` may import `httpx`. It may not import
`nightshift.db.session`, `nightshift.db.models`, or SQLAlchemy.

The rejected alternative was the obvious one: the server already runs in the
same repository, on the same machine, with the same models available — reading
Postgres directly is one fewer hop and one fewer moving part.

**It is rejected because of what M5b just finished doing.** ADR 0037 made data
isolation *structural* rather than conventional. `require_session` is attached
once, in `main.py`, to every router but `/health` and `/auth`, so a route is
protected **because it exists**. `deps.py` says what that was for:

> A route added in M5c, M8 or M13 is behind a session because it exists, and
> opening one is a deliberate edit to `main.py` that shows up in a diff.

A second door into the domain — one that opens a session, queries `Job`, and
filters by `user_id` because the author remembered to — is precisely the
arrangement M5b spent a milestone replacing. Building it in the *next*
milestone, in the component whose whole purpose is to expose the domain to an
outside program, would be the worst possible place to reintroduce it.

Every rule this product has lives at the HTTP boundary: I5's two-step in
`capture.py`, per-user scoping in every route, default-deny in `main.py`. The
MCP server goes through that boundary like any other client. `deps.py`
anticipated it:

> The cookie is how a browser actually carries the token, but a bearer token is
> the form a non-browser client — `scripts/verify.py`, and M5c's MCP server —
> can use.

**The cost is one HTTP hop to localhost**, which is nothing, and it buys one
place where isolation can be wrong — the place that already has an enumerating
test standing over it.

**The rule is enforced, not stated.** `test_mcp_boundaries.py` runs a fresh
interpreter, imports `nightshift.mcp`, and fails if any banned module appears
in `sys.modules`. It has to be a subprocess: pytest has already imported most
of this codebase before the first test runs, so the same check in-process
would pass unconditionally — which is worse than not having it.

`nightshift.db.base` is the one permitted import. It holds enums and no engine,
no session, no model, and `shapes.py` reads `LocationConfidence` from it so the
confidence table can be asserted exhaustive over the enum. The enums are a
vocabulary; the engine and the tables are the door.

### 2. stdio now, and the tools do not know what a transport is

Claude Desktop launches the server as a subprocess and speaks JSON-RPC over its
standard input and output. No port, no certificate, no public URL, no OAuth.

Streamable HTTP is what a *deployed* server would use, and `mcp` 2.0.0 supports
it. It is not what this milestone builds, for a reason that is recorded rather
than assumed: **Q2 and Q10 were both answered on 2026-08-21** with "future
concerns, I want things polished first", which puts the domain, the certificate
and the email sender at M7. A remote connector needs all three plus OAuth 2.1.
stdio needs none of them, and it keeps `make demo` offline — a hard requirement
since M0 and the property A9 made structural.

So `server.py` builds tools that know nothing about transports and
`__main__.py` binds stdio. Adding Streamable HTTP at M7 is a second entry
point, not a rewrite.

**The trap this decision carries, recorded because it produces no error
message:** on stdio the transport *is* stdout. One stray `print`, one logging
handler left on the default stream, and the JSON-RPC framing is corrupt. The
symptom is Claude Desktop reporting that the server failed, with nothing useful
in any log a person thinks to open. `__main__.py` pins every handler to stderr
with `force=True` — `basicConfig` alone is a no-op if any earlier import
already added a handler — and a test drives the module through a real pipe and
asserts every line of stdout parses as a JSON-RPC frame.

### 3. The credential is a session that grew a name, not a new table

`user_sessions` gains `origin` (a `session_origin` enum: `browser | mcp`) and
`label`. Migration `0025`.

Three options were weighed:

| | Cost |
|---|---|
| Paste a browser session token into the config | Expires in 30 days and **breaks silently** — the person sees "the tool stopped working", not "your token expired" |
| A new `user_api_tokens` table | A second identity-resolution path, in the milestone after the one that got it to one |
| **`origin` and `label` on `user_sessions`** ← chosen | One migration, two columns, one resolver |

**The third wins because the two things are the same thing.** A session is a
proven identity with a lifetime. An MCP token is a proven identity with a
longer lifetime and a name. `create_session` already took `lifetime`;
`resolve_session` already existed and was already the only function that
answers "who is this". `origin` is a **label on the answer, never a second way
to reach it** — nothing branches on it to decide whether a request is
authenticated, and a future caller that does has rebuilt what this decision
avoided.

`MCP_TOKEN_LIFETIME` is a year against `SESSION_LIFETIME`'s thirty days. That
is not a relaxation of a security rule but a different rule for a different
object: thirty days is right for a browser, where signing in again costs a
password field, and wrong for a file on disk that a person edits once. A token
expiring quarterly is a feature somebody stops using.

**What makes a year acceptable is stated rather than glossed: an MCP token has
exactly the same power as a browser session.** It is not scoped, not read-only,
not restricted by tool. It sits in a plaintext config file at the machine's
trust level. Scoped tokens are a real feature and they are not this milestone;
the honest mitigation at one user on one machine is **revocability somebody can
aim**, which is what `label` buys and what `nightshift tokens --list` exposes.
A second table pretending the credential is weaker would be a lie told in a
schema.

**Every session token now starts with `nsk_`, browser sessions included.** The
entropy is unchanged and the prefix carries no secrecy; `.gitleaks.toml` gained
a rule for it, so a token pasted into a commit, an issue or a log goes red in
CI instead of looking like base64. It is on both kinds because they are one
kind — a scanner that found only half the credentials this system mints would
be worse than none, because it would be trusted. Existing sessions are
unaffected: a stored row holds the SHA-256 of whatever string was minted.

### 4. There is no confirm tool, and there will not be one

Claude can search, read, explain, and **create a pending capture**. It cannot
confirm a capture, change an application stage, promote an inferred profile
fact, or apply to anything.

The argument for a confirm tool is not stupid: Claude Desktop shows the user an
approval dialog before every tool call, so a human *did* approve. **It is wrong,
and the difference is the whole of M5a.** Approving "call `confirm_capture`" is
not reviewing a parsed job title, a company name and a location string.
`capture.py` already recorded what is at stake:

> a one-shot endpoint that parses and commits in the same request […] makes the
> parser's reading indistinguishable from a person's decision, at exactly the
> point where the difference decides whether a job lands on the right building.

An MCP confirm tool is that one-shot endpoint with an extra process in the
middle. The two-step is the feature; it does not get an exception because the
caller is fluent. `capture_posting` creates the same `pending` row the paste
form creates and returns the URL where a person confirms it, and a test asserts
over the registered tool list that no tool named `confirm` or `approve` exists,
so a future addition trips it rather than sliding in.

## Consequences

**A failure class this repository has not had before.** Every earlier milestone
could hold I1 and I4 in a database constraint, a type, or a test. This one
cannot, because the consumer is a language model rather than a renderer. If a
result carries `location_confidence: "city_only"` and the description does not
say what that licenses a reader to claim, Claude will write *"this role is at
620 8th Avenue"* — fluently, confidently, and falsely.

**So a tool description is not documentation. It is the last place an invariant
can be enforced**, and it is reviewed as code. The schema stops a coordinate
arriving bare; only the description stops it being *read* as a street address.
Every location result carries a `means` field — one plain sentence, per row,
where a model reading one result cannot miss it — and the table of them is
asserted exhaustive over `LocationConfidence` so a sixth member cannot ship
without one.

**I3 arrives on a new surface and it is the one that will actually happen.**
Claude Desktop launches this server whether or not `make dev` is running. If an
unreachable API produced `[]`, Claude would say "there are no backend
internships open in New York" — I3's exact failure, in a sentence a person
would believe. So `NightshiftUnavailableError` is raised and never swallowed,
and its message names the cause and the fix.

**I2 has no surface in M5c**, and that is recorded so its absence reads as a
decision. The four tool families touch jobs, matches, applications and
captures; inferred facts live on the profile, behind a `get_profile` that is
not built. `UserSkill` is confirmed by construction. Whoever builds
`get_profile` inherits the labelling rule.

**ADR 0016 §2's platform split widened, and it now bites a developer rather
than only CI.** `mcp` depends on `cryptography`, which pins at a version with
no macOS x86_64 wheel — so the pinned set that CI installs cannot be installed
on this machine at all, and local development runs an older `cryptography`.
That is the same shape as onnxruntime, which §2 already documents, and the same
answer: **the pin covers CI and not a developer's machine.** It is a live cost
of an Intel Mac, not a defect to fix.

**M5d and M5e get cheaper, which was A16's whole claim.** Assisted capture from
LinkedIn/Indeed and the office-address proposal ladder are both tools on this
server. Whether "built once, the other three are configuration" survives
contact with M5d is not yet known, and this ADR does not claim it does.
