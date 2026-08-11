/**
 * Zod schemas for everything crossing the network boundary (CLAUDE.md §7).
 *
 * These are not duplicated documentation — they are the enforcement point. If
 * the API ever sends a location without a `location_confidence`, or sends a
 * confidence value outside the five allowed by invariant I1, parsing fails
 * loudly here instead of rendering a coordinate with no precision claim.
 */

import { z } from 'zod';

/** Invariant I1. Five values, no sixth, no default. */
export const locationConfidenceSchema = z.enum([
  'verified',
  'approximate',
  'city_only',
  'remote',
  'unknown',
]);
export type LocationConfidence = z.infer<typeof locationConfidenceSchema>;

export const resolutionMethodSchema = z.enum([
  'not_attempted',
  'source_text_parse',
  'nyc_geosearch',
  'nominatim',
  'neighborhood_centroid',
  'manual',
]);

export const jobStatusSchema = z.enum(['open', 'possibly_stale', 'unverified', 'closed']);
export type JobStatus = z.infer<typeof jobStatusSchema>;

export const employmentTypeSchema = z.enum([
  'full_time',
  'part_time',
  'internship',
  'contract',
  'temporary',
  'unknown',
]);

export const remotePolicySchema = z.enum(['on_site', 'hybrid', 'remote', 'unknown']);

export const jobLocationSchema = z
  .object({
    id: z.string().uuid(),
    raw_text: z.string(),
    city: z.string().nullable(),
    state: z.string().nullable(),
    country: z.string().nullable(),
    latitude: z.number().nullable(),
    longitude: z.number().nullable(),
    location_confidence: locationConfidenceSchema,
    resolution_method: resolutionMethodSchema,
    is_primary: z.boolean(),
  })
  .superRefine((location, ctx) => {
    // I1, enforced on the client too. The database has the same constraint;
    // duplicating it here means a bug in the API cannot put a point on a map
    // without a precision claim that justifies it.
    const hasPoint = location.latitude !== null && location.longitude !== null;
    const claimsPrecision =
      location.location_confidence === 'verified' || location.location_confidence === 'approximate';
    if (hasPoint !== claimsPrecision) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message:
          `location ${location.id}: coordinates (${hasPoint}) disagree with ` +
          `confidence "${location.location_confidence}" — refusing to render a ` +
          `position that the confidence does not support (invariant I1)`,
      });
    }
  });
export type JobLocation = z.infer<typeof jobLocationSchema>;

export const companySchema = z.object({
  id: z.string().uuid(),
  canonical_name: z.string(),
  website: z.string().nullable(),
});

/** A10: `provided` is the flag the UI uses to say "not provided by source". */
export const salarySchema = z.object({
  provided: z.boolean(),
  minimum: z.number().nullable().default(null),
  maximum: z.number().nullable().default(null),
  currency: z.string().nullable().default(null),
  period: z.string().nullable().default(null),
});
export type Salary = z.infer<typeof salarySchema>;

export const jobSummarySchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  company: companySchema,
  employment_type: employmentTypeSchema,
  remote_policy: remotePolicySchema,
  status: jobStatusSchema,
  locations: z.array(jobLocationSchema),
  salary: salarySchema,
  source_published_at: z.string().datetime({ offset: true }).nullable(),
  source_updated_at: z.string().datetime({ offset: true }).nullable(),
  first_seen_at: z.string().datetime({ offset: true }),
  last_seen_at: z.string().datetime({ offset: true }),
  application_deadline: z.string().datetime({ offset: true }).nullable(),
});
export type JobSummary = z.infer<typeof jobSummarySchema>;

/** A filter the spec asks for that this milestone will not fake. */
export const deferredFilterSchema = z.object({
  name: z.string(),
  blocked_on: z.string(),
  reason: z.string(),
});
export type DeferredFilter = z.infer<typeof deferredFilterSchema>;

export const jobSourceSchema = z.object({
  source_name: z.string(),
  source_job_id: z.string(),
  canonical_url: z.string().nullable(),
  first_seen_at: z.string().datetime({ offset: true }),
  last_seen_at: z.string().datetime({ offset: true }),
});
export type JobSource = z.infer<typeof jobSourceSchema>;

export const requirementKindSchema = z.enum([
  'degree',
  'graduation_window',
  'years_experience',
  'technology',
  'authorization',
  'enrollment',
  'role_level',
]);
export type RequirementKind = z.infer<typeof requirementKindSchema>;

export const requirementNecessitySchema = z.enum(['required', 'preferred', 'mentioned']);
export type RequirementNecessity = z.infer<typeof requirementNecessitySchema>;

/**
 * One thing a posting asks for, and the characters where it says so.
 *
 * `raw_text` travels with the offsets rather than being re-derived in the
 * browser, so the two can be checked against each other — see the refinement
 * on `jobDetailSchema`, which is the only place that holds both this row and
 * the text it points at.
 */
