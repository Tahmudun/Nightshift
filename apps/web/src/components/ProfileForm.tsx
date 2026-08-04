'use client';

/**
 * The manual path — §6.2's fallback, and where "nothing could be proven from
 * this file" hands over to.
 *
 * Two rules shape it. A field nobody has filled says **not set** rather than
 * showing an empty box, because a blank input and a stored empty string look
 * identical and one of them is a claim (A10). And a save sends only what
 * actually changed, with an explicit `null` for a cleared field — without that
 * distinction, clearing a school is indistinguishable from not touching it, and
 * the value becomes permanently sticky.
 *
 * `graduation_year` and `graduation_month`, never a date: a person who knows
 * they finish in May 2027 does not know the day, and a form that demands one
 * manufactures it (I1, ADR 0013).
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { PROFILE_KEY } from './SkillList';
import { patchProfile } from '@/lib/api';
import type { Profile, RemotePreference, WorkAuthorization } from '@/lib/schemas';

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

const WORK_AUTHORIZATION_LABELS: Record<WorkAuthorization, string> = {
  unspecified: 'Not set',
  us_citizen: 'US citizen',
  permanent_resident: 'Permanent resident',
  f1_student: 'F-1 student',
  other_authorized: 'Otherwise authorized',
  needs_sponsorship: 'Needs sponsorship',
};

const REMOTE_PREFERENCE_LABELS: Record<RemotePreference, string> = {
  no_preference: 'No preference',
  on_site: 'On site',
  hybrid: 'Hybrid',
  remote: 'Remote',
};

/** The badge that makes null visible. */
function NotSet({ when }: { readonly when: boolean }) {
  if (!when) return null;
  return (
    <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
      not set
    </span>
  );
}

function Field({
  id,
  label,
  unset,
  children,
}: {
  readonly id: string;
  readonly label: string;
  readonly unset: boolean;
  readonly children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="block font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint"
      >
        {label}
        <NotSet when={unset} />
      </label>
      {children}
    </div>
  );
}

const INPUT_CLASS =
  'mt-1 w-full border border-ink-700 bg-ink-900 px-2 py-1.5 text-[14px] text-paper';

/** '' is what an emptied text box holds; it must reach the API as null. */
function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : Number(trimmed);
}

