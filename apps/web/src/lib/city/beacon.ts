/**
 * The beacons themselves: one instanced column of light, and the four things §6
 * lets a role change about its own body.
 *
 * Split out of `signalLayer.ts` when the §6 treatments arrived, for the reason
 * `labelMesh.ts` was: a custom layer that owns a context, a beacon buffer, a
 * shader, four mark meshes, an atlas and a reticle is `CLAUDE.md` §8's
 * 400-line component wearing a different hat. This file owns the bodies and
 * knows nothing about MapLibre.
 *
 * **Why a shader, when the beacons used a `MeshBasicMaterial` for two tasks.**
 * §6 gives different roles different colours, different strengths and different
 * pulse rates, and a material carries exactly one of each for the whole mesh.
 * The alternative to per-instance attributes is one mesh per state, which is
 * one draw call per state and a new mesh every time §6 grows a row.
 *
 * **The pulse is not the only thing that says "new".** `prefers-reduced-motion`
 * turns every pulse off, and a treatment that is motion alone disappears
 * entirely for the people who asked for less of it. So a new role is also drawn
 * larger — `NEW_SCALE` — which survives with the animation switched off, and
 * the roster and the legend name it in words besides.
 *
 * **What this shader may not assume — ADR 0035.** ADR 0025 gives this layer
 * *one composed matrix* from MapLibre, scene metres straight to clip space,
 * and leaves the model-view alone. There is no view matrix here. So
 * `normalMatrix` carries no view rotation, `projectionMatrix` elements are not
 * a field of view, and any shader written against a conventional Three.js
 * camera is silently wrong rather than visibly broken — the first draft of this
 * one made every column alpha 0 and hundreds of kilometres tall at the same
 * time, and looked exactly like a working city because §6's marks stand on the
 * same anchors. Anything a shader here needs to know about the camera is
 * pushed in as a uniform, or measured by projecting a known quantity and
 * looking at where it lands.
 *
 * **And what the geometry may not stop carrying.** `pick.ts` raycasts three's
 * own geometry, so a size that exists only in the vertex shader cannot be
 * clicked. The geometry is the *click target* and the shader scales from it to
 * the light — see `PICK_RADIUS` and `PICK_HEIGHT`.
 */

import {
  AdditiveBlending,
  Color,
  CylinderGeometry,
  InstancedBufferAttribute,
  InstancedMesh,
  Object3D,
  ShaderMaterial,
  Vector2,
  Vector3,
} from 'three';

/**
 * `signal-400`, the cyan the whole encoding is built on.
 *
 * Duplicated out of `globals.css` because a WebGL material cannot read a CSS
 * custom property, and checked against the stylesheet by `beacon.test.ts`
 * rather than hoped for.
 */
export const SIGNAL_COLOR = '#5ce8ff';

/**
 * `ink-450`, for a rejected or withdrawn role.
 *
 * §6 is explicit that this is *not* a red fracture: this tool is opened daily
 * during a job search, and accumulating red across the skyline makes it worse
 * to use over exactly the period it is needed most. The ink family is the one
 * that carries no meaning of its own, which is what "dim neutral" needs.
 */
export const ARCHIVED_COLOR = '#56698f';

