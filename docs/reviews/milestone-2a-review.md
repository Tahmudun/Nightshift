# M2a review — search, filters, detail pages

- **Date:** 2026-08-03
- **Branch:** `m2a-search-and-detail`
- **Plan:** `docs/plans/2026-08-03-m2a-search-and-detail.md`
- **Design:** `docs/architecture/command-center.md` §4

Adversarial pass over the first slice of M2, hunting the failure modes
`CLAUDE.md` §5 names: filters that silently return everything, absence rendered
as a zero, numbers presented as scores, and tests that cannot fail.

---

## 1. What was found

**Eight defects. Six were in code that reported success**, which is the same
pattern M1a, M1b, M1c and M1d each recorded — now five milestones running.

### 1.1 Searching descriptions by default made the search box useless

**Found by:** a test failing for the wrong reason.

`q=developer` returned all nine postings on the recorded Alloy board. Not an
index bug: 'developer' stems to `develop`, and every one of those descriptions
contains "business development" or "professional development".

This is what full-text search over long documents does when there is no
relevance ranking to sort the noise down — and ranking is M3 (PRODUCT-SPEC
§24), because it depends on the match score. Ordering here is recency.

The first instinct was to fix the test. That would have shipped a search box
where typing a job title returns the corpus, which is the kind of defect that
survives to production because nothing errors and the results *look* plausible.

**Fixed** by adding `jobs.title_vector` (migration `0006`) and making the title
the default target, with `include_description=true` as an opt-in. The wide
search still earns its place: `playbooks` appears in three descriptions and no
title, and is unreachable without it. Both directions are pinned by tests, at
the route and in the browser.

### 1.2 The salary floor could not be served by an index

**Found by:** `tests/test_query_plans.py`, on its first run.

The floor is `salary_max >= :floor OR salary_min >= :floor`. Postgres can only
serve an `OR` from indexes when **both** sides have one, so it can build a
BitmapOr. Only `salary_max` was indexed, so the whole filter degraded to a
sequential scan.

This is the exact defect that test exists for, and it is worth naming why it is
invisible otherwise: **the wrong plan returns exactly the right rows.** It is
invisible in the code, in the API response, and in every correctness test. It
shows up only as slowness, and only once the corpus is big enough that fixing
it is expensive.

**Fixed** by migration `0007`.

### 1.3 A salary floor silently hid most of the corpus

**Found by:** review, before writing the filter.

Most postings state no salary (A10). A floor necessarily removes every one of
them, so a naive implementation drops the majority of the corpus and presents
the remainder as the answer.

**Fixed** by `excluded_no_salary` on the response, surfaced in the list as
*"N further roles state no salary and cannot be compared against a floor."*
Mutation-checked.

### 1.4 The salary test could never have failed

**Found by:** the test passing when it should not have been able to.

`test_a_salary_floor_reports_what_it_hid` asserted `excluded_no_salary >= 1`
against the standard seed. Every one of the nine recorded Alloy postings
carries a `salaryRange`, so the true answer is zero and the assertion was
unfailable in the useful direction.

**Fixed** by seeding a corpus with the field stripped from four of nine, and
asserting the exact numbers 4 and 5.

### 1.5 Two defaults governed one behaviour, and only one was guarded

**Found by:** mutation testing.

Flipping `JobSearchQuery.include_description` to `True` failed **nothing**,
because the FastAPI route re-declares its own default in the signature and that
is what actually governs. The model default was dead weight that a future
session could change with no test objecting.

**Fixed** by guarding both layers. This is the most useful thing mutation
testing did here: the guard looked present and was not.

### 1.6 `alembic check` fails on an expression index left out of the model

**Found by:** running `alembic check`, having written the opposite into the plan.

The plan instructed *"do not add the city index to the model"*, reasoning that
autogenerate mishandles expression indexes. Measured, the reverse is true: with
the index in the database and absent from the model, `alembic check` reports
`remove_index` and fails.

**Fixed**, and the plan corrected in place rather than quietly working around
it, so the next reader is not misled by a document that was wrong.

### 1.7 A duplicate `jobStatusCountsSchema`

**Found by:** the bundler, at build time.

A second copy was written without checking whether one existed. Caught as a
duplicate export before it could run, which is the good version of this
mistake — the bad version is two schemas that drift.

**Fixed** by reusing the existing one.

### 1.8 Two Playwright failures that were not product bugs

**Found by:** the seeded browser suite; **diagnosed by:** probing the browser
directly rather than theorising.

- `.check()` on the description toggle reported *"clicking the checkbox did not
  change its state"*. The checkbox is controlled by the URL and the round trip
  through `router.replace` is async, so `.check()` catches the input
  mid-revert. A probe confirmed the state does settle correctly.
