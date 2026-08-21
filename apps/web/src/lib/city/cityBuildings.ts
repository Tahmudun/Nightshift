/**
 * New York, drawn by us. ADR 0031.
 *
 * The human's verdict on the `fill-extrusion` city was exact: *"even the 'neon
 * buildings now' are just the same old grey buildings with a neon slab placed on
 * top."* It was accurate, and it was a statement about a **material**, not about
 * a colour choice. A `fill-extrusion` is a flat-shaded solid whose one
 * expressive channel is a colour ramp; a texture on it overrides the colour, an
 * outline on it draws on the ground underneath, and its only light is
 * MapLibre's own fixed white. Every limit in that sentence was measured in this
 * repository before this file existed.
 *
 * So the buildings move into the layer that has none of those ceilings — the
 * Three.js layer that already draws the beacons in MapLibre's own WebGL context
 * (ADR 0025) — and what a tower is made of becomes a shader we author:
 *
 * 1. **Dark glass mass**, near-black and indigo, with a vertical gradient we
 *    author rather than inherit.
 * 2. **Procedural windows**, computed from world position — no sprite, no
 *    atlas, no network, nothing to preload. Density is a quality knob.
 * 3. **Edge light** on the corners, the roofline and the base, which is the
 *    read all four reference images are built from and the one thing
 *    `fill-extrusion` can never do at any setting.
 * 4. **Distance haze** in the same shader and to the same horizon the sky
 *    layer fades the ground into, so the skyline dissolves into the weather
 *    instead of ending at it.
 *
 * ## What it is *not* allowed to do
 *
 * Nothing here says anything. A building is drawn identically whether or not
 * anyone is hiring in it — a hiring building is distinguished by a beam
 * (ADR 0023) and a role by a beacon (ADR 0024), and this layer is the surface
 * those are read against. Every colour below is `ink-*` or `neon-*`: the city's
 * own light, which `city.md` §3 ring-fences as carrying no meaning, and every
 * one of them clears ADR 0029's headroom under `signal-400`.
 * `cityBuildings.test.ts` asserts that over these constants, and asserts
 * nothing at all about how any of it looks.
 *
 * ## Why it is chunked
 *
 * One view of New York at the opening pose is **35,413 footprints and 269,439
 * polygon points** — measured, not estimated. Building that in one pass costs
 * most of a second and drops every frame in it. So the city arrives as spatial
 * cells: a fixed grid in scene metres, each cell one merged geometry and one
 * draw call, built inside a per-frame time budget. Three's own frustum culling
 * then works per cell for free, and cells far behind the camera are evicted
 * rather than kept forever — MapLibre used to do that culling silently for the
 * extrusions, and taking the material also means taking the housekeeping.
 */

import type { Matrix4 } from 'three';
import {
  BufferAttribute,
  BufferGeometry,
  Group,
  Matrix3,
  Mesh,
  ShaderMaterial,
  Vector3,
} from 'three';

import { MAP_PALETTE as C } from '@/lib/map/palette';
import { SKY_COLOURS, SUN, sunDirection } from '@/lib/map/skyLayer';

import {
  buildBuildingArrays,
  readFootprints,
  type Footprint,
  type TileFootprint,
} from './buildingGeometry';

/**
 * How wide a cell of city is, in metres.
 *
 * The trade is draw calls against cull granularity. At 1,200 m the opening
 * pose's 35,000 footprints land in a few dozen cells — a few dozen draw calls,
 * which is nothing — and a cell is small enough that turning the camera drops
 * most of them out of the frustum. At 200 m the culling would be tighter and
 * the city would be a thousand draw calls, which costs more than it saves.
 */
export const CHUNK_METRES = 1200;

/**
 * How many cells of city are kept at once.
 *
 * Cells are evicted farthest-first, and eviction is not an optimisation here —
 * it is the thing that stops a long session accumulating every footprint the
 * camera has ever passed. Six hundred cells is roughly 870 km², which comfortably
 * holds every view this map opens at, so in practice this only fires after a lot
 * of travelling.
 */
const MAX_CELLS = 600;

/** Features read out of the tiles per slice, between yields. */
const FEATURES_PER_SLICE = 1500;

