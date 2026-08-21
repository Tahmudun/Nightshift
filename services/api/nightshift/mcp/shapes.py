"""Turning API responses into tool results that carry their own qualifiers.

Pure. No I/O, no network, no clock, no database — the one import from
`nightshift.db` is `base`, which holds enums and no engine, so
:data:`CONFIDENCE_MEANS` can be proven exhaustive over `LocationConfidence`.
`tests/test_mcp_boundaries.py` permits exactly that and bans the rest.

**This module is where invariants I1 and I4 are enforced, and the enforcement
is prose.** That reads like a contradiction and is not. Every earlier milestone
had a renderer on the other end: a React component shows what it is given, and
`location_confidence` reaching it as a string is enough, because a designer
decided what that string looks like. Here the other end is a language model
that will paraphrase, summarise and answer follow-up questions hours later. A
field it cannot interpret is a field it will interpret *anyway*.

So every location carries a sentence saying what it licenses a reader to claim,
attached to the row rather than filed in a schema description, because a rule
stated once at the top of a long conversation is a rule that conversation
drifts away from.
"""

from __future__ import annotations

from typing import Any

from nightshift.db.base import LocationConfidence

#: One plain sentence per confidence value, travelling **with** the value.
#:
#: Asserted exhaustive over the enum in `tests/test_mcp_shapes.py`, so a sixth
#: member cannot ship without one. That test is the whole of I1's enforcement
#: on this surface: `LocationConfidence` docstring says "there is no sixth value
#: and no default of convenience", and if one ever arrives it must arrive with
#: an explanation rather than inheriting some neighbour's.
#:
#: They are written for a reader who will paraphrase them, which is why each one
#: says what is **not** known as well as what is.
CONFIDENCE_MEANS: dict[LocationConfidence, str] = {
    LocationConfidence.VERIFIED: (
        "A person confirmed this street address and it geocoded to a specific "
        "building. This is the only value that licenses naming a street address."
    ),
    LocationConfidence.APPROXIMATE: (
        "The coordinates come from a geocoder and land near, but not certainly "
        "on, the right building. Name the neighbourhood if you like; do not name "
        "a street address or a building."
    ),
    LocationConfidence.CITY_ONLY: (
        "The posting names a city and nothing finer. Nightshift does not know "
        "where in the city this role sits and will not place it on a building. "
        "Saying more than the city invents a fact about a real company."
    ),
    LocationConfidence.REMOTE: (
        "The posting says the role is remote. There is no office to name, and a "
        "coordinate would be a fiction rather than a rounding."
    ),
    LocationConfidence.UNKNOWN: (
        "Nightshift could not resolve this location honestly, or has not tried. "
        "This is an admission of ignorance, not a hint — do not guess from the "
        "company name, the posting text, or anything else."
    ),
}


def location_result(
    *,
    text: str | None,
    confidence: LocationConfidence | str,
    latitude: float | None = None,
    longitude: float | None = None,
    city: str | None = None,
    is_primary: bool | None = None,
) -> dict[str, Any]:
    """One location, with its qualifier attached rather than implied.

    ``coordinates`` is ``null`` unless there are both a latitude and a
    longitude. Half a coordinate is not a location, and the guard is here
    rather than at each caller because there are three callers and there will
    be more.

    **The coordinates are also withheld for `city_only`, `remote` and
    `unknown`, even if the row somehow carries them.** The database should
    never hold that combination and this is not the place to find out it does:
    a coordinate on a `city_only` row would be read as an address by exactly
    the consumer this module exists to protect against.
    """
    value = LocationConfidence(confidence)
    placeable = value in (LocationConfidence.VERIFIED, LocationConfidence.APPROXIMATE)
    has_pair = latitude is not None and longitude is not None

    result: dict[str, Any] = {
        "text": text,
        "city": city,
        "confidence": value.value,
        "means": CONFIDENCE_MEANS[value],
        "coordinates": (
            {"latitude": latitude, "longitude": longitude} if placeable and has_pair else None
        ),
    }
    if is_primary is not None:
        result["is_primary"] = is_primary
    return result


def job_summary(job: dict[str, Any]) -> dict[str, Any]:
    """A job as a search result. Locations qualified; **no score**.

    A score appears in exactly one tool's output — `explain_match` — and I4 is
    why: *"a bare number in the UI is a bug"*, and a tool result is a UI. A
    ranked list carrying `78` with nothing behind it is the thing I4 forbids,
    and the honest version is a pointer to the tool that decomposes it.
    """
    return {
        "id": job["id"],
        "title": job["title"],
        "company": job["company"]["canonical_name"],
        "employment_type": job["employment_type"],
        "remote_policy": job["remote_policy"],
        "status": job["status"],
        "locations": [_location_from_api(row) for row in job.get("locations", [])],
        "first_seen_at": job["first_seen_at"],
        "source_published_at": job.get("source_published_at"),
        "explain_match_with": (
            "Call explain_match with this job's id for its score and the evidence "
            "behind it. Do not estimate a score yourself."
        ),
    }


def _location_from_api(row: dict[str, Any]) -> dict[str, Any]:
    """`JobLocationOut` → a qualified location."""
    return location_result(
        text=row.get("raw_text"),
        confidence=row["location_confidence"],
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        city=row.get("city"),
        is_primary=row.get("is_primary"),
    )


