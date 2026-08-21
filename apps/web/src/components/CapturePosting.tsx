'use client';

/**
 * Paste a posting, read what we could, and decide.
 *
 * Two screens in one component because they are two halves of one act, and the
 * seam between them is the feature rather than an implementation detail. The
 * paste proposes; nothing exists yet. The confirm is the only thing in this
 * flow that creates a job.
 *
 * **A field the parser declined renders empty and says so.** It does not render
 * a guess, and it does not render a placeholder that reads like one. That is
 * `A10`'s rule about absent data, and here it decides more than a label: a
 * company name is what a job inherits an office from, and an office is what
 * puts a beacon on a specific building in Manhattan. A wrong employer accepted
 * without being read is invariant I1 broken by a UI affordance.
 *
 * So the confirm button is not a "looks good" button. Every value it sends is
 * a value sitting in an input the person could see and change.
 */

import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { capturePosting, confirmCapture, discardCapture } from '@/lib/api';
import type { Capture, EmploymentType } from '@/lib/schemas';

const EMPLOYMENT_TYPES: readonly { readonly value: EmploymentType; readonly label: string }[] = [
  { value: 'full_time', label: 'Full time' },
  { value: 'internship', label: 'Internship' },
  { value: 'part_time', label: 'Part time' },
  { value: 'contract', label: 'Contract' },
  { value: 'temporary', label: 'Temporary' },
  { value: 'unknown', label: 'Not stated' },
];

const FIELD_CLASS =
  'mt-1 w-full border border-ink-700 bg-ink-900 px-2 py-1.5 font-sans text-[14px] text-paper';
const LABEL_CLASS = 'block font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint';

/** Shown under any field the parser declined to fill. */
function NotRead() {
  return (
    <span className="mt-1 block text-[12px] leading-relaxed text-paper-dim">
      Not read from the text — type it in.
    </span>
  );
}