export const jobRequirementSchema = z.object({
  kind: requirementKindSchema,
  value: z.string(),
  raw_text: z.string(),
  char_start: z.number().int().nonnegative(),
  char_end: z.number().int().nonnegative(),
  necessity: requirementNecessitySchema,
  has_equivalence: z.boolean(),
});
export type JobRequirement = z.infer<typeof jobRequirementSchema>;

/**
 * The five states from PRODUCT-SPEC §8.3, and the browser must know all five.
 * `matching.md` §5.2: a state is never converted into points and never
 * collapsed into a number, so it crosses the boundary as itself.
 */
export const eligibilityStateSchema = z.enum([
  'eligible',
  'likely_eligible',
  'uncertain',
  'likely_ineligible',
  'ineligible',
]);
export type EligibilityState = z.infer<typeof eligibilityStateSchema>;

export const roleFamilySchema = z.enum([
  'software_engineering',
  'data_engineering',
  'ml_ai',
  'infrastructure',
  'security',
  'quant_trading',
  'hardware',
  'product',
  'design',
  'not_tech',
  'unclear',
]);
export type RoleFamily = z.infer<typeof roleFamilySchema>;

export const senioritySchema = z.enum([
  'internship',
  'new_grad',
  'junior',
  'mid',
  'senior',
  'staff',
  'director',
  'unclear',
]);
export type Seniority = z.infer<typeof senioritySchema>;

/**
 * The academic terms, and not the year — that is `internship_year`, a separate
 * field. Two of the recorded corpus's nineteen internships state a year and no
 * season, so a combined `summer_2027` value could keep them only by inventing
 * the season.
 *
 * No `unclear` member, unlike the two enums above. A season is quoted out of a
 * title or it is absent, and `null` carries the whole of "the posting did not
 * say".
 */
export const internshipSeasonSchema = z.enum(['summer', 'fall', 'winter', 'spring']);
export type InternshipSeason = z.infer<typeof internshipSeasonSchema>;

/**
 * A reason a posting may not be open to this person, with the posting's own
 * words. `outcome` separates a wall from a gap: `blocks` is a stated
 * requirement the profile contradicts, `soft_blocks` is a shortfall the person
 * may well decide to ignore, and rendering them identically would turn the
 * second into the first.
 */
export const eligibilityBlockerSchema = z.object({
  dimension: z.string(),
  outcome: z.enum(['blocks', 'soft_blocks']),
  posting_says: z.string().nullable(),
  char_start: z.number().int().nonnegative().nullable(),
  char_end: z.number().int().nonnegative().nullable(),
  profile_says: z.string(),
  why: z.string(),
});
export type EligibilityBlocker = z.infer<typeof eligibilityBlockerSchema>;

/**
 * Something the gate could not decide. Distinct from a blocker on purpose: a
 * blocker is a wall, this is an open question.
 *
 * `profile_field` is where the page links to, and it is **nullable** because
 * some questions have no answer a person could supply — a posting saying
 * "or equivalent experience" is unassessable however complete the profile is.
 * A link there is an action that cannot work, so the page renders none.
 */
export const eligibilityUnknownSchema = z.object({
  dimension: z.string(),
  profile_field: z.string().nullable(),
  why: z.string(),
});
export type EligibilityUnknown = z.infer<typeof eligibilityUnknownSchema>;

export const eligibilitySchema = z.object({
  state: eligibilityStateSchema,
  blockers: z.array(eligibilityBlockerSchema),
  unknowns: z.array(eligibilityUnknownSchema),
  gate_version: z.string(),
});
export type Eligibility = z.infer<typeof eligibilitySchema>;

/**
 * The six things a score is made of (`matching.md` §4.3, §5.1). Deliberately
 * not the weight file's key names — those name a weight, these name a kind of
 * claim.
 */
export const matchComponentSchema = z.enum([
  'role',
  'skill',
  'project',
  'location',
  'freshness',
  'priority',
]);
export type MatchComponent = z.infer<typeof matchComponentSchema>;

/**
 * Which of the posting's strings a span's offsets index into. Everything else
 * in this system points at `description_text`; role relevance is decided on the
 * **title** and cannot be otherwise, so a highlight that ignored this field
 * would underline the wrong text and look entirely plausible doing it.
 */
export const jobTextFieldSchema = z.enum(['title', 'description_text']);
export type JobTextField = z.infer<typeof jobTextFieldSchema>;

/**
 * Who proposed an evidence row. What makes the semantic layer auditable: it is
 * possible to ask what share of the awarded points came from an embedding
 * rather than from a vocabulary hit. Every row says `rule` until M3c Task 11.
 */
export const evidenceSourceSchema = z.enum(['rule', 'embedding']);
export type EvidenceSource = z.infer<typeof evidenceSourceSchema>;

