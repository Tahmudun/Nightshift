"""API response schemas.

Two rules shape everything here.

Invariant I1: a location is never serialised as a bare coordinate pair. Every
location carries its ``location_confidence`` and the ``raw_text`` it came from,
so a client physically cannot render a point without also having the precision
claim attached to it.

AMENDMENTS A10: a field the source did not provide is ``null`` with a companion
flag rather than an omitted key or a zero. "Absence of data is data", and the UI
is required to say "not provided by source" instead of hiding the row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationPriority,
    ApplicationStage,
    BoardTier,
    EligibilityState,
    EmploymentType,
    EventActor,
    EvidenceSource,
    ExtractionKind,
    ExtractionStatus,
    IngestionRunStatus,
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
    SkillSourceType,
    TransitionClass,
    WorkAuthorization,
)
from nightshift.domain.placement import PlacementKind
from nightshift.domain.queue import QueueSectionKey


class HealthComponent(BaseModel):
    """One dependency's health. ``ok=False`` always carries an ``error``."""

    ok: bool
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Reports honestly, including when things are down (M0 acceptance).

    ``status`` is ``degraded`` rather than ``ok`` whenever any component is
    failing, and the endpoint returns HTTP 503 in that case so a probe does not
    have to parse the body to learn the truth.
    """

    status: str = Field(description="ok | degraded")
    version: str
    environment: str
    database: HealthComponent
    redis: HealthComponent
    checked_at: datetime


class JobLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_text: str = Field(description="The exact location substring from the source")
    city: str | None
    state: str | None
    country: str | None
    latitude: float | None
    longitude: float | None
    location_confidence: LocationConfidence
    resolution_method: ResolutionMethod
    is_primary: bool

    @property
    def is_mappable(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    website: str | None


class JobSourceOut(BaseModel):
    """Provenance, exposed. Every canonical job traces to a raw source record."""

    source_name: str
    source_job_id: str
    canonical_url: str | None
    first_seen_at: datetime
    last_seen_at: datetime


class SalaryOut(BaseModel):
    """A10: sparse. ``provided=False`` is what the UI renders as an explicit absence."""

    provided: bool
    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    # Greenhouse publishes a range without stating annual vs hourly. Guessing
    # from magnitude would be a fabrication, so this stays null and the UI says
    # the period was not specified.
    period: str | None = None


class JobSummaryOut(BaseModel):
    """List-view job. Deliberately excludes the description: a jobs list that
    ships every full description is a slow list."""

    id: UUID
    title: str
    company: CompanyOut
    employment_type: EmploymentType
    remote_policy: RemotePolicy
    status: JobStatus
    locations: list[JobLocationOut]
    salary: SalaryOut

    # Named for what they are (A10). `source_published_at` is the source's own
    # publication date; `first_seen_at` is when *we* first saw it and is never
    # presented as "posted".
    source_published_at: datetime | None
    source_updated_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    application_deadline: datetime | None

    @property
    def has_any_mappable_location(self) -> bool:
        return any(loc.latitude is not None for loc in self.locations)


class JobRequirementOut(BaseModel):
    """One thing a posting asks for, and the characters where it says so.

    `raw_text` plus the offsets are what the page highlights. Serialising the
    offsets without the text — or the text without the offsets — would let the
    two drift, and the highlight would quietly point somewhere else.
    """

    kind: RequirementKind
    value: str
    raw_text: str
    char_start: int
    char_end: int
    necessity: RequirementNecessity
    has_equivalence: bool


class EligibilityBlockerOut(BaseModel):
    """One reason a posting may not be open to this person, with its evidence.

    I4 applied to a verdict rather than a score. `posting_says` and
    `posting_span` are the posting's own words and where they are, so the page
    can quote rather than paraphrase — the same discipline
    `JobRequirementOut` already follows.
    """

    dimension: str
    #: `blocks` or `soft_blocks`. The page renders them differently: one is a
    #: wall, the other is a gap the person may well decide to ignore.
    outcome: str
    posting_says: str | None
    char_start: int | None
    char_end: int | None
    profile_says: str
    why: str


class EligibilityUnknownOut(BaseModel):
    """A dimension the gate could not decide, and whether anything would fix it.

    Separate from a blocker because they mean opposite things. A blocker says
    "this is probably not for you"; an unknown says "we could not decide".
    Rendering them the same way turns an action into a rejection.

    **`profile_field` is null when no field would resolve it** — the posting
    accepts equivalent experience, and nothing the person types moves that. The
    page renders those without a link, because a link that cannot help is worse
    than no link: they follow it, fill the field, and the answer is unchanged.
    """

    dimension: str
    profile_field: str | None
    why: str


class EligibilityOut(BaseModel):
    """The gate's verdict, computed on read and stored nowhere.

    `matching.md` §5.2: the state is never converted into points and never
    collapsed into a number. It travels with its blockers, its unknowns and the
    version of the rules that produced it, because a bare state is the same bug
    as a bare score.
    """

    state: str
    blockers: list[EligibilityBlockerOut] = Field(default_factory=list)
    unknowns: list[EligibilityUnknownOut] = Field(default_factory=list)
    gate_version: str


class MatchEvidenceOut(BaseModel):
    """One link the score rests on, with both sides quoted (`matching.md` §4.3).

    This is invariant I4's payload. Every positive component has at least one of
    these behind it — the database refuses the row otherwise — so a client that
    renders `points` without rendering these has thrown the breakdown away rather
    than never having had it.

    The two nullable sides are §2.1's distinction, not missing data. `role`,
    `skill` and `project` rows carry both spans because they claim something about
    the person; `location`, `freshness` and `priority` carry `compared` instead,
    because there is no claim about anybody's qualifications to quote and
    inventing a span is the failure the whole arrangement prevents.
    """

    component: MatchComponent
    points: int
    #: The posting's own words, and which of its strings they came from. The
    #: field travels with the offsets: role relevance quotes the **title** and
    #: everything else quotes `description_text`, so offsets alone would
    #: highlight the wrong text and look plausible doing it.
    job_span_text: str | None
    job_span_field: JobTextField | None
    job_char_start: int | None
    job_char_end: int | None
    #: The person's own **confirmed** words — never a resume proposal.
    user_span_text: str | None
    user_skill_id: UUID | None
    user_project_id: UUID | None
    #: What the exempt components weighed: `{"job": "New York, NY", ...}`.
    compared: dict[str, Any] = Field(default_factory=dict)
    #: `rule` or `embedding`. What makes the semantic layer auditable — M3d
    #: reports the share of awarded points that came from a proposal.
    proposed_by: EvidenceSource
    job_requirement_id: UUID | None = None


class MatchComponentOut(BaseModel):
    """One component: its points, what they were out of, and its own sentence.

    **`assessable` is not "did it score".** False means the posting did not say
    enough to ask the question, and §5.1.1 keeps that separate from zero because
    collapsing them charges a terse posting up to 50 points for its employer's
    prose. A client rendering `points` alone cannot tell the two apart — the
    stored number is `0` either way — which is why this field crosses the
    boundary rather than being inferred from it.

    `weight` is what the component would have been out of. It is the same number
    whether or not the component was assessable: an unassessable one is left out
    of the total's denominator, not scaled down inside it.
    """

    component: MatchComponent
    points: int
    weight: int
    assessable: bool
    #: The rule's own sentence, stored beside the points it explains and rendered
    #: verbatim. Not generated at render time, and not a summary of the evidence
    #: rows below — see `MatchComponentAssessment`.
    why: str
    evidence: list[MatchEvidenceOut] = Field(default_factory=list)


class MatchPenaltyOut(BaseModel):
    """One of the two subtractions, with what it cost and why.

    `match_results.penalty_score` is a single column by §4.2's decision and that
    is unchanged — this is what the column is *made of*, which §4.2 itself calls
    the explanation's business. Until Task 10 nothing carried it, so a reader saw
    `-18` with no way to learn which half was which. I4 names penalties in the
    list of things a score stores.

    **`applicable=False` is not "cost nothing".** It is *there was nothing to
    ask*: a posting naming no required technologies, or a profile stating no years
    of experience. Both store `points=0`, and only `why` tells them apart from
    *nothing was missing* — the same distinction `MatchComponentOut.assessable`
    draws one level up.
    """

    name: PenaltyName
    #: Zero or negative, always.
    points: int
    applicable: bool
    #: The rule's own sentence, rendered verbatim. Not assembled from anything.
    why: str
    #: What the rule weighed — the required list and the unmet subset, or the
    #: title's implied years against the stated ones.
    compared: dict[str, Any] = Field(default_factory=dict)


class DeferredComponentOut(BaseModel):
    """A §8.2 component this milestone does not score, named on the page.

    §5.1 defers company preference and application urgency and says of the first
    *"deferred, and named on the page"*. Same disclosure as `DeferredFilterOut`
    one subsystem over: five points nobody mentions is an invisible gap, and five
    points with a reason is a decision a reader can check.
    """

    name: str
    weight: int
    blocked_on: str
    reason: str


class MatchOut(BaseModel):
    """A stored `match_results` row, decomposed. Never a bare number (I4).

    **Served only at the current `ruleset_version`.** A row from an earlier
    version is reported as not-yet-computed — this whole object is null — rather
    than shown with a staleness badge, because a number produced by arithmetic
    that no longer exists is not a worse score (§4.2).

    **`fraction` is the ranking key and it is nullable.** `overall_score` is out
    of `assessed_out_of`, which is not always 100 (§5.1.1), so the raw total
    cannot be compared across postings. `null` means nothing could be assessed at
    all — five pairs in the committed corpus reach it — and it is deliberately not
    `0.0`, which would sort those last as though they had been measured and found
    wanting.

    **`eligibility_status` sits beside the number and is never inside it** (§5.2).
    A posting can be an 82 and `uncertain`, and this object states both without
    reconciling them. It is the same verdict `JobDetailOut.eligibility` carries in
    full; this is the copy the ranked list's bands are built from, and a test
    asserts the two agree.
    """

    overall_score: int
    assessed_out_of: int
    fraction: float | None
    eligibility_status: EligibilityState
    #: All six, in enum order, assessable or not. A response with five is a score
    #: that has lost a part, and the database refuses to store one.
    components: list[MatchComponentOut]
    #: The two §5.1 penalties, summed — `match_results` stores one column and
    #: §4.2 records why. Zero or negative.
    penalty_score: int
    #: Both of them, applicable or not, each with what it cost and its own
    #: sentence. They sum to `penalty_score` and the database asserts it at
    #: commit, so this is a decomposition of that number rather than a second
    #: account of it.
    penalties: list[MatchPenaltyOut] = Field(default_factory=list)
    #: Named, not scored. §5.1's two deferrals.
    deferred_components: list[DeferredComponentOut] = Field(default_factory=list)
    ruleset_version: str
    #: The embedding behind this row's proposals, or null for a rules-only score,
    #: which is every row until Task 11 exists.
    model_version: str | None
    computed_at: datetime


class UnmetRequirementOut(BaseModel):
    """A thing the posting asks for that no evidence row answers.

    `matching.md` §6's second and fourth elements — *why it may not fit* and *soft
    gaps* — which are the same computation read at two necessities. `required`
    rows are the first, `preferred` rows the second, and rendering them alike
    turns a nice-to-have into a bar. `mentioned` requirements never appear:
    §4.1 says they produce no gap.

    **Derived from the stored evidence, never re-scored.** The set difference is
    over the `match_evidence` rows this score already committed, so a requirement
    listed here is one nothing in the graph points at. Re-running the scorer to
    find out would be a second derivation able to disagree with the stored number
    — `matching.posting_for`'s subject.

    Its own type rather than a reuse of `JobRequirementOut` because the claim is
    different: that one says *the posting asks for this*, this one says *and you
    have nothing on file for it*. The second is about a person and belongs to a
    score; the first is true with no user in the request at all.
    """

    kind: RequirementKind
    value: str
    raw_text: str
    char_start: int
    char_end: int
    necessity: RequirementNecessity
    #: "or equivalent experience" — a bar with a stated way around it. Carried so
    #: the page can say so rather than listing it as a flat gap.
    has_equivalence: bool


class JobDetailOut(JobSummaryOut):
    description_text: str | None
    description_html: str | None
    sources: list[JobSourceOut]
    #: In document order, so the page reads down the description it highlights.
    requirements: list[JobRequirementOut] = Field(default_factory=list)
    #: Which rules produced them. Null when nothing has been extracted, which
    #: the page states rather than rendering an empty requirements section —
    #: "this posting asks for nothing" and "we have not read it" differ, and an
    #: empty list alone cannot tell them apart.
    requirements_extractor_version: str | None = None
    #: Computed for the current user on every read, never stored. Null only when
    #: the posting has no extracted requirements at all — a verdict about a
    #: person derived from an unread posting would be a claim based on nothing.
    eligibility: EligibilityOut | None = None
    #: The stored score for the current user, at the current ruleset version.
    #: **Null means not yet computed**, and covers three situations the page has
    #: one honest sentence for: the sweep has not reached this pair yet, the
    #: posting has no description to read, or a stored row exists under a ruleset
    #: version that is no longer current. All three are "no score", which is true
    #: of each; none of them is a number.
    match: MatchOut | None = None
    #: What the posting asks for and this score found nothing for (§6). **Null
    #: rather than empty when `match` is null**: without a score there are no
    #: evidence rows to difference against, and an empty list there would read as
    #: "you meet everything" — a claim about a person computed from nothing, the
    #: same failure `eligibility`'s null exists to prevent one field up.
    unmet_requirements: list[UnmetRequirementOut] | None = None


class DeferredFilterOut(BaseModel):
    """A filter the spec asks for that this milestone will not fake.

    Serialised so the panel renders it disabled with its reason visible. An
    omitted filter is an invisible gap; a named one is a decision a reader can
    check. Same move as `/analyze/coverage` makes for source coverage.
    """

    name: str
    blocked_on: str
    reason: str


class JobListOut(BaseModel):
    items: list[JobSummaryOut]
    total: int
    limit: int
    offset: int
    # A10: how many jobs the salary floor necessarily hid, because they state
    # no salary at all. Zero when no floor was given. Without this number a
    # salary filter silently removes most of the corpus and looks like a result.
    excluded_no_salary: int = 0
    # M3b Task 11: the same honesty, for the two filters that just came on.
    #
    # How many jobs the skill filter could not have matched however well it
    # works, because nothing was extracted from them. Required-technology recall
    # is 0.861 against the answer key, so this filter is usable and incomplete,
    # and a result with no count beside it would be the first in this product to
    # hide that.
    excluded_no_requirements: int = 0
    # How many internships the season filter necessarily hid, because their
    # titles state no season (11 of 19 in the recorded corpus) or no year (9 of
    # 19). The most aggressive hider in the product — more than the salary floor.
    excluded_no_season: int = 0
    deferred_filters: list[DeferredFilterOut] = []


class RankedJobOut(BaseModel):
    """One row of the ranked list: a posting and the score it is ranked on.

    The score is not optional here. A pair with no current-version row cannot be
    ranked and is counted in `not_yet_scored` instead of being given a position —
    an unscored posting placed anywhere in an ordering is a claim about it.
    """

    job: JobSummaryOut
    match: MatchOut


class RankedBandOut(BaseModel):
    """One eligibility band, and the postings inside it, best first.

    `matching.md` §5.3. **The band is a heading, never points.** Grouping by
    eligibility and then sorting by score inside the group is the compromise
    between two things that both matter: a list where a hard blocker does not
    affect position is not usable, and a score that has silently absorbed a
    penalty for uncertainty is a lie. Making the grouping a visible structure
    satisfies both — so this is a list of bands rather than a flat list with an
    eligibility term folded into its sort key.

    **All five bands are always present, empty or not.** A band that vanishes when
    nobody is in it makes `ineligible` invisible exactly when there is nothing in
    it to see, and §3.3 is explicit that an ineligible posting is shown and dimmed
    rather than hidden — which the reader can only trust if the section is there
    to be empty.
    """

    state: EligibilityState
    items: list[RankedJobOut]
    #: How many of `items` could not be assessed at all, so their `fraction` is
    #: null. They sort last within the band and are marked rather than mixed in;
    #: see `MatchRankingOut.unassessed_sort_last`.
    unassessed: int = 0


class MatchRankingOut(BaseModel):
    """One person's corpus, banded by eligibility and ranked inside each band.

    **Sorted on the fraction, never on `overall_score`.** `assessed_out_of` is not
    always 100 (§5.1.1), so raw totals are not comparable across postings: a 40/50
    is a better match than a 45/100 and sorting on the totals puts them the other
    way round.
    """

    bands: list[RankedBandOut]
    #: Every ranked row, across all bands. Not the size of the corpus.
    total: int
    #: Open postings with no score at the current ruleset version — the sweep has
    #: not reached them, they have no description to read, or their stored row
    #: predates a ruleset bump. **Named rather than omitted**: a ranked list that
    #: silently covers 12 of 31 postings looks exactly like a ranked list that
    #: covers all of them.
    not_yet_scored: int
    #: Which arithmetic produced every row here, so a reader can tell that two
    #: numbers on the page were computed by the same rules.
    ruleset_version: str
    #: A constant, serialised so the client cannot quietly choose otherwise: a
    #: posting nothing could be assessed on has a null fraction, and null is
    #: neither best nor worst. It keeps its band — the eligibility verdict is
    #: real — and leaves the ordering, at the end, marked.
    unassessed_sort_last: Literal[True] = True
    #: What the list is sorted by, in words, because the printed number and the
    #: ordering key are deliberately not the same thing (M3d Task 6).
    #:
    #: Every row shows its `fraction` — the honest "of what could be assessed"
    #: figure — and the sort weights that fraction by how much *was* assessed. So
    #: a row reading 17% can sit above one reading 30%, and without this field a
    #: reader's only available conclusion is that the list is broken. Review
    #: §2.10 is the defect; `matching.md` §5.3 carries the measurement.
    ordering: Literal["coverage_weighted_fraction"] = "coverage_weighted_fraction"
    #: §5.1's two, repeated here because the ranked list is where a total is
    #: compared against another total, which is the moment the ten points nobody
    #: scored matter most.
    deferred_components: list[DeferredComponentOut] = Field(default_factory=list)


class JobStatusCounts(BaseModel):
    """How many jobs sit in each closure state.

    Every field defaults to zero and none is optional, so a state with no jobs
    reads as an explicit `0` rather than vanishing from the response. A missing
    key and a real zero are different claims, and the UI must not have to guess
    which it received.
    """

    open: int = 0
    possibly_stale: int = 0
    unverified: int = 0
    closed: int = 0


class CompanyRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    website: str | None
    job_count: int


class CompanyListOut(BaseModel):
    items: list[CompanyRowOut]
    total: int
    limit: int
    offset: int


class CompanyDetailOut(BaseModel):
    id: UUID
    canonical_name: str
    website: str | None
    job_status_counts: JobStatusCounts
    # Ours, not the source's. This is when *we* first saw a role from this
    # employer, and it is never presented as when they started hiring (A10).
    first_seen_at: datetime | None


class SourceHealthOut(BaseModel):
    """§2.6: source reliability must be visible, and visible on the bad days."""

    name: str
    source_type: str
    is_enabled: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    job_count: int
    last_run_status: IngestionRunStatus | None
    last_run_started_at: datetime | None
    last_run_error: str | None
    # Added at M1b. Without a breakdown, a source whose jobs have all gone
    # stale looks identical to a healthy one — the job_count above does not
    # move when a job closes, because the provenance link survives closure.
    job_status_counts: JobStatusCounts = Field(default_factory=lambda: JobStatusCounts())


class BoardPollStateOut(BaseModel):
    """One board's polling state (M1d, ADR 0007).

    **`last_success_at` here, not a posting's `last_seen_at`, is what "fresh"
    means for a board.** A board answering `304` for sixty days leaves its
    postings' timestamps sixty days old while those postings are open and
    correctly so — no misses were taken, because a 304 ages nothing. A UI
    computing staleness from posting timestamps would report a perfectly
    healthy board as rotten.

    `last_status` is carried so a `304` is distinguishable from a `200`. They
    are both success, and a surface that renders "no new jobs" as a warning
    trains people to ignore warnings.
    """

    model_config = ConfigDict(from_attributes=True)

    ats: str
    token: str
    tier: BoardTier
    #: 200, 304, or an error status. None until the board has ever been polled.
    last_status: int | None
    last_polled_at: datetime | None
    #: Only a 200 or a 304 moves this; a failure does not. That is what makes
    #: "how long since this board actually answered" answerable.
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    next_poll_at: datetime
    #: Whether a stored ETag exists, not the ETag itself. The value is an opaque
    #: provider string of no use to a reader, and printing it invites treating
    #: it as an identifier rather than a cache token.
    has_etag: bool


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_name: str
    board_tokens: list[str]
    started_at: datetime
    finished_at: datetime | None
    status: IngestionRunStatus
    records_fetched: int
    records_created: int
    records_updated: int
    records_unchanged: int
    records_closed: int
    records_failed: int
    error_summary: str | None


class LocationConfidenceBreakdown(BaseModel):
    """Counts per confidence value.

    Exists so the honesty of the data set is a first-class, visible number
    rather than something you would have to query the database to learn.
    """

    verified: int = 0
    approximate: int = 0
    city_only: int = 0
    remote: int = 0
    unknown: int = 0


class StatsOut(BaseModel):
    total_jobs: int
    open_jobs: int
    total_companies: int
    total_source_records: int
    location_confidence: LocationConfidenceBreakdown
    mappable_locations: int = Field(
        description="Locations with real coordinates. Zero until M1 adds geocoding."
    )


class JobAdminRowOut(BaseModel):
    """One row of the admin job table.

    Deliberately not the same shape as :class:`JobSummaryOut`. This view answers
    operational questions — is it still listed, how many sources describe it,
    was it merged — and putting those into the user-facing schema would show a
    job seeker the pipeline's internals.
    """

    id: UUID
    title: str
    company_name: str
    status: JobStatus
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    source_count: int
    location_count: int
    merge_count: int


class JobAdminListOut(BaseModel):
    items: list[JobAdminRowOut]
    total: int
    status_counts: JobStatusCounts


class JobStatusEventOut(BaseModel):
    """One transition, in the words the closure machine used at the time.

    ``from_status`` is null on a job's first event: it transitioned from
    nothing, and inventing `open -> open` would be a fabricated row.
    """

    model_config = ConfigDict(from_attributes=True)

    from_status: JobStatus | None
    to_status: JobStatus
    reason: str
    observed_misses: int | None
    created_at: datetime


class BlindSpotOut(BaseModel):
    """One thing the system cannot see, and why.

    ``count`` is nullable on purpose and null is the common case. For most of
    these gaps the size is genuinely unknown — counting the NYC employers on
    Workday would mean enumerating NYC employers, which is the problem itself —
    and reporting ``0`` there would be a fabricated statistic. Null renders as
    "unknown" and the page says so in words.
    """

    id: str
    title: str
    explanation: str
    count: int | None = Field(
        default=None,
        description="Size of the gap, or null when it is genuinely unknown. Never 0 as a stand-in.",
    )


class BoardCoverageOut(BaseModel):
    total: int
    pollable: int
    by_ats: dict[str, int]
    by_status: dict[str, int]
    with_nyc_presence: int


class CoverageOut(BaseModel):
    """What is covered, and what is not.

    Deliberately carries **no percentage of the market**. There is no
    denominator: nobody knows how many tech roles open in New York, so any such
    figure would be arithmetic on a number nobody has. The M1 criterion this
    schema serves is that the gaps are named, not that the coverage is high.
    """

    boards: BoardCoverageOut
    candidates: dict[str, int]
    candidates_total: int
    blind_spots: list[BlindSpotOut]


class ApplicationEventOut(BaseModel):
    """One history row. `occurred_at` is world time; `created_at` is write time."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: ApplicationEventType
    actor: EventActor
    occurred_at: datetime
    from_stage: ApplicationStage | None
    to_stage: ApplicationStage | None
    transition_class: TransitionClass | None
    body: str | None
    payload: dict[str, Any]
    created_at: datetime


