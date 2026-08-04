# Milestone 2d review — the daily queue

- **Date:** 2026-08-04
- **Branch:** `m2d-daily-queue`
- **Design:** `docs/architecture/command-center.md` §7, §7.1, §7.2, §7.3
- **Plan:** `docs/plans/2026-08-04-m2d-daily-queue.md`
- **ADR:** 0014 — queue membership comes from current state

M2d completes M2's deliverable list. **It earns none of M2's four acceptance
criteria, and that is not a gap** — all four were verified at M2a, M2b and M2c
and are unchanged. What follows is therefore a review of a feature, not of a
criterion.

---

## 1. What was built, and what it refuses to build

Four sections computed from data M2b and M2a already held, and four named
absences. The absences are the part worth defending: PRODUCT-SPEC §10.4 asks for
eight rows, this system can honestly produce four, and there are three things you
can do about the other four. Build them against an invented score (I4 forbids
it). Render them as empty sections — which claims "you have none of these", a
statement that is false rather than merely unhelpful. Or name them with the
reason. Only the third is honest, and it is what `/analyze/coverage` already does
for source coverage.

**The queue writes nothing.** No dismiss, no snooze, no "mark done". Confirmed
by grep rather than by intent: `domain/queue.py` and `api/routes/queue.py`
contain no `session.add`, no `commit`, and no INSERT/UPDATE/DELETE.
`test_the_queue_has_no_write_route` asserts POST, PATCH, PUT and DELETE all
return 405, so if a write appears later it will be a deliberate decision rather
than a drift.

---

## 2. What this review found

Six items. **Three were in code or tests that reported success**, which is the
eighth milestone running to record that pattern.

### 2.1 The query-plan assertion was wrong twice, in opposite directions

**First, the plan's version could not fail.** It specified
`assert _index_nodes(plan)` — "this section can be served by an index" — copied
from M2a's search assertions, where it is correct.

It is vacuous here. **Every queue statement joins `jobs` and `companies`**, so
`pk_jobs` and `pk_companies` appear in all four plans no matter what the filter
does. Measured rather than reasoned about: with both M2d indexes dropped, all
four plans still reported index nodes, so the assertion would have passed on a
milestone that added no indexes at all. That is the same defect class M2a §3 and
M2c §2.3 each recorded — a guard that looks present, is present, and guards
nothing.

**Then the fix over-corrected, and broke within the hour.** Naming the exact
index per section passed on the corpus it was written against and failed on the
next `make check`: `interviews_approaching` used
`ix_application_events_interviews` against one corpus and
`ix_application_events_application_id_occurred_at` against another a few
applications larger. That is the planner switching from a time scan to a nested
loop as the driving set shrank — **it doing its job, not a regression.** A test
that pins the plan asserts a decision that is not ours to make, and it fails on
correct code.

The property that actually has to hold is *no fall back to reading a whole
table*, and with `enable_seqscan = off` a sequential scan means no usable index
exists. `test_no_queue_section_scans_its_table` asserts that per section, and
`test_a_sequential_scan_is_detectable` is its non-vacuity guard. Shown able to
fail by dropping all three `application_events` indexes: the three event-backed
sections go red, and `closed_while_saved` correctly stays green because its
index is `jobs`'.

**The lesson is narrower than "write better tests".** Between a vacuous
assertion and a brittle one there was a correct one, and finding it took
measuring what the planner actually did twice, on two different corpora. The
first measurement is what exposed the vacuity; the second is what exposed the
brittleness. Neither was visible by reading.

One honest consequence: **`ix_application_events_interviews` is not proven
necessary by any test.** The M2b index can serve the interview lookup via a
nested loop, and on a small corpus the planner prefers it. The new index earns
its place at scale, when the fortnight window is more selective than the
per-application lookup — that is a judgement about the access pattern, and it is
recorded here rather than dressed up as something a test established.

### 2.2 `_plan` could not compile the queue statements at all

Two independent reasons, both silent until executed:

- a UUID bind renders as `:user_id_1::UUID`, and feeding that back through
  `text()` is a Postgres syntax error at the second colon;