/** The two subtractions a score can carry (`matching.md` §5.1, §5.1.3). */
export const penaltyNameSchema = z.enum(['missing_requirement', 'seniority_mismatch']);
export type PenaltyName = z.infer<typeof penaltyNameSchema>;

/**
 * One link a score rests on, with both sides quoted (§4.3). This is invariant
 * I4's payload — a client that renders `points` without these has thrown the
 * breakdown away rather than never having had it.
 *
 * The two nullable sides are §2.1's distinction, not missing data. `role`,
 * `skill` and `project` carry both spans because they claim something about the
 * person; `location`, `freshness` and `priority` carry `compared` instead,
 * because there is no qualification being asserted and inventing a span is the
 * failure the whole arrangement prevents.
 */
export const matchEvidenceSchema = z.object({
  component: matchComponentSchema,
  points: z.number().int(),
  job_span_text: z.string().nullable(),
  job_span_field: jobTextFieldSchema.nullable(),
  job_char_start: z.number().int().nonnegative().nullable(),
  job_char_end: z.number().int().nonnegative().nullable(),
  user_span_text: z.string().nullable(),
  user_skill_id: z.string().nullable(),
  user_project_id: z.string().nullable(),
  compared: z.record(z.unknown()).default({}),
  proposed_by: evidenceSourceSchema,
  job_requirement_id: z.string().nullable().default(null),
});
export type MatchEvidence = z.infer<typeof matchEvidenceSchema>;

/**
 * One component: its points, what they were out of, and its own sentence.
 *
 * **`assessable` is not "did it score".** False means the posting did not say
 * enough to ask the question, and §5.1.1 keeps that separate from zero because
 * collapsing them charges a terse posting up to 50 points for its employer's
 * prose. The stored number is `0` either way, which is why this field crosses
 * the boundary instead of being inferred from the points.
 */
export const matchComponentDetailSchema = z.object({
  component: matchComponentSchema,
  points: z.number().int(),
  weight: z.number().int(),
  assessable: z.boolean(),
  why: z.string(),
  evidence: z.array(matchEvidenceSchema).default([]),
});
export type MatchComponentDetail = z.infer<typeof matchComponentDetailSchema>;

/**
 * One of the two subtractions, with what it cost and why.
 *
 * `applicable: false` is not "cost nothing" — it is *there was nothing to ask*.
 * Both store `points: 0` and only `why` tells them apart from *nothing was
 * missing*, the same distinction `assessable` draws one level up.
 */
export const matchPenaltySchema = z.object({
  name: penaltyNameSchema,
  points: z.number().int(),
  applicable: z.boolean(),
  why: z.string(),
  compared: z.record(z.unknown()).default({}),
});
export type MatchPenalty = z.infer<typeof matchPenaltySchema>;

/** A §8.2 component this milestone does not score, named on the page (§5.1). */
export const deferredComponentSchema = z.object({
  name: z.string(),
  weight: z.number().int(),
  blocked_on: z.string(),
  reason: z.string(),
});
export type DeferredComponent = z.infer<typeof deferredComponentSchema>;

/**
 * A stored score, decomposed. Never a bare number (I4).
 *
 * **`fraction` is the ranking key and it is nullable.** `overall_score` is out
 * of `assessed_out_of`, which is not always 100, so raw totals are not
 * comparable across postings. `null` means nothing could be assessed at all and
 * is deliberately not `0.0`, which would sort such a posting last as though it
 * had been measured and found wanting.
 *
 * **`eligibility_status` sits beside the number and is never inside it** (§5.2).
 * A posting can be an 82 and `uncertain`, and this object states both without
 * reconciling them.
 */
export const matchSchema = z.object({
  overall_score: z.number().int(),
  assessed_out_of: z.number().int(),
  fraction: z.number().nullable(),
  eligibility_status: eligibilityStateSchema,
  components: z.array(matchComponentDetailSchema),
  penalty_score: z.number().int(),
  penalties: z.array(matchPenaltySchema).default([]),
  deferred_components: z.array(deferredComponentSchema).default([]),
  ruleset_version: z.string(),
  model_version: z.string().nullable(),
  computed_at: z.string(),
});
export type Match = z.infer<typeof matchSchema>;

/**
 * Something the posting asks for that no evidence row answers (§6). `required`
 * rows are *why it may not fit*; `preferred` rows are *soft gaps*. Rendering
 * them alike turns a nice-to-have into a bar, which is why `necessity` crosses
 * the boundary rather than the API sending two lists that could disagree.
 */
export const unmetRequirementSchema = z.object({
  kind: requirementKindSchema,
  value: z.string(),
  raw_text: z.string(),
  char_start: z.number().int().nonnegative(),
  char_end: z.number().int().nonnegative(),
  necessity: requirementNecessitySchema,
  has_equivalence: z.boolean(),
});
export type UnmetRequirement = z.infer<typeof unmetRequirementSchema>;

