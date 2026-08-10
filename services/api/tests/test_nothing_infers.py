"""Invariant I2, asserted structurally rather than promised in a docstring.

``domain/profile.py`` is the only module that may write a confirmed fact. The
claim is worth a test because it is the kind of thing that stays true until one
convenient afternoon — the same sentence ``test_nothing_applies.py`` opens
with, for the same reason.

Three assertions, each covering a different way the boundary could be crossed:
a direct assignment, a constructor, and a dynamic write that a grep for either
would miss.
"""

from __future__ import annotations

import re
from pathlib import Path

from nightshift.db.base import EligibilityState
from nightshift.domain.matching import BAND_ORDER

ROOT = Path(__file__).resolve().parents[1] / "nightshift"
WRITER = ROOT / "domain" / "profile.py"
MODELS = ROOT / "db" / "models.py"

#: The columns that hold a confirmed claim about a person.
PROFILE_COLUMNS = (
    "graduation_year",
    "graduation_month",
    "degree",
    "school",
    # M3b's two gate inputs. Both are claims about a person and both could be
    # guessed from `graduation_year` with one subtraction, which is the I2
    # violation easiest to write and hardest to spot in review.
    "years_experience",
    "is_enrolled",
    "work_authorization",
    "home_location_text",
    "remote_preference",
    "minimum_salary",
    "preferred_roles",
    "preferred_locations",
)

#: `setattr` defeats every grep in this file, so its use is allowlisted rather
#: than searched for. `applications.py` uses it for M2b's detail updates, which
#: are not profile facts. A new entry here has to be a deliberate act.
SETATTR_IS_ALLOWED_IN = {ROOT / "domain" / "applications.py"}


def _sources() -> list[Path]:
    return sorted(ROOT.rglob("*.py"))


def test_only_the_confirm_handler_writes_a_profile_column() -> None:
    # `=` but not `==`: `User.degree == value` is a filter, not a write. The
    # same subtlety bit M2b's stage guard, which matched a comparison and hid a
    # real bug behind a passing test.
    patterns = [re.compile(rf"\.{column}\s*=(?!=)") for column in PROFILE_COLUMNS]
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in _sources()
        if path not in (WRITER, MODELS)
        and any(pattern.search(path.read_text(encoding="utf-8")) for pattern in patterns)
    )
    assert offenders == [], f"these write a confirmed profile fact: {offenders}"


def test_only_the_confirm_handler_constructs_a_confirmed_row() -> None:
    constructor = re.compile(r"\b(UserSkill|UserProject)\s*\(")
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in _sources()
        if path not in (WRITER, MODELS) and constructor.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], f"these construct a confirmed fact: {offenders}"


def test_no_new_module_writes_attributes_dynamically() -> None:
    """A `setattr` is invisible to both greps above, so it is allowlisted."""
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in _sources()
        if path not in SETATTR_IS_ALLOWED_IN and "setattr(" in path.read_text(encoding="utf-8")
    )
    assert offenders == [], (
        f"these write attributes dynamically: {offenders}. If the target is not a "
        "confirmed profile fact, add the file to SETATTR_IS_ALLOWED_IN deliberately."
    )


def test_nothing_rewrites_the_text_a_proposal_quotes() -> None:
    """A span is an offset into ``resumes.parsed_text``. Edit that text and every
    proposal on it silently starts quoting different words.

    The trigger cannot catch it — it fires on ``resume_extractions``, not on
    ``resumes``, so an UPDATE to the parent passes unexamined while every child
    row becomes a lie. Today no code path assigns the column at all
    (``create_resume`` passes it to the constructor and nothing else touches
    it), and this is what keeps that true. A resume whose text really changed
    is a different resume, which is what the content hash already says.
    """
    written = re.compile(r"\.parsed_text\s*=(?!=)")
    offenders = sorted(
        str(path.relative_to(ROOT))
        for path in _sources()
        if written.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], (
        f"these rewrite the text proposals point at: {offenders}. Create a new "
        "resume instead — the spans on the old one belong to the old text."
    )


