'use client';

/**
 * The screen this whole slice exists for.
 *
 * Two panes: what the file appears to say, and the file itself with those
 * claims marked in it. Every proposal starts undecided, the page says in as many
 * words that nothing has reached the profile, and the request carries only the
 * rows a person actually answered — **silence is not consent** (I2).
 *
 * Showing the text is not decoration. It is what makes accepting a PDF safe: a
 * scrambled two-column extraction is visible here rather than hidden behind a
 * tidy form, so "we read this and found nothing" is a claim somebody can check.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { HighlightedText, type Span } from './HighlightedText';
import { PROFILE_KEY } from './SkillList';
import { confirmExtractions, deleteResume } from '@/lib/api';
import type { Extraction, ExtractionKind, ResumeDetail } from '@/lib/schemas';

type Decision = 'confirm' | 'reject';

const KIND_LABELS: Record<ExtractionKind, string> = {
  skill: 'Skill',
  graduation: 'Graduation',
  degree: 'Degree',
  school: 'School',
  project: 'Project',
};

/** What the proposal is claiming, in the shape its kind actually stores. */
function describe(row: Extraction): string {
  const value = row.value;
  if (row.kind === 'graduation') {
    const month = value.month;
    const year = value.year;
    return month === null || month === undefined
      ? String(year)
      : `${String(month)}/${String(year)}`;
  }
  const named = value.name ?? value.school ?? value.degree;
  return named === undefined ? JSON.stringify(value) : String(named);
}

const DECISION_CLASS =
  'border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] border-ink-700';