export const jobDetailSchema = jobSummarySchema
  .extend({
    description_text: z.string().nullable(),
    description_html: z.string().nullable(),
    sources: z.array(jobSourceSchema),
    requirements: z.array(jobRequirementSchema),
    /**
     * The stored score at the current ruleset version. **Null means not yet
     * computed** and covers three situations with one honest sentence: the
     * sweep has not reached this pair, the posting has no description to read,
     * or the stored row predates a ruleset bump. None of them is a number.
     */
    match: matchSchema.nullable().default(null),
    /**
     * Null rather than `[]` when `match` is null. Without a score there are no
     * evidence rows to difference against, and an empty list would read as
     * "you meet everything" — a claim about a person computed from nothing.
     */
    unmet_requirements: z.array(unmetRequirementSchema).nullable().default(null),
    /**
     * Null when nothing has been extracted. An empty `requirements` with a
     * version is "we read it and found nothing"; an empty one without is "we
     * have not read it". The page renders those differently and cannot do so
     * unless this field survives the boundary.
     */
    requirements_extractor_version: z.string().nullable(),
    /**
     * Null when the posting has no extracted requirements. A verdict from an
     * unread posting would say `eligible` to everyone and be indistinguishable
     * on the page from a posting that genuinely asks for nothing.
     */
    eligibility: eligibilitySchema.nullable(),
  })
  .superRefine((detail, ctx) => {
    // The same check `resumeDetailSchema` makes, for the same reason: only the
    // parent holds the text, so only the parent can tell a span of the right
    // *length* from one pointing at the right *words*. The page highlights
    // against this text, so a drifting offset would underline the wrong
    // sentence and still look entirely plausible.
    if (detail.description_text === null) return;
    detail.requirements.forEach((row, index) => {
      if (detail.description_text!.slice(row.char_start, row.char_end) !== row.raw_text) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'this requirement does not quote the text it points at',
          path: ['requirements', index, 'raw_text'],
        });
      }
    });
  });
export type JobDetail = z.infer<typeof jobDetailSchema>;

