'use client';

/**
 * Everything on the right-hand side of the city, in one column that decides
 * where all of it goes.
 *
 * **This file exists because of a bug it makes impossible.** The camera panel
 * placed itself at `top-24 right-4`; the roster was later given the same
 * corner and covered it completely. Nothing failed: the buttons kept their
 * size and their labels, and Playwright's `toBeVisible` means a non-empty
 * bounding box rather than a reachable element, so a full browser suite went
 * green over controls no pointer could touch. It surfaced only when a test in
 * the offline suite tried to *click* one.
 *
 * Two panels that each place themselves absolutely cannot know about each
 * other, and a third would have had the same accident. So placement is one
 * component's job and the panels are flex children with no opinion about where
 * they sit.
 *
 * The order is deliberate: the controls first, because they are the smallest
 * and the most used; the selected role next, because it is what the person
 * just asked for and it is absent most of the time; then the roster; then the
 * legend, which is what you reach for once the field has raised a question;
 * then the counts, because they are a summary of everything above them; and
 * the frame times last, because they are the only panel that is about the
 * renderer rather than about the job market.
 */

import { Suspense } from 'react';

import { CameraControls } from '@/components/CameraControls';
import { CityDetail } from '@/components/CityDetail';
import { CityLegend } from '@/components/CityLegend';
import { CityPerformance } from '@/components/CityPerformance';
import { CityRoster } from '@/components/CityRoster';
import { CitySignals } from '@/components/CitySignals';
import { useCityScene } from '@/lib/city/scene';

export function CityRail() {
  // The camera exists from the moment the map is constructed, seconds before
  // New York is on screen. Offering its buttons over a blank canvas is what
  // this gate prevents, and it lived in `CityMap`'s own state until the
  // controls moved in here.
  const mapReady = useCityScene((state) => state.mapReady);

  return (
    // `bottom-9` clears MapLibre's attribution control. `pointer-events-none`
    // on the column and back on inside each panel, so the gaps between them
    // are still places you can drag the city by.
    //
    // **One scroll container, here, rather than one inside the roster.** The
    // first version gave the roster its own `overflow-y-auto` and let the rail
    // distribute the height. On a 720px window the fixed panels — five camera
    // buttons, the sort control, the counts and their paragraph — left about
    // ninety pixels for the list, so a corpus of *three* employers scrolled and
    // showed two. Letting the whole column scroll means every panel keeps its
    // natural height and the short-viewport case degrades to a scrollbar
    // instead of to a two-row window onto a three-row list.
    <div className="pointer-events-none absolute top-24 right-4 bottom-9 z-20 flex w-[21rem] max-w-[calc(100vw-2rem)] flex-col items-stretch gap-3 overflow-y-auto">
      {mapReady && <CameraControls />}
      {/* `CityDetail` reads the selection out of the URL with
          `useSearchParams`, which `next build` refuses to prerender without a
          boundary. The fallback is nothing on purpose: the panel is absent
          whenever no role is selected, so a placeholder would be a box that
          appears for one frame on every load and says nothing. */}
      <Suspense fallback={null}>
        <CityDetail />
      </Suspense>
      <CityRoster />
      <CityLegend />
      <CitySignals />
      {/* Last, and below the counts, because it is the only panel that is
          about the *renderer* rather than about the job market. A person
          looking for a role never needs it; a person judging whether this
          thing is fast enough needs it on the screen it describes rather than
          in a document they cannot check. */}
      <CityPerformance />
    </div>
  );
}
