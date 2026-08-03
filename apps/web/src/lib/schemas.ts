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

export const jobDetailSchema = jobSummarySchema.extend({
  description_text: z.string().nullable(),
  description_html: z.string().nullable(),
  sources: z.array(jobSourceSchema),
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
