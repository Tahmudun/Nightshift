# ADR 0037 — Identity is ours, and the door is shut by default

- **Status:** accepted
- **Date:** 2026-08-20
- **Milestone:** M5b
- **Relates to:** `CLAUDE.md` §2 ("Not yet: auth provider… Add when there is a concrete need, with an ADR"), §8; AMENDMENTS A3, A9, A16; `PRODUCT-SPEC.md` §5.6; `nightshift/domain/identity.py`, `nightshift/api/deps.py`

## Context

AMENDMENTS A3 deferred authentication to M5 and made a promise about the bill:

> every table that belongs to a user carries a real `user_id` foreign key from
> the first migration, and every query filters on it. […] When auth arrives at
> M5 it is an adapter plus a middleware, not a migration of every table in the
> schema.

That promise held **on the schema**: two new tables, no existing table altered.
It did not hold on the test suite, and the gap taught this ADR something — see
"§4a, and the mistake that produced it" below.

A16 is why it is due now. The project stopped being one person's database, and
multi-user *correctness* — not scale — became a property of being deployable at
all. `CLAUDE.md` §8 was narrowed to say exactly that.

`PRODUCT-SPEC.md` §5.6 offers three answers: Auth.js, Clerk, Supabase Auth. All
three are declined, and the reasons are not preference.

## Decision

### 1. The sessions live in our API, in our Postgres

**Clerk and Supabase Auth reach the network.** `make demo` working offline from
a clean clone has been a hard requirement since M0 — `CLAUDE.md` §4 calls
fixing it the highest-priority task in the repo, and A9 made offline-by-default
a property of the configuration rather than a habit. A hosted login breaks it,
and the only way to keep the demo working is a bypass. A bypass is invariant I7
— "never let a mock become the product" — written as a login screen, on the one
surface where a mock is least acceptable.

**Auth.js lives in the frontend.** If Next.js decides who somebody is, FastAPI
must trust a header that Next.js sets, and a trusted header is how one missed
check becomes another person's applications. It also cannot serve M5c: the MCP
server is Python with no browser, and it would be authenticating against a
system that only speaks browser.

The "adapter" §5.6 asks for is `api/deps.py`, which already existed and is one
file. That is the whole isolation §5.6 wanted, and it cost nothing because A3
built it three milestones early.

### 2. A password is a row, not a column

`users` has no `password_hash` and will not get one. Credentials live in
`user_credentials`, keyed `(user_id, method)`, with `method` a PG enum holding
one value today.

This is a direct answer to a stated requirement. Asked how people should sign
in, the human said *"can be email + password for now but eventually that should
change."* A column welds the method to the account; a row does not. Adding
Google later is an INSERT and one new enum member — not an `ALTER TABLE users`,
not a data migration, and not two accounts for one person who uses both.

argon2id via `argon2-cffi`, the current OWASP default. The minimum is a length
floor of 12 and nothing else: NIST SP 800-63B withdrew character-class rules
because they push people toward `Passw0rd!` and away from length, which is the
property that actually resists an attack.

### 3. Sessions are rows, and what is stored is a hash

A JWT cannot be revoked. "Sign out", "sign out everywhere", and account deletion
all have to actually end a session rather than wait for one to lapse, and M13 is
a hardening milestone that will ask for all three. The cost is a primary-key
lookup per request against the one Postgres box `CLAUDE.md` §8 says is the
answer and will be for a long time.

`user_sessions.token_hash` holds SHA-256 of the token, so a database dump is a
list of expiry times rather than a set of live logins.

**The hash is fast, deliberately, and that is the opposite of the choice made
one table over.** A password is short and human-chosen, so slowness is the
defence. A session token is 32 bytes from `secrets`: there is no dictionary to
slow down, and argon2 on every authenticated request would cost a page load to
buy nothing.

`revoked_at` stamps rather than deletes. "This session ended deliberately" stays
distinguishable from "this session was never here" — the same distinction
invariant I3 draws for a listing that stopped appearing.

### 4. Default-deny, at the router

Every router except `/health` and `/auth` is included in `main.py` with
`dependencies=[Depends(require_session)]`. Not per handler.

Before this, a route was protected because its handler happened to declare
`CurrentUserId`. `PROGRESS.md` named the risk in as many words: *"routes filter
by convention today, and one missed filter leaks another person's
applications."* Attaching the dependency to the router inverts the default — a
route added in M5c, M8 or M13 is behind a session because it exists, and opening
one is a visible edit to a list in `main.py`.

`/jobs`, `/companies` and `/city/signals` are behind it too, though they serve
the shared corpus. A deployed product has no business handing its whole corpus
to an anonymous request.

### 4a. `require_session` shares one seam with `current_user_id`, and the mistake that produced it

`require_session` takes `CurrentUserId`, not `CurrentUser`. That reads like an
arbitrary choice between two equivalent dependencies and is not.

The first draft took `CurrentUser`. Both resolve the same session, so nothing
was wrong about a real request — and **145 route tests went red**, because they
override `current_user_id` and the router guard went on resolving a session
that was not there.

