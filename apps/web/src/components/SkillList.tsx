'use client';

/**
 * The confirmed skills, each one saying where it came from.
 *
 * Provenance is rendered, not stored and forgotten. A skill that arrived from a
 * resume links back to the exact characters the person confirmed it from, so
 * the claim can be checked rather than trusted — which is invariant I2 made
 * visible instead of merely enforced in the schema.
 *
 * There is no "suggested skills" section and there never will be one here. A
 * proposal lives on the confirmation screen; this list is facts only.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { addSkill, removeSkill } from '@/lib/api';
import type { UserSkill } from '@/lib/schemas';

export const PROFILE_KEY = ['profile'] as const;

/** `resume:<uuid>#238-244` → the parts, or null for anything else. */
export function parseSourceReference(
  reference: string | null,
): { resumeId: string; start: number; end: number } | null {
  const match = /^resume:([0-9a-fA-F-]{36})#(\d+)-(\d+)$/.exec(reference ?? '');
  if (match === null) return null;
  return { resumeId: match[1]!, start: Number(match[2]), end: Number(match[3]) };
}

function Provenance({ skill }: { readonly skill: UserSkill }) {
  const pointer = parseSourceReference(skill.source_reference);
  if (skill.source_type === 'resume' && pointer !== null) {
    return (
      <span className="font-mono text-[10px] text-paper-faint">
        from your resume ·{' '}
        <Link
          href={`/operate/resumes/${pointer.resumeId}`}
          className="text-signal-400 underline underline-offset-2"
        >
          characters {pointer.start}–{pointer.end}
        </Link>
      </span>
    );
  }
  return (
    <span className="font-mono text-[10px] text-paper-faint">
      {skill.source_type === 'manual' ? 'added by you' : `from ${skill.source_type}`}
    </span>
  );
}

export function SkillList({ skills }: { readonly skills: readonly UserSkill[] }) {
  const [draft, setDraft] = useState('');
  const queryClient = useQueryClient();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: PROFILE_KEY });
  const add = useMutation({
    mutationFn: (name: string) => addSkill(name, undefined),
    onSuccess: () => {
      setDraft('');
      void invalidate();
    },
  });
  const drop = useMutation({ mutationFn: (id: string) => removeSkill(id), onSuccess: invalidate });

  const trimmed = draft.trim();

  return (
    <div className="space-y-3">
      {skills.length === 0 ? (
        <p className="text-[13px] leading-relaxed text-paper-dim">
          No skills confirmed yet. Add one below, or upload a resume and confirm what it says.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {skills.map((skill) => (
            <li
              key={skill.id}
              className="flex items-baseline justify-between gap-3 border border-ink-700 px-3 py-2"
            >
              <span>
                <span className="text-[14px] text-paper">{skill.name}</span>{' '}
                <Provenance skill={skill} />
              </span>
              <button
                type="button"
                onClick={() => drop.mutate(skill.id)}
                className="font-mono text-[9px] uppercase tracking-[0.14em] text-paper-dim hover:text-alert-400"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <label className="flex-1">
          <span className="block font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
            Skill name
          </span>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="mt-1 w-full border border-ink-700 bg-ink-900 px-2 py-1.5 text-[14px] text-paper"
          />
        </label>
        <button
          type="button"
          // Guarded rather than disabled: a disabled button gives no reason, and
          // the empty case is the one a person hits by pressing enter twice.
          onClick={() => {
            if (trimmed !== '') add.mutate(trimmed);
          }}
          className="border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Add skill
        </button>
      </div>
      {add.error !== null ? (
        <p role="alert" className="text-[13px] text-alert-400">
          {add.error.message}
        </p>
      ) : null}
    </div>
  );
}
