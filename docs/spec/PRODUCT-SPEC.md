# CODEX.md

## Project Codename

**CitySignal**

Working tagline:

> **Live career intelligence for New York tech.**

This repository begins empty. Build the product described in this document from the ground up.

Do not treat this as a mockup, a landing page, or a decorative Three.js experiment. The finished system must be a real, continuously updating career-intelligence platform with a deeply interactive 3D representation of New York City.

The 3D city is not decoration. It is the product’s primary spatial interface.

---

# 1. Mission

Build a personal career operating system that:

1. Discovers open technology internships and jobs in or relevant to New York City.
2. Prioritizes internships, new-graduate roles, and realistic early-career opportunities.
3. Normalizes job listings from multiple sources into one reliable database.
4. Deduplicates repeated or cross-posted positions.
5. Tracks whether a listing is new, updated, stale, or closed.
6. Matches listings against the user’s resume, skills, projects, preferences, and eligibility.
7. Explains every match score using evidence rather than opaque AI judgment.
8. Tracks saved jobs, applications, assessments, interviews, offers, rejections, and follow-ups.
9. Presents hiring activity through a cinematic, smooth, fully explorable 3D New York City.
10. Produces useful daily actions, not just visual spectacle.
11. Accumulates historical hiring-market data over time.
12. Remains privacy-conscious, testable, observable, and honest about uncertainty.

The intended emotional experience is:

> Entering the source code of New York’s technology job market.

The intended engineering experience is:

> Dependable data infrastructure underneath, cinematic neon machinery above.

---

# 2. Non-Negotiable Product Principles

## 2.1 The interface must feel truly 3D

The experience must feel at least as fluid and tactile as a polished interactive 3D universe interface.

Users must be able to:

- Pinch to zoom on trackpads and mobile devices.
- Scroll to zoom.
- Click and drag to rotate.
- Two-finger drag or equivalent gesture to pitch and orbit.
- Pan smoothly.
- Select buildings and points without fighting the camera.
- Transition between locations using cinematic but fast camera movement.
- Reset or re-center the camera.
- Jump to boroughs, neighborhoods, companies, or saved views.
- Use the interface comfortably on desktop and mobile.
- Maintain smooth interaction during filtering, selection, data updates, and animation.

Camera interaction must not feel like a normal flat map with a slight tilt.

It should feel like a digital model of New York that the user can physically inspect.

## 2.2 Visual spectacle may never replace utility

The user must not be forced to navigate the 3D city for routine actions.

The product must have three clear modes:

### Explore

The immersive 3D city.

Used for:

- Discovering companies.
- Finding job clusters.
- Seeing hiring activity.
- Exploring skill demand.
- Viewing geographic relationships.
- Understanding the current market visually.

### Operate

A fast, conventional productivity interface.

Used for:

- Reviewing top job matches.
- Saving and applying.
- Updating application states.
- Adding notes.
- Comparing jobs.
- Managing resumes.
- Viewing deadlines.
- Handling follow-ups.

### Analyze

A historical and strategic interface.

Used for:

- Application outcomes.
- Response rates.
- Resume performance.
- Skill demand.
- Posting volume.
- Hiring trends.
- Source quality.
- Time-to-response.
- Geographic and company-level patterns.

## 2.3 Never fake geographic precision

A job listing may contain:

- A verified street address.
- A known company office.
- A neighborhood.
- Only “New York, NY.”
- Hybrid or remote language.
- Conflicting location information.

Represent location confidence explicitly.

Use:

1. `verified`
2. `approximate`
3. `city_only`
4. `remote`
5. `unknown`

Do not place an uncertain listing on a specific building as though it is verified.

Uncertain locations should have a distinct visual treatment.

## 2.4 Never hallucinate user qualifications

The matching system must not invent:

- Skills.
- Work history.
- Coursework.
- Projects.
- Graduation dates.
- Certifications.
- Experience levels.
- Authorization status.
- Availability.

Every positive match claim must point to evidence from the user profile.

Every negative or partial match must clearly state what is missing or uncertain.

## 2.5 Explainability is mandatory

A score such as `87% match` is not sufficient.

Every score must break down into understandable components.

Example:

- Role relevance: 18/20
- Skill overlap: 24/30
- Project evidence: 17/20
- Eligibility: pass
- Location fit: 8/10
- Freshness: 8/10
- Internship priority: 10/10
- Missing requirements penalty: -8

The user must be able to inspect why a score exists.

## 2.6 Source reliability must be visible

Each listing must retain:

- Original source.
- Canonical source URL.
- First seen timestamp.
- Last seen timestamp.
- Last verified timestamp.
- Source-specific identifier.
- Current status.
- Evidence that the listing remains open.
- Description content hash.
- Confidence level.

Listings must not silently disappear.

Closed or stale jobs should become historical records.

---

# 3. Target User

The initial user is:

- A computer science student in New York City.
- Seeking internships first.
- Also interested in new-graduate and realistic early-career software roles.
- Building a strong portfolio.
- Applying to major technology companies as well as smaller high-quality teams.
- Interested in software engineering, backend, full-stack, infrastructure, data, developer tools, and adjacent technical roles.
- Willing to use the system as a daily job-search command center.
- Interested in visually ambitious software, but unwilling to sacrifice correctness.

The architecture should support additional users later, but optimize first for one deeply personalized user.

---

# 4. Product Identity

## 4.1 Working name

Use **CitySignal** as the working product name.

Keep name usage isolated enough that it can be changed later.

Do not hardcode branding across dozens of files.

## 4.2 Visual direction

Primary inspiration:

- Futuristic holographic city models.
- Tron-like illuminated circuitry.
- Synthwave and cybernetic cartography.
- Dark glass.
- Blackened building masses.
- Cyan and electric-blue energy.
- Thin white highlights.
- Controlled magenta accents.
- Sparse gold for high-priority states.
- Pulse, flow, orbit, scanning, and signal motifs.
- Crisp geometric typography.
- High contrast without turning the screen into neon soup.

