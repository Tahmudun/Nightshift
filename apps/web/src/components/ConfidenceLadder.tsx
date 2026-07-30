/**
 * The confidence ladder — five ticks, lit up to the precision actually achieved.
 *
 * This is the product's signature element, and it is deliberately the most
 * prominent piece of visual language in the interface. Invariant I1 says never
 * fabricate a location; the ladder makes the *degree* of knowledge visible on
 * every single row, so honesty is the default reading rather than a caveat
 * buried in a detail panel.
 *
 * In M0 nothing has been geocoded, so every ladder in the app sits at three
 * ticks or fewer. That is the intended, truthful result: the interface shows
 * that it does not yet know where these jobs are.
 *
 * §12.4: the colour never carries the meaning alone. The lit tick count is a
 * shape, the label is text, and the whole control has an accessible name.
 */

import { confidenceMeta, CONFIDENCE_SCALE } from '@/lib/confidence';
import type { LocationConfidence } from '@/lib/schemas';

const TOTAL_TICKS = CONFIDENCE_SCALE.length;

interface ConfidenceLadderProps {
  readonly confidence: LocationConfidence;
  readonly showLabel?: boolean;
}

export function ConfidenceLadder({ confidence, showLabel = true }: ConfidenceLadderProps) {
  const meta = confidenceMeta(confidence);

  return (
    <span
      className="inline-flex items-center gap-2"
      title={meta.meaning}
      role="img"
      aria-label={`Location confidence: ${meta.label}, ${meta.rank} of ${TOTAL_TICKS}. ${meta.meaning}`}
    >
      <span className="flex items-end gap-[2px]" aria-hidden="true">
        {CONFIDENCE_SCALE.map((step) => {
          const lit = step.rank <= meta.rank;
          // Ticks grow in height with rank, so the ladder reads as a scale even
          // in greyscale or for a colour-blind reader.
          const height = 5 + step.rank * 2;
          return (
            <span
              key={step.value}
              style={{ height: `${height}px` }}
              className={[
                'w-[3px] rounded-[1px] transition-colors',
                lit ? (meta.mappable ? 'bg-signal-400' : 'bg-signal-600') : 'bg-ink-600',
              ].join(' ')}
            />
          );
        })}
      </span>
      {showLabel ? (
        <span
          className={[
            'font-mono text-[10px] uppercase tracking-[0.14em]',
            meta.mappable ? 'text-signal-400' : 'text-paper-dim',
          ].join(' ')}
        >
          {meta.label}
        </span>
      ) : null}
    </span>
  );
}

/**
 * The legend. §4.3: "These meanings must be documented in the interface."
 *
 * Shipped as a real, always-available panel rather than a tooltip, because a
 * meaning that is only reachable by hover is unavailable to a keyboard or
 * touch user (§12.4).
 */
export function ConfidenceLegend() {
  return (
    <dl className="space-y-3">
      {[...CONFIDENCE_SCALE].reverse().map((step) => (
        <div key={step.value} className="flex gap-3">
          <dt className="w-[136px] shrink-0">
            <ConfidenceLadder confidence={step.value} />
          </dt>
          <dd className="text-[13px] leading-snug text-paper-dim">
            {step.meaning}
            {!step.mappable ? (
              <span className="ml-1 font-mono text-[10px] uppercase tracking-wider text-paper-faint">
                · not placed on the map
              </span>
            ) : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