- `current_stage NOT IN (...)` compiles to a `__[POSTCOMPILE_...]` marker, which
  is expanded at execution and is not valid SQL standing alone.

`_plan` grew a `literal_binds` option. The helper's docstring explains why the
*search* statements must not use it — `websearch_to_tsquery`'s `REGCONFIG`
argument has no literal renderer — and the queue statements contain no tsquery,
so the constraint does not reach them. Both halves are now written down, because
the next person will otherwise "simplify" one into the other.

### 2.3 The plan's test helper could not insert a closed job

`ck_jobs_closed_at_matches_status` is a biconditional: `(status = 'closed') =
(closed_at IS NOT NULL)`. The plan's `_a_job` set `status` alone, so six tests —
every one about the "closed while saved" section — failed on insert.

The schema was right and the plan was wrong. Recorded because the constraint
catching the plan that specified it is the system working, and because M1c's
review recorded the same shape from the other direction.

### 2.4 The browser walk would not have run twice

The plan gave both application-level tests the same job. An
`interview_scheduled` event is append-only and cannot be deleted, so the
interview test's role keeps its event; the follow-up test's closing assertion
("the row is gone") would then fail on the second run of the same day.

This is precisely the bug M2b's pipeline test shipped and its review recorded.
Fixed by giving the two tests different jobs, and separately by scoping every
assertion to one section's `data-testid` rather than to the page — a role can
legitimately appear in two sections at once, so "this title is somewhere on the
queue" is a much weaker claim than these tests intend.

Verified by running the file twice back to back.

### 2.5 Operate claimed tracking was not built, above a link to it

`/operate`'s "Not built yet" list contained *"Saving, applying, and stage
tracking — milestone 2"*, directly below a Pipeline panel linking to the page
that does all three. It had been false since M2b.

The same list also contained the daily queue, correctly, until this milestone.
Both lines are gone. **A "not built" list is a claim like any other, and it goes
stale in the one direction nobody checks** — nobody re-reads it when a feature
lands. M2c's review made the same finding about a different list (§2.5); this is
the second instance, which suggests the pattern rather than the incident.

### 2.6 One acceptance run flaked on a pre-existing test

`search-and-detail.spec.ts`'s title-search test timed out once in three
`make acceptance` runs; runs two and three passed. It passes alone (7/7).

Diagnosed rather than retried: the reported location was the *count* assertion,
not the URL one, and typing calls `router.replace` per change, which under
`next dev` is a server round-trip rather than the client-side navigation it is in
a build. This test also reloads, paying that cost twice.

It is not a product race, and it is M2a's test rather than M2d's — but M2d added
three tests to the parallel pool and made it likelier. Marked `test.slow()`,
which is the identical remedy M2c's review §2.6 applied to `profile.spec.ts` for
the identical reason. Trimming the reload would have removed the assertion that
the URL really is the state.

---

## 3. Checks this review ran, and what they showed

### 3.1 "Does an empty section read as 'you have none' or as 'not built'?"

The page makes **three** distinct statements and they are separately asserted:

| Claim | Where | Test |
|---|---|---|
| This section is empty | "Nothing here today." under the heading | `names every section, including the empty ones` |
| The whole queue is empty | `queue-empty`, only when `total_rows === 0` | `distinguishes an empty section from an empty queue` |
| This row does not exist yet | `deferred-queue-rows`, with `blocked_on` | `names all four deferred rows without anything being expanded` |

`does not claim an empty queue when a section has rows` is the non-vacuity guard
on the second: without it, a component that always rendered the empty block would
pass.

### 3.2 "Can a row point at something the user cannot open?"

Followed in a real browser rather than reasoned about, which is the lesson M2c
§2.1 recorded after shipping a provenance link that 404'd. `queue.spec.ts` clicks
a row and asserts the resulting URL equals the application URL it started from.

### 3.3 "Does the page do unbounded work?"

No, and it is bounded on both sides. Rendering is capped at `ROW_CAP = 20` per
section with the honest total beside it. **Querying is bounded too**: 2 queries
per section × 4 sections = 8 per page load, constant in the number of rows —
there is no per-row query. Counted from `_build_section`, which is the only
place either query runs.

