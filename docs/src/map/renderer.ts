import { FLAT_FRAG, FLAT_VERT, POINT_FRAG, POINT_VERT, THICK_FRAG, THICK_VERT } from './shaders'

// The map's WebGL renderer, ported from expert-succotash (src/gl/renderer.ts)
// without its desire-line accumulation: polygon fills, lines as instanced
// quads with round joins (WebGL guarantees only 1px gl.LINES), and discs with
// a black ring. Buffers are uploaded only when their array changes, so a zoom
// is a transform update and a redraw.

export interface View { centerX: number; centerY: number; scaleX: number; scaleY: number }

export interface Scene {
  view: View
  pixelRatio: number
  fills: { positions: Float32Array; colors: Uint8Array } | null
  // x1,y1,x2,y2 per line, one color per line and one per endpoint (joins).
  lines: { positions: Float32Array; colors: Uint8Array; jointColors: Uint8Array; widthCssPx: number } | null
  points: { positions: Float32Array; colors: Uint8Array; radiusCssPx: number; borderCssPx: number } | null
}

function link(gl: WebGL2RenderingContext, vertexSource: string, fragmentSource: string) {
  const compile = (type: number, source: string) => {
    const shader = gl.createShader(type)!
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(`Map shader: ${gl.getShaderInfoLog(shader)}`)
    return shader
  }
  const program = gl.createProgram()
  gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource))
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource))
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(`Map program: ${gl.getProgramInfoLog(program)}`)
  return program
}

export class MapRenderer {
  private gl: WebGL2RenderingContext
  private flat: WebGLProgram
  private thick: WebGLProgram
  private disc: WebGLProgram
  private quad: WebGLBuffer
  private lineQuad: WebGLBuffer
  // One vertex array per draw path, so one path's instanced attributes never
  // leak into another's draw.
  private flatVao: WebGLVertexArrayObject
  private thickVao: WebGLVertexArrayObject
  private discVao: WebGLVertexArrayObject
  private buffers = new Map<string, { buffer: WebGLBuffer; source: ArrayBufferView | null }>()