/**
 * The column's radius in metres, and the two heights it is cut against.
 *
 * Nine metres is narrower than any tower in New York, which is the half of the
 * M4c defect that was a *world* size — a beacon had been a fixed 34 m since
 * M4c and at street zoom it was several times the size of the building
 * underneath it.
 *
 * **`COLUMN_HEIGHT` is the spire and it is deliberately enormous.** The first
 * cut of ADR 0034 made it 90 m — about twenty storeys — on the same reasoning
 * that sized the radius, and that reasoning does not transfer. A mark whose
 * *width* belongs to its building reads as standing on it; a mark whose
 * *height* belongs to its building reads as part of it. At the pose this city
 * opens on, 90 m came to roughly fifty pixels: a cyan tick mark lost in a
 * skyline of lit towers, which is exactly what
 * `docs/design/references/02-skyline-grid-plane-light-columns.jpg` does not
 * show. In the reference the columns leave the buildings, cross the skyline
 * and run out of the top of the frame.
 *
 * So the spire clears every roof in New York — One World Trade's is 417 m and
 * its spire 541 — by a wide enough margin that a role is never in competition
 * with the architecture it stands on. `beacon.test.ts` pins that as the rule,
 * in place of the ceiling it used to pin.
 *
 * **`COLUMN_BASE` is the body.** Everything that decorates a role — the saved
 * collar, the interview arc, the selection reticle — rides the bottom of the
 * column rather than its whole length, because the *job* is at the bottom and
 * the spire is the flag. Marks spread over 1.6 km would be three unrelated
 * objects in the sky.
 */
export const COLUMN_RADIUS = 9;
export const COLUMN_HEIGHT = 1_650;
export const COLUMN_BASE = 90;

/**
 * How narrow the column is ever allowed to get on screen, in CSS pixels.
 *
 * The same idea `cityBuildings.ts` uses for its edge lines, and for the same
 * reason: a size honest in metres is invisible at the range the city is
 * actually read from. Nine metres is a third of a pixel at the opening pose.
 * So the column is drawn at its true size whenever that is legible and grown
 * to this width when it is not — which means one shape that belongs to its
 * building at street level *and* reads from orbit, rather than a fixed size
 * that is wrong at one end or the other.
 *
 * It grows, and never shrinks: `max(1, ...)`. A ceiling here would be a second
 * way to be wrong up close, and up close the metres are already right.
 */
export const MIN_COLUMN_WIDTH_PX = 7;

/**
 * How short the column is ever allowed to get on screen, in CSS pixels.
 *
 * The width floor's counterpart, and it is a **separate** factor rather than
 * the same one applied twice. They used to be one number scaling both axes,
 * which meant the only way to make a distant column taller was to make it
 * fatter, and a mark that gets fatter with distance stops being a light shaft
 * and becomes a lozenge.
 *
 * At the opening pose 1,650 m is already about 275 CSS pixels, so this does
 * nothing there. It exists for the far end of the zoom range — the whole
 * region, five boroughs in frame — where the honest metres would put the field
 * back under the noise floor the height above was raised to clear.
 */
export const MIN_COLUMN_HEIGHT_PX = 150;

/**
 * The column's radius **as a click target**, in metres.
 *
 * Wider than the light, on purpose, and it is also the reason the geometry
 * carries a size at all.
 *
 * **A shader's idea of how big something is cannot be picked.** `pick.ts`
 * raycasts three's own geometry, and ADR 0034 moved the column's size out of
 * the geometry and into the vertex shader — where the pixel floor can see how
 * far away it is, which is the whole point. What was left on the CPU was a
 * *unit* cylinder: a metre across and a metre tall, at a city where a metre is
 * a sixth of a pixel. Every beacon became unclickable the day the column
 * shipped, and the ten seeded browser tests that click one have been failing
 * since without anybody running them.
 *
 * So the geometry is built at this radius and the full height, and the shader
 * scales *down* to the light's own width. One size on the CPU, one shape on
 * the screen, and the height — the part that matters most for reaching a
 * column with a mouse — is the same number in both.
 *
 * Twenty-four metres is roughly what the pixel floor draws at the pose the
 * city opens on, so at the range this field is read from the target is the
 * light. Closer in it is up to three times the light's width, which is the
 * ordinary relationship between a hit target and its ink: half a city block,
 * around a mark a person is trying to hit on a canvas with no cursor keys.
 */
export const PICK_RADIUS = 24;