class ApplicationOut(BaseModel):
    id: UUID
    job: JobSummaryOut
    current_stage: ApplicationStage
    priority: ApplicationPriority
    applied_at: datetime | None
    next_action_at: datetime | None
    application_url: str | None
    source_of_application: str | None
    selected_resume_id: UUID | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationDetailOut(ApplicationOut):
    events: list[ApplicationEventOut]


class ApplicationStageCounts(BaseModel):
    """One field per stage, defaulting to zero.

    Same shape as `JobStatusCounts`, and for the same reason: a missing key and
    a zero must not be told apart by whether the UI happened to check.
    """

    discovered: int = 0
    saved: int = 0
    preparing: int = 0
    applied: int = 0
    assessment: int = 0
    interview: int = 0
    offer: int = 0
    rejected: int = 0
    withdrawn: int = 0
    closed: int = 0


class DeferredApplicationFieldOut(BaseModel):
    """I7: what tracking cannot yet record, named rather than hidden."""

    name: str
    blocked_on: str
    reason: str


class ApplicationListOut(BaseModel):
    items: list[ApplicationOut]
    total: int
    limit: int
    offset: int
    stage_counts: ApplicationStageCounts
    archived_count: int
    deferred_fields: list[DeferredApplicationFieldOut]


class QueueRowOut(BaseModel):
    """One row. ``because`` is a sentence, not a score — I4.

    ``application_id`` and ``current_stage`` are null together, on the sections
    that offer a posting the reader is not tracking (M3d Task 7). The page links
    to the job in that case, because there is no application to link to.
    """

    application_id: UUID | None
    job_id: UUID
    job_title: str
    company_name: str
    current_stage: ApplicationStage | None
    at: datetime | None
    because: str
    #: The band this suggestion came out of. A *state*, never a number: I4
    #: forbids a bare score and a row here has nowhere to put a breakdown.
    eligibility: EligibilityState | None = None


