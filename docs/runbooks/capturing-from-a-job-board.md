# Capturing a posting you found somewhere else

**What this is for.** You are looking at a job on LinkedIn, Indeed, a
newsletter, or a friend's message. Nightshift does not ingest those. This is
how the posting gets into your review queue, and eventually onto the map.

**Nightshift never loads the page.** Not the LinkedIn one, not the Indeed one,
not the URL you paste. Those sites say `Disallow: /` and Nightshift honours it
(`CLAUDE.md` §8, `board-discovery.md` §9, ADR 0039 §1). What reaches this
database is text **you** are already looking at, handed over by you or by your
own Claude in your own session. If that distinction ever stops being true, a
test fails: `tests/test_capture_never_fetches.py`.

---

## Before anything: check whether Nightshift already has it

It very often does. Nightshift polls thousands of company boards first-hand,
and a copy that came from the employer's own board is strictly better than a
capture — it carries a location the system trusts, a match score, and a source
that can be re-read later to notice the role closed.

**You do not have to do this by hand.** Both paths below check for you and say
what they found. What matters is knowing what the answer means:

| What you see | What it means |
|---|---|
| A job is named | Nightshift already has it. Open that one; the capture would be the thinner record |
| Nothing named, and nothing said | Nightshift looked and found nothing. Go ahead |
| "Nightshift has not checked…" | **Nobody looked.** Nothing could be read from the text to search with. That is not the same as no duplicates |

---

## Path A — through the web form

1. Go to **Operate → Capture** (`/operate/capture`).
2. Paste the posting text. Include the header: the title line, the employer
   line, the location. That is where the parser reads from.
3. Optionally paste the link. It is stored so you can go back to it and it is
   never fetched.
4. Press **Read it**.
5. Check every field against the text below the form. **The employer is the
   one that matters most** — it is what a job inherits an office from, and an
   office is what stands a beacon on a specific building. A field left blank
   is the parser declining rather than failing; type it in.
6. **This is right — save it**, or **Throw it away**.

## Path B — through your own Claude

Requires the connector: `docs/runbooks/connecting-claude-desktop.md`.

1. Have the posting open, or its text to hand.
2. Ask Claude to capture it. Anything like *"save this to Nightshift"* works;
   it will call `capture_posting`.
3. Claude may quote the title, employer and location it read off the page.
   **Those are quotes, not readings** — Nightshift checks each one appears in
   the text you handed over and refuses any that does not (ADR 0039 §2). A
   refusal is the check working. Claude will tell you which field it was.
4. Claude cannot confirm it. There is no tool for that and its absence is
   deliberate. Open `/operate/capture` and decide.
5. In the review form, each pre-filled field says who proposed it — *read by
   Nightshift* or *quoted by Claude*. Where the two disagreed, the field is
   **blank on purpose** and both readings are shown. Pick one.

---

## Two things that will confuse you if nobody says them

**Pasting the same posting twice does not make two proposals.** The second
paste returns the first one, and says so. This only holds while it is still
pending — once you have confirmed or discarded it, a fresh paste is a fresh
proposal, because you presumably meant it.

**The token's account and the browser's account are independent, and nothing
reconciles them.** If your Claude connector is on one account and you are
signed into the website as another, every capture lands in a review queue you
are not looking at — and an empty queue looks exactly like an empty queue. Ask
Claude *"which account are you connected to"* (it calls `whoami`) and check it
matches the address in the top-right of the website. This bit a walk-through on
2026-08-21; see `docs/reviews/milestone-5c-desktop-walk.md` finding 5.

---

## When it goes wrong

**"Claude says it captured it and my queue is empty."** Account mismatch. See
above.

**Every field came back blank.** The parser reads lines and the text was
probably one run-on paragraph. Re-copy it with its layout intact, or type the
two fields in — the form is right there.

**Claude quoted a company that is not on the page.** It was refused and nothing
was stored. That is the whole design; the review form says which field, and you
can type the right value.

**The posting is on the map but floating rather than on a building.** Expected.
A capture's text tops out at a city name, and Nightshift will not invent a
street address (invariant I1). It stands on a building only once its employer
has a confirmed office.