The visual tone must be:

- Precise.
- Sophisticated.
- Cinematic.
- Technical.
- Legible.
- Responsive.
- Premium.

Avoid:

- Generic purple gradients.
- Random glassmorphism everywhere.
- Excessive bloom.
- Constant particle noise.
- Hard-to-read glowing text.
- Overloaded dashboards.
- Toy-like sci-fi.
- Stock crypto-dashboard aesthetics.
- Cheap cyberpunk clutter.
- Camera motion that causes nausea.
- Effects that obscure job data.

## 4.3 Semantic visual language

Visual effects must encode real state.

Suggested defaults:

| Visual behavior | Meaning |
|---|---|
| Rapid cyan pulse | Newly discovered internship |
| Slow cyan pulse | Newly discovered non-intern role |
| Thin white outline | Saved |
| Solid illuminated building | Applied |
| Rotating horizontal ring | Assessment stage |
| Multiple orbiting arcs | Interview stage |
| Gold vertical beacon | Exceptional match or urgent priority |
| Soft green core | Offer |
| Red static fracture | Rejection |
| Fading afterimage | Closed position |
| Intermittent glitch | Stale or unverified listing |
| Translucent radius | Approximate location |
| Floating signal cluster | City-only or unresolved location |

These meanings must be documented in the interface.

---

# 5. Recommended Technology Stack

Use this stack unless there is a strong technical reason to deviate.

Document any deviation in an Architecture Decision Record.

## 5.1 Monorepo

Use:

- `pnpm`
- `Turborepo`

Suggested root structure:

```text
apps/
  web/
  api/
  worker/
packages/
  db/
  shared/
  matching/
  ingestion-core/
  ui/
  config/
  test-utils/
docs/
  adr/
  architecture/
  product/
  runbooks/
infra/
  docker/
  migrations/
scripts/
```

## 5.2 Web application

Use:

- Next.js
- React
- TypeScript
- MapLibre GL JS
- Three.js
- React Three Fiber only if it improves maintainability without fighting MapLibre integration
- Zustand for focused client state
- TanStack Query for server state
- Zod for runtime validation
- Tailwind CSS for application UI
- CSS variables or design tokens for theme control
- Playwright for end-to-end tests
- Vitest for unit and component tests

Use MapLibre for:

- Geographic projection.
- Basemap.
- Camera.
- 3D building context.
- Map interactions.
- Geospatial layers.

Use Three.js for:

- Holographic beacons.
- Particle flows.
- Building highlights.
- Orbiting status rings.
- Pulses.
- Scan effects.
- Custom markers.
- Instanced visualizations.
- Shader-driven effects.
- Special camera sequences.
- Data-driven 3D overlays.

Do not build a fake city from arbitrary cubes when real geographic context can be used.

## 5.3 API

Preferred:

- FastAPI
- Python 3.12+
- Pydantic
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- PostGIS
- pgvector
- Redis
- Structured logging

Alternative:

- NestJS is acceptable if repository cohesion strongly favors TypeScript.

Default to FastAPI because ingestion, NLP, matching, and data processing are likely to benefit from Python.

## 5.4 Worker system

Use a durable background-job architecture.

Acceptable options:

- Celery + Redis
- Dramatiq + Redis
- RQ for an early version, only if migration to a more robust system is planned
- Temporal if justified, but do not add it merely for prestige

Workers must support:

- Scheduled ingestion.
- Retry with backoff.
- Idempotency.
- Source-specific rate limiting.
- Dead-letter behavior.
- Observable job state.
- Safe reprocessing.
- Partial-source failure.

## 5.5 Database

Use PostgreSQL with:

- PostGIS.
- pgvector.
- Strong foreign keys.
- Explicit enums or check constraints where appropriate.
- Append-only event records for application history.
- Source snapshots or sufficient history to detect changes.
- Migration discipline.
- Seed data for development.
- Deterministic fixtures for testing.

## 5.6 Authentication

For early development, use a simple local development account.

For production-ready architecture, isolate auth behind an adapter.

Acceptable options:

- Auth.js
- Clerk
- Supabase Auth

Do not allow authentication decisions to infect domain logic.

## 5.7 Observability

Build in:

- Structured logs.
- Request IDs.
- Job-run IDs.
- Source-adapter IDs.
- Error categorization.
- Retry visibility.
- Ingestion metrics.
- Matching evaluation metrics.
- Sentry or equivalent exception monitoring.
- OpenTelemetry-compatible tracing where practical.

---

# 6. Core Domain Model

Design the schema carefully before building the visual layer.

At minimum, define the following entities.

## 6.1 User

Fields may include:

```text
id
email
display_name
timezone
home_location
graduation_date
degree
school
work_authorization
preferred_roles
preferred_locations
remote_preference
minimum_salary
created_at
updated_at
```

Sensitive fields must be protected.

## 6.2 User Skill

```text
id
user_id
skill_id
proficiency_level
confidence
source_type
source_reference
created_at
updated_at
```

`source_type` examples:

- resume
- project
- coursework
- manual
- assessment
- github
- inferred_pending_confirmation

Do not promote inferred skills to confirmed skills without user approval.

## 6.3 User Project

```text
id
user_id
name
summary
repository_url
demo_url
technologies
evidence
start_date
end_date
status
created_at
updated_at
```

## 6.4 Resume

```text
id
user_id
name
variant_type
source_file
parsed_text
structured_profile
content_hash
is_default
created_at
updated_at
```

Variants may include:

- general_swe
- backend
- full_stack
- data_ml
- infrastructure
- custom

## 6.5 Company

```text
id
canonical_name
normalized_name
website
industry
size_band
description
logo_url
created_at
updated_at
```

## 6.6 Company Location

```text
id
company_id
label
address
city
state
postal_code
latitude
longitude
location_confidence
verification_source
verified_at
created_at
updated_at
```

## 6.7 Source