def test_the_extractor_does_not_call_back_into_the_writer() -> None:
    """`profile.py` may call the extractor; the extractor may not call back."""
    extractor = (ROOT / "domain" / "resume_extraction.py").read_text(encoding="utf-8")
    assert "profile" not in extractor


#: Columns on `users` that are **not** claims about a person, so the guard above
#: does not cover them. A column in neither tuple is a column nobody decided
#: about.
NOT_A_PROFILE_FACT = frozenset(
    {
        "id",
        "email",
        "display_name",
        "timezone",
        "created_at",
        "updated_at",
    }
)


def test_no_profile_column_escapes_the_guard_by_being_added_later() -> None:
    """`PROFILE_COLUMNS` is hand-maintained, and a hand-maintained list of what
    to protect goes stale in exactly one direction: things get added to the
    model and not to the list.

    That is not hypothetical. M3b added `years_experience` and `is_enrolled` to
    `users` and this guard did not cover either of them until somebody looked —
    which is the fourth time in this project a list has quietly stopped
    describing the thing it guards. The other three were "not built yet" lists;
    this one would have been an invariant.

    So the list is checked against the model rather than trusted. A new column
    must be classified deliberately, in one tuple or the other, and neither
    choice can be made by forgetting.
    """
    from nightshift.db.models import User

    columns = {column.name for column in User.__table__.columns}
    accounted = set(PROFILE_COLUMNS) | NOT_A_PROFILE_FACT
    assert columns - accounted == set(), (
        f"columns on `users` that nobody has classified: {sorted(columns - accounted)}"
    )
    assert accounted - columns == set(), (
        f"named here but not a column on `users`: {sorted(accounted - columns)}"
    )


# ---------------------------------------------------------------------------
# The second hand-maintained list, added at M3c Task 8, guarded the same way
#
# `matching.SCORING_RELEVANT_PROFILE_COLUMNS` decides whether a profile edit
# deletes that person's stored scores. `matching.md` §4.2 says "any profile
# change" and the M3c plan named that wording as a trap: M2c's PATCH writes
# fifteen columns and most components read none of them, so taken literally a
# display-name edit rescores the corpus.
#
# The list is what makes it *not* literal, which makes the list load-bearing in
# both directions and asymmetrically expensive to get wrong. A column wrongly on
# the not-relevant side produces a score that never updates, never errors, and
# never looks wrong on the page — the exact failure mode `PROFILE_COLUMNS`
# itself had at M3b, one list over.
# ---------------------------------------------------------------------------


def test_every_profile_column_is_classified_as_scoring_relevant_or_not() -> None:
    """The two matching tuples must partition `PROFILE_COLUMNS`. No overlap, no gap."""
    from nightshift.domain.matching import (
        NOT_SCORING_RELEVANT_PROFILE_COLUMNS,
        SCORING_RELEVANT_PROFILE_COLUMNS,
    )

    relevant = set(SCORING_RELEVANT_PROFILE_COLUMNS)
    irrelevant = set(NOT_SCORING_RELEVANT_PROFILE_COLUMNS)
    profile = set(PROFILE_COLUMNS)

    assert relevant & irrelevant == set(), f"classified both ways: {sorted(relevant & irrelevant)}"
    assert relevant | irrelevant == profile, (
        "the two tuples must cover exactly `PROFILE_COLUMNS`. "
        f"unclassified: {sorted(profile - relevant - irrelevant)}; "
        f"not a profile column: {sorted(relevant | irrelevant - profile)}"
    )


def test_the_scoring_relevant_columns_are_real_columns_on_users() -> None:
    """`PROFILE_COLUMNS` is already checked against the model, so this is
    implied by the partition above — until somebody edits one of the three lists
    and not the others, which is the whole reason any of them are checked."""
    from nightshift.db.models import User
    from nightshift.domain.matching import SCORING_RELEVANT_PROFILE_COLUMNS

    columns = {column.name for column in User.__table__.columns}
    named = set(SCORING_RELEVANT_PROFILE_COLUMNS)
    assert named - columns == set(), f"named but not columns: {sorted(named - columns)}"


