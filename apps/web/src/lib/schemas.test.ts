import { describe, expect, it } from 'vitest';

import {
  applicationEventSchema,
  applicationSchema,
  companyDetailSchema,
  dailyQueueSchema,
  queueRowSchema,
  queueSectionKeySchema,
  jobDetailSchema,
  jobListSchema,
  jobLocationSchema,
  extractionSchema,
  profileSchema,
  resumeDetailSchema,
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
      requirements: [],
      requirements_extractor_version: null,
      eligibility: null,
    });
    expect(parsed.description_text).toBeNull();
  });

  const withDescription = (
    description: string | null,
    requirements: unknown[],
    version: string | null = 'm3a.1',
  ) => ({
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
    description_text: description,
    description_html: null,
    sources: [],
    requirements,
    requirements_extractor_version: version,
    eligibility: null,
  });

  const KOTLIN_TEXT = 'You will need Kotlin.';
  const kotlin = {
    kind: 'technology',
    value: 'Kotlin',
    raw_text: 'Kotlin',
    char_start: KOTLIN_TEXT.indexOf('Kotlin'),
    char_end: KOTLIN_TEXT.indexOf('Kotlin') + 'Kotlin'.length,
    necessity: 'required',
    has_equivalence: false,
  };

  it('accepts a requirement that quotes the text it points at', () => {
    const parsed = jobDetailSchema.parse(withDescription(KOTLIN_TEXT, [kotlin]));
    expect(parsed.requirements).toHaveLength(1);
  });

  it('refuses a requirement whose span has drifted by one character', () => {
    // The span is still the right *length*, so only a check that holds both
    // the row and the text can see this. Off by one is the realistic failure:
    // it renders a plausible highlight over the wrong words.
    expect(() =>
      jobDetailSchema.parse(
        withDescription(KOTLIN_TEXT, [
          { ...kotlin, char_start: kotlin.char_start + 1, char_end: kotlin.char_end + 1 },
        ]),
      ),
    ).toThrow(/does not quote the text it points at/);
  });

  it('does not refuse requirements on a job with no description text', () => {
    // Nothing to check them against. Refusing here would reject a response
    // the API can legitimately produce.
    expect(() => jobDetailSchema.parse(withDescription(null, []))).not.toThrow();
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
    selected_resume_id: null,
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

describe('extractionSchema', () => {
  const base = {
    id: '00000000-0000-4000-8000-000000000010',
    kind: 'skill',
    value: { name: 'Python' },
    char_start: 8,
    char_end: 14,
    quoted_text: 'Python',
    status: 'pending',
    extractor_version: 'm2c.1',
    decided_at: null,
  };

  it('accepts a proposal whose quote is as long as its span', () => {
    // The positive twin. Every negative test below proves nothing without it —
    // three M2b tests passed against a schema that did not exist, because
    // `undefined.parse()` throws too.
    expect(extractionSchema.parse(base).value).toEqual({ name: 'Python' });
  });

  it('refuses a proposal whose quoted text cannot fit its span', () => {
    // The client's half of the database trigger. The trigger compares the quote
    // against the resume text; this compares it against the span it claims, so
    // a serialisation bug is caught before anything is highlighted.
    const result = extractionSchema.safeParse({ ...base, quoted_text: 'Rust' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(['quoted_text']);
  });

  it('refuses an empty span', () => {
    // Mirrors `span_is_not_empty`. A zero-width proposal highlights nothing and
    // still makes a claim, which is the shape I2 exists to forbid.
    const result = extractionSchema.safeParse({ ...base, char_end: 8 });
    expect(result.success).toBe(false);
  });

  it('refuses a kind the extractor has no rule for', () => {
    // `work_authorization` is the one that matters: a claim about legal status
    // is confirmed in a form, never read off a page.
    const result = extractionSchema.safeParse({ ...base, kind: 'work_authorization' });
    expect(result.success).toBe(false);
  });
});

describe('resumeDetailSchema', () => {
  const text = 'I write Python and some Go.';
  const base = {
    id: '00000000-0000-4000-8000-000000000011',
    name: 'my resume',
    variant_type: 'custom',
    source_kind: 'paste',
    original_filename: null,
    content_hash: 'a'.repeat(64),
    is_default: true,
    extraction_counts: { pending: 1, confirmed: 0, rejected: 0 },
    created_at: '2026-08-03T12:00:00Z',
    updated_at: '2026-08-03T12:00:00Z',
    parsed_text: text,
    nothing_proven: false,
    extractions: [
      {
        id: '00000000-0000-4000-8000-000000000012',
        kind: 'skill',
        value: { name: 'Python' },
        char_start: 8,
        char_end: 14,
        quoted_text: 'Python',
        status: 'pending',
        extractor_version: 'm2c.1',
        decided_at: null,
      },
    ],
  };

  it('accepts a resume whose every span quotes its text', () => {
    expect(resumeDetailSchema.parse(base).extractions).toHaveLength(1);
  });

  it('refuses a proposal whose span points at the wrong words', () => {
    // Same length, so `extractionSchema` alone cannot see it — only the parent
    // holds the text. This is the check that makes a highlight trustworthy.
    const result = resumeDetailSchema.safeParse({
      ...base,
      extractions: [{ ...base.extractions[0], char_start: 0, char_end: 6 }],
    });
    expect(result.success).toBe(false);
  });

  it('accepts a resume that proved nothing', () => {
    // I7's shape on the wire. An empty list with `nothing_proven` is a result,
    // and the screen says so rather than rendering an empty pane.
    const parsed = resumeDetailSchema.parse({
      ...base,
      extractions: [],
      extraction_counts: { pending: 0, confirmed: 0, rejected: 0 },
      nothing_proven: true,
    });
    expect(parsed.nothing_proven).toBe(true);
  });
});

describe('profileSchema', () => {
  const base = {
    id: '00000000-0000-4000-8000-000000000013',
    email: 'someone@example.test',
    display_name: null,
    timezone: 'America/New_York',
    graduation_year: null,
    graduation_month: null,
    degree: null,
    school: null,
    work_authorization: 'unspecified',
    home_location_text: null,
    remote_preference: 'no_preference',
    minimum_salary: null,
    preferred_roles: [],
    preferred_locations: [],
    skills: [],
    projects: [],
    deferred_fields: [{ name: '.docx upload', blocked_on: 'unscheduled', reason: 'one parser' }],
  };

  it('accepts a profile that confirms nothing at all', () => {
    // The starting state, and it must be representable. A schema that required
    // a graduation year would push the UI toward inventing one.
    expect(profileSchema.parse(base).skills).toEqual([]);
  });

  it('accepts a month once there is a year to hang it on', () => {
    const parsed = profileSchema.parse({ ...base, graduation_year: 2027, graduation_month: 5 });
    expect(parsed.graduation_month).toBe(5);
  });

  it('refuses a graduation month with no year', () => {
    // Mirrors the `graduation_month_needs_a_year` check constraint. "May" with
    // no year is not a date anyone can act on (I1).
    const result = profileSchema.safeParse({ ...base, graduation_month: 5 });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.path).toEqual(['graduation_month']);
  });
});

describe('dailyQueueSchema', () => {
  const row = {
    application_id: '00000000-0000-4000-8000-000000000001',
    job_id: '00000000-0000-4000-8000-000000000002',
    job_title: 'Software Engineer Intern',
    company_name: 'Example Inc.',
    current_stage: 'applied',
    at: '2026-08-04T12:00:00+00:00',
    because: 'no activity from you in 9 days',
  };

  it('accepts a well-formed queue', () => {
    const parsed = dailyQueueSchema.parse({
      generated_at: '2026-08-04T12:00:00+00:00',
      sections: [{ key: 'follow_up', title: 'Follow up', rows: [row], total: 1 }],
      total_rows: 1,
      deferred_rows: [
        { name: 'Best new internships', blocked_on: 'milestone 3', reason: 'no score yet' },
      ],
      thresholds: {
        follow_up_silent_days: 7,
        stale_saved_days: 21,
        interview_horizon_days: 14,
        row_cap: 20,
      },
    });
    expect(parsed.sections[0]?.rows[0]?.because).toContain('9 days');
  });

  it('refuses a row with no reason', () => {
    // A row that cannot say why it is there is the bug I4 describes, and the
    // schema is where it gets stopped rather than rendered as a bare title.
    const result = queueRowSchema.safeParse({ ...row, because: '' });
    expect(result.success).toBe(false);
  });

  it('allows a row with no date, because not every row has one', () => {
    expect(queueRowSchema.safeParse({ ...row, at: null }).success).toBe(true);
  });

  it('refuses a section key the API does not serve', () => {
    expect(queueSectionKeySchema.safeParse('recommended_action').success).toBe(false);
  });
});
