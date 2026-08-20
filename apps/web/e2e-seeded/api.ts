/**
 * The seeded specs' own way of talking to the API. M5b, ADR 0037.
 *
 * These specs derive their expectations from the API at run time rather than
 * hard-coding them, so most of them make a direct request or two alongside the
 * pages they drive. Two things changed under them at M5b and both are here
 * rather than repeated across twelve files.
 *
 * **The address.** The browser now reaches the API through the web app's own
 * origin, so these requests go the same way — the path a person's browser
 * takes, rather than a private door into the API that nothing else uses.
 *
 * **The credential.** Every route except `/health` and `/auth` needs a session.
 * These calls use Node's global `fetch`, which has no cookie jar and knows
 * nothing about the `storageState` the browser context carries, so they take a
 * bearer token instead — the same path `scripts/verify.py` uses and the one
 * M5c's MCP server will use.
 *
 * That the pages authenticate by cookie and these calls by bearer is not an
 * inconsistency to tidy away later. They are the two ways a session can be
 * presented, they resolve to one row in `user_sessions`, and this suite now
 * exercises both on every run.
 */

import { expect } from '@playwright/test';

/**
 * Absolute, and it has to be: this module uses Node's `fetch`, which rejects a
 * relative URL outright with "Failed to parse URL". The first version of this
 * change set it to `/api/ns` — correct for the browser, and it took 35 specs
 * down at once with `TypeError: Invalid URL`.
 */
export const API = `${process.env.WEB_ORIGIN ?? 'http://localhost:3000'}/api/ns`;

const EMAIL = process.env.DEV_USER_EMAIL ?? 'dev@nightshift.local';
const PASSWORD = process.env.DEV_USER_PASSWORD ?? 'nightshift-demo-password';

let token: Promise<string> | null = null;

/** Sign in once per worker process, and hand the same token to every caller. */
function bearer(): Promise<string> {
  token ??= (async () => {
    const response = await fetch(`${API}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
    });
    expect(
      response.ok,
      `POST ${API}/auth/token returned ${response.status} for ${EMAIL} — ` +
        'has `make seed` run, and does DEV_USER_PASSWORD match it?',
    ).toBe(true);
    const body = (await response.json()) as { access_token: string };
    return body.access_token;
  })();
  return token;
}

/** `fetch`, with this suite's session on it. Same signature otherwise. */
export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const authorization = `Bearer ${await bearer()}`;
  return fetch(url, { ...init, headers: { ...init?.headers, Authorization: authorization } });
}
