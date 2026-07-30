# Board discovery

> Design spec. Written 2026-07-30, before implementation, for the M1 registry
> deliverable. Status: **approved in conversation, not yet built.**

## 1. What this is for

The product goal, in the human's words: *if a tech job or internship opens in
NYC, the system knows the day of.*

That splits into two problems of very different difficulty.

**Freshness is easy.** ATS boards update live and expose cheap listing
endpoints. Polling hourly is a solved problem and the measurements in §3 show it
costs almost nothing.

**Completeness is hard, and it is entirely a discovery problem.** AMENDMENTS A1
is right: no ATS provider publishes a customer directory. You cannot ask
Greenhouse who its customers are. A job at a company whose board token we do not
know is invisible, and no amount of polling fixes that.

So this document is about one thing: **how the registry gets filled, and how we
report honestly on what it still misses.**

## 2. Scope

**In:** discovery, validation, human approval, polling strategy, coverage
reporting, for Greenhouse, Lever and Ashby.

**Out, deliberately:**

| Not in scope | Why | When |
|---|---|---|
| Workday, iCIMS, Taleo | Each is an adapter in its own right. They are where banks, hospitals, media and universities post, so this is the largest known blind spot | Next milestone |
| Cities other than NYC | Costs nothing at ingestion (§10) — it is a filter and a geocoder, not a pipeline | When wanted |
| Non-tech roles | Ingested already; the gap is matching, not collection (§10) | Not planned |
| LinkedIn, Indeed | §9 | Never |

## 3. Measured facts

Everything here was measured on 2026-07-30, not estimated. Re-verify before
relying on the numbers; A1 says the same about field shapes.

**Discovery yield.** Common Crawl's `CC-MAIN-2026-30` URL index, queried for
board URL patterns:

| Pattern | Distinct tokens |
|---|---:|
| `boards.greenhouse.io/*` | 1,789 |
| `job-boards.greenhouse.io/*` | 710 (433 not in the above) |
| `jobs.ashbyhq.com/*` | 383 |
| `jobs.lever.co/*` | **0** — see below |
| **Total** | **2,605** |

**Lever is invisible to Common Crawl, by Lever's choice.** `jobs.lever.co/robots.txt`
contains `User-agent: CCBot` / `Disallow: /`. CCBot is Common Crawl's crawler, so
Lever job pages are not in the archive and never will be. The same file allows
general agents (`User-agent: *` → `Allow: /`, `Crawl-delay: 1`), and
`api.lever.co/robots.txt` is `Allow: /` with the same delay, so Lever's public
API remains usable. **Lever boards must be discovered by careers-page probing,
not by crawl harvest.**

**A 200 response does not mean a real employer.** The discovered token
`a3c41b8b71eff8c4` returns HTTP 200 with 10 well-formed postings. Every
automated liveness check passes it. It is obviously not a company. This single
case is the argument for §6 and becomes a committed fixture.

**Employer names come from a different place in each provider.** This was
asserted wrongly in the first draft of this document and then checked. The
correction matters, because §6 makes "the provider told us who this is" the
condition for bulk approval.

| Provider | Where the name comes from | Verified |
|---|---|---|
| Greenhouse | `GET /v1/boards/{token}` → `{"name": "6sense", …}`. Also `company_name` on every job in the listing | Yes |
| Ashby | **Nowhere in the API.** `posting-api/job-board/{token}` returns only `apiVersion` and `jobs`, and no job object carries a company or organisation field. The name is on the board page: `jobs.ashbyhq.com/{token}` → `<title>`/`og:title`, suffixed " Jobs". Ashby's `robots.txt` disallows only `/meeting/`, `/b/` and `/api/`, so that page is permitted | Yes |
| Lever | Not established — no populated board was available to inspect. Does not block: Lever boards are found by careers-page probing (§4), which starts from a company's own domain and therefore already knows the employer | No |

**The token is not the name.** Ashby board `0g` belongs to "0g Labs";
`10xteam` to "10x Team". Deriving an employer from its slug would be inventing a
fact, which is the same failure mode I2 exists to prevent.

**Lever distinguishes "no such board" from "board with no jobs".** An unknown
token returns `HTTP 404` with `{"ok":false,"error":"Document not found"}`; a
live but empty board returns `HTTP 200` with `[]`. I3 depends on that
distinction being real, and here it is.

**Polling is cheap, if done in two phases.** For one board (`6sense`):

