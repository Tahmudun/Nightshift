import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SearchCaveats } from './SearchCaveats';

describe('SearchCaveats', () => {
  it('says nothing when no filter hid anything', () => {
    const { container } = render(
      <SearchCaveats excludedNoSalary={0} excludedNoRequirements={0} excludedNoSeason={0} />,
    );
    // A caveat shown beside an unfiltered result is noise, and noise is what
    // teaches people to stop reading caveats.
    expect(container).toBeEmptyDOMElement();
  });

  it('names what a salary floor necessarily hid', () => {
    render(<SearchCaveats excludedNoSalary={4} excludedNoRequirements={0} excludedNoSeason={0} />);
    expect(screen.getByText(/4 further roles state no salary/i)).toBeVisible();
  });

  it('separates postings nothing was read from, from postings that want nothing', () => {
    render(<SearchCaveats excludedNoSalary={0} excludedNoRequirements={3} excludedNoSeason={0} />);
    const text = screen.getByText(/no skills read out of them/i);
    expect(text).toBeVisible();
    // The distinction is the whole point of the number. Without it, a thin
    // result reads as "there are only two such jobs".
    expect(text.textContent).toMatch(/could not match/i);
  });

  it('reads as one internship rather than 1 internships', () => {
    render(<SearchCaveats excludedNoSalary={0} excludedNoRequirements={0} excludedNoSeason={1} />);
    expect(screen.getByText(/1 further internship does not say when it runs/i)).toBeVisible();
  });

  it('tells a person which filter to clear rather than only what went wrong', () => {
    // "Most internships state a season or a year and not both" is the measured
    // fact — 8 of 19 state both — and it is what turns a dead end into a next
    // step. §25: a failure states what happened *and what to do*.
    render(<SearchCaveats excludedNoSalary={0} excludedNoRequirements={0} excludedNoSeason={2} />);
    expect(screen.getByText(/clearing one of the two will show more/i)).toBeVisible();
  });
});
