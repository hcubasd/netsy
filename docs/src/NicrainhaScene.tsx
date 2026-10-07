import { useEffect, useRef } from 'react'
import { generatePalettes } from 'nicrainha'
import { buildPermutation, fieldRange } from './glassNoise'
import { paletteOptions } from './palette'

const maximumPanels = 40
const glassIor = 1.5
const gapRatio = 1 / (glassIor - 1) - 1 / glassIor
const parameters = new URLSearchParams(window.location.search)
const gapOffset = (() => {
  const parameter = parameters.get('gap')
  const value = parameter === null ? Number.NaN : Number(parameter)
  return Number.isFinite(value) && value >= 0 ? value : 100
})()

const vertex = `#version 300 es
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`

const fragment = `#version 300 es
precision highp float;
precision highp int;
precision highp usampler2D;
const int MAX_PANELS = 40;
const int MAX_STEPS = 512;
const int MAX_BOUNCES = 64;
uniform usampler2D u_perm;
uniform sampler2D u_palette;
uniform vec2 u_resolution;
uniform float u_z;
uniform float u_min;
uniform float u_range;
uniform int u_count;
uniform vec4 u_panels[MAX_PANELS];
uniform float u_radii[MAX_PANELS];
uniform float u_ior;
uniform float u_gap_offset;
out vec4 outColor;

int P(int i) { return int(texelFetch(u_perm, ivec2(i & 255, 0), 0).r); }
float fade(float t) { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }
float grad(int hash, float x, float y, float z) {
  int h = hash & 15;
  float u = h < 8 ? x : y;
  float v = h < 4 ? y : (h == 12 || h == 14) ? x : z;
  return ((h & 1) != 0 ? -u : u) + ((h & 2) != 0 ? -v : v);
}
float perlin3(vec3 p) {
  vec3 f = floor(p);
  int X = int(f.x), Y = int(f.y), Z = int(f.z);
  vec3 r = p - f;
  float x = r.x, y = r.y, z = r.z;
  float u = fade(x), v = fade(y), w = fade(z);
  int A = P(X) + Y, AA = P(A) + Z, AB = P(A + 1) + Z;
  int B = P(X + 1) + Y, BA = P(B) + Z, BB = P(B + 1) + Z;
  return mix(
    mix(
      mix(grad(P(AA), x, y, z), grad(P(BA), x - 1.0, y, z), u),
      mix(grad(P(AB), x, y - 1.0, z), grad(P(BB), x - 1.0, y - 1.0, z), u), v),
    mix(
      mix(grad(P(AA + 1), x, y, z - 1.0), grad(P(BA + 1), x - 1.0, y, z - 1.0), u),
      mix(grad(P(AB + 1), x, y - 1.0, z - 1.0), grad(P(BB + 1), x - 1.0, y - 1.0, z - 1.0), u), v), w);
}
float backgroundAt(vec2 point) {
  bool portrait = u_resolution.y > u_resolution.x;
  vec2 screen = portrait ? u_resolution.yx : u_resolution;
  vec2 position = portrait ? point.yx : point;
  float height = max(screen.y, screen.x / 2.0);
  vec2 field = (position + (vec2(2.0 * height, height) - screen) / 2.0) / height;
  return perlin3(vec3(field, u_z));
}

vec2 windowMin() { return vec2(0.5); }
vec2 windowMax() { return u_resolution - 0.5; }
vec2 hitBox(vec3 position, vec3 direction) {
  if (direction.z < 0.0) {
    vec2 landing = position.xy + direction.xy * (position.z / -direction.z);
    if (all(greaterThanEqual(landing, windowMin())) && all(lessThanEqual(landing, windowMax()))) return landing;
  }
  vec2 wall = vec2(
    direction.x > 0.0 ? (windowMax().x - position.x) / direction.x : direction.x < 0.0 ? (windowMin().x - position.x) / direction.x : 1e30,
    direction.y > 0.0 ? (windowMax().y - position.y) / direction.y : direction.y < 0.0 ? (windowMin().y - position.y) / direction.y : 1e30);
  float time = min(wall.x, wall.y);
  if (time >= 1e30) return clamp(position.xy, windowMin(), windowMax());
  return clamp(position.xy + time * direction.xy, windowMin(), windowMax());
}

vec2 offsetFromInner(vec2 xy, vec2 halfSize, float radius) {
  return sign(xy) * max(abs(xy) - (halfSize - radius), 0.0);
}
float distanceToTop(vec3 point, vec2 halfSize, float radius, float gap) {
  return length(vec3(offsetFromInner(point.xy, halfSize, radius), point.z - gap)) - radius;
}
float distanceToBottom(vec3 point, float gap) { return gap - point.z; }
float glassDistance(vec3 point, vec2 halfSize, float radius, float gap) {
  return max(distanceToTop(point, halfSize, radius, gap), distanceToBottom(point, gap));
}
vec3 glassNormal(vec3 point, vec2 halfSize, float radius, float gap) {
  if (distanceToBottom(point, gap) > distanceToTop(point, halfSize, radius, gap)) return vec3(0.0, 0.0, -1.0);
  return normalize(vec3(offsetFromInner(point.xy, halfSize, radius), point.z - gap));
}
float distanceToSurface(vec3 origin, vec3 direction, vec2 halfSize, float radius, float gap) {
  float time = 1e-2;
  for (int step = 0; step < MAX_STEPS; step++) {
    float distance = -glassDistance(origin + time * direction, halfSize, radius, gap);
    if (distance < 1e-3) break;
    time += max(distance, 1e-3);
  }
  return time;
}
void traceGlass(inout vec3 position, inout vec3 direction, vec2 halfSize, float radius, float gap) {
  for (int bounce = 0; bounce < MAX_BOUNCES; bounce++) {
    position += distanceToSurface(position, direction, halfSize, radius, gap) * direction;
    vec3 normal = glassNormal(position, halfSize, radius, gap);
    vec3 exitDirection = refract(direction, -normal, u_ior);
    if (exitDirection != vec3(0.0)) {
      direction = exitDirection;
      return;
    }
    direction = reflect(direction, normal);
  }
}
vec2 seenThroughPanel(vec2 pixel, vec4 panel, float radius) {
  vec2 local = pixel - panel.xy;
  vec2 offset = offsetFromInner(local, panel.zw, radius);
  float distance = length(offset);
  if (distance >= radius) return pixel;
  float gap = ${gapRatio.toFixed(8)} * radius + u_gap_offset;
  float height = sqrt(radius * radius - distance * distance);
  vec3 position = vec3(local, gap + height);
  vec3 normal = vec3(offset, height) / radius;
  vec3 direction = refract(vec3(0.0, 0.0, -1.0), normal, 1.0 / u_ior);
  traceGlass(position, direction, panel.zw, radius, gap);
  return hitBox(position + vec3(panel.xy, 0.0), direction);
}
vec2 seenPoint(vec2 pixel) {
  for (int index = MAX_PANELS - 1; index >= 0; index--) {
    if (index >= u_count) continue;
    vec4 panel = u_panels[index];
    vec2 local = pixel - panel.xy;
    vec2 offset = offsetFromInner(local, panel.zw, u_radii[index]);
    if (length(offset) < u_radii[index]) return seenThroughPanel(pixel, panel, u_radii[index]);
  }
  return pixel;
}
void main() {
  vec2 pixel = vec2(gl_FragCoord.x, u_resolution.y - gl_FragCoord.y);
  float value = backgroundAt(seenPoint(pixel));
  float position = clamp((value - u_min) / u_range, 0.0, 1.0);
  outColor = texelFetch(u_palette, ivec2(int(floor(position * 255.0 + 0.5)), 0), 0);
}`

