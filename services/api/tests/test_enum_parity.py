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
    CaptureStatus,
    EligibilityState,
    EmploymentType,
    EvidenceSource,
    ExtractionKind,
    ExtractionStatus,
    InternshipSeason,
    JobStatus,
    JobTextField,
    LocationConfidence,
    MatchComponent,
    PenaltyName,
    ProficiencyLevel,
    ProjectStatus,
    RemotePolicy,
    RemotePreference,
    RequirementKind,
    RequirementNecessity,
    ResolutionMethod,
    ResumeSourceKind,
    ResumeVariant,
    RoleFamily,
    Seniority,
    SkillSourceType,
    SourceType,
    TransitionClass,
    WorkAuthorization,
)
from nightshift.domain.eligibility import _ASKS_FOR
from nightshift.domain.placement import PlacementKind
from nightshift.domain.queue import QueueSectionKey

SCHEMAS_TS = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "schemas.ts"
CITY_ROUTES_PY = Path(__file__).resolve().parents[1] / "nightshift" / "api" / "routes" / "city.py"
BEACON_TS = (
    Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "city" / "beacon.ts"
)
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
    # M3c Task 10. All four crossed the boundary for the first time when the
    # score reached a page — Task 9 put three of them in the response and left
    # this half deliberately undone, because there was nothing in the browser to
    # compare against until a component rendered one.
    #
    # `jobTextFieldSchema` is the sharpest of the four. It selects which of the
    # posting's strings a span's offsets index into, so a wrong value does not
    # blank a field: it underlines the wrong sentence, in the right place, and
    # looks entirely plausible doing it.
    ("matchComponentSchema", MatchComponent),
    ("jobTextFieldSchema", JobTextField),
    ("evidenceSourceSchema", EvidenceSource),
    ("penaltyNameSchema", PenaltyName),
    # M4c Task 1, and the five oldest enums in the product — they have crossed
    # this boundary since M0 and none of them was guarded here.
    #
    # `resolutionMethodSchema` had already drifted, and had been wrong since
    # M4a: `ResolutionMethod` gained `company_office` when `company_locations`
    # arrived and the browser's copy did not. Nothing failed, because nothing
    # had ever sent the value — `/city/signals` is the first endpoint that
    # emits it, and it would have met a Zod refusal to parse the page. Exactly
    # the failure the docstring above describes, sitting latent for a milestone
    # because these five were not in this list.
    ("locationConfidenceSchema", LocationConfidence),
    ("resolutionMethodSchema", ResolutionMethod),
    ("jobStatusSchema", JobStatus),
    ("employmentTypeSchema", EmploymentType),
    ("remotePolicySchema", RemotePolicy),
    # M4c Task 1. Not a database enum: the renderer branches on this and
    # nothing else, so a value it does not know is a beacon that does not draw.
    ("placementKindSchema", PlacementKind),
    # M5a. Added in the same commit as the enum rather than a milestone later,
    # which every comment above this line is a record of not doing.
    ("captureStatusSchema", CaptureStatus),
)


def _typescript_enum(name: str) -> set[str]:
    """The string literals inside `export const <name> = z.enum([...])`.

    Line comments are stripped first, and that is not tidiness. An English
    apostrophe inside a `//` comment — "its employer's office" — opens a quoted
    region as far as this regex is concerned, and everything up to the next
    apostrophe becomes a phantom enum member. It happened on the first comment
    written inside one of these blocks, and the failure named the enum rather
    than the apostrophe, which is a bad hour waiting to happen twice.
    """
    source = SCHEMAS_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {re.escape(name)} = z\.enum\(\[(.*?)\]\)", source, re.DOTALL)
    assert match is not None, f"{name} is not declared as a z.enum in schemas.ts"
    body = re.sub(r"//[^\n]*", "", match.group(1))
    return set(re.findall(r"'([^']*)'", body))


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


