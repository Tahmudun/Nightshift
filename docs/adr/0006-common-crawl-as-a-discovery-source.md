# ADR 0006 — Board tokens are harvested from Common Crawl, which is structurally blind to Lever

- **Status:** accepted
- **Date:** 2026-07-30
- **Milestone:** M1

## Context

AMENDMENTS A1 established that no ATS provider exposes a way to enumerate its
customers, and proposed a token resolution pipeline: probe a company's careers
page for an embedded board. That works, but it is chicken-and-egg — it needs a
list of companies to start from, and it costs one or more requests per company
against sites that never asked to be probed.

The registry needs to reach thousands of entries for the product goal to be met
(ADR 0005).

## Decision

Primary discovery is **harvesting board URLs from Common Crawl's public URL
index**, validated against each provider's own API.

Common Crawl is a public archive of the web, free, no key, no account. Querying
its index is not crawling the ATS providers — we never fetch their pages for
discovery, only their documented APIs for validation.

A1's careers-page probe is kept as a second front-end rather than replaced. It
covers what the archive misses, and it is the only route to Lever.

## Measured yield

`CC-MAIN-2026-30` (July 2026 index), one pattern per provider:

| Pattern | Distinct tokens |
|---|---:|
| `boards.greenhouse.io/*` | 1,789 |
| `job-boards.greenhouse.io/*` | 710 (433 not in the above) |
| `jobs.ashbyhq.com/*` | 383 |
| `jobs.lever.co/*` | **0** |
| **Total** | **2,605** |

Greenhouse serves two board domains and both must be queried; the newer one
contributed 433 tokens the older one did not.

## The Lever finding

Lever returns zero, and it is not a bug in the query.

`jobs.lever.co/robots.txt` contains, among a list of blocked crawlers:

```
User-agent: CCBot
Disallow: /
```

`CCBot` is Common Crawl's crawler. Common Crawl honours it, so Lever job pages
are absent from the archive and always will be. No amount of query tuning
changes this — the data was never collected.

This does not make Lever unreachable. The same file allows general agents
(`User-agent: *` → `Allow: /`, `Crawl-delay: 1`), and `api.lever.co/robots.txt`
is `Allow: /` with the same delay. Lever's public postings API remains a
sanctioned first-party source under A1. Only *discovery by archive* is blocked.

**Consequence:** Lever boards are found exclusively by careers-page probing, and
their employer name comes from the domain the probe started at rather than from
the API. Any future work that assumes crawl harvest covers all three providers is
wrong, and the test suite asserts the crawl source is never invoked for Lever.

## Consequences

**The archive is a month behind.** A company whose board first appeared after the
last crawl is invisible to this source until the next one. This affects only
*new* employers — polling of known boards is hourly or daily and unaffected.
Careers-page probing and community name lists cover the gap for companies we
have another reason to know about.

**The index is not authoritative about employers.** It yields strings that look
like tokens, including `a3c41b8b71eff8c4`. Validation and the approval gate
(ADR 0005) exist because of this, not in spite of it.

**Re-verify before relying on the numbers.** A1 says the same about field shapes,
for the same reason: these were measured on one day against one crawl.

**Rejected alternative — careers-page probing alone.** A1's original design. It
needs a company list first, costs a request per company against third-party
sites, and would have taken far longer to reach 2,605 entries. Kept as a
secondary source, where its per-company cost buys something the archive cannot.