export const jobListSchema = z.object({
  items: z.array(jobSummarySchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
  // Defaulted so a response from an API that predates these fields still
  // parses rather than throwing at the boundary.
  excluded_no_salary: z.number().int().default(0),
  /**
   * How many jobs the skill filter could not have matched however well it
   * works, because nothing was extracted from them. Required-technology recall
   * is 0.861 against the answer key, so the filter is usable and incomplete;
   * without this number a thin result reads as "there are only two such jobs".
   */
  excluded_no_requirements: z.number().int().default(0),
  /**
   * How many internships the season filter necessarily hid, because their
   * titles state no season (11 of 19 in the recorded corpus) or no year.
   */
  excluded_no_season: z.number().int().default(0),
  deferred_filters: z.array(deferredFilterSchema).default([]),
});
export type JobList = z.infer<typeof jobListSchema>;

/** One row of the ranked list. The score is not optional: a posting nobody has
 * scored cannot be ranked, and is counted in `not_yet_scored` instead. */
export const rankedJobSchema = z.object({
  job: jobSummarySchema,
  match: matchSchema,
});
export type RankedJob = z.infer<typeof rankedJobSchema>;

/**
 * One eligibility band and the postings inside it, best first (§5.3).
 *
 * **The band is a heading, never points.** Grouping by eligibility and sorting
 * by score inside the group is the compromise between two things that both
 * matter: a list where a hard blocker does not affect position is not usable,
 * and a score that has silently absorbed a penalty for uncertainty is a lie.
 */
export const rankedBandSchema = z.object({
  state: eligibilityStateSchema,
  items: z.array(rankedJobSchema),
  unassessed: z.number().int().default(0),
});
export type RankedBand = z.infer<typeof rankedBandSchema>;

export const matchRankingSchema = z.object({
  bands: z.array(rankedBandSchema),
  total: z.number().int(),
  /**
   * Open postings with no score at the current ruleset version. Rendered, not
   * swallowed: a ranked list covering 12 of 31 postings looks exactly like one
   * covering all 31.
   */
  not_yet_scored: z.number().int(),
  ruleset_version: z.string(),
  unassessed_sort_last: z.literal(true).default(true),
  // What the list is sorted by. The printed fraction and the ordering key are
  // deliberately different: rows show "of what could be assessed", and the sort
  // weights that by how much was assessed, so 17% can sit above 30%.
  ordering: z.literal('coverage_weighted_fraction').default('coverage_weighted_fraction'),
  deferred_components: z.array(deferredComponentSchema).default([]),
});
export type MatchRanking = z.infer<typeof matchRankingSchema>;

export const healthComponentSchema = z.object({
  ok: z.boolean(),
  detail: z.string().nullable(),
  latency_ms: z.number().nullable(),
});
export type HealthComponent = z.infer<typeof healthComponentSchema>;

export const healthSchema = z.object({
  status: z.string(),
  version: z.string(),
  environment: z.string(),
  database: healthComponentSchema,
  redis: healthComponentSchema,
  checked_at: z.string(),
});
export type Health = z.infer<typeof healthSchema>;

export const locationConfidenceBreakdownSchema = z.object({
  verified: z.number().int(),
  approximate: z.number().int(),
  city_only: z.number().int(),
  remote: z.number().int(),
  unknown: z.number().int(),
});

export const statsSchema = z.object({
  total_jobs: z.number().int(),
  open_jobs: z.number().int(),
  total_companies: z.number().int(),
  total_source_records: z.number().int(),
  location_confidence: locationConfidenceBreakdownSchema,
  mappable_locations: z.number().int(),
});
export type Stats = z.infer<typeof statsSchema>;

/**
 * The four closure states, and how many jobs are in each.
 *
 * Every field is required rather than optional. The API always sends all four,
 * including the zeros, because "no closed jobs" and "the API did not mention
 * closed jobs" are different claims and a UI that cannot tell them apart will
 * eventually report the wrong one.
 */
export const jobStatusCountsSchema = z.object({
  open: z.number().int().nonnegative(),
  possibly_stale: z.number().int().nonnegative(),
  unverified: z.number().int().nonnegative(),
  closed: z.number().int().nonnegative(),
});
export type JobStatusCounts = z.infer<typeof jobStatusCountsSchema>;

export const companyRowSchema = z.object({
  id: z.string().uuid(),
  canonical_name: z.string(),
  website: z.string().nullable(),
  job_count: z.number().int(),
});
export type CompanyRow = z.infer<typeof companyRowSchema>;

export const companyListSchema = z.object({
  items: z.array(companyRowSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type CompanyList = z.infer<typeof companyListSchema>;

export const companyDetailSchema = z.object({
  id: z.string().uuid(),
  canonical_name: z.string(),
  website: z.string().nullable(),
  job_status_counts: jobStatusCountsSchema,
  // Ours, not the employer's. Never rendered as "hiring since".
  first_seen_at: z.string().datetime({ offset: true }).nullable(),
});
export type CompanyDetail = z.infer<typeof companyDetailSchema>;

export const jobAdminRowSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  company_name: z.string(),
  status: jobStatusSchema,
  first_seen_at: z.string(),
  last_seen_at: z.string(),
  closed_at: z.string().nullable(),
  source_count: z.number().int().nonnegative(),
  location_count: z.number().int().nonnegative(),
  merge_count: z.number().int().nonnegative(),
});
export type JobAdminRow = z.infer<typeof jobAdminRowSchema>;

export const jobAdminListSchema = z.object({
  items: z.array(jobAdminRowSchema),
  total: z.number().int().nonnegative(),
  status_counts: jobStatusCountsSchema,
});
export type JobAdminList = z.infer<typeof jobAdminListSchema>;

export const jobStatusEventSchema = z.object({
  from_status: jobStatusSchema.nullable(),
  to_status: jobStatusSchema,
  reason: z.string(),
  observed_misses: z.number().int().nullable(),
  created_at: z.string(),
});
export type JobStatusEvent = z.infer<typeof jobStatusEventSchema>;

export const sourceHealthSchema = z.object({
  name: z.string(),
  source_type: z.string(),
  is_enabled: z.boolean(),
  last_success_at: z.string().nullable(),
  last_failure_at: z.string().nullable(),
  job_count: z.number().int(),
  last_run_status: z.enum(['running', 'succeeded', 'partial', 'failed']).nullable(),
  last_run_started_at: z.string().nullable(),
  last_run_error: z.string().nullable(),
  job_status_counts: jobStatusCountsSchema,
});
export type SourceHealth = z.infer<typeof sourceHealthSchema>;

/**
 * One board's polling state (M1d, ADR 0007).
 *
 * `last_success_at` — not any posting's timestamp — is what "fresh" means for a
 * board. A board answering 304 for sixty days leaves its postings' timestamps
 * sixty days old while those postings are open and correctly so, because a 304
 * ages nothing. Computing staleness from posting timestamps would report a
 * perfectly healthy board as rotten.
 *
 * `last_status` is carried so 304 stays distinguishable from 200. Both are
 * success, and a surface that renders "nothing changed" as a warning teaches
 * people to ignore warnings.
 */
export const boardPollStateSchema = z.object({
  ats: z.string(),
  token: z.string(),
  tier: z.enum(['hot', 'warm']),
  last_status: z.number().int().nullable(),
  last_polled_at: z.string().nullable(),
  last_success_at: z.string().nullable(),
  last_error: z.string().nullable(),
  consecutive_failures: z.number().int(),
  next_poll_at: z.string(),
  has_etag: z.boolean(),
});
export type BoardPollState = z.infer<typeof boardPollStateSchema>;

/**
 * One thing this system cannot see, and why.
 *
 * `count` is nullable and null is the common case: for most of these gaps the
 * size is genuinely unknown, and rendering `0` instead would turn "we cannot
 * know" into "there is no gap". The UI must print the word "unknown" rather
 * than coercing this to a number.
 */
export const blindSpotSchema = z.object({
  id: z.string(),
  title: z.string(),
  explanation: z.string(),
  count: z.number().int().nonnegative().nullable(),
});
export type BlindSpot = z.infer<typeof blindSpotSchema>;

export const coverageSchema = z.object({
  boards: z.object({
    total: z.number().int().nonnegative(),
    pollable: z.number().int().nonnegative(),
    by_ats: z.record(z.string(), z.number().int().nonnegative()),
    by_status: z.record(z.string(), z.number().int().nonnegative()),
    with_nyc_presence: z.number().int().nonnegative(),
  }),
  candidates: z.record(z.string(), z.number().int().nonnegative()),
  candidates_total: z.number().int().nonnegative(),
  blind_spots: z.array(blindSpotSchema).min(1, 'a coverage report with no named gaps is a bug'),
});
export type Coverage = z.infer<typeof coverageSchema>;

export const applicationStageSchema = z.enum([
  'discovered',
  'saved',
  'preparing',
  'applied',
  'assessment',
  'interview',
  'offer',
  'rejected',
  'withdrawn',
  'closed',
]);
export type ApplicationStage = z.infer<typeof applicationStageSchema>;

export const applicationPrioritySchema = z.enum(['high', 'normal', 'low']);
export type ApplicationPriority = z.infer<typeof applicationPrioritySchema>;

export const transitionClassSchema = z.enum(['advance', 'correction', 'reopen']);
export type TransitionClass = z.infer<typeof transitionClassSchema>;

export const applicationEventTypeSchema = z.enum([
  'saved',
  'stage_changed',
  'note_added',
  'detail_updated',
  'interview_scheduled',
  'archived',
  'restored',
  'listing_closed',
]);
export type ApplicationEventType = z.infer<typeof applicationEventTypeSchema>;

export const applicationEventSchema = z
  .object({
    id: z.string().uuid(),
    event_type: applicationEventTypeSchema,
    actor: z.enum(['user', 'system']),
    occurred_at: z.string().datetime({ offset: true }),
    from_stage: applicationStageSchema.nullable(),
    to_stage: applicationStageSchema.nullable(),
    transition_class: transitionClassSchema.nullable(),
    body: z.string().nullable(),
    payload: z.record(z.unknown()),
    created_at: z.string().datetime({ offset: true }),
  })
  .superRefine((event, ctx) => {
    // The two database check constraints, restated where the UI can see them.
    // Duplicating them here means a bug in the API cannot render a stage badge
    // with no classification behind it, or one the user never asked for.
    if (event.to_stage !== null && event.transition_class === null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'a stage change must carry its classification',
        path: ['transition_class'],
      });
    }
    if (event.to_stage !== null && event.actor !== 'user') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'invariant I5: only a user moves a stage',
        path: ['actor'],
      });
    }
  });