### 3.4 "Is the timezone converted once, at the edge?"

Yes. One `toLocaleDateString` in `QueuePanel.tsx`, no date formatting in Python,
`TIMESTAMPTZ` throughout. This matters more than it looks: a date rendered in UTC
to somebody in New York is wrong by up to five hours and looks entirely
plausible while being wrong.

### 3.5 Mutation testing

Every load-bearing guard was shown able to fail. Each mutation killed **exactly
one** test — no overlap, so each test is guarding its own claim rather than
riding on a neighbour's.

| Mutation | Test that died |
|---|---|
| Drop `actor = 'user'` from `_last_user_activity` | `test_a_system_event_does_not_count_as_activity` |
| Drop `archived_at IS NULL` from `_live` | `test_an_archived_application_is_in_no_section` |
| Drop `user_id == user_id` from `_live` | `test_another_users_application_is_in_no_section` |
| Drop all three `application_events` indexes | 3 of 4 `test_no_queue_section_scans_its_table` |
| Remove `'stale_saved'` from the Zod enum | `test_enum_parity[queueSectionKeySchema]` |

### 3.6 "Does `make acceptance` leave anything behind?"

No, and M2d is the first check that leaves *nothing*.
`check_application_tracking` leaves one archived application by design and says
so; `check_daily_queue` clears the next action it set and asserts the
application ends un-archived with no date. The browser walk's interview test
does leave its application archived — an `interview_scheduled` event cannot be
deleted, so archiving is the only way to take the role back out of the queue,
and that is stated in the test.

### 3.7 "Does anything here log personal data?"

No logging statement exists in either new module. The queue reads job titles and
company names, which are public, plus dates the user entered.

---

## 4. A prediction the plan made that did not come true

The plan added M2b's four enums to `test_enum_parity.py` and predicted **at
least one would disagree** with Python, reasoning that hand-transcribed and never
machine-checked is exactly the condition that produced M2c's defect.

All four were correct on the first run.

Recorded rather than deleted. The prediction was sound and the outcome was
better than it; deleting it afterwards would leave a false impression that the
guard was added on a hunch. The guard stays either way — it now covers thirteen
enums instead of nine, and `QueueSectionKey` is the first entry in it that is
not a database enum.

---

## 5. What M2d deliberately did not build

| Not built | Why | Where it lands |
|---|---|---|
| Best new internships | 'best' is a ranking with no score behind it (I4) | M3 |
| High-match roles closing soon | Needs a score *and* a deadline most sources never publish (A10) | M3 |
| Resume mismatch warnings | Needs requirement extraction and the evidence graph | M3 |
| The one thing to do today | Ranking across four heterogeneous row types | M3 |
| Dismiss / snooze | New state, a new table, and a decision about whether a dismissed row returns tomorrow | Unscheduled |
| `assessment_due_at` | §7.1: `next_action_at` already carries the date | Only if an assessment deadline must differ from the next action |
| Reminders by email or push | An outbound action, and M2 has no delivery path | Unscheduled |

**None are stubbed.** The first four are named on the page with their reason and
their milestone, rendered from the API's own `deferred_rows`.

---

## 6. Carried into M3

1. **ADR 0014's rule will be tested immediately.** A `match_result` is a fact
   about a scoring run, not about a job; when `ruleset_version` changes, old
   results stay true about their run and stop being true about the role. The
   same current-state-versus-history choice, with more at stake.
2. **The four deferred rows are M3's acceptance surface.** Each has a written
   reason in `DEFERRED_ROWS`; when M3 lands, the row and its reason are deleted
   together, and a test that the count is four will need updating deliberately.
3. **`TERMINAL_STAGES` excludes `offer` from the queue.** That is a judgement —
   an offer is a decision rather than a chase, and the pipeline shows it
   prominently — and it is the kind of judgement a real user would overturn in a
   week. It is one tuple in one file.
4. **The parallel-load ceiling on the seeded suite is real and now has two
   instances** (§2.6 here, §2.6 in M2c). 39 tests against one `next dev` server
   with four workers. The next milestone that adds browser tests should expect a
   third rather than be surprised by it.
