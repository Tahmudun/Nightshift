/**
 * One `CitySignal`, with every field defaulted, shared by everything that tests
 * the city.
 *
 * A fixture module rather than a builder in each test file, and it exists
 * because four of them had drifted apart: the field's tests, the layer's, the
 * roster's and the detail panel's each carried their own copy of the same
 * fifteen defaults. Adding a field to the payload meant editing four literals
 * and, in practice, discovering the fourth from a type error.
 *
 * `CLAUDE.md` §7 wants fakes named as fakes: nothing in the product imports
 * this file, and the defaults below are the shape this corpus actually
 * produces — an unresolved placement, a city-only confidence, and a posting
 * that names no street (`city.md` §4.1).
 */

import type { CitySignal } from '@/lib/schemas';

/** The default placement: what every role in this corpus actually has. */
export const UNRESOLVED_PLACEMENT: CitySignal['placement'] = {
  kind: 'unresolved',
  latitude: null,
  longitude: null,
  building_id: null,
  location_confidence: 'city_only',
  resolution_method: 'source_text_parse',
  stated: 'New York, NY',
  inherited: false,
  office_label: null,
  office_address: null,
};

/**
 * A role on the city. `job_id` is required because two signals that share one
 * are the bug most of these tests are looking for.
 */
export function signalFixture(
  overrides: Partial<CitySignal> & Pick<CitySignal, 'job_id'>,
): CitySignal {
  return {
    title: 'Software Engineer',
    company_id: 'company-a',
    company_name: 'Alloy',
    employment_type: 'full_time',
    remote_policy: 'on_site',
    status: 'open',
    first_seen_at: '2026-01-01T00:00:00Z',
    last_seen_at: '2026-01-01T00:00:00Z',
    last_verified_at: '2026-01-01T00:00:00Z',
    application_deadline: null,
    placement: UNRESOLVED_PLACEMENT,
    ...overrides,
  };
}
