# ADR 0039 — The page is read by the reader, not by us

- **Status:** accepted
- **Date:** 2026-08-22
- **Milestone:** M5d
- **Relates to:** `CLAUDE.md` §1 (I1, I2, I7), §8 ("Scraping anything that asks not to be scraped"); AMENDMENTS A16; ADR 0038; `docs/architecture/board-discovery.md` §9; `nightshift/domain/capture.py`, `nightshift/api/routes/capture.py`, `nightshift/mcp/`

## Context

M5d is *assisted capture from LinkedIn and Indeed*, and the first thing that
has to be settled is how it is legal at all.

`docs/architecture/board-discovery.md` §9 answered both sites in M1 and the
answer was **no**. LinkedIn's `robots.txt` ends `User-agent: *` / `Disallow: /`
with an address to email for permission; Indeed's public Publisher API is
partner-only and much of its site is disallowed. `CLAUDE.md` §8 forbids
scraping anything that asks not to be scraped, and neither of those is a close
call. §9 also priced the refusal honestly: an employer that posts only to
LinkedIn does not appear in this corpus, and that hole is listed rather than
hidden.

A16 then re-cut the milestones and put "reading LinkedIn/Indeed" back on the
map — not by reversing §9, but by changing **who does the reading**:

> assisted capture from LinkedIn and Indeed rides on that server:
> **user-initiated and session-bound, never a poller.**

The distinction is real and it is the whole architecture of this milestone. A
person opening a job posting in their own browser is that site's ordinary
audience. Their own Claude, reading the page they are already looking at,
inside their own session, at their explicit request, is not a crawler: it
visits one page, because they asked, once. Nightshift receives *text*.

## §1 — Decision: Nightshift's server never dereferences a captured URL

`captured_postings.source_url` is stored, displayed, and passed through to
`jobs.canonical_url` as the place a person can go back to. **Nothing in this
codebase requests it.** No route, no worker, no ARQ task, no schedule, no
freshness check, no closure check.

That was already true and it was held up by a comment on the column —
*"Never fetched — see the class note."* M5d is the milestone where a reader
starts handing this server job-board URLs by the dozen, so the comment becomes
`tests/test_capture_never_fetches.py`: two guards, each shown able to fail.

- **The transport guard** unplugs httpx's real transports and drives paste →
  read → confirm, asserting all three succeed and nothing was requested.
  Confirmation is included because it is the step that runs the whole ingestion
  pipeline on a row whose `canonical_url` is a LinkedIn link — the plausible
  place for a fetch to appear later.
- **The source guard** parses the capture modules and asserts no string literal
  outside a docstring is a job-board **address**. That is the half a transport
  patch cannot see: a URL sitting in a constant, written before anything uses
  it.

The source guard says *address* rather than *host* because it fired on real
code and was wrong to. Its first version flagged any literal containing a board
host; §5's `capture_origin` then had to **recognise** one — a table of
registrable domains, used to label a capture *From LinkedIn* — and the guard
went red on it. Recognising a host is the opposite of fetching one, and a guard
that cannot tell them apart forbids the honest use along with the dangerous
one, which puts the pressure on weakening the guard rather than fixing the
code.

So the rule is about shape. A bare registrable domain is a name; anything
carrying a scheme, an authority prefix or a path is an address.
`"linkedin.com"` passes, `"https://www.linkedin.com"` and
`"www.linkedin.com/jobs/view/1"` do not. **The narrowing is not free** —
`BASE = "linkedin.com"` followed by `httpx.get("https://" + BASE)` now slips
past this guard, and the transport guard is what catches it at runtime. That is
why there are two of them with their limits written down, rather than one that
claims to cover everything. The rule is tested apart from the modules it is
applied to, because narrowing a guard is the moment it most easily stops
guarding anything, and "it still passes on the current code" is not evidence
either way — the current code is what made it narrow.

Both were sabotaged before being committed. A `httpx.get(source_url)` in
`create_capture` produces `AssertionError: the capture path reached the
network: https://www.linkedin.com/jobs/view/4012345678/`; a
`BOARD_BASE = "https://www.linkedin.com"` constant produces `domain/capture.py
holds a job-board host in a string literal`. Neither guard was believed until
it had failed. That is this project's rule since `m5c-claude-desktop` found an
import guard that had been passing on an empty module graph for a whole
milestone.

