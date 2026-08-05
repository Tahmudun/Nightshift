import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { JobRequirements } from './JobRequirements';
import { jobRequirementSchema } from '@/lib/schemas';

const DESCRIPTION = "WHAT YOU'LL NEED Proficiency in Kotlin. NICE TO HAVES React.";

// Parsed through the real schema, because M2c shipped a component test fed
// data the API cannot produce — the exact row its schema exists to refuse.
const required = jobRequirementSchema.parse({
  kind: 'technology',
  value: 'Kotlin',
  raw_text: 'Kotlin',
  char_start: DESCRIPTION.indexOf('Kotlin'),
  char_end: DESCRIPTION.indexOf('Kotlin') + 'Kotlin'.length,
  necessity: 'required',
  has_equivalence: false,
});

const preferred = jobRequirementSchema.parse({
  kind: 'technology',
  value: 'React',
  raw_text: 'React',
  char_start: DESCRIPTION.indexOf('React'),
  char_end: DESCRIPTION.indexOf('React') + 'React'.length,
  necessity: 'preferred',
  has_equivalence: false,
});

describe('JobRequirements', () => {
  it('separates what is required from what is merely preferred', () => {
    render(
      <JobRequirements
        requirements={[required, preferred]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    const requiredSection = screen.getByRole('region', { name: /required/i });
    expect(requiredSection).toHaveTextContent('Kotlin');
    expect(requiredSection).not.toHaveTextContent('React');
  });

  it('quotes the sentence each requirement came from', () => {
    render(
      <JobRequirements
        requirements={[required]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    expect(screen.getByText(/Proficiency in Kotlin/)).toBeInTheDocument();
  });

  it('quotes the posting rather than reconstructing it', () => {
    // The quoted sentence must be a literal slice of the description. A
    // component that rebuilt the sentence from `value` would pass the test
    // above and still be putting words in the posting's mouth.
    render(
      <JobRequirements
        requirements={[required]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    const quote = screen.getByTestId('requirement-quote');
    expect(DESCRIPTION).toContain(quote.textContent);
  });

  it('says nothing has been read rather than showing an empty list', () => {
    render(
      <JobRequirements requirements={[]} descriptionText={DESCRIPTION} extractorVersion={null} />,
    );
    expect(screen.getByText(/not been read/i)).toBeInTheDocument();
  });

  it('distinguishes an empty result from an unread posting', () => {
    render(
      <JobRequirements requirements={[]} descriptionText={DESCRIPTION} extractorVersion="m3a.1" />,
    );
    expect(screen.getByText(/no requirements this system could read/i)).toBeInTheDocument();
    expect(screen.queryByText(/not been read/i)).not.toBeInTheDocument();
  });

  it('marks a degree carrying an equivalence clause', () => {
    const phd = jobRequirementSchema.parse({
      kind: 'degree',
      value: 'phd',
      raw_text: 'PhD',
      char_start: 0,
      char_end: 3,
      necessity: 'required',
      has_equivalence: true,
    });
    render(
      <JobRequirements
        requirements={[phd]}
        descriptionText="PhD in Computer Science or equivalent experience"
        extractorVersion="m3a.1"
      />,
    );
    // By test id, not by text: the quoted sentence contains the same phrase,
    // which is the point — the marker is only trustworthy because the posting
    // is right there saying it. Matching on text alone finds both.
    expect(screen.getByTestId('equivalence-marker')).toHaveTextContent(/or equivalent/i);
    expect(screen.getByTestId('requirement-quote')).toHaveTextContent(/or equivalent experience/i);
  });

  it('does not mark a requirement that carries no equivalence clause', () => {
    render(
      <JobRequirements
        requirements={[required]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    expect(screen.queryByTestId('equivalence-marker')).not.toBeInTheDocument();
  });

  it('names the rules that produced the rows', () => {
    // I4's habit, early: a claim on screen carries the version behind it.
    render(
      <JobRequirements
        requirements={[required]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    expect(screen.getByText(/m3a\.1/)).toBeInTheDocument();
  });

  it('renders a section only when it has rows', () => {
    render(
      <JobRequirements
        requirements={[preferred]}
        descriptionText={DESCRIPTION}
        extractorVersion="m3a.1"
      />,
    );
    // An empty "Required" heading reads as "this posting requires nothing",
    // which is a claim this component has no basis to make.
    expect(screen.queryByRole('region', { name: /^required/i })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: /preferred/i })).toBeInTheDocument();
  });
});
