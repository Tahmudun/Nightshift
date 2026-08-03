import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CompanyCounts } from './CompanyDetail';

describe('CompanyCounts', () => {
  it('shows every closure state including the empty ones', () => {
    render(<CompanyCounts counts={{ open: 4, possibly_stale: 0, unverified: 0, closed: 2 }} />);
    // A state with no jobs reads as an explicit 0 rather than vanishing: a
    // missing count and a real zero are different claims.
    expect(screen.getByText(/possibly stale/i)).toBeVisible();
    expect(screen.getByTestId('count-possibly_stale')).toHaveTextContent('0');
    expect(screen.getByTestId('count-unverified')).toHaveTextContent('0');
    expect(screen.getByTestId('count-closed')).toHaveTextContent('2');
  });

  it('does not hide closed roles', () => {
    render(<CompanyCounts counts={{ open: 0, possibly_stale: 0, unverified: 0, closed: 7 }} />);
    expect(screen.getByTestId('count-closed')).toHaveTextContent('7');
    expect(screen.getByTestId('count-open')).toHaveTextContent('0');
  });

  it('renders all four states, never a subset', () => {
    render(<CompanyCounts counts={{ open: 1, possibly_stale: 2, unverified: 3, closed: 4 }} />);
    for (const state of ['open', 'possibly_stale', 'unverified', 'closed']) {
      expect(screen.getByTestId(`count-${state}`)).toBeVisible();
    }
  });
});