/**
 * The colours a building is made of, and every one of them is `ink-*` or
 * `neon-*`.
 *
 * Named here rather than typed into the shader for the same structural reason
 * `SKY_COLOURS` is: a constant a test can read is a constant a test can hold a
 * margin over, and the margin is the one thing about this file's appearance
 * that must not drift. See `cityBuildings.test.ts`.
 */
export const BUILDING_COLOURS = {
  /** The mass at street level, on the darkest of the four families. */
  massDarkA: C.mass950,
  /** The mass at street level, a shade toward violet. */
  massDarkB: C.mass900,
  /** The roofline on the near-black family. */
  massPrimaryA: C.mass800,
  /** The roofline on the navy family — the commonest tower in New York. */
  massPrimaryB: C.mass700,
  /** The roofline on the indigo family. */
  massIndigo: C.mass600,
  /** The roofline on the rare violet family. The accent, not the rule. */
  massViolet: C.mass500,
  /** A wall the sun is behind, lifted. The one directional cue in the scene. */
  massSunlit: C.mass400,
  /** Roofs. Seen from above at this pitch, and the darkest surface drawn. */
  roof: C.mass900,
  /** Windows, the cold end. 40% of the light with `windowBlue` below it. */
  windowCyan: C.aqua400,
  /** Windows, electric blue. */
  windowBlue: C.azure400,
  /** Windows, violet — 30%. */
  windowViolet: C.iris400,
  /** Windows, magenta — 20%, the accent. */
  windowMagenta: C.fuchsia400,
  /** Windows, warm — 10%, and no more than that. */
  windowWarm: C.ember350,
  /** Corners, rooflines and the base line, on 55% of towers. */
  edgeViolet: C.neon400,
  /** The same lines, electric blue, on 25%. */
  edgeBlue: C.azure400,
  /** The same lines, magenta, on 12%. */
  edgeMagenta: C.fuchsia400,
  /**
   * The same lines, warm, on 8% — against a third of every tower before.
   *
   * This one number is most of why the ADR 0033 city read as a realistic
   * night-time Manhattan render. A window is a third of a pixel from the pose
   * the city opens at; the edge light *is* the building at that distance, so
   * warming a third of the rooflines warmed the whole frame.
   */
  edgeWarm: C.ember400,
} as const;

/**
 * What the window mix averages out to, as linear RGB: 0.40 x (cyan..blue) +
 * 0.30 x violet + 0.20 x magenta + 0.10 x warm, weighted and summed once here.
 *
 * The far field needs a constant. Past the point where a bay is finer than a
 * pixel, a hue read from a per-group hash is a different hue in every
 * neighbouring pixel — a sheet of confetti over the back half of the frame.
 * So the distance that cannot resolve a window gets the average of all of
 * them, which is this cool periwinkle.
 */
const FAR_FIELD_TONE = [0.353, 0.404, 0.788] as const;

/**
 * What the preview multiplies the window density by: a 62% cut.
 *
 * Expressed as a scale on `uWindowDensity` rather than as its own constant so
 * it composes with M4d Task 2's quality tiers instead of racing them — turn
 * the tier down and the windows turn down with it, in whichever order the two
 * are set.
 */
export const GROUP_DENSITY_SCALE = 0.38;

/**
 * How tall a building must be, in metres, before its roofline is lit.
 *
 * Carried over from `darkStyle.ts`'s crown, and carried over *with its
 * measurement*: at the opening pose 25,176 footprints are on screen, of which
 * 3,181 clear 150 ft, 1,107 clear 250 ft and 408 clear 400 ft. At 150 the frame
 * is a carpet of lit roofs; at 400 it is Midtown and the Financial District
 * glowing over a dark city, which is both the reference image and the actual
 * place. 400 ft is 121.9 m.
 */
export const CROWN_MIN_METRES = 121.9;

/** The lit band at the top of a tall tower, in metres. Two storeys of light. */
const CROWN_METRES = 7;

/** A window bay: metres along a wall, and metres per floor. */
const WINDOW_WIDTH_METRES = 3.4;
const WINDOW_HEIGHT_METRES = 3.9;

/** How wide a corner, roofline or base line is drawn, in metres. */
const EDGE_METRES = 0.9;

/** How far up from the street the base glow reaches, in metres. */
const BASE_GLOW_METRES = 6;

/**
 * What share of window bays are lit at the default quality tier.
 *
 * A knob rather than a constant because ADR 0031 makes window density a tier
 * setting: it is the cheapest thing in this shader to turn down and the most
 * expensive thing to leave on for a phone. M4d Task 2 owns the tiers; this is
 * the value the top tier uses.
 */
