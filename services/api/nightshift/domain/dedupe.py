"""Layered deduplication (PRODUCT-SPEC §7.5, ADR 0010).

Pure: this module compares two candidates and returns a verdict. It performs no
I/O and holds no session, so the whole evaluation suite runs in milliseconds and
the database applier in :mod:`nightshift.domain.ingestion` stays a translation
layer with no policy in it.

The layers are ordered strongest-first and the first that fires decides. One
asymmetry shapes every rule here: a missed merge shows a user the same job
twice, which is obvious and self-correcting; a wrong merge deletes a real
opening from their view and they never learn it existed. So the layer that is
hardest to explain gets the least authority.

``compare`` is symmetric by construction — every comparison below is between
values, never between "the new one" and "the existing one". An asymmetric
matcher would make merges depend on ingestion order, and the same board polled
twice would produce different canonical jobs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from nightshift.db.base import EmploymentType
from nightshift.domain.embeddings import cosine_similarity

# Bumped whenever a layer, a threshold or a blocking rule changes. Stored on
# every merge event, so a change in merge behaviour is attributable rather than
# archaeological.
DEDUPE_RULESET_VERSION = "1"

# Derived from tests/fixtures/dedupe_pairs.yaml by
# scripts/derive_dedupe_threshold.py, not chosen. Measured 2026-08-01 under
# bge-small-en-v1.5:
#
#     0.9693  merge     edited_description_still_merges
#     0.9370  merge     cross_posted_reworded_text
#     0.7640  distinct  same_title_genuinely_different_role
#
# Any value in (0.7640, 0.9370] separates the labelled set; this is the
# midpoint. The midpoint rather than something more cautious because the
# caution already lives in the layer ordering — similarity is unreachable
# until company, employment type, title and location all agree — and doubling
# it here would only cost true merges without buying protection the blocking
# rules do not already provide.
#
# Re-derive when the fixture set grows, and bump DEDUPE_RULESET_VERSION when
# this changes.
SIMILARITY_THRESHOLD = 0.85

# `content_hash(None)` is the sha256 of the empty string, not a null. Two
# postings with no description therefore carry identical, perfectly real
# hashes, and layer 2 must refuse to read that as evidence.
EMPTY_DESCRIPTION_HASH = hashlib.sha256(b"").hexdigest()

# Tracking parameters carry no identity. Everything else in the query string is
# kept: some boards identify the posting there, and stripping the whole query
# would merge every job on such a board into one.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gh_src",
        "gh_jid",
        "ref",
        "source",
        "src",
        "lever-source",
        "lever-origin",
    }
)


@dataclass(frozen=True, slots=True)
class DedupeCandidate:
    """One side of a comparison, flattened out of the ORM.

    ``embedding`` is None until the embedder has run. A None embedding disables
    the similarity layer for that pair rather than failing it — an unembedded
    job falls back to the deterministic layers, which is the safe direction.
    """

    company_key: str
    canonical_url: str | None
    normalized_title: str
    employment_type: EmploymentType
    location_keys: frozenset[str]
    description_hash: str
    description: str | None = None
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class DedupeVerdict:
    """A decision, the reason for it, and how sure it is.

    ``reason`` becomes ``job_source_links.link_reason`` and
    ``job_merge_events.reason``. It is a short stable token rather than prose,
    because it is queried and grouped.
    """

    merge: bool
    reason: str
    confidence: float = 0.0


def normalize_url(url: str | None) -> str | None:
    """Strip tracking parameters, lowercase the host, drop a trailing slash.

    Deliberately conservative. The path is untouched and only known tracking
    keys are removed, because a posting identifier hiding in the query string is
    common and dropping it would merge a whole board into one job.

    Returns None for anything without a host. None is important: the layer-1
    check requires both sides to be non-None, so two postings that both lack a
    URL cannot merge by matching each other's absence.
    """
    if not url or not url.strip():
        return None
    parts = urlsplit(url.strip())
    if not parts.netloc or not parts.scheme:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def location_key(city: str | None, state: str | None, country: str | None) -> str:
    """A comparable key for one parsed location.

    Case-folded and pipe-joined rather than hashed, so a failing assertion
    prints something a human can read. Nulls become empty strings rather than
    ``"None"``: two unparsed locations must not match each other, since that
    would merge two jobs on the basis of two parsing failures.
    """
    return "|".join((city or "", state or "", country or "")).casefold()


def _blocked(a: DedupeCandidate, b: DedupeCandidate) -> str | None:
    """Name the blocking rule that refuses this pair, or None.

    These override every layer. Employment type is here because it is the rule
    that fires on real data: on the recorded Ashby board an internship and a
    full-time role share a title, an office and often a description.
    """
    if a.company_key != b.company_key:
        return "different_company"
    if a.employment_type is not b.employment_type:
        return "different_employment_type"
    return None


def compare(a: DedupeCandidate, b: DedupeCandidate) -> DedupeVerdict:
    """Decide whether two candidates describe one real-world opening."""
    blocking = _blocked(a, b)
    # Company is absolute and applies even to layer 1. Nothing merges across
    # employers, ever, whatever the URLs say.
    if blocking == "different_company":
        return DedupeVerdict(False, blocking)

    # Layer 1 — the same posting, literally. This is identity rather than
    # evidence, so it survives the employment-type block: two URLs being equal
    # while the types disagree is a source defect, and splitting the job in two
    # would not fix it.
    url_a, url_b = normalize_url(a.canonical_url), normalize_url(b.canonical_url)
    if url_a is not None and url_a == url_b:
        return DedupeVerdict(True, "same_canonical_url", 1.0)

    if blocking is not None:
        return DedupeVerdict(False, blocking)

    if a.normalized_title != b.normalized_title:
        # §7.5 is explicit: do not merge on title similarity. Equality is the
        # only title test here, and "Software Engineer II" and
        # "Software Engineer III" differ by one character and are different
        # jobs.
        return DedupeVerdict(False, "different_title")

    if not (a.location_keys & b.location_keys):
        # One shared location is enough — a role open in two cities and
        # cross-posted is still one role — but no overlap at all means two
        # openings, per M0's note on keeping multi-location roles distinct.
        return DedupeVerdict(False, "no_shared_location")

    # Layer 2 — byte-identical descriptions, under an agreeing title and office.
    #
    # The empty hash is excluded explicitly. `content_hash(None)` returns a real
    # sha256 — of the empty string — so without this guard two postings that
    # both lack a description would compare equal and merge. That is a merge
    # made on two absences rather than on evidence, and it is the same failure
    # shape as two null URLs matching each other.
    if (
        a.description_hash
        and a.description_hash != EMPTY_DESCRIPTION_HASH
        and a.description_hash == b.description_hash
    ):
        return DedupeVerdict(True, "identical_content", 0.99)

    # Layer 3 — ADR 0010. Reachable only once company, employment type, title
    # and location already agree, so similarity breaks a tie and never makes a
    # match on its own. A pair disagreeing on any of the above never arrives
    # here, however high it would have scored.
    if a.embedding is not None and b.embedding is not None:
        similarity = cosine_similarity(a.embedding, b.embedding)
        if similarity >= SIMILARITY_THRESHOLD:
            # Confidence is the similarity itself, capped below the 0.99 that
            # layer 2 earns by comparing actual bytes. A number is not a reason,
            # and this layer must never outrank one that compared content.
            return DedupeVerdict(True, "similar_description", min(similarity, 0.95))
        return DedupeVerdict(False, "below_similarity_threshold")

    return DedupeVerdict(False, "no_matching_layer")
