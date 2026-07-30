import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ConfidenceLadder, ConfidenceLegend } from './ConfidenceLadder';

describe('ConfidenceLadder', () => {
  it('states the confidence in text, not only in colour (§12.4)', () => {
    render(<ConfidenceLadder confidence="city_only" />);
    expect(screen.getByText('City only')).toBeInTheDocument();
  });

  it('gives an accessible name carrying the rank and the meaning', () => {
    render(<ConfidenceLadder confidence="unknown" />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toContain('Unknown');
    expect(label).toContain('1 of 5');
    expect(label).toContain('not placed anywhere');
  });

  it('describes verified as placed on its building', () => {
    render(<ConfidenceLadder confidence="verified" />);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('5 of 5');
  });
});

describe('ConfidenceLegend', () => {
  it('documents every confidence value in the interface (§4.3)', () => {
    render(<ConfidenceLegend />);
    for (const label of ['Verified', 'Approximate', 'City only', 'Remote', 'Unknown']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('marks the three unplaceable levels as not shown on the map', () => {
    render(<ConfidenceLegend />);
    expect(screen.getAllByText(/not placed on the map/)).toHaveLength(3);
  });
});
