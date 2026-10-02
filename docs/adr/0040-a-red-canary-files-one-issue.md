# ADR 0040 — A red canary files one issue, and closes it when it goes green

- **Status:** accepted
- **Date:** 2026-10-02
- **Milestone:** pick-up (after M5d)
- **Relates to:** ADR 0016 §4 (its notification paragraph is superseded here; the rest stands), `.github/workflows/dependency-canary.yml`, `services/api/constraints-ci.txt`

## Context

ADR 0016 made the canary informational and gave it one channel: GitHub's
default email to the repository owner when a scheduled run fails on the default
branch. "No bot, no issue-filing: one reader does not need a queue."

That was tested by what happened next. The canary went red on 2026-08-31 and
stayed red every Monday through 2026-09-28, five runs in a row, and nobody
read any of it until an audit on 2026-10-02. What it had found was real, and
some of it reached production code paths:

- **SQLAlchemy 2.1** made `Select` variadic, so `Select[Any]` stopped meaning
  "a select" and three multi-column builders stopped type-checking. It also binds
  a bare Python float as `FLOAT`, so the salary floor became
  `numeric >= float8`. Postgres then casts the column, and neither salary index
  can serve the filter. `tests/test_query_plans.py` caught it.
- **mcp 2.2** started treating any exception from a tool other than
  `ToolError` as a crash, and shows the model only "Error executing tool
  search_jobs". The outage message that names the cause and the fix (I3,
  `NightshiftUnavailableError`) never reached Claude.
  `test_an_outage_surfaces_to_the_model_as_a_tool_error` caught it.

Both were fixed on 2026-10-02 and the pin was regenerated. The pin also had
known advisories against pypdf (which parses uploaded resumes), PyJWT and
urllib3. The email had been sent each time. A notification that lands in an
inbox with everything else is easy to never see.

## Decision

The canary stays informational. It still runs only on `schedule` and
`workflow_dispatch`, gates nothing, and no branch protection rule may require
it. What changes is where a red run goes:

1. **A red run opens one issue**, labelled `dependency-canary`, linking the run
   and pointing at its job summary (the drift table). If that issue is already
   open, the run **comments on it** instead. There is never more than one, so it
   is not a queue: it is a single "this is still red" flag that shows on the
   repository page and in the GitHub app.
2. **A green run closes it**, with a comment linking the green run. The flag
   clears itself. A person never has to remember to tidy up after fixing the
   code or regenerating the pin.

The workflow gets `issues: write` and nothing more. The email still arrives too.

## Consequences

- A red canary is visible where the repository is looked at, not only in an
  inbox, and it stays visible until a green run says otherwise.
- The issue thread becomes the record of how long it was red and which runs
  failed. That is the evidence ADR 0016 wanted for "read the diff and decide".
- Cost: one permission and two short steps. If the label is deleted, the next
  red run recreates it (`gh label create --force`).
- Still not done, on purpose: no automatic pin regeneration, no pull requests
  from a bot. Deciding what a red run means is still a person's job (ADR 0016).
