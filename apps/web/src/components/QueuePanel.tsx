'use client';

/**
 * The daily queue: what is actually waiting on you.
 *
 * Three rendering decisions carry the design rather than decorate it, and all
 * three come from `docs/architecture/command-center.md` §7.
 *
 * Every section renders, including the empty ones. The pipeline board does the
 * opposite — it hides stages nobody is at — and the difference is deliberate:
 * a stage is a place a role can be, while a section here is a *question*, and
 * "no interviews in the next fortnight" is an answer worth reading.
 *
 * An empty section and an empty queue are different claims and are made
 * separately. So is the third claim on this page: the rows that do not exist
 * yet are named with their reason, because rendering them as empty sections
 * would say "you have none of these", which is false (I7).
 *
 * M3d Task 7 added a fourth claim, for the sections backed by a match score: a
 * row that could not consider a posting says so. A list shortened because the
 * sweep is behind looks exactly like a list of everything there is.
 *
 * Nothing here mutates. There is no dismiss and no snooze — §7.3 — and a test
 * asserts the component renders no button at all.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { fetchQueue } from '@/lib/api';
import type { DailyQueue, EligibilityState, QueueRow, QueueSection } from '@/lib/schemas';

export const QUEUE_KEY = ['queue'] as const;

/**
 * What the band means, in a person's words — the ranked list's five sentences,
 * shortened to fit a row. A queue row shows an eligibility *state* and never
 * the score it was ranked on: I4 forbids a number without its breakdown, and a
 * row has nowhere to put one.
 */
const ELIGIBILITY_LABEL: Record<EligibilityState, string> = {
  eligible: 'you meet what it states',
  likely_eligible: 'you probably meet what it states',
  uncertain: 'not enough stated to tell',
  likely_ineligible: 'probably not a fit — the reason is on the posting',
  ineligible: 'it states something you do not meet',
};

/** Dates arrive UTC and are converted here, at the edge, and nowhere else. */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function Row({ row }: { readonly row: QueueRow }) {
  // A posting nobody is tracking has no application to open. The job page is
  // not a fallback for it — it is where the sentence behind this row's
  // eligibility state is quoted, which is the only place that claim is
  // checkable.
  const href =
    row.application_id === null
      ? `/explore/jobs/${row.job_id}`
      : `/operate/applications/${row.application_id}`;
  return (
    <li>
      <Link href={href} className="block border border-ink-700 px-3 py-2 hover:border-signal-400">
        <span className="text-[14px] text-paper">{row.job_title}</span>
        <span className="ml-2 text-[12px] text-paper-dim">{row.company_name}</span>
        {row.current_stage !== null ? (
          <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
            {row.current_stage}
          </span>
        ) : null}
        {row.eligibility !== null ? (
          <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-gold-400">
            {ELIGIBILITY_LABEL[row.eligibility]}
          </span>
        ) : null}
        <span className="mt-1 block text-[12px] text-paper-dim">
          {row.because}
          {row.at !== null ? (
            <span className="ml-2 font-mono text-[10px] text-paper-faint">
              {formatDate(row.at)}
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

/**
 * What a section could not see.
 *
 * Rendered only where the count is not zero. The API always sends every spot so
 * the shape is stable, and a permanent "0 hidden" line is noise — noise is what
 * stops the non-zero one being read. The counts are deliberately kept out of
 * the section's `total`: these are postings the row could not *consider*, not
 * rows it truncated, and adding them would make the cap message wrong.
 */
function BlindSpots({ section }: { readonly section: QueueSection }) {
  const seen = section.blind_spots.filter((spot) => spot.count > 0);
  if (seen.length === 0) return null;
  return (
    <ul data-testid={`queue-blind-spots-${section.key}`} className="mt-2 space-y-1">
      {seen.map((spot) => (
        <li key={spot.name} className="max-w-2xl text-[12px] leading-relaxed text-gold-400">
          <span className="font-mono text-[11px]">{spot.count}</span> {spot.because}
        </li>
      ))}
    </ul>
  );
}

function Section({ section }: { readonly section: QueueSection }) {
  const hidden = section.total - section.rows.length;
  return (
    // The testid is addressable per section so a test can assert that a role
    // is in *this* list rather than merely somewhere on the page. Asserting
    // page-wide is how a browser test comes to pass for the wrong reason.
    <section data-testid={`queue-section-${section.key}`}>
      <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
        {section.title}
      </h2>
      {section.note !== null ? (
        <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-paper-faint">
          {section.note}
        </p>
      ) : null}
      {section.rows.length === 0 ? (
        <p className="mt-2 text-[13px] text-paper-dim">Nothing here today.</p>
      ) : (
        <>
          <ul className="mt-2 space-y-1.5">
            {section.rows.map((row) => (
              <Row key={`${row.application_id ?? row.job_id}-${row.at ?? ''}`} row={row} />
            ))}
          </ul>
          {hidden > 0 ? (
            // Stated rather than truncated silently. It is not a link: there
            // is no "all follow-ups" page to send anybody to.
            <p className="mt-2 font-mono text-[11px] text-paper-faint">
              and {hidden} more, not shown here
            </p>
          ) : null}
        </>
      )}
      <BlindSpots section={section} />
    </section>
  );
}

function Deferred({ queue }: { readonly queue: DailyQueue }) {
  return (
    <section data-testid="deferred-queue-rows" className="border border-ink-700 bg-ink-900/40 p-5">
      <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
        Not computed yet
      </h2>
      <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
        The product spec asks for these four as well. They are absent rather than empty — an empty
        list here would tell you that you have none of them, and that is a different claim.
      </p>
      <ul className="mt-3 space-y-2">
        {queue.deferred_rows.map((row) => (
          <li key={row.name} className="text-[13px] text-paper-dim">
            <span className="text-paper">{row.name}</span>
            <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-gold-400">
              {row.blocked_on}
            </span>
            <span className="mt-0.5 block text-[12px] text-paper-faint">{row.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function QueuePanel() {
  const { data, isPending, error } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: fetchQueue,
  });

  if (isPending) {
    return <p className="font-mono text-[12px] text-paper-faint">Loading today…</p>;
  }
  if (error !== null) {
    return (
      <p role="alert" className="text-[13px] text-alert-400">
        {error.message}
      </p>
    );
  }

  const { thresholds } = data;

  return (
    <div className="space-y-6">
      {data.total_rows === 0 ? (
        <p data-testid="queue-empty" className="text-[14px] leading-relaxed text-paper-dim">
          Nothing needs you today. That is a normal state rather than a failure — this page only
          shows work that is genuinely waiting, so an empty queue means there is none.
        </p>
      ) : null}

      {data.sections.map((section) => (
        <Section key={section.key} section={section} />
      ))}

      {/*
       * The thresholds come from the API rather than from a constant here. Two
       * copies of one number in two languages is how M2c's enum defect
       * happened, and a number is no safer than a string.
       */}
      <p data-testid="queue-thresholds" className="text-[12px] leading-relaxed text-paper-faint">
        A role is a follow-up once you have applied and {thresholds.follow_up_silent_days} days have
        passed with nothing from you, or once a next action you set has come due. A saved role goes
        quiet after {thresholds.stale_saved_days} days untouched. Interviews appear{' '}
        {thresholds.interview_horizon_days} days ahead. Each list stops at {thresholds.row_cap} and
        says how many it left out.
      </p>

      <Deferred queue={data} />
    </div>
  );
}