### The alternative that was rejected

**Fetch `source_url` server-side and parse the page properly.** It is the
obvious engineering answer and it would produce a far better capture than
reading pasted text: real markup, `JobPosting` JSON-LD on many pages, a
canonical employer name instead of a guess.

Rejected because the sites said no. Not because a fetch would be detected,
not because it would be rate-limited, and not because it is hard — because
`Disallow: /` is a request and `CLAUDE.md` §8 is a commitment to honour it.
The cost of the refusal is a worse parse, and M5d pays it by asking the party
who is *allowed* to read the page to do the reading.

**A browser extension of our own** was rejected for the same reason with an
extra one: it would put Nightshift back inside `robots.txt`'s jurisdiction
while also being a second client to maintain, when the reader's Claude already
has a browser.

## §2 — Decision: an assistant may point, not paraphrase

§1 forbids this server loading the page, which leaves the reader's own Claude
as the only party that has seen the posting rendered. It is a far better reader
than `domain/capture.py`'s line parser, which guesses the employer from
position and — as the M5c desktop walk demonstrated on a run-on sentence —
declines every field when handed prose.

So the assistant may propose. It gets no more authority than the parser, and
one new failure mode:

    the parser can misread the text
    the assistant can produce a company that was never in the text at all

A misread is bounded by what was pasted. An invention is not, and in a review
form the two are indistinguishable — both arrive as a pre-filled field beside a
label. `domain/capture.py`'s own docstring already priced this: *a blank field
costs a person four seconds of typing; a wrong field costs them a building.*

**The rule: a field the assistant proposes must appear, verbatim, in
`raw_text`.** Whitespace-collapsed and case-insensitive; nothing else is
forgiven. A value that fails is not stored, and the model is told which field
and why.

It is the guarantee `resume_extractions` gets from its span trigger — no
accepted fact that is not literally in the document — reached with a substring
test rather than a trigger, because a capture is one short form reviewed
against text the person pasted seconds ago, not dozens of facts accepted
individually.

The rule is strict enough to refuse correct answers. "NYC" for "New York, NY"
is right and is refused. That is the point: a gate with an exception for values
that look right is the model's judgement again, wearing a check's clothes. What
strictness buys is that a reader looking at an assistant-proposed field can
find it in the text below the form, every time, with no exceptions to remember.

**What it does not claim.** Quotability is not correctness. "Ramp" appearing in
the text does not make Ramp the employer, and a posting naming a customer will
let that customer through. The confirmation step is still what makes a company
real. This narrows the failure from *anything the model can say* to *something
on the page*, and that is all.

### Stored apart, not merged

`assistant_title`, `assistant_company_name` and `assistant_location_text` are
their own columns beside `proposed_*` rather than a better value written into
them. Merging would erase which reader said what at exactly the moment a person
is deciding whether to believe it, and would make "how good are the quotes"
unanswerable forever. Where the two disagree, the review surface shows both and
pre-fills neither (§5 of the M5d plan).

`assistant_rejected_fields` holds **field names only, never values**. Storing
the refused value would put a possibly-invented company name in this database,
which is the thing the rule exists to keep out of it. The names are kept
because they are the only measurement there will ever be of whether the gate is
set too tight — and if the M5d walk shows it refusing most fields, that
measurement is what the correction will be argued from.

### The alternatives that were rejected

**Let the assistant's values into `proposed_*` directly.** Simpler, one set of
columns, and the review form would not need to change at all. Rejected because
it makes the two proposers indistinguishable in the one record a person reads
before agreeing to it.

**Accept the assistant's value unconditionally and rely on the confirm step.**
The confirm step is real and it is not sufficient: a pre-filled field is a
default, and a default is what a tired person accepts at 11pm. The gate exists
so that accepting the default cannot introduce a fact that was not on the page.

**Score the assistant's value by similarity to the text instead of requiring an
exact quote.** It would accept "NYC" and it would need a threshold, and a
threshold is a number nobody can defend at the moment it lets something wrong
through. Substring is explainable to a reader in one sentence.

### A prediction from M5a, corrected here

