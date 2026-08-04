import { ResumeReviewPanel } from '@/components/ResumeReviewPanel';

export default async function ResumeReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">What this resume says</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Every claim below points at the words it came from. Nothing here is on your profile yet,
          and nothing will be until you say so.
        </p>
      </section>
      <ResumeReviewPanel resumeId={id} />
    </div>
  );
}
