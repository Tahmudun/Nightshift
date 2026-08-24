"""Does the corpus already hold the job somebody is about to capture?

M5d / ADR 0039 §4. Nightshift polls thousands of board tokens first-hand, so
most NYC tech postings a reader finds on LinkedIn are **already in it** — with
a match score, a location the system trusts, and a source it can go back to.
Capturing one of those costs a review and produces a thinner second record of a
job already held.

So the capture response says what the corpus already has, and the tool
description tells the model to lead with it.

## This is advisory, and it is not ``dedupe.compare``

Nothing here merges anything. No ``job_merge_event`` is written, no
``job_source_link`` is created, and the reader still decides. The merge
comparator was considered and does not fit: its layers block on company,
employment type, title *and* location before similarity is even reachable, and
a pasted posting honestly has none of the last three. Feeding it invented
values to get an answer would be exactly the failure this milestone is about.

What is here instead is two deterministic rules, each of which can be stated to
a reader in one sentence, and each of which names itself in the result.

## The rule about not knowing

**When there is nothing to check with, the answer is "not checked" — never an
empty list.** An empty ``matches`` reads as *no duplicates*, and presenting
silence as evidence is invariant I3's failure moved to a new place. A capture
whose company the parser declined to read is a capture this module cannot
answer for, and it says so in a sentence the reader can act on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.greenhouse import normalize_title
from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, JobSourceLink, SourceJobRecord
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.dedupe import normalize_url

#: More than this and the answer stops being "you already have this" and starts
#: being a search result, which is what `search_jobs` is for.
MAX_MATCHES = 5


@dataclass(frozen=True, slots=True)
class CorpusMatch:
    """One job the corpus already holds, and why this module thinks so.

    ``reason`` is a short stable token rather than prose, the same choice
    ``DedupeVerdict.reason`` makes and for the same reason: it is rendered by
    two clients and compared by tests.
    """

    job_id: uuid.UUID
    title: str
    company_name: str
    status: JobStatus
    reason: str


@dataclass(frozen=True, slots=True)
class CorpusCheck:
    """The answer, including the answer "I could not look".

    ``checked is False`` with an empty ``matches`` is a different statement
    from ``checked is True`` with an empty ``matches``, and collapsing the two
    is the only way this module can mislead somebody.
    """

    checked: bool
    why_not: str | None
    matches: tuple[CorpusMatch, ...]


#: Open roles first, then most recently seen.
#:
#: Two records of one opening happen — a role reposted, or polled from two
#: boards — and the live one is the one a reader can act on. Shared by both
#: rules rather than written twice, because an ordering that disagreed between
#: them would put the closed copy first depending on which rule happened to
#: fire.
LIVE_FIRST = ((Job.status != JobStatus.OPEN), Job.last_seen_at.desc())


async def check_corpus(
    session: AsyncSession,
    *,
    title: str | None,
    company_name: str | None,
    source_url: str | None,
) -> CorpusCheck:
    """Look for jobs Nightshift already holds that this paste is probably about.

    Two rules, tried in order of how much they prove.

    **``same_url``** — the reader pasted a link this corpus already has a
    source record for. Narrow, because a LinkedIn URL will never equal a
    Greenhouse one, and worth having anyway: it is the only rule that works
    when the text could not be read at all, which is exactly when the other
    rule is unavailable. Compared through ``dedupe.normalize_url``, so
    ``?utm_source=linkedin`` does not make it a different posting.

    **``same_company_and_title``** — the normalised employer and the normalised
    title both match. Normalisation is the ingestion pipeline's own
    (``normalize_company_name``, ``normalize_title``) rather than a private
    reading, so this check and the corpus agree by construction; a second
    normaliser here would drift, and the symptom would be a duplicate warning
    that quietly stopped firing.
    """
    by_url = await _by_url(session, source_url)
    if by_url:
        return CorpusCheck(checked=True, why_not=None, matches=by_url)

    if not company_name or not title:
        missing = "a company name" if not company_name else "a job title"
        also = " or a URL Nightshift already has a record for" if not source_url else ""
        return CorpusCheck(
            checked=False,
            why_not=(
                f"Nothing could be read from this posting as {missing}{also}, so "
                "Nightshift has not checked whether it already holds this job. "
                "This is not the same as finding no duplicates."
            ),
            matches=(),
        )

    rows = (
        await session.execute(
            select(Job, Company)
            .join(Company, Company.id == Job.company_id)
            .where(
                Company.normalized_name == normalize_company_name(company_name),
                Job.normalized_title == normalize_title(title),
            )
            .order_by(*LIVE_FIRST)
            .limit(MAX_MATCHES)
        )
    ).all()

    return CorpusCheck(
        checked=True,
        why_not=None,
        matches=tuple(
            CorpusMatch(
                job_id=job.id,
                title=job.title,
                company_name=company.canonical_name,
                status=job.status,
                reason="same_company_and_title",
            )
            for job, company in rows
        ),
    )


async def _by_url(session: AsyncSession, source_url: str | None) -> tuple[CorpusMatch, ...]:
    """Jobs whose own source record points at the same page.

    Two steps, and the split is deliberate. **SQL narrows, Python decides.**

    ``normalize_url`` is a Python function — it strips tracking parameters,
    lowercases the host, drops a trailing slash — and reimplementing it as a
    SQL predicate would be a second reading of one rule, which is the drift
    this module avoids everywhere else. So the query narrows on the part of the
    URL that is stable under that normalisation, the host and path, with a
    ``LIKE``; then ``normalize_url`` compares the survivors exactly.

    The first draft of this function did it the other way round — select
    everything with a URL, limit 5, filter in Python — which would have found
    the right job only if it happened to be among the five most recent rows in
    the whole corpus. It is written down because the test that caught it was a
    two-row fixture, and a bigger one would have caught it later or never.
    """
    normalized = normalize_url(source_url)
    if normalized is None:
        return ()

    split = urlsplit(normalized)
    if not split.netloc:
        return ()
    # Host and path, with no scheme and no query: everything `normalize_url`
    # can change is outside it.
    stem = f"{split.netloc}{split.path}".rstrip("/")
    if not stem:
        return ()

    rows = (
        await session.execute(
            select(Job, Company, SourceJobRecord.canonical_url)
            .join(Company, Company.id == Job.company_id)
            .join(JobSourceLink, JobSourceLink.job_id == Job.id)
            .join(
                SourceJobRecord,
                SourceJobRecord.id == JobSourceLink.source_job_record_id,
            )
            .where(SourceJobRecord.canonical_url.ilike(f"%{stem}%"))
            .order_by(*LIVE_FIRST)
        )
    ).all()

    matches: list[CorpusMatch] = []
    seen: set[uuid.UUID] = set()
    for job, company, canonical_url in rows:
        if job.id in seen or normalize_url(canonical_url) != normalized:
            continue
        seen.add(job.id)
        matches.append(
            CorpusMatch(
                job_id=job.id,
                title=job.title,
                company_name=company.canonical_name,
                status=job.status,
                reason="same_url",
            )
        )
        if len(matches) == MAX_MATCHES:
            break
    return tuple(matches)


__all__ = ["LIVE_FIRST", "MAX_MATCHES", "CorpusCheck", "CorpusMatch", "check_corpus"]