M5a wrote, in `apps/web/src/lib/schemas.ts`, that assisted capture would be *a
new source name of this same type*. It is not. A posting captured through
Claude and the same posting pasted into the web form came from the same place —
a person who found it — and `capture_source_job_id` is content-derived
precisely so two people capturing one opening land on one job. Two source names
would give each channel its own `source_job_records` row for identical text and
hand the difference to the dedupe layer to undo. The channel is not a source.

**Which client relayed a capture is deliberately not stored.** It is derivable
only when the assistant quoted something, and nothing needs it: what a reader
cares about is where the *posting* came from, which comes from `source_url`.
Recorded here as a decision rather than left as an omission, so a later
milestone that needs it knows nobody forgot.


## §3 — Decision: one posting, one thing to review

`POST /capture` created a row per call. M5c's own test argued that was right —
*two captures of one posting are two records of a person pasting, which is
honest* — and checked only that they do not become two jobs.

That is right about the corpus and wrong about the queue. **A review queue is a
to-do list, and two identical to-do items is a defect in one.** M5d is also the
milestone that makes it common rather than theoretical: a model unsure whether
its last tool call landed will call again, and that is reasonable behaviour on
its part.

So `capture_paste` is idempotent over one person's *pending* rows, keyed on
`text_fingerprint` — sha256 of the whitespace-collapsed, casefolded text,
because re-copying a page rarely produces byte-identical text and a trailing
newline is not a second posting. A repeat returns the existing proposal
untouched, with `already_existed: true`, HTTP 200 rather than 201, and a
sentence telling the model to say it is already in the queue rather than
reporting a second capture.

**Three boundaries, each of which is a decision.**

*It is scoped to a person.* A shared proposal id would hand one reader a row
belonging to another and let them confirm or discard it — M5b's isolation,
broken by a deduplication shortcut. The index carries `user_id` first for that
reason and not for speed.

*It stops at a decision.* A confirmed or discarded row is a record of what
somebody decided; folding a fresh paste into it would rewrite that record and
leave a deliberate re-capture with nothing to review. §4's corpus check is what
tells the reader the re-capture is redundant.

*The existing row is returned unmodified.* Not updated with the new call's
`source_url` or assistant quotes. The stored row is what the reader is about to
look at, and quietly editing it under them while telling them it already
existed is two contradictory statements in one response.

**This is not `capture_source_job_id`.** That is the identity of a *job*,
content-derived across all users so two people capturing one opening land on
one row in the corpus. This is the identity of a *paste* and is only ever
looked up beside a `user_id`. Both exist, they answer different questions, and
the module says so where each is defined.

### The queue this argument is about, which did not exist when it was written

Every sentence above reasons from "a review queue is a to-do list", and the
to-do list had no screen. `/operate/capture` rendered a paste box and the
proposal the current browser tab had just created; a capture made through the
MCP server — the ordinary case this milestone was built for — had a row, a
`pending` status, and nowhere to be looked at. `capture_proposal` handed the
reader `review_url` and said *"the reader confirms or discards it at
`review_url`"*, which was an instruction that could not be followed.

`GET /capture?status=pending` had existed since M5a and `fetchCaptures` was
written against it in the web client, unused. **A route with no caller and a
tool description promising a screen is how a gap this size stays invisible**:
the API was complete, the tests were green, and the flow was broken at the one
seam nothing tested end to end.

So the list exists (`components/CaptureQueue.tsx`), and two consequences follow
that are decisions rather than layout:

*`GET /capture/{id}` runs §4's corpus check.* A capture made through the server
is read for the first time by that route — the person deciding never saw the
paste response, because it went to their Claude. Without this, §4 protected
only whoever typed the text into the browser. It is computed per response and
still never stored, for the reason the field's own docstring gives.

*The form has a third exit.* Confirm and discard were the only ways out, which
made *"I am not sure"* cost the same as *"no"*. **Decide later** leaves the row
pending. The proposal is stored the moment it is read, so this loses nothing —
and an unsure person pressed for a decision is exactly who accepts a wrong
employer, which is I1 broken by a UI affordance.

### The alternative that was rejected

**A unique constraint on `(user_id, text_fingerprint)` instead of a lookup.**
It would enforce the rule in the schema, which is this project's usual
preference. Rejected because the rule is *pending* rows only — a partial unique
index would work, and then a second paste is an `IntegrityError` the route has
to catch and turn back into the existing row, which is the lookup again with a
worse error path. The lookup runs inside the same transaction that would do the
insert, so the race window is the transaction's, and the cost of losing that
race is one duplicate row in one person's queue.


