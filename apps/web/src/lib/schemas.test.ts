import { describe, expect, it } from 'vitest';

import {
  applicationEventSchema,
  applicationSchema,
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
    const partial: Record<string, number> = { ...base.job_status_counts };
    delete partial.closed;
    expect(companyDetailSchema.safeParse({ ...base, job_status_counts: partial }).success).toBe(
      false,
    );
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

const jobSummaryFixture = {
  id: '22222222-2222-4222-8222-222222222222',
  title: 'Software Engineer',
  company: {
    id: '33333333-3333-4333-8333-333333333333',
    canonical_name: 'Example Inc.',
    website: null,
  },
  employment_type: 'full_time',
  remote_policy: 'unknown',
  status: 'open',
  locations: [baseLocation],
  salary: { provided: false },
  source_published_at: null,
  source_updated_at: null,
  first_seen_at: '2026-08-03T12:00:00Z',
  last_seen_at: '2026-08-03T12:00:00Z',
  application_deadline: null,
};

describe('applicationSchema', () => {
  const base = {
    id: '00000000-0000-4000-8000-000000000001',
    job: jobSummaryFixture,
    current_stage: 'saved',
    priority: 'normal',
    applied_at: null,
    next_action_at: null,
    application_url: null,
    source_of_application: null,
    archived_at: null,
    created_at: '2026-08-03T12:00:00Z',
    updated_at: '2026-08-03T12:00:00Z',
  };

  it('accepts a saved application', () => {
    expect(applicationSchema.parse(base).current_stage).toBe('saved');
  });

  it('rejects a stage outside the ten', () => {
    // The stage set is the product's vocabulary. An eleventh value reaching a
    // component means the API and the UI disagree about what a pipeline is.
    //
    // `safeParse`, not `expect(...).toThrow()`. A `toThrow` assertion passes
    // when the schema does not exist at all — `undefined.parse(...)` throws —
    // and that is not hypothetical: it is what these three tests did on their
    // first run, before the schemas were written.
    const result = applicationSchema.safeParse({ ...base, current_stage: 'ghosted' });
    expect(result.success).toBe(false);
  });

  it('rejects a stage change event with no classification', () => {
    // Mirrors the database check constraint: a destination with no class is
    // half a transition, and the UI would render it as a blank badge.
    const result = applicationEventSchema.safeParse({
      id: '00000000-0000-4000-8000-000000000002',
      event_type: 'stage_changed',
      actor: 'user',
      occurred_at: '2026-08-03T12:00:00Z',
      from_stage: 'saved',
      to_stage: 'applied',
      transition_class: null,
      body: null,
      payload: {},
      created_at: '2026-08-03T12:00:00Z',
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(['transition_class']);
  });

  it('rejects a system actor that carries a stage', () => {
    // Invariant I5, enforced on the client too — the same move
    // jobLocationSchema makes for I1.
    const result = applicationEventSchema.safeParse({
      id: '00000000-0000-4000-8000-000000000003',
      event_type: 'stage_changed',
      actor: 'system',
      occurred_at: '2026-08-03T12:00:00Z',
      from_stage: 'saved',
      to_stage: 'closed',
      transition_class: 'advance',
      body: null,
      payload: {},
      created_at: '2026-08-03T12:00:00Z',
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(['actor']);
  });

  it('accepts the listing_closed event the system really writes', () => {
    // The other half of the I5 rule: a system actor recording a fact about the
    // world must pass. A refinement that rejected this would make the closure
    // notification unrenderable, which is the failure mode of over-tightening.
    const parsed = applicationEventSchema.parse({
      id: '00000000-0000-4000-8000-000000000004',
      event_type: 'listing_closed',
      actor: 'system',
      occurred_at: '2026-08-03T12:00:00Z',
      from_stage: null,
      to_stage: null,
      transition_class: null,
      body: 'the source stopped listing this role: 3 misses over 8 days',
      payload: {},
      created_at: '2026-08-03T12:00:00Z',
    });
    expect(parsed.actor).toBe('system');
  });
});
