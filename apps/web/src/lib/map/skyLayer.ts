/**
 * The sky, drawn by us — gradient, horizon glow, a sun over the Hudson, stars.
 *
 * M4e Task 3. ADR 0029 closed with a list of things the built-in `sky` block
 * cannot do and a measurement of why, and this is the layer that answer was
 * deferred to. The three constraints it inherits are all measured rather than
 * assumed:
 *
 * **1. The sky is a strip, and a shallow one.** MapLibre's pitch is the angle
 * from straight down, so the view direction sits `90 - pitch` degrees *below*
 * the horizon and the horizon lands near the top of the frame. At the opening
 * pose — pitch 76, vertical fov 36.9° — the horizon is 12% from the top and the
 * highest elevation on screen is **4.4°**. At the camera's own ceiling of 78 it
 * is 6.4°. Everything below is therefore authored inside the first few degrees:
 * a gradient with its stops spread over a hemisphere would put one flat colour
 * on screen, which is exactly the "neon purple rectangle placed at the top"
 * ADR 0029 named. The constants here are in `sin(elevation)`, and the last one
 * that can ever be seen is ~0.11.
 *
 * **2. The hard edge under the sky is drawn ground, not void.** ADR 0029 swept
 * `fog-ground-blend` and `horizon-fog-blend` from 0 to 0.85 and the band did not
 * move. So the fix cannot come from above the horizon — this layer draws *over*
 * the ground as well, with a haze whose density comes from the actual distance
 * along the view ray to the ground plane, solved per pixel. That is why the
 * layer is inserted **below the buildings and above the roads**: it hazes the
 * ground and the street grid receding into the distance, and the towers draw on
 * top of it unhazed until ADR 0031's building shader takes over their share.
 *
 * **3. Nothing here may outshine the data.** ADR 0029's stack is
 * `city < hiring building (63.6 L*) < open role (85.6 L*)`, and a sun is
 * exactly the sort of thing that would quietly break it. Every colour below
 * clears the same 20 L* margin the palette does, and `skyLayer.test.ts` asserts
 * it over this file's own constants — the one kind of test ADR 0031 still wants
 * written, because it pins a semantic and not a taste.
 *
 * **Raw WebGL rather than Three.js**, unlike `city/signalLayer.ts`. This draws
 * one triangle with one shader and needs no scene graph; a second
 * `WebGLRenderer` on MapLibre's context would mean two libraries caching two
 * beliefs about the same GL state, which is a bug the signal layer already pays
 * `resetState()` for once a frame. MapLibre calls `setCustomLayerDefaults()`
 * before this and `context.setDirty()` after, so the state this sets is its own
 * business and is invalidated for it.
 *
 * Nothing animates. There is no `triggerRepaint` in here and no clock: a sky
 * that asked for the next frame would pin a core at 60fps for a static image,
 * and `prefers-reduced-motion` would have to be plumbed in to stop it.
 */

import type {
  CustomLayerInterface,
  CustomRenderMethodInput,
  Map as MapLibreMap,
} from 'maplibre-gl';
import { Matrix4 } from 'three';

import { metreInMercatorUnits } from '@/lib/city/mercator';

import { BUILDING_LAYER_ID } from './darkStyle';

/** The layer's id in the style, and the handle the tests reach for. */
export const SKY_LAYER_ID = 'nightshift-sky';

/**
 * Where this layer goes in the stack: under the buildings, over everything else.
 *
 * The haze below the horizon is drawn *over* ground MapLibre has already
 * painted, so anything that should be hazed has to be on screen before this
 * runs and anything that should not has to come after. The towers are the
 * "after" — they get their own haze from their own shader when ADR 0031 lands,
 * and until then an unhazed skyline over a hazed ground is the honest halfway
 * state rather than a skyline with weather in front of it.
 *
 * `undefined` when the style was built without buildings — `buildDarkStyle`
 * does that when the archive is missing, and `addLayer` throws on a `beforeId`
 * that is not there. So the sky goes on top in that case, over a city with no
 * skyline to be behind.
 */
export function skyBefore(map: { getLayer(id: string): unknown }): string | undefined {
  return map.getLayer(BUILDING_LAYER_ID) === undefined ? undefined : BUILDING_LAYER_ID;
}

/**
 * The sky's colours, and every one of them is `dusk-*` or built from it.
 *
 * `city.md` §3 ring-fences the `dusk` family to atmosphere and forbids it on
 * objects, which is the only reason the sky is allowed to be this saturated at
 * all: it cannot be mistaken for a mark because no mark may ever be this hue.
 * The two that are not literal tokens — the sun and the stars — are named here
 * rather than typed into the shader so the margin test can read them, which is
 * the same structural trick `palette.test.ts` plays on the style.
 */
