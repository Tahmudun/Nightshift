# ADR 0041 — New York is the first market, not the only one

- **Status:** accepted
- **Date:** 2026-10-02
- **Milestone:** pick-up (unblocks M6)
- **Relates to:** `docs/QUESTIONS.md` Q14 (answered by this ADR), A16 (M6, the Archipelago), I1, I3, `nightshift/domain/markets.py`, `nightshift/domain/placement.py`

## Context

The first live pass (2026-08-24) filled the corpus from 32 jobs to 1,200, and
three quarters of it is not New York: 295 roles in New York, 384 remote or
address-unknown, and **521 physically in another city** (San Francisco,
London, Toronto, Miami, Barcelona). Nothing filtered postings by place, M6's
Island had no meaning for "known to be elsewhere", and Q14 asked which of three
products this is: the Island absorbs them, ingestion filters to New York, or
other cities get drawn.

Q14 was answered on 2026-10-02: **filter to New York for now, but New York must
not be the limit.** The other major tech cities are next.

Implementing it turned up one more reason it matters. `placement.py`'s third
rule draws a non-remote role at its employer's confirmed office. With an office
typed in Manhattan, that rule drew the employer's Denver and Vancouver roles on
the Manhattan building (`tests/test_city_routes.py` had a test asserting
exactly that, on a fixture with no New York role in it). Q14's 521 were not
only homeless in the design; given an office, they were placed wrongly.

## Decision

### 1. A market is a named set of cities, and the scope is configuration

`nightshift/domain/markets.py` defines markets: `nyc`, and already the next
ones, `sf-bay-area`, `seattle`, `boston`, `austin`, `los-angeles`, `chicago`,
`washington-dc`, `london` and `toronto`. The `MARKETS` setting (default `nyc`)
says which are on. `MARKETS=nyc,sf-bay-area` turns San Francisco on;
`MARKETS=all` turns the scope off. An unknown key refuses to boot, since a typo
would otherwise look exactly like an empty market.

`nyc` is `NYC_CITY_NAMES`, the codebase's single definition of New York,
reused rather than restated, so polling tiers, discovery and the scope cannot
disagree. Jersey City and Hoboken are therefore outside it; widening New York
is one deliberate change in one place.

### 2. Evaluated when a job is read, never stored

The scope is a SQL predicate over `job_locations`, which ingestion already
writes. Nothing is stored per market. So enabling a market, or defining a new
one, needs no migration, no backfill and no re-poll: the rows are already
there, and so are their match scores (`pending_pairs` scores every open job,
in scope or not).

This is Q14's own caveat honoured more strongly than it asked: it wanted the
filter at the canonical layer rather than the adapter, so turning it off would
be a backfill. Here it is not even that. `source_job_records` and canonical
jobs keep everything every board publishes.

### 3. Hidden only on positive knowledge

A job is out of scope only when **every** location it names is a known city and
none is in an enabled market. A remote role is in scope. So is a role with any
location the parser could not resolve, and a role with no location at all.
"We could not tell where this is" is not evidence that it is elsewhere: the
same temperament as I3, applied to place.

Matching is on the parsed city, casefolded. A state or country the parser
found must be one of the market's; one it did not find does not disqualify.
That keeps Cambridge, Massachusetts apart from Cambridge, United Kingdom, and
London from London, Ontario. The spellings are the parser's (it is the only
writer of `job_locations`), and a test fails if a market and the parser ever
disagree about one.

### 4. Every read path that applies it says what it left out

| Surface | Scope | What it reports |
|---|---|---|
| Search (`GET /jobs`, and MCP `search_jobs` over it) | enabled markets | `excluded_out_of_market`, `markets`; its other excluded counts are taken inside the scope |
| Matches (`GET /matches`) | enabled markets | `excluded_out_of_market` (scored, not listed) |
| Queue, new internships | enabled markets | an `outside_markets` blind spot |
| City (`GET /city/signals`) | **always New York** (`NEW_YORK`) | `excluded_out_of_market` |
| Coverage (`GET /stats`) | reports the scope | in/out counts, and where the rest is, with the market that would show it |

Not scoped: a person's own applications, captures and their jobs, the job
detail page, the company directory and detail (an inventory of what was
ingested), and the operational `/jobs/admin` view.

### 5. The city is a model of New York, whatever MARKETS says

The city draws New York's roles and the placeless ones (the Island), and
nothing else, even with San Francisco enabled or the scope off. It has New
York's basemap, buildings and offices, and placement's third rule would
otherwise draw an SF role on its employer's Manhattan office. When other cities
are drawn (Q14's third option, M12's territory), each gets its own scope the
same way.

## Consequences

- The numbers on every screen describe New York again, and every screen that
  scopes says how much it left out, so the scope cannot read as a thin market.
- M6's Island means exactly what A16 said: remote and address-unknown roles.
  "Known to be elsewhere" has a home now, and it is not the Island.
- Turning on the next city is a one-line `.env` change, visible immediately,
  and the coverage page names which market each out-of-scope role would join.
- Known limits, recorded rather than solved:
  - A remote role is in scope whatever its country, so "Remote (Canada)"
    shows. A remote-country rule is a separate decision.
  - Market membership is by city name, so a suburb not listed is "elsewhere"
    until it is added to its market (the coverage page shows the city name).
  - A role naming a New York location and a remote one is in scope, as is a
    role naming Denver and something unparseable; both by design (§3).