export type ApplicationEvent = z.infer<typeof applicationEventSchema>;

export const applicationSchema = z.object({
  id: z.string().uuid(),
  job: jobSummarySchema,
  current_stage: applicationStageSchema,
  priority: applicationPrioritySchema,
  applied_at: z.string().datetime({ offset: true }).nullable(),
  next_action_at: z.string().datetime({ offset: true }).nullable(),
  application_url: z.string().nullable(),
  source_of_application: z.string().nullable(),
  selected_resume_id: z.string().uuid().nullable(),
  archived_at: z.string().datetime({ offset: true }).nullable(),
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
});
export type Application = z.infer<typeof applicationSchema>;

export const applicationDetailSchema = applicationSchema.extend({
  events: applicationEventSchema.array(),
});
export type ApplicationDetail = z.infer<typeof applicationDetailSchema>;

export const applicationStageCountsSchema = z.object({
  discovered: z.number(),
  saved: z.number(),
  preparing: z.number(),
  applied: z.number(),
  assessment: z.number(),
  interview: z.number(),
  offer: z.number(),
  rejected: z.number(),
  withdrawn: z.number(),
  closed: z.number(),
});
export type ApplicationStageCounts = z.infer<typeof applicationStageCountsSchema>;

export const deferredApplicationFieldSchema = z.object({
  name: z.string(),
  blocked_on: z.string(),
  reason: z.string(),
});
export type DeferredApplicationField = z.infer<typeof deferredApplicationFieldSchema>;