def search_result(payload: dict[str, Any]) -> dict[str, Any]:
    """`JobListOut` → a search result the model can read honestly.

    ``total`` travels beside the jobs because a limited list read as a complete
    one is its own small lie: "there are 25 backend roles open" is wrong when
    25 was the page size.
    """
    return {
        "jobs": [job_summary(job) for job in payload.get("items", [])],
        "total_matching": payload.get("total"),
        "returned": len(payload.get("items", [])),
    }


def job_detail(job: dict[str, Any]) -> dict[str, Any]:
    """`JobDetailOut` → one job in full. Still no score (I4).

    ``requirements_extractor_version`` travels with the requirements because an
    empty list means two different things — *this posting asks for nothing* and
    *nothing has read this posting* — and the version is what separates them.
    `JobDetailOut` records the same reasoning for the same reason.
    """
    detail = job_summary(job)
    detail.update(
        {
            "description": job.get("description_text"),
            "requirements": job.get("requirements", []),
            "requirements_extractor_version": job.get("requirements_extractor_version"),
            "requirements_note": (
                "An empty requirements list with a null extractor version means no "
                "one has read this posting yet — not that it asks for nothing."
            ),
            "sources": [source.get("source_name") for source in job.get("sources", [])],
            "url": job.get("canonical_url"),
        }
    )
    return detail


def match_explanation(job: dict[str, Any]) -> dict[str, Any]:
    """`JobDetailOut` → the score and everything that has to travel with it.

    **The only shape in this module that carries a number**, and it carries the
    whole of I4's list: components, penalties, `ruleset_version`, evidence.

    A null ``match`` is returned as a null with a sentence rather than as an
    empty object or a zero. `MatchOut` names the three situations it covers —
    the sweep has not reached this pair, the posting has no description, or the
    stored row is at a ruleset version no longer current — and all three are
    "no score", none of which is a number.
    """
    match = job.get("match")
    if match is None:
        return {
            "job_id": job["id"],
            "title": job["title"],
            "company": job["company"]["canonical_name"],
            "match": None,
            "why_no_score": (
                "Nightshift has not scored this job for this reader. That means the "
                "scoring sweep has not reached it, the posting has no description to "
                "read, or the stored score was computed by a ruleset version that is "
                "no longer current. It does not mean the score is low. Do not "
                "estimate one."
            ),
        }

    return {
        "job_id": job["id"],
        "title": job["title"],
        "company": job["company"]["canonical_name"],
        "match": {
            "score": match["overall_score"],
            "out_of": match["assessed_out_of"],
            "fraction": match["fraction"],
            "eligibility_status": match["eligibility_status"],
            "components": match["components"],
            "penalty_score": match["penalty_score"],
            "penalties": match["penalties"],
            "deferred_components": match["deferred_components"],
            "ruleset_version": match["ruleset_version"],
            "computed_at": match["computed_at"],
        },
        "eligibility": job.get("eligibility"),
        "how_to_read_this": (
            "`out_of` is not always 100 — a component the posting said too little to "
            "assess is left out of the denominator rather than scored zero, so "
            "compare `fraction` across jobs and not `score`. A component with "
            "`assessable: false` was not asked, which is not the same as failing it. "
            "`eligibility_status` is separate from the score: a job can score well "
            "and still be `ineligible`."
        ),
    }


def application_list(payload: dict[str, Any]) -> dict[str, Any]:
    """`ApplicationListOut` → the pipeline, with each job's locations qualified."""
    return {
        "applications": [
            {
                "id": row["id"],
                "stage": row["current_stage"],
                "priority": row["priority"],
                "applied_at": row.get("applied_at"),
                "next_action_at": row.get("next_action_at"),
                "job": job_summary(row["job"]),
            }
            for row in payload.get("items", [])
        ],
        "total": payload.get("total"),
        "stage_counts": payload.get("stage_counts"),
        "read_only": (
            "You cannot change a stage or apply to anything through Nightshift's "
            "MCP server. Say what you would change and let the reader do it."
        ),
    }


def capture_proposal(capture: dict[str, Any], *, web_url: str) -> dict[str, Any]:
    """`CaptureOut` → a proposal, described as a proposal.

    **The wording here is the enforcement.** I5 and the whole of M5a live in
    whether the model says *"I've added that job"* or *"I've put that in your
    review queue"*. The first is false — nothing is in the corpus, nothing is
    on the map, no application exists — and it is what a model will say by
    default about a successful write, because a successful write usually means
    something happened.

    So the result names its own status, names what the parser declined to read,
    and carries the URL where a person decides. `CaptureProposalOut` already
    makes every field nullable with `null` meaning *the parser declined rather
    than the key is missing*; this surfaces that distinction to a reader who
    would otherwise see a blank and assume a bug.
    """
    proposed = capture.get("proposed") or {}
    unread = sorted(field for field, value in proposed.items() if value is None)

    return {
        "capture_id": capture["id"],
        "status": capture["status"],
        "proposed": proposed,
        "could_not_read": unread,
        "review_url": f"{web_url.rstrip('/')}/operate/capture",
        "what_just_happened": (
            "A proposal was created and nothing else. This posting is NOT in "
            "Nightshift's job corpus, is NOT on the map, and has NO application "
            "attached. Nightshift read what it could from the text; a field listed "
            "in `could_not_read` is one the parser declined to guess at, which is "
            "deliberate rather than a failure. The reader confirms or discards it "
            "at `review_url`, and only then does a job exist."
        ),
    }
