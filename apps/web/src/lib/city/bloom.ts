/**
 * Bloom — the light spilling out of everything bright, over the whole frame.
 *
 * M4e Task 7. The city has been drawing its neon at exactly the width of the
 * geometry that emits it since ADR 0029 lit it: a window is a 2 px square, a
 * roofline is a 1 px line, and both stop dead at their own edge. Every one of
 * `docs/design/references/` is built the other way round — the light is *wider*
 * than the thing making it, and the halo is most of what the eye reads as
 * brightness. A lamp with no halo does not look dim; it looks like a drawing of
 * a lamp. That is the whole gap this file closes.
 *
 * **It runs over the composited frame, not over our scene.** The obvious
 * implementation renders the Three scene into an offscreen target, blooms that,
 * and composites it back — and it would leave out the two brightest things on
 * screen, because the streets are MapLibre `line` layers and the sun is
 * `map/skyLayer.ts`. Reference 02 is a grid plane and a horizon glow; blooming
 * everything except those is blooming the wrong half of the picture. So this
 * takes the frame apart *after* everything has drawn into it: the signal layer
 * is the last layer in the style, so at the end of its render the colour buffer
 * holds the finished city, and that buffer is both the input and the output.
 *
 * **The read is a hardware blit, not a `readPixels`.** Pulling a 2880×1800
 * frame back to the CPU would cost a pipeline stall a frame; `blitFramebuffer`
 * downsamples on the GPU and never leaves it. That is the one call here that
 * needs WebGL 2, and it is why `available` can be false — see below.
 *
 * **Three octaves, because one is a smudge.** A single blur radius gives either
 * a tight rim with no atmosphere or a wash with no core. The chain halves three
 * times and adds the results back with falling weights, so a lit window keeps a
 * hard centre, gains a small halo, and contributes to a broad glow over the
 * whole block — which is what a city photographed at night actually does.
 *
 * **Nothing here is pinned by a test except its semantics.** ADR 0031's working
 * method: a threshold, a radius and a weight are taste, judged by the human
 * against reference 02, and a test asserting them would freeze the tuning
 * rather than protect it. What `bloom.test.ts` does assert is the arithmetic
 * that must not drift — the soft-knee curve is monotonic and passes nothing
 * below the threshold, and the octave sizes never reach zero on a small canvas.
 */

/** Either context. Only the blit needs the WebGL 2 half; see `createBloom`. */
type AnyGL = WebGLRenderingContext | WebGL2RenderingContext;

/**
 * Luminance at which a pixel starts to glow, on the 0..1 the frame is stored in.
 *
 * The city's own mass sits far below this and its neon far above, which is the
 * only reason a single number works: `ink-950` is 0.03 and `neon-400` is 0.50,
 * so the threshold has most of a decade of empty space to sit in. It is the
 * first knob to move if the frame looks washed (raise) or flat (lower).
 */
export const BLOOM_THRESHOLD = 0.18;

/**
 * How soft the threshold is — the width of the ramp either side of it.
 *
 * A hard cut makes bloom pop on and off as a surface crosses the threshold,
 * which on a rotating camera reads as flicker along every lit edge. The knee
 * turns that step into a quadratic.
 */
export const BLOOM_KNEE = 0.12;

/** How much of the blurred light is added back. Straight multiplier. */
export const BLOOM_STRENGTH = 0.85;

/**
 * What each octave contributes: tight, medium, broad.
 *
 * Falling rather than equal — an even mix is a fog. The broad octave is a
 * sixteenth of the frame's resolution, so its weight buys atmosphere over a
 * whole district for almost nothing.
 */
export const BLOOM_OCTAVE_WEIGHTS = [1.0, 0.62, 0.38] as const;

/** How many halvings the chain runs. Three is `BLOOM_OCTAVE_WEIGHTS.length`. */
export const BLOOM_OCTAVES = BLOOM_OCTAVE_WEIGHTS.length;

/**
 * Octave sizes for a canvas, in device pixels, smallest dimension clamped to 1.
 *
 * Exported for the test rather than for a caller: a 40 px tall window on a
 * phone in landscape drives the fourth halving to zero, and a zero-sized
 * texture is an incomplete framebuffer — which fails as a black frame with a
 * console warning nobody is watching for.
 */