class QueueSectionBlindSpotOut(BaseModel):
    """What a section could not see, counted and named.

    Serialised even at zero. "Nothing was hidden from this row" is a statement
    worth being able to make, and a spot that appears only when non-zero cannot
    make it — the reader cannot tell a clean run from a field nobody added.
    """

    name: str
    count: int
    because: str


class QueueSectionOut(BaseModel):
    key: QueueSectionKey
    title: str
    rows: list[QueueRowOut]
    #: Before the cap, so the page can say "and N more" honestly.
    total: int
    #: Empty for the four M2d sections, which read committed application state
    #: and can see all of it.
    blind_spots: list[QueueSectionBlindSpotOut] = []
    #: One sentence about the section as a whole, where the rows cannot carry
    #: it. Null where the title says everything.
    note: str | None = None


class DeferredQueueRowOut(BaseModel):
    """I7: a row this system cannot compute yet, named rather than faked.

    Same shape as ``DeferredApplicationFieldOut`` and ``DeferredFilter`` because
    it is the same idea in a third place.
    """

    name: str
    blocked_on: str
    reason: str


class QueueThresholdsOut(BaseModel):
    """The numbers behind the rows, so the page can explain itself without a
    second copy of them in TypeScript.

    M2c's enum-parity defect is the reason this is in the response: two
    vocabularies transcribed by hand into two languages drifted, and nothing
    local could see it.
    """

    follow_up_silent_days: int
    stale_saved_days: int
    interview_horizon_days: int
    row_cap: int


