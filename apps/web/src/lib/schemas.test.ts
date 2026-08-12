import { describe, expect, it } from 'vitest';

import {
  applicationEventSchema,
  applicationSchema,
  companyDetailSchema,
  dailyQueueSchema,
  queueRowSchema,
  queueSectionBlindSpotSchema,
  queueSectionKeySchema,
  jobDetailSchema,
  jobListSchema,
  jobLocationSchema,
  matchRankingSchema,
  matchSchema,
  placementSchema,
  resolutionMethodSchema,
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
    eligibility: null,
  };

  it('accepts a well-formed queue', () => {
    const parsed = dailyQueueSchema.parse({
      generated_at: '2026-08-04T12:00:00+00:00',
      sections: [
        {
          key: 'follow_up',
          title: 'Follow up',
          rows: [row],
          total: 1,
          blind_spots: [],
          note: null,
        },
      ],
      total_rows: 1,
      deferred_rows: [
        { name: 'High-match roles closing soon', blocked_on: 'the sources', reason: 'no deadline' },
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

  it('allows a row with no application, because a suggestion has none yet', () => {
    // M3d Task 7. The page links such a row to the posting instead.
    const offered = { ...row, application_id: null, current_stage: null, eligibility: 'uncertain' };
    expect(queueRowSchema.safeParse(offered).success).toBe(true);
  });

  it('refuses a blind spot with a count and no sentence', () => {
    // A bare "4" beside a section is exactly the unexplained number I4 is
    // about, one level up from a score.
    const spot = { name: 'not_yet_scored', count: 4, because: '' };
    expect(queueSectionBlindSpotSchema.safeParse(spot).success).toBe(false);
  });
});

describe('matchSchema — the score at the network boundary', () => {
  const score = {
    overall_score: 40,
    assessed_out_of: 50,
    fraction: 0.8,
    eligibility_status: 'uncertain',
    components: [],
    penalty_score: 0,
    penalties: [],
    deferred_components: [],
    ruleset_version: '1+2026-08-09.1',
    model_version: null,
    computed_at: '2026-08-09T00:00:00+00:00',
  };

  it('keeps a null fraction null rather than coercing it to zero', () => {
    // The ranking key. `null` means nothing could be assessed; `0` means
    // measured and found wanting, and the two sort at opposite ends.
    const parsed = matchSchema.parse({ ...score, assessed_out_of: 0, fraction: null });
    expect(parsed.fraction).toBeNull();
  });

  it('refuses an eligibility state the API cannot send', () => {
    expect(matchSchema.safeParse({ ...score, eligibility_status: 'maybe' }).success).toBe(false);
  });

  it('refuses a penalty name outside the two', () => {
    const result = matchSchema.safeParse({
      ...score,
      penalties: [{ name: 'salary_mismatch', points: 0, applicable: false, why: 'x' }],
    });
    expect(result.success).toBe(false);
  });

  it('refuses an evidence row that names a field of the posting we do not have', () => {
    // `job_span_field` selects which string the offsets index into. A value the
    // browser accepts and the API cannot send is dead UI; a value it refuses is
    // an unparseable page — and a wrong one underlines the wrong sentence.
    const result = matchSchema.safeParse({
      ...score,
      components: [
        {
          component: 'role',
          points: 20,
          weight: 20,
          assessable: true,
          why: 'x',
          evidence: [
            {
              component: 'role',
              points: 20,
              job_span_text: 'Engineer',
              job_span_field: 'summary',
              job_char_start: 0,
              job_char_end: 8,
              user_span_text: 'engineer',
              user_skill_id: null,
              user_project_id: null,
              compared: {},
              proposed_by: 'rule',
            },
          ],
        },
      ],
    });
    expect(result.success).toBe(false);
  });
});

describe('matchRankingSchema', () => {
  const ranking = {
    bands: [],
    total: 0,
    not_yet_scored: 0,
    ruleset_version: '1+2026-08-09.1',
  };

  it('defaults the ordering promise rather than leaving it undefined', () => {
    // A constant on the wire so a client cannot quietly decide that a pair
    // nothing could be assessed on belongs at the top.
    expect(matchRankingSchema.parse(ranking).unassessed_sort_last).toBe(true);
  });

  it('refuses a response that claims unassessed rows sort first', () => {
    expect(matchRankingSchema.safeParse({ ...ranking, unassessed_sort_last: false }).success).toBe(
      false,
    );
  });

  it('requires the count of what it could not rank', () => {
    // Omitting it is how a list covering 12 of 31 postings comes to look like a
    // list covering all 31, so it is required rather than defaulted to zero.
    const without: Record<string, unknown> = { ...ranking };
    delete without.not_yet_scored;
    expect(matchRankingSchema.safeParse(without).success).toBe(false);
  });
});

describe('placementSchema — I1 at the browser boundary', () => {
  const unresolved = {
    kind: 'unresolved' as const,
    latitude: null,
    longitude: null,
    building_id: null,
    location_confidence: 'city_only' as const,
    resolution_method: 'source_text_parse' as const,
    stated: 'New York, NY',
    inherited: false,
    office_label: null,
    office_address: null,
  };

  const onABuilding = {
    kind: 'building' as const,
    latitude: 40.755913,
    longitude: -73.989658,
    building_id: '1087186',
    location_confidence: 'verified' as const,
    resolution_method: 'company_office' as const,
    stated: 'New York, NY',
    inherited: true,
    office_label: 'New York HQ',
    office_address: '620 Eighth Avenue, New York, NY',
  };

  it('accepts the shape this corpus actually produces', () => {
    expect(placementSchema.safeParse(unresolved).success).toBe(true);
  });

  it('accepts a role standing at its employer’s confirmed office', () => {
    const parsed = placementSchema.parse(onABuilding);
    // ADR 0024: the inheritance travels with the coordinate, so a panel can
    // never render the position without the sentence that qualifies it.
    expect(parsed.inherited).toBe(true);
    expect(parsed.resolution_method).toBe('company_office');
  });

  it('refuses an unresolved placement that arrived carrying a position', () => {
    expect(
      placementSchema.safeParse({ ...unresolved, latitude: 40.7, longitude: -74 }).success,
    ).toBe(false);
  });

  it('refuses a building placement below verified', () => {
    // The exact failure I1 names: something plausible-looking put on a
    // structure on the strength of a city name.
    expect(
      placementSchema.safeParse({ ...onABuilding, location_confidence: 'approximate' }).success,
    ).toBe(false);
  });

  it('refuses a placed beacon with no coordinates to place it at', () => {
    expect(
      placementSchema.safeParse({ ...onABuilding, latitude: null, longitude: null }).success,
    ).toBe(false);
  });

  it('refuses an approximate placement that named a building — a BIN is not a promotion', () => {
    expect(
      placementSchema.safeParse({
        ...onABuilding,
        kind: 'area',
        location_confidence: 'approximate',
      }).success,
    ).toBe(false);
  });

  it('knows the resolution method M4a added, which it did not until M4c', () => {
    // `company_office` reached the Python enum a milestone before it reached
    // this file. Nothing failed in between because nothing sent it.
    expect(resolutionMethodSchema.safeParse('company_office').success).toBe(true);
  });
});