export const SKY_COLOURS = {
  /** `dusk-900`, 6.5 L*. Overhead, and only reachable by pitching down. */
  zenith: '#180d33',
  /** `dusk-700`, 14.9 L*. The top of the strip at the opening pose. */
  high: '#2d1263',
  /** `dusk-500`, 27.3 L*. */
  low: '#5a1d94',
  /** `dusk-300`, 42.4 L*. The horizon itself, away from the sun. */
  horizon: '#a63398',
  /**
   * The sun and the glow it throws along the horizon. 60.9 L*, which is 24.7
   * below `signal-400` and 2.7 below `alert-400` — so the brightest thing in
   * the sky still sits under the dimmest thing that means something.
   */
  sun: '#e85fc0',
  /**
   * Stars. 60.7 L* at their brightest, and most are drawn far below that.
   *
   * Not white, and that is the constraint doing the work rather than taste:
   * `paper` is 94.9 L* and would put the brightest pixels on the screen in the
   * scenery. This is white pulled toward the sky's own indigo, which is what a
   * star looks like through a city's light anyway.
   */
  star: '#7e93bb',
} as const;

/**
 * Where the sun is, and why it is allowed to be anywhere at all.
 *
 * Due west is 270°; sunset in New York in August runs a little north of it, and
 * from Midtown that line lies over the Hudson. It sits 1° above the horizon —
 * far enough up to throw a glow the length of the skyline, low enough that the
 * city stands in front of it, which is the whole read of reference 02.
 *
 * A fixed sun rather than a clock-driven one on purpose. A sun that tracked the
 * real time of day would be the map making a claim about the world it has not
 * measured, and at 3pm this city would be a daylight scene it has no palette
 * for. This is a *lighting decision*, stated once, the way `light` in
 * `darkStyle.ts` is.
 */
export const SUN = { azimuthDeg: 285, elevationDeg: 0.7 } as const;

/**
 * How far light travels before the haze wins, as a multiple of how far away the
 * camera is.
 *
 * **Not a fixed distance, and the first draft's was the instructive mistake.**
 * 5,200 m is a sensible haze at street level and washes the entire island flat
 * magenta at the opening pose, because at zoom 13.6 the ground under the bottom
 * of the frame is already kilometres away and the horizon is tens of them. The
 * distance that matters is not a property of the weather, it is a property of
 * where the camera is standing — so the scale is tied to the camera's own
 * distance to the point it is looking at, and one number then reads the same
 * from a rooftop and from orbit.
 *
 * 3.4 puts a light veil on the middle distance and takes the far ground all the
 * way into the horizon colour. Tuned by looking, which is what ADR 0031 sets as
 * the method for this class of number.
 *
 * **Exported because the buildings use it too.** `cityBuildings.ts` fogs the
 * skyline with the same scale into the same colour; two numbers here would be
 * a ground and a skyline dissolving at different rates, which is a seam along
 * the horizon that no amount of tuning either one can close.
 */
export const HAZE_CAMERA_DISTANCES = 2.1;

/** Metres per pixel at the equator at zoom 0 — the mercator scale constant. */
const EQUATOR_METRES_PER_PIXEL = 156543.03392;

interface SkyLayerOptions {
  /** The scene's anchor, for the latitude that converts mercator to metres. */
  readonly anchor: readonly [number, number];
}

export interface SkyLayer extends CustomLayerInterface {
  /** Has a frame been drawn? The one thing a test can ask without a GPU. */
  readonly drawn: number;
}

