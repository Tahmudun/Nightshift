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

### I2 — an inferred fact is labelled where it is read, and none is read here

The rule is: anything `inferred_pending_confirmation` says so in its own object,
and Claude may report it as unconfirmed but never as fact.

**No tool in this slice reaches one**, and that is worth stating rather than
leaving as an unexplained silence in the task list. The four chosen families
touch jobs, matches, applications and captures; the inferred facts live on the
profile, behind `get_profile`, which is not built here. `UserSkill` is
confirmed-by-construction — its docstring says *"A skill the user confirmed.
Never a proposal (invariant I2)"* — so `explain_match`'s evidence rows cannot
carry one either.

**So I2 has no surface in M5c and gets no task.** It acquires one the moment
`get_profile` is built, and whoever builds it owes the labelling above. Recorded
here so that its absence from §5 reads as a decision rather than an oversight.

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

## 4. The files, and what each one is responsible for

Six new modules, three touched. **`nightshift/mcp/` is four small files rather
than one**, because the boundary between them is the boundary this milestone is
about: `client.py` is the only thing that speaks HTTP, `shapes.py` is the only
thing that decides what a qualifier means, and `server.py` may do neither.

| File | Responsible for | May import |
|---|---|---|
| `nightshift/mcp/__init__.py` | Nothing. The package marker | — |
| `nightshift/mcp/client.py` | The authenticated HTTP client. The only module that knows a URL | `httpx` |
| `nightshift/mcp/shapes.py` | Turning API JSON into tool results with their qualifiers attached. **Pure** — no I/O, no network, no clock | `nightshift.db.base` enums **only** |
| `nightshift/mcp/server.py` | The tool functions and their descriptions | `client`, `shapes`, `mcp` |
| `nightshift/mcp/__main__.py` | The stdio entry point, stderr logging, and reading config from the environment | `server` |
| `nightshift/domain/identity.py` | *(touched)* `origin`/`label` on `create_session`; `MCP_TOKEN_LIFETIME` | — |
| `nightshift/db/models.py` | *(touched)* two columns on `UserSession` | — |
| `nightshift/cli.py` | *(touched)* the `tokens` command | — |

**`shapes.py` importing `nightshift.db.base` is the one exception to §1's rule**
and it is deliberate: `LocationConfidence` is an enum of five members, and the
`means` table must be **exhaustive over it** so a sixth member cannot ship
without a sentence. Importing the enum is how that becomes a test rather than a
hope. `nightshift.db.base` holds enums and no engine, no session and no model —
task 2's import guard bans `nightshift.db.session` and `nightshift.db.models`,
not the whole package, and says why in the test.

---

## 5. Tasks

Each ends runnable and testable. Commits are scoped (`feat(mcp): …`).

### Task 1 — the credential

**Files**
- Modify: `services/api/nightshift/db/base.py` (a `SessionOrigin` enum)
- Modify: `services/api/nightshift/db/models.py` (`UserSession.origin`, `.label`)
- Create: `services/api/migrations/versions/<rev>_session_origin_and_label.py`
- Modify: `services/api/nightshift/domain/identity.py`
- Modify: `services/api/nightshift/cli.py`
- Test: `services/api/tests/test_mcp_tokens.py`, and the existing
  `tests/test_identity.py` for `create_session`'s new arguments

**Produces**, for tasks 2–5:

```python
class SessionOrigin(enum.StrEnum):
    BROWSER = "browser"
    MCP = "mcp"

MCP_TOKEN_LIFETIME = timedelta(days=365)

async def create_session(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
    lifetime: timedelta = SESSION_LIFETIME,
    origin: SessionOrigin = SessionOrigin.BROWSER,   # new
    label: str | None = None,                        # new
) -> IssuedSession: ...
```

`resolve_session` is **not** changed. That is the point of the design — one
resolve path — and a diff that touches it means the design slipped.

Steps:

- [ ] **1.1** Write the failing test: a session created with
      `origin=SessionOrigin.MCP` resolves through the same `resolve_session` as a
      browser one, and `UserSession.origin` round-trips. Run it; expect a
      `TypeError` on the unexpected keyword.
- [ ] **1.2** Add `SessionOrigin` to `db/base.py` beside `CredentialMethod`,
      with a docstring saying why these are one table (§1).
- [ ] **1.3** Add the two columns to `UserSession`. `origin` not-null with a
      server default of `browser`, so the migration does not have to invent a
      value for existing rows; `label` nullable.
- [ ] **1.4** `alembic revision --autogenerate`, then **read the generated file
      and fix it by hand** — autogenerate does not create a PG enum type in the
      right order. Downgrade must drop the column *and* the type.
- [ ] **1.5** Test the migration **both directions** against a real database
      (§7): `alembic upgrade head`, `downgrade -1`, `upgrade head`.
