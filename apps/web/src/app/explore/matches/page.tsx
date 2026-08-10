import Link from 'next/link';

import { RankedMatches } from '@/components/RankedMatches';

/**
 * The ranked list (`matching.md` §5.3).
 *
 * Its own page rather than a sort option on Explore, because it is a different
 * list: Explore is the corpus, the same rows for everybody, ordered by recency.
 * This is a list of scores, which exist only for a person, and only for the
 * postings the sweep has reached. Folding them together would make one page
 * whose meaning changes with a toggle — and whose "12 of 31 postings scored"
 * caveat has nowhere honest to live.
 */
export default function MatchesPage() {
  return (
    <div className="space-y-8">
      <section>
        <Link
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint hover:text-paper-dim"
          href="/explore"
        >
          ← Back to all roles
        </Link>
        <h1 className="mt-3 text-[22px] font-medium tracking-tight text-paper">Ranked for you</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Every posting we have scored against your profile, grouped by whether it is open to you
          and ordered by how well it matches inside each group. The grouping is a heading and never
          a number — an eligibility verdict never moves a score. Nothing here is hidden: a posting
          that states something you do not meet is listed with the reason on it.
        </p>
      </section>

      <RankedMatches />
    </div>
  );
}
