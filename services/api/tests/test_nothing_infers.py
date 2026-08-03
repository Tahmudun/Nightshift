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

ROOT = Path(__file__).resolve().parents[1] / "nightshift"
WRITER = ROOT / "domain" / "profile.py"
MODELS = ROOT / "db" / "models.py"

#: The columns that hold a confirmed claim about a person.
PROFILE_COLUMNS = (
    "graduation_year",
    "graduation_month",
    "degree",
    "school",
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


def test_the_extractor_does_not_call_back_into_the_writer() -> None:
    """`profile.py` may call the extractor; the extractor may not call back."""
    extractor = (ROOT / "domain" / "resume_extraction.py").read_text(encoding="utf-8")
    assert "profile" not in extractor
