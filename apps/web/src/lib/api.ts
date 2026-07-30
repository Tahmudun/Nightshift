/**
 * The API client. One place that knows the base URL and one place that parses.
 *
 * Every response goes through a Zod schema before it reaches a component, so a
 * component never handles `unknown` and never has to defend against a shape the
 * API did not promise.
 */

import type { z } from 'zod';

import {
  healthSchema,
  jobListSchema,
  sourceHealthSchema,
  statsSchema,
  type Health,
  type JobList,
  type SourceHealth,
  type Stats,
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
  status?: string;
  confidence?: string;
}

export function fetchJobs(query: JobQuery = {}): Promise<JobList> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit ?? 25));
  params.set('offset', String(query.offset ?? 0));
  if (query.status) params.set('status', query.status);
  if (query.confidence) params.set('confidence', query.confidence);
  return request(`/jobs?${params.toString()}`, jobListSchema);
}

export function fetchStats(): Promise<Stats> {
  return request('/stats', statsSchema);
}

export function fetchSourceHealth(): Promise<SourceHealth[]> {
  return request('/sources', sourceHealthSchema.array());
}
