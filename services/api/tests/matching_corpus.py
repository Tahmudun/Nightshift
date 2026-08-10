"""The scoring corpus, built once and shared by every test that scores it.

Extracted from `test_matching_golden.py` at M3c Task 11, when a second test
needed the same 153 postings through the same extractors. Copying it would have
produced two corpora that drift, and a measurement taken against a corpus that
is *nearly* the golden file's is a measurement of nothing in particular.

Nothing here is a fixture in the pytest sense — these are plain functions, so a
script outside the suite can build the same corpus and get the same rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from nightshift.adapters.base import BoardRef, RawJob
from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.domain.eligibility_reading import read_posting
from nightshift.domain.requirement_extraction import RequirementProposal, extract_requirements
from nightshift.domain.role_classification import classify_role
from nightshift.domain.scoring import (
    ConfirmedProject,
    ConfirmedSkill,
    JobLocationForScoring,
    PostingForScoring,
    ScoringProfile,
)
from nightshift.domain.skill_vocabulary import load_vocabulary

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS = FIXTURES / "eligibility"
PROFILES_FILE = FIXTURES / "matching" / "profiles.yaml"

#: Frozen, and it has to be. `listing_freshness` is arithmetic against today,
#: so a golden file computed with `date.today()` would go red every morning and
#: teach everyone to regenerate it without reading the diff — which is the
#: habit that makes that file's regeneration guard pointless.
AS_OF = date(2026, 8, 9)


@dataclass(frozen=True)
class CorpusPosting:
    key: str
    posting: PostingForScoring


def load_corpus() -> tuple[CorpusPosting, ...]:
    """Every recorded posting, through the real adapter and the real extractors.

    The nine boards are all Greenhouse, so one adapter covers them. Going
    through `normalize` rather than reaching into the payload is deliberate:
    `remote_policy`, `locations` and `source_published_at` are adapter decisions
    (A10's warning about `posted_at` being a last-modified stamp lives in
    there), and a test that re-derived them would pin a second opinion.
    """
    adapter = GreenhouseAdapter.__new__(GreenhouseAdapter)  # normalize() is pure; no client needed
    vocabulary = load_vocabulary()
    out: list[CorpusPosting] = []

    for path in sorted(CORPUS.glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        token = str(meta["provenance"]["board_token"])
        board = BoardRef(company=token, ats="greenhouse", token=token)

        for job in json.loads(path.read_text(encoding="utf-8"))["jobs"]:
            raw = RawJob(source_job_id=str(job["id"]), source_company_key=token, payload=job)
            normalized = adapter.normalize(raw, board)
            text = normalized.description_text or ""
            proposals = extract_requirements(text, vocabulary=vocabulary)
            reading = read_posting(proposals)
            years = reading.min_years_experience
            classification = classify_role(
                normalized.title,
                description=text,
                years=years if isinstance(years, int) else None,
            )
            out.append(
                CorpusPosting(
                    key=f"{token}/{job['id']}",
                    posting=PostingForScoring(
                        title=normalized.title,
                        description_text=text,
                        role_family=classification.role_family,
                        role_family_span=classification.family_span,
                        seniority=classification.seniority,
                        requirements=tuple(proposals),
                        locations=tuple(
                            JobLocationForScoring(city=loc.city, region=loc.state)
                            for loc in normalized.locations
                        ),
                        remote_policy=normalized.remote_policy,
                        source_published_at=(
                            normalized.source_published_at.date()
                            if normalized.source_published_at
                            else None
                        ),
                    ),
                )
            )
    return tuple(sorted(out, key=lambda c: c.key))


def load_profiles() -> tuple[tuple[str, ScoringProfile], ...]:
    raw = yaml.safe_load(PROFILES_FILE.read_text(encoding="utf-8"))
    profiles: list[tuple[str, ScoringProfile]] = []
    for entry in raw["profiles"]:
        profiles.append(
            (
                str(entry["name"]),
                ScoringProfile(
                    skills=tuple(
                        # `taxonomy_id` equals the name because these are all
                        # vocabulary terms; a fixture skill outside the taxonomy
                        # would be a different test, not a different fixture.
                        ConfirmedSkill(name=str(s), taxonomy_id=str(s))
                        for s in entry["skills"]
                    ),
                    projects=tuple(
                        ConfirmedProject(
                            name=str(p["name"]),
                            technologies=tuple(str(t) for t in p["technologies"]),
                            evidence=str(p["evidence"]),
                        )
                        for p in entry["projects"]
                    ),
                    preferred_roles=tuple(str(r) for r in entry["preferred_roles"]),
                    preferred_locations=tuple(str(loc) for loc in entry["preferred_locations"]),
                    remote_preference=entry["remote_preference"],
                    years_experience=entry["years_experience"],
                ),
            )
        )
    return tuple(profiles)


def required_technologies(posting: PostingForScoring) -> tuple[RequirementProposal, ...]:
    """The rows skill overlap and project evidence divide by.

    Deliberately re-derived here rather than imported from `scoring`: a test
    measuring what the scorer misses has to state its own denominator, or a
    change to the scorer's definition silently moves the measurement with it.
    """
    return tuple(
        r for r in posting.requirements if r.kind == "technology" and r.necessity == "required"
    )