export function octaveSizes(width: number, height: number): { width: number; height: number }[] {
  const sizes: { width: number; height: number }[] = [];
  // The chain starts at a half-res copy of the frame, so octave 0 is a quarter.
  let w = width;
  let h = height;
  for (let i = 0; i <= BLOOM_OCTAVES; i += 1) {
    w = Math.max(1, Math.floor(w / 2));
    h = Math.max(1, Math.floor(h / 2));
    sizes.push({ width: w, height: h });
  }
  return sizes;
}

/**
 * The soft-knee curve, in TypeScript, so a test can hold the shader to it.
 *
 * The shader below computes this per pixel and the two must agree; a curve that
 * drifts from its own description is the sort of thing that gets found by
 * eye months later. Returns the fraction of a pixel's colour that blooms.
 */
export function bloomContribution(luma: number, threshold: number, knee: number): number {
  const soft = Math.min(Math.max(luma - threshold + knee, 0), 2 * knee);
  const curved = (soft * soft) / (4 * knee + 0.0001);
  return Math.max(curved, luma - threshold) / Math.max(luma, 0.0001);
}

const VERTEX_SOURCE = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

/**
 * What is bright enough to glow, and by how much.
 *
 * The four taps are a box filter, not an economy: the source is exactly twice
 * this target's size, so a bilinear tap offset half a source texel into each
 * quadrant averages four source texels, and four of them average sixteen. A
 * single centre tap instead would sample one 2×2 out of every 4×4 and drop
 * three quarters of the thin lines this city is made of — which on a moving
 * camera is not softness, it is sparkle.
 */
const BRIGHT_SOURCE = `
precision highp float;
uniform sampler2D u_source;
uniform vec2 u_texel;
uniform float u_threshold;
uniform float u_knee;
varying vec2 v_uv;

void main() {
  vec3 c = texture2D(u_source, v_uv + u_texel * vec2(-1.0, -1.0)).rgb;
  c += texture2D(u_source, v_uv + u_texel * vec2( 1.0, -1.0)).rgb;
  c += texture2D(u_source, v_uv + u_texel * vec2(-1.0,  1.0)).rgb;
  c += texture2D(u_source, v_uv + u_texel * vec2( 1.0,  1.0)).rgb;
  c *= 0.25;

  // Rec. 709 luma. A max() of the channels instead would bloom a saturated
  // blue as hard as a white, and this city is mostly saturated blue.
  float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
  float soft = clamp(luma - u_threshold + u_knee, 0.0, 2.0 * u_knee);
  soft = soft * soft / (4.0 * u_knee + 0.0001);
  float contribution = max(soft, luma - u_threshold) / max(luma, 0.0001);
  gl_FragColor = vec4(c * contribution, 1.0);
}
`;

/**
 * One axis of a Gaussian, five taps standing in for nine.
 *
 * The offsets are between texels on purpose: each one is a bilinear fetch that
 * returns a weighted pair, so five samples carry nine taps' worth of kernel.
 * The weights are the normalised 9-tap binomial and the offsets are their
 * centres of mass — this is the standard collapse, written out rather than
 * imported so the numbers can be checked.
 *
 * It also does the halving between octaves: a horizontal pass whose target is
 * half the source's size resolves the vertical axis by bilinear minification
 * on the way in, which is a box filter, which is what a downsample wants.
 */
const BLUR_SOURCE = `
precision highp float;
uniform sampler2D u_source;
uniform vec2 u_step;
varying vec2 v_uv;

void main() {
  vec3 c = texture2D(u_source, v_uv).rgb * 0.2270270270;
  c += (texture2D(u_source, v_uv + u_step * 1.3846153846).rgb +
        texture2D(u_source, v_uv - u_step * 1.3846153846).rgb) * 0.3162162162;
  c += (texture2D(u_source, v_uv + u_step * 3.2307692308).rgb +
        texture2D(u_source, v_uv - u_step * 3.2307692308).rgb) * 0.0702702703;
  gl_FragColor = vec4(c, 1.0);
}
`;

/**
 * The three octaves added back onto the frame, with `blendFunc(ONE, ONE)`.
 *
 * Additive rather than a lerp, because bloom is light arriving at the sensor on
 * top of what was already there. A blend would *replace* the crisp pixel with a
 * blurred one and take the core out of every window.
 */