export const applicationListSchema = z.object({
  items: applicationSchema.array(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  stage_counts: applicationStageCountsSchema,
  archived_count: z.number(),
  deferred_fields: deferredApplicationFieldSchema.array(),
});
export type ApplicationList = z.infer<typeof applicationListSchema>;

/* -------------------------------------------------------------------------
 * The daily queue (M2d)
 *
 * Read-only. There is no mutation schema here and `command-center.md` §7.3
 * says there is not to be one — the queue suggests, and acting happens on the
 * application page it links to.
 * ---------------------------------------------------------------------- */

export const queueSectionKeySchema = z.enum([
  'follow_up',
  'interviews_approaching',
  'stale_saved',
  'closed_while_saved',
]);
export type QueueSectionKey = z.infer<typeof queueSectionKeySchema>;

export const queueRowSchema = z.object({
  application_id: z.string().uuid(),
  job_id: z.string().uuid(),
  job_title: z.string(),
  company_name: z.string(),
  current_stage: applicationStageSchema,
  at: z.string().datetime({ offset: true }).nullable(),
  // A row with no reason is a bare signal, which is what I4 exists to prevent.
  because: z.string().min(1),
});
export type QueueRow = z.infer<typeof queueRowSchema>;

export const queueSectionSchema = z.object({
  key: queueSectionKeySchema,
  title: z.string().min(1),
  rows: queueRowSchema.array(),
  total: z.number().int().nonnegative(),
});
export type QueueSection = z.infer<typeof queueSectionSchema>;

export const deferredQueueRowSchema = z.object({
  name: z.string().min(1),
  blocked_on: z.string().min(1),
  reason: z.string().min(1),
});
export type DeferredQueueRow = z.infer<typeof deferredQueueRowSchema>;

export const queueThresholdsSchema = z.object({
  follow_up_silent_days: z.number().int().positive(),
  stale_saved_days: z.number().int().positive(),
  interview_horizon_days: z.number().int().positive(),
  row_cap: z.number().int().positive(),
});
export type QueueThresholds = z.infer<typeof queueThresholdsSchema>;

export const dailyQueueSchema = z.object({
  generated_at: z.string().datetime({ offset: true }),
  sections: queueSectionSchema.array(),
  total_rows: z.number().int().nonnegative(),
  deferred_rows: deferredQueueRowSchema.array(),
  thresholds: queueThresholdsSchema,
});
export type DailyQueue = z.infer<typeof dailyQueueSchema>;

/* -------------------------------------------------------------------------
 * Profile and resumes (M2c)
 *
 * Invariant I2 crosses the network here, so it is enforced here. An
 * `Extraction` is a *proposal* — what a file appears to say, and the exact
 * characters it says it at. A `Profile` holds only what a person confirmed.
 * Nothing turns the first into the second except a `confirmExtractions` call
 * carrying their decisions.
 * ------------------------------------------------------------------------- */

export const workAuthorizationSchema = z.enum([
  'unspecified',
  'us_citizen',
  'permanent_resident',
  'f1_student',
  'other_authorized',
  'needs_sponsorship',
]);
export type WorkAuthorization = z.infer<typeof workAuthorizationSchema>;

export const remotePreferenceSchema = z.enum(['no_preference', 'on_site', 'hybrid', 'remote']);
export type RemotePreference = z.infer<typeof remotePreferenceSchema>;

export const proficiencyLevelSchema = z.enum([
  'unspecified',
  'beginner',
  'intermediate',
  'advanced',
]);
export type ProficiencyLevel = z.infer<typeof proficiencyLevelSchema>;

export const skillSourceTypeSchema = z.enum([
  'manual',
  'resume',
  'project',
  'coursework',
  'assessment',
  'github',
  'inferred_pending_confirmation',
]);

export const projectStatusSchema = z.enum(['active', 'completed', 'archived']);

export const resumeSourceKindSchema = z.enum(['paste', 'txt', 'pdf']);
export type ResumeSourceKind = z.infer<typeof resumeSourceKindSchema>;

export const resumeVariantSchema = z.enum([
  'general_swe',
  'backend',
  'full_stack',
  'data_ml',
  'infrastructure',
  'custom',
]);
export type ResumeVariant = z.infer<typeof resumeVariantSchema>;

/**
 * Five kinds and no sixth. There is deliberately no `work_authorization`: a
 * claim about legal status is confirmed in a form, never read off a page, and
 * a value arriving here would mean the API grew a rule I2 forbids.
 */
export const extractionKindSchema = z.enum(['skill', 'graduation', 'degree', 'school', 'project']);
export type ExtractionKind = z.infer<typeof extractionKindSchema>;

export const extractionStatusSchema = z.enum(['pending', 'confirmed', 'rejected']);
export type ExtractionStatus = z.infer<typeof extractionStatusSchema>;

/**
 * One proposal. The refinement is the client's half of the database trigger:
 * the trigger checks the quote against the resume text, and this checks it
 * against the span the row claims. A quote that cannot fit its own span means
 * an offset moved in serialisation, and the highlight would land on the wrong
 * words while still looking authoritative.
 */
export const extractionSchema = z
  .object({
    id: z.string().uuid(),
    kind: extractionKindSchema,
    value: z.record(z.unknown()),
    char_start: z.number().int().nonnegative(),
    char_end: z.number().int().positive(),
    quoted_text: z.string(),
    status: extractionStatusSchema,
    extractor_version: z.string(),
    decided_at: z.string().datetime({ offset: true }).nullable(),
  })
  .superRefine((row, ctx) => {
    if (row.char_end <= row.char_start) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'a proposal with an empty span highlights nothing and still claims something',
        path: ['char_end'],
      });
    }
    if (row.quoted_text.length !== row.char_end - row.char_start) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'invariant I2: the quoted words do not fill the span they claim to come from',
        path: ['quoted_text'],
      });
    }
  });