```text
id
name
source_type
base_url
is_enabled
priority
rate_limit_policy
last_success_at
last_failure_at
created_at
updated_at
```

## 6.8 Source Job Record

Preserve raw source records separately from canonical jobs.

```text
id
source_id
source_job_id
source_company_key
canonical_url
raw_payload
raw_text
description_hash
first_seen_at
last_seen_at
last_verified_at
source_status
created_at
updated_at
```

## 6.9 Canonical Job

```text
id
company_id
title
normalized_title
role_family
seniority
employment_type
internship_season
description
requirements
preferred_qualifications
salary_min
salary_max
salary_currency
salary_period
remote_policy
location_text
latitude
longitude
location_confidence
posted_at
application_deadline
first_seen_at
last_seen_at
closed_at
status
canonical_description_hash
created_at
updated_at
```

## 6.10 Job Source Link

Many source records may point to one canonical job.

```text
id
job_id
source_job_record_id
match_confidence
link_reason
created_at
```

## 6.11 Application

```text
id
user_id
job_id
current_stage
priority
selected_resume_id
applied_at
next_action_at
source_of_application
notes
created_at
updated_at
```

## 6.12 Application Event

Append-only.

```text
id
application_id
event_type
occurred_at
source
metadata
created_at
```

Event examples:

- discovered
- saved
- applied
- confirmation_received
- assessment_received
- assessment_completed
- recruiter_contact
- interview_scheduled
- interview_completed
- follow_up_sent
- rejected
- withdrawn
- offer_received
- offer_accepted
- offer_declined
- listing_closed
- note_added

## 6.13 Match Result

```text
id
user_id
job_id
resume_id
overall_score
eligibility_status
role_score
skill_score
project_evidence_score
location_score
freshness_score
priority_score
penalty_score
explanation
model_version
ruleset_version
created_at
```

## 6.14 Job Snapshot

Store daily or meaningful-change snapshots.

```text
id
job_id
snapshot_date
status
description_hash
salary_min
salary_max
requirements
metadata
created_at
```

## 6.15 Ingestion Run

```text
id
source_id
started_at
finished_at
status
records_fetched
records_created
records_updated
records_unchanged
records_closed
records_failed
error_summary
created_at
```

---

# 7. Job Source Architecture

Implement each source as an adapter behind a common interface.

## 7.1 Adapter contract

Each adapter should support something like:

```python
class JobSourceAdapter(Protocol):
    source_name: str

    async def discover_companies(self) -> list[SourceCompany]:
        ...

    async def fetch_jobs(self, company: SourceCompany) -> list[RawJob]:
        ...

    async def normalize(self, raw_job: RawJob) -> NormalizedSourceJob:
        ...

    async def verify_open(self, source_job: SourceJobRecord) -> VerificationResult:
        ...
```

Exact design may differ, but all adapters must produce normalized output.

## 7.2 Initial sources

Implement in this order:

1. Greenhouse
2. Lever
3. Ashby
4. NYC official jobs data
5. USAJOBS
6. Additional sources only after the first five are stable

Community-maintained internship repositories may be added as discovery sources, but listings must be verified against an original application page whenever possible.

## 7.3 Scraping policy

Do not build the core system around scraping sites that prohibit or aggressively resist automated access.

Prefer:

- Public APIs.
- Public company job-board endpoints.
- Official feeds.
- User-provided sources.
- Lawful and respectful crawling with explicit controls.

Every adapter must:

- Identify itself.
- Respect rate limits.
- Cache responsibly.
- Retry safely.
- Avoid hammering endpoints.
- Log failures.
- Preserve raw payloads.
- Be disableable.
- Support fixture-based offline testing.

## 7.4 Freshness and closure

A listing must not be marked closed after a single transient failure.

Use a state machine such as:

```text
open
possibly_stale
unverified
closed
```

Suggested behavior:

- Successful fetch: `open`
- Missing once: remain open, increment missing count
- Missing repeatedly across a configured window: `possibly_stale`
- Direct endpoint confirms removal or closed state: `closed`
- Source unavailable: do not alter listing state
- Manual user confirmation: override with audit trail

## 7.5 Deduplication

Deduplication is a flagship engineering feature.

Use layered evidence:

- Same canonical URL.
- Same source ID.
- Same company.
- Similar normalized title.
- Similar location.
- Similar description hash.
- Similar requirement set.
- Similar posting date.
- Embedding similarity.
- Known cross-posting patterns.

Do not merge records solely because titles are similar.

Every merge must preserve:

- All source links.
- Confidence.
- Reason.
- Reversibility or repair path.
- Audit trail.

Create a deduplication evaluation fixture set with:

- True duplicates.
- Near duplicates.
- Distinct roles with similar titles.
- Reposts.
- Seasonal internship variations.
- Jobs in multiple locations.
- Jobs with modified descriptions.

---

# 8. Matching Engine

## 8.1 Philosophy

Use a hybrid system.

Deterministic rules handle:

- Hard eligibility.
- Graduation windows.
- Required authorization.
- Required years of experience.
- Role level.
- Location constraints.
- Required degree status.
- Internship eligibility.
- Explicit must-have technologies when clearly stated.

Semantic models assist with:

- Skill normalization.
- Requirement extraction.
- Role similarity.
- Project evidence matching.
- Explanation generation.
- Detecting adjacent or transferable experience.

An LLM may assist, but it must not be the sole source of truth.

## 8.2 Suggested score

Implement a configurable scoring system.

Initial example:

```text
eligibility gate              pass/fail/unknown
role relevance                0-20
skill overlap                 0-30
project evidence              0-20
location and work mode        0-10
listing freshness             0-10
internship/new-grad priority  0-10
company preference            0-5
application urgency           0-5
missing requirement penalty   0 to -25
seniority mismatch penalty    0 to -30
```

Normalize to 0-100 after gating.

The score weights must live in versioned configuration.

## 8.3 Eligibility states

Use:

- `eligible`
- `likely_eligible`
- `uncertain`
- `likely_ineligible`
- `ineligible`

Never collapse uncertainty into confidence.

## 8.4 Evidence graph

For each matched skill, preserve evidence.

Example:

```json
{
  "skill": "Python",
  "job_requirement": "Experience building backend services in Python",
  "user_evidence": [
    {
      "type": "project",
      "name": "Groupchat Wrapped",
      "detail": "Python-based analytics and processing pipeline"
    },
    {
      "type": "coursework",
      "name": "Algorithms",
      "detail": "Implemented assignments in Python"
    }
  ],
  "confidence": 0.91
}
```

## 8.5 Match explanation

Every explanation must include:

- Why the role fits.
- Why it may not fit.
- Hard blockers.
- Soft gaps.
- Relevant project evidence.
- Recommended resume.
- Recommended emphasis.
- Suggested next action.
- Confidence.

Do not automatically rewrite or submit a resume without explicit user action.

## 8.6 Evaluation

Create a manually labeled evaluation set.

Measure:

- Eligibility precision.
- Top-k relevance.
- Skill extraction accuracy.
- Project evidence accuracy.
- Hallucination rate.
- Explanation faithfulness.
- Ranking stability.
- Sensitivity to stale listings.

A matching engine without evaluation is not complete.

---

# 9. 3D City Experience

## 9.1 Initial geographic scope

Begin with New York City.

Prioritize:

- Manhattan
- Brooklyn
- Queens
- The Bronx
- Staten Island

The default camera may begin around Manhattan, but the entire city must remain accessible.

## 9.2 City rendering

Use a dark map style with:

- Dark water.
- Nearly black land.
- Thin road lines.
- Controlled grid illumination.
- 3D buildings.
- Minimal labels.
- Selective neighborhood labels.
- Strong depth cues.
- Atmospheric perspective.
- Fog used carefully.
- Anti-aliasing.
- Responsive quality settings.

Buildings should not all glow.

Most of the city should remain dark so active data can breathe.

## 9.3 Camera requirements

Create a dedicated camera controller abstraction.

It must support:

- Mouse orbit.
- Mouse pan.
- Wheel zoom.
- Trackpad pinch zoom.
- Trackpad rotation where supported.
- Touch pinch.
- Touch rotate.
- Touch pan.
- Double-click focus.
- Keyboard navigation.
- Reduced-motion mode.
- Programmatic fly-to.
- Programmatic orbit around selection.
- Smooth cancellation when the user takes control.
- Bounds and pitch limits.
- Collision or ground-avoidance behavior if needed.

Camera transitions must:

- Preserve spatial orientation.
- Avoid snapping.
- Avoid long forced animations.
- Respect user interruption.
- Use easing curves.
- Keep selected targets visible.
- Maintain stable frame pacing.

## 9.4 Performance budgets

Target:

- 60 FPS on a modern desktop during normal exploration.
- At least 30 FPS on supported mobile hardware.
- No major frame hitch when filters change.
- No full scene rebuild for minor data updates.
- No one-object-per-job architecture when instancing can be used.
- No unbounded particle systems.
- No uncontrolled React re-renders driving the render loop.
- Graceful degradation on low-power devices.

Implement adaptive quality tiers.

Possible tiers:

- Ultra
- High
- Balanced
- Battery saver

Adjust:

- Pixel ratio.
- Bloom.
- Particle count.
- Shadow usage.
- Fog density.
- Building detail.
- Animation density.
- Post-processing.

## 9.5 Instancing

Use instanced rendering for large repeated visual elements:

- Job beacons.
- Pulses.
- Markers.
- Rings.
- Flow particles.
- Building highlights where practical.

Do not create thousands of independent React components for scene objects.

## 9.6 Selection

Selecting a company or job must:

1. Highlight the relevant location.
2. Move the camera gently if needed.
3. Open a detail panel.
4. Preserve current filters.
5. Support keyboard navigation.
6. Update the URL or application state so selection is shareable.
7. Allow escape/back to return cleanly.

## 9.7 Unresolved signal district

Jobs that only specify “New York, NY” must not receive fake building placement.

Create a visually compelling unresolved layer.

Possible treatment:

- Floating signal stacks over the city.
- A holographic queue above Lower Manhattan.
- A ring around the city edge.
- A separate “unresolved signals” orbital view.

The user should be able to inspect these roles normally.

## 9.8 Hiring pulses

When new data arrives:

- Do not explosively animate every update.
- Batch nearby updates.
- Show subtle pulse propagation.
- Allow the user to replay recent activity.
- Maintain a “last refreshed” state.
- Surface source failures without corrupting the visual state.

## 9.9 Skill-demand layer

Add a mode where selecting a skill highlights:

- Relevant companies.
- Active job count.
- Geographic concentrations.
- Role-family concentrations.
- Change over time.

Potential visual forms:

- Vertical atmospheric columns.
- Floating labels.
- Heat intensity.
- Building-edge illumination.
- Data arcs between related clusters.

Keep the visualization interpretable.

## 9.10 Timeline mode

Allow the user to scrub through historical snapshots.

Requirements:

- Stable camera while time changes.
- Smooth data transition.
- Clear date display.
- Open/closed transitions.
- Hiring volume changes.
- User application history overlay.
- Ability to return to live mode.

---

# 10. Application Tracking

## 10.1 Stages

Default stages:

```text
discovered
saved
preparing
applied
assessment
interview
offer
rejected
withdrawn
closed
```

Allow custom substages later.

## 10.2 Manual control

The user must always be able to:

- Set stage.
- Correct stage.
- Add notes.
- Add contacts.
- Add deadlines.
- Add interview dates.
- Add follow-up dates.
- Select resume used.
- Record application URL.
- Archive or restore.

## 10.3 Automation suggestions

Automated systems may suggest status changes.

They must not silently make ambiguous changes.

Example:

> “An email from ExampleCorp appears to contain an online assessment invitation. Move this application to Assessment?”

