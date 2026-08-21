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

  /**
   * The city's own *warm* light — lit windows, and nothing else. ADR 0033.
   *
   * The `neon-*` note above ends "a lit street has to be a colour that means
   * nothing, or the encoding pays for the scenery", and that was right about
   * streets and wrong about the conclusion drawn from it: it left exactly one
   * saturated hue for every lit surface in New York, and a city lit in one hue
   * is a monochrome. ADR 0033 spends a second one, on the argument that hue was
   * never carrying the separation alone — a role floats above the roofline,
   * pulses, is far brighter, wears a name plate and has a beam under it, and a
   * 3 px amber square in a wall shares none of those.
   *
   * The rule it does *not* bend is the headroom: `ember-400` is 22.9 L* below
   * `signal-400`, inside the same 20 the whole palette clears, and the test
   * below checks it with the rest.
   *
   * Warm rather than a second cool, because the gap in the frame was warmth.
   * Reference 02 is built on the opposition between an amber-lit tower and a
   * cyan ground plane; two neighbouring blues cannot make that picture at any
   * saturation.
   */
  /**
   * The building mass — ADR 0034, and the family this city is actually made of.
   *
   * Seven near-blacks running navy to indigo. Seven rather than one because a
   * skyline of twenty-five thousand boxes in a single shade reads as one
   * extruded material, which is the exact note that started this milestone; a
   * per-building seed picks a family and the towers stop looking stamped.
   *
   * Every step is under 16 L*, so nothing here comes near a ceiling. That is
   * the point — ADR 0034 moves the city's colour into its *light* and leaves
   * its *mass* darker than anything that means something.
   */
  mass950: '#07061a',
  mass900: '#0a0924',
  mass800: '#0d0b32',
  mass700: '#111044',
  mass600: '#18104f',
  mass500: '#21105d',
  mass400: '#2a1268',

  /**
   * Window light — ADR 0034. Four hues, one step each.
   *
   * One step because a window is a light rather than a lit thing: nothing dims
   * it but distance, and distance is handled in the shader. Four hues because
   * `neon-*`'s note — "a lit street has to be a colour that means nothing" —
   * was written for a monochrome city and does not survive one that is not.
   * What replaces it is narrower and stronger, and it is the whole of this
   * ADR's colour rule: **cyan is a role.** `aqua-400` is the closest the
   * scenery comes and it sits 27.4 L* below `signal-400` and 5.4 below
   * `alert-400`, so the city can be as polychrome as it likes without ever
   * competing with the one hue that carries a job.
   */
  aqua400: '#0096cc',
  azure400: '#168bff',
  iris400: '#7040ff',
  fuchsia400: '#e82cff',

  ember900: '#4a2711',
  ember700: '#8a4a1a',
  ember500: '#b0611f',
  /**
   * The brightest window in the city: 56.4 L*.
   *
   * Chosen by the *lower* of the two ceilings rather than the palette's own.
   * The 20 L* headroom under `signal-400` would have admitted 62.7, and
   * `cityBuildings.test.ts` holds a second and tighter rule that the first
   * draft cleared by 0.8 L*: ADR 0029's stack is city < hiring building < open
   * role, and `alert-400` — the hiring building — sits at 63.6. A window 0.8
   * below it passes the assertion and defeats what the assertion is for. This
   * clears it by 7.2.
   */
  ember400: '#cd6e2b',
  /**
   * The warm window — ADR 0034.
   *
   * More golden than `ember-400` (hue 33 against 25) and 1.6 L* brighter, and
   * both moves are deliberate: warm is now a tenth of the window light rather
   * than most of it, so the few that are warm have to actually read as warm.
   * 58.0 L*, which is 5.6 under a hiring building — the binding ceiling, and
   * the one ADR 0033's first draft cleared by 0.8 and learned from.
   */
  ember350: '#bf7d2a',
} as const;

export type MapPalette = typeof MAP_PALETTE;
