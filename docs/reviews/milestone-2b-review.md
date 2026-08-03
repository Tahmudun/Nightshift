# M2b review — the loop: save, apply, track

Written per `CLAUDE.md` §5, before the milestone is claimed. The brief is to
look for hallucinated certainty, silent data loss, race conditions, retry
storms, accessibility gaps, privacy overreach, and tests that assert nothing.

Ten findings. **Six were in code or tests that reported success**, which is the
sixth milestone running to record that pattern.

---

## 1. Fixed during the slice

### 1.1 The event timeline could not be ordered — `now()` is per transaction

**Severity: high. Silent, and the rows all look present.**

`application_events.created_at` defaulted to `now()`, copied from every other
table in the schema. Postgres's `now()` is the *transaction* timestamp, so
every event written in one transaction shares it. Measured directly:

```sql
begin; insert x3;
select count(distinct now_col), count(distinct clock_col) from t;
-- 1 | 3
```

With one distinct value, `ORDER BY created_at, id` falls through to `id`, which
is a random UUID. The history renders complete, in a plausible order, and
wrong. Two of the plan's own tests failed on this before anything was changed —
`test_archive_and_restore_both_leave_a_trace` expected
`[saved, archived, restored]` and got a permutation.

Fixed at the column: `clock_timestamp()`, which advances within a transaction.
Every other table keeps `now()`, which is correct for them — this is the only
append-only log where the order rows were written *is* the data.

Guarded by `test_events_written_in_one_transaction_keep_their_order`, proven
able to fail: `ALTER ... SET DEFAULT now()` turns 3 tests red.

### 1.2 A concurrent save returned HTTP 500

**Severity: medium. Reproduced against Postgres before being fixed, per the
M1d practice with the `merge_jobs` deadlock.**

`save_job` read, found nothing, and inserted. Four simultaneous POSTs for one
job, fired from a thread barrier against the real API:

```
round 1: codes=[200, 500, 200, 201] rows=1
round 2: codes=[500, 500, 201, 500] rows=1
round 3: codes=[500, 500, 500, 201] rows=1
...
```

**Data integrity never broke** — one row every time, which is the unique
constraint doing its job. What broke was what the loser was told. A person with
the job list open in two tabs gets a server error for saving something that
saved fine.

Fixed by running the insert in a savepoint and re-reading on `IntegrityError`.
The constraint remains the guarantee; the savepoint only decides the response.
Re-measured, same six rounds:

```
round 1: codes=[201, 200, 200, 200] rows=1
...
round 6: codes=[201, 200, 200, 200] rows=1
```

Zero 500s. Regression test:
`test_a_lost_save_race_returns_the_winner_not_an_error`.

### 1.3 A tracked job flashed an actionable "Save" button

**Severity: medium. Found by a browser test catching the element mid-swap.**

`SaveJobButton` rendered the save button whenever `data` was undefined, which
includes the whole time the query is in flight. For a job that is already
tracked, that is a live button offering an action the user has already taken —
and Playwright landed a click in exactly that window on the second seeded run:

```
locator resolved to <button>Save</button>
attempting click action
element was detached from the DOM, retrying
```

The flake was the product telling the truth about itself. Fixed with a pending
state; the control renders an inert placeholder until it knows.

### 1.4 An archived application looked unsaved, and Save did nothing

**Severity: medium.**

`SaveJobButton` called `fetchApplications()` with no `archived` flag, so the
route filtered archived rows out. An archived application was therefore
invisible to the control, which offered to save the role again — and the save
returned 200 having changed nothing. A button that responds to a click by
staying exactly the same.

Fixed by querying with `archived: true` (which means "do not filter them out",
not "only archived") and labelling the chip `· archived`. Pinned by
`test_still_reports_an_archived_application_instead_of_offering_to_save_it_again`,
which also asserts the query argument, because the rendering is correct for the
wrong reason if the flag is dropped.

### 1.5 A test that could not detect the thing it tested

`test_a_stage_change_records_its_classification` asserted on the event object
`change_stage` **returns**. That object is constructed in memory and carries
the right fields whether or not it was ever written. Deleting `session.add`
left it green. It now reads the rows back.

The plan predicted this mutation would fail two tests; it failed one, and that
discrepancy is what exposed the hole.

### 1.6 Three client-side tests passed before the schema existed

`expect(() => applicationSchema.parse(x)).toThrow()` passes when
`applicationSchema` is `undefined`, because `undefined.parse` throws. Three of
the five new schema tests were green against a module that did not exist.
Rewritten with `safeParse`, which fails on a missing schema, and the two
refinement tests now assert the issue *path* rather than only that something
went wrong.

### 1.7 The I5 source guard had two holes, both found by tightening it

`test_the_stage_machine_is_the_only_thing_that_moves_a_stage` excluded the
stage machine by **basename**. There are two `applications.py` in this tree, so
a route assigning `current_stage` directly was invisible. Comparing by full
path made it go red immediately — on a false positive, because the substring
`.current_stage =` also matches `Application.current_stage == stage`, which is
a filter. Now a regex that excludes `==`. The basename exclusion had been
hiding the substring bug.

