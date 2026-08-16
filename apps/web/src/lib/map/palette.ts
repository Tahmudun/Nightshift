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
 * and this style draws no text.
 *
 * What stops the palette climbing is a stated number rather than taste: **every
 * colour here stays at least 20 L\* below `signal-400`**, so a beacon always has
 * somewhere brighter to be. The margin is 20 because that is what admits
 * `alert-400` — the hiring building, the brightest thing the city itself may
 * draw, at 22.0 below — and nothing above it. ADR 0023 set this rule at 40 when
 * the only thing testing it was a grey skyline; ADR 0029 lit the city and moved
 * the number to the one the encoding actually needs. `palette.test.ts` asserts
 * it over every entry below.
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
  /** Administrative boundaries, rail, and anything structural the neon family
   *  would over-light. Was the motorway colour until ADR 0029 lit the streets. */
  ink400: '#4d5f83',
  /**
   * The tallest buildings.
   *
   * Above the old `ink-400` ceiling on purpose: ADR 0023 replaced that cap with
   * a headroom rule, and this sits 41.3 L* below `signal-400`. Reached only by
   * the handful of towers over 900 feet, which is what makes it read as a
   * skyline rather than as a brighter map.
   */
  ink450: '#56698f',

  /** Atmosphere. Never a mark. See `city.md` §3. */
  dusk900: '#180d33',
  dusk700: '#2d1263',
  dusk500: '#5a1d94',
  dusk300: '#a63398',

  /**
   * The city's own light — infrastructure, carrying no meaning. ADR 0029.
   *
   * Electric indigo, because every other saturated hue in this product is
   * spoken for: cyan is a job, magenta is something you can act on, gold is
   * urgency, green is an offer, and violet is the weather. A lit street has to
   * be a colour that means nothing, or the encoding pays for the scenery.
   *
   * Ordered dimmest-first, and the road ramp reads straight down it:
   * `road-path` → `road-minor` → `road-major` → `road-highway`. Never darker,
   * always wider — `darkStyle.test.ts` holds that.
   */
  neon900: '#2f2170',
  neon700: '#4733ad',
  neon500: '#6547d1',
  /** The brightest thing the basemap may draw: 55.2 L*, 30.4 below `signal-400`. */
  neon400: '#8a6bff',
} as const;

export type MapPalette = typeof MAP_PALETTE;
