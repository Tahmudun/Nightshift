/**
 * The API client. One place that knows the base URL and one place that parses.
 *
 * Every response goes through a Zod schema before it reaches a component, so a
 * component never handles `unknown` and never has to defend against a shape the
 * API did not promise.
 */

import type { z } from 'zod';

import {
  applicationDetailSchema,
  applicationEventSchema,
  applicationListSchema,
  applicationSchema,
  companyDetailSchema,
  companyListSchema,
  coverageSchema,
  dailyQueueSchema,
  healthSchema,
  jobDetailSchema,
  jobAdminListSchema,
  jobListSchema,
  jobStatusEventSchema,
  matchRankingSchema,
  boardPollStateSchema,
  sourceHealthSchema,
  statsSchema,
  confirmationSchema,
  profileSchema,
  resumeDetailSchema,
  resumeListSchema,
  userProjectSchema,
  userSkillSchema,
  type CompanyDetail,
  type CompanyList,
  type Coverage,
  type DailyQueue,
  type Health,
  type JobDetail,
  type JobAdminList,
  type JobList,
  type JobStatusEvent,
  type MatchRanking,
  type BoardPollState,
  type SourceHealth,
  type Stats,
  type Application,
  type ApplicationDetail,
  type ApplicationEvent,
  type ApplicationList,
  type ApplicationPriority,
  type ApplicationStage,
  type Confirmation,
  type ProficiencyLevel,
  type Profile,
  type RemotePreference,
  type ResumeDetail,
  type ResumeList,
  type ResumeVariant,
  type UserProject,
  type UserSkill,
  type WorkAuthorization,
} from './schemas';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

/** Thrown for any non-2xx or unparseable response. Carries the status. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * The input type is `unknown` and the output is `T`: we are parsing arbitrary
 * JSON, and schemas with `.default()` legitimately accept less than they emit.
 * Declaring both sides as `T` makes those two schemas fail to typecheck.
 */
async function request<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
      cache: 'no-store',
    });
  } catch {
    // A dead API is the common case during local development, so the message
    // says what to do about it rather than just "fetch failed".
    throw new ApiError(
      `cannot reach the API at ${API_BASE_URL} — is it running? (\`make dev\`)`,
      null,
    );
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      body !== null && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(`${path} failed: ${detail}`, response.status);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(`${path} returned an unexpected shape: ${parsed.error.message}`, 200);
  }
  return parsed.data;
}

/**
 * Health is a special case: a 503 body is still a valid, useful HealthResponse.
 * Treating it as an error would lose exactly the information we asked for.
 */
