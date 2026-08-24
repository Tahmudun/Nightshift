import { describe, expect, it } from 'vitest';

import { ORIGIN_LABEL, originLabel, readCapture, readField } from '@/lib/capture';

describe('readField', () => {
  it('shows the parser when it is the only reader', () => {
    expect(readField('Ramp', null)).toEqual({
      value: 'Ramp',
      source: 'parser',
      parser: 'Ramp',
      assistant: null,
    });
  });

  it('shows the assistant when the parser declined', () => {
    // The common case on prose: the line parser reads nothing and the model
    // that saw the page reads everything.
    expect(readField(null, 'Ramp')).toEqual({
      value: 'Ramp',
      source: 'assistant',
      parser: null,
      assistant: 'Ramp',
    });
  });

  it('calls it agreed when both read the same thing', () => {
    expect(readField('Ramp', ' ramp ').source).toBe('agreed');
  });

  it('opens on nothing when the two readers disagree', () => {
    // The rule this module exists for. A silent winner here is the thing the
    // two-step review is designed to prevent — a pre-filled value is a
    // default, and a default is what gets accepted without being read.
    const reading = readField('Ramp', 'Stripe');
    expect(reading.source).toBe('conflict');
    expect(reading.value).toBe('');
    expect(reading.parser).toBe('Ramp');
    expect(reading.assistant).toBe('Stripe');
  });

  it('treats a blank string as nothing offered', () => {
    expect(readField('   ', null).source).toBe('none');
    expect(readField('   ', null).value).toBe('');
  });

  it('reports nothing when neither reader had anything', () => {
    expect(readField(null, null).source).toBe('none');
  });
});

describe('readCapture', () => {
  const proposed = {
    title: 'Staff Backend Engineer',
    company_name: 'Ramp',
    location_text: null,
    employment_type: null,
  };

  it('reads every field independently', () => {
    const reading = readCapture(proposed, {
      title: 'Staff Backend Engineer',
      company_name: 'Stripe',
      location_text: 'New York, NY',
    });
    expect(reading.title.source).toBe('agreed');
    expect(reading.company_name.source).toBe('conflict');
    expect(reading.location_text.source).toBe('assistant');
  });

  it('falls back to the parser alone when no assistant was involved', () => {
    const reading = readCapture(proposed, null);
    expect(reading.title.source).toBe('parser');
    expect(reading.company_name.value).toBe('Ramp');
    expect(reading.location_text.source).toBe('none');
  });
});

describe('originLabel', () => {
  /**
   * Q13, answered 2026-08-24. The live walk captured a real LinkedIn posting
   * through Claude Desktop and the queue row read **"Pasted text"** — because
   * Claude sent no `source_url`, so `origin` was `none`, and `none` had one
   * label written for the browser form.
   *
   * "Pasted text" is true of somebody typing into the box and false of a
   * capture made in a Claude session, and the row is the reader's only account
   * of where a posting came from. The distinction the UI *can* honestly draw
   * is not which website — nothing recorded that — but **whether an assistant
   * was involved**, which the quote columns state as fact.
   */
  it('names every origin the API can send', () => {
    expect(Object.keys(ORIGIN_LABEL).sort()).toEqual(['indeed', 'linkedin', 'none', 'other']);
  });

  it('says a link was never recorded when Claude captured it without one', () => {
    expect(
      originLabel('none', { title: 'Staff Engineer', company_name: null, location_text: null }),
    ).toBe('Origin not recorded');
  });

  it('still calls a browser paste a browser paste', () => {
    expect(originLabel('none', null)).toBe('Pasted text');
  });

  it('leaves an origin that is actually known alone', () => {
    expect(originLabel('linkedin', { title: 'x', company_name: null, location_text: null })).toBe(
      'From LinkedIn',
    );
    expect(originLabel('indeed', null)).toBe('From Indeed');
    expect(originLabel('other', null)).toBe('From a link');
  });
});
