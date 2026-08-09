"""The database's vocabulary and the browser's, asserted equal.

Every `z.enum([...])` in `apps/web/src/lib/schemas.ts` is a copy of a Python
enum, and a copy drifts. When it does, nothing fails until a real response
carrying the missing value reaches a real browser and Zod refuses to parse a
page — a failure that no Python test and no component test can reach, because
both sides pass in isolation.

**This test was written because that drift had already happened.** Two of the
nine enums below were transcribed wrong on their first write: `WorkAuthorization`
gained a `requires_sponsorship` that does not exist (the real member is
`needs_sponsorship`), and `SkillSourceType` lost `assessment` and `github`
entirely. Both were found by printing the enums rather than by reading the code,
which is the same lesson `test_repo_integrity.py` records: a check that only
reads one side of a boundary cannot see the boundary.

Values, not order — `z.enum` does not care about order and neither does the
wire.
"""

from __future__ import annotations

import enum
import re
from pathlib import Path

import pytest

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationPriority,
    ApplicationStage,
    EligibilityState,
    ExtractionKind,
    ExtractionStatus,
    InternshipSeason,
    ProficiencyLevel,
    ProjectStatus,
    RemotePreference,
    RequirementKind,
    RequirementNecessity,
    ResumeSourceKind,
    ResumeVariant,
    RoleFamily,
    Seniority,
    SkillSourceType,
    TransitionClass,
    WorkAuthorization,
)
from nightshift.domain.eligibility import _ASKS_FOR
from nightshift.domain.queue import QueueSectionKey

SCHEMAS_TS = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "schemas.ts"
JOB_ELIGIBILITY_TSX = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "web"
    / "src"
    / "components"
    / "JobEligibility.tsx"
)

#: The TypeScript constant name for each Python enum.
PAIRS: tuple[tuple[str, type[enum.Enum]], ...] = (
    ("workAuthorizationSchema", WorkAuthorization),
    ("remotePreferenceSchema", RemotePreference),
    ("proficiencyLevelSchema", ProficiencyLevel),
    ("skillSourceTypeSchema", SkillSourceType),
    ("projectStatusSchema", ProjectStatus),
    ("resumeSourceKindSchema", ResumeSourceKind),
    ("resumeVariantSchema", ResumeVariant),
    ("extractionKindSchema", ExtractionKind),
    ("extractionStatusSchema", ExtractionStatus),
    # M3b. RoleFamily and Seniority are database enums; EligibilityState is not
    # — the gate computes on read and stores nothing until M3c — and it is here
    # anyway, because this test is about a vocabulary crossing the boundary and
    # not about where it happens to be persisted.
    ("roleFamilySchema", RoleFamily),
    ("senioritySchema", Seniority),
    ("eligibilityStateSchema", EligibilityState),
    # M3b Task 11. This one reaches the browser as a *filter* value rather than
    # as a field the page renders, which is the more brittle direction: a typo
    # here produces a query the API rejects, or worse an empty result that
    # looks like an honest "no such job".
    ("internshipSeasonSchema", InternshipSeason),
    # M2d. `QueueSectionKey` is the first entry here that is not a database
    # enum — it is a shape of the API, defined in `domain.queue`. It crosses
    # the same boundary and drifts the same way, which is what this file is
    # about.
    ("queueSectionKeySchema", QueueSectionKey),
    # M2b's vocabulary, unguarded until M2d added the four lines below. The
    # nine pairs above are all M2c's, written the day this file was created;
    # these four had been crossing the same boundary unchecked since M2b. The
    # queue's row schema parses `current_stage`, so M2d depends directly on
    # the first of them being right.
    ("applicationStageSchema", ApplicationStage),
    ("applicationPrioritySchema", ApplicationPriority),
    ("applicationEventTypeSchema", ApplicationEventType),
    ("transitionClassSchema", TransitionClass),
    # M3a. Added before the TypeScript existed, so the guard failed first and
    # was seen to fail — the transcription was then checked by printing the
    # Python members rather than reading them, which is how M2c's two defects
    # were eventually found.
    ("requirementKindSchema", RequirementKind),
    ("requirementNecessitySchema", RequirementNecessity),
)


def _typescript_enum(name: str) -> set[str]:
    """The string literals inside `export const <name> = z.enum([...])`."""
    source = SCHEMAS_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {re.escape(name)} = z\.enum\(\[(.*?)\]\)", source, re.DOTALL)
    assert match is not None, f"{name} is not declared as a z.enum in schemas.ts"
    return set(re.findall(r"'([^']*)'", match.group(1)))


def test_the_typescript_file_is_where_this_test_thinks_it_is() -> None:
    """`parents[3]` is the repo root — `parents[2]` is `services/`.

    Stated as its own assertion because this project has made that exact
    off-by-one three times, and a path that does not exist would otherwise turn
    every check below into a vacuous pass.
    """
    assert SCHEMAS_TS.is_file(), f"{SCHEMAS_TS} does not exist"


@pytest.mark.parametrize(("name", "enum_cls"), PAIRS, ids=[name for name, _ in PAIRS])
def test_the_browser_knows_exactly_the_values_the_database_can_send(
    name: str, enum_cls: type[enum.Enum]
) -> None:
    python_values = {member.value for member in enum_cls}
    assert _typescript_enum(name) == python_values, (
        f"{name} in schemas.ts and {enum_cls.__name__} disagree. A value the API "
        "can send and the client refuses is an unparseable page; a value the "
        "client accepts and the API cannot send is dead UI."
    )


