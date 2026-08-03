'use client';

/**
 * One application: where it is, how it got there, and what you can do next.
 *
 * Invariant I5 is the whole shape of this page.
 *
 * - "Open the posting" opens the employer's page in a new tab. "I applied"
 *   records that *you* did. They are two controls because they are two
 *   different actions, and nothing in this project performs the first one on
 *   your behalf.
 * - When a listing comes down, the page says so and offers three stages. It
 *   does not pick one. The prompt disappears once you have answered it, because
 *   a prompt that survives its answer is a prompt people learn to ignore.
 * - Every event recorded by ingestion is labelled "recorded by Nightshift", so
 *   nobody is left thinking they did something they did not.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { APPLICATIONS_KEY, STAGE_LABELS } from './SaveJobButton';
import {
  addNote,
  changeStage,
  fetchApplication,
  fetchApplications,
  patchApplication,
  scheduleInterview,
  setArchived,
} from '@/lib/api';
import type { ApplicationDetail, ApplicationEvent, ApplicationStage } from '@/lib/schemas';

const ALL_STAGES: readonly ApplicationStage[] = [
  'discovered',
  'saved',
  'preparing',
  'applied',
  'assessment',
  'interview',
  'offer',
  'rejected',
  'withdrawn',
  'closed',
];

/** Stages at or past "applied". Used only to hide a button that would 409. */
const APPLIED_OR_LATER: ReadonlySet<ApplicationStage> = new Set<ApplicationStage>([
  'applied',
  'assessment',
  'interview',
  'offer',
  'rejected',
  'withdrawn',
  'closed',
]);

const EVENT_LABELS: Record<ApplicationEvent['event_type'], string> = {
  saved: 'Saved',
  stage_changed: 'Stage changed',
  note_added: 'Note',
  detail_updated: 'Details updated',
  interview_scheduled: 'Interview scheduled',
  archived: 'Archived',
  restored: 'Restored',
  listing_closed: 'Listing closed',
};

const CHIP = 'inline-block border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em]';
const BUTTON = `${CHIP} border-ink-700 text-paper-dim hover:border-signal-400 hover:text-signal-400 disabled:opacity-50`;

/**
 * True when a listing closed and the user has not responded since.
 *
 * "Since" is measured on `created_at`, the write time, because that is the only
 * column whose order reflects what actually happened first — `occurred_at` on
 * an interview is a future date on purpose.
 */
function needsClosurePrompt(events: readonly ApplicationEvent[]): boolean {
  const closed = events.filter((event) => event.event_type === 'listing_closed').at(-1);
  if (closed === undefined) return false;
  return !events.some(
    (event) => event.event_type === 'stage_changed' && event.created_at > closed.created_at,
  );
}

function HistoryEntry({ event }: { readonly event: ApplicationEvent }) {
  return (
    <li data-testid="history-entry" className="border-l border-ink-700 py-1.5 pl-3">
      <span className="font-mono text-[10px] text-paper-faint">
        {event.occurred_at.slice(0, 10)}
      </span>
      <span className="ml-2 text-[13px] text-paper">{EVENT_LABELS[event.event_type]}</span>
      {event.to_stage !== null ? (
        <span className="ml-2 text-[13px] text-paper-dim">→ {STAGE_LABELS[event.to_stage]}</span>
      ) : null}
      {event.transition_class !== null ? (
        <span className={`${CHIP} ml-2 border-ink-700 text-paper-faint`}>
          {event.transition_class}
        </span>
      ) : null}
      {event.actor === 'system' ? (
        <span className="ml-2 font-mono text-[10px] text-paper-faint">recorded by Nightshift</span>
      ) : null}
      {event.body !== null ? (
        <p className="mt-1 text-[13px] leading-relaxed text-paper-dim">{event.body}</p>
      ) : null}
    </li>
  );
}

