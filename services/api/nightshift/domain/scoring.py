"""The score: six components, two penalties, and the total they compose into.

`matching.md` §2.1 and §5.1. Role relevance, skill overlap and project evidence
are the three components that assert something about somebody's qualifications,
which is what invariant I2 governs, and each one must trace to **two quotable
strings**: a span in the posting, and a span in the person's own confirmed data.
A component that cannot produce both produces nothing — no points, no evidence
row, no line in the explanation.

Pure, and importing no ORM, exactly as `eligibility.py` is and for the same
reason: this is the thing M3d has to grade against 60 postings in a test, and
`test_every_component_is_load_bearing` has to be able to zero a weight and
re-run. A scorer that reads a session cannot be mutation-tested that way.

Each component returns its own points, its own evidence, and **whether it could
be assessed at all**; `compose_score` sums them and records what the sum is out
of. The reason that denominator is not always 100 is §2 below, and it is the
single fact that shapes the most of this module.

## Why a component says "not assessable" instead of scoring zero

Measured on the committed answer key, 2026-08-09: **26 of the 60 labeled
postings name no required technology at all**, and 16 of those name no
technology of any kind. That is the human's own labels, not the extractor
missing them — it is a fact about how employers write, and it is 43% of the
corpus.

A skill-overlap component that scores 0 when a posting requires no technologies
removes 30 of 100 points from 43% of the corpus for a reason that has nothing to
do with the person being scored. That is precisely the argument §5.1 used to
defer application urgency — *"that measures an employer's ATS configuration, not
urgency"* — with a bigger number behind it.

The dishonest fix is to award the points anyway, and it is worth naming that the
database already refuses it: a positive component score with no evidence row
cannot be committed (`match_results_component_needs_evidence`). So the choice is
between scoring zero and saying the component could not be assessed, and this
module says the latter.

What a *total* should then do with an unassessable component was QUESTIONS Q6,
and the answer decided on 2026-08-09 is **the total is out of what could be
assessed** (§5.1.1). A posting naming no technologies is scored out of 50, the
page names the two components that could not be assessed and why, and the ranked
list sorts on the fraction rather than on the raw total. The alternative — always
out of 100, with the gaps shown — systematically ranks terse postings below
verbose ones, and redistributing the missing weight would silently make location
and freshness worth 50 points between them, which nobody chose.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from nightshift.db.base import (
    EvidenceSource,
    JobTextField,
    MatchComponent,
    RoleFamily,
    Seniority,
)
from nightshift.domain.matching_weights import MatchingWeights
from nightshift.domain.requirement_extraction import RequirementProposal
from nightshift.domain.role_classification import TextSpan

#: Bumped when any rule below changes shape. Composed onto every stored score by
#: `matching_weights.ruleset_version()`, and what keeps it honest is Task 6's
#: golden test rather than anyone remembering.
SCORING_VERSION = "m3c.1"


@dataclass(frozen=True)
class ConfirmedSkill:
    """One row of `user_skills`. Confirmed, never a proposal (I2)."""

    name: str
    #: `user_skills.skill_id` — the taxonomy's canonical name, or `None` for a
    #: skill the person typed that the vocabulary does not carry. A `None` here
    #: can never match a requirement, and that is the point: resolving it to a
    #: neighbour would fabricate a qualification.
    taxonomy_id: str | None = None
    user_skill_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ConfirmedProject:
    """One row of `user_projects`. `evidence` is the text the claim quotes."""

    name: str
    technologies: tuple[str, ...] = ()
    #: The literal bullets. `matching.md` §4.3 requires a user-side span, and
    #: this is the only text on a project long enough to contain one.
    evidence: str | None = None
    user_project_id: uuid.UUID | None = None


@dataclass(frozen=True)
class JobLocationForScoring:
    """One row of `job_locations`. No coordinates — those are M4 (§9)."""

    city: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class ScoringProfile:
    """Only confirmed facts, same rule as `eligibility.SeekerProfile`."""

    skills: tuple[ConfirmedSkill, ...] = ()
    projects: tuple[ConfirmedProject, ...] = ()
    #: `users.preferred_roles`, as the person typed them.
    preferred_roles: tuple[str, ...] = ()
    #: `users.preferred_locations`, likewise.
    preferred_locations: tuple[str, ...] = ()
    #: `users.remote_preference`. `"no_preference"` means the person expressed
    #: none, which is why that value makes the dimension unassessable rather
    #: than making everything match.
    remote_preference: str | None = None
    #: `users.years_experience`, as the person entered it. Read by the seniority
    #: penalty and by nothing else here. **`None` is not zero** — it is "not
    #: told", and the penalty declines to fire rather than charging every silent
    #: profile the full amount against every senior posting in the corpus.
    years_experience: int | None = None


@dataclass(frozen=True)
class PostingForScoring:
    """What the score reads. Assembled by the caller; nothing here queries."""

    title: str
    description_text: str
    role_family: RoleFamily | None = None
    #: The span behind `role_family`, from the classifier. `None` when no rule
    #: matched, which is `unclear`.
    role_family_span: TextSpan | None = None
    seniority: Seniority | None = None
    requirements: tuple[RequirementProposal, ...] = ()
    locations: tuple[JobLocationForScoring, ...] = ()
    #: `jobs.remote_policy`, as the source stated it. `"unknown"` is the source
    #: not saying and is never read as a mismatch (A10).
    remote_policy: str | None = None
    #: `jobs.source_published_at` — a real publication date on all three
    #: adapters, and the only date in this system measuring the *posting* rather
    #: than this system's own polling.
    source_published_at: date | None = None


@dataclass(frozen=True)
class Evidence:
    """One row destined for `match_evidence`, before it meets a database.

    Mirrors that table's columns rather than inventing a second vocabulary, so
    persisting it at Task 8 is a field copy and not a translation — which is
    where the two-vocabulary defect M3a.1 found in `score_sets` came from.
    """

    component: MatchComponent
    points: int
    job_span_text: str | None = None
    #: Which of the posting's strings the offsets index into. Every span in the
    #: rest of this system points at `description_text`; role relevance is
    #: decided on the title, so it cannot.
    job_span_field: JobTextField | None = None
    job_char_start: int | None = None
    job_char_end: int | None = None
    user_span_text: str | None = None
    user_skill_id: uuid.UUID | None = None
    user_project_id: uuid.UUID | None = None
    compared: dict[str, Any] = field(default_factory=dict)
    proposed_by: EvidenceSource = EvidenceSource.RULE
    #: The requirement this answers, when there is one. Task 11's embedding
    #: proposals point at spans that are no requirement row at all.
    requirement: RequirementProposal | None = None


@dataclass(frozen=True)
class ComponentScore:
    """One component's contribution, and whether it could be assessed.

    `assessable is False` always means `points == 0`, and the two are not the
    same statement. Zero means *this person does not match*; unassessable means
    *the posting does not say enough to ask the question*. Collapsing them is
    how a terse posting becomes a bad match.
    """

    component: MatchComponent
    points: int
    assessable: bool
    why: str
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.assessable and self.points:
            raise ValueError(
                f"{self.component} is not assessable and scored {self.points}; "
                "points with nothing behind them is what I4 forbids"
            )
        if self.points and not self.evidence:
            # The database refuses this at commit. Refusing it here too means a
            # unit test sees it without needing Postgres.
            raise ValueError(f"{self.component} scored {self.points} with no evidence row")


@dataclass(frozen=True)
class Penalty:
    """One subtraction, and whether it applied at all.

    Not a `ComponentScore`, and the difference is structural rather than
    stylistic: `MatchComponent` has no penalty member, so a penalty has no
    `match_evidence` row to point at and `match_results.penalty_score` stores
    the two as one column (§4.2). What each penalty cost is carried here, is
    rendered by the explanation, and is never a row in the evidence graph.

    `applicable is False` always means `points == 0`, the same distinction
    `ComponentScore.assessable` draws: zero means *nothing was missing*,
    inapplicable means *there was nothing to ask*.
    """

    name: str
    points: int
    applicable: bool
    why: str
    compared: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.points > 0:
            raise ValueError(
                f"{self.name} scored {self.points}; a penalty never adds points, "
                "or the arithmetic says the opposite of the word"
            )
        if not self.applicable and self.points:
            raise ValueError(f"{self.name} did not apply and still cost {self.points}")


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def _required_technologies(posting: PostingForScoring) -> list[RequirementProposal]:
    """Only `required`. `preferred` and `mentioned` are §4.1's whole point."""
    return [r for r in posting.requirements if r.kind == "technology" and r.necessity == "required"]


