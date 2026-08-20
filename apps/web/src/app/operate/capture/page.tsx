import { CapturePosting } from '@/components/CapturePosting';

export default function CapturePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Add a posting</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Most openings are not on a board we poll. Paste one here and it becomes a real posting —
          searched, scored and drawn on the map like any other. It is read, quoted back to you, and
          waits: nothing it appears to say is stored until you say it is right.
        </p>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <CapturePosting />
      </section>
    </div>
  );
}
