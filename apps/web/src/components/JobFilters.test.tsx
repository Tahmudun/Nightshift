import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { JobFilters } from './JobFilters';

const DEFERRED = [
  {
    name: 'borough',
    blocked_on: 'M4',
    reason: 'A posting saying "New York, NY" does not say which borough it is in.',
  },
  { name: 'match_score', blocked_on: 'M3', reason: 'No score exists yet.' },
];

describe('JobFilters', () => {
  it('reports a text change to its parent without fetching anything itself', () => {
    const onChange = vi.fn();
    render(<JobFilters value={{}} onChange={onChange} deferred={[]} />);
    fireEvent.change(screen.getByLabelText(/^search$/i), { target: { value: 'engineer' } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0]?.[0]).toEqual({ q: 'engineer' });
  });

  it('names every deferred filter and shows its reason unexpanded', () => {
    const { container } = render(<JobFilters value={{}} onChange={vi.fn()} deferred={DEFERRED} />);
    // Visible without clicking anything. The gap must not be hidden behind a
    // disclosure — the same rule the coverage page is tested against.
    expect(screen.getByText(/which borough it is in/i)).toBeVisible();
    expect(screen.getByText(/no score exists yet/i)).toBeVisible();
    expect(container.querySelector('details')).toBeNull();
  });

  it('renders a deferred filter as disabled so it cannot be used', () => {
    render(<JobFilters value={{}} onChange={vi.fn()} deferred={DEFERRED} />);
    expect(screen.getByLabelText(/borough/i)).toBeDisabled();
    expect(screen.getByLabelText(/match score/i)).toBeDisabled();
  });

  it('clearing a field removes it rather than sending an empty string', () => {
    const onChange = vi.fn();
    render(<JobFilters value={{ city: 'Brooklyn' }} onChange={onChange} deferred={[]} />);
    fireEvent.change(screen.getByLabelText(/^city$/i), { target: { value: '' } });
    const next = onChange.mock.calls[0]?.[0] as { city?: string };
    expect('city' in next).toBe(false);
  });

  it('keeps the other filters when one changes', () => {
    const onChange = vi.fn();
    render(
      <JobFilters value={{ q: 'engineer', city: 'Brooklyn' }} onChange={onChange} deferred={[]} />,
    );
    fireEvent.change(screen.getByLabelText(/^city$/i), { target: { value: 'Queens' } });
    expect(onChange.mock.calls[0]?.[0]).toEqual({ q: 'engineer', city: 'Queens' });
  });

  describe('the two filters M3b turned on', () => {
    it('sends a skill as typed and lets the API resolve the alias', () => {
      // `golang` must reach the API unaltered. Resolving it here would put a
      // second copy of the vocabulary in the browser, and two copies is how the
      // filter and the extractor come to disagree about what `Go` means.
      const onChange = vi.fn();
      render(<JobFilters value={{}} onChange={onChange} deferred={[]} />);
      fireEvent.change(screen.getByLabelText(/^skill$/i), { target: { value: 'golang' } });
      expect(onChange.mock.calls[0]?.[0]).toEqual({ skill: 'golang' });
    });

    it('states what the skill filter is based on, beside the control', () => {
      // The human's decision of 2026-08-05: this filter comes on *with what it
      // is based on stated next to it*. Recall of 0.861 means it hides roughly
      // one matching role in seven, and a filter that hides part of its own
      // answer silently is worse than no filter.
      render(<JobFilters value={{}} onChange={vi.fn()} deferred={[]} />);
      expect(screen.getByText(/0\.861/)).toBeVisible();
    });

    it('offers a season and a year as separate controls', () => {
      // Two corpus internships state a year and no season. Collapsed into one
      // control, asking for 2027 could not reach them.
      const onChange = vi.fn();
      render(<JobFilters value={{}} onChange={onChange} deferred={[]} />);
      fireEvent.change(screen.getByLabelText(/internship season/i), {
        target: { value: 'summer' },
      });
      expect(onChange.mock.calls[0]?.[0]).toEqual({ internship_season: 'summer' });

      fireEvent.change(screen.getByLabelText(/internship year/i), { target: { value: '2027' } });
      expect(onChange.mock.calls[1]?.[0]).toEqual({ internship_year: 2027 });
    });

    it('no longer lists either of them as unavailable', () => {
      // The deferral entries are deleted server-side, so this asserts the panel
      // does not carry its own stale copy of the same claim. Three "not built"
      // lists in this project have gone stale in exactly that way.
      render(<JobFilters value={{}} onChange={vi.fn()} deferred={DEFERRED} />);
      const unavailable = screen.getByRole('heading', { name: /not available yet/i }).parentElement;
      expect(unavailable?.textContent).not.toMatch(/internship season/i);
    });
  });

  it('offers the description search as an explicit opt-in, off by default', () => {
    // Measured on the recorded Alloy board: searching descriptions for
    // "developer" returns every posting, because it stems to 'develop' and
    // every description says "business development". Without relevance
    // ranking (M3) that default is a search box that does nothing.
    const onChange = vi.fn();
    render(<JobFilters value={{ q: 'developer' }} onChange={onChange} deferred={[]} />);
    const toggle = screen.getByLabelText(/also search descriptions/i);
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(onChange.mock.calls[0]?.[0]).toEqual({ q: 'developer', include_description: true });
  });
});