- The first navigation into `/explore/jobs/[id]` blew the 5s default timeout.
  The seeded stack runs `next dev`, which compiles a route on first request.

Both worth recording because the tempting diagnosis — "the link is broken" —
was wrong, and a fix aimed at it would have changed working code.

---

## 2. Deliberate decisions a reviewer should check

### 2.1 The query-plan test does not assert "no Seq Scan"

On a 31-row table Postgres seq-scans everything, correctly. So:

- `assert no Seq Scan` → fails on correct code.
- `assert Seq Scan` → passes on a table with no indexes at all.

Both are useless. The test sets `enable_seqscan = off` and asserts an index node
appears, which answers *is this filter servable by an index* — the question that
survives corpus growth. `test_a_filter_on_an_unindexed_column_is_detectable` is
the non-vacuity guard; without it the assertion would pass for anything.

The measured latency is recorded separately in PROGRESS. Both are needed: the
plan test prevents regression, the measurement earns the criterion.

### 2.2 Ordering is recency, not relevance

PRODUCT-SPEC §24's ranking is M3 and depends on the match score. Sorting by a
text-relevance number here would be building half of M3 and calling it done.
Stated in the route docstring so the next reader does not mistake it for an
oversight.

### 2.3 There is no borough filter and this is I1, not scheduling

`job_locations` has `city`, `state`, `country`. A posting saying
`"New York, NY"` does not say which borough it is in, and deriving one is the
interpolation I1 forbids. A **city** filter is honest because it matches what
the source wrote.

`test_borough_is_deferred_for_an_invariant_reason_not_a_schedule` asserts
`blocked_on == "M4"` and that the reason mentions geocoding, specifically so a
future session cannot quietly reclassify it as an ordering problem and infer
one.

### 2.4 Two kinds of absence, never collapsed

The job page distinguishes *"not provided by source"* (A10 — the posting did not
say) from *"not yet computed"* (I4 — M3 does not exist). A UI rendering both as
a blank field tells the reader the same thing about unrelated situations.

The seven M3 fields are listed **by name**, because a reader cannot check for a
field that was never mentioned. Tests assert no percentage appears in that
block, in both vitest and Playwright.

---

## 3. Weaknesses carried forward

1. **Pagination is offset-based and the UI has no pager.** The list requests
   `limit=50` and shows what comes back; `total` is displayed honestly, so a
   corpus above 50 silently shows a subset with the real count beside it. Not
   wrong, but incomplete. M2b or a follow-up.
2. **No test asserts the filter panel's keyboard path.** A14 defers automated
   accessibility to M4, and the manual keyboard pass has not been done for
   these controls. Recorded rather than claimed.
3. **`fetchJobs({ company: companyName ?? '' })` has an unreachable fallback.**
   `enabled` guarantees the name exists, but `exactOptionalPropertyTypes` makes
   an explicit `undefined` an error. Commented as unreachable. A cleaner shape
   would build the argument object conditionally.
4. **The company page filters roles by company *name*, not id.** It reuses the
   existing `company` substring filter, so two employers whose canonical names
   contain one another would cross-contaminate that list. `normalize_company_name`
   makes this unlikely and the counts above it come from the id, so the numbers
   are right even if the list were not. Worth a `company_id` filter when M2b
   touches this route.
5. **The dev database is truncated by the Python test fixtures.** Measuring
   latency straight after `make check` produced a 0-job corpus and five
   plausible-looking millisecond figures. Caught because the corpus size was
   printed alongside; it would not have been caught otherwise. Any future
   measurement must print what it measured against.

---

## 4. Evidence

| Check | Result |
|---|---|
| `make check` | green — **856 Python**, **63 web**, ruff/mypy/eslint/tsc clean |
| `make acceptance` | green — **18 verify checks**, **27 seeded browser tests**, 1 skip |
| `alembic check` | no drift, with all three migrations applied |
| Migration round trip | `0005`–`0007` down and up; both generated columns and all five indexes confirmed absent then present, read from `pg_indexes` |
| Filter latency, 31 jobs | worst of five per query: 31.6 / 40.1 / 36.1 / 42.7 / 53.4 ms — all inside the 200ms criterion |
| Mutation checks | blank-query filter, `excluded_no_salary`, description default — each fails the intended test when broken |

The single e2e skip is the pre-existing one: *an unchanged board is not
presented as a problem* needs a board that has answered `304`, and the seeded
stack has polled nothing.

---

## 5. Not built in this slice

Save, apply, tracking, notes, stage history (M2b); profile and resume (M2c);
the daily queue (M2d); match score, eligibility, skill and internship-season
filters (M3); boroughs and any coordinate (M4).

None of these are stubbed. Where the spec asks for them, the UI names them and
says what they are waiting for.