| Request | Bytes |
|---|---:|
| `/jobs` (listing only) | 27,179 |
| `/jobs?content=true` (all descriptions) | 840,747 |
| `/jobs/{id}` (one job, with description) | 17,932 |

A 31× difference. The listing endpoint also returns `ETag` and supports gzip,
with `Cache-Control: max-age=0, private, must-revalidate` — so an unchanged
board can be revalidated for approximately nothing.

## 4. Architecture

A new package, deliberately separate from ingestion:

```
nightshift/discovery/
  sources/crawl_index.py    Common Crawl CDX  -> candidate tokens
  sources/community.py      committed list snapshots -> company names
  sources/careers_probe.py  domain -> careers page -> embedded board (Lever)
  validate.py               probe the provider API, classify the candidate
  candidates.py             read/write data/board-candidates.yaml
  approve.py                promote approved candidates into the registry
```

Three front-ends, one validation-and-approval path. Discovery is **explicitly
invoked and never scheduled** (A1). It is a `make` target, not an ARQ cron.

Ingestion does not import discovery, and discovery does not write to any table
ingestion reads. The only thing they share is `data/board-registry.yaml`.

### Boundaries

- `crawl_index` takes a crawl id and a URL pattern, returns tokens. No network
  knowledge of ATS providers, no database.
- `validate` takes `(ats, token)` and returns a `CandidateVerdict`. It is the
  only module here that talks to a provider, and it does so through the existing
  `PoliteClient` — nothing else in the repo imports `httpx` and that stays true.
- `approve` is pure file manipulation over YAML. No network.

## 5. Data flow

```
crawl index ─┐
community  ─┼─> raw candidate tokens ─> validate ─> board-candidates.yaml
careers    ─┘                                              │
                                                  human runs `make registry-approve`
                                                           │
                                                  board-registry.yaml (committed)
                                                           │
                                                    ingestion polls
```

Nothing writes to `board-registry.yaml` automatically. The approval command
writes it; a human reads the diff and commits. This satisfies A1's "never
auto-commit" literally.

## 6. Validation and the approval gate

### Verdicts

`validate` classifies every candidate into exactly one of:

| Verdict | Meaning | Route |
|---|---|---|
| `live_named` | 200, ≥1 posting, employer name present in the provider's own response | Bulk approval |
| `live_unnamed` | 200, ≥1 posting, no resolvable employer name | Manual review |
| `name_collision` | Name normalises to an existing company under `normalize_company_name` | Manual review |
| `empty` | 200, zero postings — authoritative, not an error (ADR 0003) | Stays a candidate; re-validated each run |
| `unreachable` | Non-200, timeout, or unparseable | Stays a candidate; re-validated each run |

`empty` and `unreachable` are **not rejections** and no candidate is ever
discarded. A company between hiring rounds returns an empty board, and a
provider having a bad morning returns a timeout; neither is evidence that a
board is worthless. Both re-validate on the next discovery run and become
approvable the moment they return named postings. Discarding them would recreate,
one level up, the mistake I3 forbids at the listing level: treating absence of
data as data.

`live_named` requires that we obtained the employer's name from the provider,
by the route established for that provider in §3 — the board metadata endpoint
for Greenhouse, the board page title for Ashby, the originating domain for
Lever. We never infer an employer from the token string; `0g` → "0g Labs" is
why.

Ashby's name lookup is one extra request per *candidate*, at discovery time
only. It never happens during polling.

### The bulk-approval decision

A1 says a human reviews every candidate. There are 2,605 of them, and a review
step that cannot realistically be performed is a review step that gets skipped.

**Decision:** `live_named` candidates are approved as a batch. `live_unnamed`,
`name_collision` and anything unreachable are held for individual attention. The
human reviews the generated summary and the resulting git diff, and commits.

The approval report is ordered by relevance — boards that produced an NYC
posting first — so review effort lands on what matters and the tail can be
skimmed. Each row carries: employer name, ATS, token, posting count, NYC posting
count, and verdict.

This is a deviation from A1's letter and **requires an ADR** recording that the
human moved from per-entry approval to per-batch approval with exceptions, and
why. It preserves A1's intent: nothing enters the registry unreviewed and
nothing is written automatically.

## 7. Polling

### Two phases

1. **Revalidate.** `GET /jobs` with `If-None-Match`. A `304` ends the poll for
   that board at near-zero cost.
2. **Fetch changed only.** On `200`, diff the listing against stored job ids and
   `updated_at`. Fetch `/jobs/{id}` for new or changed postings only.

