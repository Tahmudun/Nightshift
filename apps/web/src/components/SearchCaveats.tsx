/**
 * What the filters necessarily hid, said out loud beside the result.
 *
 * Its own component for one reason: it has to render in **both** branches of
 * the list — the one with rows and the empty one. The empty branch is where it
 * matters most, and where the first version of this left it out. A season
 * filter over the seeded corpus returns nothing, and "No roles match these
 * filters" alone is the product asserting there are no summer internships when
 * the truth is that its one internship never says when it runs.
 *
 * Every number here is zero unless its own filter was asked for. A caveat shown
 * beside an unfiltered result is noise, and noise is what teaches people to
 * stop reading caveats.
 */

const ROW = 'border-b border-ink-700 px-5 py-2 text-[12px] text-paper-dim';

export interface SearchCaveatsProps {
  readonly excludedNoSalary: number;
  readonly excludedNoRequirements: number;
  readonly excludedNoSeason: number;
}

export function SearchCaveats({
  excludedNoSalary,
  excludedNoRequirements,
  excludedNoSeason,
}: SearchCaveatsProps) {
  return (
    <>
      {excludedNoSalary > 0 && (
        // A10: absence of data is data. A salary floor necessarily hides every
        // posting that states no salary, and most postings do.
        <p className={ROW}>
          {excludedNoSalary} further {excludedNoSalary === 1 ? 'role states' : 'roles state'} no
          salary and cannot be compared against a floor.
        </p>
      )}
      {excludedNoRequirements > 0 && (
        // The condition the skill filter shipped under. These are not postings
        // that want nothing — they are postings nothing was read out of.
        <p className={ROW}>
          {excludedNoRequirements} further{' '}
          {excludedNoRequirements === 1 ? 'role has' : 'roles have'} no skills read out of{' '}
          {excludedNoRequirements === 1 ? 'it' : 'them'} at all, so this filter could not match{' '}
          {excludedNoRequirements === 1 ? 'it' : 'them'} either way.
        </p>
      )}
      {excludedNoSeason > 0 && (
        // The most aggressive hider in the product: 11 of the 19 recorded
        // internships state no season anywhere in their title, and 9 state no
        // year. The second sentence is the next step rather than the diagnosis.
        <p className={ROW}>
          {excludedNoSeason} further {excludedNoSeason === 1 ? 'internship does' : 'internships do'}{' '}
          not say when {excludedNoSeason === 1 ? 'it runs' : 'they run'}. Most internships state a
          season or a year and not both, so clearing one of the two will show more.
        </p>
      )}
    </>
  );
}