- [ ] **1.6** Thread `origin` and `label` through `create_session`; add
      `MCP_TOKEN_LIFETIME` beside `SESSION_LIFETIME` with its reasoning comment.
      Run 1.1; expect PASS.
- [ ] **1.7** Write the failing tests for the CLI: `--list` prints neither a
      token nor a hash; revoking an MCP token leaves a browser session live, and
      the reverse; `--create` prints the token exactly once.
- [ ] **1.8** Implement `cmd_tokens` in `cli.py` following `cmd_users`'s shape —
      `session_scope()`, print to stdout, errors to stderr, return an int.
      Register in `COMMANDS` and add the subparser.
- [ ] **1.9** `make check`. Commit.

**The output that matters**, because task 5 pastes it:

```
$ nightshift tokens --email you@example.com --create --label "claude desktop"
  token (shown once — it cannot be recovered):

    nsk_live_<...>

  add this to claude_desktop_config.json:

  { "mcpServers": { "nightshift": {
      "command": "…/.venv/bin/python", "args": ["-m", "nightshift.mcp"],
      "env": { "NIGHTSHIFT_API_URL": "http://localhost:8000",
               "NIGHTSHIFT_MCP_TOKEN": "nsk_live_<...>" } } } }
```

### Task 2 — the server, the transport, and the guard rails

**Files**
- Modify: `services/api/pyproject.toml` (`mcp>=2.0`)
- Modify: `services/api/constraints-ci.txt` (**by `make constraints`, same commit**)
- Create: the four `nightshift/mcp/` modules
- Test: `services/api/tests/test_mcp_server.py`, `tests/test_mcp_boundaries.py`

**Produces**, for tasks 3–4:

```python
# client.py
class NightshiftUnavailableError(RuntimeError):
    """The API could not be reached. Never raised for an empty result."""

class NightshiftClient:
    def __init__(self, base_url: str, token: str, *,
                 http: httpx.AsyncClient | None = None) -> None: ...
    async def get(self, path: str, **params: Any) -> dict[str, Any]: ...
    async def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]: ...
```

`http` is injectable **so the tests can hand it an `ASGITransport` pointed at the
real FastAPI app** — real routes, real `require_session`, real auth, no network
and no port. That is the seam this milestone is tested through.

Steps:

- [ ] **2.1** Add `mcp>=2.0` to `pyproject.toml`; run `make constraints`; commit
      both together. **Verify the constraints diff is non-empty before
      committing** — this is ADR 0016 §3's failure and it has no local signal.
- [ ] **2.2** Confirm the v2 import surface against the installed package
      (`python -c "from mcp.server import MCPServer"`). The SDK went 1.x → 2.0
      and this plan was written from documentation, not from the wheel.
- [ ] **2.3** Write the failing boundary tests — both, before any server code:

```python
def test_the_mcp_package_never_reaches_the_database() -> None:
    """§1: the MCP server is a client of the API, not a second door into it.

    `nightshift.db.base` is allowed and `session`/`models` are not. The enums
    are a vocabulary; the engine and the tables are the door.
    """
    import nightshift.mcp  # noqa: F401
    banned = {"nightshift.db.session", "nightshift.db.models"}
    loaded = banned & set(sys.modules)
    assert loaded == set(), f"the MCP package imported {sorted(loaded)}"


@pytest.mark.asyncio
async def test_a_tool_call_writes_nothing_to_stdout(capsys) -> None:
    """§3: on stdio the protocol *is* stdout. One log line kills the session."""
    ...  # drive a whoami call through an in-memory MCP client
    assert capsys.readouterr().out == ""
```

      The first must be run in a **fresh interpreter** (`subprocess`), because
      pytest has already imported half the codebase — a test that reads a dirty
      `sys.modules` is a test that cannot fail.
- [ ] **2.4** Write `client.py`. `httpx.AsyncClient` with
      `Authorization: Bearer`; `httpx.ConnectError`/`ConnectTimeout` →
      `NightshiftUnavailableError` naming the URL and `make dev`.
- [ ] **2.5** Write `server.py` with **one** tool, `whoami`, calling `GET /auth/me`.
- [ ] **2.6** Write `__main__.py`: read `NIGHTSHIFT_API_URL` and
      `NIGHTSHIFT_MCP_TOKEN`, fail loudly on stderr if either is absent, pin
      logging to stderr, run stdio.
- [ ] **2.7** Write the protocol test: an in-memory MCP client completes the
      handshake, lists tools, calls `whoami`, and gets back the account the
      token belongs to. Run 2.3 and 2.7; expect PASS.
- [ ] **2.8** `make check`. Commit.

### Task 3 — the read tools

**Files**
- Modify: `nightshift/mcp/shapes.py`, `server.py`
- Test: `tests/test_mcp_shapes.py`, `tests/test_mcp_read_tools.py`