/**
 * How tall a click target is, in metres — a role's own slot in its stack.
 *
 * **Not the spire's height, and the difference is what makes a stack
 * selectable at all.** Roles at one employer are stacked *coaxially*, 45 m
 * apart on the same axis. Give each of them a 1.65 km tube and every tube in
 * the stack occupies the same sky as every other; a ray through any of them
 * passes through all of them, three returns the nearest, and one role — always
 * the same one — answers for the whole employer. It was tried, and the unit
 * test that picks each of two roles at one company caught it immediately.
 *
 * Forty-five metres is the spacing itself, so the targets **tile**: role *n*
 * owns the 45 m above its own anchor and nothing else, and every role in a
 * stack is reachable by the click that lands on it. `beacon.test.ts` pins it
 * against both spacings rather than against the number, so a field that spreads
 * its roles further apart goes red here instead of quietly leaving gaps.
 *
 * The cost, stated: most of a spire is not clickable. The light is a flag
 * visible from twelve kilometres; the role is at its foot, and that is where
 * the mouse has to go. A whole-spire target cannot coexist with a stack, and a
 * stack is the more important of the two.
 */
export const PICK_HEIGHT = 45;

/**
 * How fast the column's light rises, in Hz.
 *
 * Five seconds a cycle. Slow enough to read as the city breathing rather than
 * as a progress bar, and far under WCAG 2.3.1's three-a-second threshold with
 * the two recency pulses it runs alongside.
 *
 * This is the *envelope* — how far up the spire the light reaches. On its own
 * it is an animation almost nobody ever sees, and that is a finding rather
 * than a guess: at 1.65 km the top of a column is off the top of the frame at
 * every pose this city is actually read at, so the one part of the shaft the
 * envelope changes is the one part that is not on screen. Two captures 2.5 s
 * apart were pixel-identical along the whole visible length. `FLOW_HZ` is what
 * fixes that.
 */
export const RISE_HZ = 0.2;

/**
 * The travelling light, and the gesture that is actually visible.
 *
 * A repeating band scrolling up the shaft rather than one head chasing the
 * envelope's front. A single head is in frame for a couple of seconds out of
 * every five and off the top for the rest; a repeating pattern means there is
 * always motion in the first few hundred metres above the roof, which is where
 * the role is and where the eye already is.
 *
 * `FLOW_BANDS` is how many bands fit the whole spire, so the wavelength is
 * 1,650 / 9 ≈ 183 m — a band roughly every sixty storeys. `FLOW_HZ` is how
 * many wavelengths pass a fixed point per second: 0.45, so a band takes about
 * 2.2 s to travel one wavelength and about six seconds to cross the visible
 * stretch of a column at a mid pose. That is also the flicker rate at any one
 * point, and it is well under WCAG 2.3.1's three a second — the test pins it,
 * because "make the beacons more obviously alive" is the change somebody will
 * try to make here and speeding this up is how they will try to make it.
 */
export const FLOW_HZ = 0.45;
export const FLOW_BANDS = 9;

/**
 * The most beacons this mesh will allocate room for.
 *
 * An `InstancedMesh` allocates its buffers once at its declared count, so this
 * is a real ceiling rather than a hint. It matches `MAX_SIGNALS` on the API,
 * which is the most the endpoint will ever send.
 */
export const MAX_BEACONS = 5_000;

/**
 * How fast each §6 pulse runs, in Hz.
 *
 * Both are far below WCAG 2.3.1's three-flashes-a-second threshold, and the
 * test pins that — "make the new ones more obvious" is the most natural change
 * anyone will ever make to this file, and the natural way to make it is to
 * raise these numbers.
 */
export const PULSE_HZ = { none: 0, slow: 0.28, rapid: 0.75 } as const;

/**
 * What a dimmed role's strength is multiplied by.
 *
 * §6: reduced opacity for a stale or unverified listing, and explicitly "not a
 * glitch — a glitch reads as a bug, gets reported as one, and then gets
 * ignored". So it dims to something clearly still there. A role faded to
 * nothing would be indistinguishable from one that had closed, which is the
 * exact confusion I3 exists to prevent.
 */
