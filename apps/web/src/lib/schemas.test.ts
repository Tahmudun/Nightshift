import { describe, expect, it } from 'vitest';

import { jobLocationSchema, salarySchema } from './schemas';

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
