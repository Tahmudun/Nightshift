# ADR 0039 — The page is read by the reader, not by us

- **Status:** accepted (§1); §2–§4 pending, added as M5d builds them
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