export const DIM_FACTOR = 0.45;

/** How much larger a new role is drawn, before any pulse. */
export const NEW_SCALE = 1.22;

/** One beacon, as the buffer holds it. */
export interface Beacon {
  readonly x: number;
  readonly y: number;
  readonly z: number;
  readonly tint: string;
  /** Strength before the pulse. Dimming is already applied by the caller. */
  readonly alpha: number;
  /** Hz. Zero means still, and a buffer of zeroes means no repaints at all. */
  readonly pulse: number;
  /** Base size multiplier — `NEW_SCALE` for a new role, 1 otherwise. */
  readonly scale: number;
}

export interface BeaconMesh {
  readonly mesh: InstancedMesh;
  set(beacons: readonly Beacon[]): void;
  readonly drawn: number;
  /** Move the shader's clock, in seconds. The only per-frame call. */
  tick(seconds: number): void;
  /**
   * The drawing surface in CSS pixels, for the column's two pixel floors.
   *
   * Handed in rather than read off a canvas here: this file knows nothing
   * about MapLibre, and a second reading of the viewport is a second thing
   * that can disagree with the one the projection was built from.
   */
  setViewport(width: number, height: number): void;
  /**
   * Whether the ambient rise runs at all.
   *
   * False draws every column whole and still, which is what
   * `prefers-reduced-motion` has to mean here: the rise is not a fact about a
   * role, so switching it off must not leave the light frozen at whatever
   * fraction of the way up the clock happened to stop.
   */
  setMotion(enabled: boolean): void;
  /**
   * Where the camera stands, in scene metres.
   *
   * Handed in per frame from the same matrix the frame is drawn with — never
   * from a second derivation of the pose — for the reason `cityBuildings`'
   * haze takes it the same way: a camera position that disagreed with the
   * projection would shade every column from slightly the wrong side, which
   * reads as nothing at all being wrong.
   */
  setEye(x: number, y: number, z: number): void;
  /** The clock the buffer currently holds. */
  readonly timeAt: number;
  /**
   * Is anything in this buffer moving? What decides whether to ask for a frame.
   *
   * **Any drawn column is moving.** ADR 0034 made the rise ambient and
   * identical on every role; this getter went on answering the question it
   * answered before that ADR — is some role new enough to earn a recency
   * pulse? The two stopped being the same question and the code did not
   * notice.
   *
   * On the seeded corpus it happened to be harmless: 27 of 30 roles are inside
   * `NEW_WINDOW_DAYS`, so something was always pulsing and the frames kept
   * coming. It is not harmless in general. A city whose roles are all more
   * than a week old — which is every city this product has been open in front
   * of for a week — would have gone completely still while the shader stood
   * ready to animate it, and no test or screenshot would have said so.
   *
   * The cost is real and is the one the render loop's comment warns about: a
   * city with a single role on it now repaints continuously. That is what an
   * ambient animation *is*, and `setMotion(false)` is the way out of it.
   */
  readonly animating: boolean;
  tintAt(index: number): string | null;
  alphaAt(index: number): number | null;
  pulseAt(index: number): number | null;
  scaleAt(index: number): number | null;
  /** The altitude the *matrix* holds, not the one that was handed in. */
  altitudeAt(index: number): number | null;
  dispose(): void;
}