export async function fetchHealth(): Promise<Health> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/health`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(`cannot reach the API at ${API_BASE_URL}`, null);
  }

  const body: unknown = await response.json().catch(() => null);
  const parsed = healthSchema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(`/health returned an unexpected shape`, response.status);
  }
  return parsed.data;
}

export interface JobQuery {
  limit?: number;
  offset?: number;
  /** Searches the job title. Widen it with `include_description`. */
  q?: string;
  include_description?: boolean;
  company?: string;
  city?: string;
  employment_type?: string;
  remote_policy?: string;
  status?: string;
  confidence?: string;
  source?: string;
  first_seen_after?: string;
  salary_at_least?: number;
  /**
   * A technology the posting names. Resolved server-side through
   * `data/skills.yaml`, so `GCP` finds postings stored as `Google Cloud`.
   * Incomplete by a measured amount — see `excluded_no_requirements`.
   */
  skill?: string;
  internship_season?: string;
  internship_year?: number;
}

/**
 * Only non-empty values become query parameters, so a cleared filter really
 * clears rather than being sent as an empty string the API would then try to
 * match against.
 */
export function fetchJobs(query: JobQuery = {}): Promise<JobList> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit ?? 25));
  params.set('offset', String(query.offset ?? 0));
  const optional: ReadonlyArray<[string, string | number | boolean | undefined]> = [
    ['q', query.q],
    ['include_description', query.include_description],
    ['company', query.company],
    ['city', query.city],
    ['employment_type', query.employment_type],
    ['remote_policy', query.remote_policy],
    ['status', query.status],
    ['confidence', query.confidence],
    ['source', query.source],
    ['first_seen_after', query.first_seen_after],
    ['salary_at_least', query.salary_at_least],
    ['skill', query.skill],
    ['internship_season', query.internship_season],
    ['internship_year', query.internship_year],
  ];
  for (const [key, value] of optional) {
    if (value === undefined || value === '' || value === false) continue;
    params.set(key, String(value));
  }
  return request(`/jobs?${params.toString()}`, jobListSchema);
}

/** One job in full, with its provenance. */
export function fetchJob(jobId: string): Promise<JobDetail> {
  return request(`/jobs/${jobId}`, jobDetailSchema);
}

/**
 * The ranked list: this person's scored postings, banded by eligibility.
 *
 * A separate endpoint from `fetchJobs` rather than a flag on it, because they
 * are different resources — `/jobs` is the corpus, the same rows for everybody
 * and ordered by recency; this is a list of `match_results`, which exist only
 * for a person.
 */
export function fetchMatches(limit = 100): Promise<MatchRanking> {
  return request(`/matches?limit=${limit}`, matchRankingSchema);
}

/** Every employer we have ingested a role from. */
export function fetchCompanies(q?: string): Promise<CompanyList> {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  return request(`/companies?${params.toString()}`, companyListSchema);
}

export function fetchCompany(companyId: string): Promise<CompanyDetail> {
  return request(`/companies/${companyId}`, companyDetailSchema);
}

export function fetchStats(): Promise<Stats> {
  return request('/stats', statsSchema);
}

export function fetchSourceHealth(): Promise<SourceHealth[]> {
  return request('/sources', sourceHealthSchema.array());
}

export function fetchBoardPollState(): Promise<BoardPollState[]> {
  return request('/boards', boardPollStateSchema.array());
}

export interface JobAdminQuery {
  limit?: number;
  offset?: number;
  status?: string;
}

/**
 * The operational view of the job table. Unlike `fetchJobs`, this includes
 * closed jobs by default — hiding them would make the closure machine
 * unobservable, which is the one thing the admin view exists to prevent.
 */
export function fetchJobAdmin(query: JobAdminQuery = {}): Promise<JobAdminList> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit ?? 50));
  params.set('offset', String(query.offset ?? 0));
  if (query.status) params.set('status', query.status);
  return request(`/jobs/admin?${params.toString()}`, jobAdminListSchema);
}

/** Every closure-machine transition for one job, oldest first. */
export function fetchJobHistory(jobId: string): Promise<JobStatusEvent[]> {
  return request(`/jobs/${jobId}/history`, jobStatusEventSchema.array());
}

/** What is covered and — the reason the endpoint exists — what is not. */
export function fetchCoverage(): Promise<Coverage> {
  return request('/coverage', coverageSchema);
}

/** Today's queue, and the rows it cannot compute yet. Read-only by design. */
export function fetchQueue(): Promise<DailyQueue> {
  return request('/queue', dailyQueueSchema);
}

/**
 * Mutations go through the same `request()` as every read, so a failed write
 * carries the API's own message rather than an unparsed Response.
 */
async function send<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  method: 'POST' | 'PATCH',
  body?: unknown,
): Promise<T> {
  // The key is omitted rather than set to `undefined`: this project runs
  // `exactOptionalPropertyTypes`, under which `body: undefined` is not the same
  // as no body and does not typecheck.
  const init: RequestInit = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) init.body = JSON.stringify(body);
  return request(path, schema, init);
}

export interface ApplicationQuery {
  stage?: ApplicationStage;
  archived?: boolean;
  limit?: number;
  offset?: number;
}

export function fetchApplications(query: ApplicationQuery = {}): Promise<ApplicationList> {
  const params = new URLSearchParams();
  if (query.stage) params.set('stage', query.stage);
  if (query.archived) params.set('archived', 'true');
  params.set('limit', String(query.limit ?? 100));
  params.set('offset', String(query.offset ?? 0));
  return request(`/applications?${params.toString()}`, applicationListSchema);
}

export function fetchApplication(id: string): Promise<ApplicationDetail> {
  return request(`/applications/${id}`, applicationDetailSchema);
}

/** Save a job. Idempotent — the API answers 200 if it was already saved. */
export function saveJob(jobId: string): Promise<Application> {
  return send('/applications', applicationSchema, 'POST', { job_id: jobId });
}

export interface StageChange {
  to_stage: ApplicationStage;
  note?: string;
  applied_at?: string;
  application_url?: string;
}

export function changeStage(id: string, change: StageChange): Promise<ApplicationDetail> {
  return send(`/applications/${id}/stage`, applicationDetailSchema, 'PATCH', change);
}

export function addNote(id: string, body: string): Promise<ApplicationEvent> {
  return send(`/applications/${id}/notes`, applicationEventSchema, 'POST', { body });
}

export function scheduleInterview(id: string, scheduledFor: string): Promise<ApplicationEvent> {
  return send(`/applications/${id}/interviews`, applicationEventSchema, 'POST', {
    scheduled_for: scheduledFor,
  });
}

/**
 * Only the keys present in `changes` are sent, so an explicit `null` clears a
 * field and an omitted key leaves it alone — matching `ApplicationPatchIn`.
 */
export function patchApplication(
  id: string,
  changes: Partial<{
    priority: ApplicationPriority;
    next_action_at: string | null;
    application_url: string | null;
    source_of_application: string | null;
    applied_at: string | null;
    selected_resume_id: string | null;
  }>,
): Promise<ApplicationDetail> {
  return send(`/applications/${id}`, applicationDetailSchema, 'PATCH', changes);
}

export function setArchived(id: string, archived: boolean): Promise<ApplicationDetail> {
  return send(
    `/applications/${id}/${archived ? 'archive' : 'restore'}`,
    applicationDetailSchema,
    'POST',
  );
}

/* -------------------------------------------------------------------------
 * Profile and resumes (M2c)
 * ------------------------------------------------------------------------- */

/**
 * A 204 has no body, so it cannot go through `request` — `schema.parse(null)`
 * would reject a response that succeeded.
 */
async function remove(path: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method: 'DELETE', cache: 'no-store' });
  } catch {
    throw new ApiError(
      `cannot reach the API at ${API_BASE_URL} — is it running? (\`make dev\`)`,
      null,
    );
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body !== null && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(`${path} failed: ${detail}`, response.status);
  }
}