def test_every_column_a_score_reads_is_named_scoring_relevant() -> None:
    """The list against the code that reads it, rather than against a memory of it.

    `profile_for` builds the scorer's `ScoringProfile` and `profile_from_user`
    builds the gate's `SeekerProfile`; between them they name every `users`
    column a stored `match_results` row depends on. Both are written as literal
    `user.<column>` / `getattr(user, "<column>")` reads, so a grep sees them —
    and a component that starts reading a new column without anyone updating the
    list turns this red, which is the case the partition test above cannot
    reach because such a column is already classified, just wrongly.
    """
    from nightshift.domain.matching import SCORING_RELEVANT_PROFILE_COLUMNS

    sources = "\n".join(
        (ROOT / "domain" / name).read_text(encoding="utf-8")
        for name in ("matching.py", "eligibility.py")
    )
    read = {
        column
        for column in PROFILE_COLUMNS
        if re.search(rf"user\.{column}\b", sources)
        or re.search(rf'getattr\(user, "{column}"', sources)
    }
    unnamed = read - set(SCORING_RELEVANT_PROFILE_COLUMNS)
    assert unnamed == set(), (
        f"a score reads these and the list does not name them: {sorted(unnamed)}. "
        "A profile edit to one of them would leave every stored score stale, "
        "with nothing failing."
    )


# ---------------------------------------------------------------------------
# The third hand-maintained mapping, added at M3c Task 9
#
# `matching.COMPONENT_SCORE_COLUMNS` was one function's local detail until the
# job route began reading the columns back to rebuild the breakdown. Two
# hand-written mappings of the same six pairs is the drift this file exists for,
# and this one is invisible when it goes wrong: a transposition leaves the total
# adding up and every constraint holding, and only the decomposition is wrong —
# which is the one thing invariant I4 is a claim about.
# ---------------------------------------------------------------------------


def test_every_component_maps_to_its_own_real_score_column() -> None:
    from nightshift.db.base import MatchComponent
    from nightshift.db.models import MatchResult
    from nightshift.domain.matching import COMPONENT_SCORE_COLUMNS

    named = set(COMPONENT_SCORE_COLUMNS)
    assert named == set(MatchComponent), (
        f"components with no column: {sorted(set(MatchComponent) - named)}; "
        f"columns for no component: {sorted(named - set(MatchComponent))}"
    )

    columns = {column.name for column in MatchResult.__table__.columns}
    mapped = set(COMPONENT_SCORE_COLUMNS.values())
    assert mapped - columns == set(), f"named but not columns: {sorted(mapped - columns)}"
    # Distinct, or two components read one column and one of them is silently
    # showing the other's points.
    assert len(mapped) == len(MatchComponent)


# ---------------------------------------------------------------------------
# The ranked list's band order — M3c Task 10
# ---------------------------------------------------------------------------


def test_every_eligibility_state_has_a_band() -> None:
    """`BAND_ORDER` against the enum, with no database in the way.

    A state missing from the tuple is a band of postings that never renders and
    never errors — the rows are stored, the counts above them are right, and the
    section simply is not there.
    """
    assert set(BAND_ORDER) == set(EligibilityState)
    assert len(BAND_ORDER) == len(EligibilityState)


def test_uncertain_sorts_above_likely_ineligible() -> None:
    """§5.3, stated as its own assertion because it is the one ordering choice in
    the tuple that is a product decision rather than an obvious ranking.

    An open question is not a soft no. Sorting them the other way round buries the
    postings a person could resolve by filling in one profile field under the ones
    they cannot resolve at all.
    """
    assert BAND_ORDER.index(EligibilityState.UNCERTAIN) < BAND_ORDER.index(
        EligibilityState.LIKELY_INELIGIBLE
    )