class DailyQueueOut(BaseModel):
    generated_at: datetime
    sections: list[QueueSectionOut]
    total_rows: int
    deferred_rows: list[DeferredQueueRowOut]
    thresholds: QueueThresholdsOut


class SaveJobIn(BaseModel):
    job_id: UUID


class StageChangeIn(BaseModel):
    to_stage: ApplicationStage
    note: str | None = Field(default=None, max_length=4000)
    applied_at: datetime | None = None
    application_url: str | None = Field(default=None, max_length=1000)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime | None = None


class InterviewIn(BaseModel):
    scheduled_for: datetime
    body: str | None = Field(default=None, max_length=4000)


class ApplicationPatchIn(BaseModel):
    """Absent means "leave alone"; explicit null means "clear".

    The route reads `model_fields_set` rather than checking for None, because
    otherwise there is no way to clear `next_action_at` once it is set — the
    field would be permanently sticky and the bug would look like a UI problem.
    """

    priority: ApplicationPriority | None = None
    next_action_at: datetime | None = None
    application_url: str | None = Field(default=None, max_length=1000)
    source_of_application: str | None = Field(default=None, max_length=200)
    applied_at: datetime | None = None
    #: The route checks this resume belongs to the caller before it is stored.
    #: The foreign key alone would happily accept a stranger's id (A3).
    selected_resume_id: UUID | None = None