def test_the_page_has_words_for_every_profile_field_an_unknown_can_ask_for() -> None:
    """`_ASKS_FOR`'s values against `ASKS`'s keys, which is the same boundary.

    Not a `z.enum`, so the parametrised test above cannot reach it, and it drifts
    the same way and fails more quietly. `ASKS[field] ?? field` falls back to the
    raw column name, so a rule added without its phrase does not throw and does
    not blank the page — it prints **"Add years_experience"** to a person, which
    reads as a bug in a sentence that is otherwise asking them for help.

    One-directional on purpose. Every field a rule can ask for must have words;
    a spare phrase in `ASKS` for a field no rule asks for is dead but harmless,
    and M3c adds rules faster than it removes them.
    """
    assert JOB_ELIGIBILITY_TSX.is_file(), f"{JOB_ELIGIBILITY_TSX} does not exist"
    source = JOB_ELIGIBILITY_TSX.read_text(encoding="utf-8")
    match = re.search(r"const ASKS: Record<string, string> = \{(.*?)\n\};", source, re.DOTALL)
    assert match is not None, "ASKS is not declared in JobEligibility.tsx"
    phrased = set(re.findall(r"^\s*(\w+):", match.group(1), re.MULTILINE))

    missing = set(_ASKS_FOR.values()) - phrased
    assert not missing, (
        f"the gate can ask for {sorted(missing)} and JobEligibility.tsx has no words "
        "for it, so the page would print the column name at a person"
    )


def test_the_match_migration_creates_exactly_the_types_the_models_declare() -> None:
    """M3c's three new enums, against the copies inside `0016_match_results`.

    The same boundary `test_eligibility_labels.py` guards for `RoleFamily` and
    `Seniority`, and the copy is unavoidable for the same reason: a migration
    that imports a model stops describing the schema as of its own revision and
    starts describing today's. So the values are module constants there
    precisely so this test can read them.

    `eligibility_state` is the one to watch. It existed as a Python enum for a
    whole milestone before it became a database type, which is exactly the shape
    of transcription this file was written after — a vocabulary that has been
    correct in one place long enough that nobody re-reads it when it acquires a
    second.
    """
    import importlib

    from nightshift.db.base import EligibilityState, EvidenceSource, MatchComponent

    migration = importlib.import_module("migrations.versions.20260809_1607_match_results")

    assert set(migration.ELIGIBILITY_STATE_VALUES) == {m.value for m in EligibilityState}
    assert set(migration.MATCH_COMPONENT_VALUES) == {m.value for m in MatchComponent}
    assert set(migration.EVIDENCE_SOURCE_VALUES) == {m.value for m in EvidenceSource}


def test_the_denominator_migration_creates_exactly_the_type_the_model_declares() -> None:
    """`job_text_field`, against its copy inside `0017_match_score_denominator`.

    A fourth enum with a fourth copy, and the one with the sharpest failure mode
    of the four: `job_span_field` selects which column of `jobs` the quoting
    trigger checks a span against. A member missing from the type is not a
    rendering bug — it is a `CASE` with no matching branch, a null `source_text`,
    and every evidence row for that field refused at insert.
    """
    import importlib

    from nightshift.db.base import JobTextField

    migration = importlib.import_module("migrations.versions.20260809_1930_match_score_denominator")

    assert set(migration.JOB_TEXT_FIELD_VALUES) == {m.value for m in JobTextField}


def test_the_quoting_trigger_reads_every_field_the_enum_can_hold() -> None:
    """The `CASE` inside the trigger, against the enum, rather than by eye.

    This is the assertion the test above cannot make. The two vocabularies can
    agree perfectly while the trigger's `CASE` handles only one of them — and a
    `CASE` with no matching branch returns null in Postgres rather than raising,
    so the row is refused with *'scores a job whose title is null'* on a job
    whose title is right there. A message that sends the reader to look at the
    wrong table is worse than no message.
    """
    import importlib

    from nightshift.db.base import JobTextField

    migration = importlib.import_module("migrations.versions.20260809_1930_match_score_denominator")
    branches = set(re.findall(r"WHEN '([^']+)' THEN", migration._SELECT_BY_FIELD))

    assert branches == {m.value for m in JobTextField}


def test_every_match_component_is_scored_by_a_column_of_its_own() -> None:
    """The evidence guard walks a hand-written list of (component, column) pairs
    inside the migration, and a component missing from it is a component nothing
    checks.

    This is the failure mode the guard cannot report on itself: adding a seventh
    component to `MatchComponent` and a seventh score column to `match_results`
    without extending `COMPONENT_SCORE_COLUMNS` produces a component that can be
    scored with no evidence and no error, forever. `PROFILE_COLUMNS` stopped
    describing what it named at M3b in precisely this way.
    """
    import importlib

    from nightshift.db.base import MatchComponent
    from nightshift.db.models import MatchResult

    migration = importlib.import_module("migrations.versions.20260809_1607_match_results")
    pairs = dict(migration.COMPONENT_SCORE_COLUMNS)

    assert set(pairs) == {m.value for m in MatchComponent}
    columns = set(MatchResult.__table__.columns.keys())
    assert set(pairs.values()) <= columns, sorted(set(pairs.values()) - columns)