Allow a confidence threshold for automatic low-risk updates later, but begin with confirmation.

## 10.4 Daily command center

Build a daily queue containing:

- Best new internships.
- High-match roles closing soon.
- Applications needing follow-up.
- Assessments due.
- Interviews approaching.
- Stale saved jobs.
- Resume mismatch warnings.
- One focused recommended action.

The product must help the user act, not merely browse.

---

# 11. Gmail Integration

This is not required for the first milestone.

Design for it from the start.

## 11.1 Goals

With explicit user permission:

- Detect application confirmations.
- Detect assessments.
- Detect recruiter outreach.
- Detect interview scheduling.
- Detect rejections.
- Detect offers.
- Suggest application-stage updates.
- Extract relevant dates.
- Associate messages with companies and jobs.

## 11.2 Privacy

Minimize data retention.

Prefer storing:

- Message ID.
- Thread ID.
- Sender.
- Subject.
- Timestamp.
- Classification.
- Extracted dates.
- Company.
- Job association.
- Confidence.
- Short user-visible rationale.

Avoid storing full email bodies unless necessary and explicitly approved.

## 11.3 Safety

- No email sending without explicit user action.
- No deletion.
- No broad inbox scanning beyond configured scope.
- Explain classification.
- Allow correction.
- Preserve audit events.
- Support disconnect and deletion of integration data.

---

# 12. User Experience Requirements

## 12.1 First run

The first-run experience should guide the user through:

1. Creating profile.
2. Uploading or pasting resume.
3. Confirming extracted facts.
4. Choosing target roles.
5. Choosing location and remote preferences.
6. Selecting graduation timing.
7. Adding major projects.
8. Choosing company interests.
9. Entering the 3D city.
10. Reviewing first job matches.

Never silently trust resume parsing.

## 12.2 Search

Support:

- Company.
- Role.
- Skill.
- Neighborhood.
- Borough.
- Job type.
- Internship season.
- Remote policy.
- Date posted.
- Salary.
- Match score.
- Application stage.
- Source.
- Location confidence.
- Eligibility.

Search must remain fast.

## 12.3 Detail panel

A selected job should show:

- Title.
- Company.
- Location.
- Location confidence.
- Internship/new-grad status.
- Salary if available.
- Posted date.
- Last verified date.
- Match score.
- Eligibility.
- Match breakdown.
- Skills.
- Missing requirements.
- Project evidence.
- Recommended resume.
- Application deadline.
- Source links.
- Save/apply controls.
- Notes.
- Application history.
- Similar jobs.
- Stale-data warning where needed.

## 12.4 Accessibility

Required:

- Keyboard-accessible non-3D interface.
- Screen-reader-friendly job lists.
- Visible focus states.
- Color meanings reinforced with labels and shape.
- Reduced motion.
- High-contrast mode.
- Text scaling support.
- No essential information available only through hover.
- Alternative list view for every map result.

The 3D city may be advanced, but the product must not exclude users who cannot use it.

---

# 13. Security and Privacy

Implement:

- Environment variable validation.
- Secret isolation.
- No secrets committed.
- Input validation.
- Output encoding.
- CSRF protection where relevant.
- Secure cookies.
- Rate limiting.
- Authorization checks.
- Database least privilege.
- Audit logs for sensitive actions.
- Safe file upload handling.
- Resume file type and size restrictions.
- Malware-aware upload architecture.
- Dependency scanning.
- Security headers.
- Sanitized rich text.
- SSRF protection in URL-fetching systems.
- Allowlisted external fetch behavior.
- No arbitrary URL crawling.

Document a threat model before production deployment.

---

# 14. Repository Quality Rules

## 14.1 General rules

- Use strict TypeScript.
- Use type checking in Python.
- Avoid `any`.
- Avoid giant modules.
- Prefer small, testable units.
- Keep domain logic out of UI components.
- Keep external source logic behind adapters.
- Keep visual effects behind semantic interfaces.
- Use feature flags for unfinished systems.
- Do not leave silent TODOs.
- Every TODO must include context or an issue reference.
- Do not add dependencies without justification.
- Do not introduce architecture purely to appear advanced.

## 14.2 Documentation

Maintain:

```text
README.md
CODEX.md
docs/architecture/system-overview.md
docs/architecture/data-model.md
docs/architecture/ingestion.md
docs/architecture/matching.md
docs/architecture/3d-rendering.md
docs/product/visual-language.md
docs/product/user-flows.md
docs/runbooks/local-development.md
docs/runbooks/ingestion-failure.md
docs/runbooks/database-recovery.md
docs/adr/
```

## 14.3 Architecture Decision Records

Create ADRs for consequential decisions.

Examples:

- MapLibre + Three.js integration.
- FastAPI selection.
- Worker system.
- Job deduplication strategy.
- Embedding provider.
- Email classification architecture.
- Hosting.
- Database.
- Authentication.
- Map tile provider.
- Geocoding provider.
- Data-retention policy.

## 14.4 Testing pyramid

Required:

- Unit tests.
- Integration tests.
- Source-adapter fixture tests.
- Database migration tests.
- Contract tests.
- Deduplication tests.
- Matching evaluation tests.
- End-to-end tests.
- Visual regression tests for important UI states.
- Performance tests for the 3D scene.
- Accessibility tests.

No milestone is complete because the page “looks good.”

---

# 15. Local Development

Create a one-command local setup.

Preferred workflow:

```bash
pnpm install
docker compose up -d
pnpm db:migrate
pnpm db:seed
pnpm dev
```

If Python uses a separate environment, provide a root command that manages it cleanly.

The developer must not need to manually visit five directories and remember hidden setup steps.

Create:

- `.env.example`
- Docker Compose services
- Seed fixtures
- Mock job sources
- Development user
- Development resume/profile
- Sample applications
- Sample city data
- Sample historical snapshots

The product must be demonstrable offline using fixtures.

---

# 16. CI Requirements

Set up CI early.

