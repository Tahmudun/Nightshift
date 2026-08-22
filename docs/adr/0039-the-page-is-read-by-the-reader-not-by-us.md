# ADR 0039 — The page is read by the reader, not by us

- **Status:** accepted (§1, §2); §3–§4 pending, added as M5d builds them
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
  outside a docstring names a job-board host. That is the half a transport
  patch cannot see: a URL sitting in a constant, written before anything uses
  it.

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