# ---------------------------------------------------------------------------
# Profile and resumes (M2c)
#
# Two shapes, and the boundary between them is invariant I2. `ExtractionOut` is
# a *proposal* — what a file appears to say, with the characters it says it at.
# `ProfileOut` is what a person confirmed. Nothing moves from the first to the
# second without a `ConfirmIn` carrying their decision.
# ---------------------------------------------------------------------------


class UserSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    proficiency_level: ProficiencyLevel
    source_type: SkillSourceType
    #: Where it came from, in a form a human can follow back:
    #: ``resume:<uuid>#214-229``, or ``manual``.
    source_reference: str | None
    vocabulary_version: str | None
    created_at: datetime


class UserProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    summary: str | None
    evidence: str | None
    repository_url: str | None
    demo_url: str | None
    technologies: list[str]
    status: ProjectStatus
    created_at: datetime


class DeferredProfileFieldOut(BaseModel):
    """I7: what the profile cannot infer, named rather than left blank."""

    name: str
    blocked_on: str
    reason: str


class ProfileOut(BaseModel):
    """Confirmed facts only. Every field here was typed or clicked by a person.

    ``graduation_year`` and ``graduation_month`` rather than a date: a resume
    saying "May 2027" does not name a day, and inventing one to fill a column is
    the fabrication I1 forbids (ADR 0013).
    """

    id: UUID
    email: str
    display_name: str | None
    timezone: str
    graduation_year: int | None
    graduation_month: int | None
    degree: str | None
    school: str | None
    #: M3b gate inputs. Null is "you have not told us" and stays distinct from
    #: 0 and from false — the gate answers `uncertain` for null and would answer
    #: `passes` for 0, which are different things to say to a person.
    years_experience: int | None
    is_enrolled: bool | None
    work_authorization: WorkAuthorization
    home_location_text: str | None
    remote_preference: RemotePreference
    minimum_salary: int | None
    preferred_roles: list[str]
    preferred_locations: list[str]
    skills: list[UserSkillOut]
    projects: list[UserProjectOut]
    deferred_fields: list[DeferredProfileFieldOut]


