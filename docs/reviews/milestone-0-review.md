# Milestone 0 — adversarial review

**Date:** 2026-07-29
**Reviewer:** the engineer who wrote it, which is the weakness of this document
**Verdict: M0 is not complete.** Three findings must be fixed before it can be.

CLAUDE.md §5 asks this review to actively look for: hallucinated certainty,
silent data loss, wrong merges, race conditions, retry storms, GPU leaks,
unbounded render work, mobile gesture conflicts, accessibility gaps, privacy
overreach, and tests that assert nothing. Each is addressed below, including the
ones that do not apply yet and why.

---

## Findings

### F1 — Nothing has been executed against a live database (blocker)

**Severity: blocker.** The single most important fact about this milestone.

Every code path touching Postgres or Redis is written, typechecked, and
unit-tested, and **none of it has ever run**. That includes: the migration
applying, the migration rolling back, `persist_source_job` inserting anything,
the four `job_locations` check constraints actually rejecting what they claim to
reject, `/health` returning 200, and any job appearing in a browser from a
database.

The cause is B1 in PROGRESS: no container runtime on this machine, blocked on one
interactive `sudo mkdir`.

The honest risk assessment: the parts I would bet on are the models and the
routes, because mypy strict checks them and it already caught a missing
relationship that would have been a runtime `AttributeError` in `GET /sources`.
The parts I would **not** bet on are:

- The circular FK between `jobs.primary_location_id` and `job_locations.job_id`.
  `_replace_locations` detaches the pointer, flushes, deletes, flushes, inserts,
  flushes, re-points. That sequence is exactly the kind of thing that works in
  theory and deadlocks or trips a constraint in practice.
- The `CASE`-based confidence/coordinate check constraint. Postgres treats a
  `CHECK` evaluating to NULL as passing; all five enum values are covered so
  there should be no NULL branch, but "should be" is doing real work in that
  sentence and only a live insert settles it.
- `session.begin_nested()` savepoint behaviour inside an outer `session_scope()`
  transaction.

**Required before M0 completes:** run `make demo`, then deliberately attempt each
of the four constraint violations by hand and confirm the database refuses them.
A constraint nobody has seen reject anything is a comment with extra syntax.

### F2 — CI has never run (blocker)

`.github/workflows/ci.yml` has four jobs and has executed zero times, because
there is no git remote. Every *step* it contains was run locally and passes, but
the workflow file itself is unvalidated YAML with unvalidated assumptions:

- `ghcr.io/imresamu/postgis:16-3.4-bundle` is asserted to contain pgvector. Not
  verified. If it does not, the `migrations` job fails at extension creation.
  Mitigation already in place: the init SQL and `/health` both assert the
  extensions rather than assuming them, so the failure is loud.
- The drift-probe step greps a generated file for `op.create|drop|alter|add`.
  That is a heuristic, not a parse. It would miss a drift expressed only as an
  `op.execute`.
- `gitleaks-action@v2` on a repository with no license key may be rate-limited or
  require configuration on private repos.

**Required before M0 completes:** push to a remote and get a green run. Until
then criterion 2 is `UNVERIFIED` in PROGRESS, and it says so.

### F3 — `make demo` calls `make dev`, which never exits — *addressed*

`demo: up && migrate && seed && dev`. That matches the CLAUDE.md §4 spec exactly,
and it also means `make demo` blocks forever by design — it ends in a foreground
dev server.

This is correct for a human and **wrong for CI or any scripted verification**,
which is part of why F1 has not been self-resolved: I cannot run `make demo`
non-interactively and check its exit code.

**Fixed.** `scripts/verify.py` plus `make verify` and `make acceptance`. It
starts the API, asserts `/health` is 200 with both dependencies up and both
extensions present, asserts `/jobs` is non-empty, re-checks invariant I1 against
live data rather than a fixture, and — the part this review specifically
demanded — attempts all four `job_locations` constraint violations and fails
unless the database refuses each one. `make demo` stays exactly as CLAUDE.md §4
specifies.

The script itself has never run (F1). It is written to fail loudly rather than
skip, so a wrong assumption in it surfaces as a failed check rather than a
false pass.

---

## Weaknesses I am reporting on myself

### W1 — The location parser is narrower than it looks

`parse_location_field` was built against **one** provider's output. 98
assertions pass, which sounds thorough and is misleading: the shapes it handles
are the shapes Greenhouse produces, and the two hardest heuristics are
unvalidated outside that.