function hexToVec3(hex: string): readonly [number, number, number] {
  const h = hex.replace('#', '');
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

function glslVec3(hex: string): string {
  const [r, g, b] = hexToVec3(hex);
  return `vec3(${r.toFixed(4)}, ${g.toFixed(4)}, ${b.toFixed(4)})`;
}

/**
 * The sun as a unit vector in the scene's frame: x east, y north, z up.
 *
 * Azimuth is degrees clockwise from north, which is the convention the compass
 * and `bearing` already use, so a reader can check this against the map's own
 * north arrow rather than against a comment.
 */
/**
 * How far the camera is from the point it is looking at, in metres.
 *
 * The haze needs a length scale and the only honest one is this: the same view
 * that is 400 m deep from a rooftop is 40 km deep from the opening pose, and a
 * constant density is therefore either invisible at one end or a wash at the
 * other. Written out from the pose rather than read off `transform`, because
 * `cameraToCenterDistance` is one of MapLibre's internals and this file has no
 * business depending on a field that carries no compatibility promise.
 */
export function cameraDistanceMetres(
  zoom: number,
  latitude: number,
  viewportHeightPx: number,
  fovRadians: number,
): number {
  const metresPerPixel =
    (EQUATOR_METRES_PER_PIXEL * Math.cos((latitude * Math.PI) / 180)) / Math.pow(2, zoom);
  return (metresPerPixel * (0.5 * viewportHeightPx)) / Math.tan(fovRadians / 2);
}

export function sunDirection(azimuthDeg: number, elevationDeg: number): [number, number, number] {
  const a = (azimuthDeg * Math.PI) / 180;
  const e = (elevationDeg * Math.PI) / 180;
  return [Math.sin(a) * Math.cos(e), Math.cos(a) * Math.cos(e), Math.sin(e)];
}

const VERTEX_SOURCE = `
attribute vec2 a_pos;
varying vec2 v_ndc;
void main() {
  v_ndc = a_pos;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

/**
 * The sky itself.
 *
 * The whole layer is one triangle covering the viewport, and every pixel asks
 * the same question: which way is this looking? The answer comes from
 * un-projecting the pixel through the inverse of the matrix MapLibre hands
 * over, which means the sun and the stars are fixed to the *world* rather than
 * to the screen — orbit the city and the sun stays over the Hudson. A sky
 * painted in screen space instead is the one that reads as a gradient somebody
 * put on top of a map, which is what this replaces.
 */
const FRAGMENT_SOURCE = `
precision highp float;

uniform mat4 u_inverse;
uniform vec3 u_sun;
uniform float u_metres_per_mercator;
uniform float u_haze_metres;
uniform float u_star_density;

varying vec2 v_ndc;

const vec3 ZENITH  = ${glslVec3(SKY_COLOURS.zenith)};
const vec3 HIGH    = ${glslVec3(SKY_COLOURS.high)};
const vec3 LOW     = ${glslVec3(SKY_COLOURS.low)};
const vec3 HORIZON = ${glslVec3(SKY_COLOURS.horizon)};
const vec3 SUN     = ${glslVec3(SKY_COLOURS.sun)};
const vec3 STAR    = ${glslVec3(SKY_COLOURS.star)};

float hash(vec3 p) {
  return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

vec3 hash3(vec3 p) {
  return vec3(
    hash(p),
    hash(p + vec3(19.19, 3.71, 7.13)),
    hash(p + vec3(41.03, 11.57, 23.31))
  );
}

/**
 * A dusting of stars, fixed to the sky rather than to the screen.
 *
 * One hash lookup per pixel: the direction is scaled onto a lattice, and the
 * cell it lands in either holds a star or does not. The twenty-seven-cell
 * search a "proper" Worley pass would do buys nothing here — a star is far
 * smaller than a cell, so one that straddles a boundary is a fraction of a
 * pixel clipped off something already a pixel wide.
 *
 * **The lattice is sized in pixels, not in taste.** The first draft used 640,
 * which puts a cell at 0.09 deg — about two device pixels at this viewport —
 * and a star at a fraction of one. Three thousand of them were computed per
 * frame and the sky looked empty, because every one of them was smaller than
 * the pixel it was meant to land in. At 110 a cell is roughly 25 device pixels
 * and a star is one to three, which is a star.
 */
float stars(vec3 dir) {
  vec3 p = dir * 110.0;
  vec3 cell = floor(p);
  vec3 r = hash3(cell);
  if (r.z > u_star_density) return 0.0;
  vec3 at = cell + vec3(0.2) + 0.6 * r;
  float d = length(p - at);
  // Varied rather than uniform: a field of identical dots reads as a texture.
  float size = 0.045 + 0.090 * r.x;
  float mag = 0.35 + 0.65 * r.y * r.y;
  return mag * smoothstep(size, 0.0, d);
}

/** The sky in one direction, with the sun's glow already in it. */
vec3 skyAt(vec3 dir) {
  float h = max(dir.z, 0.0);

  // Every stop inside sin(4.4 deg) = 0.077, because that is the last elevation
  // this camera can put on screen; see the head of this file. The first draft
  // of these ran to 0.32 and produced one flat violet across the whole strip —
  // a hemisphere's worth of gradient with 12% of the frame to show it in, which
  // is ADR 0029's "neon purple rectangle" rebuilt in a shader.
  vec3 c = mix(HORIZON, LOW, smoothstep(0.0, 0.010, h));
  c = mix(c, HIGH, smoothstep(0.008, 0.028, h));
  c = mix(c, ZENITH, smoothstep(0.026, 0.082, h));

  // The glow is wide across the sky and thin up it, which is what a low sun
  // does and what an isotropic falloff around the sun vector cannot do — that
  // draws a circular hotspot, and the references are all horizontal bands.
  float az = atan(dir.x, dir.y) - atan(u_sun.x, u_sun.y);
  az = abs(atan(sin(az), cos(az)));
  float dEl = dir.z - u_sun.z;
  float glow = exp(-(az * az) / 1.70 - (dEl * dEl) / 0.0010);
  c = mix(c, SUN, 0.62 * glow);

  // The sun. A core and a halo rather than a disc with an edge — the first
  // draft used one smoothstep and drew a flat pink oval sitting in the sky
  // with a visible rim, which reads as a sprite somebody pasted on rather than
  // as the thing lighting the scene. Nothing in the sky has an edge; the halo
  // runs out into the horizon glow above, so there is no seam between them.
  float ang = acos(clamp(dot(dir, u_sun), -1.0, 1.0));
  float core = exp(-(ang * ang) / 0.00075);
  float halo = exp(-ang / 0.075);
  c = mix(c, SUN, clamp(0.92 * core + 0.40 * halo, 0.0, 1.0));

  // Stars thin out into the glow and into the horizon haze, the way they do —
  // and are not computed at all below the point where they would be invisible.
  // Three sine-based hashes per pixel is the most expensive thing in this
  // shader, and four fifths of a pitched frame is ground.
  float clear = smoothstep(0.006, 0.030, h) * (1.0 - smoothstep(0.10, 0.55, glow));
  if (clear > 0.0) c += STAR * stars(dir) * clear;

  return c;
}

void main() {
  vec4 pNear = u_inverse * vec4(v_ndc, -1.0, 1.0);
  vec4 pFar = u_inverse * vec4(v_ndc, 1.0, 1.0);
  vec3 near = pNear.xyz / pNear.w;
  vec3 far = pFar.xyz / pFar.w;

  // Mercator y grows *southward*; the scene's y is metres north. Without the
  // flip the sun sets in the east and nothing on screen says so.
  vec3 span = far - near;
  vec3 dir = normalize(vec3(span.x, -span.y, span.z));

  // Above the horizon this layer *is* the sky and covers what MapLibre drew.
  // Below it, the ground is already on screen and this is haze over it, with a
  // density from the real distance to the ground plane along this ray — which
  // is what makes the far ground meet the horizon instead of ending at it.
  //
  // **The alpha is computed before the colour, and that ordering is the
  // optimisation.** Most of a pitched frame is ground close enough to the
  // camera that the haze over it is a fraction of one code value; computing a
  // sun, a glow and a starfield for those pixels and then multiplying the
  // result by nothing cost 12 ms a frame on the machine this is developed on.
  float alpha = 1.0;
  if (span.z < 0.0 && near.z > 0.0) {
    float t = near.z / (near.z - far.z);
    float metres = t * length(span) * u_metres_per_mercator;
    // Quadratic rather than linear in distance, and that is the difference
    // between haze and a wash. A plain exp(-d/s) starts thickening from the
    // first metre, so the tuning that clears the far ground also fogs the
    // street the camera is standing over; squaring the argument keeps the
    // middle distance crisp — the grid still reads, which is most of what
    // reference 02 is — and then closes fast into the horizon.
    float d = metres / u_haze_metres;
    alpha = 1.0 - exp(-d * d);
  }

  // Below half a code value there is nothing to draw and nothing to compute.
  if (alpha < 0.002) {
    gl_FragColor = vec4(0.0);
    return;
  }

  vec3 colour = skyAt(dir);

  // A dither of half a code value, which is the difference between a gradient
  // and a stack of visible stripes. Eight bits over a sky this smooth quantises
  // into bands you can count — most visible in the sun's halo, where the ramp
  // is slowest — and the fix is noise below the threshold of being noise.
  colour += (hash(vec3(gl_FragCoord.xy, 1.0)) - 0.5) / 255.0;

  gl_FragColor = vec4(colour, clamp(alpha, 0.0, 1.0));
}
`;

function compile(gl: WebGLRenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (shader === null) throw new Error('sky: could not create shader');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    // Thrown rather than logged. A sky that fails to compile and says so in the
    // console is a map that silently lost its atmosphere, and the whole point
    // of this milestone is that nobody has to notice a missing look by eye.
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`sky: shader did not compile: ${log ?? 'no log'}`);
  }
  return shader;
}

export function createSkyLayer(options: SkyLayerOptions): SkyLayer {
  const metresPerMercator = 1 / metreInMercatorUnits(options.anchor[1]);
  const sun = sunDirection(SUN.azimuthDeg, SUN.elevationDeg);
  const inverse = new Matrix4();

  /**
   * The haze's length scale for this frame. Falls back to the opening pose's
   * own distance if the map has gone — a sky drawn with a stale scale is a
   * wrong picture, and a sky that throws in the render loop is a black one.
   */
  function distanceMetres(args: CustomRenderMethodInput): number {
    if (map === null) return 12_000;
    return cameraDistanceMetres(
      map.getZoom(),
      map.getCenter().lat,
      map.getCanvas().clientHeight,
      args.fov,
    );
  }

  let program: WebGLProgram | null = null;
  let buffer: WebGLBuffer | null = null;
  let attribute = -1;
  let uniforms: {
    inverse: WebGLUniformLocation | null;
    sun: WebGLUniformLocation | null;
    metres: WebGLUniformLocation | null;
    haze: WebGLUniformLocation | null;
    density: WebGLUniformLocation | null;
  } | null = null;
  let map: MapLibreMap | null = null;
  let drawn = 0;

  return {
    id: SKY_LAYER_ID,
    type: 'custom',
    // '2d', not '3d'. '3d' asks MapLibre for the depth mode the extrusions use;
    // this triangle wants no depth test at all and turns it off below, and
    // saying so in one place is better than asking for a mode and overriding it.
    renderingMode: '2d',

    get drawn() {
      return drawn;
    },

    onAdd(addedMap, gl) {
      map = addedMap;

      const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX_SOURCE);
      const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SOURCE);
      const created = gl.createProgram();
      if (created === null) throw new Error('sky: could not create program');
      gl.attachShader(created, vertex);
      gl.attachShader(created, fragment);
      gl.linkProgram(created);
      // Detached and deleted whether or not the link succeeded: the shaders are
      // owned by the program now, and two of these leak per failed style reload.
      gl.detachShader(created, vertex);
      gl.detachShader(created, fragment);
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
      if (!gl.getProgramParameter(created, gl.LINK_STATUS)) {
        const log = gl.getProgramInfoLog(created);
        gl.deleteProgram(created);
        throw new Error(`sky: program did not link: ${log ?? 'no log'}`);
      }
      program = created;

      attribute = gl.getAttribLocation(program, 'a_pos');
      uniforms = {
        inverse: gl.getUniformLocation(program, 'u_inverse'),
        sun: gl.getUniformLocation(program, 'u_sun'),
        metres: gl.getUniformLocation(program, 'u_metres_per_mercator'),
        haze: gl.getUniformLocation(program, 'u_haze_metres'),
        density: gl.getUniformLocation(program, 'u_star_density'),
      };

      // One triangle rather than two, so there is no seam down the diagonal
      // where the interpolators disagree by a bit and the haze shows it.
      buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    },

    render(gl: WebGLRenderingContext | WebGL2RenderingContext, args: CustomRenderMethodInput) {
      if (program === null || buffer === null || uniforms === null) return;

      // The matrix MapLibre hands over takes spherical mercator 0..1 to clip
      // space — the same one the signal layer composes with its anchor
      // transform. Inverted, it takes a pixel back out to a direction. It is
      // `defaultProjectionData.mainMatrix` and not `modelViewProjectionMatrix`
      // for the reason written out at the head of `city/signalLayer.ts`: both
      // typecheck, they are in different spaces, and the wrong one fails
      // silently rather than loudly.
      inverse.fromArray(args.defaultProjectionData.mainMatrix as unknown as number[]).invert();

      gl.useProgram(program);
      gl.uniformMatrix4fv(uniforms.inverse, false, inverse.elements);
      gl.uniform3f(uniforms.sun, sun[0], sun[1], sun[2]);
      gl.uniform1f(uniforms.metres, metresPerMercator);
      gl.uniform1f(uniforms.haze, HAZE_CAMERA_DISTANCES * distanceMetres(args));
      gl.uniform1f(uniforms.density, 0.12);

      // No depth test at all: above the horizon this is the backdrop, and below
      // it, it is haze that has to land on ground MapLibre has already drawn
      // and already written depth for.
      gl.disable(gl.DEPTH_TEST);
      gl.depthMask(false);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(attribute);
      gl.vertexAttribPointer(attribute, 2, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      drawn += 1;
    },

    onRemove(_removedMap, gl) {
      // The program and the buffer are this layer's, and a style reload calls
      // `onRemove` without destroying the context — so skipping either one
      // leaks a program per reload against a context that has a hard limit.
      if (program !== null) gl.deleteProgram(program);
      if (buffer !== null) gl.deleteBuffer(buffer);
      program = null;
      buffer = null;
      uniforms = null;
      map = null;
    },
  };
}