# ---------------------------------------------------------------------------
# Skill overlap — 0-30
# ---------------------------------------------------------------------------


def _skill_index(profile: ScoringProfile) -> dict[str, ConfirmedSkill]:
    """Confirmed skills by the string a requirement could match.

    Both the taxonomy id and the casefolded name are keys. The taxonomy id is
    the reliable one — it is the same string `job_requirements.value` carries —
    and the name is the fallback for a skill confirmed before the taxonomy
    column existed or typed outside the vocabulary.
    """
    index: dict[str, ConfirmedSkill] = {}
    for skill in profile.skills:
        index.setdefault(_normalize(skill.name), skill)
        if skill.taxonomy_id:
            index.setdefault(_normalize(skill.taxonomy_id), skill)
    return index


def score_skill_overlap(
    posting: PostingForScoring, profile: ScoringProfile, *, weight: int
) -> ComponentScore:
    """What fraction of what the posting *requires* this person has confirmed.

    Only `necessity == "required"` counts toward the fraction. `preferred` and
    `mentioned` are deliberately worth nothing here, and it is not an oversight:
    §4.1 calls necessity "the column the product turns on", and Ramp's Android
    internship lists nine technologies under *nice to haves*. Scoring those would
    reward a posting for listing more things.

    A matched preferred technology still produces an evidence row worth zero
    points, because the explanation panel needs it to say "you also have this"
    without claiming it earned anything.
    """
    required = _required_technologies(posting)
    if not required:
        return ComponentScore(
            component=MatchComponent.SKILL,
            points=0,
            assessable=False,
            why="this posting names no required technologies",
        )

    index = _skill_index(profile)
    rows: list[Evidence] = []
    matched = 0
    for requirement in required:
        skill = index.get(_normalize(requirement.value))
        if skill is None:
            continue
        matched += 1
        rows.append(
            Evidence(
                component=MatchComponent.SKILL,
                # Filled in below, once the fraction is known. Points per row
                # are the component's points shared out, not a second scale.
                points=0,
                job_span_text=requirement.raw_text,
                job_span_field=JobTextField.DESCRIPTION_TEXT,
                job_char_start=requirement.char_start,
                job_char_end=requirement.char_end,
                user_span_text=skill.name,
                user_skill_id=skill.user_skill_id,
                compared={"requirement": requirement.value, "confirmed_as": skill.name},
                requirement=requirement,
            )
        )

    points = round(weight * matched / len(required))
    if not rows:
        return ComponentScore(
            component=MatchComponent.SKILL,
            points=0,
            assessable=True,
            why=f"none of the {len(required)} required technologies is confirmed on this profile",
        )

    rows = _share_out(points, rows)
    return ComponentScore(
        component=MatchComponent.SKILL,
        points=points,
        assessable=True,
        why=f"{matched} of {len(required)} required technologies confirmed",
        evidence=tuple(rows),
    )