Specifically, `_strip_tail_tokens` consumes country-then-state from the right.
`"New York, USA, Remote"` correctly yields state=New York with no city, because
after dropping `Remote` and `USA` the remaining `"New York"` matches the state
table first. But `"New York, New York, USA"` yields city=New York — the same
token, a different role, decided purely by position. That is correct for this
provider's convention and it is *fragile*. Lever's `"New York"` alone, with no
corroboration, currently yields `unknown` — arguably right, arguably a miss.

The `_COUNTRIES` table is also a judgement call masquerading as data: ~90
entries chosen because they appear on tech boards. An unlisted country yields
`unknown`, which is the safe direction, but a European board would produce a lot
of `unknown`.

Honest framing: this is a first-provider parser with a good test harness, not a
general location parser. A2 requires the fixture file to grow before the parser
does, and M1 must add Lever and Ashby fixtures **first**.

### W2 — "207 tests passing" is a number that can mislead

Of 183 Python tests, 98 are parametrised cases over one YAML file. That is
genuine coverage of one module and it inflates the headline. There are **zero**
tests for `domain/ingestion.py`, which is the module with the most branching
logic in the repo — because every one of them needs a database (F1). There are
zero tests for the API routes, for the same reason. Those two gaps are the real
content of this finding and they remain open.

`domain/registry.py` and `domain/companies.py` had no tests either, which was a
plain gap rather than a blocked one — both are pure functions. **Fixed during
this review:** 59 assertions added across `test_registry.py` and
`test_companies.py`. Writing them immediately found a real bug (below), which is
the argument for having written them sooner.

### W3 — Two invariants are asserted but not exercised

I2 (never fabricate a qualification) has no code and no tests, because M0 has no
user qualifications. I4 (never a score without a breakdown) likewise. Both are
listed as satisfied-by-absence, which is true and is also the weakest possible
form of compliance. They become real work at M2 and M3.

### W4 — `_existing_location_signature` does redundant work

It orders by `is_primary DESC, raw_text` and the caller immediately wraps it in
`set()`, discarding the ordering. Harmless, and a small sign that the
change-detection logic was rewritten mid-flight — which it was.

---

## The checklist §5 asks for

**Hallucinated certainty.** The failure mode I was most watchful for, and I found
one real instance in my own work: the first draft of `_extract_employment_type`
would have inferred `salary_period` from magnitude (large number → yearly). That
is a guess rendered as data. Removed; `salary_period` is now always `None` for
Greenhouse and the UI says "period not stated". `test_pay_transparency_range_is_extracted`
asserts it stays that way.

More broadly, the interface is built so that low confidence is *more* visible
than high confidence would be: the ladder is on every row, the corpus readout
leads with "placeable on a map: 0", and the Analyze page has a section titled
"Why every location is unresolved". I am reasonably confident there is no place
where M0 asserts more than it knows.

**Silent data loss.** Three real risks, two mitigated:

- `_replace_locations` deletes and reinserts. Today it loses nothing, because
  there is nothing but parsed text. **Once M1 adds geocoding it would discard
  resolved coordinates on every poll.** Mitigated now by only calling it when the
  location signature actually changed, and the docstring says why. M1 must
  re-read this.
- `_apply_normalized_fields` deliberately does not copy `first_seen_at`,
  `status`, or `closed_at`. Without that exclusion a re-poll would resurrect a
  closed job.
- One bad posting failing to persist. Mitigated with a real savepoint —
  unverified per F1.

**Wrong merges.** Not applicable: M0 does no merging. The relevant M0 decision is
that `normalize_company_name` is conservative — it strips legal suffixes and
punctuation and nothing else. No fuzzy matching, so "Meta" and "Metabase" cannot
collapse. The risk runs the other way: "Datadog" and "Datadog Inc" merge
correctly, but a company that renames itself creates a second row. Acceptable.

**Race conditions.** One real one, unfixed: `get_or_create_company` and
`get_or_create_source` are check-then-insert with no upsert. Two concurrent
ingestion runs would race on the unique constraint. Not currently reachable —
`max_jobs = 1` in `WorkerSettings` means one ARQ job at a time, and there is one
worker. It becomes reachable the moment concurrency is raised. **Should become an
`ON CONFLICT DO NOTHING` before that happens.** Noting it rather than fixing it
because the fix cannot be tested (F1).

**Retry storms.** Addressed deliberately. Exponential backoff with **full
jitter** in `_backoff_delay`; without jitter, several boards failing in one pass
would retry in lockstep. Retries only on 429/500/502/503/504 — a 404 is terminal
and retried zero times, asserted by `test_does_not_retry_a_404`. Queue-level
retries are off (`max_tries = 1`) specifically so they do not multiply against
the adapter's retries. A shared `RateLimiter` caps outbound requests at a
configured 2/s, and the config validator refuses anything above 20/s.