class ProfilePatchIn(BaseModel):
    """Absent means "leave alone"; explicit null means "clear".

    Same rule as :class:`ApplicationPatchIn`, and for the same reason: without
    it there is no way to unset a graduation year once it is set.
    """

    display_name: str | None = Field(default=None, max_length=200)
    graduation_year: int | None = Field(default=None, ge=1900, le=2100)
    graduation_month: int | None = Field(default=None, ge=1, le=12)
    degree: str | None = Field(default=None, max_length=200)
    school: str | None = Field(default=None, max_length=300)
    #: `ge=0` mirrors the check constraint. A negative figure would pass every
    #: experience requirement in the gate, so it is refused at both edges.
    years_experience: int | None = Field(default=None, ge=0, le=80)
    is_enrolled: bool | None = None
    work_authorization: WorkAuthorization | None = None
    home_location_text: str | None = Field(default=None, max_length=300)
    remote_preference: RemotePreference | None = None
    minimum_salary: int | None = Field(default=None, ge=0)
    preferred_roles: list[str] | None = None
    preferred_locations: list[str] | None = None


class SkillIn(BaseModel):
    """The manual path — §6.2's fallback, and where "nothing could be proven
    from this file" hands over to."""

    name: str = Field(min_length=1, max_length=120)
    proficiency_level: ProficiencyLevel = ProficiencyLevel.UNSPECIFIED


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=4000)
    evidence: str | None = Field(default=None, max_length=8000)
    repository_url: str | None = Field(default=None, max_length=500)
    demo_url: str | None = Field(default=None, max_length=500)
    technologies: list[str] = Field(default_factory=list)
    status: ProjectStatus = ProjectStatus.COMPLETED


