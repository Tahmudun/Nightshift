# Milestone 5b review — identity, and the two facts that were kept in two places

**Date:** 2026-08-20
**Branch:** `m5b-identity`
**Scope:** the identity slice — `user_credentials`, `user_sessions`, argon2id,
`/auth/sign-in|token|sign-out|me`, default-deny at the router, `nightshift users create`,
a seed that plants two accounts, the Next.js proxy, the session gate, and the enumerating
isolation test that is the milestone's whole point. ADR 0037.

---

## 1. The shape of what went wrong this time

M4b's finding was about the **instrument** — the suite and the product were not looking at
the same thing. M4c's was about the **corpus** — every claim was tested against the only
data that could not falsify it. M5b's is about **seams**:

> **A fact that lives in two places is not one fact. It is two facts that happen to agree
> today, and nothing tells you the day they stop.**

The slice already learned this once, loudly, and wrote it down. ADR 0037 §4a is the story:
`require_session` depended on `current_user` while every route test overrode
`current_user_id`, so a handler could believe it was serving A while the guard believed
nobody was signed in. The fix was to give them one seam — `require_session` depends on
`CurrentUserId` — and the ADR says exactly why:

> **two independent entry points into "who is this", which anything replacing one can
> desynchronise.** […] One seam, so the two cannot disagree.

That reasoning was applied to the dependency and **not carried across the rest of the
slice.** This review found two more places with the identical shape, both shipped, both
invisible at their defaults. Neither is a leak — the isolation property M5 is judged on
holds — but both are the same mistake the milestone had already diagnosed once.

Finding 2.3 is different in kind and is the more serious of the three.

---

## 2. Findings

### 2.1 The cookie's lifetime and the session row's lifetime were two constants and a comment — **fixed**

**What was wrong.** `_set_cookie` sized the browser's `Max-Age` from
`Settings.session_lifetime_days`. `create_session` set the row's `expires_at` from
`identity.SESSION_LIFETIME`, a module constant nothing passed the setting into. The two
were related by a comment on the config field saying they "mirror" each other, and by
nothing else. `session_lifetime_days` is a real, range-validated setting (`ge=1, le=365`)
that a person is invited to change.

**Why it survived.** Both default to 30. Every test in the suite ran at the default, so the
two agreed in every run.

**And it is not an obscure knob.** `SESSION_LIFETIME_DAYS=30` ships in `.env.example`, which
is the file a person is told to copy and edit. `tests/test_env_example.py` even exercises the
value — but it checks that bash, `docker compose` and python-dotenv *parse* it identically,
which is a question about quoting rather than about what the number does. The setting was
tested for being readable and never for being obeyed.

**Both directions are silent, and neither reads as configuration:**

| Set to | What the browser does | What the server does | How it looks |
|---|---|---|---|
| more than 30 | keeps sending the token | expired the row at day 30 | signed out mid-session holding a cookie that still looks good — reads as a bug |
| less than 30 | drops the cookie early | row stays resolvable for the full 30 days | the setting reads as "how long a sign-in lasts" and shortens only the browser's memory of it, not the credential's life |

**Shown able to fail.** `test_the_cookie_expires_when_the_session_row_does` was written
first and run against the unfixed code:

```
AssertionError: the cookie lasts 604800s and the session row lasts 2592000s.
```

Seven days against thirty, from a single setting whose documented job was to keep them
equal.

**The fix is structural, not a corrected number.** `session_lifetime_days` is now the
authority: both `/auth/sign-in` and `/auth/token` pass it to `create_session` through one
`_lifetime()` helper, and the cookie's `max_age` is **computed from the session that was
actually minted** — `issued.expires_at - utcnow()`. The browser's copy is derived from the
row rather than recalculated beside it, so they cannot disagree by construction.
`identity.SESSION_LIFETIME` stays as the domain's default for callers with no `Settings` to
hand.

`/auth/token` did not read `Settings` at all before this, which is the same divergence a
second time: a bearer session and a cookie session are one row in one table and were being
issued under two rules.

### 2.2 `next.config.ts` documented a variable the same slice deleted — **fixed**

The rewrite's comment read *"The public variable still exists for the Playwright specs,
which talk to the API directly to set up their state."* `NEXT_PUBLIC_API_BASE_URL` does not
exist — `.env.example` records its removal, and the specs go through the proxy at
`WEB_ORIGIN + /api/ns` (`e2e-seeded/api.ts`). Both halves of the sentence were false: the
variable is gone, and the specs deliberately stopped taking a private door into the API.

