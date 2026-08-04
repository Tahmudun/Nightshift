'use client';

/**
 * The profile page's data layer. Thin on purpose — data in, components out.
 *
 * It also renders `deferred_fields`, which is M2c's I7 surface: what this
 * product will *not* read off a page is stated where somebody would expect it
 * to be read off a page.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { ProfileForm } from './ProfileForm';
import { PROFILE_KEY, SkillList } from './SkillList';
import { fetchProfile, listResumes } from '@/lib/api';

const RESUMES_KEY = ['resumes'] as const;

function Resumes() {
  const { data, isPending, error } = useQuery({ queryKey: RESUMES_KEY, queryFn: listResumes });

  if (isPending) {
    return <p className="font-mono text-[12px] text-paper-faint">Loading your resumes…</p>;
  }
  if (error !== null) {
    return (
      <p role="alert" className="text-[13px] text-alert-400">
        {error.message}
      </p>
    );
  }
  if (data.items.length === 0) {
    return (
      <p className="text-[13px] leading-relaxed text-paper-dim">
        No resume yet. Read one below and you will be shown exactly what it says before anything is
        added to your profile.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {data.items.map((resume) => (
        <li key={resume.id}>
          <Link
            href={`/operate/resumes/${resume.id}`}
            className="block border border-ink-700 px-3 py-2 hover:border-signal-400"
          >
            <span className="text-[14px] text-paper">{resume.name}</span>
            <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
              {resume.source_kind}
            </span>
            {resume.extraction_counts.pending > 0 ? (
              <span className="ml-2 font-mono text-[10px] text-gold-400">
                {resume.extraction_counts.pending} awaiting your decision
              </span>
            ) : (
              <span className="ml-2 font-mono text-[10px] text-paper-faint">
                {resume.extraction_counts.confirmed} confirmed · {resume.extraction_counts.rejected}{' '}
                rejected
              </span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function ProfilePanel() {
  const { data, isPending, error } = useQuery({ queryKey: PROFILE_KEY, queryFn: fetchProfile });

  if (isPending) {
    return <p className="font-mono text-[12px] text-paper-faint">Loading your profile…</p>;
  }
  if (error !== null) {
    return (
      <p role="alert" className="text-[13px] text-alert-400">
        {error.message}
      </p>
    );
  }

  return (
    <div className="space-y-8">
      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">You</h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Everything here is what you told us. Nothing on this page was read off a file without you
          confirming it first.
        </p>
        <div className="mt-4">
          <ProfileForm profile={data} />
        </div>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Skills
        </h2>
        <div className="mt-3">
          <SkillList skills={data.skills} />
        </div>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Projects
        </h2>
        {data.projects.length === 0 ? (
          <p className="mt-2 text-[13px] leading-relaxed text-paper-dim">
            No projects confirmed yet.
          </p>
        ) : (
          <ul className="mt-3 space-y-1.5">
            {data.projects.map((project) => (
              <li key={project.id} className="border border-ink-700 px-3 py-2">
                <span className="text-[14px] text-paper">{project.name}</span>
                {project.evidence !== null ? (
                  <p className="mt-1 whitespace-pre-line text-[12px] leading-relaxed text-paper-dim">
                    {project.evidence}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Resumes
        </h2>
        <div className="mt-3">
          <Resumes />
        </div>
      </section>

      <section data-testid="deferred-profile" className="border border-ink-700 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          What this page will not work out for you
        </h2>
        <ul className="mt-3 space-y-2">
          {data.deferred_fields.map((field) => (
            <li key={field.name} className="text-[13px] leading-relaxed text-paper-dim">
              <span className="text-paper">{field.name}</span> —{' '}
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-gold-400">
                {field.blocked_on}
              </span>{' '}
              {field.reason}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