function ProposalRow({
  row,
  decision,
  isActive,
  onDecide,
  onFocus,
}: {
  readonly row: Extraction;
  readonly decision: Decision | undefined;
  readonly isActive: boolean;
  readonly onDecide: (decision: Decision) => void;
  readonly onFocus: () => void;
}) {
  const decided = row.status !== 'pending';
  return (
    <li
      data-testid={`proposal-${row.id}`}
      onClick={onFocus}
      // `onFocus` bubbles in React, so tabbing to this row's buttons moves the
      // highlight too. Without it the pairing between a claim and its words is
      // mouse-only, and the words are the whole point of the screen.
      onFocus={onFocus}
      className={`border px-3 py-2 ${isActive ? 'border-signal-400' : 'border-ink-700'}`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span>
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
            {KIND_LABELS[row.kind]}
          </span>{' '}
          <span className="text-[14px] text-paper">{describe(row)}</span>
        </span>
        {decided ? (
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
            {row.status}
          </span>
        ) : (
          <span className="flex gap-1">
            <button
              type="button"
              aria-pressed={decision === 'confirm'}
              onClick={() => onDecide('confirm')}
              className={`${DECISION_CLASS} ${
                decision === 'confirm' ? 'border-signal-400 text-signal-400' : 'text-paper-dim'
              }`}
            >
              Confirm
            </button>
            <button
              type="button"
              aria-pressed={decision === 'reject'}
              onClick={() => onDecide('reject')}
              className={`${DECISION_CLASS} ${
                decision === 'reject' ? 'border-alert-400 text-alert-400' : 'text-paper-dim'
              }`}
            >
              Reject
            </button>
          </span>
        )}
      </div>
      <p className="mt-1 font-mono text-[11px] leading-relaxed text-paper-dim">
        “{row.quoted_text}”{' '}
        <span className="text-paper-faint">
          characters {row.char_start}–{row.char_end}
        </span>
      </p>
    </li>
  );
}

export function ExtractionReview({ resume }: { readonly resume: ResumeDetail }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [activeId, setActiveId] = useState<string | null>(null);

  const confirm = useMutation({
    mutationFn: (payload: { extraction_id: string; decision: Decision }[]) =>
      confirmExtractions(resume.id, payload),
    onSuccess: async () => {
      setDecisions({});
      await queryClient.invalidateQueries({ queryKey: PROFILE_KEY });
      await queryClient.invalidateQueries({ queryKey: ['resume', resume.id] });
    },
  });

  const drop = useMutation({
    mutationFn: () => deleteResume(resume.id),
    onSuccess: () => router.push('/operate/profile'),
  });

  const pending = resume.extractions.filter((row) => row.status === 'pending');
  // Only the rows somebody answered. An undecided proposal is absent from the
  // request rather than defaulted into either answer.
  const payload = resume.extractions
    .filter((row) => decisions[row.id] !== undefined)
    .map((row) => ({ extraction_id: row.id, decision: decisions[row.id]! }));

  const spans: Span[] = resume.extractions.map((row) => ({
    id: row.id,
    start: row.char_start,
    end: row.char_end,
  }));

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
            What this file appears to say
          </h2>

          {resume.nothing_proven ? (
            <div className="mt-3 space-y-2 border border-ink-700 p-4">
              <p className="text-[14px] text-paper">Nothing could be proven from this file.</p>
              <p className="text-[13px] leading-relaxed text-paper-dim">
                The text is on the right, exactly as it was read. Nothing in it matched a rule this
                project is willing to make a claim from — so nothing was proposed, and nothing was
                guessed.{' '}
                <Link
                  href="/operate/profile"
                  className="text-signal-400 underline underline-offset-2"
                >
                  Add them yourself
                </Link>
                .
              </p>
            </div>
          ) : (
            <>
              <p
                data-testid="review-status"
                className="mt-2 text-[13px] leading-relaxed text-paper-dim"
              >
                {pending.length} of {resume.extractions.length} still undecided.{' '}
                <strong className="font-medium text-paper">
                  Nothing here has been saved to your profile.
                </strong>{' '}
                Confirm what is true, reject what is not, and leave the rest alone.
              </p>
              <ul className="mt-3 space-y-1.5">
                {resume.extractions.map((row) => (
                  <ProposalRow
                    key={row.id}
                    row={row}
                    decision={decisions[row.id]}
                    isActive={activeId === row.id}
                    onFocus={() => setActiveId(row.id)}
                    onDecide={(decision) => {
                      setActiveId(row.id);
                      setDecisions((current) => ({ ...current, [row.id]: decision }));
                    }}
                  />
                ))}
              </ul>

              <div className="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    if (payload.length > 0) confirm.mutate(payload);
                  }}
                  className="border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
                >
                  Save these decisions
                </button>
                <span className="font-mono text-[10px] text-paper-faint">
                  {payload.length} decided
                </span>
              </div>
            </>
          )}

          {confirm.isSuccess ? (
            <p className="mt-3 text-[13px] leading-relaxed text-paper-dim">
              {confirm.data.confirmed} confirmed, {confirm.data.rejected} rejected.{' '}
              <Link
                href="/operate/profile"
                className="text-signal-400 underline underline-offset-2"
              >
                See your profile
              </Link>
              .
            </p>
          ) : null}
          {confirm.error !== null ? (
            <p role="alert" className="mt-3 text-[13px] text-alert-400">
              {confirm.error.message}
            </p>
          ) : null}

          <button
            type="button"
            onClick={() => drop.mutate()}
            className="mt-6 font-mono text-[9px] uppercase tracking-[0.14em] text-paper-dim hover:text-alert-400"
          >
            Delete this resume
          </button>
          <p className="mt-1 text-[12px] leading-relaxed text-paper-faint">
            Anything you already confirmed stays on your profile — it belongs to you, not to the
            file it arrived in.
          </p>
        </section>

        <section>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
            What we actually read
          </h2>
          <div className="mt-3 max-h-[70vh] overflow-y-auto border border-ink-700 p-4">
            <HighlightedText text={resume.parsed_text} spans={spans} activeId={activeId} />
          </div>
        </section>
      </div>
    </div>
  );
}