Trivial next to 2.1 and 2.3, and worth recording because of *where* it is. It sits four
lines above the rewrite that makes the cookie work at all, and it is the file somebody
reads when the session breaks in a deployment. A comment that confidently describes a
mechanism that does not exist costs more there than almost anywhere else in the repo.

### 2.3 `nightshift seed` created accounts with a published password, in any environment — **fixed**

**This is the finding.** The other two are seams; this one is a live hazard aimed directly
at M7.

`cmd_seed` plants two accounts at fixed UUIDs, gives both `settings.dev_user_password` —
default `nightshift-demo-password` — and prints it to stdout. It did this unconditionally,
against whatever database `NIGHTSHIFT_DATABASE_URL` named, with no environment check.

**The dangerous shape is the second run, not the first.** `set_password` sits *outside* the
`if existing_user is None` branch, deliberately, because it is an upsert. So seeding a stack
that already holds those accounts **resets their passwords to the published default** rather
than skipping them. A command whose name reads as "load the fixture jobs" hands a stranger a
working login.

**Shown able to fail**, and the failure output is the finding rather than a description of
it. With `nightshift_env` forced to `production`, the unfixed seed ran to completion:

```
  user dev@nightshift.local already present
  user second@nightshift.local already present
  both accounts sign in with the password 'nightshift-demo-password'
```

**Why this is in scope rather than deferred to M7.** A16 put multi-user correctness in scope
from M5 because it is *"a property of being deployable at all, not a bet on volume"*, and
CLAUDE.md §8 was narrowed to say so. M5b is the milestone that decided a deployed product has
no business handing its corpus to a stranger; this is that rule one command over. The
precedent is already in the codebase: `Settings._forbid_dev_password_in_production` refuses
to *start* with a development database password. This refuses to *seed*, for the same reason
and in nearly the same words.

`cmd_seed` now returns 1 with a message naming `nightshift users create` as the alternative.

---

## 3. What was looked for and found sound

Recorded because a review that only lists defects makes the rest look unexamined.

| Checked | Verdict |
|---|---|
| **Timing side channel on sign-in** | `authenticate` verifies a throwaway argon2 hash when no user is found (`_burn_a_verification`), so "no such email" is not measurably faster than "wrong password". The shared 401 message is not undone by the clock. |
| **The token in the database** | Only a SHA-256 hash is stored, and the plaintext exists exactly once, as `create_session`'s return value. `test_the_plaintext_token_is_never_stored` pins it. |
| **Fast hash for the token, slow hash for the password** | Correct and deliberately opposite choices. A 256-bit CSPRNG token has no dictionary to slow down; a human-chosen password does. |
| **Failure modes collapse to `None`** | Every path that could plausibly "fall back to the dev user" returns `None` and lets the caller raise. `InvalidHashError` included — an unparseable credential does not match, rather than matching. |
| **Revocation vs. deletion** | Sign-out stamps `revoked_at` rather than deleting, so "ended deliberately" stays distinguishable from "never existed" — the same distinction I3 draws for a listing. |
| **Email normalisation** | Case and whitespace only. Gmail's dot-and-plus folding is explicitly *not* applied, which would silently merge two accounts a person considers distinct. |
| **The degraded path** | `SessionGate` keys on a definite 401 and never on "I could not ask", so M0's offline shell survives. This was wrong in the first draft and is right now. |
| **Cache after sign-out** | `SessionIdentity` calls `queryClient.clear()`, not a single-key invalidation — the pages behind the gate hold another person's applications and résumés. |
| **Accessibility of the new surface** | The sign-in form labels both inputs, uses `autoComplete="username"` / `"current-password"`, marks the error `role="alert"` and the pending state `role="status"`. |
| **Registration** | Absent rather than present-and-disabled, which is the right call on the one surface where half-built is least acceptable. |

---

## 4. Two things left open deliberately

**A session is never renewed.** `SESSION_LIFETIME`'s docstring says "how long a session lives
*without being renewed*", and nothing renews one — the expiry is absolute from sign-in, not a
sliding window of inactivity. This is not an oversight to fix quietly: renewal is a **write on
a read path**, which is exactly what got `last_seen_at` deleted earlier in this slice for
being persisted non-deterministically. A sliding session needs a write path that actually
runs, and there is nowhere to put one until M13's account page. The wording is the only thing
wrong today, and it is now the config field that carries the explanation.

