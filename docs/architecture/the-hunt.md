# The Hunt — the M6 design

> Read before any M6 work. It decides why the roadmap was re-cut around one
> reader, which of the four obstacles is real and which was assumed, and what
> "usable" is allowed to mean before the word may be written in PROGRESS.
>
> Governing decisions: **A17** (the re-cut; the Archipelago becomes M7), **I1**,
> **I2**, **I3**, **I5**, **I7**.
>
> Supersedes nothing in `archipelago.md`. That design stands and is deferred;
> §5.4 cherry-picks one column out of it and says why.

---

## 1. What changed

The human's instruction, 2026-08-25, verbatim in substance: *forget deployment
for a while; the main purpose is usability for me, as soon as possible — not a
demo, an actual version I use to find and apply to internships.*

That is a change of goal, not of scope. Every milestone so far has been built
to a specification. This one is built to a person, and it is measured by
whether that person opens it in the morning.

**It also arrives at the worst possible moment to be late.** It is late August
2026. Summer 2027 internship postings open now through roughly October. A tool
that becomes usable in November has missed the season it was built for, and no
amount of correctness recovers that.

### 1.1 The re-cut

| Was | Becomes |
|---|---|
| M6 — The Archipelago | **M6 — The Hunt** |
| M7 — Smooth (the ship) | M8 |
| M8–M13 | M9–M14 |
| — | M7 — The Archipelago (unchanged in content) |

Recorded as **A17**. `CLAUDE.md` §6 is updated to match. Deployment, which was
M8's first public deploy, moves with its milestone and is explicitly not
pursued in M6: the reader runs this on the machine it is written on.

---

## 2. The corpus, measured against the actual goal

Measured 2026-08-25 against the live development database. The M6 numbers
differ from `archipelago.md` §2 not because the data changed but because the
question did. That document asked *where are the roles.* This one asks *how
many could this reader apply to.*

| | |
|---|---:|
| Jobs | 1,200 |
| Companies | 23 |
| Open jobs | 1,200 |
| **Early-career (`internship`, `new_grad`, `junior`)** | **12** |
| — of those, `internship` | 8 |
| — of those, open and in New York | 4 |

**The twelve, in full**, because a number this small should be read rather than
summarised:

```
internship | 1X           | CNC Machine Park Internship
internship | 1X           | Internship - Manufacturing Engineering (Fall)
internship | 42dot        | [MS/PhD Intern] AI Engineer (정규직 전환형)
internship | Datadog      | Product Management Intern
internship | Datadog      | Software Engineering Intern (Winter)
internship | Jump Trading | Campus AI Research Engineer (Intern)
internship | Ramp         | Software Engineer Internship, Android
internship | a16z Media   | Research Intern
junior     | 0g Labs      | Junior Controller
new_grad   | Abound       | Graduate AI Engineer
new_grad   | Abound       | Graduate Software Engineer
new_grad   | Abound       | Graduate Data Scientist
```

Two are machining. One is in Korean, in Korea. One is accounting. **Three or
four are roles this reader would plausibly apply to, and that is the whole
product as it stands today.**

### 2.1 The classifier was suspected and is innocent

The obvious hypothesis is that internships are present and mis-labelled: 552
open jobs carry `seniority: unclear`, and if even 5% of those were internships
the corpus would look very different.

Measured rather than assumed. Of the 552, **six** have a title matching
`intern|co-?op|new grad|university|campus|student`. All six are false
positives of the pattern:

```
Manager, Internal Product Analytics        Financial Partnerships Manager, International
Software Engineer, International           Marketing Media Strategist, International (Contract)
Product Manager | International            Internal Controls Manager, Accounting Team
```

**Zero internships are hiding in the unclear bucket.** `role_classification.py`
caught every internship in the corpus. M3's scoring decomposes correctly, M2's
tracker works, M5's capture works. *Nothing downstream of ingestion is the
problem.* The corpus contains three usable roles because 23 boards contain
three usable roles.

This measurement removed a task from §5 before it was written, which is the
argument for taking it.

---

## 3. What already exists and is not rebuilt

Stated so that M6 is not tempted to re-do it. All of this is built, tested and
working against fixture data:

| Capability | Where | Milestone |
|---|---|---|
| Search, filters, saved jobs | `routes/jobs.py`, `JobFilters.tsx` | M2 |
| Application tracking, append-only events, stage history, notes | `routes/applications.py` | M2 |
| Daily queue | `domain/queue.py`, `routes/queue.py` | M2 |
| Resume upload (PDF/txt/paste) → parse → **confirm** | `resume_text.py`, `resume_extraction.py` | M2 |
| Explainable scoring, evidence rows, eligibility gate | `domain/scoring.py`, `matching.py` | M3 |
| Real accounts, sessions, per-user isolation | ADR 0037, `routes/auth.py` | M5 |
| Paste / Claude-assisted capture with review queue | ADR 0039, `routes/capture.py` | M5 |
| Three ATS adapters behind one Protocol | `adapters/` | M1 |
| Board discovery, validation, batch approval | `discovery/` | M1c |

M6 adds one adapter, one background runner, one backup path, and a great deal
of data. It does not add a feature the reader has not asked for.

---

## 4. The four obstacles, ranked by whether they are real

### 4.1 Coverage — real, and it is the whole problem

23 boards: 20 Ashby, 2 Greenhouse, 1 Lever. `board-discovery.md` §3 measured
**2,605 discoverable board tokens** on 2026-07-30. The candidate file holds
**23**, because `make discover` reads a committed crawl fixture and has never
been run with `--live`.

Two known repo gaps compound it, both already recorded in PROGRESS:

* **`make ingest` reaches 2 of 23 registered boards.** It hardcodes
  `pollable(ats="greenhouse")`. Two of the three adapters M1 built have no live
  CLI entry point at all; the ATS-general path exists only inside the worker.
* The polling pass that filled the corpus was driven by a throwaway script that
  **is not in the repo**.

### 4.2 The reader does not exist — real, and cheap

`users` holds two rows, `dev@nightshift.local` and `second@nightshift.local`,
both created by `make seed` at 2026-08-23 04:15 UTC. The dev user carries **6
fixture skills, 2 fixture projects and 10 fixture applications**. All 3,182
`match_results` score real jobs against an invented person.

Cheap because M5 built real identity. This is mostly *using* the application,
not extending it.

### 4.3 Disk — real, and it is the reader's to clear

```
/System/Volumes/Data   233Gi   206Gi used   6.1Gi free   98%
~/Downloads            78G
```

1,200 jobs occupy 72 MB of database. Linear projection to ~100,000 jobs is
**~6 GB**, which is every byte free. This is the same condition that killed
Docker on 2026-08-23 (`docs/runbooks/docker-will-not-start.md`): the volume hit
zero, the VM died mid-write, and a session was lost.

**§7 is gated on ~30 GB being freed.** §5 and §6 are not — they cost megabytes.
Nothing in this milestone deletes a file belonging to the reader.

### 4.4 Nothing runs unless a human starts it — real, and small

Polling happens in the ARQ worker's cron. The worker runs under `make dev`,
which is a foreground process in a terminal. If the reader is not running a dev
server, Nightshift learns nothing that day.

---

## 5. M6a — the reader exists, and there is something worth ranking

The slice ends with the reader looking at real early-career postings, ranked
against their own confirmed resume.

### 5.1 The reader's account

A real account through the front door — `POST /auth/register`, the same path
any user takes (ADR 0038). Not a seed function, not a `settings.dev_user_id`
special case. The fixture accounts stay where they are; `make seed` remains
what it is, and the reader's data lives beside it.

**The four facts a parser may not guess** — graduation month and year, school
and degree, work authorization, currently enrolled — are typed by the reader
into the profile screen. I2 admits user-*entered* data, so a value the reader
states in conversation is admissible; it is nonetheless entered once and then
**shown back on the profile screen for confirmation**, because the failure mode
here is not dishonesty but transcription, and a wrong graduation year silently
re-ranks the entire corpus.

The resume goes through the existing upload → parse → confirm flow unchanged.
No `proposed_*` value is promoted without the reader's click. That flow was
built in M2b and has never been used by the person it was built for.

### 5.2 The internship lists — one adapter, hundreds of roles

Publicly published, machine-readable lists of exactly the roles this reader
wants. Verified live 2026-08-25:

| Repo | Covers | File | Size | License |
|---|---|---|---|---|
| `SimplifyJobs/Summer2027-Internships` | SWE, data, AI, **quant**, PM, hardware | `.github/scripts/listings.json` | 10.6 MB | none stated |
| `vanshb03/Summer2027-Internships` | Summer / Fall / Spring 2027 | `.github/scripts/listings.json` | 275 KB | MIT |

One HTTP request each, structured JSON, refreshed daily by their maintainers.
This is the single highest-yield thing in the milestone and it is not disk-
gated.

**A list is a source, and gets a source row each.** `simplify_list` and
`vansh_list`, each writing `source_job_records` with the raw entry preserved,
each flowing through normalization, `job_locations` and the existing dedupe
layers. A posting on both lists produces two raw records and one canonical job,
which is what the dedupe layer is for; M1's fixtures already cover that shape.

