# QUESTIONS

Things that need a human. Batched, not blocking — work continues around them.

Format: newest first. Answered questions move to the bottom with the answer and
the date, because the reasoning is usually worth more than the decision.

---

## Q12 — CI takes fifteen minutes against a five-minute target. Spend a slice on it, or accept it?

**Raised:** 2026-08-21 (M5b, opening PR #18) · **Answered:** 2026-08-21 · **Type:** working practice · **Blocking:** no

**ANSWERED 2026-08-21 — option 1, accept it, with the door left open.** The
human's words: *"the 15 min ci is fine for now, if it irks me later we can do
something about it."*

**What that decides and what it does not.** It decides that no slice is spent on
CI speed now. It does **not** retire the reasoning below — the behavioural risk
is real and is now carried deliberately rather than unnoticed. The trigger for
revisiting is stated in the answer itself: **the human finding the wait
annoying.** That is a legitimate trigger, because A14's argument was always about
behaviour rather than seconds, and the person whose behaviour is at stake is the
one who just answered.

**A14 is not amended.** Its five-minute figure now describes an intention this
repo misses by three times, and saying so in `ci.yml`'s header — which was
corrected in place at `06725d6` — is more honest than editing the target down to
whatever today happens to cost. A target you move to meet is not a target.

**What is preserved for whenever it is picked up:** the cheapest honest first
step is still a `--durations` run, and `pytest-xdist` is still the same piece of
work as Q8's separate test database. Nothing below is stale.

**What happened.** The `python` job was cancelled mid-suite at exactly 10m00s,
having reached 64% with **zero failures**. It was not a broken test — the suite
outgrew `timeout-minutes: 10`. Raised to 20 in the same commit, which unblocks
the PR and fixes nothing.

**The measurement.** 2128 python tests, 10m16s locally; on the runner, 6% → 64%
in 479s, extrapolating to ~12.7 minutes of pytest on ~2.5 minutes of setup. The
`e2e` job is eleven minutes behind it. Jobs run in parallel, so **wall clock is
about fifteen minutes** against A14's stated target of five.

**Why it is a real question rather than a chore.** A14's reasoning is
*"a slow CI is a CI you start skipping"*, and that is a claim about behaviour,
not about seconds. Fifteen minutes is the range where a person stops waiting for
the result and merges on local evidence — which is exactly the habit that let
the partial pin ship, because the pin is checkable *only* in CI.

**The options, with what each costs:**

1. **Accept it and move the target.** Free. Amend A14 to say what is true. The
   risk is the behavioural one above, and it compounds silently.
2. **Parallelise with `pytest-xdist`.** Probably the largest win for the least
   code — but the suite shares one Postgres, and this project has *already*
   measured a real `DeadlockDetectedError` from two suites overlapping on one
   database (2026-08-20). That makes xdist and **Q8's separate test database the
   same piece of work**, which is an argument for doing Q8 first.
3. **Find the slow tests.** The CI log has visible stalls — one stretch spent two
   minutes on 3% of the suite. Nobody has looked at where the time actually goes,
   so the cheapest honest first step is a `--durations` run.
4. **Split the job.** Moves wall clock, adds runner minutes and a second place
   for the pin to be checked.

**My recommendation:** 3, then 2 — measure before optimising, and fold it into
Q8 rather than treating them as two problems. But this is a slice of work with no
product visible at the end of it, so it is the human's call whether it happens
now or after M5c.

---

## Q10 — Sending email costs money. Which means no password reset. For how long?

**Raised:** 2026-08-20 (M5b) · **Answered:** 2026-08-21 · **Type:** cost / account · **Blocking:** no

**ANSWERED 2026-08-21 — deferred to the deploy, deliberately.** The human's
words: *"the domain and email thing are future concerns i wanna make sure things
are polished before worrying about that."*

**Which lands it at M7**, the milestone that already owns the first public
deploy, and it is the right home on the merits rather than a punt: an email
sender, a domain to send *from*, and HTTPS are one purchase and one afternoon,
and buying a sender before there is a deployed thing to send about would be
paying early for nothing.

**What is now true and must stay written down until then:** an account whose
password is forgotten is **unrecoverable except by `nightshift users create`
against the database**, and an address typed wrong is never checked. That is
tolerable for a user who is also the operator and stops being tolerable the
moment somebody else has an account. **It is therefore a gate on inviting a
second person, not on M7's calendar** — see Q11, which has the same gate.

M5b built accounts. It did **not** build password reset or email verification,
and both are blocked on the same thing: something that can send an email.

**What is missing today, stated plainly.** If you mistype your address when
creating an account, or forget your password, nothing in this system can help
you. There is no reset link because there is nowhere to send one. That is
tolerable right now — you are the only account and it is created at a prompt on
your own machine — and it is a hard blocker for the "eventually anyone" you
asked for.

**What it costs.** All three usual options have a free tier that comfortably
covers a product with tens of users:

| | Free tier | Then |
|---|---|---|
| Resend | 3,000 emails/month, 100/day | $20/month |
| AWS SES | 3,000/month for 12 months | ~$0.10 per 1,000 |
| Postmark | 100/month | $15/month |

**Why it is not free the way everything else here is.** Every other dependency
in this project runs on your machine — the tiles, the embeddings, the geocoder
fallback. Email cannot: sending mail that arrives requires a reputable IP, and
that is the thing you are renting. Running our own mail server is possible and
lands in spam folders, which is worse than not sending.

**Two things I need from you, and you can answer either separately:**

1. **A domain.** Reset mail from `@gmail.com` gets filtered. This needs an
   address at a domain you control, which is also the thing M7's deploy will
   need — so it is one purchase, not two.
2. **Which provider**, and an account on it. I would take **Resend**: the free
   tier is the largest of the three at the volume that matters, and it is the
   least configuration.

**What I will do until you answer**, and it is not nothing: accounts stay
closed, created by `nightshift users create`, which prompts rather than mailing.
Invite-only can also ship without email if the invite is a link you hand
somebody directly. **Open sign-up cannot** — that is the rung this question
blocks, and it is the last one on your list rather than the next.

---

## Q11 — Nothing rate-limits sign-in. Before or after the first deploy?

**Raised:** 2026-08-20 (M5b) · **Type:** security / scope · **Blocking:** no

> **STILL OPEN, but one of its two branches is now closed — 2026-08-21.** The
> human deferred the domain and the deploy to the polish phase (Q2, Q10), which
> removes the *"if you intend to hand somebody an invite before M7"* branch
> below. **Nothing is reachable from outside this machine, so there is no
> attacker with a route to the endpoint**, and the answer defaults to M7.
>
> **This is an inference from an adjacent answer, not the human's words on this
> question**, which is why it stays open. It closes for real on the same trigger
> as Q10: **the first invited user.** If somebody else is ever given an account,
> a rate limiter and a password reset both become due in the same breath, before
> the invite rather than after it.

A real gap, named rather than discovered later.

**What is true.** Sign-in has no rate limit. Somebody can try passwords against
`/auth/sign-in` as fast as the API answers. argon2id makes each attempt cost
real CPU — roughly 50ms — so this is expensive rather than free, and the 12
character minimum means a dictionary is not enough. But "expensive" is not
"prevented", and enough attempts against a weak password will find it.

**Why it is not built.** It needs somewhere to count attempts, Redis is already
running, and it is perhaps an afternoon. I did not build it in M5b because M5b
had one acceptance criterion — two users cannot see each other's data — and a
rate limiter does not move it. Doing it badly is also worse than not doing it:
a limiter keyed on IP alone locks out an office, and one keyed on email alone
lets anybody lock **you** out of your own account by failing your sign-in.

**The actual question is when, and there are only two sensible answers:**

- **Now**, if you intend to hand somebody an invite before M7. The moment a
  second person has an account on a machine you do not own, this stops being
  theoretical.
- **At M7**, with the first public deploy, which is where it belongs on the
  merits — alongside HTTPS, a real domain, and the `secure` cookie flag that
  only becomes true off `localhost`.

**What I would pick, asked directly:** M7. Nothing is reachable from outside
your machine until then, so there is no attacker with a route to the endpoint.
If you plan to invite somebody sooner, say so and I will move it.

---

## Q9 — The reference's sky is 70% of the frame. Ours can be 17% or 36%. Which?

**Raised:** 2026-08-18 (M4e Task 3) · **Type:** product / look · **Blocking:** no

> **STILL OPEN, and deferred rather than answered — 2026-08-21.** The human ran
> `make demo`, looked at the city, and reported *"it looks ok for now until a
> later polish and optimization phase."* That is a verdict on the whole frame
> and it is not an answer to this question, which asks for one number.
>
> **It belongs to that polish phase, and it now has company there**: the untuned
> roof wash and the 1.65 km spires of ADR 0035 are the same kind of open —
> decided, shipped, never looked at hard. **Do not raise `maxPitch` on a guess
> in the meantime.** The cost below is unmeasured and the machine is an Intel
> Iris Plus 645; measuring 82 against 78 is the first move whenever this is
> picked up, not choosing between them.

You approved the sky on 2026-08-18. This is the one thing about it I cannot
decide for you, because it is a trade and both sides of the trade are yours.

**The measurement.** MapLibre's pitch is the angle from straight *down*, so the
camera always looks below horizontal and the horizon sits near the top of the
frame. `docs/adr/0032` has the table; the short version:

| Pitch | Sky, as a share of the frame |
|---|---|
| 76 — today's opening pose | 12% |
| 78 — `CAMERA_LIMITS.maxPitch` today | 17% |
| 85 — MapLibre's own ceiling | 36% |

`02-skyline-grid-plane-light-columns.jpg` puts its horizon about **70%** down the
frame. That needs a pitch near 94°, which does not exist. So the gradient, the
sun and the stars can look like the reference; the *proportion of sky* can only
go as far as 36%, and only by raising the cap.

**What raising it costs.** The cap is 78 because the tile budget explodes past
it: a flatter camera sees much further, so many more tiles are in view for a
view of mostly nothing. I have not measured how much worse 85 is — I would
before changing it — but the direction is certain and the machine is an Intel
Iris Plus 645.

**What I would pick, asked directly:** raise it to 82. That is most of the gain
— roughly 27% of frame — at meaningfully less tile cost than 85, and it keeps a
hard stop before the ground goes fully edge-on. But you filed the reference and
you are the acceptance test, so if the sky should be as big as it can possibly
be, say 85 and I will measure what it costs and tier it.

---

## Q8 — `make check` wipes the offices you typed. Separate test database?

**Raised:** 2026-08-17 (M4e Task 6) · **Type:** engineering, with a cost in your
time · **Blocking:** no

The Python suite runs against the same Postgres the dev stack uses. This is
already known — PROGRESS records it as the `TRUNCATE` deadlock trap, where a
test and a live dev session fight over the same table and one of them hangs.
Today it did something else: `make check` emptied `company_locations` **and**
`geocode_cache`, so the city went back to "nothing is on a building yet" hours
after you filled the worksheet in.

Recovery is one command — `make offices` — and everything came back. Two things
still make it worth your decision rather than mine:

- **It is silent and it looks like a product state.** The city does not error.
  It draws the honest empty-city screen, which is a sentence this project
  deliberately made convincing, and nothing distinguishes it from the true
  version by looking.
- **A wiped `geocode_cache` costs the offline guarantee.** ADR 0022's bargain is
  that an address is geocoded once, ever, and the buildings it placed survive
  into an offline `make demo`. After a wipe the next `make offices` needs the
  network again, so `make check` can quietly make a later demo require it.

**Why I have not just done it.** A separate test database is the obvious fix and
it is not a patch: it changes `make test`, the CI job, `conftest.py`'s session
fixture, and it retires two documented traps that only exist because the suite
shares the dev stack. That is an ADR and a migration of the developer workflow,
and it is the kind of change that is annoying to have done to you mid-milestone
without being asked. The options, roughly:

- **A second database on the same container** (`nightshift_test`), created by
  `make up` and used by `pytest`. Cheapest, ~an hour, no new infrastructure.
- **A throwaway schema per test session.** Cleaner isolation, more machinery.
- **Leave it and document the recovery.** Free. Costs a rerun of `make offices`
  after every `make check`, forever, and relies on somebody noticing.

I would take the first. Say the word and it is the next thing I do.

---

## Q7 — No ATS posting names a street. How many company addresses will you type?

**Raised:** 2026-08-11 (M4a Task 1) · **Type:** product + your time · **Blocking:** no,
until the city needs a building
**ANSWERED 2026-08-11: "as many as you'd like — it makes no difference, I can do
them relatively fast."**

Which answers the scope question by removing it, so the shape was mine to pick.
`data/company-locations.yaml` ships as a **worksheet** with `street_address`
blank. Same pattern that answered Q5, which worked.

**Updated 2026-08-16 (M4e Task 1), and the update is a correction of my own
work.** The worksheet was pre-filled with the nine registry companies whose
postings parse to NYC. It now carries **all 23 registry boards**: `nyc_presence`
is derived from posting text, and posting text is not a company directory — a
board whose postings all say "Remote" can still be run out of an office on
Lafayette Street. The other fourteen have `city` and `state` left blank rather
than pre-filled with "New York", so nothing prompts an address in a city the
company may not be in.

**And the file now leads somewhere.** `read_worksheet` and `load_offices` were
complete and tested from M4a/M4b, and nothing outside the test suite called
either of them — so the answer above could not have changed a single pixel no
matter how many addresses were typed. `make offices` is the caller, added
2026-08-16 and verified live end to end (Datadog → `620 8th Ave` → `verified`,
BIN 1087186). The remaining gap is the renderer: a `building` placement is still
not drawn, which is M4e Task 6.

**CLOSED 2026-08-17: the worksheet came back filled.** 8 of 23 rows carry a
confirmed street address, 15 are deliberately blank, and `make offices` refused
none of them. Two offices are placed on real buildings (Datadog → BIN 1087186,
Ramp → BIN 1080672) and 20 of 31 seeded roles now resolve to `kind: building`.

**The answer to "how far do you want to take it" turned out to be the wrong
axis.** The filled rows are not 8 addresses; they are 23 decisions, and the
blanks carry more information than the fills. Three of them are reasoned refusals
written into the file — 1Password (remote-first, no street published anywhere),
A.Team (genuinely NYC, publishes no address), Abound (three conflicting
headquarters and an acquisition that invalidates some of them). And one is the
case §4.4 was written for: `jobs.lever.co/alloy` is **Alloy.ai of San Francisco**,
not the NYC identity-decisioning fintech that shares the name. Searching "Alloy"
surfaces two real, geocodable Manhattan addresses, both completely wrong for that
board. The file rejected both and said why.

That is the argument for a human-confirmed file, stated better by the file than
by the ADR: **the failure mode is not a missing address, it is a confident wrong
one**, and no automated proposer would have caught the Alloy collision.

Two things written into the file rather than assumed:

- **Blank is a correct answer.** A company with no NYC office, or one whose
  address is not to hand, loads as nothing — not a guess and not a city centroid.
  Its jobs stay in the unresolved layer, fully usable. The coverage page reports
  the fill rate rather than hiding it.
- **A wrong building is worse than no building**, because it looks exactly as
  confident as a right one and nothing downstream can tell them apart.

**I am deliberately not looking these up myself.** §4.4's argument is that the
address is the one fact in this system a human vouches for; me finding it on a
website and typing it in would make `confirmed_by` a fiction on the first row.
The OSM proposal path stays worth building later, because it proposes and a human
still promotes — but it is not what fills this file today.

M4's first task was a census, and the answer was a clean zero.
`services/api/scripts/census_location_text.py` walked 247 recorded postings across
139 distinct location strings, 10 location-bearing fields and all three providers.
**Nothing names a street.** All 58 NYC postings top out at a city name. Ashby's
structured `postalAddress` — the field this project had been saving for exactly this
moment — carries `addressLocality`/`addressRegion`/`addressCountry` and never
`streetAddress`, on any posting, from any employer.

Under I1 that settles something: **a job can never place itself on a building.** The
best a posting can honestly say about itself is `city_only`.

So a building has to come from the *company*, and `docs/architecture/city.md` §4.4
works through the four candidate sources. Scraping is out on policy (`CLAUDE.md` §8:
first-party public APIs only). OSM and Wikidata are free and open but of uneven
quality and unknown currency — good enough to propose, not to confirm. Which leaves
a curated file, `data/company-locations.yaml`, in the same shape as
`board-registry.yaml`: an address a human confirmed, geocoded through NYC GeoSearch,
where rung 1 of A4's ladder finally works because an office address is exactly what
GeoSearch resolves.

**The question is how far you want to take it, because the ceiling on lit buildings
is a number of addresses somebody types.**

- **The 23 registry boards** — perhaps 40 minutes, and it makes the demo real. The
  NYC subset is smaller still.
- **NYC employers only, as they appear** — curate on demand, when a company shows up
  in your queue. Slower to look impressive, closer to how you would actually use it.
- **Let OSM propose and you approve in bulk** — I build the proposal path, you click
  through a review screen. More engineering, less typing, ADR 0005's batch-approval
  shape which already exists for boards.
- **None, and ship the unresolved layer alone** — a city of floating signals over an
  unlit skyline. Honest, buildable, and genuinely striking, but the 3D city stops
  being about New York and becomes about a list that hovers.

My recommendation is the third with the first as its seed: type the handful of NYC
registry companies by hand so M4c has real buildings from day one, and build the OSM
proposal path so it scales without either of us guessing an address.

**Not blocking.** M4a builds the geocoder, the tables and the promotion path
regardless; those are the same code whether the file has 4 rows or 400. The answer
decides what the city looks like at M4c, not what gets written before it.

---

## Q6 — 43% of postings require no technology. What should a score out of 100 do about it?

**Raised:** 2026-08-09 (M3c Task 3) · **Type:** product · **Blocking:** no
**ANSWERED 2026-08-09: option 1 — score out of what could be assessed.**

A posting naming no technologies is scored out of 50, not out of 100, and the
page says which components could not be assessed and why. The ranked list sorts
on the fraction; the number shown carries its own denominator. Task 10 owns how
two numbers read on one screen.

**Implemented at Task 5** — `scoring.compose_score`, and `MatchScore.fraction`
returns `None` rather than a number when *nothing* could be assessed, because
0.0 sorts a pair last and 1.0 sorts it first and both are claims nobody made.
Implementing it surfaced one thing the answer implied and nobody had written
down: **the denominator has to reach the database**. A component that scored
zero and a component that could not be assessed both store `0`, so the fraction
cannot be recomputed on read — `match_results` needs an `assessed_out_of`
column, and it lands with Task 8's migration. Recorded in `matching.md` §5.1.2.

What this buys, restated so the reason survives the decision: a terse posting no
longer sorts below a verbose one for reasons about the employer's prose. What it
costs is that the headline number is no longer always out of 100, which is a
presentation problem rather than a measurement one.

**The measurement, on the committed answer key rather than on the extractor's
output:** 26 of the 60 labeled postings name **no required technology at all**,
and 16 of those name no technology of any kind. That is 43%, and it is a fact
about how employers write rather than about anything this system does — the
human labeled those postings by hand and there was nothing to label.

Skill overlap is worth 30 of 100 and project evidence another 20. Both read the
same required-technology list. So on 43% of the corpus, **half the available
score cannot be computed at all**, and the question is what the total does then.

Scoring those components zero is the option to reject, and §5.1 already rejected
its twin: application urgency was deferred because scoring an absent deadline as
zero "measures an employer's ATS configuration, not urgency". This is the same
shape with a bigger number. A terse posting would sort below a verbose one for
reasons having nothing to do with the person reading the list.

Awarding the points anyway is not available, and it is worth saying that the
database is what makes it unavailable: a positive component with no evidence row
cannot be committed. The guard built at Task 2 removed the tempting option
before anybody had to be disciplined about it.

That leaves a real choice, and it changes what the number on the screen means:

1. **Score out of what could be assessed.** A posting naming no technologies is
   scored out of 50, and the page says "50 points not assessable: this posting
   names no technologies". The ranked list sorts on the fraction. Honest, and it
   makes two numbers on one screen that a person has to reconcile.
2. **Score out of 100 always, with the unassessable components visibly empty.**
   Simpler to read, and it systematically ranks terse postings below verbose
   ones — which is the defect above, accepted deliberately and disclosed.
3. **Redistribute the weight** across the components that could be assessed, so
   every posting is scored out of 100. Comparable, and it silently changes what
   the weights mean per posting — a posting with no technologies would have
   location and freshness worth 50 points between them, which nobody chose.

I would take (1): it is the only one that does not quietly lie, and the
two-numbers problem is a presentation question rather than a measurement one.
But it is your product, the tradeoff is visible to a user, and Task 5 will
implement whichever you pick.

Task 3 does not need the answer. Each component already returns `assessable`
alongside its points, so the information exists either way and no rule has to
change — only the composition.

---

## Q5 — Twenty minutes of your judgement, or M3 ships with ranking quality unmeasured

**Raised:** 2026-08-09 (M3c planning) · **Type:** product · **Blocking:** no

**ANSWERED 2026-08-10. All thirty rated, profile filled, `ratings.yaml` complete.**
See "The second pass" at the end of this question for what changed and why the
first pass could not have been used.

`matching.md` §7.3 names this and M3c's plan brings it forward so it can be
scheduled rather than discovered at M3d.

**The problem, plainly.** M3 will be able to prove that the ranking is *stable* —
same inputs, same version, byte-identical output — and it will not be able to
prove the ranking is *good*. Those are different claims and only one of them is
what a person cares about.

The reason is not laziness. Whether a role is a **good** role for you is not a
property of the posting, so it cannot be read out of the 60-posting answer key by
construction. The key can say "this posting requires a bachelor's degree" because
that has a right answer. It cannot say "this posting is a 78 for Tahmudun".

**What would fix it:** you rate roughly 30 postings `good` / `acceptable` / `poor`.
No explanation needed, no tie-breaking, just the three buckets. Roughly twenty
minutes. That becomes the held-out set the ranking is measured against in M3d,
and it is the only thing in this project that can produce that measurement.

**What happens if it does not happen:** M3 ships with stability measured and
quality unmeasured, and PROGRESS says exactly that under "Not real yet" — rather
than reporting a number computed against labels the system wrote for itself,
which would be the most flattering and least honest option available.

**Not blocking.** M3c is twelve tasks and none of them needs this. It is wanted
before M3d starts.

### The worksheet exists — 2026-08-09

`docs/labeling/relevance-worksheet.md`, thirty postings, filled in at
`services/api/tests/fixtures/relevance/ratings.yaml`. Generated by
`scripts/make_relevance_worksheet.py` from the same 153-posting corpus M3a
labeled, so a rating and an eligibility label always describe the same job.

Two things about it that are not in the question above, both decided while
building it:

- **The file carries the profile the ratings were made against**, and the first
  two minutes go there. A rating without one is unusable: `poor` from a
  first-year student and `poor` from a staff engineer are different claims about
  the same posting. It also means M3d grades a pure function against a committed
  file rather than against whatever is in the database that day.
- **The thirty are stratified by role shape, not drawn evenly.** Twelve
  early-career technical, nine experienced technical, six clearly non-technical,
  three residual. The first draft round-robined by employer and produced four
  engineering roles and twenty-six accountants, receptionists and AML analysts —
  every one a `poor`, and a ranker that sorts them last is not thereby good.
  `test_the_set_spreads_across_employers_and_role_shapes` is that guard.

**One limit worth knowing before you spend the twenty minutes.** The nine
employers in that corpus are all quant trading firms or AI labs, because M3a
recorded them for eligibility-rule coverage rather than as a sample of New York
tech. So the resulting number measures the ranking over that slice, not over the
job market. It is still the only measurement available and it is worth having;
it is not worth over-claiming, and PROGRESS says so where the number will go.

### The second pass — answered 2026-08-10

Thirty ratings and a profile. **12 `good`, 11 `acceptable`, 7 `poor`.** The file
is complete, `test_a_filled_profile_uses_skill_names_the_matcher_can_resolve`
runs instead of skipping, and M3d has a held-out set to grade against.

**The first pass could not have been used, and the reason is worth keeping.** It
rated 27 of 30 `good`. That is the ranking-metric form of a gate answering
`uncertain` to everything: with one class holding nine tenths of the corpus,
every ordering scores about the same and the metric discriminates nothing. It
was not a careless pass — the rater was answering *would I take this*, which is
a real question and not the one the worksheet asks.

**What the second pass fixed was the control group, not the spread.** Broken out
by the role shape each posting was *selected* for:

| Bucket | good | acceptable | poor |
|---|---|---|---|
| technical, early career (12) | 6 | 5 | 1 |
| technical, experienced (9) | 5 | 2 | 2 |
| clearly non-technical (6) | 0 | 3 | 3 |
| residual (3) | 1 | 1 | 1 |

The six non-technical postings exist so that a ranker burying them proves
something. In the intermediate draft they came back 2 `good` / 3 `acceptable` /
1 `poor` — statistically indistinguishable from the early-career engineering
roles this product exists to surface, which would have meant a ranker putting
Jane Street's **Campus Recruiter** above Databricks' **Software Engineer 2027
Internship** scoring no worse than the correct order. Three rows moved on a
re-read (7 Account Executive → `acceptable`, 15 Campus Recruiter → `poor`,
21 Employee Experience Specialist → `poor`) and the bucket now separates.

**Three fields needed translating, and the translations are decisions.**

- **`degree: bachelors`** for somebody with no degree yet. The field is *highest
  degree held **or in progress*** (`eligibility.py:79`), so a fifth-year
  undergraduate is `bachelors` by definition rather than by charity.
- **`years_experience: 0`**, from *"no formal job experience, but four years of
  coding"*. The column counts professional years and the seniority penalty reads
  it directly (`matching.md` §5.1.3), so the coding years have no honest route
  into it — they are already carried by the 32 confirmed skills. `0` rather than
  blank is the load-bearing half: blank is I2's *never told us*, `0` is a stated
  fact, and §5.1.3 keeps them apart on purpose.
- **`preferred_roles`** gained `software engineer`. *"or developer or whatever"*
  was not added as a second entry, being the same role in different clothes.

**One thing the profile makes concrete.** The rater's confirmed skills include
**Data Structures, Machine Learning and Distributed Systems** — precisely the
three concept terms ADR 0018 measured as the scorer's one real recall gap, 33
occurrences across the corpus it sees nothing of. The `demonstrated_by:` edges
that ADR recommends now have a named person they would help rather than an
argument.

**The limit above is unchanged and still applies.** Nine employers, all quant
trading firms or AI labs. Whatever M3d reports is a measurement over that slice.

---

## Q2 — Deployment target for the M4 ship

**Raised:** 2026-07-29 (M0) · **Answered:** 2026-08-21 · **Type:** cost · **Blocking:** no

**ANSWERED 2026-08-21 — not yet, and the question has moved milestones.** The
human's words: *"the domain and email thing are future concerns i wanna make
sure things are polished before worrying about that."*

**The question outlived its own premise.** It was raised against A15, where M4
was the ship. **A16 moved the ship to M7**, so the deadline this question was
written to beat no longer exists, and "$0 until then" is the answer for every
milestone between here and there. `make demo` stays the only way to see
Nightshift, which is what A9's $0 target always intended.

**What still needs deciding, unchanged, when M7 arrives:** a monthly figure or
"local only". The four options below are still the options, and the PostGIS +
pgvector constraint is still the one that eliminates most free tiers. **Nothing
about the answer got easier by waiting** — but nothing got more expensive
either, which is what makes deferring it free.

A15 says M0–M4 is the portfolio project and M4 should be a real ship — deployed,
case study written, on the resume. That is the first point where this project can
cost money, so it is worth deciding before it arrives rather than under deadline.

The shape needed: one Next.js app, one Python service (API + worker in one
process), Postgres with PostGIS and pgvector, Redis.

The PostGIS + pgvector requirement is the constraint that matters — several
managed Postgres free tiers do not offer both. Rough options:

- **Fly.io** — one machine + a Postgres app, both extensions installable. Around
  $5–10/month at this size, scale-to-zero possible.
- **Railway / Render** — simpler, similar money, extension support needs checking
  per provider.
- **A single small VPS with docker compose** — cheapest and closest to the
  committed compose file, but you own the backups.
- **Local-only, demo by video** — $0, and A9's target is $0 for M0–M4. Loses the
  live link, which is a real part of what makes the project persuasive.

What I need: a monthly figure you are comfortable with, or "local only". I will
write the ADR with the number and the degradation behaviour either way.

**Not blocking:** nothing before M4 needs it, and `docs/architecture/costs.md`
tracks the answer when it exists.

---

## Q1 — Gmail OAuth client, and confirmation you accept the A8 constraint

**Raised:** 2026-07-29 (M0) · **Type:** credential + legal · **Blocking:** no, until M7

M7 needs a Google Cloud OAuth client that only you can create. Before then,
please confirm you accept what A8 establishes, because it is a real product
limitation and not a technical detail:

- `gmail.readonly` is a Google **restricted scope**. An unverified app is capped
  at a small number of test users and shows an unverified-app warning screen.
  Full verification requires a security assessment that is not realistic for this
  project.
- Therefore **public demo mode and Gmail are mutually exclusive.** The public
  demo uses synthetic classified-message fixtures only. Never a real inbox. If
  you want a shareable demo *and* Gmail on your own account, those are two
  deployments.
- Storage is minimal by design: message id, thread id, sender, subject,
  timestamp, classification, extracted dates, confidence, associations. **Never
  bodies.** A classifier that needs body text processes in memory and stores only
  its output.
- Disconnect must revoke the token *and* delete every derived row, with a test
  proving it.

Nothing to do now. Flagging at M0 so M7 does not end in a surprise.

---

## Answered

## Q4 — Should CI pin its Python dependencies?

**Raised:** 2026-08-05 (M3a.1) · **Answered:** 2026-08-05

> **Numbering correction.** This was raised as "Q3" and Q3 was already taken by
> the registry question below. Renumbered on answering rather than left to
> collide, since these are referred to by number from PROGRESS and the ADRs.

**Both. Pin the jobs that gate a merge; keep one unpinned job that gates
nothing.** The human's decision on 2026-08-05, taken on the recommendation in
the question. Full reasoning and what was rejected: **ADR 0016**.

What the question got right, and it is the part worth keeping: reproducibility
and early warning only conflict if there is one place to install. There are now
two.

- `ci.yml` installs from `services/api/constraints-ci.txt` — 72 distributions at
  exact versions, wired in through one workflow-level `PIP_CONSTRAINT` so all
  three install steps read the same file and cannot drift apart. The `python`
  job then diffs `pip freeze` against that file, so "CI is pinned" is checked
  rather than assumed — a dependency added to `pyproject.toml` and never
  regenerated would otherwise install unpinned with nothing saying so.
- `dependency-canary.yml` installs unpinned, weekly, and runs the checks a
  release can break — including the drift probe that started all this. It runs
  on `schedule` and `workflow_dispatch` only, so it cannot gate a merge. Every
  run writes a diff of unpinned-versus-pinned to the job summary, green or red.

**Who reads it**, which was the open half of the question: GitHub emails the
repository owner when a scheduled workflow fails on the default branch. No bot,
no auto-filed issue — one reader does not need a queue.

**What this gives up, stated plainly:** the alembic finding arrived for free the
day it shipped. The same finding would now arrive up to seven days later. That
is the price of an unrelated pull request never going red at a moment nobody
chose, and it is paid deliberately.

Two things generated the answer that were not in the question:

1. **The constraints file cannot be generated on the developer's machine.**
   `make constraints` resolves inside a `linux/amd64` container because the two
   platforms disagree about eleven distributions and one of them irreconcilably:
   onnxruntime resolves to 1.28.0 on linux and 1.23.2 is the newest release with
   a macOS x86_64 wheel. So **the pin covers CI and not a developer's machine**,
   which is a smaller version of the original problem left standing on purpose.
2. **The related gap is now closed.** `make drift` runs the drift probe against
   your own stack and is part of `make acceptance`. It is not in `make check`,
   which must keep working without a database.

## Q3 — Which boards go in the registry, and who vets them?

**Raised:** 2026-07-29 (M0) · **Answered:** 2026-07-30

**The question was wrong, and the answer changed the milestone.**

It asked how many companies to curate — 50, 100 — and assumed a hand-built list.
Asked directly, the human's goal turned out to be: *if any tech job or internship
opens in NYC, the system knows the day of, from any employer.* Curation cannot
reach that at any list length, so the registry stops being curated and becomes
the output of a discovery pipeline.

Answers to what was actually asked:

- **How many companies:** as many as can be discovered. **2,605** board tokens
  were available immediately from one Common Crawl index, measured 2026-07-30.
  Not a target — a floor.
- **Which companies:** not decided in advance at all. Whole boards are polled and
  NYC-ness is read off the postings, so no list needs to declare a city. This
  also means expanding beyond NYC costs nothing at ingestion.
- **Who vets them:** the human, in batches rather than per entry. Candidates
  whose employer name came from the provider are approved as a batch and
  committed from a git diff; unnameable and colliding ones are held for
  individual review. This departs from A1 and is recorded in **ADR 0005**.
- **How often it runs:** a command the human runs, not a schedule. New crawl data
  appears monthly. This only affects finding *new companies* — checking known
  boards for new jobs is hourly or daily and unaffected.

Scope decisions taken at the same time:

- **Employer breadth:** tech roles at *any* employer, not only at tech companies.
  Banks, hospitals, media and universities are in scope eventually — they are on
  Workday/iCIMS/Taleo, which is the milestone after this one and until then a
  stated blind spot.
- **LinkedIn and Indeed: no.** LinkedIn's robots.txt is a blanket `Disallow: /`
  for all agents with an address to email for permission; Indeed's public API is
  partner-only and its inventory is largely resold from the same ATS boards read
  here first-hand. `docs/architecture/board-discovery.md` §9.
- **Long-term ambition** — other cities, then every state, then every job type —
  is answered in §10 of the same document, including where it stops being
  honestly possible.

Full design: `docs/architecture/board-discovery.md`. Decisions: ADRs 0005, 0006,
0007.
