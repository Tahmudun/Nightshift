# M5c task 5 — the MCP server driven over real stdio against a live API

Recorded 2026-08-21. Not Claude Desktop — a real subprocess, real pipes, a
real MCP client, a real token from `nightshift tokens`, and a real uvicorn.
Everything up to the desktop app itself.

## With the API running

```
CONNECTED to nightshift
  instructions: 1042 chars
TOOLS (6):
  - whoami: Return the Nightshift account this connection is authenticated as. Use...
  - search_jobs: Search open New York technology jobs in Nightshift's corpus. Returns m...
  - get_job: Read one job posting in full: its description, its locations with thei...
  - explain_match: Why Nightshift scored a job the way it did for this reader. The ONLY t...
  - list_applications: The reader's own application pipeline: which jobs they saved or applie...
  - capture_posting: Save a job posting the reader found somewhere Nightshift does not inge...
WHOAMI: dev@nightshift.local
SEARCH_JOBS: 3 of 10
  - Software Engineer Internship, Android @ Ramp
      confidence=city_only coords=None
      means: The posting names a city and nothing finer. Nightshift does not know where in th...
  - GTM Systems Engineer, Salesforce @ Ramp
      confidence=city_only coords=None
      means: The posting names a city and nothing finer. Nightshift does not know where in th...
  - Staff Software Engineer, iOS @ Ramp
      confidence=city_only coords=None
      means: The posting names a city and nothing finer. Nightshift does not know where in th...
EXPLAIN_MATCH: 30/100 ruleset=3+2026-08-09.1 components=6 eligibility=eligible
LIST_APPLICATIONS: 5 tracked
CAPTURE_POSTING: status=pending
  proposed: {"title": "Senior Platform Engineer", "company_name": "Stripe", "location_text": "New York, NY", "employment_type": null}
  could_not_read: ['employment_type']
  review_url: http://localhost:3000/operate/capture
OUTAGE CHECK (stopping is not possible here; using a bad job id):
  is_error=True content=[TextContent(type='text', text='Error executing tool get_job: Nightshift answered 404 for GET /jobs/
```

## With the API stopped — invariant I3

The server still starts, because Claude Desktop launches it whether or not
`make dev` ran. An unreachable API is a tool **error**, never an empty list.

```
The server still started with the API down — as it must,
because Claude Desktop launches it whether or not make dev ran.

search_jobs is_error = True
structured_content = None

what the model is told:
  Error executing tool search_jobs: Nightshift's API is not reachable at http://localhost:8000. Start it with `make dev` in the Nightshift repository, then try again. No conclusion should be drawn about the corpus from this failure.
```

## The credential's whole life, against the real database

```
$ nightshift tokens --email dev@nightshift.local --create --label "m5c walk"
  token (shown once — it cannot be recovered):
    nsk_… (redacted here; it was printed once and is now revoked)
  add this to claude_desktop_config.json, then restart Claude Desktop:
  { "mcpServers": { "nightshift": { "command": ".../.venv/bin/python",
      "args": ["-m", "nightshift.mcp"],
      "env": { "NIGHTSHIFT_API_URL": "http://localhost:8000",
               "NIGHTSHIFT_MCP_TOKEN": "nsk_…" } } } }

$ nightshift tokens --email dev@nightshift.local --list
  1 live MCP token(s) for dev@nightshift.local:
    e12ea415-a04e-4865-bd29-54357361b854  m5c walk  expires 2027-08-21

$ nightshift tokens --email dev@nightshift.local --revoke e12ea415-…
  revoked e12ea415-a04e-4865-bd29-54357361b854

$ nightshift tokens --email dev@nightshift.local --list
  dev@nightshift.local has no live MCP tokens
```

The listing prints an id, a label and an expiry — never a token and never a
hash. And the revoked token is genuinely dead: the same tool call that worked a
minute earlier now returns

```
Error executing tool search_jobs: Nightshift rejected this token. Mint a new
one with `nightshift tokens --email <you> --create --label 'claude desktop'`,
paste it into claude_desktop_config.json, and restart Claude Desktop.
```

which names the fix rather than the fault.

## What this does and does not prove

**Proved:** the transport, the handshake, tool discovery, the bearer token
against `require_session`, all six tools against real data, a capture landing
as `pending` with `job_id IS NULL`, an unreachable API surfacing as an error
rather than an empty list, a revoked token being refused, and the CLI's whole
credential lifecycle.

**Not proved:** that Claude Desktop itself connects, and that a model reading
these descriptions actually says "in New York, address unknown" rather than
inventing a street. **The second is the real acceptance criterion**, because it
is the one this milestone's new failure class lives in — a result can be
correct and its reading false — and no test in this repository can check it.
That needs a person, a desktop app, and a conversation.
