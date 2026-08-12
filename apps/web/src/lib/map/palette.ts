/**
 * The subset of the design tokens the map style needs, as values.
 *
 * MapLibre's style spec takes literal colours; it cannot read a CSS custom
 * property. So these are duplicated out of `globals.css` — and duplication is
 * the thing that rots, which is why `palette.test.ts` reads the stylesheet and
 * fails if the two ever disagree. One source of truth, checked rather than
 * hoped for.
 *
 * What is *not* here is as deliberate as what is. No `signal-*`, no `alert-*`,
 * no `gold-400`: those carry meaning (`city.md` §3), and the basemap is the
 * surface data is read against, not a place data lives. A basemap that reached
 * for the signal colour would be spending the encoding on scenery.
 *
 * `paper-*` is absent for the same reason in reverse — it is the text family,
 * and this style draws no text. The brightest thing on the map is `ink-400`,
 * which is the dimmest shade cleared for a non-text indicator.
 */

export const MAP_PALETTE = {
  /** The void behind everything. */
  ink950: '#04070c',
  /** Land. One step above the void, so the coastline reads without a stroke. */
  ink900: '#070b14',
  /** Parks and green space. */
  ink800: '#0c1220',
  /** Footpaths, ferry routes, the shoreline. */
  ink700: '#131b2c',
  /** Minor roads, rail. */
  ink600: '#1d2739',
  /** Major roads, administrative boundaries. */
  ink500: '#2b374d',
  /** Motorways — the brightest thing on the basemap, and it stops here. */
  ink400: '#4d5f83',

  /** Atmosphere. Never a mark. See `city.md` §3. */
  dusk900: '#100a1f',
  dusk700: '#1d1038',
  dusk500: '#2f1a52',
  dusk300: '#4a2a72',
} as const;

export type MapPalette = typeof MAP_PALETTE;
