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
from nightshift.domain.queue import QueueSectionKey

SCHEMAS_TS = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "lib" / "schemas.ts"

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
