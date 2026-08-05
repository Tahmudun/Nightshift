import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { JobFacts } from './JobDetail';
import { jobDetailSchema } from '@/lib/schemas';

// Parsed through the real schema rather than cast to its type. A cast asserts
// the shape; the schema *checks* it, and M2c shipped a component test fed a row
// its own schema would have refused. This fixture went stale the moment M3a
// added two fields, and the cast said nothing — the render crashed instead.
const BASE = jobDetailSchema.parse({
  id: '11111111-1111-4111-8111-111111111111',
  title: 'Platform Engineer',
  company: {
    id: '22222222-2222-4222-8222-222222222222',
    canonical_name: 'Datadog',
    website: null,
  },
  employment_type: 'full_time',
  remote_policy: 'hybrid',
  status: 'open',
  locations: [],
  salary: { provided: false, minimum: null, maximum: null, currency: null, period: null },
  source_published_at: null,
  source_updated_at: null,
  first_seen_at: '2026-08-01T00:00:00+00:00',
  last_seen_at: '2026-08-03T00:00:00+00:00',
  application_deadline: null,
  description_text: 'We build things.',
  description_html: null,
  sources: [],
  requirements: [],
  requirements_extractor_version: null,
});

describe('JobFacts', () => {
  it('says a missing salary was not provided rather than hiding the row', () => {
    render(<JobFacts job={BASE} />);
    expect(screen.getByText(/salary/i)).toBeVisible();
    expect(screen.getAllByText(/not provided by source/i).length).toBeGreaterThan(0);
  });

  it('never labels first_seen_at as a posting date', () => {
    render(<JobFacts job={BASE} />);
    // A10: first_seen_at is our observation, not the source's claim.
    expect(screen.queryByText(/^posted$/i)).toBeNull();
    expect(screen.getByText(/first seen by nightshift/i)).toBeVisible();
  });

  it('distinguishes "not provided by source" from "not yet computed"', () => {
    render(<JobFacts job={BASE} />);
    // Two different claims. A UI that renders both as an empty field is
    // telling the reader the same thing about two unrelated situations.
    expect(screen.getAllByText(/not provided by source/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/not yet computed/i)).toBeVisible();
  });

  it('names the M3 fields it cannot compute yet', () => {
    render(<JobFacts job={BASE} />);
    expect(screen.getByText(/match score/i)).toBeVisible();
    expect(screen.getByText(/eligibility/i)).toBeVisible();
  });

  it('shows no percentage anywhere in the deferred block', () => {
    // I4: a bare score is a bug, and an invented one is worse.
    const { container } = render(<JobFacts job={BASE} />);
    const deferred = container.querySelector('[data-testid="deferred-facts"]');
    expect(deferred).not.toBeNull();
    expect(deferred?.textContent ?? '').not.toMatch(/\d+\s*%/);
  });

  it('says so when the source stated no location, rather than rendering nothing', () => {
    render(<JobFacts job={BASE} />);
    expect(screen.getByText(/no location stated by the source/i)).toBeVisible();
  });

  it('renders a provided salary with its period marked unstated', () => {
    render(
      <JobFacts
        job={{
          ...BASE,
          salary: {
            provided: true,
            minimum: 90000,
            maximum: 120000,
            currency: 'USD',
            period: null,
          },
        }}
      />,
    );
    // A10 again: Greenhouse publishes a range without saying annual or hourly,
    // and inferring one from magnitude would be a guess presented as data.
    expect(screen.getByText(/period not stated/i)).toBeVisible();
  });
});
