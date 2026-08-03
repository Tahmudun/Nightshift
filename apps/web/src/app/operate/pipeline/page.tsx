import { PipelineBoard } from '@/components/PipelineBoard';

export default function PipelinePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Pipeline</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Every role you have saved, and where it got to. Nothing here moves on its own — when a
          listing comes down, this page says so and waits for you.
        </p>
      </section>
      <PipelineBoard />
    </div>
  );
}
