"""The committed match weights, and the version stored on every score.

``matching.md`` §4.2 and §5.1. Two files decide what a score is: this module's
rule logic version and ``data/matching.yaml``'s numbers. The value written to
``match_results.ruleset_version`` composes both, because M3's acceptance
criterion is *identical inputs + identical ruleset_version → identical output*
and one version covering only half of the inputs cannot carry that.

Nothing here scores anything. It loads six numbers, refuses a file that would
score dishonestly, and says what version the pair of them is.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

# `parents[4]`, matching `skill_vocabulary.py`. `parents[3]` is `services/` and
# the resulting path resolves to nothing — a crash in the best case and a
# silently empty file in the worst.
DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parents[4] / "data" / "matching.yaml"

#: The rule logic's own version, bumped whenever a scoring rule changes shape —
#: a different comparison, a different curve, a component computed from
#: something else. The weights file carries the numbers; this carries what is
#: done with them, and §4.2 composes the two.
#:
#: **What keeps this constant honest is the golden test, not discipline.**
#: Changing a rule without bumping it turns that test red with a diff showing
#: exactly what moved, which is the moment to bump. A developer remembering is
#: the version of this that fails silently.
RULESET_LOGIC_VERSION = "1"

#: The six components, in the order §5.1 lists them. Named here rather than read
#: from the file: a component the code has never heard of must be a load error,
#: not a silently ignored key, and a component the code expects and the file
#: omits must be the same. A weights file is small enough to be exhaustive
#: about, and a score is not a place to be permissive.
COMPONENT_NAMES = (
    "role_relevance",
    "skill_overlap",
    "project_evidence",
    "location_and_work_mode",
    "listing_freshness",
    "early_career_priority",
)

#: The two penalties §5.1 keeps. Ceilings; the curves are rule logic.
PENALTY_NAMES = ("missing_requirement", "seniority_mismatch")

#: What the six weights must sum to. Not a normalisation factor — nothing is
#: divided by it. It is an assertion that the file describes a score out of 100,
#: which is what the UI, the bands and every explanation assume it is.
WEIGHT_TOTAL = 100


class WeightsError(ValueError):
    """A weights file that would produce a dishonest score. Raised on load."""


#: Rule thresholds, as `<group>.<name>`. §4.2 puts every threshold in the data
#: file beside the weights, because a number that moves a score has to be a
#: traceable data change carrying the version stored on every row.
#:
#: Named exhaustively for the same reason the components are: a threshold the
#: code has never heard of must be a load error rather than a silently ignored
#: key, and one the code expects and the file omits must be the same.
#: `db.base.Seniority`'s members, in order, lowest level first. Duplicated here
#: rather than imported so this loader stays free of the ORM module, and kept
#: honest by `test_the_seniority_ladder_names_every_level_the_classifier_can_produce`
#: — which compares it against the enum itself.
SENIORITY_LADDER = (
    "internship",
    "new_grad",
    "junior",
    "mid",
    "senior",
    "staff",
    "director",
)

THRESHOLD_NAMES = (
    "freshness_days.full",
    "freshness_days.zero",
    "missing_requirement.per_requirement",
    "seniority_mismatch.per_year",
    *(f"seniority_years.{level}" for level in SENIORITY_LADDER),
)

#: Thresholds that are a *cost per unit*. Zero is the interesting failure: it is
#: a valid whole number, it loads, and it turns the rule that reads it off for
#: every posting in the corpus — which then reads as "nothing was penalised"
#: rather than as "this rule stopped running".
_PER_UNIT_THRESHOLDS = ("missing_requirement.per_requirement", "seniority_mismatch.per_year")


@dataclass(frozen=True, slots=True)
class MatchingWeights:
    version: str
    components: dict[str, int]
    penalties: dict[str, int]
    thresholds: dict[str, int]

    @property
    def ruleset_version(self) -> str:
        """``"<logic>+<data>"`` — the value stored on every ``match_results`` row."""
        return f"{RULESET_LOGIC_VERSION}+{self.version}"

    def weight(self, component: str) -> int:
        return self.components[component]

    def ceiling(self, penalty: str) -> int:
        return self.penalties[penalty]

    def threshold(self, name: str) -> int:
        return self.thresholds[name]


def _whole_number(value: Any, *, where: str) -> int:
    # `isinstance(True, int)` is True in Python, and a weight of `true` reading
    # as 1 is exactly the kind of quiet nonsense this loader exists to refuse.
    if isinstance(value, bool) or not isinstance(value, int):
        raise WeightsError(f"{where} must be a whole number, not {value!r}")
    return value


def parse_weights(raw: Any) -> MatchingWeights:
    """Build weights from already-loaded YAML. Raises on anything questionable.

    Every check here exists because its absence is silent. A missing component
    is a component scoring zero for every job in the corpus; an extra one is a
    weight somebody wrote and nothing reads; a positive penalty adds points for
    a mismatch. None of those fail a test that does not look for them, because
    the output is still a plausible number.
    """
    if not isinstance(raw, dict):
        raise WeightsError(f"the weights file must be a mapping, not {type(raw).__name__}")

    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise WeightsError(f"version must be a non-empty string, not {version!r}")

    components = raw.get("components")
    if not isinstance(components, dict):
        raise WeightsError("components must be a mapping of the six component names")
    missing = [name for name in COMPONENT_NAMES if name not in components]
    unknown = [name for name in components if name not in COMPONENT_NAMES]
    if missing or unknown:
        raise WeightsError(f"components: missing {missing}, unknown {unknown}")

    weights = {
        name: _whole_number(components[name], where=f"components.{name}")
        for name in COMPONENT_NAMES
    }
    for name, value in weights.items():
        if value < 0:
            raise WeightsError(f"components.{name} is negative ({value}); penalties are separate")
        # **At least 1, not merely non-negative**, and the sum-to-100 assertion
        # below does not cover it: `role_relevance: 0` beside `skill_overlap: 50`
        # totals 100 and passes, while removing role relevance from every score in
        # the corpus — which is the silent removal `data/matching.yaml`'s own
        # header claims is caught.
        #
        # It is also what `match_results_components_are_assessed` rests on. That
        # trigger asserts `assessed_out_of = 100` exactly when every component was
        # assessable, which is only true while an unassessable component
        # necessarily narrows the denominator. A zero weight would make a legal
        # weights file produce scores the database refuses, with the error naming
        # the row rather than the file.
        if value == 0:
            raise WeightsError(
                f"components.{name} is 0; a component worth nothing is a component "
                "that does not exist — delete it and renormalise, rather than "
                "leaving a score with a part that can never contribute"
            )
    total = sum(weights.values())
    if total != WEIGHT_TOTAL:
        breakdown = ", ".join(f"{name}={weights[name]}" for name in COMPONENT_NAMES)
        raise WeightsError(f"the six components sum to {total}, not {WEIGHT_TOTAL} — {breakdown}")

    penalties_raw = raw.get("penalties")
    if not isinstance(penalties_raw, dict):
        raise WeightsError("penalties must be a mapping of the two penalty names")
    missing = [name for name in PENALTY_NAMES if name not in penalties_raw]
    unknown = [name for name in penalties_raw if name not in PENALTY_NAMES]
    if missing or unknown:
        raise WeightsError(f"penalties: missing {missing}, unknown {unknown}")

    penalties = {
        name: _whole_number(penalties_raw[name], where=f"penalties.{name}")
        for name in PENALTY_NAMES
    }
    for name, value in penalties.items():
        if value >= 0:
            raise WeightsError(
                f"penalties.{name} is {value}; a penalty ceiling must be negative, "
                "or the score adds points for a mismatch"
            )

    return MatchingWeights(
        version=version,
        components=weights,
        penalties=penalties,
        thresholds=_parse_thresholds(raw.get("thresholds")),
    )


def _parse_thresholds(raw: Any) -> dict[str, int]:
    """Flatten `freshness_days: {full: 7}` to `{"freshness_days.full": 7}`.

    Flat because the names are checked exhaustively and a nested lookup that
    silently returns `None` for a missing group is the failure this whole loader
    exists to make loud.
    """
    if not isinstance(raw, dict):
        raise WeightsError("thresholds must be a mapping of threshold groups")

    flat: dict[str, int] = {}
    for group, entries in raw.items():
        if not isinstance(entries, dict):
            raise WeightsError(
                f"thresholds.{group} must be a mapping, not {type(entries).__name__}"
            )
        for name, value in entries.items():
            flat[f"{group}.{name}"] = _whole_number(value, where=f"thresholds.{group}.{name}")

    missing = [name for name in THRESHOLD_NAMES if name not in flat]
    unknown = [name for name in flat if name not in THRESHOLD_NAMES]
    if missing or unknown:
        raise WeightsError(f"thresholds: missing {missing}, unknown {unknown}")

    # A freshness window that runs backwards would score an ancient posting
    # above a new one, silently and with no error anywhere.
    if flat["freshness_days.full"] >= flat["freshness_days.zero"]:
        raise WeightsError(
            f"freshness_days.full ({flat['freshness_days.full']}) must be below "
            f"freshness_days.zero ({flat['freshness_days.zero']}), or freshness runs backwards"
        )
    for name, value in flat.items():
        if value < 0:
            raise WeightsError(
                f"thresholds.{name} is negative ({value}); days do not run backwards"
            )

    for name in _PER_UNIT_THRESHOLDS:
        if flat[name] == 0:
            raise WeightsError(
                f"thresholds.{name} is 0, which switches its penalty off for every "
                "posting in the corpus without switching anything else"
            )

    _check_the_ladder_rises(flat)
    return flat


def _check_the_ladder_rises(flat: dict[str, int]) -> None:
    """A seniority ladder that falls, or never climbs, is a silent penalty bug.

    Neither shape raises anything on its own. A falling rung inverts the
    penalty — a Lead posting costs an early-career profile less than a Junior
    one — and a flat ladder makes every gap zero, which is the rule deleted in
    data while every test that does not read this file stays green.
    """
    rungs = [(level, flat[f"seniority_years.{level}"]) for level in SENIORITY_LADDER]
    for (lower, below), (higher, above) in pairwise(rungs):
        if above < below:
            raise WeightsError(
                f"seniority_years does not rise: {higher} implies {above} years and "
                f"{lower} implies {below}, so the penalty runs backwards"
            )
    if rungs[0][1] == rungs[-1][1]:
        raise WeightsError(
            f"seniority_years never rises: every level implies {rungs[0][1]} years, "
            "which is the seniority penalty switched off in data"
        )


@lru_cache(maxsize=4)
def load_weights(path: Path | None = None) -> MatchingWeights:
    """Cached: the file is source data and does not change inside a process."""
    resolved = path or DEFAULT_WEIGHTS_PATH
    return parse_weights(yaml.safe_load(resolved.read_text(encoding="utf-8")))


def ruleset_version() -> str:
    """The composed version for the committed weights file."""
    return load_weights().ruleset_version
