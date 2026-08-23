'use client';

/**
 * Paste a posting, read what we could, and decide.
 *
 * Two screens in one component because they are two halves of one act, and the
 * seam between them is the feature rather than an implementation detail. The
 * paste proposes; nothing exists yet. The confirm is the only thing in this
 * flow that creates a job.
 *
 * **The queue in front of them is M5d's, and it is not a third half.** Pasting
 * here is now the rare way a proposal is made; the common one is the reader's
 * own Claude calling `capture_posting` in a session this browser knows nothing
 * about. `CaptureQueue` lists what is waiting and this component opens one of
 * them into the same review form a paste lands on — one review surface, two
 * ways to reach it. Anything with a rule in it lives outside the `.tsx`
 * (`lib/capture.ts`), because a rule inside a component is a rule only an
 * end-to-end test can reach.
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

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { CaptureQueue } from '@/components/CaptureQueue';
import {
  capturePosting,
  confirmCapture,
  discardCapture,
  fetchCapture,
  fetchCaptures,
  fetchMe,
} from '@/lib/api';
import { ORIGIN_LABEL, readCapture, type FieldReading } from '@/lib/capture';
import type { Capture, CorpusCheck, EmploymentType } from '@/lib/schemas';

/** Everything that has to be re-read once a capture is created or decided. */
const PENDING_KEY = ['captures', 'pending'] as const;

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

/** Shown under any field neither reader could fill. */
function NotRead() {
  return (
    <span className="mt-1 block text-[12px] leading-relaxed text-paper-dim">
      Not read from the text — type it in.
    </span>
  );
}

const SOURCE_NOTE: Readonly<Record<string, string>> = {
  parser: 'Read by Nightshift from the text.',
  assistant: 'Quoted by Claude from the posting.',
  agreed: 'Read by Nightshift and quoted by Claude — they agree.',
};

/**
 * Who proposed this field, said out loud.
 *
 * A pre-filled input is a claim, and until M5d there was only one thing it
 * could be a claim by. Now there are two, and they can be wrong in different
 * ways — so the form names the reader rather than leaving the person to
 * assume. ADR 0039 §2.
 */
function Provenance({ reading }: { reading: FieldReading }) {
  if (reading.source === 'none') return <NotRead />;

  if (reading.source === 'conflict') {
    return (
      <span className="mt-1 block text-[12px] leading-relaxed text-paper-dim">
        Two readings disagreed, so this is blank on purpose. Nightshift read{' '}
        <strong className="font-medium text-paper">{reading.parser}</strong>; Claude quoted{' '}
        <strong className="font-medium text-paper">{reading.assistant}</strong>. Pick one.
      </span>
    );
  }

  return (
    <span className="mt-1 block text-[12px] leading-relaxed text-paper-dim">
      {SOURCE_NOTE[reading.source]}
    </span>
  );
}

/**
 * What Nightshift already holds that this posting appears to be.
 *
 * Above the form rather than below it, because it can make the whole form
 * unnecessary: the corpus copy came from the employer's own board and carries
 * a location the system trusts and a score this capture never will.
 *
 * **The `checked === false` branch is the one that matters.** An empty list
 * with no explanation reads as "this is new to Nightshift", and nobody
 * established that — it is invariant I3's failure moved to duplicate
 * detection.
 */