class ExtractionOut(BaseModel):
    """A proposal, and the characters it came from.

    ``char_start``/``char_end`` index into :attr:`ResumeDetailOut.parsed_text`,
    and ``quoted_text`` is what that slice must contain. The database enforces
    it with a trigger; `test_every_proposal_in_the_response_quotes_the_parsed_text`
    enforces it again here, where the browser reads it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: ExtractionKind
    value: dict[str, Any]
    char_start: int
    char_end: int
    quoted_text: str
    status: ExtractionStatus
    extractor_version: str
    decided_at: datetime | None


class ExtractionCounts(BaseModel):
    """Same shape rule as `ApplicationStageCounts`: a zero, never a missing key."""

    pending: int = 0
    confirmed: int = 0
    rejected: int = 0


class ResumeOut(BaseModel):
    """One resume, without its text. **The uploaded bytes are never stored** —
    what survives is the filename, a hash of the text, and the text itself."""

    id: UUID
    name: str
    variant_type: ResumeVariant
    source_kind: ResumeSourceKind
    original_filename: str | None
    content_hash: str
    is_default: bool
    extraction_counts: ExtractionCounts
    created_at: datetime
    updated_at: datetime


class ResumeDetailOut(ResumeOut):
    """The text the extractor actually read, plus every proposal over it.

    ``parsed_text`` is here so the confirmation screen can show the words rather
    than a tidy form — a scrambled two-column PDF extraction is then visible
    instead of hidden, which is what makes accepting PDFs safe.
    """

    parsed_text: str
    extractions: list[ExtractionOut]
    nothing_proven: bool = Field(
        description="No proposal could be made from this text. Stated, never "
        "papered over with a half-filled form (I7)."
    )


class ResumeListOut(BaseModel):
    items: list[ResumeOut]
    total: int


class ResumePasteIn(BaseModel):
    name: str = Field(default="Pasted resume", min_length=1, max_length=200)
    text: str = Field(min_length=1)
    variant_type: ResumeVariant = ResumeVariant.CUSTOM


class ResumePatchIn(BaseModel):
    """Rename, retype, or make default. Nothing here re-reads the text —
    proposals are made once, so a decision already made is never stranded."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    variant_type: ResumeVariant | None = None
    is_default: bool | None = None