**Expired and revoked sessions are never collected.** `user_sessions` grows without bound.
At one account and a thirty-day expiry this is a row a month, so it is not a problem and
building a sweeper for it would be CLAUDE.md §8's "building for imaginary scale". It belongs
with M13's hardening, and it is recorded here so that milestone does not have to rediscover
it.

---

## 5. Evidence

| Check | Result |
|---|---|
| `make check` | **exit 0**, run clean after all three fixes landed — ruff format (187 files), ruff check, prettier, mypy (80 source files), `tsc` all clean; **2128 Python passed** in 13m18s; **799 web passed** across 55 files |
| The two new tests | 2126 → 2128 is exactly the two this review added, so neither displaced an existing test |
| `test_the_cookie_expires_when_the_session_row_does` | red at 604800s vs 2592000s before the fix, green after |
| `test_the_seed_refuses_to_run_in_production` | red — printed the demo password in `production` — before the guard, green after |
| The isolation suite's four mutations | recorded in PROGRESS and ADR 0037; unchanged by this review |

**On the run itself.** The first attempt at this `make check` is not the one in the table,
and the reason belongs in a review rather than in a commit message. Ad-hoc `pytest`
invocations and `make check` share one Postgres, and running both at once produced a real
`DeadlockDetectedError` inside the suite:

```
deadlock detected … Process 63751 waits for RowExclusiveLock … blocked by process 63649
```

**A test run that overlaps another test run is not evidence**, so it was killed and re-run
with nothing else touching the database. This is Q8 with a second face — Q8 is about
`make check` wiping `company_locations`, this is about two suites corrupting each other's
results — and both are the same underlying fact: the suite and the dev stack share a
database. It strengthens the case for the separate test database Q8 asks about.

### 5.1 The e2e suites, and the thing this review could not close

`make verify` — **exit 0, 109 checks**, including `✓ signed in as dev@nightshift.local`,
which is a real sign-in over a real socket through the code §2.1 changed. That is the
instrument that caught the uncommitted-session-token bug earlier in this slice, so it is
the one that most needed to be green.

`make acceptance` — **failed, and not where it matters.** It stops at step 5 of 7
(`test-e2e`, the offline suite) on two known city failures, so `verify` and
`test-e2e-seeded` never ran and had to be run by hand afterwards.

**A wrong conclusion drawn and corrected during this review**, recorded because the
correction is the useful part. Seeing the offline suite gate the two meaningful steps, I
called the target's ordering a defect and proposed reordering it. That is wrong, and the
comment directly above the target says why: `test-e2e` runs *before* the API starts on
purpose, because that suite asserts the shell reports "api unreachable" and that the city
needs no API at all — **and a running API turns both into passes for the wrong reason.**
Reordering would have converted two real assertions into false passes. The Makefile is
right; I had not read it before proposing to change it.

The real problem is narrower: **the frame-timer test is deferred in prose but not in
code.** PROGRESS reasons correctly that raising its timeout would hide the regression it
exists to catch — but it still runs, still fails, and therefore `make acceptance` can never
exit 0. A milestone whose scriptable gate cannot pass has no working gate. Resolving that
belongs with M7's performance work, and it needs a decision (quarantine with a documented
reason, or fix) rather than another timeout.

`make test-e2e-seeded` — **84 passed, 3 failed, 1 skipped**, where PROGRESS records 87
passed / 0 failed. **This review does not close it, and does not claim the fixes are
innocent.** The three failures reproduce; run alone the file is 4 failed / 25 passed, which
is *worse* and so rules out the load-sensitivity that explains the frame timer and the scale
guard. The baseline comparison — the same spec at `7675d11` — was started and not finished.
Nothing in §2.1–2.3 plausibly reaches MapLibre, but this project's own history says a
plausible story is not evidence. PROGRESS's "Next exact action" carries the full state and
names the baseline run as the next thing to do.

---

## 6. The lesson, stated so the next milestone can use it

M5c adds an MCP server: another client, another way to present a session, another set of
routes. Its failure mode is named in advance by this review rather than by hindsight —

> **Every fact this milestone owns should have exactly one place it is decided, and every
> other place should be computed from that one.**

The isolation test already enforces this for *routes*: a new endpoint with no entry in
`CASES` turns CI red. There is no equivalent for *constants*, which is why 2.1 shipped. When
M5c gives the MCP server its own session lifetime, its own cookie, or its own idea of who the
caller is, the question to ask is not "does it agree?" but "**can it disagree?**"