  constructor(canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false })
    if (!gl) throw new Error('WebGL2 is not available.')
    this.gl = gl
    this.flat = link(gl, FLAT_VERT, FLAT_FRAG)
    this.thick = link(gl, THICK_VERT, THICK_FRAG)
    this.disc = link(gl, POINT_VERT, POINT_FRAG)
    this.quad = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW)
    // 0..1 along a segment and -1..1 across it.
    this.lineQuad = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.lineQuad)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, -1, 1, -1, 1, 1, 0, -1, 1, 1, 0, 1]), gl.STATIC_DRAW)
    this.flatVao = gl.createVertexArray()
    this.thickVao = gl.createVertexArray()
    this.discVao = gl.createVertexArray()
  }

  private upload(key: string, data: ArrayBufferView) {
    const gl = this.gl
    let entry = this.buffers.get(key)
    if (!entry) {
      entry = { buffer: gl.createBuffer(), source: null }
      this.buffers.set(key, entry)
    }
    if (entry.source !== data) {
      gl.bindBuffer(gl.ARRAY_BUFFER, entry.buffer)
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW)
      entry.source = data
    }
    return entry.buffer
  }

  private attribute(program: WebGLProgram, name: string, buffer: WebGLBuffer, size: number, type: number, normalized: boolean, divisor: number, stride = 0) {
    const gl = this.gl
    const location = gl.getAttribLocation(program, name)
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.enableVertexAttribArray(location)
    gl.vertexAttribPointer(location, size, type, normalized, stride, 0)
    gl.vertexAttribDivisor(location, divisor)
  }

  private transform(program: WebGLProgram, view: View) {
    const gl = this.gl
    gl.uniform2f(gl.getUniformLocation(program, 'u_center'), view.centerX, view.centerY)
    gl.uniform2f(gl.getUniformLocation(program, 'u_scale'), view.scaleX, view.scaleY)
  }

  private drawFills(positions: Float32Array, colors: Uint8Array, view: View) {
    if (!positions.length) return
    const gl = this.gl
    gl.bindVertexArray(this.flatVao)
    gl.useProgram(this.flat)
    this.transform(this.flat, view)
    this.attribute(this.flat, 'a_position', this.upload('fills:pos', positions), 2, gl.FLOAT, false, 0)
    this.attribute(this.flat, 'a_color', this.upload('fills:col', colors), 3, gl.UNSIGNED_BYTE, true, 0)
    gl.drawArrays(gl.TRIANGLES, 0, positions.length / 2)
    gl.bindVertexArray(null)
  }

  private drawLines(positions: Float32Array, colors: Uint8Array, widthCssPx: number, view: View, width: number, height: number, ratio: number) {
    if (!positions.length || widthCssPx <= 0) return
    const gl = this.gl
    gl.bindVertexArray(this.thickVao)
    gl.useProgram(this.thick)
    this.transform(this.thick, view)
    gl.uniform2f(gl.getUniformLocation(this.thick, 'u_viewportPx'), width, height)
    gl.uniform1f(gl.getUniformLocation(this.thick, 'u_halfWidthPx'), (widthCssPx * ratio) / 2)
    this.attribute(this.thick, 'a_corner', this.lineQuad, 2, gl.FLOAT, false, 0)
    this.attribute(this.thick, 'a_endpoints', this.upload('lines:pos', positions), 4, gl.FLOAT, false, 1, 16)
    this.attribute(this.thick, 'a_color', this.upload('lines:col', colors), 3, gl.UNSIGNED_BYTE, true, 1)
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, positions.length / 4)
    gl.bindVertexArray(null)
  }

  // Discs: agents (with a black ring), and the round joins where line
  // quads meet (without one).
  private drawDiscs(key: string, positions: Float32Array, colors: Uint8Array, radiusCssPx: number, borderCssPx: number, view: View, width: number, height: number, ratio: number) {
    if (!positions.length || radiusCssPx <= 0) return
    const gl = this.gl
    gl.bindVertexArray(this.discVao)
    gl.useProgram(this.disc)
    this.transform(this.disc, view)
    const outer = radiusCssPx * ratio, inner = Math.max(0, outer - borderCssPx * ratio)
    gl.uniform2f(gl.getUniformLocation(this.disc, 'u_pixelRadius'), (outer * 2) / width, (outer * 2) / height)
    gl.uniform1f(gl.getUniformLocation(this.disc, 'u_radiusPx'), outer)
    gl.uniform1f(gl.getUniformLocation(this.disc, 'u_innerRatio'), outer > 0 ? inner / outer : 1)
    this.attribute(this.disc, 'a_corner', this.quad, 2, gl.FLOAT, false, 0)
    this.attribute(this.disc, 'a_position', this.upload(`${key}:pos`, positions), 2, gl.FLOAT, false, 1)
    this.attribute(this.disc, 'a_color', this.upload(`${key}:col`, colors), 3, gl.UNSIGNED_BYTE, true, 1)
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, positions.length / 2)
    gl.bindVertexArray(null)
  }

  render(scene: Scene) {
    const gl = this.gl
    const width = gl.drawingBufferWidth, height = gl.drawingBufferHeight
    gl.viewport(0, 0, width, height)
    gl.clearColor(1, 1, 1, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)
    const { view, pixelRatio: ratio } = scene
    if (scene.fills) this.drawFills(scene.fills.positions, scene.fills.colors, view)
    if (scene.lines) {
      const { positions, colors, jointColors, widthCssPx } = scene.lines
      this.drawLines(positions, colors, widthCssPx, view, width, height, ratio)
      // A join is only visible once a line is wide enough to notch.
      if (widthCssPx >= 2) this.drawDiscs('joints', positions, jointColors, widthCssPx / 2, 0, view, width, height, ratio)
    }
    if (scene.points) {
      const { positions, colors, radiusCssPx, borderCssPx } = scene.points
      this.drawDiscs('points', positions, colors, radiusCssPx, borderCssPx, view, width, height, ratio)
    }
  }

  dispose() {
    const gl = this.gl
    for (const { buffer } of this.buffers.values()) gl.deleteBuffer(buffer)
    gl.deleteBuffer(this.quad)
    gl.deleteBuffer(this.lineQuad)
    gl.deleteVertexArray(this.flatVao)
    gl.deleteVertexArray(this.thickVao)
    gl.deleteVertexArray(this.discVao)
    gl.deleteProgram(this.flat)
    gl.deleteProgram(this.thick)
    gl.deleteProgram(this.disc)
  }
}