const COMPOSITE_SOURCE = `
precision highp float;
uniform sampler2D u_octave0;
uniform sampler2D u_octave1;
uniform sampler2D u_octave2;
uniform vec3 u_weights;
uniform float u_strength;
varying vec2 v_uv;

void main() {
  vec3 c = texture2D(u_octave0, v_uv).rgb * u_weights.x
         + texture2D(u_octave1, v_uv).rgb * u_weights.y
         + texture2D(u_octave2, v_uv).rgb * u_weights.z;
  gl_FragColor = vec4(c * u_strength, 1.0);
}
`;

function compile(gl: AnyGL, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (shader === null) throw new Error('bloom: could not create shader');
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`bloom: shader did not compile: ${log ?? 'no log'}`);
  }
  return shader;
}

/**
 * The attribute slot every program here uses for the fullscreen triangle.
 *
 * Bound explicitly rather than looked up, so all three programs agree and one
 * vertex array can serve them all. Per-program `getAttribLocation` would work
 * too, right up until a driver assigns different slots and the shared array
 * feeds the wrong one.
 */
const POSITION_LOCATION = 0;

function link(gl: AnyGL, fragmentSource: string): WebGLProgram {
  const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX_SOURCE);
  const fragment = compile(gl, gl.FRAGMENT_SHADER, fragmentSource);
  const program = gl.createProgram();
  if (program === null) throw new Error('bloom: could not create program');
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.bindAttribLocation(program, POSITION_LOCATION, 'a_pos');
  gl.linkProgram(program);
  // Detached whether or not the link succeeded — the program owns them now, and
  // a style reload that fails to link would otherwise leak two per attempt.
  gl.detachShader(program, vertex);
  gl.detachShader(program, fragment);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`bloom: program did not link: ${log ?? 'no log'}`);
  }
  return program;
}

interface Target {
  readonly framebuffer: WebGLFramebuffer;
  readonly texture: WebGLTexture;
  readonly width: number;
  readonly height: number;
}

function createTarget(gl: AnyGL, width: number, height: number): Target {
  const texture = gl.createTexture();
  const framebuffer = gl.createFramebuffer();
  if (texture === null || framebuffer === null) throw new Error('bloom: could not create target');
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
  // LINEAR is load-bearing rather than a default: every pass above samples
  // between texels and relies on the hardware to weight the pair.
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  // Clamped, so the widest tap at the edge of the frame reads the edge pixel
  // rather than wrapping the far side of the city into it.
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
  return { framebuffer, texture, width, height };
}

export interface Bloom {
  /**
   * Whether this context can run the effect at all.
   *
   * False on WebGL 1, where `blitFramebuffer` does not exist. MapLibre asks for
   * a WebGL 2 context first and falls back, so this is a real machine rather
   * than a hypothetical one — and the honest behaviour there is a city with no
   * glow rather than a city that fails to draw. `signalLayer` reports it.
   */
  readonly available: boolean;
  /** Frames this has actually run on. The one thing a test can ask with no GPU. */
  readonly drawn: number;
  /**
   * Bloom the framebuffer that is currently bound, in place.
   *
   * Must be called after everything that should glow has drawn into it. Leaves
   * that framebuffer bound and the viewport covering it; every other piece of
   * GL state it touches is invalidated by MapLibre's own `setDirty()`
   * immediately after the custom layer returns, and by Three's `resetState()`
   * at the top of the next frame.
   */
  apply(): void;
  dispose(): void;
}

export interface BloomOptions {
  readonly threshold?: number;
  readonly knee?: number;
  readonly strength?: number;
}

/**
 * Build the effect against MapLibre's own context.
 *
 * Nothing is allocated until the first `apply`, because the drawing buffer's
 * size is not knowable at `onAdd` — the map may not have been laid out yet, and
 * a chain sized against a 300×150 default canvas would be rebuilt on the first
 * real frame anyway.
 */
