'use client';

/**
 * Fetches one resume and hands it to the review. Thin on purpose — the page
 * stays a server component and the decision-making stays in `ExtractionReview`.
 */

import { useQuery } from '@tanstack/react-query';

import { ExtractionReview } from './ExtractionReview';
import { fetchResume } from '@/lib/api';

export function ResumeReviewPanel({ resumeId }: { readonly resumeId: string }) {
  const { data, isPending, error } = useQuery({
    queryKey: ['resume', resumeId],
    queryFn: () => fetchResume(resumeId),
  });

  if (isPending) {
    return <p className="font-mono text-[12px] text-paper-faint">Loading what we read…</p>;
  }
  if (error !== null) {
    return (
      <p role="alert" className="text-[13px] text-alert-400">
        {error.message}
      </p>
    );
  }
  return <ExtractionReview resume={data} />;
}