They are **not** modelled as a second name for an existing source. M5a made
that mistake in the other direction and corrected it: a channel is not a
source. Here the reverse holds — these are genuinely different publishers with
different data, and collapsing them would hide which one was right.

### 5.3 The list says who is hiring; the board says what the job is

A list entry is a pointer: company, title, location text, URL, terms, a posted
date. It has **no description**, so M3's requirement extraction has almost
nothing to read and any score built on it alone is thin. Stated plainly rather
than discovered later.

The bridge is that most entries point at a Greenhouse, Ashby or Lever board
this repository already knows how to read. So:

1. Ingest the list entry. It is a real posting and the reader can apply to it
   today, thin score or not.
2. **Mine the URL for a board token.** A token that is not in the registry
   becomes a discovery candidate through the existing `candidates.yaml` →
   `validate` → `approve` chain, with no new approval machinery.
3. Once the board is registered and polled, the full posting arrives through
   the ATS adapter, dedupes against the list entry, and the score thickens.

This is **discovery aimed at companies that demonstrably hire interns**, which
is a far better filter for this reader than a Common Crawl sweep of every
company that has ever had a job board. It also means §7 is an improvement to
§5 rather than a prerequisite for it.

### 5.4 Relocation, not landmasses

The reader's answer on geography: **New York, plus remote, plus roles elsewhere
worth relocating for** — nothing discarded, other cities flagged so the
decision is per-role.

`archipelago.md` §4 already designed exactly this column: `landmass` ∈
`new_york | elsewhere_city | elsewhere_broad | unplaced`, written at ingestion
by one pure function, with measured populations (224 / 675 / 239 / 62).

**The design exists; the code does not.** Verified 2026-08-25: `landmass`
appears in no module and no migration on `m6a-geo-spine` or anywhere else. That
branch carries the gazetteer, ADR 0040 and a backfill — not this. So M6a
**builds** the column to `archipelago.md` §4's design, which is the same work
M7 would have done, brought forward because a reader filtering to New York
needs it and a renderer does not exist to need it yet. The water, the crossing
and the four drawn landmasses stay in M7.

The same applies to `archipelago.md` §6's placement preference rule. Placement
currently selects `is_primary`, which is whichever segment the employer typed
first, and that hides **71 New York roles — 24% of the city**. For a reader
filtering to New York, that is a quarter of their results missing, which makes
it an M6 defect rather than an M7 one.

### 5.5 Backup, because his data is now irreplaceable

`make reset-db` drops the database. Until now that cost fixture rows. After
§5.1 it costs an application history that exists nowhere else, and the runbooks
already record `make reset-db` being run casually.

`make backup` and `make restore`: `pg_dump` of the reader-owned tables to a
gitignored local directory, plus a warning in `reset-db` naming what is about
to be destroyed. Small, and the alternative is finding out the hard way.

### 5.6 Acceptance

* The reader signs in as themselves; `dev@nightshift.local` is not involved.
* Their resume is uploaded, parsed, and **confirmed by them**; no
  `proposed_*` value reached `confirmed` without a click. Shown able to fail.
* Early-career open roles rise from **12** to a number recorded in PROGRESS.
  No target is set here — a target invites tuning the classifier until it is
  met, which is precisely the failure this milestone opened by refuting.
* Every list-sourced job traces to a raw `source_job_records` row.
* Re-running the list ingest is idempotent: no duplicates, no spurious updates.
* A list that 404s or returns `[]` closes **zero** jobs. Shown able to fail.
* A job in another city is labelled as requiring relocation, and is reachable
  by filter rather than deleted.
* `make backup` produces a file; `make restore` reproduces the reader's
  applications into an empty database.

---

## 6. M6b — the daily loop

The slice ends with Nightshift being fresh without being started.

1. **The poller runs without a terminal.** A `launchd` agent running the ARQ
   worker, installed by an opt-in make target, logging where a person can read
   it. Not a new scheduler — ADR 0007's conditional polling and ADR 0011's
   `next_poll_at` are unchanged; this only keeps the existing worker alive.
2. **"New since you last looked."** The daily queue reads current state (ADR
   0014). What it cannot say is what changed since the reader's last visit,
   which is the question a person actually opens a job board with.
3. **Deadlines.** `application_deadline` exists on `jobs` and is surfaced
   nowhere. Internship deadlines are the thing you lose a season to.