export const DEFAULT_WINDOW_DENSITY = 0.34;

function glsl(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  return `vec3(${r.toFixed(4)}, ${g.toFixed(4)}, ${b.toFixed(4)})`;
}

const VERTEX_SHADER = `
attribute vec4 span;
attribute float roof;

varying vec3 vWorld;
varying vec4 vSpan;
varying float vRoof;

void main() {
  vWorld = position;
  vSpan = span;
  vRoof = roof;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * A tower, per pixel.
 *
 * Read it as four passes over the same fragment: the mass, the windows, the
 * edges, and then the weather in front of all of it.
 *
 * **Every line width in here is in metres with a screen-space floor.** That is
 * the difference between a skyline of outlined towers and a skyline of
 * flickering dots: a 0.9 m corner is a third of a pixel at the opening pose, so
 * drawn honestly it would vanish at the exact distance the reference image is
 * built on, and drawn without the floor it would strobe as the camera moved.
 * `fwidth` gives the metres-per-pixel of the quantity being measured, so the
 * line is never allowed thinner than the pixel that has to show it.
 */
const FRAGMENT_SHADER = `
precision highp float;

uniform vec3 uCamera;
uniform float uHaze;
uniform vec3 uSun;
uniform float uWindowDensity;

varying vec3 vWorld;
varying vec4 vSpan;
varying float vRoof;

const vec3 MASS_DARK_A = ${glsl(BUILDING_COLOURS.massDarkA)};
const vec3 MASS_DARK_B = ${glsl(BUILDING_COLOURS.massDarkB)};
const vec3 MASS_PRIM_A = ${glsl(BUILDING_COLOURS.massPrimaryA)};
const vec3 MASS_PRIM_B = ${glsl(BUILDING_COLOURS.massPrimaryB)};
const vec3 MASS_INDIGO = ${glsl(BUILDING_COLOURS.massIndigo)};
const vec3 MASS_VIOLET = ${glsl(BUILDING_COLOURS.massViolet)};
const vec3 MASS_SUNLIT = ${glsl(BUILDING_COLOURS.massSunlit)};
const vec3 ROOF        = ${glsl(BUILDING_COLOURS.roof)};

const vec3 WIN_CYAN    = ${glsl(BUILDING_COLOURS.windowCyan)};
const vec3 WIN_BLUE    = ${glsl(BUILDING_COLOURS.windowBlue)};
const vec3 WIN_VIOLET  = ${glsl(BUILDING_COLOURS.windowViolet)};
const vec3 WIN_MAGENTA = ${glsl(BUILDING_COLOURS.windowMagenta)};
const vec3 WIN_WARM    = ${glsl(BUILDING_COLOURS.windowWarm)};
const vec3 FAR_FIELD   = vec3(${FAR_FIELD_TONE.map((v) => v.toFixed(4)).join(', ')});

const vec3 EDGE_VIOLET = ${glsl(BUILDING_COLOURS.edgeViolet)};
const vec3 EDGE_BLUE   = ${glsl(BUILDING_COLOURS.edgeBlue)};
const vec3 EDGE_MAGENTA= ${glsl(BUILDING_COLOURS.edgeMagenta)};
const vec3 EDGE_WARM   = ${glsl(BUILDING_COLOURS.edgeWarm)};

const vec3 HORIZON    = ${glsl(SKY_COLOURS.horizon)};
const vec3 SKY_LOW    = ${glsl(SKY_COLOURS.low)};
const vec3 SUN_COLOUR = ${glsl(SKY_COLOURS.sun)};

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

/**
 * What the sky is in this direction, near the horizon.
 *
 * The same gradient and the same sun glow skyLayer.ts draws, cut down to the
 * two terms a building can actually be seen against. It has to be the same
 * function or the skyline fades into a different colour than the ground beside
 * it does, and that seam is visible from across the room.
 */
vec3 skyTint(vec3 dir) {
  vec3 c = mix(HORIZON, SKY_LOW, smoothstep(0.0, 0.010, max(dir.z, 0.0)));
  float az = atan(dir.x, dir.y) - atan(uSun.x, uSun.y);
  az = abs(atan(sin(az), cos(az)));
  float dEl = dir.z - uSun.z;
  float glow = exp(-(az * az) / 1.70 - (dEl * dEl) / 0.0010);
  return mix(c, SUN_COLOUR, 0.62 * glow);
}

