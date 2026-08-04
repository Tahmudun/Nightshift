# ADR 0013 — A resume produces proposals with spans, never facts

- **Status:** accepted
- **Date:** 2026-08-03
- **Milestone:** M2c
- **Overrides:** `PRODUCT-SPEC.md` §6.1's `graduation_date`; §6.4's `structured_profile`

## Context

Invariant I2 says the system never fabricates a user qualification. M2c is the
milestone that makes that hard, because reading a resume is exactly the act of
turning somebody's document into claims about them.

The usual shape — parse the file, fill the profile, let the user correct it —
fails I2 on the first request and keeps failing quietly. A field the parser got
wrong looks identical to a field the person typed. There is no column that
records which is which, so "correct it later" is advice nobody can act on:
you cannot correct what you cannot find.

Three decisions follow, and each one is structural rather than procedural. A
rule that lives in a code review is a rule that survives until a busy afternoon.

## Decision 1 — Two tables, one writer

Proposals live in `resume_extractions`. Confirmed facts live in `users`,
`user_skills` and `user_projects`. **`domain/profile.py` is the only module that
may write the second set**, and `tests/test_nothing_infers.py` asserts that at
the source level with three greps — a direct assignment, a constructor, and a
dynamic `setattr` that would defeat both.

The extractor cannot reach the confirmed tables at all. It does not import the
ORM, and a test asserts it never learns to. So **no bug in the extractor can
produce a confirmed fact** — not because the extractor is careful, but because
it has no path to those rows.

The alternative was one table with a `confirmed` boolean. Rejected: every read
of a skill would then have to remember the filter, and the one that forgets is
the one that surfaces a guess as a qualification. A boolean is a convention; two
tables are a schema.

## Decision 2 — Every proposal quotes the words it came from, and a trigger checks it

Every row in `resume_extractions` carries `char_start`, `char_end` and
`quoted_text`. Both bounds are `NOT NULL`, so **a proposal with no span is
unrepresentable**.

`quoted_text` is redundant with the span on purpose. A trigger
(`resume_extractions_span_must_quote`) compares the two against
`resumes.parsed_text` and refuses any row where they disagree. The highlight on
the confirmation screen and the claim in the row therefore cannot diverge.

**Why a trigger and not a check constraint.** A check constraint can only see
the row being written. The text it must quote lives in a different table, and
Postgres does not allow a subquery in a `CHECK` — the constraint would have to
be a lie by omission. A trigger can read the parent row, so it does.

**The 1-indexing detail.** The columns are 0-indexed, because they are consumed
by Python slicing and by JavaScript's `String.slice` — the two places that will
ever read them. SQL's `substring` is 1-indexed, so the trigger adds one. Getting
this backwards produces a system that is off by exactly one character
everywhere, which reads as a plausible highlight and is wrong every time.

The same promise is asserted at two more boundaries, because a trigger cannot
see a serialisation bug: `test_every_proposal_in_the_response_quotes_the_parsed_text`
checks it in the API response, and `resumeDetailSchema` checks it in the browser
before anything is rendered.

## Decision 3 — `graduation_year` + `graduation_month`, not `graduation_date`

PRODUCT-SPEC §6.1 specifies `graduation_date DATE`. A resume says **"Expected
graduation: May 2027"**. It does not say a day, and no resume ever will.

Storing that in a `DATE` column requires inventing one — the 1st, the 15th, the
31st. That is invariant I1's failure mode moved from geography to time: a
precision the source never provided, presented as if it had. It is the same
reasoning that moved location off `jobs` in AMENDMENTS A2.

So `users` has `graduation_year SMALLINT` and `graduation_month SMALLINT`, with
two check constraints: a month must be 1–12, and a month requires a year. M3's
internship-eligibility window needs a month and a year, which is exactly what a
resume actually says.

`resumes.structured_profile` from §6.4 is dropped for a related reason: the
proposals *are* the structure, and they carry spans. A second denormalised copy
could disagree with them, and nothing would notice which one was wrong.

## Consequences

**A person must click.** Reading a resume that proves sixteen things adds
nothing to a profile. That is the cost, and it is the feature.

**Deleting a resume does not un-confirm anything.** A skill somebody confirmed
belongs to them, not to the file it arrived in. `applications.selected_resume_id`
is `ON DELETE SET NULL` for the same reason.

**Proposals are made once per resume.** Re-proposing against a resume somebody
has already answered would strand those decisions, and "your confirmed skills
quietly reverted to pending" is not a behaviour worth having.

**Two new dependencies, both $0 (A9).** `pypdf` (BSD, pure Python, no native
libraries) reads PDFs; `python-multipart` (Apache 2.0, pure Python) is what
FastAPI needs to parse an upload at all. Neither reaches the network, so
`make demo` still works offline. No LLM anywhere in this path —
`command-center.md` §6.1 decided that, over both an LLM and a no-parsing form,
and reversing it would need an ADR naming the cost.

## Alternatives rejected

**An LLM extractor.** Better recall, and no span it cannot invent. A model that
returns "characters 214–229" for a claim it inferred from the whole document is
the exact failure this design exists to prevent, and the trigger would either
refuse every row or be relaxed until it refused none.

**No parsing at all — a form.** Honest, and the thing people abandon. The
confirmation screen is the compromise: the machine reads and the person decides,
which is the division of labour I2 actually asks for.

**Storing the uploaded bytes.** We need the text, not the file. Not storing it
is the smallest honest footprint for the most personal data in the project
(§13). The row keeps the filename, a hash of the *text*, and the text.
