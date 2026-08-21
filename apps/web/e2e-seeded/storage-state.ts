/**
 * Where the seeded suite keeps its signed-in state.
 *
 * A module of its own, importing nothing, and both of those are load-bearing.
 *
 * `playwright.seeded.config.ts` needs this path, and `auth.setup.ts` needs it
 * too. Putting it in `auth.setup.ts` and importing it from the config makes the
 * config *execute the setup file* while it is being loaded — which calls
 * `setup()` outside a test run, and Playwright refuses: "Playwright Test did
 * not expect test() to be called here." The suite then fails while loading its
 * config, before one test runs, so it reports a Node stack trace and an exit
 * code rather than a result. **Nothing is verified and it does not look like
 * nothing was verified**, which is the worst shape a failure can take here.
 *
 * A relative string rather than `import.meta.dirname` or `__dirname`.
 * Playwright loads config files as CommonJS, so `import.meta` throws outright —
 * the first version of this did exactly that. `__dirname` works today and
 * breaks silently the day that loader changes, which trades one version of this
 * bug for another. Playwright resolves a relative `storageState` against the
 * config's own directory.
 */
export const STORAGE_STATE = 'e2e-seeded/.auth/seeded.json';
