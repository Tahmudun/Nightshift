# ADR 0007 — Polling is two-phase and conditional, and queue-driven from the start

- **Status:** accepted
- **Date:** 2026-07-30
- **Milestone:** M1

## Context

The product requires same-day knowledge of any NYC tech opening. With ~2,605
boards in the registry (ADR 0006) and no webhooks available from any provider,
freshness is bought entirely by polling frequency.

M0 fetched one board with `content=true` — every job description in one request.
That is correct for one board and ruinous for thousands.

Measured 2026-07-30 against the `6sense` Greenhouse board:

| Request | Bytes |
|---|---:|
| `/jobs` — listing only | 27,179 |
| `/jobs?content=true` — all descriptions | 840,747 |
| `/jobs/{id}` — one job, with description | 17,932 |

A **31×** difference between listing a board and reading it. The listing
endpoint also returns an `ETag`, supports gzip, and sends
`Cache-Control: max-age=0, private, must-revalidate`.

## Decision

### Two phases

1. **Revalidate.** `GET /jobs` with `If-None-Match`. A `304` ends the poll at
   near-zero cost — no body, no parsing, no writes.
2. **Fetch what changed.** On `200`, diff the listing against stored job ids and
   `updated_at`, then fetch `/jobs/{id}` for new or changed postings only.

`content=true` on a whole board is reserved for a board's first ingestion. Using
it on a routine poll is a bug.

### Two tiers

| Tier | Membership | Interval |
|---|---|---|
| `hot` | produced ≥1 NYC posting in the last 30 days | hourly |
| `warm` | every other `active` board | daily |

Hourly across all boards would be roughly 62,000 requests/day concentrated on a
handful of provider hosts. This lands near 10,000, most of which are `304`s.

Tier membership is **derived from ingested postings** and stored in the database.
It is never hand-set in the registry YAML, and `nyc_presence` in that file is not
consulted for it — a board is hot because of what its jobs said.

**A weekly tier was considered and rejected.** It would mean a company's first
NYC posting could sit unseen for six days, which breaks the one promise the
product makes. Daily on the long tail is the floor.

### Queue-driven

Each board poll is an individual ARQ job, not an iteration inside one long task.
Rate limiting is per-provider-host in `PoliteClient`, so adding boards never
raises the request rate against any one provider.

This is the decision that keeps §10 of `docs/architecture/board-discovery.md`
open: going from 2,605 boards to 100,000 becomes a worker-count question rather
than a rewrite. It costs nothing today — ARQ is already a dependency and already
runs one real task.

## Consequences

**A 304 must not look like an empty board.** Invariant I3 is at risk here in a
new way: a `304` carries no jobs, and code that treats "no jobs in this response"
as "this board has no jobs" would close every listing on every unchanged board.
`FetchOutcome` (ADR 0003) already distinguishes authoritative emptiness from
absence of data, and `304` is neither — it is "unchanged". Fixtures assert that
a `304` produces zero writes of any kind.

**ETags must be stored per board and invalidated on schema change.** A stale
stored ETag combined with a change in how we parse a listing would silently skip
re-parsing. The stored value is namespaced by parser version.

**Providers may not all support this.** Verified on Greenhouse. Ashby and Lever
must be checked when their adapters are built; a provider without ETags simply
falls back to fetching the listing, which is still 31× cheaper than the
alternative.

**Rejected alternative — poll everything hourly with `content=true`.** Simplest
code, roughly 2 GB/hour, and an impolite request volume against providers who
have been generous with unauthenticated access. Getting blocked would end the
project's data supply, and the politeness constraints in §7.3 are not negotiable
for convenience.