export function ProfileForm({ profile }: { readonly profile: Profile }) {
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(profile.display_name ?? '');
  const [year, setYear] = useState(profile.graduation_year?.toString() ?? '');
  const [month, setMonth] = useState(profile.graduation_month?.toString() ?? '');
  const [degree, setDegree] = useState(profile.degree ?? '');
  const [school, setSchool] = useState(profile.school ?? '');
  const [authorization, setAuthorization] = useState<WorkAuthorization>(profile.work_authorization);
  const [home, setHome] = useState(profile.home_location_text ?? '');
  const [remote, setRemote] = useState<RemotePreference>(profile.remote_preference);
  const [salary, setSalary] = useState(profile.minimum_salary?.toString() ?? '');
  const [refusal, setRefusal] = useState<string | null>(null);

  const save = useMutation({
    // Wrapped rather than passed by reference: react-query calls a mutationFn
    // with a second context argument, and forwarding it into the client makes
    // the call site say something it did not mean.
    mutationFn: (changes: Parameters<typeof patchProfile>[0]) => patchProfile(changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PROFILE_KEY }),
  });

  function onSave() {
    const next = {
      display_name: textOrNull(displayName),
      graduation_year: numberOrNull(year),
      graduation_month: numberOrNull(month),
      degree: textOrNull(degree),
      school: textOrNull(school),
      work_authorization: authorization,
      home_location_text: textOrNull(home),
      remote_preference: remote,
      minimum_salary: numberOrNull(salary),
    };

    if (next.graduation_month !== null && next.graduation_year === null) {
      // The same rule as the check constraint and the Zod refinement, said here
      // so the answer is a sentence rather than a 422.
      setRefusal('A graduation month needs a year to hang it on.');
      return;
    }
    setRefusal(null);

    const current: typeof next = {
      display_name: profile.display_name,
      graduation_year: profile.graduation_year,
      graduation_month: profile.graduation_month,
      degree: profile.degree,
      school: profile.school,
      work_authorization: profile.work_authorization,
      home_location_text: profile.home_location_text,
      remote_preference: profile.remote_preference,
      minimum_salary: profile.minimum_salary,
    };

    const changes = Object.fromEntries(
      Object.entries(next).filter(
        ([key]) => next[key as keyof typeof next] !== current[key as keyof typeof current],
      ),
    );
    // A no-op save that writes anyway is how a field somebody never touched
    // appears in their history.
    if (Object.keys(changes).length === 0) return;
    save.mutate(changes);
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Field id="display-name" label="Display name" unset={profile.display_name === null}>
          <input
            id="display-name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            className={INPUT_CLASS}
          />
        </Field>

        <Field id="school" label="School" unset={profile.school === null}>
          <input
            id="school"
            value={school}
            onChange={(event) => setSchool(event.target.value)}
            className={INPUT_CLASS}
          />
        </Field>

        <Field id="degree" label="Degree" unset={profile.degree === null}>
          <input
            id="degree"
            value={degree}
            onChange={(event) => setDegree(event.target.value)}
            className={INPUT_CLASS}
          />
        </Field>

        <Field id="home" label="Home location" unset={profile.home_location_text === null}>
          <input
            id="home"
            value={home}
            onChange={(event) => setHome(event.target.value)}
            className={INPUT_CLASS}
          />
        </Field>

        <Field
          id="graduation-year"
          label="Graduation year"
          unset={profile.graduation_year === null}
        >
          <input
            id="graduation-year"
            type="number"
            value={year}
            onChange={(event) => setYear(event.target.value)}
            className={INPUT_CLASS}
          />
        </Field>

        <Field
          id="graduation-month"
          label="Graduation month"
          unset={profile.graduation_month === null}
        >
          <select
            id="graduation-month"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            className={INPUT_CLASS}
          >
            <option value="">Not set</option>
            {MONTHS.map((name, index) => (
              <option key={name} value={String(index + 1)}>
                {name}
              </option>
            ))}
          </select>
        </Field>

        <Field
          id="work-authorization"
          label="Work authorization"
          unset={profile.work_authorization === 'unspecified'}
        >
          <select
            id="work-authorization"
            value={authorization}
            onChange={(event) => setAuthorization(event.target.value as WorkAuthorization)}
            className={INPUT_CLASS}
          >
            {(Object.keys(WORK_AUTHORIZATION_LABELS) as WorkAuthorization[]).map((value) => (
              <option key={value} value={value}>
                {WORK_AUTHORIZATION_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>

        <Field
          id="remote-preference"
          label="Remote preference"
          unset={profile.remote_preference === 'no_preference'}
        >
          <select
            id="remote-preference"
            value={remote}
            onChange={(event) => setRemote(event.target.value as RemotePreference)}
            className={INPUT_CLASS}
          >
            {(Object.keys(REMOTE_PREFERENCE_LABELS) as RemotePreference[]).map((value) => (
              <option key={value} value={value}>
                {REMOTE_PREFERENCE_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>

        <Field id="minimum-salary" label="Minimum salary" unset={profile.minimum_salary === null}>
          <input
            id="minimum-salary"
            type="number"
            value={salary}
            onChange={(event) => setSalary(event.target.value)}
            className={INPUT_CLASS}
          />
        </Field>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          className="border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Save profile
        </button>
        {save.isSuccess ? (
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
            Saved
          </span>
        ) : null}
      </div>

      {refusal !== null ? (
        <p role="alert" className="text-[13px] text-alert-400">
          {refusal}
        </p>
      ) : null}
      {save.error !== null ? (
        <p role="alert" className="text-[13px] text-alert-400">
          {save.error.message}
        </p>
      ) : null}
    </div>
  );
}
