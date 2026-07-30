# ADR 0005 — Discovered boards are approved in batches, not one at a time

- **Status:** accepted
- **Date:** 2026-07-30
- **Milestone:** M1
- **Overrides:** AMENDMENTS A1, "Emit a registry entry for human review. Never auto-commit."

## Context

A1 requires that every candidate board token is reviewed by a human before it
enters `data/board-registry.yaml`. That was written when the registry was
expected to be curated — the amendment's own example is a handful of companies.

The product goal changed the shape of the problem. The human's requirement is
that any tech role opening in NYC is known the day it appears, from any employer.
Curation cannot reach that: it is bounded by the reviewer's patience, which is a
few hundred entries at the very most.

Measured 2026-07-30 against Common Crawl `CC-MAIN-2026-30`: **2,605 distinct
board tokens** are discoverable immediately, from one monthly crawl and one URL
pattern per provider. Unioning further crawls grows it.

A1's rule, applied literally to 2,605 entries, is a review step that will not be
performed. A control nobody executes is worse than a weaker control that runs,
because the documentation still claims the strong one.

Against that: the rule is protecting something real. The discovered token
`a3c41b8b71eff8c4` returns HTTP 200 with 10 well-formed postings. Every
automated liveness check passes it. It is plainly not a company, and under a
fully automatic policy its jobs would enter the corpus attributed to an employer
that does not exist — a direct I2 violation.

Discovery also cannot name every employer from the provider alone. Ashby exposes
no company name anywhere in its API. And the token is not the name: Ashby's `0g`
is "0g Labs". Deriving an employer from its slug would be inventing a fact.

## Decision

The human gate is kept and moved from per-entry to per-batch, with a typed
exception path.

`validate` assigns every candidate exactly one verdict:

| Verdict | Condition | Route |
|---|---|---|
| `live_named` | 200, ≥1 posting, employer name obtained **from the provider** | Bulk approval |
| `live_unnamed` | 200, ≥1 posting, no name obtainable | Individual review |
| `name_collision` | Normalises onto an existing company | Individual review |
| `empty` | 200, zero postings — authoritative, not an error | Stays a candidate |
| `unreachable` | Non-200, timeout, unparseable | Stays a candidate |

- Only `live_named` is bulk-approvable, and it requires the employer's name to
  have come from the provider by the route established for that provider —
  Greenhouse's board metadata endpoint, Ashby's board page title, or, for Lever,
  the domain the careers-page probe started from. Never the token string.
- `make registry-approve` writes the registry from approved candidates. Nothing
  else writes it. A human reads the resulting git diff and commits, so "never
  auto-commit" holds literally.
- The approval report is ordered by NYC posting count, so review attention lands
  on the boards that affect the product and the tail can be skimmed.
- `empty` and `unreachable` are **not rejections**. Nothing is ever discarded;
  both re-validate on the next run. Discarding them would repeat, at the registry
  level, the mistake I3 forbids at the listing level — treating absence of data
  as data.

## Consequences

**Accepted risk.** A `live_named` board can still be junk if a provider reports
a plausible-looking name for a board that is not a real employer. The batch diff
is the only thing standing between that and the corpus. This is a genuine
weakening of A1 and is the price of a registry that can grow past a few hundred.

**Mitigation that must not be dropped.** The `a3c41b8b71eff8c4` case is a
committed validation fixture asserting it classifies `live_unnamed` and cannot
reach the bulk path. If that test is ever deleted or weakened, this ADR's
reasoning no longer holds and the gate is decorative.

**Rejected alternative — review every candidate.** Honest to A1's letter, and it
caps the registry at whatever the reviewer tolerates. It makes the stated product
goal unreachable while appearing to comply.

**Rejected alternative — no gate at all.** Fastest and broadest. Puts
`a3c41b8b71eff8c4` and everything like it into the corpus with a fabricated
employer, contradicting both A1 and I2.

**Revisit if** the exception classes grow large enough to be skipped in turn. The
gate's value is that `live_unnamed` and `name_collision` stay small enough to read.