def test_the_penalty_migration_creates_exactly_the_type_the_model_declares() -> None:
    """`penalty_name`, against its copy inside `0019_match_penalties`.

    A fifth enum with a fifth copy. This one closes the domain of a column the
    guard counts rows over: `match_penalties` asserts *exactly one row per name*,
    and a count is only an assertion when nothing else can be written there. A
    typo'd `seniority_missmatch` beside a correct one is two rows, two names, and
    a guard that passes.
    """
    import importlib

    from nightshift.db.base import PenaltyName

    migration = importlib.import_module("migrations.versions.20260810_0100_match_penalties")

    assert set(migration.PENALTY_NAME_VALUES) == {m.value for m in PenaltyName}


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


def test_the_browser_allocates_room_for_every_signal_the_api_can_send() -> None:
    """`MAX_BEACONS` against `MAX_SIGNALS`, which is the same boundary as the
    enums above and fails more quietly than any of them.

    The instance buffer is allocated once at `MAX_BEACONS` and `setSignals`
    clamps to it with a `Math.min`. If the API's ceiling is ever raised past the
    renderer's — a one-line change on the Python side, made for a good reason,
    with every test in both suites still green — the extra roles are dropped on
    the floor. Nothing throws, no count on the page disagrees with itself, and
    the `truncated` banner stays off because the *API* did not truncate. The
    city simply stops drawing some of the corpus.

    `beacon.ts` already claims the two match, in a comment. This is the claim
    with something behind it.
    """
    signals = re.search(
        r"^MAX_SIGNALS = ([\d_]+)", CITY_ROUTES_PY.read_text(encoding="utf-8"), re.M
    )
    beacons = re.search(
        r"^export const MAX_BEACONS = ([\d_]+);", BEACON_TS.read_text(encoding="utf-8"), re.M
    )
    assert signals is not None, "MAX_SIGNALS is no longer a module-level literal in city.py"
    assert beacons is not None, "MAX_BEACONS is no longer a module-level literal in beacon.ts"

    assert int(beacons.group(1).replace("_", "")) >= int(signals.group(1).replace("_", "")), (
        "the API can return more signals than the renderer has room for, and the "
        "surplus is dropped silently — raise MAX_BEACONS or lower MAX_SIGNALS"
    )


def test_the_capture_source_name_matches_the_browsers_copy() -> None:
    """Not an enum, and it drifts exactly like one.

    `JobDetail` renders the "added by hand" badge by comparing a source's name
    against this string. A mismatch raises nothing, breaks no type, and fails
    no other test — the badge simply stops appearing, and a captured posting
    becomes indistinguishable from a polled one. That is invariant I7 failing
    silently, which is the failure mode this whole file exists for.
    """
    from nightshift.domain.capture import CAPTURE_SOURCE_NAME

    source = SCHEMAS_TS.read_text(encoding="utf-8")
    match = re.search(r"export const CAPTURE_SOURCE_NAME = '([^']+)'", source)
    assert match is not None, "CAPTURE_SOURCE_NAME is not exported from schemas.ts"
    assert match.group(1) == CAPTURE_SOURCE_NAME


def test_the_capture_source_type_matches_the_browsers_copy() -> None:
    """The other half, and it is a separate string for a reason.

    `SourceHealthTable` labels a row by its `source_type`, not by its name, and
    `sourceHealthSchema` types that field as a bare `z.string()` — so nothing
    in the parity above covers it and nothing in Zod would refuse a wrong
    value. A drift here puts a captured posting in the source health table
    labelled **live**, which is the word the table gives a board we poll every
    hour, about the one source nothing ever reads twice.
    """
    source = SCHEMAS_TS.read_text(encoding="utf-8")
    match = re.search(r"export const CAPTURE_SOURCE_TYPE = '([^']+)'", source)
    assert match is not None, "CAPTURE_SOURCE_TYPE is not exported from schemas.ts"
    assert match.group(1) == SourceType.MANUAL_CAPTURE.value
