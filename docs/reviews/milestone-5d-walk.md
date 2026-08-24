# M5d — the walk, against a real LinkedIn posting

Task 6.2 of `docs/plans/2026-08-22-m5d-assisted-capture.md`: **a capture made in
Claude Desktop, from a real LinkedIn job page the reader was actually looking
at.** Not a fixture. The M5c walk found four defects a green suite could not;
this is the same instrument pointed at new code.

Walked 2026-08-24 by the human, on `m5d-assisted-capture`.

**The posting.** Notion — *Software Engineer Intern (Summer 2027)* — New York,
NY, hybrid, internship. A live LinkedIn page, copied out of the browser and
handed to Claude Desktop in the reader's own session. Nightshift never loaded
it; ADR 0039 §1 holds by construction and its two guards were already green.

---

## 0. Two things blocked the walk before it began, and neither was in the code

Recorded because both cost a session and neither is visible from the repository.

**The machine's disk filled to zero bytes**, which killed Docker's VM
mid-write — it could not log its own crash. Restarting Docker Desktop the
ordinary way did not fix it: one `com.docker.backend` process left over from
the crash **ignores `SIGTERM`**, and while it lives a relaunched Docker attaches
to the dead instance instead of building a new VM. Seven minutes of polling, no
daemon, and `com.docker.virtualization.log` silent throughout — which is the
tell. `docs/runbooks/docker-will-not-start.md`.

**Both MCP tokens were dead**, destroyed by a `make reset-db` this branch had
already documented. The failure is silent by construction: Claude Desktop
launches, the server starts, the handshake succeeds, and every tool answers
*"Nightshift rejected this token."* **The reader was being asked to walk across
a bridge that had been removed** — the previous session left the task standing
without noticing the connector under it was gone. Re-minted and verified against
`/auth/me`, with a dead token as the contrast.

**The lesson is about instructions, not infrastructure.** An ask left standing
while its prerequisite silently broke is indistinguishable, to the person
receiving it, from an ask they are failing to understand.

---

## 1. What the assistant quoted, and what the parser read

The capture reached the database with both readings preserved side by side,
which is ADR 0039 §2's whole shape. Read back from `GET /capture/{id}`:

| Field | Nightshift's parser | Claude's quote |
|---|---|---|
| Title | `Company logo for, Notion.` | `Software Engineer Intern (Summer 2027)` |
| Employer | `Notion` | `Notion` |
| Location | `New York, NY` | `New York, NY` |

`assistant_rejected_fields` was **empty**. All three quotes appeared verbatim in
the pasted text, so the substring gate passed every one.

**The parser read LinkedIn's image alt-text as the job title.** The pasted text
begins `Company logo for, Notion.` on its own line, and the title line is
fourth. This is not a defect in the parser so much as the shape of a LinkedIn
copy-paste, and it is the clearest argument the milestone has produced for §2
existing at all: **the assistant was right where the deterministic reader was
wrong, and it was still only allowed to point.** A paraphrase would have been
equally right here and the rule would still be correct to refuse it.

**The corpus check ran and answered.** `{"checked": true, "why_not": null,
"matches": []}` — Nightshift looked and held nothing matching. §4's rule that
*"not checked" is never an empty list* is satisfied on the branch where it is
easiest to get wrong.

---

## 2. The defect this walk found: a capture from LinkedIn that cannot say it came from LinkedIn

`origin` came back **`none`**.

The queue row is specified to name where a posting was found, and
`capture_origin` derives that from `source_url`. Claude Desktop called
`capture_posting` **without a `source_url`** — the column holds `''` — so the
one channel this entire milestone exists to serve produced a row whose origin is
unknown.

Nothing is broken in the sense of throwing. `capture_origin('')` correctly
declines to guess, which is I1's temperament applied to provenance and is the
right behaviour for the function. The gap is upstream: **nothing in the tool's
contract makes the URL feel required**, and the reader in Claude Desktop has no
reason to know that omitting it costs the badge.

This is the same failure class the branch keeps producing, one layer out: a
field that is optional in the schema and load-bearing in the interface.

**Raised as Q13 and answered the same day: ask for the URL, and say so when it
is absent.** Inference was rejected — pattern-matching a provenance claim out
of body text invents a fact about where a posting came from, which is the thing
`location_confidence` exists to refuse. `capture_posting`'s description never
mentioned `source_url` at all, which is the whole reason the walk's capture
carried none; it now asks for it. And `originLabel()` replaces the bare lookup,
because **the distinction the interface can honestly draw is not which website
but whether an assistant took part** — recorded fact, in the quote columns. The
walk's own capture now reads *"Origin not recorded"* where it read *"Pasted
text"*, and a browser paste still reads *"Pasted text"*.
`docs/reviews/milestone-5d-origin.png`.