**GPU leaks / unbounded render work.** Not applicable — no WebGL, no canvas, no
`requestAnimationFrame` anywhere in the repo, and neither MapLibre nor Three.js
is a dependency. Starting the 3D city before M4 is the first item on CLAUDE.md's
anti-pattern list. The relevant M0 discipline is that the jobs list is capped at
`limit=50` client-side and `MAX_LIMIT=100` server-side, so it cannot be asked to
render thousands of rows.

**Mobile gesture conflicts.** Not applicable yet — no map, no custom gesture
handling, nothing intercepting touch. The layout is responsive (the header wraps,
the source table scrolls inside its own `overflow-x-auto` container rather than
scrolling the page), but I have **not** tested on a real device. Not claiming it
works, only that nothing is fighting the browser.

**Accessibility gaps.** Done: skip link as the first focusable element (e2e
asserted); `:focus-visible` never removed; `aria-current="page"` on the active
mode (e2e asserted); the confidence ladder has an `aria-label` carrying the rank
and the plain-language meaning, and its tick heights vary so the scale survives
greyscale; every coloured state also has a text label; the legend is a permanent
panel, not a tooltip, because §12.4 forbids essential information available only
through hover; the source table has a `<caption>` and `scope` attributes;
`prefers-reduced-motion` is respected.

Gaps I have not closed: no screen-reader pass has actually been run (A14 defers
automated a11y tests to M4 but asks for **manual** keyboard and screen-reader
passes from M2 — so this is on time, not overdue). No high-contrast mode yet
(§12.4 requires one). Colour contrast has not been measured; `--color-paper-faint`
`#5d6e88` on `--color-ink-950` `#04070c` is the pair I would expect to fail, and
it is used for small mono labels, which is the worst place for it. **Should be
measured and probably lightened.**

**Privacy overreach.** Nothing collected. No user data, no auth, no email, no
analytics, no telemetry, no third-party script — the CSP-relevant fact is that
the app makes exactly one outbound class of request, to its own API. Outbound
HTTP to job boards is off by default. The one privacy-relevant decision made now
is documented in Q1 and A8: Gmail bodies are never stored, and public demo mode
and Gmail are mutually exclusive.

**Tests that assert nothing.** I went looking. Every test file has at least one
test that would fail if the invariant it covers were removed, and I verified this
by reasoning about the negative case for each invariant test rather than by
mutation testing. The strongest examples: `test_never_produces_coordinates`
fails if anyone adds a latitude field to `ParsedLocation`;
`test_genuine_empty_board_is_authoritative` fails if I3 is "satisfied" by never
trusting anything; `test_does_not_attempt_role_family_normalisation` fails if
someone quietly makes `normalize_title` smarter. The `_load_cases` helper
asserts the fixture file is non-empty, so a truncated YAML cannot turn 98 tests
into 0 silently passing.

The weakest test in the repo is `test_absent_deadline_stays_none`, which is
conditional on the fixture's data and would vacuously pass if the fixture ever
contained only postings *with* deadlines. Low stakes, but it is the one I would
point at if asked which test is closest to asserting nothing.

---

## Actions before M0 can be marked complete

| # | Action | From |
|---|---|---|
| 1 | Install a container runtime; run `make demo`; record real output for acceptance rows 1, 3, 4, 5 | F1 |
| 2 | Manually attempt all four `job_locations` constraint violations and confirm the database refuses each | F1 |
| 3 | Push to a remote; get one green CI run | F2 |
| ~~4~~ | ~~Add `make verify`~~ — **written** (`scripts/verify.py`, `make verify` / `make acceptance`). Itself unrun, per F1 | F3 |
| ~~5~~ | ~~Add tests for `domain/registry.py`~~ — **done**, 29 assertions; also added 30 for `domain/companies.py` | W2 |
| 6 | Measure contrast on `paper-faint`/`ink-500` against the background; lighten if below 4.5:1 | a11y |

## Actions before M1 can start

| # | Action | From |
|---|---|---|
| 7 | Make `get_or_create_*` upserts before any concurrency is introduced | races |
| 8 | Write Lever and Ashby location fixtures **before** touching the parser | W1, A2 |
| 9 | Re-read `_replace_locations` when geocoding lands — it must not discard resolved coordinates | data loss |
| 10 | Delete the redundant ordering in `_existing_location_signature` | W4 |