## §4 — Decision: the capture says what the corpus already holds

Nightshift polls thousands of board tokens first-hand. Most NYC tech postings a
reader finds on LinkedIn are **already in the corpus** — with a match score, a
location the system trusts, and the employer's own board as the source.

Capturing one of those is worse than useless. It costs a review, and it
produces a thinner second record of a job already held: a capture has no
freshness signal, no closure signal, and a location parsed out of free text.

So `POST /capture` answers with `corpus_check`, and the tool description tells
the model to **lead with it**. If the corpus holds the job, the useful reply is
not *"captured"* — it is *"you already have this, here it is, and it closed on
Tuesday."*

**Two rules, both deterministic, both naming themselves in the result.**

- `same_company_and_title` — the normalised employer and the normalised title
  both match. Normalisation is the ingestion pipeline's own
  (`normalize_company_name`, `normalize_title`) rather than a private reading,
  so this check and the corpus agree by construction. A second normaliser would
  drift, and the symptom would be a duplicate warning that quietly stopped
  firing.
- `same_url` — a source record points at the same page, compared through
  `dedupe.normalize_url` so a tracking parameter does not make one posting two.
  Narrow, because a LinkedIn URL will never equal a Greenhouse one, and worth
  keeping because it is the only rule that works when the text could not be
  read at all — exactly when the other rule is unavailable.

**Closed jobs are returned, not filtered out.** Somebody capturing a role
Nightshift already knows has closed is about to spend an evening on it, and
hiding closed matches to keep the warning tidy would withhold the single most
useful thing this check can say.

### Not knowing is an answer, and it is not an empty list

`checked: false` with an empty `matches` is a **different statement** from
`checked: true` with an empty `matches`. The first means nothing could be read
from the paste to search with; the second means Nightshift looked and found
nothing.

Collapsing them is invariant I3's failure — silence presented as evidence —
moved from source outages to duplicate detection. The result carries a
`why_not` sentence, the MCP shape turns it into an instruction (*"do not tell
the reader this posting is new to Nightshift — nobody looked"*), and
`test_capture_matches.py` asserts both halves.

### The assistant's quote outranks the parser here, and only here

The search runs on `assistant_company_name or proposed_company_name`. That
inverts §2's usual footing, and it is safe **because it steers a search rather
than a stored fact**: a wrong company finds nothing, and finding nothing is
what an unassisted capture would have done anyway. Nothing that comes back is
written to the capture row.

### The alternatives that were rejected

**Use `dedupe.compare`.** It is the system's real merge comparator and it does
not fit. Its layers block on company, employment type, title *and* location
before similarity is reachable, and a pasted posting honestly has none of the
last three. Feeding it invented values to get an answer is precisely the
failure this milestone exists to avoid.

**Embedding similarity against the corpus.** More recall, and it needs a
threshold. A threshold is a number nobody can defend at the moment it wrongly
tells a reader they already have a job they do not — and unlike a merge, this
warning is read by a person deciding whether to bother. `same_company_and_title`
can be explained in one sentence, which is what a warning needs to be.

**Refuse the capture when a duplicate is found.** Tempting and wrong. The
corpus copy might be a different opening with the same title, the reader might
want their own record, and I5 says suggest and surface rather than decide. The
proposal is created; what changes is what the reader is told.

**Store the check on the capture row.** It is a fact about the corpus *now*,
not a property of the row. Cached, it would go stale against the very jobs it
is about — so it is computed on the response to `POST /capture` and absent when
a stored capture is read back.


## Consequences

- The parse quality of a captured posting is bounded by what the reader's
  Claude hands over. §2 is about making that hand-off trustworthy rather than
  making it richer.
- Nothing in M5d can be re-read. A captured posting still has no freshness or
  closure signal (I3 already says silence is not evidence of closure; for a
  capture, silence is all there is).
- The guard is narrow on purpose. It covers the capture request path, not the
  whole package — the Greenhouse adapter fetches boards deliberately and a
  guard that scanned everything would be asserting about the wrong module.
  Adding a module to the capture path means adding it to `CAPTURE_PATH_MODULES`,
  and the test file says so.
