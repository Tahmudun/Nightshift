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
 * and this style draws no text. The brightest thing here is `ink-450`, the top
 * of the building height ramp, and what stops it going further is ADR 0023's
 * headroom rule rather than taste: scenery stays at least 40 L\* below
 * `signal-400`, so a beacon always has somewhere brighter to be.
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
  /** Motorways — the brightest thing on the *ground*, and it stops here. */
  ink400: '#4d5f83',
  /**
   * The tallest buildings, and the brightest shade on the map.
   *
   * Above the old `ink-400` ceiling on purpose: ADR 0023 replaced that cap with
   * a headroom rule — scenery stays at least 40 L* below `signal-400` — and this
   * sits at 41.3. Reached only by the handful of towers over 900 feet, which is
   * what makes it read as a skyline rather than as a brighter map.
   */
  ink450: '#56698f',

  /** Atmosphere. Never a mark. See `city.md` §3. */
  dusk900: '#180d33',
  dusk700: '#2d1263',
  dusk500: '#5a1d94',
  dusk300: '#a63398',
} as const;

export type MapPalette = typeof MAP_PALETTE;