---

## 3. The confirmation failed, and the reason was not in this branch

Pressing save returned:

```
/capture/9f97104b-8c73-4e92-a28d-deb8735f5ea5/confirm failed: Internal Server Error
```

`apps/web/src/lib/api.ts:132` produces that string from a real FastAPI 500, so
it was an unhandled exception rather than a network fault.

**It was not the capture path.** `confirm_capture` was driven directly against
the reader's own row, in a transaction that was rolled back, and it succeeded —
job created, dedupe run, embedding loaded. The API process serving the browser
had been running for **22 hours, straight through the Docker outage**, holding a
connection pool pointed at a Postgres that had been killed and restarted
underneath it. Reads that drew a fresh connection worked, which is why the
review screen rendered; the confirm was the first request that needed a write.

Proved rather than assumed: the identical posting text was pasted under the
second seeded account and confirmed through the real HTTP endpoint on a
restarted API — **HTTP 200 in 2.2 seconds** — and every row that probe created
was then deleted, returning the corpus to 32 jobs and 4 companies. The reader
retried and it succeeded.

**One thing is stated rather than proved:** the old process was killed before
its logs were captured, so the stale pool is the explanation the evidence best
supports, not one that was demonstrated. What was demonstrated is that the code
path is sound.

**What is worth changing is the error surface, not the pool.** A reader who has
just been told to check every field and press save is handed
`Internal Server Error` and no next step. The two-step design spends real effort
making the *decision* legible and then reports its failure in the least legible
way available.

---

## 4. A defect that was predicted, measured, and turned out not to exist

The confirmed title reached the corpus as `SOFTWARE ENGINEER INTERN (SUMMER
2027)`. The posting reads *Software Engineer Intern (Summer 2027)*.

The screen was the obvious suspect. The four review fields sit **inside**
`<label>` elements carrying `LABEL_CLASS` — `uppercase tracking-[0.14em]` — and
the paste form's two inputs override that with `normal-case` while the review
form's four do not. That asymmetry reads exactly like a leak that was fixed in
one place and missed in another.

**Measured in a real browser, it is not one.** `text-transform` computes to
`none` on all four fields. The reading of the cascade predicted a defect; the
measurement refuted it. The shouted title came from what was typed into the box,
not from what the box did to it.

The guard was kept anyway — `apps/web/e2e-seeded/capture.spec.ts`, *"the review
form shows the reader the text it will actually save"* — because the property is
real and nothing else covers it: **a confirmation screen that displays anything
other than what it will save defeats its own purpose**, and `toHaveValue(...)`
is blind to the cascade. Shown able to fail by adding `uppercase` to
`FIELD_CLASS`: *"the Title field renders as uppercase, not as the posting
reads."*

**The residue is a data question, not a code one.** The corpus now holds a job
whose title is louder than the employer's. Nothing in the flow warned that the
approved value differed in case from the text sitting directly beneath it, and
nothing offers to edit a confirmed capture afterwards.

---

## 5. What held

- **I5 held.** Claude captured and stopped. There is no confirm tool and its
  absence is what forced the decision back to a person and a screen.
- **ADR 0039 §2 held**, and earned its keep on the field where the parser was
  wrong.
- **ADR 0039 §4 held.** The corpus check ran on `GET /capture/{id}`, which is
  the path that matters here — the reader never saw the paste response, because
  it went to their Claude.
- **ADR 0039 §1 held by construction**, unexercised by this walk and already
  covered by two guards shown able to fail.
- **The queue did its job.** A proposal created in Claude Desktop appeared on a
  screen the browser had never created it from, which is precisely the defect
  closed on 2026-08-23.
- **The pipeline ran end to end.** `employment_type` `internship`,
  `remote_policy` `on_site`, `status` `open`, one `job_locations` row, corpus
  32 → 33 jobs.

## 6. What is owed

1. **The conversational half of this walk is not recorded here.** Task 6.2 asks
   whether the model **led with the corpus check** and whether it **described
   the capture as a proposal**. Both are properties of the conversation, and
   this document is written from the database — the transcript was not captured
   at the time. Those two answers are outstanding and the acceptance claim is
   incomplete without them.
2. **The 500's error surface** (§3) — a bare `Internal Server Error` on the
   confirm step deserves better than the generic client string.
3. **The title in the corpus** (§4) is the reader's to correct or keep. It was
   destroyed by `make check`'s `TRUNCATE` before either could happen (Q8's
   third bill), and the capture was restored as a **pending** proposal rather
   than a confirmed one, so the decision is still the reader's to make.