**Produces:**

```python
# shapes.py
CONFIDENCE_MEANS: dict[LocationConfidence, str]   # exhaustive over the enum
def location_result(text: str | None, confidence: LocationConfidence,
                    coordinates: tuple[float, float] | None) -> dict[str, Any]: ...
```

Four tools: `search_jobs`, `get_job`, `list_applications`, `explain_match`.

Steps:

- [ ] **3.1** Write the failing exhaustiveness test — the one that makes §3's
      rule structural rather than remembered:

```python
def test_every_location_confidence_has_a_sentence() -> None:
    """I1 lives in the description here, not in a constraint. A sixth enum
    member shipping without a sentence is how a reader gets told a `city_only`
    job is at a street address."""
    assert set(CONFIDENCE_MEANS) == set(LocationConfidence)
    for value, sentence in CONFIDENCE_MEANS.items():
        assert sentence.strip(), value
```

- [ ] **3.2** Write `CONFIDENCE_MEANS` and `location_result`. Run; expect PASS.
- [ ] **3.3** Write the failing test that **no coordinate ships bare**: over
      every read tool's output, any object with a `coordinates` key also has
      `confidence` and `means`. Walk the result recursively rather than checking
      one known path — a tool added at M5d must trip this too.
- [ ] **3.4** Write the failing test that **no tool but `explain_match` returns a
      score** (I4), asserted over the registered tool list.
- [ ] **3.5** Write the failing outage test: a client pointed at a closed port
      **raises `NightshiftUnavailableError`** and does not return `[]`. This is
      I3 on a new surface and it is the one that will actually happen.
- [ ] **3.6** Write the failing isolation test using M5b's **enumerating**
      pattern — every tool, against a second user's data, rather than one spot
      check.
- [ ] **3.7** Implement the four tools against the existing routes. Run all;
      expect PASS.
- [ ] **3.8** `make check`. Commit.

### Task 4 — capture

**Files**
- Modify: `nightshift/mcp/server.py`
- Test: `tests/test_mcp_capture.py`

Steps:

- [ ] **4.1** Write the failing test that **no confirm tool exists**, asserted
      over the registered tool list so a future addition trips it:

```python
@pytest.mark.asyncio
async def test_no_tool_can_confirm_a_capture() -> None:
    """I5, and the whole of M5a. Approving `confirm_capture` in a dialog is not
    reviewing a parsed title, a company and a location string."""
    names = {t.name for t in await client.list_tools()}
    assert not [n for n in names if "confirm" in n or "approve" in n]
```

- [ ] **4.2** Write the failing test that `capture_posting` leaves the capture
      `pending` and creates **no** job.
- [ ] **4.3** Write the failing test that the same posting captured twice
      creates no duplicate — M5's acceptance names this in as many words.
- [ ] **4.4** Implement `capture_posting` against `POST /capture`, returning the
      proposal and the confirm URL. Run; expect PASS.
- [ ] **4.5** `make check`. Commit.

### Task 5 — the connection, walked in Claude Desktop

The acceptance criterion is *"Claude Desktop connects and captures a posting end
to end"*. It is a live integration and cannot be a unit test.

- [ ] **5.1** Write `docs/runbooks/mcp-claude-desktop.md`: mint, paste, restart,
      verify, revoke.
- [ ] **5.2** Walk it against a real Claude Desktop with `make dev` running.
- [ ] **5.3** Capture evidence: the tool list, a search, and a capture appearing
      in the web UI as `pending`.
- [ ] **5.4** Walk it again with the API **stopped**, and confirm the failure
      message names the cause and the fix rather than returning nothing.
- [ ] **5.5** Record what broke. **Expect this task to find something the tests
      could not** — every milestone here that first met a real client did.

### Task 6 — ADR 0038, the review, and the docs

- [ ] **6.1** ADR 0038, owing three decisions with their rejected alternatives:
      the server as an API client, the token as a session rather than a table,
      and why there is no confirm tool.
- [ ] **6.2** `docs/reviews/milestone-5c-review.md`, hunting `CLAUDE.md` §5's
      failure classes plus this milestone's own: **a tool whose output is
      correct and whose description permits a false reading.**
- [ ] **6.3** `docs/PROGRESS.md`; `AMENDMENTS` only if A16's *"built once, the
      other three are configuration"* turns out to be optimistic.
- [ ] **6.4** `make check`, `make acceptance`, push, open the PR, watch CI.

---

## 6. What this plan does not build, deliberately

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

## 7. The risk this plan is most likely to be wrong about

**That the tool set is the right one.** Four families were chosen from a list I
proposed, and a tool surface is only really testable by using it. If task 5's
walk shows that the useful question is one these four cannot answer, the
correction belongs in this milestone rather than in a follow-up — a tool nobody
reaches for is a mock that passes its tests (I7).