Never `content=true` on a whole board. That is the 841 KB path and it is only
justified for a board being ingested for the first time.

### Two tiers

| Tier | Membership | Interval |
|---|---|---|
| `hot` | produced ≥1 NYC posting in the last 30 days | hourly |
| `warm` | every other `active` board | daily |

Hourly across all 2,605 would be ~62,000 requests/day against a handful of
hosts. This design lands near 10,000, most of them `304`s. Daily on the long
tail is what keeps "the day of" true for a company posting its first NYC role;
a weekly tier would break that promise and is deliberately absent.

Tier membership is computed from ingestion results and stored in the database,
never hand-edited in the registry YAML.

### Queue-driven, not loop-driven

Each board poll is an individual ARQ job, not an iteration inside one long task.
This is the decision that makes §10 possible: going from 2,600 boards to 100,000
becomes a worker-count question rather than a rewrite. Rate limiting is
per-provider-host, enforced in `PoliteClient`, so adding boards never increases
the request rate against any one provider.

## 8. Determining NYC — and the dependency this has

NYC-ness is read off the postings by `parse_location_field`, never declared by a
registry entry. A board qualifies for the `hot` tier because of what its jobs
said, not because someone ticked `nyc_presence`.

**This depends on work that must happen first.** The parser is a
first-provider parser: its conventions came from Greenhouse, and `"New York"`
alone currently returns `unknown`. `docs/PROGRESS.md` "Before M1 starts" item 1
already requires Lever and Ashby location fixtures to be written *before* the
parser is touched. This design does not change that ordering — it depends on it.
Adding providers to the parser before adding them to the fixtures would encode
one provider's conventions as if they were general.

Invariant I1 is unaffected: parsing a location to `city_only` NYC is not
geocoding and produces no coordinate.

## 9. LinkedIn and Indeed

Asked directly, answered here so it is not re-litigated.

**LinkedIn: no.** `www.linkedin.com/robots.txt` ends with `User-agent: *` /
`Disallow: /` and a note to email `whitelist-crawl@linkedin.com` for permission.
It is a blanket prohibition on all automated access, there is no free public
jobs API, and CLAUDE.md §8 forbids scraping anything that asks not to be
scraped. This is not a close call.

**Indeed: effectively no.** Large parts of the site are disallowed, and the
public Publisher API is partner-only. Beyond permission, Indeed is mostly an
aggregator — much of its inventory originates on the same ATS boards this system
already reads first-hand, so it would add duplicates and a legal exposure rather
than coverage.

**The honest cost:** an employer that posts only to LinkedIn and nowhere else
will not appear. That is a real hole and it is listed in §11 rather than hidden.

## 10. Scale path

The human's stated ambition: NYC, then other tech cities, then every state, then
every job type. What that costs, honestly.

**Geography is nearly free, because the unit of polling is a company, not a
city.** A board is fetched whole; Datadog's postings in Boston and Paris are
already downloaded and stored today. `job_locations` (A2) keeps every location
of every job. NYC is a query-time filter. Adding a city adds no ingestion work.

Two real costs as geography grows:

1. **The geocoder is NYC-only by design.** A4 chose NYC GeoSearch — a city
   government service that knows NYC addresses and nothing else. National
   coverage needs a different provider. Mitigation, cheap now: geocoding sits
   behind an interface with the provider resolved per region, so a second
   provider is a registration rather than a refactor.
2. **The location parser is US- and NYC-shaped.** It grows by fixtures, as
   above.

**Job type is nearly free to collect and expensive to be useful about.** Every
posting on a board is already ingested regardless of function. Filtering to tech
is a query. What does not generalise is matching: M3's skill taxonomy,
eligibility rules and evidence graph are tech-shaped. A system that explains to
a nurse why they match a nursing role is a different product, not a larger one.

**Where this architecture genuinely stops.** Employers at the small end — local
restaurants, contractors, dental practices — do not use machine-readable job
boards at all. They post directly to aggregators or not on the internet at all.
No polling strategy reaches them, because the data was never published in a form
a machine can read. This is the actual moat aggregators have, and it is
commercial rather than technical.

**The honest ceiling: every job posted to a machine-readable board in the US.**
Millions of postings, skewed toward professional and office roles, thin on
hourly and local work. "Every job of every type" is not reachable by these
means and should not be promised.

**Decisions taken now because they are cheap now and expensive later:**

1. No NYC anywhere in the schema — every location stored, city filtered at query
   time. Already true via A2.