Required checks:

- Formatting.
- Linting.
- Type checking.
- Unit tests.
- Python tests.
- Migration check.
- Build.
- End-to-end smoke test.
- Dependency audit.
- Secret scan.
- License awareness.
- Test coverage reporting.

Prevent merging broken main branches.

---

# 17. Milestones

Build in strict sequence.

Do not begin with cinematic polish.

## Milestone 0: Foundation

### Goal

Create a healthy monorepo with reliable local development.

### Deliverables

- Monorepo scaffolding.
- Web app.
- API.
- Worker.
- Database package.
- Shared schemas.
- Docker Compose.
- Environment validation.
- CI.
- Formatting and linting.
- Test frameworks.
- Basic documentation.
- Seed data.
- Health endpoints.
- Local one-command startup.

### Acceptance criteria

- Fresh clone works using documented commands.
- Web, API, worker, database, and Redis start.
- CI passes.
- Tests run.
- Database migrations apply.
- Seed data loads.
- No secret values are committed.

## Milestone 1: Employment Data Spine

### Goal

Create a reliable canonical job database.

### Deliverables

- Core database schema.
- Greenhouse adapter.
- Lever adapter.
- Ashby adapter.
- Source job storage.
- Normalization.
- Canonical job creation.
- Initial deduplication.
- Ingestion runs.
- Freshness checks.
- Closure state machine.
- Admin-style job table.
- Source health page.
- Offline fixtures.
- Adapter contract tests.

### Acceptance criteria

- Same fixture input produces deterministic output.
- Re-ingestion is idempotent.
- Transient source failure does not close jobs.
- Duplicate test cases merge correctly.
- Similar-but-distinct roles remain separate.
- Source provenance is visible.
- Every job has first-seen and last-seen timestamps.
- Raw source records are preserved.
- Failures are observable.

## Milestone 2: Functional Job Command Center

### Goal

Make the product useful before the 3D city exists.

### Deliverables

- User profile.
- Resume upload or paste.
- Resume parsing review.
- Job search.
- Filtering.
- Saving.
- Application tracking.
- Notes.
- Stage history.
- Daily queue.
- Basic dashboard.
- Company pages.
- Job detail pages.

### Acceptance criteria

- User can discover, inspect, save, and track jobs.
- Application events are append-only.
- Filters are fast.
- Resume facts require confirmation.
- Job source and freshness are visible.
- Core workflows work without 3D.

## Milestone 3: Explainable Matching

### Goal

Rank jobs intelligently and honestly.

### Deliverables

- Skill taxonomy.
- Requirement extraction.
- Eligibility rules.
- Role-family normalization.
- Project evidence graph.
- Versioned score weights.
- Match explanations.
- Resume recommendations.
- Evaluation fixture set.
- Ranking metrics.
- Hallucination checks.

### Acceptance criteria

- Every score has a breakdown.
- Every positive skill claim has evidence.
- Hard blockers are surfaced.
- Uncertainty is explicit.
- Evaluation suite runs in CI.
- Matching model and ruleset versions are stored.
- Re-running a fixed test set is reproducible.

## Milestone 4: Living City Prototype

### Goal

Create the true 3D spatial interface.

### Deliverables

- MapLibre city.
- 3D buildings.
- Dark Tron-like map style.
- Company locations.
- Job beacons.
- Selection.
- Camera controller.
- Smooth zoom, rotate, pan, pitch, and touch interactions.
- Job detail panel integration.
- Location-confidence visuals.
- Unresolved signal district.
- Performance instrumentation.
- Adaptive quality settings.
- Reduced-motion support.
- List-view synchronization.

### Acceptance criteria

- Interaction is smooth on a modern desktop.
- Touch gestures work on mobile.
- User can interrupt camera animations.
- No fake precise placement.
- Thousands of markers do not create thousands of heavy React objects.
- Selected locations and list results remain synchronized.
- 3D mode is not required for routine tasks.
- Performance metrics are recorded.

## Milestone 5: Cinematic Visual System

### Goal

Make the city memorable without damaging usability.

### Deliverables

- Pulse language.
- Building state language.
- Status rings.
- Data flows.
- Scan effect.
- Job arrival animation.
- Application-stage visuals.
- Skill-demand visualization.
- Carefully tuned post-processing.
- Visual legend.
- Theme tokens.
- Screenshots and visual regression coverage.

### Acceptance criteria

- Every effect has semantic meaning.
- Text remains readable.
- Effects degrade gracefully.
- Battery-saver mode exists.
- No effect causes severe frame drops.
- Reduced-motion mode remains complete.
- City remains legible when many jobs are active.

## Milestone 6: Historical Intelligence

### Goal

Turn accumulated data into an original dataset.

### Deliverables

- Daily snapshots.
- Timeline scrubber.
- Hiring-volume trends.
- Skill-demand trends.
- Company activity history.
- Application outcome analysis.
- Resume performance.
- Source performance.
- Time-to-response metrics.
- Live versus historical mode.

### Acceptance criteria

- Historical data is reproducible.
- Timeline does not alter live records.
- Snapshot generation is idempotent.
- Time-based queries are tested.
- The user can understand what changed and when.

## Milestone 7: Gmail-Assisted Tracking

### Goal

Reduce manual application maintenance.

### Deliverables

- OAuth integration.
- Scoped email access.
- Message classifier.
- Company/job association.
- Assessment detection.
- Interview detection.
- Rejection detection.
- Offer detection.
- Suggested stage updates.
- User correction flow.
- Privacy settings.
- Disconnect and delete flow.

### Acceptance criteria

- No email sent automatically.
- No ambiguous stage changed silently.
- User can see why a message was classified.
- Incorrect classifications can be corrected.
- Stored email data is minimized.
- Disconnect removes credentials safely.
- Integration is covered by fixture tests.

## Milestone 8: Recruiter-Grade Hardening

### Goal

Make the project defensible under technical scrutiny.

### Deliverables

