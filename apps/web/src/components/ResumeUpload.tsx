'use client';

/**
 * Two ways in, side by side, and the limits stated before anybody hits them.
 *
 * `.docx` is named as unsupported on the page rather than discovered through a
 * 415 after picking a file (I7). Paste sits next to the file control for the
 * same reason: it is the way around every format this project cannot read, so
 * it is an equal option and not a fallback buried in an error message.
 *
 * Reading a resume proposes; it does not confirm. This component navigates to
 * the confirmation screen and nothing about the person has changed yet.
 */

import { useMutation } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { pasteResume, uploadResume } from '@/lib/api';
import type { ResumeDetail } from '@/lib/schemas';

export function ResumeUpload() {
  const router = useRouter();
  const [text, setText] = useState('');

  const onRead = (resume: ResumeDetail) => {
    router.push(`/operate/resumes/${resume.id}`);
  };

  const paste = useMutation({
    mutationFn: () => pasteResume(text.trim(), undefined),
    onSuccess: onRead,
  });
  const upload = useMutation({
    mutationFn: (file: File) => uploadResume(file, undefined),
    onSuccess: onRead,
  });

  const error = paste.error ?? upload.error;

  return (
    <div className="space-y-4">
      <p
        data-testid="upload-formats"
        className="max-w-2xl text-[13px] leading-relaxed text-paper-dim"
      >
        A PDF or a <code className="font-mono text-[12px]">.txt</code> file, or paste the text.{' '}
        <strong className="font-medium text-paper">
          <code className="font-mono text-[12px]">.docx</code> is not supported
        </strong>{' '}
        — export it as a PDF, or paste the text instead. Nothing you upload is stored as a file: we
        keep the text we could read and throw the bytes away.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="border border-ink-700 p-4">
          <label
            htmlFor="resume-paste"
            className="block font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint"
          >
            Paste the text of your resume
          </label>
          <textarea
            id="resume-paste"
            rows={8}
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="mt-2 w-full border border-ink-700 bg-ink-900 px-2 py-1.5 font-mono text-[12px] leading-relaxed text-paper"
          />
          <button
            type="button"
            onClick={() => {
              if (text.trim() !== '') paste.mutate();
            }}
            className="mt-2 border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
          >
            Read this text
          </button>
        </div>

        <div className="border border-ink-700 p-4">
          <label
            htmlFor="resume-file"
            className="block font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint"
          >
            Choose a file
          </label>
          <input
            id="resume-file"
            type="file"
            accept=".pdf,.txt"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file !== undefined) upload.mutate(file);
            }}
            className="mt-2 w-full text-[13px] text-paper-dim file:mr-3 file:border file:border-ink-700 file:bg-ink-900 file:px-3 file:py-1.5 file:font-mono file:text-[10px] file:uppercase file:tracking-[0.14em] file:text-signal-400"
          />
          <p className="mt-2 text-[12px] leading-relaxed text-paper-faint">
            You will see exactly what we read out of it before anything is added to your profile.
          </p>
        </div>
      </div>

      {paste.isPending || upload.isPending ? (
        <p className="font-mono text-[12px] text-paper-faint">Reading…</p>
      ) : null}

      {error !== null && error !== undefined ? (
        <p role="alert" className="text-[13px] leading-relaxed text-alert-400">
          {error.message}
        </p>
      ) : null}
    </div>
  );
}