4. **Apply, and track it.** One action that opens the employer's own posting
   and creates a tracked application at `applied`. **I5 is not bent**:
   Nightshift never submits anything, never fills a form, never sends mail. It
   opens the page and records that the reader went there.

### 6.1 Acceptance

* The machine is rebooted, nothing is started by hand, and boards are polled.
* The queue distinguishes new-since-last-visit from merely open, and the test
  that proves it is shown able to fail.
* A role with a deadline inside 14 days is visible without filtering for it.
* Applying creates exactly one application and one append-only event, and
  submits nothing anywhere. Shown able to fail.

---

## 7. M6c — full reach. Gated on §4.3

Not started until ~30 GB is free. Order:

1. **`make ingest` polls every registered board**, all three adapters, one
   shared `PoliteClient` so the per-host rate limit holds across the run — the
   property the throwaway script had and the repo does not.
2. **Tokens mined from §5.3** validated and approved first: highest yield per
   byte, and already known to hire interns.
3. **`make discover --live`** against Common Crawl for Greenhouse and Ashby,
   then `validate`, then `approve --write`. ADR 0005's batch approval applies;
   a live-but-unnameable board still cannot reach bulk approval.
4. **A full polling pass**, measured: boards, jobs, failures, wall time, bytes.

Recorded before and after: corpus size, early-career count, database size on
disk. **If the database passes 4 GB the pass stops** and the number goes in
PROGRESS rather than the disk filling silently.

---

## 8. M6d — the blind spots, named

Not built in M6. Named because a coverage page that lists only what it has is
the failure `CLAUDE.md` M1 already legislated against.

| Blind spot | Why it matters to this reader | Cost |
|---|---|---|
| **Lever discovery** | `jobs.lever.co/robots.txt` disallows CCBot, so Common Crawl cannot see Lever and never will (`board-discovery.md` §3). Needs careers-page probing. | Medium |
| **Workday, iCIMS, Taleo, SmartRecruiters** | Where banks and large quant shops post. The reader named quant explicitly. | One adapter each |
| **Handshake** | Where a large share of university-channel internships live. Requires a school login; assisted capture (M5) is the only sanctioned route. | ADR needed |
| **LinkedIn, Indeed** | Ruled out permanently for polling (`board-discovery.md` §9). Reachable only through M5's user-initiated capture. | Already built |

---

## 9. Invariants under strain, and how each holds

**I1 — never fabricate a location.** List entries carry free text like
`"New York, NY"` or `"Remote in USA"`. They resolve to `city_only` and `remote`
through the existing normalizer, never to a building. `archipelago.md`'s
gazetteer (ADR 0040) handles bare city names on ADR 0008's terms. **A list
entry never produces `verified`.**

**I2 — never fabricate a qualification.** Unchanged. The resume flow's confirm
step is used as built, and §5.1 adds a second look at the four typed facts.

**I3 — never silently close a listing.** The sharp edge in this milestone.
Both lists carry an `active` boolean, and it is tempting to treat
`active: false` as a closure. **It is not.** It is evidence that a volunteer
maintainer believes the role closed — hearsay about a source we do not poll.
It is *recorded* on the source record and may inform ranking; closure still
requires ADR 0009's misses-and-elapsed-time rule against a source polled
first-hand. A list going 404, empty, or all-inactive closes nothing.

**I5 — never take an irreversible action.** §6.4 is the whole of the exposure
and it is deliberately one click short of applying.

**I7 — never let a mock become the product.** Both list adapters ship with
committed fixtures recorded from the real files, and the live path is the same
code. Nothing in M6 is fixture-only.

---

## 10. Licensing, and the one thing that needs a human

`SimplifyJobs/Summer2027-Internships` states **no license**. `vanshb03` is MIT.
Both are published expressly so job-seekers can find postings, both are read as
a single public file over HTTPS with no crawling, both are attributed in the
coverage page, and every entry links out to the employer's own posting rather
than reproducing it. For one person's personal job search this is
unobjectionable.

It is nonetheless an unstated license, which `CLAUDE.md` §5 says to raise
rather than decide silently. **Logged as Q16.** It does not block: the MIT list
alone is unambiguous, and the work is structured so either source can be
dropped without touching the other.

---

## 11. Deferred, and open

* **The Archipelago** (M7) — everything in `archipelago.md` except the
  `landmass` column and the placement rule.
* **Deployment** (M8) — the reader runs this locally, by instruction.
* **Multi-user anything** beyond the isolation M5 already proved.
* **Q15** (the Island's second and third districts) — moves with M7.
* **Open and not blocking:** Q16 (above), Q13, Q12, Q11, Q10, Q9, Q7, Q6.