def _share_out(points: int, rows: list[Evidence]) -> list[Evidence]:
    """Split a component's points across its evidence rows, losing none.

    Integer division drops the remainder, and a breakdown that does not add up
    to its own total is the small version of the defect I4 exists to prevent —
    so the remainder goes to the earliest rows one point at a time rather than
    being rounded away.
    """
    if not rows:
        return rows
    base, remainder = divmod(points, len(rows))
    return [replace(row, points=base + (1 if i < remainder else 0)) for i, row in enumerate(rows)]


# ---------------------------------------------------------------------------
# Role relevance — 0-20
# ---------------------------------------------------------------------------

#: A preferred role a person types is free text — "backend engineer", "data
#: eng", "ML". These map that text onto the families the classifier produces, so
#: the two sides are comparable without either being re-typed to match the
#: other. Ordered longest-phrase-first at match time for the same reason
#: `skill_vocabulary` sorts its terms: "data engineer" must beat "engineer".
_ROLE_WORDS: tuple[tuple[RoleFamily, tuple[str, ...]], ...] = (
    (RoleFamily.DATA_ENGINEERING, ("data engineer", "data engineering", "data platform")),
    (RoleFamily.ML_AI, ("machine learning", "ml engineer", "ai engineer", "deep learning")),
    (RoleFamily.INFRASTRUCTURE, ("infrastructure", "platform engineer", "sre", "devops")),
    (RoleFamily.SECURITY, ("security", "appsec", "cryptography")),
    (RoleFamily.QUANT_TRADING, ("quant", "quantitative", "trader", "trading")),
    (RoleFamily.HARDWARE, ("hardware", "fpga", "asic")),
    (RoleFamily.DESIGN, ("design", "designer")),
    (RoleFamily.PRODUCT, ("product manager", "product management")),
    (
        RoleFamily.SOFTWARE_ENGINEERING,
        ("software engineer", "backend", "back end", "frontend", "front end", "full stack", "swe"),
    ),
)


def families_wanted(preferred_roles: tuple[str, ...]) -> dict[RoleFamily, str]:
    """Families the person asked for, each keyed to the words they typed.

    The typed words are kept because they are the user-side span §2.1 requires.
    A family with no words behind it could not be quoted and so could not score.
    """
    wanted: dict[RoleFamily, str] = {}
    for typed in preferred_roles:
        haystack = _normalize(typed)
        for family, phrases in _ROLE_WORDS:
            for phrase in phrases:
                if re.search(rf"(?<![0-9a-z]){re.escape(phrase)}(?![0-9a-z])", haystack):
                    wanted.setdefault(family, typed)
                    break
    return wanted