- Architecture diagrams.
- Threat model.
- Load tests.
- Source failure drills.
- Data recovery runbooks.
- Privacy documentation.
- Accessibility audit.
- Performance audit.
- Matching evaluation report.
- Deduplication evaluation report.
- Public demo mode with synthetic user data.
- Project case study.
- Deployment documentation.

### Acceptance criteria

- Public demo exposes no private data.
- Failure of one source does not break the system.
- Data recovery is documented.
- Accessibility issues are tracked and addressed.
- Matching claims are supported by evaluation.
- Performance is measured, not guessed.
- Architecture can be explained in an interview.

---

# 18. Public Demo Mode

The repository must eventually support a safe portfolio demonstration.

Use:

- Synthetic user profile.
- Synthetic resume.
- Synthetic application history.
- Real or fixture job data according to legal and source constraints.
- No private email.
- No private notes.
- No personal contact data.
- Clearly labeled demo mode.

The demo should tell a coherent story:

1. New internship signal appears.
2. User explores company location.
3. Match score is explained.
4. Project evidence is shown.
5. User saves and applies.
6. Application state changes visually.
7. Historical analytics show progress.

---

# 19. Visual Scene Architecture

Create a semantic scene system.

Suggested abstraction:

```text
CityScene
  MapLayer
  BuildingLayer
  CompanyLayer
  JobSignalLayer
  ApplicationStateLayer
  SkillDemandLayer
  ActivityFlowLayer
  AtmosphereLayer
  SelectionLayer
  TimelineLayer
```

Each layer must:

- Receive normalized data.
- Be independently toggleable.
- Expose performance metrics.
- Avoid domain-specific database calls.
- Use stable IDs.
- Clean up GPU resources.
- Support quality tiers.
- Support reduced motion.

Do not scatter Three.js creation code across React components.

Create a coherent rendering subsystem.

---

# 20. Data Contracts

Define shared schemas for communication between services.

Examples:

```text
JobSummary
JobDetail
CompanyMapPoint
CompanyMapBuilding
JobSignal
ApplicationVisualState
SkillDemandCluster
TimelineFrame
MatchExplanation
DailyAction
SourceHealth
```

Use generated or shared types where practical.

Runtime-validate external data.

Do not trust source payloads.

---

# 21. Geocoding and Company Location Strategy

Build this in layers.

Priority:

1. Verified office address from company source.
2. Company careers page or official location page.
3. Trusted geocoding result.
4. Manually verified location.
5. Neighborhood-level approximation.
6. City-only unresolved state.

Store:

- Input address.
- Normalized address.
- Coordinates.
- Provider.
- Confidence.
- Verification method.
- Verification timestamp.
- Manual override.
- Audit history.

Cache geocoding.

Do not repeatedly geocode identical addresses.

---

# 22. Skill Taxonomy

Create a normalized skill system.

Examples:

```text
javascript
typescript
react
nextjs
nodejs
python
java
c
cpp
csharp
go
rust
sql
postgresql
redis
aws
gcp
azure
docker
kubernetes
terraform
graphql
rest
fastapi
django
spring
machine_learning
data_engineering
distributed_systems
testing
observability
```

Support aliases.

Examples:

- `js` -> `javascript`
- `ts` -> `typescript`
- `postgres` -> `postgresql`
- `k8s` -> `kubernetes`
- `amazon web services` -> `aws`

Do not over-normalize distinct skills.

Keep taxonomy versioned.

---

# 23. Internship Priority Logic

Internships should receive special treatment.

Detect:

- Summer.
- Fall.
- Spring.
- Off-cycle.
- Co-op.
- Student.
- University.
- Campus.
- Early talent.
- Emerging talent.
- New graduate.
- Recent graduate.
- Apprenticeship.
- Fellowship.

Store season and target graduation window when available.

Boost only when eligibility appears plausible.

Do not rank an internship highly if the graduation rules clearly exclude the user.

---

# 24. Search Ranking

Search ranking and match ranking are separate.

Search ranking may consider:

- Text relevance.
- Filters.
- Freshness.
- Job state.
- User priority.
- Company preference.
- Match score.
- Source confidence.

Expose sort options:

- Recommended.
- Newest.
- Best match.
- Deadline soonest.
- Salary.
- Company.
- Distance.
- Recently updated.

---

# 25. Failure Behavior

The product must fail honestly.

Examples:

## Source failure

Show:

- Source unavailable.
- Last successful refresh.
- Jobs remain visible.
- No false closure.

## Matching failure

Show:

- Match temporarily unavailable.
- Existing score version.
- Ability to inspect job normally.

## Map failure

Show:

- Conventional list interface.
- Clear explanation.
- Retry action.
- No blank screen.

## Geocoding failure

Show:

- City-only or unknown location.
- No fabricated point.

## Email classification uncertainty

Show:

- Suggested classification.
- Confidence.
- User confirmation.

---

# 26. Performance Instrumentation

Record:

- Time to first interactive.
- Time to first map frame.
- Average FPS.
- Low-percentile FPS.
- Number of draw calls.
- GPU memory indicators where accessible.
- Marker count.
- Visible building count.
- Filter update latency.
- Camera transition duration.
- API latency.
- Match calculation latency.
- Ingestion duration.
- Deduplication duration.

Create a developer performance panel.

---

# 27. Codex Operating Instructions

## 27.1 Work autonomously

This repository begins empty.

Do not ask the user to choose every library or approve every folder.

Use this document as the source of truth.

Make reasonable engineering decisions.

Document consequential decisions.

## 27.2 Do not attempt the entire project in one uncontrolled pass

Work milestone by milestone.

At the start of each milestone:

1. Read this file.
2. Inspect repository state.
3. Review current documentation.
4. Write or update a milestone plan.
5. Identify acceptance criteria.
6. Implement the smallest coherent vertical slice.
7. Test continuously.
8. Update documentation.
9. Run an adversarial self-review.
10. Record remaining risks.