---

## 2. Interrogated and accepted

### 2.1 `_load` runs four queries per mutation, and that is fine at this size

Measured by reading the code rather than guessing: a stage change runs `_load`
twice and `_to_detail` once. `_load` is one SELECT plus three `selectinload`
round trips, so:

```
load (4) + reload (4) + events (1) = 9 round trips per mutation
```

Against a local Postgres at one user with a 31-job corpus, the seeded browser
suite completes the full loop — save, apply, note, stage change, archive,
restore, stage reset — in **15.2 s** including `next dev` compiles. This is not
a problem to solve now, and saying so with a number beats assuming.

It becomes one when a user has hundreds of applications *and* the reload is on
the critical path of a list render. Neither is true. Recorded rather than
optimised.

### 2.2 The closure prompt survives a repost, correctly

Walked by hand. `needsClosurePrompt` takes the **last** `listing_closed` event
and asks whether any `stage_changed` was written after it, by `created_at`.

- Listing closes → prompt appears.
- User sets `withdrawn` → prompt gone. Asserted:
  `drops the prompt once the user has answered it`.
- The role is reposted and later closes again → a *new* `listing_closed` with a
  later `created_at` → the prompt returns.

That last case is the one a "has any closure event" implementation gets wrong,
and it is the realistic one: employers repost.

Ordering by `created_at` rather than `occurred_at` matters here and is
deliberate — an `interview_scheduled` event carries a *future* `occurred_at`,
so an interview booked for next month would otherwise sort ahead of everything
and suppress the prompt.

### 2.3 Nothing in this project can submit an application

Asserted three ways rather than promised in a docstring:
`PoliteClient`'s public surface is exactly `{get_json, get_json_conditional,
get_text}`; no route handler's name contains `submit` or `autoapply`; and the
browser test asserts `getByRole('button', { name: /^apply$/i })` has count 0 on
the application page. Mutation-checked: adding `post_json` to `PoliteClient`
turns the first red.

### 2.4 Privacy

No new personal data is collected. `application_url` and
`source_of_application` are user-entered, notes are user-written, and nothing
is sent anywhere — the only outbound HTTP in this project is `PoliteClient`
reading public job boards. No email bodies, per the anti-pattern list.

---

## 3. Open, recorded rather than fixed

### 3.1 `next_action_at` is a UTC instant used as a local date

**Severity: low now, higher at M2d.**

The date input yields `2026-08-05`; `new Date(...).toISOString()` makes that
`2026-08-05T00:00:00.000Z`, which is **8:00 PM on 4 August in New York**. The
round trip is self-consistent — the page slices the ISO string back to
`2026-08-05` — so today nothing looks wrong.

It stops being self-consistent the moment something compares the value to
"today". Measured: an instant of `2026-08-05T23:00:00Z` renders as `2026-08-05`
here and is also 5 August in New York, but midnight-UTC values are the previous
evening locally. **M2d's daily queue reads exactly this column**, so the queue
is where a day-boundary bug would surface, and it should decide whether this is
a date or an instant before it does.

`users.timezone` already exists and nothing reads it. That is the fix when it
is needed.

### 3.2 Accessibility gaps in the new controls

M4 owns the accessibility pass; recording these now so it inherits a list
rather than a search.

- The stage `<select>` carries `aria-label="Stage"` and the note `<textarea>`
  `aria-label="Note"` — usable, but neither has a visible `<label>` associated
  by `for`/`id`. A visible label is better than an accessible name.
- The closure prompt is `role="status"` (polite). A listing coming down is not
  urgent enough for `role="alert"`, which interrupts; this is the right choice
  but it has not been checked with a real screen reader. Nothing in this
  project has.
- No test asserts focus-visible styling on the new buttons. That gap was
  already recorded at M0 and is unchanged.
- The archived state is conveyed by a text label as well as colour, which is
  §12.4's rule and is asserted in the browser suite.

### 3.3 `make acceptance` leaves one archived application behind

Stated rather than hidden, and `check_application_tracking`'s docstring says
so. `make reset-db` clears it. The alternative — deleting the row — is
impossible by design (§1 of ADR 0012's consequences), which is the correct
trade.

### 3.4 The seeded browser test mutates the developer's own corpus

It saves two jobs, walks one to `interview`, and resets it to `saved`. It is
idempotent — run twice back to back, 31 passed / 1 skipped both times — and it
normalises the stage on entry rather than trusting its own tidy exit, because a
test that only survives being run to completion fails the first time somebody
interrupts it.

The residue is two saved applications. That is visible on `/operate/pipeline`
and is the honest cost of testing the loop against a real stack.

---

## 4. What the next milestone inherits

Ranked.

1. **`next_action_at`'s date-versus-instant question** (§3.1). M2d reads this
   column; decide there.
2. **The nine-round-trip mutation path** (§2.1). Fine now, measured, and the
   first thing to look at if the application page ever feels slow.
3. **Accessibility** (§3.2). M4's pass, with the list above as its input.
4. **Contacts are not built.** Named in the API's own `deferred_fields` and on
   the application page, unscheduled.