function compile(gl: WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)
  if (!shader) throw new Error('Unable to allocate a scene shader.')
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? 'Unable to compile a scene shader.')
  return shader
}

function texture(gl: WebGL2RenderingContext, unit: number, internalFormat: number, format: number, bytes: Uint8Array) {
  const value = gl.createTexture()
  if (!value) throw new Error('Unable to allocate a scene texture.')
  gl.activeTexture(gl.TEXTURE0 + unit)
  gl.bindTexture(gl.TEXTURE_2D, value)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
  gl.texImage2D(gl.TEXTURE_2D, 0, internalFormat, 256, 1, 0, format, gl.UNSIGNED_BYTE, bytes)
  return value
}

export function NicrainhaScene() {
  const reference = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = reference.current
    const gl = canvas?.getContext('webgl2', { antialias: false, alpha: false })
    if (!canvas || !gl) return
    const program = gl.createProgram()
    if (!program) return
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertex))
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragment))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? 'Unable to link the scene shader.')
    const permutation = buildPermutation(Math.floor(Math.random() * 99999))
    const palette = generatePalettes(256, paletteOptions)[Math.floor(Math.random() * 256)]
    const permutationTexture = texture(gl, 0, gl.R8UI, gl.RED_INTEGER, permutation)
    const paletteTexture = texture(gl, 1, gl.RGBA8, gl.RGBA, new Uint8Array(palette.flatMap(({ r, g, b }) => [r, g, b, 255])))
    const uniforms = {
      permutation: gl.getUniformLocation(program, 'u_perm'),
      palette: gl.getUniformLocation(program, 'u_palette'),
      resolution: gl.getUniformLocation(program, 'u_resolution'),
      depth: gl.getUniformLocation(program, 'u_z'),
      minimum: gl.getUniformLocation(program, 'u_min'),
      range: gl.getUniformLocation(program, 'u_range'),
      count: gl.getUniformLocation(program, 'u_count'),
      panels: gl.getUniformLocation(program, 'u_panels[0]'),
      radii: gl.getUniformLocation(program, 'u_radii[0]'),
      ior: gl.getUniformLocation(program, 'u_ior'),
      gapOffset: gl.getUniformLocation(program, 'u_gap_offset'),
    }
    gl.useProgram(program)
    gl.uniform1i(uniforms.permutation, 0)
    gl.uniform1i(uniforms.palette, 1)
    gl.uniform1f(uniforms.ior, glassIor)
    gl.uniform1f(uniforms.gapOffset, gapOffset * (window.devicePixelRatio || 1))
    const start = performance.now()
    let frame = 0
    const render = (now: number) => {
      const ratio = window.devicePixelRatio || 1
      const width = Math.round(canvas.clientWidth * ratio)
      const height = Math.round(canvas.clientHeight * ratio)
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      const elements = [...document.querySelectorAll<HTMLElement>('[data-glass-panel]')].slice(0, maximumPanels)
      const panels = new Float32Array(maximumPanels * 4)
      const radii = new Float32Array(maximumPanels)
      elements.forEach((element, index) => {
        const box = element.getBoundingClientRect()
        const radius = element.dataset.glassShape === 'circle'
          ? Math.min(box.width, box.height) / 2
          : Number.parseFloat(getComputedStyle(element).borderTopLeftRadius) || 24
        panels.set([(box.left + box.width / 2) * ratio, (box.top + box.height / 2) * ratio, box.width / 2 * ratio, box.height / 2 * ratio], index * 4)
        radii[index] = Math.min(radius * ratio, box.width / 2 * ratio, box.height / 2 * ratio)
      })
      const depth = ((now - start) / 10000) % 256
      const range = fieldRange(permutation, depth)
      gl.viewport(0, 0, width, height)
      gl.useProgram(program)
      gl.activeTexture(gl.TEXTURE0)
      gl.bindTexture(gl.TEXTURE_2D, permutationTexture)
      gl.activeTexture(gl.TEXTURE1)
      gl.bindTexture(gl.TEXTURE_2D, paletteTexture)
      gl.uniform2f(uniforms.resolution, width, height)
      gl.uniform1f(uniforms.depth, depth)
      gl.uniform1f(uniforms.minimum, range.minimum)
      gl.uniform1f(uniforms.range, range.range)
      gl.uniform1i(uniforms.count, elements.length)
      gl.uniform4fv(uniforms.panels, panels)
      gl.uniform1fv(uniforms.radii, radii)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      frame = requestAnimationFrame(render)
    }
    frame = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(frame)
      gl.deleteTexture(permutationTexture)
      gl.deleteTexture(paletteTexture)
      gl.deleteProgram(program)
    }
  }, [])
  return <canvas className="nicrainha-scene" ref={reference} aria-hidden="true" />
}
