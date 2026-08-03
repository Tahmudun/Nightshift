import { describe, expect, it } from 'vitest';

import {
  companyDetailSchema,
  jobDetailSchema,
  jobListSchema,
  jobLocationSchema,
  salarySchema,
} from './schemas';

const baseLocation = {
  id: '11111111-1111-4111-8111-111111111111',
  raw_text: 'New York, New York, USA',
  city: 'New York',
  state: 'New York',
  country: 'USA',
  latitude: null,
  longitude: null,
  location_confidence: 'city_only',
  resolution_method: 'source_text_parse',
  is_primary: true,
};

describe('jobLocationSchema — invariant I1 at the network boundary', () => {
  it('accepts a city-only location with no coordinates', () => {
    expect(jobLocationSchema.safeParse(baseLocation).success).toBe(true);
  });

  it('accepts a verified location that has coordinates', () => {
    const result = jobLocationSchema.safeParse({
      ...baseLocation,
      latitude: 40.7563,
      longitude: -73.9903,
      location_confidence: 'verified',
      resolution_method: 'nyc_geosearch',
    });
    expect(result.success).toBe(true);
  });

  it('rejects coordinates carrying a confidence that does not justify them', () => {
    // The exact fabrication I1 forbids: a precise point labelled "we do not know".
    const result = jobLocationSchema.safeParse({
      ...baseLocation,
      latitude: 40.7563,
      longitude: -73.9903,
      location_confidence: 'unknown',
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toContain('invariant I1');
  });

  it('rejects a verified claim with no coordinates to back it', () => {
    const result = jobLocationSchema.safeParse({
      ...baseLocation,
      location_confidence: 'verified',
    });
    expect(result.success).toBe(false);
  });

  it('rejects a confidence value outside the five allowed', () => {
    const result = jobLocationSchema.safeParse({
      ...baseLocation,
      location_confidence: 'probably_manhattan',
    });
    expect(result.success).toBe(false);
  });

  it('rejects a half-populated coordinate pair', () => {
    const result = jobLocationSchema.safeParse({
      ...baseLocation,
      latitude: 40.7563,
      location_confidence: 'verified',
    });
    expect(result.success).toBe(false);
  });
});

describe('salarySchema', () => {
  it('defaults every absent field to null rather than zero', () => {
    const parsed = salarySchema.parse({ provided: false });
    expect(parsed.minimum).toBeNull();
    expect(parsed.maximum).toBeNull();
    expect(parsed.period).toBeNull();
  });
});

describe('jobListSchema — the honesty fields', () => {
  it('defaults them when an API that predates them responds', () => {
    const parsed = jobListSchema.parse({ items: [], total: 0, limit: 25, offset: 0 });
    expect(parsed.excluded_no_salary).toBe(0);
    expect(parsed.deferred_filters).toEqual([]);
  });

  it('keeps the reason a deferred filter carries', () => {
    const parsed = jobListSchema.parse({
      items: [],
      total: 0,
      limit: 25,
      offset: 0,
      excluded_no_salary: 3,
      deferred_filters: [{ name: 'borough', blocked_on: 'M4', reason: 'needs the geocoder' }],
    });
    expect(parsed.deferred_filters[0]?.reason).toBe('needs the geocoder');
  });
});

describe('companyDetailSchema', () => {
  const base = {
    id: '11111111-1111-4111-8111-111111111111',
    canonical_name: 'Datadog',
    website: null,
    job_status_counts: { open: 4, possibly_stale: 0, unverified: 0, closed: 2 },
    first_seen_at: null,
  };

  it('accepts a full set of closure counts', () => {
    expect(companyDetailSchema.safeParse(base).success).toBe(true);
  });

  it('rejects a response missing a closure state', () => {
    // A missing key and a real zero are different claims. Defaulting here
    // would silently turn "we did not report closed" into "closed: 0".
    const { closed: _closed, ...partial } = base.job_status_counts;
    expect(
      companyDetailSchema.safeParse({ ...base, job_status_counts: partial }).success,
    ).toBe(false);
  });
});

describe('jobDetailSchema', () => {
  it('accepts a job whose description the source never provided', () => {
    const parsed = jobDetailSchema.parse({
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Engineer',
      company: {
        id: '22222222-2222-4222-8222-222222222222',
        canonical_name: 'X',
        website: null,
      },
      employment_type: 'full_time',
      remote_policy: 'unknown',
      status: 'open',
      locations: [],
      salary: { provided: false },
      source_published_at: null,
      source_updated_at: null,
      first_seen_at: '2026-08-03T00:00:00+00:00',
      last_seen_at: '2026-08-03T00:00:00+00:00',
      application_deadline: null,
      description_text: null,
      description_html: null,
      sources: [],
    });
    expect(parsed.description_text).toBeNull();
  });
});
