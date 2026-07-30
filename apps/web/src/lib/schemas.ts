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

export const jobListSchema = z.object({
  items: z.array(jobSummarySchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
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
});
export type SourceHealth = z.infer<typeof sourceHealthSchema>;
