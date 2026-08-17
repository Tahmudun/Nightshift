'use client';

/**
 * Where §6's inputs come from: your applications, and the ranked list.
 *
 * The city already knows what a role *is* — `/city/signals` says that. What it
 * does not know is anything about **you and that role**, and every lifecycle
 * row of `city.md` §6 is about exactly that: saved, applied, mid-interview, an
 * offer, a rejection. Two queries the rest of the app already makes answer it,
 * and TanStack dedupes them against their existing callers rather than issuing
 * a second request.
 *
 * **Neither query failing takes the city down.** A beacon with no treatment is
 * a plain beacon, which is the honest render of "we do not know what you have
 * done about this role" — and is exactly what the city looked like before this
 * hook existed. `useQuery`'s error is deliberately not surfaced here: I3's
 * habit of mind says an unreachable endpoint is not evidence, and the evidence
 * it is not is "you have never applied to anything".
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';

import { fetchApplications, fetchMatches, MATCH_LIMIT } from '@/lib/api';
import { useCityScene } from '@/lib/city/scene';
import { treatmentFor, type MatchStanding, type SignalTreatment } from '@/lib/city/treatments';
import type { ApplicationStage } from '@/lib/schemas';

/** Shared with `SaveJobButton`'s key so one fetch serves both. */
const TRACKED_KEY = ['applications', { archived: true }] as const;

export function useCityTreatments(): void {
  const signals = useCityScene((state) => state.signals);
  const setTreatments = useCityScene((state) => state.setTreatments);

  // `archived: true` means "do not filter archived out", not "only archived" —
  // and it matters more here than anywhere else in the product, because §6's
  // archived row is *about* those rows. Without it a rejected role would come
  // back untracked and be drawn as though nothing had ever happened to it.
  const applications = useQuery({
    queryKey: TRACKED_KEY,
    queryFn: () => fetchApplications({ archived: true }),
  });

  // The ranked list, for the gold beam. One request for the corpus rather than
  // one per beacon: `MAX_SIGNALS` is 5,000 and a per-role fetch would be the
  // one-object-per-job anti-pattern of `CLAUDE.md` §8 in network form.
  //
  // This asked for 500 until 2026-08-17 and the endpoint's ceiling is 200, so
  // **every city page load 422'd** and every gold beam quietly stopped being
  // drawn — the failure the paragraph at the head of this file describes as
  // acceptable ("a beacon with no treatment is a plain beacon") arriving for a
  // reason that is not acceptable at all: a number this side made up. The
  // endpoint's own constant is now imported instead of guessed.
  const matches = useQuery({
    queryKey: ['city-matches'],
    queryFn: () => fetchMatches(MATCH_LIMIT),
  });

  const stages = useMemo(() => {
    const byJob = new Map<string, ApplicationStage>();
    for (const item of applications.data?.items ?? []) byJob.set(item.job.id, item.current_stage);
    return byJob;
  }, [applications.data]);

  const standings = useMemo(() => {
    const byJob = new Map<string, MatchStanding>();
    for (const band of matches.data?.bands ?? []) {
      for (const row of band.items) {
        // The band's own state, not the row's: `matching.md` §5.2 groups by
        // eligibility and sorts by score inside the group, so the band *is*
        // the verdict.
        byJob.set(row.job.id, { fraction: row.match.fraction, eligibility: band.state });
      }
    }
    return byJob;
  }, [matches.data]);

  const treatments = useMemo(() => {
    const now = Date.now();
    const resolved = new Map<string, SignalTreatment>();
    for (const signal of signals) {
      resolved.set(signal.job_id, treatmentFor(signal, { stages, matches: standings, now }));
    }
    return resolved;
  }, [signals, stages, standings]);

  useEffect(() => {
    setTreatments(treatments);
  }, [treatments, setTreatments]);
}
