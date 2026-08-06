"""`role_family` and `seniority` get filled in, including on an unchanged poll.

These two columns were null on every row in the database the day M3b added
them, and the event that fills them in is a poll. **A poll of a posting nobody
has edited is by far the commonest kind**, so a classifier gated on "the
description changed" — which is how `sync_requirements` is correctly gated —
would leave the corpus null until each posting's text happened to move.

That is the `EXTRACTOR_VERSION` lag M3a.1 recorded, except that one at least had
a version column making it visible. A null `seniority` and an unclassifiable
`seniority` look identical from the outside unless something keeps them apart.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import RoleFamily, Seniority
from nightshift.domain.ingestion import sync_classification
from tests.conftest import make_job_with_text, requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

_INTERNSHIP = "Requirements for this role: Pursuing a bachelor's in a technical field."


async def test_a_title_and_a_description_produce_both_columns(db_session: AsyncSession) -> None:
    job = await make_job_with_text(db_session, _INTERNSHIP)
    job.title = "Hardware Engineer Intern, Summer 2027"

    sync_classification(job)

    assert job.seniority is Seniority.INTERNSHIP
    assert job.role_family is RoleFamily.HARDWARE


async def test_classifying_twice_produces_the_same_answer(db_session: AsyncSession) -> None:
    """Determinism, which M3's acceptance criterion asks for directly."""
    job = await make_job_with_text(db_session, _INTERNSHIP)
    job.title = "Senior Security Engineer"

    sync_classification(job)
    first = (job.role_family, job.seniority)
    sync_classification(job)

    assert (job.role_family, job.seniority) == first


async def test_a_retitled_posting_is_reclassified(db_session: AsyncSession) -> None:
    """The reason classification is not gated on the description hash.

    "Software Engineer" becoming "Senior Software Engineer" is a re-levelling
    with no character of the description changing. Gated the way requirements
    are, this posting would keep the level it was first seen at forever.
    """
    job = await make_job_with_text(db_session, "We build things.")
    job.title = "Software Engineer"
    sync_classification(job)
    assert job.seniority is Seniority.UNCLEAR

    job.title = "Senior Software Engineer"
    sync_classification(job)
    assert job.seniority is Seniority.SENIOR


async def test_a_job_with_no_title_is_left_null_rather_than_guessed_at(
    db_session: AsyncSession,
) -> None:
    """Null means "never classified" and must not become `unclear`.

    `unclear` is the classifier having read a posting and declined to guess.
    Merging the two would make a coverage figure unreadable: an unrun classifier
    and a corpus of ambiguous titles would look identical.
    """
    job = await make_job_with_text(db_session, _INTERNSHIP)
    job.title = ""

    sync_classification(job)

    assert job.role_family is None
    assert job.seniority is None


async def test_a_posting_with_no_description_still_gets_a_level(
    db_session: AsyncSession,
) -> None:
    """The title carries most of the signal, so an empty description is not a
    reason to refuse. `read_posting` over empty text yields no years figure,
    which the level rule handles as "the posting states none"."""
    job = await make_job_with_text(db_session, None)
    job.title = "Director of Engineering"

    sync_classification(job)

    assert job.seniority is Seniority.DIRECTOR
    assert job.role_family is RoleFamily.SOFTWARE_ENGINEERING


async def test_the_years_figure_comes_from_the_same_reading_the_gate_uses(
    db_session: AsyncSession,
) -> None:
    """Jane Street's campus recruiter, in miniature.

    Three words in the title say early career and the posting asks for six
    years, so the level is `senior`. That rule only works if the years figure
    reaching the classifier is the one the reading produced — re-deriving it
    here with a second regex is how the gate and the level come to disagree
    about the same posting.
    """
    job = await make_job_with_text(
        db_session, "Requirements: 6+ years of experience in early careers programmes."
    )
    job.title = "Campus Recruiter, Early Careers"

    sync_classification(job)

    assert job.seniority is Seniority.SENIOR