The red tests are the smaller half of it. The larger half is the shape: **two
independent entry points into "who is this", which anything replacing one can
desynchronise.** A test override is the benign version. A future impersonation
or service-account path is not, and in that world a handler can believe it is
serving A while the guard believes nobody is signed in. One seam, so the two
cannot disagree. That one line turned 84 of the 145 green.

The remaining 61 were tests of the corpus routes — open before this ADR, closed
by it. Those are the decision working rather than a defect, and each fixture
now names a caller explicitly.

### 5. `current_user_id` raises. There is no fallback

It returned `settings.dev_user_id` for every request through M0–M4. It now
raises 401, and there is no flag, environment check or "make local development
easier" path that restores the old behaviour.

This is the single most dangerous line in the milestone. A fallback here does
not leak one route — it makes every anonymous request in the entire application
act as a person, silently, and every isolation test still passes because they
all sign in. `test_the_identity_dependency_has_no_fallback` asserts the raise
directly.

### 6. Registration is closed, and there is no disabled form

Asked who may create an account, the human said *"for now, just me. soon
invite-only, eventually anyone."*

So there is no `POST /auth/register`. Accounts are created by
`nightshift users create --email … --create`, which prompts for the password
rather than taking it as an argument — a `--password` flag lands in shell
history and in `ps`, and a password leaked by the tool that set it is a bad
joke.

Invite-only is a token table and a form. Open is a flip after that. Neither is
built, and neither is stubbed: a registration endpoint built now and left
disabled is a half-built feature on the surface where half-built is worst.

### 7. The browser reaches the API through the web app's own origin

The web app runs on `localhost:3000` and the API on `127.0.0.1:8000`. Those are
different *sites*, so a `SameSite=Lax` cookie set by the API is never sent back
by a fetch from the web app — and `SameSite=None` requires `Secure` requires
HTTPS, which local development does not have.

M5b.2 adds a Next.js rewrite so the browser calls `/api/ns/*` on its own origin.
The cookie becomes first-party, CORS stops mattering for the browser path, and
in production the API need not be publicly exposed at all. In code it is one
rewrite rule and one constant, because `apps/web/src/lib/api.ts` is the only
place that knows the base URL.

The token is **also** accepted as `Authorization: Bearer` against the same
sessions table. `scripts/verify.py` uses it today and M5c's MCP server will
tomorrow; neither has a cookie jar. One table, one revocation path, two ways to
present the same token.

## Consequences

**Deliberately not built, and each for a reason rather than for time:**

- **Password reset and email verification.** Both need an email sender: an
  account the human must create and a monthly bill. Filed as an open question
  rather than half-built. Until one exists, a mistyped address on an account is
  unrecoverable — which is tolerable while accounts are made by hand at a
  prompt, and is a blocker for open sign-up.
- **Rate limiting on sign-in.** A real gap, and named as one. The argon2 cost
  makes brute force expensive rather than impossible. It wants Redis, which is
  already running, and it belongs with M13's hardening or with the first public
  deploy at M7 — whichever comes first.
- **Revoking other sessions on a password change.** `set_password` deliberately
  leaves them. That is right for somebody who simply chose a better password and
  wrong for a compromised account; the difference needs a "sign out my other
  devices" affordance to sit behind, and there is no account page yet to put one
  on.
- **2FA, "remember me" tiers, session listing.** Nothing asks for them.

**What this makes true, verified rather than asserted:**

`tests/test_two_users_cannot_see_each_other.py` reads the application's own
route table out of its OpenAPI schema and requires every one of its 48 routes to
carry an explicit isolation classification. A route with no entry fails the
suite. Signed in as A, every route is called with B's identifiers and B's UUIDs
must not appear anywhere in the response body — a substring scan of the whole
response, not a field check, because a field check only inspects the fields
somebody thought of.

**The defect this ADR most wants remembered.** `get_db_session` commits
nothing by design — write routes commit explicitly, so a handler's body says
whether it writes. The first draft of `/auth/sign-in` and `/auth/token` flushed
and did not commit, so **the token went back to the client and the row it named
was rolled back.** Every unit test passed, because the fixture yields one open
transaction shared by the sign-in and the request after it.

`make verify` caught it, and only `make verify` could have: it starts a real
server and signs in over a real socket, so it is the one instrument in this
repo that does not share the harness with the code under test. `last_seen_at`
was removed while fixing it, for the same reason inverted — it could only ever
be written by a request that committed for unrelated reasons.

**Shown able to fail, four ways** (`docs/PROGRESS.md` records the output):

| Mutation | Result |
|---|---|
| Delete one `.where(Application.user_id == user_id)` | 7 routes red |
| Restore the dev-user fallback in `deps.py` | 43 routes red |
| Include one router outside the default-deny loop | 3 routes red |
| Add a route with no isolation case | classification test red |

**The third mutation is the finding worth keeping.** Removing `require_session`
from the `jobs` router turned three of its four routes red — not four.
`GET /jobs/{job_id}` stayed green, because its handler *also* declares
`CurrentUserId` and 401s on its own. The two guards overlap, neither is
redundant, and neither alone covers the surface. That is an argument for keeping
both, and it was produced by the mutation rather than by reasoning about it.
