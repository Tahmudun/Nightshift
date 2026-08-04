import { ProfilePanel } from '@/components/ProfilePanel';
import { ResumeUpload } from '@/components/ResumeUpload';

export default function ProfilePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Profile</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          What we know about you, and only what you confirmed. A resume is read, quoted back to you,
          and waits — nothing it appears to say reaches this page until you say it is true.
        </p>
      </section>

      <ProfilePanel />

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Read a resume
        </h2>
        <div className="mt-3">
          <ResumeUpload />
        </div>
      </section>
    </div>
  );
}
