/**
 * The selection, as it lives in the address bar.
 *
 * §5.6 asks selection to be shareable and to *preserve filters*, and those two
 * pull in the same direction: the URL is the shareable thing, so the selection
 * has to be a parameter added to whatever query is already there rather than a
 * new query that replaces it. Both functions here exist because getting that
 * wrong is easy and quiet — `?job=…` built from scratch drops every filter the
 * person had set, and the city still looks right because the map has its own
 * copy of the corpus.
 *
 * Pure, so the round trip can be tested without a router.
 */

/**
 * The query parameter. Singular and unprefixed, matching `/explore`'s own
 * vocabulary — the city is a second view of that list, not a separate product
 * with its own URL language.
 */
export const SELECTION_PARAM = 'job';

/**
 * The shape `job_id` actually has, which is the same one `citySignalSchema`
 * enforces on the way in from the API.
 */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Something that answers `get`: `URLSearchParams`, or Next's read-only version of it. */
export interface ReadableParams {
  get(key: string): string | null;
  forEach(callback: (value: string, key: string) => void): void;
}

/**
 * The selected role in a URL, or null.
 *
 * A value that is not a job id is read as *no selection* rather than carried
 * around as one. It can never match a signal, so holding it would give the
 * page a selection that is permanently unresolvable — and the panel would have
 * to explain a role that was never real. The sync then rewrites the parameter
 * away, which is the honest end state.
 */
export function selectionFromParams(params: ReadableParams): string | null {
  const raw = params.get(SELECTION_PARAM);
  if (raw === null || !UUID.test(raw)) return null;
  return raw.toLowerCase();
}

/**
 * The same page with a different role selected — every other parameter intact.
 *
 * `null` removes the parameter rather than setting it empty, so clearing a
 * selection gives back the URL the person would have had without ever making
 * one. A stray `?job=` is a URL that looks like it means something.
 */
export function selectionHref(
  pathname: string,
  params: ReadableParams,
  jobId: string | null,
): string {
  const next = new URLSearchParams();
  params.forEach((value, key) => {
    if (key !== SELECTION_PARAM) next.append(key, value);
  });
  // `append`, not `set`, and that is the deliberate choice: `set` would paper
  // over a broken filter above by silently collapsing a duplicated parameter,
  // so the test that says a selection replaces rather than doubles would have
  // nothing left to catch. Appending makes the filter load-bearing.
  if (jobId !== null) next.append(SELECTION_PARAM, jobId);
  const query = next.toString();
  return query === '' ? pathname : `${pathname}?${query}`;
}