export function ApplicationDetailView({ applicationId }: { readonly applicationId: string }) {
  const queryClient = useQueryClient();
  const [stageChoice, setStageChoice] = useState<ApplicationStage | ''>('');
  const [note, setNote] = useState('');
  const [interviewAt, setInterviewAt] = useState('');

  const detailKey = ['application', applicationId] as const;
  const { data, isPending, error } = useQuery({
    queryKey: detailKey,
    queryFn: () => fetchApplication(applicationId),
  });

  // The deferred list already lives on the list endpoint. Reading it from there
  // beats adding a field to the detail response that says the same thing.
  const { data: list } = useQuery({
    queryKey: APPLICATIONS_KEY,
    queryFn: () => fetchApplications(),
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: detailKey });
    void queryClient.invalidateQueries({ queryKey: APPLICATIONS_KEY });
  }

  const stage = useMutation({
    mutationFn: (to: ApplicationStage) => changeStage(applicationId, { to_stage: to }),
    onSuccess: invalidate,
  });
  const recordApplied = useMutation({
    mutationFn: (application: ApplicationDetail) =>
      changeStage(applicationId, {
        to_stage: 'applied',
        applied_at: new Date().toISOString(),
        ...(application.application_url !== null
          ? { application_url: application.application_url }
          : {}),
      }),
    onSuccess: invalidate,
  });
  const note_ = useMutation({
    mutationFn: (body: string) => addNote(applicationId, body),
    onSuccess: () => {
      setNote('');
      invalidate();
    },
  });
  const interview = useMutation({
    mutationFn: (when: string) => scheduleInterview(applicationId, new Date(when).toISOString()),
    onSuccess: () => {
      setInterviewAt('');
      invalidate();
    },
  });
  const nextAction = useMutation({
    mutationFn: (value: string) =>
      patchApplication(applicationId, {
        next_action_at: value === '' ? null : new Date(value).toISOString(),
      }),
    onSuccess: invalidate,
  });
  const archive = useMutation({
    mutationFn: (archived: boolean) => setArchived(applicationId, archived),
    onSuccess: invalidate,
  });

  if (isPending) {
    return <p className="font-mono text-[12px] text-paper-faint">Loading the application…</p>;
  }
  if (error !== null) {
    return (
      <p role="alert" className="text-[13px] text-alert-400">
        {error.message}
      </p>
    );
  }

  const archived = data.archived_at !== null;
  // `application_url` is where the user actually applied. The job summary this
  // endpoint returns carries no source URLs — those live on the job detail
  // response — so when there is no application_url the honest fallback is the
  // job page, not a fabricated board link.
  const postingHref = data.application_url;

  return (
    <div className="space-y-8">
      <header>
        <Link
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint hover:text-paper-dim"
          href="/operate/pipeline"
        >
          ← Back to the pipeline
        </Link>
        <h1 className="mt-3 text-[22px] font-medium tracking-tight text-paper">
          <Link href={`/explore/jobs/${data.job.id}`} className="hover:text-signal-400">
            {data.job.title}
          </Link>
        </h1>
        <Link
          className="mt-1 inline-block text-[14px] text-signal-400 underline underline-offset-2"
          href={`/explore/companies/${data.job.company.id}`}
        >
          {data.job.company.canonical_name}
        </Link>
        <p className="mt-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
            Stage
          </span>{' '}
          <span
            data-testid="current-stage"
            className={`${CHIP} border-signal-400/40 text-signal-400`}
          >
            {STAGE_LABELS[data.current_stage]}
          </span>
          {archived ? (
            <span className={`${CHIP} ml-2 border-gold-400/40 text-gold-400`}>archived</span>
          ) : null}
        </p>
      </header>

      {needsClosurePrompt(data.events) ? (
        <section role="status" className="border border-gold-400/40 px-4 py-3">
          <p className="text-[14px] leading-relaxed text-paper-dim">
            This role is no longer listed at the source. Your application is unchanged — move it
            yourself if that is what happened.
          </p>
          <div className="mt-3 flex gap-2">
            {(['rejected', 'withdrawn', 'closed'] as const).map((target) => (
              <button
                key={target}
                type="button"
                className={BUTTON}
                disabled={archived || stage.isPending}
                onClick={() => stage.mutate(target)}
              >
                {STAGE_LABELS[target]}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Applying
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {postingHref !== null ? (
            <a
              href={postingHref}
              target="_blank"
              rel="noreferrer"
              className={`${CHIP} border-signal-400/40 text-signal-400 hover:border-signal-400`}
            >
              Open the posting
            </a>
          ) : (
            <span className="text-[13px] text-paper-faint">
              No application URL recorded yet — open the role and add one when you apply.
            </span>
          )}
          {!APPLIED_OR_LATER.has(data.current_stage) ? (
            <button
              type="button"
              className={BUTTON}
              disabled={archived || recordApplied.isPending}
              onClick={() => recordApplied.mutate(data)}
            >
              I applied
            </button>
          ) : null}
        </div>
        <p className="text-[12px] leading-relaxed text-paper-faint">
          Nightshift never submits an application. It opens the employer&apos;s page and records
          what you tell it.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Set stage
        </h2>
        <div className="flex items-center gap-2">
          <select
            aria-label="Stage"
            value={stageChoice}
            disabled={archived}
            onChange={(event) => setStageChoice(event.target.value as ApplicationStage)}
            className="border border-ink-700 bg-transparent px-2 py-1 text-[13px] text-paper"
          >
            <option value="">Choose a stage…</option>
            {ALL_STAGES.filter((value) => value !== data.current_stage).map((value) => (
              <option key={value} value={value}>
                {STAGE_LABELS[value]}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={BUTTON}
            disabled={archived || stageChoice === '' || stage.isPending}
            onClick={() => stageChoice !== '' && stage.mutate(stageChoice)}
          >
            Set stage
          </button>
        </div>
        {archived ? (
          <p className="text-[12px] text-paper-faint">
            Restore this application before changing it.
          </p>
        ) : null}
        {stage.error !== null ? (
          <p role="alert" className="text-[12px] text-alert-400">
            {stage.error.message}
          </p>
        ) : null}
      </section>

      <section className="space-y-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Dates
        </h2>
        <label className="block text-[13px] text-paper-dim">
          Next action
          <input
            type="date"
            disabled={archived}
            defaultValue={data.next_action_at?.slice(0, 10) ?? ''}
            onBlur={(event) => nextAction.mutate(event.target.value)}
            className="ml-2 border border-ink-700 bg-transparent px-2 py-1 text-[13px] text-paper"
          />
        </label>
        <label className="block text-[13px] text-paper-dim">
          Interview
          <input
            type="datetime-local"
            value={interviewAt}
            disabled={archived}
            onChange={(event) => setInterviewAt(event.target.value)}
            className="ml-2 border border-ink-700 bg-transparent px-2 py-1 text-[13px] text-paper"
          />
        </label>
        <button
          type="button"
          className={BUTTON}
          disabled={archived || interviewAt === '' || interview.isPending}
          onClick={() => interview.mutate(interviewAt)}
        >
          Add interview
        </button>
      </section>

      <section className="space-y-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Notes
        </h2>
        <textarea
          aria-label="Note"
          value={note}
          disabled={archived}
          onChange={(event) => setNote(event.target.value)}
          rows={3}
          className="w-full border border-ink-700 bg-transparent px-2 py-1 text-[13px] text-paper"
        />
        <button
          type="button"
          className={BUTTON}
          disabled={archived || note.trim() === '' || note_.isPending}
          onClick={() => note_.mutate(note)}
        >
          Add note
        </button>
      </section>

      <section className="space-y-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          History
        </h2>
        {data.events.length === 0 ? (
          <p className="text-[13px] text-paper-faint">No history recorded yet.</p>
        ) : (
          <ul className="space-y-1">
            {data.events.map((event) => (
              <HistoryEntry key={event.id} event={event} />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <button type="button" className={BUTTON} onClick={() => archive.mutate(!archived)}>
          {archived ? 'Restore' : 'Archive'}
        </button>
        <p className="text-[12px] leading-relaxed text-paper-faint">
          There is no delete. An application&apos;s history is append-only, so archiving is the
          reversible way to put a role away.
        </p>
      </section>

      <section data-testid="deferred-tracking" className="space-y-1">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Not tracked yet
        </h2>
        <ul className="space-y-1">
          {(list?.deferred_fields ?? []).map((field) => (
            <li key={field.name} className="text-[12px] leading-relaxed text-paper-faint">
              <span className="text-paper-dim">{field.name}</span> — {field.reason} (
              {field.blocked_on})
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