export function createBloom(gl: AnyGL, options: BloomOptions = {}): Bloom {
  const threshold = options.threshold ?? BLOOM_THRESHOLD;
  const knee = options.knee ?? BLOOM_KNEE;
  const strength = options.strength ?? BLOOM_STRENGTH;

  // The feature test is for the method rather than for `instanceof
  // WebGL2RenderingContext`: the constructor is absent in some embedded
  // runtimes where the method is not, and jsdom has neither.
  const gl2 = gl as WebGL2RenderingContext;
  const available = typeof gl2.blitFramebuffer === 'function';

  let bright: WebGLProgram | null = null;
  let blur: WebGLProgram | null = null;
  let composite: WebGLProgram | null = null;
  let quad: WebGLBuffer | null = null;
  /**
   * The effect's own vertex array, and the bug it exists to prevent.
   *
   * Three leaves one of *its* vertex arrays bound when `render` returns.
   * Setting an attribute pointer without binding our own would therefore write
   * into Three's — and read the rest of that array's state back out, including
   * the instancing divisor the beacon mesh sets. A divisor of 1 on the position
   * attribute collapses the fullscreen triangle to a point: every pass runs,
   * every framebuffer is complete, `drawn` climbs, nothing errors, and the
   * frame comes out exactly as it went in. That is what this file did for its
   * first hour, and it is the failure mode a post-process is most likely to
   * have — the effect is *supposed* to be subtle, so "no visible change" reads
   * as "the constants are too low" rather than as "it never drew".
   */
  let vertexArray: WebGLVertexArrayObject | null = null;
  /** The half-res copy of the whole frame; the head of the chain. */
  let half: Target | null = null;
  /**
   * One rung per octave: the octave itself, and a target of the same size for
   * the horizontal half of the separable blur to land in.
   */
  let chain: { readonly octave: Target; readonly scratch: Target }[] = [];
  let sized: { width: number; height: number } | null = null;
  let drawn = 0;

  function programs(): void {
    if (bright !== null) return;
    bright = link(gl, BRIGHT_SOURCE);
    blur = link(gl, BLUR_SOURCE);
    composite = link(gl, COMPOSITE_SOURCE);
    quad = gl.createBuffer();
    vertexArray = gl2.createVertexArray();
    gl2.bindVertexArray(vertexArray);
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    // One triangle, as in `skyLayer.ts`: two would put a seam down the diagonal
    // for every pass to widen.
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(POSITION_LOCATION);
    gl.vertexAttribPointer(POSITION_LOCATION, 2, gl.FLOAT, false, 0, 0);
    gl2.bindVertexArray(null);
  }

  function releaseTargets(): void {
    const targets: Target[] = [];
    if (half !== null) targets.push(half);
    for (const rung of chain) targets.push(rung.octave, rung.scratch);
    for (const target of targets) {
      gl.deleteFramebuffer(target.framebuffer);
      gl.deleteTexture(target.texture);
    }
    half = null;
    chain = [];
    sized = null;
  }

  function resize(width: number, height: number): void {
    if (sized !== null && sized.width === width && sized.height === height) return;
    // Every resize throws the whole chain away and builds a new one. A canvas
    // resize is a window drag, not a frame, so the allocation cost is invisible
    // — and reusing a texture at the wrong size is how a post-process ends up
    // sampling last week's frame down one edge.
    releaseTargets();
    const [halfSize, ...rungs] = octaveSizes(width, height);
    if (halfSize === undefined) return;
    half = createTarget(gl, halfSize.width, halfSize.height);
    chain = rungs.map((size) => ({
      octave: createTarget(gl, size.width, size.height),
      scratch: createTarget(gl, size.width, size.height),
    }));
    sized = { width, height };
  }

  /**
   * Draw the fullscreen triangle into `target`, with `program` already selected
   * and its uniforms already set.
   */
  function pass(target: WebGLFramebuffer | null, width: number, height: number): void {
    gl.bindFramebuffer(gl.FRAMEBUFFER, target);
    gl.viewport(0, 0, width, height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  return {
    get available() {
      return available;
    },
    get drawn() {
      return drawn;
    },

    apply() {
      if (!available) return;
      const width = gl.drawingBufferWidth;
      const height = gl.drawingBufferHeight;
      if (width < 4 || height < 4) return;

      // Whatever MapLibre is drawing into — usually the default framebuffer,
      // but not when terrain or a projection transition is on. Read from it and
      // write back to it, rather than assuming null and blooming a buffer
      // nobody is going to present.
      const frame = gl.getParameter(gl.FRAMEBUFFER_BINDING) as WebGLFramebuffer | null;

      programs();
      resize(width, height);
      if (half === null || bright === null || blur === null || composite === null) return;
      const first = chain[0];
      if (first === undefined) return;

      gl.disable(gl.DEPTH_TEST);
      gl.depthMask(false);
      gl.disable(gl.STENCIL_TEST);
      gl.disable(gl.SCISSOR_TEST);
      gl.disable(gl.CULL_FACE);
      gl.disable(gl.BLEND);
      // Everything either library may have masked off. A colour mask still
      // closed over one channel is invisible in a screenshot and wrong in every
      // composite the browser does with the page behind the canvas.
      gl.colorMask(true, true, true, true);
      gl.activeTexture(gl.TEXTURE0);
      // Ours, for the whole effect. See `vertexArray` above.
      gl2.bindVertexArray(vertexArray);

      // 1. The frame, halved on the GPU. LINEAR over an exact 2:1 is a 2×2 box.
      gl2.bindFramebuffer(gl2.READ_FRAMEBUFFER, frame);
      gl2.bindFramebuffer(gl2.DRAW_FRAMEBUFFER, half.framebuffer);
      gl2.blitFramebuffer(
        0,
        0,
        width,
        height,
        0,
        0,
        half.width,
        half.height,
        gl.COLOR_BUFFER_BIT,
        gl.LINEAR,
      );
      gl2.bindFramebuffer(gl2.READ_FRAMEBUFFER, null);

      // 2. What glows, at a quarter of the frame.
      gl.useProgram(bright);
      gl.bindTexture(gl.TEXTURE_2D, half.texture);
      gl.uniform1i(gl.getUniformLocation(bright, 'u_source'), 0);
      gl.uniform2f(gl.getUniformLocation(bright, 'u_texel'), 0.5 / half.width, 0.5 / half.height);
      gl.uniform1f(gl.getUniformLocation(bright, 'u_threshold'), threshold);
      gl.uniform1f(gl.getUniformLocation(bright, 'u_knee'), knee);
      pass(first.octave.framebuffer, first.octave.width, first.octave.height);

      // 3. Blur each octave, and halve into the next on the way.
      gl.useProgram(blur);
      const source = gl.getUniformLocation(blur, 'u_source');
      const step = gl.getUniformLocation(blur, 'u_step');
      gl.uniform1i(source, 0);
      for (const [i, rung] of chain.entries()) {
        const { octave, scratch: spare } = rung;
        // Horizontal, into the scratch of the same size.
        gl.bindTexture(gl.TEXTURE_2D, octave.texture);
        gl.uniform2f(step, 1 / octave.width, 0);
        pass(spare.framebuffer, spare.width, spare.height);
        // Vertical, back into the octave.
        gl.bindTexture(gl.TEXTURE_2D, spare.texture);
        gl.uniform2f(step, 0, 1 / spare.height);
        pass(octave.framebuffer, octave.width, octave.height);
        // And halve into the next octave, which the blur does for free: a pass
        // whose target is half the size resolves the other axis by bilinear
        // minification on the way in.
        const next = chain[i + 1];
        if (next !== undefined) {
          gl.bindTexture(gl.TEXTURE_2D, octave.texture);
          gl.uniform2f(step, 1 / octave.width, 0);
          pass(next.octave.framebuffer, next.octave.width, next.octave.height);
        }
      }

      // 4. Back onto the frame, additively.
      gl.useProgram(composite);
      gl.enable(gl.BLEND);
      gl.blendEquation(gl.FUNC_ADD);
      gl.blendFunc(gl.ONE, gl.ONE);
      for (const [i, rung] of chain.entries()) {
        gl.activeTexture(gl.TEXTURE0 + i);
        gl.bindTexture(gl.TEXTURE_2D, rung.octave.texture);
        gl.uniform1i(gl.getUniformLocation(composite, `u_octave${i}`), i);
      }
      gl.uniform3f(
        gl.getUniformLocation(composite, 'u_weights'),
        BLOOM_OCTAVE_WEIGHTS[0],
        BLOOM_OCTAVE_WEIGHTS[1],
        BLOOM_OCTAVE_WEIGHTS[2],
      );
      gl.uniform1f(gl.getUniformLocation(composite, 'u_strength'), strength);
      pass(frame, width, height);

      gl.activeTexture(gl.TEXTURE0);
      gl.disable(gl.BLEND);
      // Handed back, so neither library draws its next thing through ours.
      gl2.bindVertexArray(null);
      drawn += 1;
    },

    dispose() {
      releaseTargets();
      if (vertexArray !== null) gl2.deleteVertexArray(vertexArray);
      vertexArray = null;
      if (bright !== null) gl.deleteProgram(bright);
      if (blur !== null) gl.deleteProgram(blur);
      if (composite !== null) gl.deleteProgram(composite);
      if (quad !== null) gl.deleteBuffer(quad);
      bright = null;
      blur = null;
      composite = null;
      quad = null;
    },
  };
}
