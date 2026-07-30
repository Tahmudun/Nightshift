# ADR 0003 — `FetchOutcome.ok` carries the I3 distinction

- **Status:** accepted
- **Date:** 2026-07-29
- **Milestone:** M0

## Context

Invariant I3: never silently close a listing. A source returning an error, a
timeout, or an empty array is not evidence a job closed.

The subtle half of that sentence is "or an empty array". Two situations produce
zero jobs from an adapter and they mean opposite things:

- The board responded and has no open postings. Evidence. Those jobs really are
  gone.
- The board timed out, 500'd, 404'd, or returned malformed JSON. Not evidence of
  anything. We learned nothing.

If an adapter's signature is `async def fetch_jobs(...) -> list[RawJob]`, those
two cases are indistinguishable at the call site. The pipeline sees `[]` and has
no way to know which happened. That is not a bug you fix with care at the call
site — it is missing information, and the first plausible-looking closure loop
someone writes will close every job on a board that was briefly down.

## Decision

`fetch_board` returns a `FetchOutcome`, never a bare list, and **never raises**
for an unreachable source:

```python
class FetchOutcome(BaseModel):
    board: BoardRef
    ok: bool
    jobs: tuple[RawJob, ...] = ()
    http_status: int | None = None
    error: str | None = None

    @property
    def is_authoritative_empty(self) -> bool:
        return self.ok and not self.jobs
```

`ok=False` means "we learned nothing about these jobs" and the pipeline must not
touch their state. `is_authoritative_empty` is the only property that may ever be
read as evidence of closure — and it is deliberately a named property rather than
an inline `if not jobs`, so the claim is legible in a diff.

Not raising matters as much as the return type: one bad board must not abort a
run over the others, and the failure has to become a row in `ingestion_runs`
rather than a traceback.

Every failure inside the HTTP client funnels into a single exception type,
`SourceUnavailableError`, because the required behaviour is identical for a
timeout, a 503, and a truncated body. Even the offline kill switch
(`OUTBOUND_HTTP_ENABLED=false`) raises a subclass of it, so a disabled network
degrades through exactly the same path as a real outage.

At the database level, `ingestion_runs.status` distinguishes `partial` from
`failed`, and the `jobs` table has a check constraint that a closed job has a
`closed_at` and an open one does not — so an inconsistent transition is a
database error rather than data.

## Consequences

- M0's `records_closed` counter is hardcoded to zero and the closure state
  machine does not exist yet. That is honest: closing a job requires the
  consecutive-miss tracking that M1 builds. The column and the counter are
  present so M1 adds logic rather than schema.
- Six tests in `tests/test_greenhouse_adapter.py::TestInvariantI3` cover 404,
  timeout, 503, malformed JSON, a 200 of the wrong shape, and the genuine empty
  board. The last one matters: without it the invariant could be satisfied by
  never trusting anything, and a board that really emptied would never close.
- Adapters are slightly more verbose to write. Worth it.
