import { describe, expect, it } from 'vitest';

import { ORIGIN_LABEL, readCapture, readField } from '@/lib/capture';

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

describe('ORIGIN_LABEL', () => {
  it('names every origin the API can send', () => {
    expect(Object.keys(ORIGIN_LABEL).sort()).toEqual(['indeed', 'linkedin', 'none', 'other']);
  });
});
