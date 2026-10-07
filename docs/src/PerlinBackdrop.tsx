import { useEffect, useRef } from 'react'
import { continuousPalette } from './palette'

const vertex = `#version 300 es
void main() {
  vec2 position = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(position * 2.0 - 1.0, 0.0, 1.0);
}`

const fragment = `#version 300 es
precision highp float;
uniform sampler2D u_palette; uniform vec2 u_resolution; uniform float u_time;
out vec4 out_color;
vec3 fade(vec3 t) { return t*t*t*(t*(t*6.0-15.0)+10.0); }
float hash(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453123); }
float grad(vec3 p, vec3 d) {
  float h = hash(p) * 6.2831853;
  vec3 g = normalize(vec3(cos(h), sin(h), cos(h * .73 + 1.2)));
  return dot(g, d);
}
float perlin(vec3 position) {
  vec3 base = floor(position); vec3 local = fract(position); vec3 f = fade(local);
  float n000=grad(base+vec3(0,0,0),local-vec3(0,0,0)), n100=grad(base+vec3(1,0,0),local-vec3(1,0,0));
  float n010=grad(base+vec3(0,1,0),local-vec3(0,1,0)), n110=grad(base+vec3(1,1,0),local-vec3(1,1,0));
  float n001=grad(base+vec3(0,0,1),local-vec3(0,0,1)), n101=grad(base+vec3(1,0,1),local-vec3(1,0,1));
  float n011=grad(base+vec3(0,1,1),local-vec3(0,1,1)), n111=grad(base+vec3(1,1,1),local-vec3(1,1,1));
  return mix(mix(mix(n000,n100,f.x),mix(n010,n110,f.x),f.y),mix(mix(n001,n101,f.x),mix(n011,n111,f.x),f.y),f.z);
}
void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution;
  vec2 field = (uv - .5) * vec2(u_resolution.x / u_resolution.y, 1.0) * 4.0;
  float noise = perlin(vec3(field, u_time * .1)) * .5 + .5;
  vec3 colour = texelFetch(u_palette, ivec2(int(noise * 255.0), 0), 0).rgb;
  out_color = vec4(colour, 1.0);
}`

function shader(gl: WebGL2RenderingContext, type: number, source: string) {
  const value = gl.createShader(type)
  if (!value) throw new Error('Unable to allocate a WebGL shader.')
  gl.shaderSource(value, source)
  gl.compileShader(value)
  return value
}

export function PerlinBackdrop() {
  const reference = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = reference.current
    const gl = canvas?.getContext('webgl2', { antialias: false, alpha: false })
    if (!canvas || !gl) return
    const program = gl.createProgram()
    if (!program) return
    gl.attachShader(program, shader(gl, gl.VERTEX_SHADER, vertex))
    gl.attachShader(program, shader(gl, gl.FRAGMENT_SHADER, fragment))
    gl.linkProgram(program)
    const texture = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
    const bytes = new Uint8Array(continuousPalette.flatMap(({ r, g, b }) => [r, g, b, 255]))
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, bytes)
    let frame = 0
    const render = (time: number) => {
      const ratio = window.devicePixelRatio || 1
      const width = Math.round(canvas.clientWidth * ratio)
      const height = Math.round(canvas.clientHeight * ratio)
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      gl.viewport(0, 0, width, height)
      gl.useProgram(program)
      gl.activeTexture(gl.TEXTURE0)
      gl.bindTexture(gl.TEXTURE_2D, texture)
      gl.uniform1i(gl.getUniformLocation(program, 'u_palette'), 0)
      gl.uniform2f(gl.getUniformLocation(program, 'u_resolution'), width, height)
      gl.uniform1f(gl.getUniformLocation(program, 'u_time'), time / 1000)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      frame = requestAnimationFrame(render)
    }
    frame = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(frame)
      gl.deleteTexture(texture)
      gl.deleteProgram(program)
    }
  }, [])
  return <canvas ref={reference} className="perlin-backdrop" aria-hidden="true" />
}