export function createBeaconMesh(capacity: number = MAX_BEACONS): BeaconMesh {
  // One geometry, one material, one mesh, N transforms — §5.5.
  //
  // A column rather than the octahedron this drew for three milestones, and
  // ADR 0034 has the argument. The short version is that a diamond has an
  // orientation and a column does not: at the pitch this city is read at you
  // see an octahedron near edge-on, which is why a stack of roles read as a
  // stack of rhombi rather than as one thing.
  //
  // Open-ended, because a cap is a hard disc exactly where the light is
  // supposed to be dissipating. Unit-sized and scaled in the vertex shader,
  // where the pixel floor can be applied — a size baked in here could not
  // know how far away it is.
  // Built at the *click target's* size rather than the light's — see
  // `PICK_RADIUS` and `PICK_HEIGHT` — because `pick.ts` raycasts this geometry
  // and a size that lives only in the shader cannot be picked. The shader
  // below works relative to it, scaling down in width and up in height, so
  // there is one size on the CPU and one shape on the screen and each of them
  // is written once.
  const geometry = new CylinderGeometry(PICK_RADIUS, PICK_RADIUS, PICK_HEIGHT, 24, 1, true);
  // Three's cylinder runs along y and the scene's up is z. Rotated once here
  // rather than per instance, so the instance matrix stays a translate-and-
  // scale and the orientation cannot be forgotten by a caller.
  geometry.rotateX(Math.PI / 2);
  // Sits *on* its anchor rather than straddling it, so a role placed on a roof
  // rises from the roof instead of sinking half a column into the building.
  geometry.translate(0, 0, PICK_HEIGHT / 2);

  const tint = new InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
  const alpha = new InstancedBufferAttribute(new Float32Array(capacity), 1);
  const pulse = new InstancedBufferAttribute(new Float32Array(capacity), 1);
  geometry.setAttribute('tint', tint);
  geometry.setAttribute('alpha', alpha);
  geometry.setAttribute('pulse', pulse);

  const material = new ShaderMaterial({
    uniforms: {
      time: { value: 0 },
      viewport: { value: new Vector2(1440, 900) },
      motion: { value: 1 },
      // Where the camera stands, in scene metres. See `vThickness` below for
      // why a shader in this renderer cannot work it out for itself.
      eye: { value: new Vector3(0, 0, 1) },
    },
    // `instanceMatrix`, `position`, `normal`, `normalMatrix`,
    // `projectionMatrix` and `modelViewMatrix` are declared by three itself
    // for a non-raw `ShaderMaterial` — redeclaring any of them is a compile
    // error, so this declares only what three does not.
    vertexShader: /* glsl */ `
      uniform float time;
      uniform vec2 viewport;
      uniform vec3 eye;
      attribute vec3 tint;
      attribute float alpha;
      attribute float pulse;
      varying vec3 vTint;
      varying float vAlpha;
      varying float vUp;
      varying float vThickness;

      void main() {
        // A pulse of zero must be perfectly still, not slow: 'new' is a claim
        // about a role and a beacon that breathes at 0 Hz would make every
        // role look new.
        float wave = pulse > 0.0 ? 0.5 + 0.5 * sin(time * pulse * 6.28318530718) : 1.0;
        vTint = tint;
        // Never below half strength. A beacon that blinks out is a role that
        // appears to have closed, twice a second.
        vAlpha = alpha * mix(0.55, 1.0, wave);

        // Scene metres straight to clip space. ADR 0025: MapLibre hands over
        // one composed matrix and the model-view is left alone, so these two
        // are not a view and a projection and must never be read as though
        // they were. Everything below works in scene metres and applies this
        // once, at the end.
        mat4 toClip = projectionMatrix * modelViewMatrix;
        vec3 anchor = (instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;

        // The horizontal direction from this column to the camera, and the
        // screen-right perpendicular to it. Both are needed below; the first
        // also shades the shaft. See vThickness.
        vec2 toEye = eye.xy - anchor.xy;
        // A camera directly overhead has no horizontal direction to offer, and
        // a column seen from straight above is a disc with no silhouette to
        // soften. Anything is right there; this keeps it finite.
        vec2 view = length(toEye) > 1e-3 ? normalize(toEye) : vec2(0.0, 1.0);
        vec2 across = vec2(-view.y, view.x);

        // --- How big this column would be on screen ----------------------
        //
        // Measured by projecting one metre and looking at where it lands,
        // rather than read out of the matrix's elements.
        //
        // **The version this replaces read element [1][1] as 1/tan(fov/2).**
        // That is true of a perspective projection and false of the matrix
        // this renderer is handed, which folds the whole world transform in
        // and carries a scale of about 1e-7 there. The floors below came out
        // around 7,000x, every column was scaled to tens of kilometres across
        // and hundreds of kilometres tall, and the entire mesh clipped out of
        // frame — so the bodies drew nothing at all, at any zoom, and the
        // marks and the roof beams have been standing in for them.
        //
        // Projecting a known length and measuring it needs no assumption about
        // what the matrix contains, which is the property worth having in a
        // renderer whose matrix belongs to somebody else.
        vec4 clipAnchor = toClip * vec4(anchor, 1.0);
        vec4 clipAcross = toClip * vec4(anchor + vec3(across, 0.0), 1.0);
        vec4 clipUp = toClip * vec4(anchor + vec3(0.0, 0.0, 1.0), 1.0);
        vec2 halfViewport = 0.5 * viewport;
        vec2 ndcAnchor = clipAnchor.xy / clipAnchor.w;
        float pxPerMetreAcross = length((clipAcross.xy / clipAcross.w - ndcAnchor) * halfViewport);
        float pxPerMetreUp = length((clipUp.xy / clipUp.w - ndcAnchor) * halfViewport);

        float widthPx = 2.0 * ${COLUMN_RADIUS.toFixed(1)} * pxPerMetreAcross;
        float heightPx = ${COLUMN_HEIGHT.toFixed(1)} * pxPerMetreUp;
        // Two floors, two factors. One factor applied to both axes is how a
        // distant column would get taller only by getting fatter, which turns
        // a light shaft into a lozenge.
        //
        // Grow, never shrink: up close the metres are already right. The
        // ceiling is not a design parameter, it is a guard — behind the camera
        // the w divide above is meaningless, and a column that has left the
        // frame should leave it rather than become a continent. It is far
        // above anything the zoom range reaches.
        float growW = clamp(${MIN_COLUMN_WIDTH_PX.toFixed(1)} / max(widthPx, 1e-4), 1.0, 400.0);
        float growH = clamp(${MIN_COLUMN_HEIGHT_PX.toFixed(1)} / max(heightPx, 1e-4), 1.0, 400.0);

        // The 'new' scale rides on the instance matrix and the recency pulse
        // swells the body, exactly as they did on the octahedron — both are
        // claims about the *role*, and neither is what the column itself is.
        // The swell is width only: a spire that grew 8% *longer* twice a
        // second would read as the light reaching further, which is the rise's
        // gesture and already means something else.
        float swell = mix(0.92, 1.08, wave);
        // Relative to the geometry, which is the click target: narrower in
        // width, and a great deal taller.
        vec3 sized = position * vec3(
          ${(COLUMN_RADIUS / PICK_RADIUS).toFixed(4)} * growW * swell,
          ${(COLUMN_RADIUS / PICK_RADIUS).toFixed(4)} * growW * swell,
          ${(COLUMN_HEIGHT / PICK_HEIGHT).toFixed(4)} * growH
        );

        // Zero at the foot, one at the top of the light — not of the target.
        vUp = position.z / ${PICK_HEIGHT.toFixed(1)};

        // --- How much column the eye is looking through ------------------
        //
        // Zero at the silhouette, one through the middle. This is what turns a
        // hard-edged tube into a soft-edged glow without a second mesh, a
        // texture or a blur — and a soft edge is one of the four things ADR
        // 0034 gives a role that the city, all crisp mullions and hairlines,
        // cannot have.
        //
        // **The first version was exactly zero everywhere**, for the same
        // reason the size floors were wrong: it was
        // abs(normalize(normalMatrix * normal).z), which is how you ask "is
        // this surface facing me" in a renderer that has a view matrix. Here
        // normalMatrix carries no view rotation, so that .z is the world's up
        // rather than the camera's forward — and a cylinder standing on end
        // has purely horizontal normals.
        //
        // The column's axis is world-up, so the fraction of the tube the eye
        // sees through depends only on the horizontal direction to the camera:
        // with the radial unit normal n and that direction d, it is |n · d|.
        // Per instance, so a column at the edge of a wide frame is shaded from
        // where it actually is rather than from the middle of the screen.
        //
        // The geometry is a unit cylinder, so the radial normal *is* the
        // vertex's own xy direction — read off the position rather than the
        // normal attribute, which is what the broken version reached for.
        vThickness = abs(dot(normalize(position.xy), view));

        gl_Position = toClip * instanceMatrix * vec4(sized, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform float time;
      uniform float motion;
      varying vec3 vTint;
      varying float vAlpha;
      varying float vUp;
      varying float vThickness;

      void main() {
        // --- Across the shaft --------------------------------------------
        //
        // A filament inside a haze, rather than an evenly lit tube. The
        // thickness alone gave a solid cylinder with a soft rim, which reads
        // as a cyan *object*; a light shaft is mostly glow with a hard bright
        // line down its axis, and that is what the reference's columns are.
        // Both terms vanish at the silhouette, so there is still no edge.
        float core = pow(vThickness, 5.0);
        float haze = pow(vThickness, 0.7) * 0.26;

        // --- Along the shaft: the rise (ADR 0034) ------------------------
        //
        // Light leaving the roof: the column is solid at its base and thinning
        // toward its top, and what cycles is how far up the thinning reaches.
        //
        // **The base is never touched, and that is the whole amendment.** The
        // shape asked for was whole, slimmer, gone, back. Gone is already
        // spoken for — §6 spends disappearance on 'closed' and on 'rejection'
        // — so a mark that periodically vanishes tells a lie about a listing
        // every five seconds. This reads the same and does not say that.
        //
        // Ambient and identical on every role: the rise is what says 'this is
        // a job'. Recency stays on the two channels it already had, the
        // brightness pulse above and NEW_SCALE, so one gesture is not being
        // asked to carry two meanings.
        //
        // **Under reduced motion the column is drawn whole**, not frozen at
        // whatever the clock stopped on. The motion uniform is the switch, and
        // it is a uniform rather than a zeroed attribute because, unlike the
        // pulses, this is not a fact about any role — every column rises
        // identically, so there is nothing in the buffer for it to be honest
        // about.
        float reach = mix(1.12, mix(0.34, 1.12, fract(time * ${RISE_HZ.toFixed(2)})), motion);
        float body = 1.0 - smoothstep(reach * 0.22, reach, vUp);
        // Brightest at the foot even when the light has reached the top, so
        // the eye is pulled to the roof the role actually stands on rather
        // than to the middle of a uniform bar. It is also what keeps a stack
        // of roles at one employer readable as a stack: each column carries
        // its own bright knot at its own base, 45 m above the one below it.
        body *= mix(1.0, 0.30, vUp);

        // --- The travelling light ----------------------------------------
        //
        // Bands scrolling up the shaft, and this is the motion anybody
        // actually sees. The envelope above changes the column's *top*, which
        // at 1.65 km is off the top of the frame at every pose this city is
        // read at — an animation that is real, measurable in the uniform, and
        // invisible.
        //
        // Wrapped with fract() so it repeats, and the band is measured as a
        // wrapped distance to the band centre rather than from fract()
        // directly, because a gaussian of a sawtooth has a hard seam at the
        // wrap.
        float flow = fract(vUp * ${FLOW_BANDS.toFixed(1)} - time * ${FLOW_HZ.toFixed(2)});
        float band = exp(-pow(abs(flow - 0.5) / 0.16, 2.0));

        // **It multiplies, it does not add.** The first version added light at
        // the bands, which is the obvious way to write a travelling glow and
        // is invisible here: the shaft's core is already at or past full
        // strength, this material is additive, and light added to a clipped
        // pixel changes nothing. Measured over a whole rise cycle, the column
        // moved by 2% and looked still. Dimming *between* the bands has
        // headroom wherever the shaft is bright, which is exactly where the
        // motion needs to be seen.
        float travel = mix(1.0, mix(0.62, 1.12, band), motion);

        float a = vAlpha * (core + haze) * body * travel;

        gl_FragColor = vec4(vTint, a);
      }
    `,
    transparent: true,
    // Additive, so overlapping beacons brighten instead of flattening into one
    // silhouette — a stack of roles at one employer should read as a stack.
    blending: AdditiveBlending,
    // Written depth from an additive, transparent mesh occludes the beacons
    // behind it with an invisible surface. Reading depth is still on, which is
    // the half that matters: a building in front of a beacon still hides it.
    depthWrite: false,
  });

  const mesh = new InstancedMesh(geometry, material, capacity);
  mesh.frustumCulled = false;
  mesh.count = 0;

  const scratch = new Object3D();
  const colour = new Color();

  let drawn = 0;
  let motion = true;
  let scales: number[] = [];

  return {
    mesh,

    get drawn() {
      return drawn;
    },

    get animating() {
      return motion && drawn > 0;
    },

    get timeAt() {
      return material.uniforms.time?.value as number;
    },

    set(beacons) {
      const count = Math.min(beacons.length, capacity);
      scales = [];

      for (let i = 0; i < count; i += 1) {
        const item = beacons[i];
        if (!item) break;
        scratch.position.set(item.x, item.y, item.z);
        scratch.scale.setScalar(item.scale);
        scratch.updateMatrix();
        mesh.setMatrixAt(i, scratch.matrix);

        colour.set(item.tint);
        tint.setXYZ(i, colour.r, colour.g, colour.b);
        alpha.setX(i, item.alpha);
        pulse.setX(i, item.pulse);
        scales.push(item.scale);
      }

      mesh.count = count;
      mesh.instanceMatrix.needsUpdate = true;
      tint.needsUpdate = true;
      alpha.needsUpdate = true;
      pulse.needsUpdate = true;
      // three caches the bounding sphere on first raycast and gates every later
      // one on it, so a field that grows keeps a sphere too small to admit its
      // new columns — and picking silently stops working for exactly the
      // employers that just arrived. `pick.test.ts` demonstrates it.
      mesh.boundingSphere = null;
      drawn = count;
    },

    tick(seconds) {
      if (material.uniforms.time) material.uniforms.time.value = seconds;
    },

    setViewport(width, height) {
      if (width > 0 && height > 0) {
        (material.uniforms.viewport!.value as Vector2).set(width, height);
      }
    },

    setMotion(enabled) {
      motion = enabled;
      material.uniforms.motion!.value = enabled ? 1 : 0;
    },

    setEye(x, y, z) {
      (material.uniforms.eye!.value as Vector3).set(x, y, z);
    },

    tintAt(index) {
      if (index < 0 || index >= drawn) return null;
      colour.setRGB(tint.getX(index), tint.getY(index), tint.getZ(index));
      return `#${colour.getHexString()}`;
    },

    alphaAt(index) {
      if (index < 0 || index >= drawn) return null;
      return alpha.getX(index);
    },

    pulseAt(index) {
      if (index < 0 || index >= drawn) return null;
      return pulse.getX(index);
    },

    scaleAt(index) {
      if (index < 0 || index >= drawn) return null;
      return scales[index] ?? null;
    },

    altitudeAt(index) {
      if (index < 0 || index >= drawn) return null;
      const matrix = mesh.matrix.clone();
      mesh.getMatrixAt(index, matrix);
      // Element 14 of a column-major 4×4 is the z translation, and the scene's
      // z is metres above the anchor's ground plane.
      return matrix.elements[14] ?? null;
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
      scales = [];
    },
  };
}
