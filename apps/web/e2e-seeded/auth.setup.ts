import { expect, test as setup } from '@playwright/test';
import path from 'node:path';

/**
 * Sign in once, and hand every other spec the cookie. M5b, ADR 0037.
 *
 * The API answers 401 to everything except `/health` and `/auth`, so before
 * this file existed the whole seeded suite would have gone red at once — not
 * because anything is broken, but because nobody was signed in.
 *
 * **It signs in through the web app's own origin, not against the API
 * directly**, which is the point rather than a convenience. The rewrite in
 * `next.config.ts` is what makes the session cookie first-party; a setup that
 * talked to `127.0.0.1:8000` would get a cookie scoped to a host the browser
 * never visits, and the suite would pass while the thing a person does was
 * untested. Going through the proxy means this file exercises the same path
 * the product takes.
 *
 * The saved state then covers both halves of every spec: the pages the browser
 * loads, and the direct `request.get(API + …)` calls the specs make to derive
 * their expectations, because `API` points at the same origin.
 */

export const STORAGE_STATE = path.join(import.meta.dirname, '.auth', 'seeded.json');

const EMAIL = process.env.DEV_USER_EMAIL ?? 'dev@nightshift.local';
const PASSWORD = process.env.DEV_USER_PASSWORD ?? 'nightshift-demo-password';

setup('sign in as the seeded account', async ({ request }) => {
  const response = await request.post('/api/ns/auth/sign-in', {
    data: { email: EMAIL, password: PASSWORD },
  });

  // A hard failure with a message naming the cause. A 401 here means the seed
  // has not run or the password does not match `.env`, and without this the
  // symptom is every spec in the suite failing on an unrelated assertion.
  expect(
    response.status(),
    `POST /api/ns/auth/sign-in returned ${response.status()} for ${EMAIL}. ` +
      `Has \`make seed\` run, and does DEV_USER_PASSWORD match it?`,
  ).toBe(200);

  await request.storageState({ path: STORAGE_STATE });
});