export function CapturePosting() {
  const [text, setText] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [capture, setCapture] = useState<Capture | null>(null);
  const [confirmed, setConfirmed] = useState<Capture | null>(null);

  // The review form's own state, seeded from the proposal exactly once.
  const [title, setTitle] = useState('');
  const [company, setCompany] = useState('');
  const [location, setLocation] = useState('');
  const [employment, setEmployment] = useState<EmploymentType>('unknown');

  const read = useMutation({
    mutationFn: () =>
      capturePosting({
        raw_text: text,
        source_url: sourceUrl.trim() === '' ? null : sourceUrl.trim(),
      }),
    onSuccess: (result) => {
      setCapture(result);
      // `?? ''` is the whole contract in three characters: a declined field
      // becomes an empty box, never a guess.
      setTitle(result.proposed.title ?? '');
      setCompany(result.proposed.company_name ?? '');
      setLocation(result.proposed.location_text ?? '');
      setEmployment(result.proposed.employment_type ?? 'unknown');
    },
  });

  const confirm = useMutation({
    mutationFn: () =>
      confirmCapture(capture!.id, {
        title: title.trim(),
        company_name: company.trim(),
        location_text: location.trim() === '' ? null : location.trim(),
        employment_type: employment,
      }),
    onSuccess: (result) => {
      setConfirmed(result);
      setCapture(null);
      setText('');
      setSourceUrl('');
    },
  });

  const discard = useMutation({
    mutationFn: () => discardCapture(capture!.id),
    onSuccess: () => {
      setCapture(null);
      setText('');
      setSourceUrl('');
    },
  });

  const error = read.error ?? confirm.error ?? discard.error;
  const canConfirm = title.trim() !== '' && company.trim() !== '';

  if (confirmed !== null) {
    return (
      <div className="space-y-3" data-testid="capture-done">
        <p className="text-[14px] leading-relaxed text-paper">
          Saved. It is a real posting now, matched and on the map.
        </p>
        <p className="max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          It has no street address, so it floats with the other unplaced roles rather than standing
          on a building. Nothing you pasted said where the office is, and we will not guess one.
        </p>
        <div className="flex gap-3">
          <a
            href={`/explore/jobs/${confirmed.job_id}`}
            className="border border-ink-700 px-3 py-1.5 text-[13px] text-paper hover:border-ink-500"
          >
            Open the posting
          </a>
          <button
            type="button"
            onClick={() => setConfirmed(null)}
            className="border border-ink-700 px-3 py-1.5 text-[13px] text-paper hover:border-ink-500"
          >
            Paste another
          </button>
        </div>
      </div>
    );
  }

  if (capture !== null) {
    return (
      <div className="space-y-4" data-testid="capture-review">
        <p className="max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          This is what we could read.{' '}
          <strong className="font-medium text-paper">Nothing is saved yet.</strong> Correct anything
          that is wrong — especially the employer, which decides whose building this stands on.
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          <label htmlFor="capture-title" className={LABEL_CLASS}>
            Title
            <input
              id="capture-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className={FIELD_CLASS}
            />
            {capture.proposed.title === null && <NotRead />}
          </label>

          <label htmlFor="capture-company" className={LABEL_CLASS}>
            Employer
            <input
              id="capture-company"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              className={FIELD_CLASS}
            />
            {capture.proposed.company_name === null && <NotRead />}
          </label>

          <label htmlFor="capture-location" className={LABEL_CLASS}>
            Location
            <input
              id="capture-location"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              className={FIELD_CLASS}
              placeholder=""
            />
            {capture.proposed.location_text === null && <NotRead />}
          </label>

          <label htmlFor="capture-employment" className={LABEL_CLASS}>
            Type
            <select
              id="capture-employment"
              value={employment}
              onChange={(event) => setEmployment(event.target.value as EmploymentType)}
              className={FIELD_CLASS}
            >
              {EMPLOYMENT_TYPES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error !== null && (
          <p role="alert" className="text-[13px] text-alert-400">
            {error.message}
          </p>
        )}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => confirm.mutate()}
            disabled={!canConfirm || confirm.isPending}
            className="border border-ink-500 bg-ink-800 px-3 py-1.5 text-[13px] text-paper disabled:opacity-40"
          >
            {confirm.isPending ? 'Saving…' : 'This is right — save it'}
          </button>
          <button
            type="button"
            onClick={() => discard.mutate()}
            disabled={discard.isPending}
            className="border border-ink-700 px-3 py-1.5 text-[13px] text-paper-dim hover:text-paper"
          >
            Throw it away
          </button>
          {!canConfirm && (
            <span className="text-[12px] text-paper-dim">
              A title and an employer are required.
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="max-w-2xl text-[13px] leading-relaxed text-paper-dim">
        Paste a posting from anywhere — LinkedIn, Indeed, a job board, an email, a friend. We read
        what we can and show it to you before anything is saved.
      </p>

      <label htmlFor="capture-url" className={`max-w-xl ${LABEL_CLASS}`}>
        Link to it (optional)
        <input
          id="capture-url"
          value={sourceUrl}
          onChange={(event) => setSourceUrl(event.target.value)}
          className={`${FIELD_CLASS} normal-case tracking-normal`}
        />
      </label>

      <label htmlFor="capture-text" className={LABEL_CLASS}>
        The posting
        <textarea
          id="capture-text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={12}
          className={`${FIELD_CLASS} normal-case tracking-normal`}
        />
      </label>

      {error !== null && (
        <p role="alert" className="text-[13px] text-alert-400">
          {error.message}
        </p>
      )}

      <button
        type="button"
        onClick={() => read.mutate()}
        disabled={text.trim() === '' || read.isPending}
        className="border border-ink-500 bg-ink-800 px-3 py-1.5 text-[13px] text-paper disabled:opacity-40"
      >
        {read.isPending ? 'Reading…' : 'Read it'}
      </button>
    </div>
  );
}
