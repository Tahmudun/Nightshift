'use client';

/**
 * Live health indicators for the API's dependencies (an M0 deliverable).
 *
 * The point of this strip is that it must be able to say "down". A status
 * widget that only ever shows green is decoration; this one polls `/health`,
 * renders the failure detail the API reports, and distinguishes three real
 * states: healthy, degraded (API up, a dependency down), and unreachable
 * (the API itself is not answering).
 */

import { useQuery } from '@tanstack/react-query';

import { ApiError, fetchHealth } from '@/lib/api';
import type { HealthComponent } from '@/lib/schemas';

const POLL_INTERVAL_MS = 10_000;

type DotState = 'ok' | 'down' | 'unknown';

function Dot({ state }: { readonly state: DotState }) {
  const className =
    state === 'ok'
      ? 'bg-signal-400 signal-breath shadow-[0_0_6px_var(--color-signal-500)]'
      : state === 'down'
        ? 'bg-alert-500'
        : 'bg-ink-400';
  return <span aria-hidden="true" className={`size-[6px] rounded-full ${className}`} />;
}

function Reading({
  name,
  component,
}: {
  readonly name: string;
  readonly component: HealthComponent | undefined;
}) {
  const state: DotState = component === undefined ? 'unknown' : component.ok ? 'ok' : 'down';
  // The label is the accessible source of truth; the dot only reinforces it.
  const value = component === undefined ? '—' : component.ok ? 'up' : (component.detail ?? 'down');

  return (
    <span className="inline-flex items-center gap-1.5" title={component?.detail ?? undefined}>
      <Dot state={state} />
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
        {name}
      </span>
      <span
        className={[
          'font-mono text-[10px] tracking-wide',
          state === 'ok'
            ? 'text-signal-400'
            : state === 'down'
              ? 'text-alert-400'
              : 'text-paper-faint',
        ].join(' ')}
      >
        {state === 'down' ? 'down' : value}
      </span>
    </span>
  );
}

export function HealthTelemetry() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: POLL_INTERVAL_MS,
    // Failures here are the signal, not noise — do not retry them away.
    retry: false,
  });

  if (error !== null) {
    const message = error instanceof ApiError ? 'api unreachable' : 'api error';
    return (
      <div
        role="status"
        className="flex items-center gap-2 border border-alert-900 bg-alert-900/40 px-2.5 py-1"
      >
        <span aria-hidden="true" className="size-[6px] rounded-full bg-alert-500" />
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-alert-400">
          {message}
        </span>
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-4 border border-ink-700 bg-ink-900/70 px-2.5 py-1"
    >
      <Reading name="db" component={data?.database} />
      <Reading name="redis" component={data?.redis} />
      {data !== undefined ? (
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
          {data.environment}
        </span>
      ) : isLoading ? (
        <span className="font-mono text-[10px] tracking-wide text-paper-faint">checking…</span>
      ) : null}
    </div>
  );
}