void main() {
  // A wall's length is never zero — anything shorter than 0.2 m was dropped
  // when the geometry was built — so zero is free to mean "this is a roof".
  bool isRoof = vSpan.y <= 0.0;
  float height = max(vRoof, 1.0);
  float up = clamp(vWorld.z / height, 0.0, 1.0);

  // One number per building, shared by every wall of it. The mass family, the
  // edge colour and the crown all read it, so a tower cannot come out navy on
  // one face and indigo on the next.
  float towerSeed = hash(vec2(height, height * 0.618));

  vec3 colour;
  if (isRoof) {
    colour = ROOF;
  } else {
    // Four mass families, all of them dark. The reference images are not a
    // city of purple buildings — they are a city of near-black buildings in
    // four slightly different colds, which is what stops a skyline of 25,000
    // boxes reading as one extruded material.
    float fam = hash(vec2(height, height * 0.618) + 3.0);
    vec3 massBase = fam < 0.30 ? MASS_DARK_A : fam < 0.86 ? MASS_DARK_B : MASS_DARK_A;
    vec3 massTop = fam < 0.30 ? MASS_PRIM_A
                 : fam < 0.62 ? MASS_PRIM_B
                 : fam < 0.86 ? MASS_INDIGO
                              : MASS_VIOLET;
    // Squared, so the lift sits in the top third rather than spreading evenly
    // down a wall. An even ramp is what makes a box read as a box.
    colour = mix(massBase, massTop, up * up);
    // The sun is over the Hudson at 285 deg; a wall turned into it is lifted a
    // little. This is the only non-emissive light in the scene and it is worth
    // roughly one shade — enough that a tower's two visible faces differ,
    // which is most of what makes a mass read as solid.
    colour = mix(colour, MASS_SUNLIT, 0.55 * max(vSpan.w, 0.0));
  }

  if (!isRoof) {
    // Named wall and not length: GLSL has a builtin called length(), which
    // this shader calls further down.
    float wall = vSpan.y;
    float u = vSpan.x;

    // --- How big this building is, in pixels and in metres ---------------
    //
    // Computed once, up here, because both the windows and the edges need it.
    // Without these gates every structure in New York is lit and outlined: the
    // low-rise carpet becomes a bright wire mesh and the far half of the frame
    // saturates into a solid sheet, because past a certain distance every
    // pixel of a building is within a pixel of one of its own edges.
    float below = height - vWorld.z;
    float metresPerPixel = max(fwidth(below), 1e-4);

    // On screen. Under a few pixels there is no detail left to draw, only
    // aliasing to add.
    float onScreen = smoothstep(3.0, 16.0, height / metresPerPixel);

    // In the world. The references light the towers that make the silhouette
    // and leave the low-rise a dark mat with the street grid running through
    // it — which is also what the actual city looks like from this height, and
    // what stops 25,000 lit boxes reading as a wireframe model of New York
    // rather than as New York.
    float tall = smoothstep(18.0, 55.0, height);
    float lifted = smoothstep(8.0, 30.0, height);

    // --- Windows ---------------------------------------------------------
    //
    // The grid is in metres of facade, so a bay is a bay whether the camera is
    // on the street or twenty kilometres up, and it does not swim when the
    // zoom changes.
    float cu = u / ${WINDOW_WIDTH_METRES.toFixed(2)};
    float cv = vWorld.z / ${WINDOW_HEIGHT_METRES.toFixed(2)};
    vec2 f = fract(vec2(cu, cv)) - 0.5;

    // How many bays fit in a pixel. Past one, the grid is finer than the
    // screen can show and every sample lands in a different bay — which is a
    // sheet of white noise crawling over the far skyline, and the single worst
    // artefact this shader could ship. Past that point the speckle is replaced
    // by its own average, so a distant tower is lit by the same amount of
    // light without any of it being resolvable.
    float bays = max(fwidth(cu), fwidth(cv));
    float crisp = 1.0 - smoothstep(0.35, 0.9, bays);

    // Whether a bay is lit is decided for a *group* of bays rather than for
    // each one. Three group shapes, chosen per wall: a vertical strip five
    // floors tall, a horizontal band four bays wide, and a squat block. That
    // is the whole difference between a facade of scattered dots and a facade
    // with strips and bands on it, and it costs one hash and one divide.
    float mode = hash(vec2(vSpan.z, 11.3));
    vec2 grp = mode < 0.34 ? vec2(1.0, 5.0)
             : mode < 0.67 ? vec2(4.0, 1.0)
                           : vec2(2.0, 3.0);
    vec2 gcell = floor(vec2(cu, cv) / grp);

    // A 62% cut against the pre-ADR-0034 city, as a scale on the tier knob
    // rather than as a second knob.
    float density = uWindowDensity * ${GROUP_DENSITY_SCALE.toFixed(2)};
    float litGroup = step(1.0 - density, hash(gcell + vSpan.z * 137.0 + 4.0));

    // Hue, per group: 40% cyan-to-blue, 30% violet, 20% magenta, 10% warm.
    // The per-wall bias is what stops it looking evenly salted — one facade
    // runs colder than the one beside it instead of every wall averaging to
    // the same lilac.
    float t = fract(hash(gcell + vSpan.z * 19.0 + 8.0)
                    + 0.16 * (hash(vec2(vSpan.z, 2.9)) - 0.5));
    vec3 tone = t < 0.40 ? mix(WIN_CYAN, WIN_BLUE, t / 0.40)
              : t < 0.70 ? WIN_VIOLET
              : t < 0.90 ? WIN_MAGENTA
                         : WIN_WARM;

    // Brightness, per group, in four steps — very dim, moderate, bright, hot —
    // because a facade where every lit bay is equally bright reads as a texture
    // rather than as lights. Completely dark is already covered by litGroup,
    // which is 87% of them.
    float b = hash(gcell + vSpan.z * 31.0 + 15.0);
    float bright = b < 0.38 ? 0.22 : b < 0.72 ? 0.55 : b < 0.93 ? 1.00 : 1.35;

    // Wide panes, so bays inside a group nearly touch and the group reads as
    // one strip or band with mullions in it rather than as five dots.
    float pane =
      (1.0 - smoothstep(0.32, 0.42, abs(f.x))) *
      (1.0 - smoothstep(0.24, 0.32, abs(f.y)));

    // The occasional whole-facade panel: six bays by ten floors, lit as one
    // sheet with no mullions and turned well down. A glowing wall, not a
    // searchlight — 3.5% of them, which is a handful per block.
    float panel = step(0.965, hash(floor(vec2(cu / 6.0, cv / 10.0)) + vSpan.z * 57.0));
    pane = mix(pane, 1.0, panel);
    bright = mix(bright, 0.30, panel);
    litGroup = max(litGroup, panel);

    // Dimmed on the low-rise. A two-storey building with a full grid of lit
    // bays reads as an office tower that happens to be short, and 25,000 of
    // them turn the foreground into a field of speckle with no silhouette in
    // it. The references put the light in the towers and leave the mat dark.
    float occupied = mix(0.30, 1.0, lifted);
    colour += tone * litGroup * bright * pane * crisp * occupied;
    // 0.58 is the mean of the four brightness steps, so the distance that
    // cannot resolve a window still carries the light the near field would
    // have put there — the mid-ground of every reference image is exactly that
    // halo, thousands of windows nobody can resolve read as one lit mass.
    colour += FAR_FIELD * density * 0.58 * 1.45 * (1.0 - crisp) * occupied;

    // --- Edges -----------------------------------------------------------
    //
    // The edge light is the silhouette, and at the pose the city opens at it is
    // the only thing about a tower anyone can see — a window is a third of a
    // pixel from twelve kilometres up. So this is where the frame's overall
    // temperature is actually decided, and it is the single biggest reason the
    // ADR 0033 city read warm: a third of every roofline in New York was amber.
    // Here warm is 8% and the other 92% is violet, blue and magenta.
    vec3 edgeTone = towerSeed < 0.55 ? EDGE_VIOLET
                  : towerSeed < 0.80 ? EDGE_BLUE
                  : towerSeed < 0.92 ? EDGE_MAGENTA
                                     : EDGE_WARM;

    float corner = min(u, wall - u);
    float cornerW = max(${EDGE_METRES.toFixed(2)}, 1.1 * fwidth(corner));
    float vertical = 1.0 - smoothstep(0.0, cornerW, corner);

    float roofW = max(${EDGE_METRES.toFixed(2)}, 1.1 * metresPerPixel);
    float roofline = 1.0 - smoothstep(0.0, roofW, below);

    colour += edgeTone * onScreen * (0.70 * tall * vertical + 0.85 * lifted * roofline);

    // Where the mass meets the street. In the references this is what stops a
    // building looking pasted onto the ground plane — the grid runs up to it
    // and the contact glows.
    float baseW = max(${BASE_GLOW_METRES.toFixed(2)}, 1.5 * fwidth(vWorld.z));
    colour += edgeTone * 0.26 * onScreen * lifted * (1.0 - smoothstep(0.0, baseW, vWorld.z));

    // --- Crown -----------------------------------------------------------
    // Only on the towers that make the silhouette. The threshold is a counted
    // number, not a taste; see CROWN_MIN_METRES.
    if (height > ${CROWN_MIN_METRES.toFixed(1)}) {
      float band = 1.0 - smoothstep(0.0, ${CROWN_METRES.toFixed(1)}, below);
      // The same tower seed the edges used, so a tower does not change its mind
      // about its own colour seven metres from the top.
      colour += edgeTone * 0.45 * band;
    }
  }

  // --- Weather -------------------------------------------------------------
  //
  // Quadratic in distance, exactly as skyLayer.ts fogs the ground, and into
  // the same sky colour in the same direction. A linear falloff would start
  // thickening from the first metre and fog the street the camera is standing
  // over; squaring keeps the middle distance crisp and then closes fast.
  vec3 away = vWorld - uCamera;
  float metres = length(away);
  float d = metres / uHaze;
  float fog = 1.0 - exp(-d * d);
  colour = mix(colour, skyTint(normalize(away)), fog);

  // Half a code value of noise. Eight bits over a gradient this shallow bands
  // into stripes you can count, most visibly across a near-black wall.
  colour += (hash(gl_FragCoord.xy) - 0.5) / 255.0;

  gl_FragColor = vec4(colour, 1.0);
}
`;

/**
 * Where the camera is, in scene metres, read out of the matrix it drew with.
 *
 * MapLibre 5 has no `getFreeCameraOptions`, and deriving the position from the
 * pose by hand would be a second derivation of the projection that can disagree
 * with the first — the exact failure `pick.ts` is written against. So it comes
 * out of the matrix itself: for any perspective matrix, the eye is the point
 * that projects to the singular homogeneous coordinate, and rows 0, 1 and 3 of
 * the matrix form the 3×4 camera whose null point it is. `C = −A⁻¹b`.
 *
 * The matrix takes *scene metres* to clip space, so the answer is in scene
 * metres too, with no scale factor to get wrong.
 */
export function cameraPositionFrom(projection: Matrix4, into: Vector3): Vector3 {
  const e = projection.elements;
  const at = (row: number, column: number): number => e[column * 4 + row] as number;
  const a = new Matrix3().set(
    at(0, 0),
    at(0, 1),
    at(0, 2),
    at(1, 0),
    at(1, 1),
    at(1, 2),
    at(3, 0),
    at(3, 1),
    at(3, 2),
  );
  const determinant = a.determinant();
  // Three's `invert()` silently returns the zero matrix on a singular input,
  // which would park the camera at the anchor and fog the whole city uniformly
  // — a wrong picture that looks like a deliberate one. The previous position
  // is a better answer than the origin.
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-30) return into;
  return into.set(at(0, 3), at(1, 3), at(3, 3)).applyMatrix3(a.invert()).negate();
}

/** One cell of city: its meshes, where it is, and which buildings it holds. */
interface Cell {
  readonly key: string;
  /** The cell's centre in scene metres, for distance-ordered eviction. */
  readonly x: number;
  readonly y: number;
  readonly meshes: Mesh[];
  readonly bins: string[];
}

export interface CityBuildingsOptions {
  /** The scene's anchor. The same one the signal layer is built around. */
  readonly anchor: readonly [number, number];
}

export interface CityBuildings {
  /** The object to add to the scene. Hidden until the first drain finishes. */
  readonly group: Group;
  /**
   * Whether the city has been drawn once end to end.
   *
   * The MapLibre extrusion layers are only retired when this goes true, which
   * is ADR 0031's "the city never goes buildingless in between" made
   * mechanical rather than remembered.
   */
  readonly ready: boolean;
  /** Footprints waiting to be read or built. Zero means the city is complete. */
  readonly pending: number;
  /** What is on the GPU: buildings, cells, draw calls, vertices. */
  readonly stats: {
    readonly buildings: number;
    readonly cells: number;
    readonly meshes: number;
    readonly vertices: number;
  };
  /** Hand it whatever the map has loaded. Already-known footprints are ignored. */
  ingest(features: readonly TileFootprint[]): void;
  /** Do up to `budgetMs` of work. Returns true while there is more to do. */
  step(budgetMs: number): boolean;
  /** The camera, for the haze and for which cells are worth keeping. */
  setCamera(position: Vector3, hazeMetres: number): void;
  /** What share of window bays are lit, 0..1. A quality tier's knob. */
  setWindowDensity(density: number): void;
  dispose(): void;
}

export function createCityBuildings(options: CityBuildingsOptions): CityBuildings {
  const group = new Group();
  // Off until the first drain completes: a half-built city drawn over
  // MapLibre's extrusions is two skylines in the same place.
  group.visible = false;
  // Nothing here moves, and the frustum check runs per cell against a bounding
  // sphere the geometry computes. Sorting is not needed — every fragment is
  // opaque and the depth buffer settles it.
  group.matrixAutoUpdate = false;

  const sun = sunDirection(SUN.azimuthDeg, SUN.elevationDeg);
  // Held by name rather than reached for through `material.uniforms`, which is
  // typed as an open record — every write through it would be an index into
  // something that might not be there, and the compiler is right that a
  // misspelt uniform name is silent at runtime.
  const uniforms = {
    uCamera: { value: new Vector3() },
    /**
     * The opening pose's own haze length, so the very first frame is not drawn
     * with a zero scale — which divides the fog by nothing and paints every
     * building flat magenta.
     */
    uHaze: { value: 25_000 },
    uSun: { value: new Vector3(sun[0], sun[1], sun[2]) },
    uWindowDensity: { value: DEFAULT_WINDOW_DENSITY },
  };
  const material = new ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms,
    // Walls are wound counter-clockwise seen from outside and roofs face up,
    // so the inside of every building is back-facing. Culling it is half the
    // fragments in the city for free.
    // (`side` defaults to FrontSide; stated because the winding in
    // `buildingGeometry.ts` exists for this and nothing else says so here.)
    depthTest: true,
    depthWrite: true,
    transparent: false,
  });

  /** Every BIN this has ever admitted, so a footprint is built exactly once. */
  const seen = new Set<string>();
  /** Tile features handed over but not yet projected. */
  let raw: TileFootprint[] = [];
  /** Footprints projected but not yet on the GPU, by cell. */
  const queued = new Map<string, Footprint[]>();
  const cells = new Map<string, Cell>();

  let ready = false;
  let buildings = 0;
  let vertices = 0;
  let meshes = 0;
  const camera = new Vector3();

  function cellKey(x: number, y: number): string {
    return `${Math.floor(x / CHUNK_METRES)}:${Math.floor(y / CHUNK_METRES)}`;
  }

  function readSlice(): void {
    const slice = raw.splice(0, FEATURES_PER_SLICE);
    const footprints = readFootprints(slice, options.anchor, seen);
    for (const footprint of footprints) {
      // The first point of the first ring. A footprint is far smaller than a
      // cell, so which of its own corners decides its cell does not matter —
      // only that the choice is the same every time, or a building would move
      // between cells across rebuilds and be drawn twice.
      const ring = footprint.polygons[0]?.[0];
      if (ring === undefined) continue;
      const key = cellKey(ring[0] ?? 0, ring[1] ?? 0);
      const bucket = queued.get(key);
      if (bucket === undefined) queued.set(key, [footprint]);
      else bucket.push(footprint);
    }
  }

  function buildCell(key: string, footprints: readonly Footprint[]): void {
    const arrays = buildBuildingArrays(footprints, [sun[0], sun[1]]);
    if (arrays.index.length === 0) return;

    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(arrays.position, 3));
    geometry.setAttribute('span', new BufferAttribute(arrays.span, 4));
    geometry.setAttribute('roof', new BufferAttribute(arrays.roof, 1));
    geometry.setIndex(new BufferAttribute(arrays.index, 1));
    // Frustum culling reads this, and computing it here means Three never has
    // to walk a hundred thousand vertices during a render.
    geometry.computeBoundingSphere();

    const mesh = new Mesh(geometry, material);
    mesh.matrixAutoUpdate = false;
    // Every position is already in scene metres; the mesh sits at the origin
    // and the layer's anchor transform does the rest.
    mesh.updateMatrix();
    group.add(mesh);

    const [cx = 0, cy = 0] = key.split(':').map(Number);
    const existing = cells.get(key);
    const cell: Cell = existing ?? {
      key,
      x: (cx + 0.5) * CHUNK_METRES,
      y: (cy + 0.5) * CHUNK_METRES,
      meshes: [],
      bins: [],
    };
    cell.meshes.push(mesh);
    for (const footprint of footprints) cell.bins.push(footprint.bin);
    cells.set(key, cell);

    buildings += footprints.length;
    vertices += arrays.position.length / 3;
    meshes += 1;
  }

  function disposeCell(cell: Cell): void {
    for (const mesh of cell.meshes) {
      group.remove(mesh);
      vertices -= mesh.geometry.getAttribute('position').count;
      // The material is shared across every cell and is disposed once, at the
      // end. Disposing it here would take the whole city's shader with it.
      mesh.geometry.dispose();
      meshes -= 1;
    }
    // Forgotten, not merely unloaded: a BIN left in `seen` is a building that
    // can never come back, so returning to a neighbourhood would draw a hole
    // in it that nothing on screen could explain.
    for (const bin of cell.bins) seen.delete(bin);
    buildings -= cell.bins.length;
    cells.delete(cell.key);
  }

  function evict(): void {
    if (cells.size <= MAX_CELLS) return;
    const ordered = [...cells.values()].sort(
      (a, b) =>
        Math.hypot(b.x - camera.x, b.y - camera.y) - Math.hypot(a.x - camera.x, a.y - camera.y),
    );
    for (const cell of ordered) {
      if (cells.size <= MAX_CELLS) break;
      disposeCell(cell);
    }
  }

  return {
    group,

    get ready() {
      return ready;
    },

    get pending() {
      let count = raw.length;
      for (const bucket of queued.values()) count += bucket.length;
      return count;
    },

    get stats() {
      return { buildings, cells: cells.size, meshes, vertices };
    },

    ingest(features) {
      if (features.length === 0) return;
      // Not filtered against `seen` here. That check needs the BIN, reading the
      // BIN means touching every feature, and touching 35,000 features is
      // exactly the work this defers into `step`.
      raw = raw.length === 0 ? [...features] : raw.concat(features);
    },

    step(budgetMs) {
      const until = performance.now() + budgetMs;
      // Reading comes first and finishes completely before anything is built.
      // Interleaving them would hand each cell its footprints in instalments
      // and give it one mesh per instalment — hundreds of draw calls where
      // there should be dozens, for no benefit at all.
      while (raw.length > 0 && performance.now() < until) readSlice();
      if (raw.length > 0) return true;

      while (queued.size > 0 && performance.now() < until) {
        const [key, footprints] = queued.entries().next().value as [string, Footprint[]];
        queued.delete(key);
        buildCell(key, footprints);
      }

      if (queued.size > 0) return true;

      evict();
      // **`cells.size > 0`, and that condition is the whole guarantee.** The
      // first drain runs before any tile has loaded — `querySourceFeatures`
      // answers 0 on a map that is still fetching — so a drain alone means
      // "nothing to do", not "the city is built". Announcing ready there
      // retires MapLibre's extrusions in exchange for nothing, and the result
      // is a screenshot of New York with no buildings in it at all. That is
      // exactly what happened the first time this ran.
      if (!ready && cells.size > 0) {
        ready = true;
        group.visible = true;
      }
      return false;
    },

    setCamera(position, hazeMetres) {
      camera.copy(position);
      uniforms.uCamera.value.copy(position);
      // A zero or negative scale divides the haze by nothing. It happens when
      // the viewport has no height yet, which is a real state during layout.
      uniforms.uHaze.value = hazeMetres > 1 ? hazeMetres : 1;
    },

    setWindowDensity(density) {
      uniforms.uWindowDensity.value = Math.min(1, Math.max(0, density));
    },

    dispose() {
      for (const cell of [...cells.values()]) disposeCell(cell);
      material.dispose();
      raw = [];
      queued.clear();
      seen.clear();
    },
  };
}