function AlreadyHave({ check }: { check: CorpusCheck | null }) {
  if (check === null) return null;

  if (check.matches.length > 0) {
    return (
      <div
        data-testid="capture-already-have"
        className="border border-ink-700 bg-ink-900 px-3 py-2.5"
      >
        <p className="text-[13px] leading-relaxed text-paper">
          Nightshift already has {check.matches.length === 1 ? 'this' : 'these'}, from the
          employer&rsquo;s own board.
        </p>
        <ul className="mt-2 space-y-1">
          {check.matches.map((match) => (
            <li key={match.job_id} className="text-[13px] leading-relaxed">
              <a
                href={`/explore/jobs/${match.job_id}`}
                className="text-signal-400 underline-offset-2 hover:underline"
              >
                {match.title} — {match.company_name}
              </a>
              {match.status !== 'open' && (
                <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.14em] text-alert-400">
                  {match.status.replace(/_/g, ' ')}
                </span>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[12px] leading-relaxed text-paper-dim">
          You can still save this one. It will carry less than the copy above — a capture has no
          board to re-read, so nothing can tell you later that it closed.
        </p>
      </div>
    );
  }

  if (!check.checked) {
    return (
      <p
        data-testid="capture-not-checked"
        className="max-w-2xl text-[12px] leading-relaxed text-paper-dim"
      >
        {check.why_not}
      </p>
    );
  }

  return null;
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

  const queryClient = useQueryClient();

  /**
   * The queue: pending captures, however they were made.
   *
   * A paste in this tab is the *rare* way a capture is created now — the
   * common one is a reader's Claude calling `capture_posting` somewhere else
   * entirely — so the screen has to be able to show a proposal it did not
   * create.
   */
  const pending = useQuery({
    queryKey: PENDING_KEY,
    queryFn: () => fetchCaptures('pending'),
  });
  const session = useQuery({ queryKey: ['session'], queryFn: fetchMe, retry: false });

  /**
   * Seed the review form from a proposal, exactly once per opening.
   *
   * `readCapture` is the whole contract: a field neither reader could fill
   * becomes an empty box rather than a guess, and a field the two readers
   * disagreed about becomes an empty box rather than a silent winner.
   */
  const openForReview = (result: Capture) => {
    setCapture(result);
    const reading = readCapture(result.proposed, result.assistant);
    setTitle(reading.title.value);
    setCompany(reading.company_name.value);
    setLocation(reading.location_text.value);
    setEmployment(result.proposed.employment_type ?? 'unknown');
  };

  /**
   * Close the review form and put the screen back on the queue.
   *
   * Shared by confirm, discard and *leaving it for later*, because all three
   * end the same way: the row's fate is now the queue's business rather than
   * this form's, and the pending list has to be re-read either way.
   */
  const leaveReview = () => {
    setCapture(null);
    setText('');
    setSourceUrl('');
    void queryClient.invalidateQueries({ queryKey: PENDING_KEY });
  };

  const read = useMutation({
    mutationFn: () =>
      capturePosting({
        raw_text: text,
        source_url: sourceUrl.trim() === '' ? null : sourceUrl.trim(),
      }),
    onSuccess: (result) => {
      openForReview(result);
      void queryClient.invalidateQueries({ queryKey: PENDING_KEY });
    },
  });

  /**
   * Open a queued capture.
   *
   * Fetched rather than taken from the list row, because `GET /capture/{id}`
   * answers with a live corpus check and a list of rows does not — and the
   * duplicate warning is the one thing on this screen that can make the whole
   * form unnecessary.
   */
  const open = useMutation({
    mutationFn: (captureId: string) => fetchCapture(captureId),
    onSuccess: openForReview,
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
      leaveReview();
    },
  });

  const discard = useMutation({
    mutationFn: () => discardCapture(capture!.id),
    onSuccess: leaveReview,
  });

  const error = read.error ?? confirm.error ?? discard.error ?? open.error;
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
            Back to the queue
          </button>
        </div>
      </div>
    );
  }

  if (capture !== null) {
    const reading = readCapture(capture.proposed, capture.assistant);
    return (
      <div className="space-y-4" data-testid="capture-review">
        <div className="flex flex-wrap items-center gap-2">
          <span
            data-testid="capture-origin"
            className="border border-ink-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint"
          >
            {ORIGIN_LABEL[capture.origin]}
          </span>
          {capture.already_existed && (
            <span
              data-testid="capture-already-existed"
              className="text-[12px] leading-relaxed text-paper-dim"
            >
              You had already pasted this — it is the same proposal, not a second one.
            </span>
          )}
        </div>

        <AlreadyHave check={capture.corpus_check} />

        <p className="max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          This is what we could read.{' '}
          <strong className="font-medium text-paper">Nothing is saved yet.</strong> Correct anything
          that is wrong — especially the employer, which decides whose building this stands on.
        </p>

        {capture.assistant_rejected_fields.length > 0 && (
          <p
            data-testid="capture-refused-quotes"
            className="max-w-2xl text-[12px] leading-relaxed text-paper-dim"
          >
            Claude offered {capture.assistant_rejected_fields.join(', ').replace(/_/g, ' ')} and
            Nightshift did not keep {capture.assistant_rejected_fields.length === 1 ? 'it' : 'them'}
            : the words were not in the text you pasted. That is the check working, not a failure.
          </p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <label htmlFor="capture-title" className={LABEL_CLASS}>
            Title
            <input
              id="capture-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className={FIELD_CLASS}
            />
            <Provenance reading={reading.title} />
          </label>

          <label htmlFor="capture-company" className={LABEL_CLASS}>
            Employer
            <input
              id="capture-company"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              className={FIELD_CLASS}
            />
            <Provenance reading={reading.company_name} />
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
            <Provenance reading={reading.location_text} />
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

        {/*
          The evidence, on the same screen as the decision.

          The runbook has always said "check every field against the text", and
          until the queue existed the text was in the reader's own clipboard,
          so its absence here was survivable. It is not survivable for a
          capture made in Claude Desktop: the person confirming never saw the
          posting, and a confirmation with nothing to check against is the
          person's name on the parser's reading — which is exactly what the two
          steps exist to prevent.

          Scrolls in place rather than expanding the page, because a decision
          surface that pushes its own buttons below the fold is one people stop
          reading.
        */}
        <div>
          <h3 className={LABEL_CLASS}>The text it was read from</h3>
          <pre
            data-testid="capture-raw-text"
            className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap border border-ink-800 bg-ink-950 px-3 py-2 font-sans text-[12px] leading-relaxed text-paper-dim"
          >
            {capture.raw_text}
          </pre>
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
          {/*
            A way out that is neither a yes nor a no.

            Until there was a queue, confirm and discard were the only exits
            from this form, which quietly made "I am not sure" cost the same as
            "no". The proposal is already stored the moment it is read, so
            leaving it is free and nothing is lost — and an unsure person
            pressed for a decision is exactly who accepts a wrong employer.
          */}
          <button
            type="button"
            onClick={leaveReview}
            className="text-[13px] text-paper-dim underline-offset-2 hover:text-paper hover:underline"
          >
            Decide later
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
    <div className="space-y-6">
      <CaptureQueue
        captures={pending.data?.captures ?? []}
        isLoading={pending.isLoading}
        error={pending.error}
        email={session.data?.email ?? null}
        onOpen={(captureId) => open.mutate(captureId)}
        opening={open.isPending ? (open.variables ?? null) : null}
      />

      <div className="space-y-4 border-t border-ink-800 pt-6">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
          Or paste one yourself
        </h2>
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
    </div>
  );
}
