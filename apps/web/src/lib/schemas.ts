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

export const jobDetailSchema = jobSummarySchema
  .extend({
    description_text: z.string().nullable(),
    description_html: z.string().nullable(),
    sources: z.array(jobSourceSchema),
    requirements: z.array(jobRequirementSchema),
    /**
     * Null when nothing has been extracted. An empty `requirements` with a
     * version is "we read it and found nothing"; an empty one without is "we
     * have not read it". The page renders those differently and cannot do so
     * unless this field survives the boundary.
     */
    requirements_extractor_version: z.string().nullable(),
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
  deferred_filters: z.array(deferredFilterSchema).default([]),
});
export type JobList = z.infer<typeof jobListSchema>;

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