export type Extraction = z.infer<typeof extractionSchema>;

export const extractionCountsSchema = z.object({
  pending: z.number(),
  confirmed: z.number(),
  rejected: z.number(),
});
export type ExtractionCounts = z.infer<typeof extractionCountsSchema>;

export const resumeSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  variant_type: resumeVariantSchema,
  source_kind: resumeSourceKindSchema,
  original_filename: z.string().nullable(),
  content_hash: z.string(),
  is_default: z.boolean(),
  extraction_counts: extractionCountsSchema,
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
});
export type Resume = z.infer<typeof resumeSchema>;

/**
 * The resume with its text and its proposals. The second refinement is the one
 * `extractionSchema` cannot make on its own: only the parent holds the text, so
 * only the parent can check that a span of the right *length* also points at
 * the right *words*.
 */
export const resumeDetailSchema = resumeSchema
  .extend({
    parsed_text: z.string(),
    extractions: extractionSchema.array(),
    nothing_proven: z.boolean(),
  })
  .superRefine((detail, ctx) => {
    detail.extractions.forEach((row, index) => {
      if (detail.parsed_text.slice(row.char_start, row.char_end) !== row.quoted_text) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'invariant I2: this proposal does not quote the text it points at',
          path: ['extractions', index, 'quoted_text'],
        });
      }
    });
  });
export type ResumeDetail = z.infer<typeof resumeDetailSchema>;

export const resumeListSchema = z.object({
  items: resumeSchema.array(),
  total: z.number(),
});
export type ResumeList = z.infer<typeof resumeListSchema>;

export const userSkillSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  proficiency_level: proficiencyLevelSchema,
  source_type: skillSourceTypeSchema,
  source_reference: z.string().nullable(),
  vocabulary_version: z.string().nullable(),
  created_at: z.string().datetime({ offset: true }),
});
export type UserSkill = z.infer<typeof userSkillSchema>;

export const userProjectSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  summary: z.string().nullable(),
  evidence: z.string().nullable(),
  repository_url: z.string().nullable(),
  demo_url: z.string().nullable(),
  technologies: z.string().array(),
  status: projectStatusSchema,
  created_at: z.string().datetime({ offset: true }),
});
export type UserProject = z.infer<typeof userProjectSchema>;

export const deferredProfileFieldSchema = z.object({
  name: z.string(),
  blocked_on: z.string(),
  reason: z.string(),
});
export type DeferredProfileField = z.infer<typeof deferredProfileFieldSchema>;

/**
 * Confirmed facts only. `graduation_year` and `graduation_month` rather than a
 * date, because "May 2027" does not name a day and inventing one to fill a
 * field is the fabrication I1 forbids.
 */
export const profileSchema = z
  .object({
    id: z.string().uuid(),
    email: z.string(),
    display_name: z.string().nullable(),
    timezone: z.string(),
    graduation_year: z.number().int().nullable(),
    graduation_month: z.number().int().min(1).max(12).nullable(),
    degree: z.string().nullable(),
    school: z.string().nullable(),
    work_authorization: workAuthorizationSchema,
    home_location_text: z.string().nullable(),
    remote_preference: remotePreferenceSchema,
    minimum_salary: z.number().int().nullable(),
    preferred_roles: z.string().array(),
    preferred_locations: z.string().array(),
    skills: userSkillSchema.array(),
    projects: userProjectSchema.array(),
    deferred_fields: deferredProfileFieldSchema.array(),
  })
  .superRefine((profile, ctx) => {
    // Mirrors the `graduation_month_needs_a_year` check constraint. A month with
    // no year is not a date anyone can act on, and M3's eligibility window would
    // have to guess the missing half.
    if (profile.graduation_month !== null && profile.graduation_year === null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'a graduation month needs a year',
        path: ['graduation_month'],
      });
    }
  });
export type Profile = z.infer<typeof profileSchema>;

export const confirmationSchema = z.object({
  confirmed: z.number(),
  rejected: z.number(),
  skipped: z.number(),
  skills_added: z.number(),
  projects_added: z.number(),
  profile_fields_set: z.string().array(),
});
export type Confirmation = z.infer<typeof confirmationSchema>;
