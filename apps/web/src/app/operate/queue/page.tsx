import { QueuePanel } from '@/components/QueuePanel';

export default function QueuePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Today</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          What is actually waiting on you, from what this system can prove. Nothing here is ranked
          and nothing here acts on its own — every row is a link to the application it is about.
        </p>
      </section>
      <QueuePanel />
    </div>
  );
}
