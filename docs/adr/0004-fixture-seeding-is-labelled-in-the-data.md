# ADR 0004 — Fixture-backed seeding is labelled in the data, not just in a doc

- **Status:** accepted
- **Date:** 2026-07-29
- **Milestone:** M0

## Context

Two requirements pull against each other.

`make demo` must work offline from a clean clone, from M0 onward, as a hard
requirement. That means seeded job data cannot come from a live network call.

Invariant I7 says never let a mock become the product, and names the worst
failure mode available: a mock presented as working functionality.

A seed script that loads recorded job data and puts it in the same table as live
data, indistinguishable, is precisely that failure — the demo looks like
production and nothing in the system knows the difference.

## Decision

Fixture data is loaded through the real pipeline but **attributed to a distinct
source row**, so its provenance is a queryable fact rather than a claim in a
README.

- `make seed` uses `FixtureGreenhouseAdapter`, which subclasses the real
  `GreenhouseAdapter` and overrides exactly one method: `fetch_board` reads a
  committed JSON file instead of making a request. `normalize` — where every
  interesting decision lives — is the production code path, unmodified. It is
  constructed with no HTTP client at all, so it cannot make a request even if
  outbound HTTP were enabled.
- Rows it creates belong to a source named `greenhouse_fixture` with
  `source_type = 'fixture'`, a value in the `source_type` enum.
- `GET /sources` reports that type, and the Operate page renders a
  **"committed fixture"** badge in gold next to it. A developer or a viewer can
  see, in the interface, that this data did not come from a live poll.
- `make ingest` runs the same pipeline against the live endpoint, attributed to
  the `greenhouse` source, and refuses to run unless
  `OUTBOUND_HTTP_ENABLED=true`.

The fixture itself is honest about what it is. Every job object in
`tests/fixtures/greenhouse/datadog_board.json` is byte-identical to the live
response; only the *set* of jobs was reduced, from 426 to 10, because committing
5.3MB to exercise a parser is a liability rather than a test.
`datadog_board.meta.json` records the endpoint, the recording date, why each job
was selected, and — importantly — a
`coverage_not_available_on_this_board` list naming the cases the real board did
not contain. `scripts/record_fixture.py` regenerates it and never edits the
contents of a job.

## The internship case

The recorded board contains no internship postings, so
`_extract_employment_type`'s internship branch has no real payload behind it.
Rather than fabricate a "recorded" internship — which would be exactly the mock
wearing a fixture's name — the internship cases are unit tests against the
function directly, in a test class whose docstring says they are synthetic and
why. `docs/PROGRESS.md` lists it under "Not real yet".

## Consequences

- `make demo` is offline by construction rather than by convention: the kill
  switch defaults to off, so a clean clone physically cannot reach the network
  during a seed.
- There is one small amount of duplication: `FixtureGreenhouseAdapter` restates
  the raw-job construction loop. Accepted, because sharing it would mean either a
  seam in the production fetch path or a parameter that makes the real adapter
  able to read from disk.
- When M1 adds Lever and Ashby, each gets the same treatment. The `fixture`
  source type is per-provider by name (`lever_fixture`, `ashby_fixture`).
