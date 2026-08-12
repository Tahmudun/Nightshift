import { describe, expect, it } from 'vitest';

import { selectionFromParams, selectionHref, SELECTION_PARAM } from './selection';

const JOB = '3f9a1c22-9b4e-4c7a-9f1d-2b6e5a8c0d31';

describe('selectionFromParams', () => {
  it('reads the selected role out of the query', () => {
    expect(selectionFromParams(new URLSearchParams(`${SELECTION_PARAM}=${JOB}`))).toBe(JOB);
  });

  it('answers null when nothing is selected', () => {
    expect(selectionFromParams(new URLSearchParams('sort=openings'))).toBeNull();
  });

  it('treats a value that is not a job id as no selection', () => {
    // Carrying it would give the page a selection that can never resolve to a
    // role, and a panel that has to describe something that was never real.
    expect(selectionFromParams(new URLSearchParams(`${SELECTION_PARAM}=alloy`))).toBeNull();
    expect(selectionFromParams(new URLSearchParams(`${SELECTION_PARAM}=`))).toBeNull();
  });

  it('normalises case, so two links to the same role are the same selection', () => {
    expect(
      selectionFromParams(new URLSearchParams(`${SELECTION_PARAM}=${JOB.toUpperCase()}`)),
    ).toBe(JOB);
  });
});

describe('selectionHref', () => {
  it('keeps every other parameter — §5.6 asks selection to preserve filters', () => {
    const href = selectionHref(
      '/explore/city',
      new URLSearchParams('remote_policy=hybrid&q=infra'),
      JOB,
    );

    const params = new URL(href, 'https://example.test').searchParams;
    expect(params.get('remote_policy')).toBe('hybrid');
    expect(params.get('q')).toBe('infra');
    expect(params.get(SELECTION_PARAM)).toBe(JOB);
  });

  it('replaces a selection rather than appending a second one', () => {
    const href = selectionHref(
      '/explore/city',
      new URLSearchParams(`${SELECTION_PARAM}=${JOB}`),
      [...'11111111-2222-4333-8444-555555555555'].join(''),
    );

    expect(new URL(href, 'https://example.test').searchParams.getAll(SELECTION_PARAM)).toEqual([
      '11111111-2222-4333-8444-555555555555',
    ]);
  });

  it('removes the parameter entirely when the selection is cleared', () => {
    const href = selectionHref(
      '/explore/city',
      new URLSearchParams(`${SELECTION_PARAM}=${JOB}`),
      null,
    );

    // Not `?job=`. A URL with an empty parameter looks like it means something.
    expect(href).toBe('/explore/city');
  });

  it('leaves the other parameters behind when a selection is cleared', () => {
    const href = selectionHref(
      '/explore/city',
      new URLSearchParams(`q=infra&${SELECTION_PARAM}=${JOB}`),
      null,
    );

    expect(href).toBe('/explore/city?q=infra');
  });

  it('keeps repeated parameters repeated', () => {
    // `append`, not `set`. A filter that legitimately appears twice — two
    // skills, two sources — would be silently collapsed to one by a `set`, and
    // the person would lose half a filter by clicking a beacon.
    const href = selectionHref('/explore/city', new URLSearchParams('skill=go&skill=rust'), JOB);

    expect(new URL(href, 'https://example.test').searchParams.getAll('skill')).toEqual([
      'go',
      'rust',
    ]);
  });
});