class ExtractionDecisionIn(BaseModel):
    extraction_id: UUID
    decision: Literal["confirm", "reject"]


class ConfirmIn(BaseModel):
    decisions: list[ExtractionDecisionIn] = Field(min_length=1)


class ConfirmationOut(BaseModel):
    """What the click did, counted. ``skipped`` is a proposal already decided —
    reported rather than refused, so a double-submitted form is not an error."""

    confirmed: int
    rejected: int
    skipped: int
    skills_added: int
    projects_added: int
    profile_fields_set: list[str]


# ---------------------------------------------------------------------------
# The city (M4c)
# ---------------------------------------------------------------------------


class PlacementOut(BaseModel):
    """Where one role is drawn, and why it is drawn there.

    I1 with its teeth showing. ``kind`` is the only thing the renderer is
    allowed to branch on, and there is no shape it can produce from a
    coordinate alone: an ``unresolved`` placement has no coordinates at all, and
    a ``building`` cannot exist below ``verified``.

    ``inherited`` is the field that keeps two different sentences apart, and it
    is the reason this schema is not just a lat/lng pair. ``location_confidence``
    describes the *coordinate* — an office resolved from a confirmed street
    address really is verified. It says nothing about the claim that this role
    sits at it. When ``inherited`` is true the honest sentence is "this posting
    named no address; its employer's confirmed office is here", and ``stated``
    carries what the posting did say so the panel can show both.
    """

    kind: PlacementKind
    latitude: float | None
    longitude: float | None
    building_id: str | None = Field(
        description="NYC Building Identification Number, when the office carried one"
    )
    location_confidence: LocationConfidence
    resolution_method: ResolutionMethod
    stated: str | None = Field(description="What the posting itself said about where it is")
    inherited: bool
    office_label: str | None
    office_address: str | None


class CitySignalOut(BaseModel):
    """One role on the map: enough to draw it, name it and open it.

    Deliberately not :class:`JobSummaryOut`. The map asks for thousands of these
    at once and needs none of the salary or the location list; sending them
    would multiply the payload for fields no beacon reads. The detail panel
    fetches the full job by id, the way the list view already does.

    ``first_seen_at`` is the one source timestamp that survived that cut, and it
    is here because `city.md` §4.8 asks for a field that is **sortable**. Every
    other ordering the field offers can be derived from what is already on this
    model; "newest first" cannot, and on a corpus where every role floats it is
    the ordering a person actually wants. Sending it costs one timestamp per
    role and saves the alternative, which is a second round trip per column.
    """

    job_id: UUID
    title: str
    company_id: UUID
    company_name: str
    employment_type: EmploymentType
    remote_policy: RemotePolicy
    status: JobStatus
    #: When ingestion first saw this role — *not* when the employer posted it.
    #: No ATS in this corpus publishes a reliable posting date, and naming this
    #: field ``posted_at`` would turn "we noticed this on Tuesday" into "this
    #: was posted on Tuesday", which is a claim nobody measured.
    first_seen_at: datetime
    placement: PlacementOut


class PlacementCounts(BaseModel):
    """The honest coverage readout, per §4.7, in the payload that draws the map.

    On this corpus ``unresolved`` is expected to be the total and the other two
    zero, and that is the milestone rather than a shortfall — no ATS posting
    names a street (§4.1). A client that wants to say "247 roles, none of them
    placeable" has the numbers to say it without counting the array itself.
    """

    building: int = 0
    area: int = 0
    unresolved: int = 0
    total: int = 0


class CitySignalsOut(BaseModel):
    signals: list[CitySignalOut]
    counts: PlacementCounts
    limit: int
    truncated: bool = Field(
        description="True when more roles matched than were returned. The map says so on screen."
    )