def score_role_relevance(
    posting: PostingForScoring, profile: ScoringProfile, *, weight: int
) -> ComponentScore:
    """Full marks when the posting's family is one the person asked for.

    Deliberately not a similarity: either a stated preference names this family
    or it does not. A graded distance between families would be a number nobody
    could argue with, which is what §2.2 rejects embedding-first ranking for.

    Both sides must be quotable. The posting's side is the phrase the classifier
    matched — carried on the classification since Task 3, rather than recovered
    by parsing `family_reason` back apart — and the person's side is the text
    they typed into `preferred_roles`.
    """
    if not profile.preferred_roles:
        return ComponentScore(
            component=MatchComponent.ROLE,
            points=0,
            assessable=False,
            why="this profile states no preferred roles",
        )
    if posting.role_family is None or posting.role_family is RoleFamily.UNCLEAR:
        return ComponentScore(
            component=MatchComponent.ROLE,
            points=0,
            assessable=False,
            why="no rule could tell what kind of role this posting is",
        )
    if posting.role_family_span is None:
        # A family with no span cannot be quoted, and §2.1 makes a claim about a
        # person with nothing quoted behind it unrepresentable.
        return ComponentScore(
            component=MatchComponent.ROLE,
            points=0,
            assessable=False,
            why="the posting's role family has no quotable span",
        )

    wanted = families_wanted(profile.preferred_roles)
    typed = wanted.get(posting.role_family)
    if typed is None:
        return ComponentScore(
            component=MatchComponent.ROLE,
            points=0,
            assessable=True,
            why=f"this is a {posting.role_family} role and none of the stated preferences names it",
        )

    span = posting.role_family_span
    return ComponentScore(
        component=MatchComponent.ROLE,
        points=weight,
        assessable=True,
        why=f"this is a {posting.role_family} role and the profile asks for one",
        evidence=(
            Evidence(
                component=MatchComponent.ROLE,
                points=weight,
                job_span_text=span.text,
                job_span_field=span.field,
                job_char_start=span.char_start,
                job_char_end=span.char_end,
                user_span_text=typed,
                compared={"role_family": str(posting.role_family), "preferred_role": typed},
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Project evidence — 0-20
# ---------------------------------------------------------------------------


def score_project_evidence(
    posting: PostingForScoring, profile: ScoringProfile, *, weight: int
) -> ComponentScore:
    """Required technologies a project demonstrates, quoted from its own bullets.

    Distinct from skill overlap on purpose: a confirmed skill is somebody saying
    they know a thing, and a project is somebody having built one with it. The
    same technology can score in both, and that is not double-counting — they
    are two different claims with two different pieces of evidence.

    The user-side span is the words in the project's `evidence` text, so the
    explanation can show the bullet rather than the project's name. A project
    listing a technology with no bullet mentioning it produces **no row**: there
    would be nothing on the person's side to quote, and §2.1 does not allow the
    name of the project to stand in for it.
    """
    required = _required_technologies(posting)
    if not required:
        return ComponentScore(
            component=MatchComponent.PROJECT,
            points=0,
            assessable=False,
            why="this posting names no required technologies",
        )
    if not profile.projects:
        return ComponentScore(
            component=MatchComponent.PROJECT,
            points=0,
            assessable=False,
            why="this profile records no projects",
        )

    rows: list[Evidence] = []
    demonstrated: set[str] = set()
    for requirement in required:
        wanted = _normalize(requirement.value)
        for project in profile.projects:
            if wanted not in {_normalize(t) for t in project.technologies}:
                continue
            quoted = _quote_from(project.evidence, requirement.value)
            if quoted is None:
                continue
            demonstrated.add(wanted)
            rows.append(
                Evidence(
                    component=MatchComponent.PROJECT,
                    points=0,
                    job_span_text=requirement.raw_text,
                    job_span_field=JobTextField.DESCRIPTION_TEXT,
                    job_char_start=requirement.char_start,
                    job_char_end=requirement.char_end,
                    user_span_text=quoted,
                    user_project_id=project.user_project_id,
                    compared={"requirement": requirement.value, "project": project.name},
                    requirement=requirement,
                )
            )
            break

    if not rows:
        return ComponentScore(
            component=MatchComponent.PROJECT,
            points=0,
            assessable=True,
            why=f"no project demonstrates any of the {len(required)} required technologies",
        )

    points = round(weight * len(demonstrated) / len(required))
    rows = _share_out(points, rows)
    return ComponentScore(
        component=MatchComponent.PROJECT,
        points=points,
        assessable=True,
        why=f"projects demonstrate {len(demonstrated)} of {len(required)} required technologies",
        evidence=tuple(rows),
    )


def _quote_from(evidence: str | None, term: str) -> str | None:
    """The sentence in a project's bullets that names `term`, or `None`.

    Whole-word, and the same lookaround `skill_vocabulary._compile` uses rather
    than `\\b` — `\\bC++\\b` can never match, because there is no word boundary
    after a plus sign. A technology this system claims a project demonstrates
    has to appear in what the person wrote about it.
    """
    if not evidence:
        return None
    pattern = re.compile(rf"(?<![0-9A-Za-z_]){re.escape(term)}(?![0-9A-Za-z_])", re.IGNORECASE)
    match = pattern.search(evidence)
    if match is None:
        return None
    start = evidence.rfind(".", 0, match.start()) + 1
    end = evidence.find(".", match.end())
    end = len(evidence) if end == -1 else end + 1
    return evidence[start:end].strip() or None


# ---------------------------------------------------------------------------
# The three exempt components
#
# `matching.md` §2.1: location, freshness and priority make no claim about the
# person. Location compares a posting's own city and remote policy against a
# preference somebody typed; freshness is arithmetic on a date the source gave
# us; priority reads the posting's own seniority. There is no assertion about
# anybody's qualifications, so there is no user-side span to quote — and
# requiring one would mean inventing it.
#
# They are exempt from quoting, not from being inspectable. Every row records
# `compared`: the two values that were weighed, so the breakdown can be read
# back. `ck_match_evidence_only_a_person_claim_quotes_a_person` refuses a
# user-side span on any of them.
# ---------------------------------------------------------------------------


def score_location_and_work_mode(
    posting: PostingForScoring, profile: ScoringProfile, *, weight: int
) -> ComponentScore:
    """Scored on the dimensions the person actually stated, and no others.

    Two things can be compared — where the job is, and how it is worked — and a
    profile may state either, both or neither. The weight is split across the
    ones stated: somebody who named cities and no work-mode preference is scored
    entirely on cities, because scoring them on a preference they did not
    express would be inventing one and then marking them against it.

    A dimension the *posting* cannot answer is dropped rather than failed. A
    `remote_policy` of `unknown` is the source not saying, and A10's rule is
    that absence of data is data — it is not a mismatch.
    """
    stated_places = tuple(p for p in profile.preferred_locations if p.strip())
    wants_mode = (
        profile.remote_preference is not None and profile.remote_preference != "no_preference"
    )
    if not stated_places and not wants_mode:
        return ComponentScore(
            component=MatchComponent.LOCATION,
            points=0,
            assessable=False,
            why="this profile states no preferred locations and no work-mode preference",
        )

    dimensions: list[tuple[str, bool, dict[str, Any]]] = []
    if stated_places:
        cities = tuple(loc.city for loc in posting.locations if loc.city)
        if cities or posting.remote_policy == "remote":
            matched = _place_matches(stated_places, cities, posting.remote_policy)
            dimensions.append(
                ("place", matched, {"job_cities": list(cities), "preferred": list(stated_places)})
            )
    if wants_mode and posting.remote_policy and posting.remote_policy != "unknown":
        matched = posting.remote_policy == profile.remote_preference
        dimensions.append(
            (
                "work_mode",
                matched,
                {
                    "job_remote_policy": posting.remote_policy,
                    "preference": profile.remote_preference,
                },
            )
        )

    if not dimensions:
        return ComponentScore(
            component=MatchComponent.LOCATION,
            points=0,
            assessable=False,
            why="this posting states no location and no work-mode this profile asked about",
        )

    share = weight // len(dimensions)
    remainder = weight - share * len(dimensions)
    matched_rows: list[Evidence] = []
    unmatched_rows: list[Evidence] = []
    for index, (name, matched, compared) in enumerate(dimensions):
        points = share + (remainder if index == 0 else 0) if matched else 0
        row = Evidence(
            component=MatchComponent.LOCATION,
            points=points,
            compared={"dimension": name, **compared},
        )
        (matched_rows if matched else unmatched_rows).append(row)

    points = sum(row.points for row in matched_rows)
    return ComponentScore(
        component=MatchComponent.LOCATION,
        points=points,
        assessable=True,
        why=f"{len(matched_rows)} of {len(dimensions)} stated location preferences met",
        # Unmatched rows are kept: "you asked for hybrid and this is on-site" is
        # what the explanation panel needs, and a component that only records
        # its wins is not a breakdown.
        evidence=tuple(matched_rows + unmatched_rows),
    )


def _place_matches(
    stated: tuple[str, ...], cities: tuple[str, ...], remote_policy: str | None
) -> bool:
    normalized = {_normalize(city) for city in cities}
    for place in stated:
        wanted = _normalize(place)
        if wanted in normalized:
            return True
        # "remote" is a place people type into a locations field, and refusing
        # to read it there would mark a remote job against somebody who said
        # the only thing that could express what they wanted.
        if wanted == "remote" and remote_policy == "remote":
            return True
    return False


def score_listing_freshness(
    posting: PostingForScoring, *, weight: int, full_days: int, zero_days: int, as_of: date
) -> ComponentScore:
    """How long ago the **source** says this posting went up.

    Not `last_seen_at`, which `matching.md` §2.1 named and which measurement
    rejected: it records when this system last polled, so on an actively polled
    board it is near-now for every open job — one distinct day across 31 seeded
    jobs — and it would make a score depend on which poll tier ADR 0007 assigned
    the board. `source_published_at` is a real publication date on all three
    adapters and is present on 153 of 153 recorded postings.

    Linear between the two thresholds so no single day costs several points.
    Takes no `profile`: there is no person in this calculation at all, which is
    exactly why §2.1 exempts it from quoting one.
    """
    if posting.source_published_at is None:
        return ComponentScore(
            component=MatchComponent.FRESHNESS,
            points=0,
            assessable=False,
            why="this source gave no publication date",
        )

    age = (as_of - posting.source_published_at).days
    if age <= full_days:
        points = weight
    elif age >= zero_days:
        points = 0
    else:
        points = round(weight * (zero_days - age) / (zero_days - full_days))

    compared = {
        "published_on": posting.source_published_at.isoformat(),
        "age_days": age,
        "full_within_days": full_days,
        "zero_after_days": zero_days,
    }
    if not points:
        return ComponentScore(
            component=MatchComponent.FRESHNESS,
            points=0,
            assessable=True,
            why=f"published {age} days ago, past the {zero_days}-day window",
        )
    return ComponentScore(
        component=MatchComponent.FRESHNESS,
        points=points,
        assessable=True,
        why=f"published {age} days ago",
        evidence=(Evidence(component=MatchComponent.FRESHNESS, points=points, compared=compared),),
    )


#: The two levels §5.1 calls early-career. Read off the **posting**, never off
#: the person — see `score_early_career_priority`.
_EARLY_CAREER = (Seniority.INTERNSHIP, Seniority.NEW_GRAD)


def score_early_career_priority(posting: PostingForScoring, *, weight: int) -> ComponentScore:
    """Whether this posting is an internship or a new-grad role. That is all.

    **It reads the posting's own seniority and never the person's status**, which
    is `data/matching.yaml`'s own wording for this component and is what keeps it
    exempt from §2.1's span rule. The moment it consulted a graduation year it
    would be making a claim about somebody and would owe a user-side span.

    PRODUCT-SPEC §23 says the opposite — *"boost only when eligibility appears
    plausible"* and *"do not rank an internship highly if the graduation rules
    clearly exclude the user"*. That is overridden here and the precedence is
    CLAUDE.md's: `matching.md` §5.2 forbids eligibility from ever becoming
    points, and §23 would do exactly that. The concern behind §23 is real and is
    answered by §5.3 instead — an ineligible posting sorts into a lower band
    whatever it scores, so a graduation rule that excludes somebody moves the
    row without ever touching the number.
    """
    if posting.seniority is None or posting.seniority is Seniority.UNCLEAR:
        return ComponentScore(
            component=MatchComponent.PRIORITY,
            points=0,
            assessable=False,
            why="no rule could tell what level this posting is",
        )
    if posting.seniority not in _EARLY_CAREER:
        return ComponentScore(
            component=MatchComponent.PRIORITY,
            points=0,
            assessable=True,
            why=f"this is a {posting.seniority} posting, not an early-career one",
        )
    return ComponentScore(
        component=MatchComponent.PRIORITY,
        points=weight,
        assessable=True,
        why=f"this is a {posting.seniority} posting",
        evidence=(
            Evidence(
                component=MatchComponent.PRIORITY,
                points=weight,
                compared={"seniority": str(posting.seniority)},
            ),
        ),
    )


# ---------------------------------------------------------------------------
# The two penalties
#
# `matching.md` §5.1 gives the ceilings — -25 and -30 — and says nothing about
# the curves, so both were decided here and both decisions are written down
# where the rule is rather than in a review nobody re-reads.
# ---------------------------------------------------------------------------

#: The only requirement kind the missing-requirement penalty may read, and the
#: exclusion is §5.2 rather than convenience.
#:
#: A posting's other required kinds are `degree`, `graduation_window`,
#: `years_experience`, `enrollment` and `authorization` — which is exactly the
#: set of dimensions M3b's eligibility gate owns. Charging points for an unmet
#: degree requirement is the eligibility verdict converted into a number by a
#: side door, and §5.2 forbids it in the plainest language that document has.
#: `role_level` belongs to the seniority penalty below.
#:
#: `test_every_requirement_kind_is_owned_by_the_gate_the_penalty_or_the_level`
#: is what keeps this true when a seventh kind is added.
PENALIZED_REQUIREMENT_KINDS = frozenset({"technology"})


def penalize_missing_requirements(
    posting: PostingForScoring,
    evidence: Iterable[Evidence],
    *,
    ceiling: int,
    per_requirement: int,
) -> Penalty:
    """A fixed cost per required technology with no evidence row behind it.

    **It counts rather than divides**, and that is the load-bearing choice. A
    fraction-based penalty — *the share you failed to meet, times 25* —
    combines with skill overlap's *the share you met, times 30* into
    ``55·matched - 25``, which is arithmetically a single component of weight 55
    with an offset. The penalty would then be a weight change wearing a
    penalty's name, and Task 7's mutation test could zero either one and watch
    the other absorb it. Counting reads a fact the fraction cannot: five
    required technologies you cannot evidence are five things to learn whether
    the posting lists five of them or fifty.

    It reads the **evidence rows**, not the components' verdicts, so a
    technology covered only by a project counts as met — anything else would
    contradict a row this same score is about to store.
    """
    required = [
        requirement
        for requirement in posting.requirements
        if requirement.necessity == "required" and requirement.kind in PENALIZED_REQUIREMENT_KINDS
    ]
    if not required:
        return Penalty(
            name="missing_requirement",
            points=0,
            applicable=False,
            why="this posting names no required technologies",
        )

    evidenced = {
        _normalize(row.requirement.value) for row in evidence if row.requirement is not None
    }
    missing = [r.value for r in required if _normalize(r.value) not in evidenced]
    if not missing:
        return Penalty(
            name="missing_requirement",
            points=0,
            applicable=True,
            why=f"all {len(required)} required technologies have evidence behind them",
            compared={"required": [r.value for r in required], "missing": []},
        )

    # `max` because both sides are negative: the ceiling is the floor of the
    # subtraction, and writing it as `min` on absolute values is the version of
    # this line that gets a sign wrong six months from now.
    points = max(ceiling, -per_requirement * len(missing))
    return Penalty(
        name="missing_requirement",
        points=points,
        applicable=True,
        why=f"{len(missing)} of {len(required)} required technologies have no evidence",
        compared={
            "required": [r.value for r in required],
            "missing": missing,
            "per_requirement": per_requirement,
            "ceiling": ceiling,
        },
    )


def penalize_seniority_mismatch(
    posting: PostingForScoring,
    profile: ScoringProfile,
    *,
    ceiling: int,
    per_year: int,
    implied_years: Mapping[Seniority, int],
) -> Penalty:
    """A posting pitched far above the person's confirmed experience costs points.

    **And it can never block.** M3b refused to let seniority reach the gate at
    all — `Seniority`'s own docstring says so, and A13's argument is that a
    posting's title is not a statement about who may apply. The mechanical form
    of that refusal is that `eligibility.Dimension` has no seniority member, so
    this rule has no route to `ineligible` even if somebody wanted one.

    Scoring it off the title band is also what makes it *additive* rather than a
    second copy of the gate's years rule: the gate reads a stated minimum in the
    posting's text and can only answer when one is stated, while a "Lead
    Engineer" title that names no number is invisible to it and obvious here.

    Both sides must be stated. A level of `unclear` is no rule having decided,
    and a null `years_experience` is the person not having told us — I2's rule,
    and the reason neither resolves to zero. A level with no rung on the ladder
    raises rather than scoring nothing, because a silent skip is
    indistinguishable from a posting that deserved no penalty.
    """
    level = posting.seniority
    if level is None or level is Seniority.UNCLEAR:
        return Penalty(
            name="seniority_mismatch",
            points=0,
            applicable=False,
            why="no rule could tell what level this posting is",
        )
    if profile.years_experience is None:
        return Penalty(
            name="seniority_mismatch",
            points=0,
            applicable=False,
            why="this profile states no years of experience",
        )

    implied = implied_years[level]
    gap = max(0, implied - profile.years_experience)
    compared = {
        "seniority": str(level),
        "posting_implies_years": implied,
        "stated_years": profile.years_experience,
        "gap_years": gap,
        "per_year": per_year,
        "ceiling": ceiling,
    }
    if not gap:
        return Penalty(
            name="seniority_mismatch",
            points=0,
            applicable=True,
            why=(
                f"this is a {level} posting and the profile states {profile.years_experience} years"
            ),
            compared=compared,
        )
    return Penalty(
        name="seniority_mismatch",
        points=max(ceiling, -per_year * gap),
        applicable=True,
        why=(
            f"this is a {level} posting, which implies about {implied} years, "
            f"and the profile states {profile.years_experience}"
        ),
        compared=compared,
    )


# ---------------------------------------------------------------------------
# Composition — the total, out of what could be assessed
# ---------------------------------------------------------------------------

#: `MatchComponent` names a kind of claim in the database; `data/matching.yaml`
#: names a weight in a file a human edits. They are deliberately different
#: strings, and `test_every_component_has_a_weight` is the only thing keeping
#: them mapped rather than merely similar — which `MatchComponent`'s docstring
#: promises by name.
WEIGHT_NAME: dict[MatchComponent, str] = {
    MatchComponent.ROLE: "role_relevance",
    MatchComponent.SKILL: "skill_overlap",
    MatchComponent.PROJECT: "project_evidence",
    MatchComponent.LOCATION: "location_and_work_mode",
    MatchComponent.FRESHNESS: "listing_freshness",
    MatchComponent.PRIORITY: "early_career_priority",
}


@dataclass(frozen=True)
class MatchScore:
    """One posting's whole score, and the denominator it is out of.

    **`assessed_out_of` is not decoration and it is not always 100** (§5.1.1,
    QUESTIONS Q6). Skill overlap and project evidence both read the required
    technology list, and 26 of the 60 labeled postings name none — so on 43% of
    the corpus half the available score cannot be computed. Scoring those out of
    100 subtracts 50 points for something about the employer's prose, which is
    §5.1's `application_urgency` argument with a bigger number behind it.

    `overall` is the literal sum of the parts, floored at zero, exactly as
    `match_results.the_total_is_its_parts` asserts. **The ranking sorts on
    `fraction`, not on `overall`** — and that is why the denominator has to
    reach the database rather than being recomputed on read: a component that
    scored zero and a component that could not be assessed are indistinguishable
    from the stored points alone, which is the entire point of the distinction.
    """

    components: tuple[ComponentScore, ...]
    penalties: tuple[Penalty, ...]
    assessed_out_of: int
    component_total: int
    penalty_total: int
    overall: int

    def __post_init__(self) -> None:
        # A score is all six components or it is not a score. Five of them sum
        # to a smaller total *and* a smaller denominator, so the fraction still
        # looks reasonable and nothing downstream notices — and assembling this
        # tuple from six separate calls is exactly where one gets dropped.
        present = sorted(c.component for c in self.components)
        if present != sorted(MatchComponent):
            missing = sorted(set(MatchComponent) - set(present))
            duplicated = sorted({c for c in present if present.count(c) > 1})
            raise ValueError(
                f"a score needs each of the six components exactly once: "
                f"missing {[str(c) for c in missing]}, "
                f"counted twice {[str(c) for c in duplicated]}"
            )
        expected = max(0, self.component_total + self.penalty_total)
        if self.overall != expected:
            raise ValueError(
                f"overall is {self.overall} and its parts sum to {expected}; "
                "the database refuses this row and so does I4"
            )

    @property
    def fraction(self) -> float | None:
        """`None` when nothing could be assessed, and never 0.0.

        Zero sorts a posting last and one sorts it first, and both are claims.
        A profile with no skills, no projects and no stated preferences against
        a posting with no dates and no readable level reaches this, and the
        honest answer there is that this pair was not scored.
        """
        if not self.assessed_out_of:
            return None
        return self.overall / self.assessed_out_of

    @property
    def unassessable(self) -> tuple[ComponentScore, ...]:
        """What the page names, with each component's own reason (§5.1.1)."""
        return tuple(c for c in self.components if not c.assessable)

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(row for component in self.components for row in component.evidence)


def compose_score(
    components: Iterable[ComponentScore],
    penalties: Iterable[Penalty],
    *,
    weights: MatchingWeights,
) -> MatchScore:
    """Sum the parts, and record what the sum is out of.

    Penalties subtract from the numerator and never widen the denominator: a
    heavily penalised posting has not been assessed on *more*, and adding the
    ceilings to `assessed_out_of` would make it look like it had.
    """
    scored = tuple(components)
    costs = tuple(penalties)
    assessed = sum(weights.weight(WEIGHT_NAME[c.component]) for c in scored if c.assessable)
    component_total = sum(c.points for c in scored)
    penalty_total = sum(p.points for p in costs)
    return MatchScore(
        components=scored,
        penalties=costs,
        assessed_out_of=assessed,
        component_total=component_total,
        penalty_total=penalty_total,
        overall=max(0, component_total + penalty_total),
    )


def score_match(
    posting: PostingForScoring,
    profile: ScoringProfile,
    *,
    weights: MatchingWeights,
    as_of: date,
) -> MatchScore:
    """The whole score for one (person, posting) pair. Pure, and no database.

    The penalties run *after* the components because one of them reads their
    evidence rows: "a required technology with no evidence behind it" is a
    statement about rows this function has just produced, not a second search
    through the profile that could disagree with them.

    Deliberately not here: the eligibility state. It is computed by
    `eligibility.py`, stored in its own column beside this number, and never
    folded into it (§5.2). A job can be an 82 and `uncertain`.
    """
    components = (
        score_role_relevance(posting, profile, weight=weights.weight("role_relevance")),
        score_skill_overlap(posting, profile, weight=weights.weight("skill_overlap")),
        score_project_evidence(posting, profile, weight=weights.weight("project_evidence")),
        score_location_and_work_mode(
            posting, profile, weight=weights.weight("location_and_work_mode")
        ),
        score_listing_freshness(
            posting,
            weight=weights.weight("listing_freshness"),
            full_days=weights.threshold("freshness_days.full"),
            zero_days=weights.threshold("freshness_days.zero"),
            as_of=as_of,
        ),
        score_early_career_priority(posting, weight=weights.weight("early_career_priority")),
    )
    evidence = tuple(row for component in components for row in component.evidence)
    penalties = (
        penalize_missing_requirements(
            posting,
            evidence,
            ceiling=weights.ceiling("missing_requirement"),
            per_requirement=weights.threshold("missing_requirement.per_requirement"),
        ),
        penalize_seniority_mismatch(
            posting,
            profile,
            ceiling=weights.ceiling("seniority_mismatch"),
            per_year=weights.threshold("seniority_mismatch.per_year"),
            implied_years={
                level: weights.threshold(f"seniority_years.{level}")
                for level in Seniority
                if level is not Seniority.UNCLEAR
            },
        ),
    )
    return compose_score(components, penalties, weights=weights)