export function fetchProfile(): Promise<Profile> {
  return request('/profile', profileSchema);
}

/**
 * Only the keys present in `changes` are sent, so an explicit `null` clears a
 * field and an omitted key leaves it alone — matching `ProfilePatchIn`.
 */
export function patchProfile(
  changes: Partial<{
    display_name: string | null;
    graduation_year: number | null;
    graduation_month: number | null;
    degree: string | null;
    school: string | null;
    work_authorization: WorkAuthorization;
    home_location_text: string | null;
    remote_preference: RemotePreference;
    minimum_salary: number | null;
    preferred_roles: string[];
    preferred_locations: string[];
  }>,
): Promise<Profile> {
  return send('/profile', profileSchema, 'PATCH', changes);
}

export function addSkill(name: string, proficiency?: ProficiencyLevel): Promise<UserSkill> {
  const body: { name: string; proficiency_level?: ProficiencyLevel } = { name };
  if (proficiency !== undefined) body.proficiency_level = proficiency;
  return send('/profile/skills', userSkillSchema, 'POST', body);
}

export function removeSkill(id: string): Promise<void> {
  return remove(`/profile/skills/${id}`);
}

export function addProject(project: {
  name: string;
  summary?: string;
  evidence?: string;
  repository_url?: string;
  demo_url?: string;
  technologies?: string[];
}): Promise<UserProject> {
  return send('/profile/projects', userProjectSchema, 'POST', project);
}

export function removeProject(id: string): Promise<void> {
  return remove(`/profile/projects/${id}`);
}

export function listResumes(): Promise<ResumeList> {
  return request('/resumes', resumeListSchema);
}

export function fetchResume(id: string): Promise<ResumeDetail> {
  return request(`/resumes/${id}`, resumeDetailSchema);
}

export function pasteResume(text: string, name?: string): Promise<ResumeDetail> {
  const body: { text: string; name?: string } = { text };
  if (name !== undefined) body.name = name;
  return send('/resumes/paste', resumeDetailSchema, 'POST', body);
}

/**
 * The only call in this client that does not send JSON.
 *
 * No `Content-Type` header: the browser sets the multipart boundary, and
 * setting the header by hand produces a request the server cannot parse.
 */
export async function uploadResume(file: File, name?: string): Promise<ResumeDetail> {
  const body = new FormData();
  body.append('file', file);
  if (name !== undefined) body.append('name', name);
  return request('/resumes/upload', resumeDetailSchema, { method: 'POST', body });
}

export function patchResume(
  id: string,
  changes: Partial<{ name: string; variant_type: ResumeVariant; is_default: boolean }>,
): Promise<ResumeDetail> {
  return send(`/resumes/${id}`, resumeDetailSchema, 'PATCH', changes);
}

export function deleteResume(id: string): Promise<void> {
  return remove(`/resumes/${id}`);
}

/**
 * The one call in the product that can turn a proposal into a fact.
 *
 * It sends only the ids the person decided on. A proposal left undecided stays
 * pending — silence is not consent (I2).
 */
export function confirmExtractions(
  resumeId: string,
  decisions: { extraction_id: string; decision: 'confirm' | 'reject' }[],
): Promise<Confirmation> {
  return send(`/resumes/${resumeId}/confirm`, confirmationSchema, 'POST', { decisions });
}