2. Queue-driven polling (§7), so board count is a capacity question.
3. Geocoding behind a region-resolved provider interface.
4. Location parsing yields structured city/state/country, never a boolean
   "is NYC".

**Deliberately not built:** distributed workers, sharding, read replicas,
multi-region deployment, a non-tech skill taxonomy. CLAUDE.md §8 forbids building
for imaginary scale and this document is not an exception to it. The four
decisions above are the complete list of what is being done for a future that
may not arrive; each costs approximately nothing today.

## 11. Coverage reporting

This replaces a guarantee the system cannot honestly make. A page reporting:

- boards by status and ATS; how many polled in the last hour and last 24h
- boards producing NYC roles; candidates awaiting review, by verdict
- last successful sweep per tier
- **named blind spots**: Lever boards not yet discovered; Workday/iCIMS/Taleo
  employers; companies with no public board; employers posting only to
  aggregators

A missing coverage number is worse than a low one. Per I6, the page reports what
was measured, not what was hoped.

## 12. Failure handling

Governed by existing invariants; nothing new is invented here.

- **I3.** A failed poll, a timeout, a `304`, or an empty array never closes a
  job. `FetchOutcome` (ADR 0003) already encodes this and discovery does not get
  to bypass it.
- Discovery failures leave the registry untouched. A Common Crawl outage means
  no new candidates, never a modified registry.
- Per-board consecutive failures mark an entry `dead`, which surfaces it on the
  source health page and deletes nothing (A1).
- `unreachable` candidates are retried on the next discovery run, never
  auto-approved and never auto-discarded.

## 13. Testing

Every claim in §3 becomes a test or a committed fixture.

- A recorded Common Crawl CDX response per provider pattern, committed. Parsing
  it is deterministic: same input, same token set, twice.
- **The `a3c41b8b71eff8c4` case**: a validation fixture asserting a live,
  well-formed, unnameable board is classified `live_unnamed` and therefore
  cannot reach bulk approval. This is the test that stops the approval gate
  becoming decorative.
- A `name_collision` fixture using a real near-miss pair from the existing
  company-normalisation suite.
- **Ashby name extraction**: a recorded board page asserting `0g` resolves to
  "0g Labs" and not to "0g". A test that accepted the token would pass against a
  suffix-stripping bug and is worthless.
- **Lever 404 vs empty**: two committed fixtures — `{"ok":false}` at 404 must
  produce `unreachable`, and `[]` at 200 must produce `empty` with
  `is_authoritative_empty=True`. Collapsing these is exactly the I3 violation
  ADR 0003 exists to prevent.
- Lever: a test asserting the crawl-index source is never invoked for Lever, with
  the committed `robots.txt` as the reason in the docstring.
- Polling: a fixture pair proving a `304` results in zero writes, and that a
  changed `updated_at` fetches exactly one job rather than the whole board.
- Tier assignment fixtures, including a board that loses NYC postings and must
  demote from `hot` to `warm`.
- An approval test proving that a `live_unnamed` candidate cannot be promoted by
  the bulk path even when the report is approved wholesale.

## 14. Work this depends on

In order. The first two are from the existing "Before M1 starts" list and are
prerequisites, not part of this design.

1. Lever and Ashby location fixtures, then parser breadth (PROGRESS W1).
2. `get_or_create_source` / `get_or_create_company` become upserts. They are
   check-then-insert today, which is safe only at `max_jobs=1`; queue-driven
   polling makes concurrency real and this becomes a duplicate-company bug.
3. Tests for `domain/ingestion.py` and the API routes — the largest coverage gap
   in the repo, and this design adds load to exactly that code.

## 15. ADRs this requires

- **Batch approval of `live_named` candidates**, departing from A1's per-entry
  review. Records the 2,605 count, the reasoning, and the exception classes.
- **Common Crawl as a discovery source**, including the CCBot finding that makes
  it structurally blind to Lever.
- **Two-tier polling with conditional requests**, recording the 31× measurement
  that motivates the two-phase fetch.

## 16. Open questions

Tracked in `docs/QUESTIONS.md`; none block starting.

- Q3 is now largely answered: the registry is filled by discovery, not curation,
  and the human is the batch approver. The remaining question is how often they
  want to run it.
- Whether `nyc_presence` stays in the registry YAML at all. It is currently
  hand-set and used for poll ordering, but §8 derives the same fact from
  postings. Likely deleted rather than maintained in two places.