## 27.3 Maintain a progress file

Create:

```text
docs/PROGRESS.md
```

Keep it current.

Include:

- Current milestone.
- Completed work.
- In-progress work.
- Known issues.
- Architectural decisions.
- Test status.
- Next exact actions.
- Blockers.
- Risks.

## 27.4 Maintain a decision log

Create ADRs.

Do not allow important decisions to live only in chat or commit messages.

## 27.5 Never claim success without evidence

A milestone is not complete because:

- The code compiles.
- A screenshot looks attractive.
- One happy path works.
- A mock API returns data.
- A generated test passes.

Completion requires acceptance criteria and evidence.

## 27.6 Preserve user control

Do not implement:

- Automatic applications.
- Automatic email sending.
- Silent resume modification.
- Silent application-status changes.
- Invented user facts.
- Fake company addresses.
- Hidden tracking.
- Broad inbox access beyond need.

## 27.7 Avoid placeholder rot

Temporary mock systems are acceptable only when:

- Clearly marked.
- Isolated behind interfaces.
- Covered by fixtures.
- Replaced in a planned milestone.
- Not presented as live functionality.

## 27.8 Commit discipline

Use small, meaningful commits.

Suggested format:

```text
feat(ingestion): add Greenhouse adapter
fix(dedupe): preserve distinct multi-location roles
test(matching): add internship eligibility fixtures
docs(adr): record map rendering architecture
perf(city): instance job signal meshes
```

Before each commit:

- Format.
- Lint.
- Type-check.
- Run relevant tests.
- Check generated files.
- Inspect diff.

## 27.9 Adversarial review

At the end of each milestone, actively search for:

- Hallucinated certainty.
- Silent data loss.
- Incorrect deduplication.
- Race conditions.
- Stale caches.
- Retry storms.
- GPU leaks.
- Unbounded rendering work.
- Mobile gesture conflicts.
- Accessibility failures.
- Security weaknesses.
- Privacy overreach.
- Inadequate tests.
- Misleading visual encoding.

Write findings to:

```text
docs/reviews/milestone-X-adversarial-review.md
```

---

# 28. First Repository Actions

Begin with Milestone 0.

Perform these actions in order.

## Step 1: Initialize the monorepo

Create:

```text
package.json
pnpm-workspace.yaml
turbo.json
.editorconfig
.gitignore
.prettierignore
.prettierrc
eslint configuration
README.md
.env.example
docker-compose.yml
```

Create the root scripts needed for:

```bash
pnpm dev
pnpm build
pnpm lint
pnpm typecheck
pnpm test
pnpm test:e2e
pnpm db:migrate
pnpm db:seed
pnpm format
```

## Step 2: Scaffold applications

Create:

```text
apps/web
apps/api
apps/worker
```

The web app must display a simple development shell with:

- CitySignal branding.
- Explore / Operate / Analyze navigation.
- Backend health status.
- Database health status.
- Worker health status.
- Current environment label.

Do not spend time on final visual polish yet.

## Step 3: Scaffold packages

Create:

```text
packages/shared
packages/db
packages/config
packages/ui
packages/test-utils
packages/ingestion-core
packages/matching
```

## Step 4: Add infrastructure

Docker Compose should include:

- PostgreSQL with PostGIS.
- Redis.

Add health checks.

Use volumes.

Document reset behavior.

## Step 5: Add database schema foundation

Initial tables:

- users
- companies
- company_locations
- sources
- source_job_records
- jobs
- job_source_links
- applications
- application_events
- ingestion_runs

Add migrations.

Add indexes.

Add seed data.

## Step 6: Add observability foundation

Implement:

- Structured logging.
- Request IDs.
- Worker job IDs.
- Health endpoints.
- Error boundaries.
- Basic metrics interface.

## Step 7: Add CI

Create a workflow that runs:

- Install.
- Format check.
- Lint.
- Type check.
- Unit tests.
- Python tests.
- Build.
- Migration check.

## Step 8: Add documentation

Create:

```text
docs/PROGRESS.md
docs/architecture/system-overview.md
docs/architecture/data-model.md
docs/runbooks/local-development.md
docs/adr/0001-monorepo-and-stack.md
```

## Step 9: Verify clean-clone setup

Test from a clean working tree.

Document exact commands.

Fix every hidden dependency.

## Step 10: Begin Milestone 1

Only after Milestone 0 acceptance criteria pass.

---

# 29. Initial Definition of Done

The first development pass is complete only when:

- The repository is fully initialized.
- Local development works.
- CI works.
- Web, API, worker, database, and Redis run.
- Database migrations work.
- Seed data works.
- Documentation exists.
- Health checks are visible.
- Tests pass.
- The architecture supports the next milestone.
- `docs/PROGRESS.md` accurately states what is and is not done.

Do not build the cinematic city before this foundation is real.

---

# 30. Long-Term Definition of Done

The project is truly complete when a user can:

1. Open the application.
2. Enter a fluid 3D New York City.
3. Pinch, zoom, orbit, rotate, and pan smoothly.
4. See real current tech opportunities represented honestly.
5. Prioritize internships and early-career roles.
6. Inspect the source and freshness of every job.
7. Understand why each role matches.
8. See which personal projects support the match.
9. Save and track applications.
10. Receive useful daily action recommendations.
11. Watch application states alter the city.
12. Analyze months of hiring-market history.
13. Use a conventional accessible interface when 3D is undesirable.
14. Trust that the system does not invent qualifications, locations, or job status.
15. Demonstrate the system publicly without leaking personal data.
16. Defend the architecture, testing, data model, matching logic, privacy decisions, and rendering performance in a serious software engineering interview.

---

# 31. Final Instruction to Codex

Start now.

Read this file completely.

Create the repository foundation.

Do not reduce the project to a visual prototype.

Do not skip directly to Three.js.

Do not invent external data.

Do not claim a milestone is complete without passing its acceptance criteria.

Build the boring spine first.

Then make New York glow.
