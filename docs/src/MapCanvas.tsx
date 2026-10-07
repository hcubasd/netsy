import { useEffect, useMemo, useRef, useState } from 'react'
import { continuousPalette } from './palette'
import type { Geometry, Position, ValueFeature } from './types'

interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

function positions(geometry: Geometry): Position[] {
  if (geometry.type === 'Point') return [geometry.coordinates]
  if (geometry.type === 'LineString') return geometry.coordinates
  if (geometry.type === 'Polygon') return geometry.coordinates.flat()
  if (geometry.type === 'MultiPoint') return geometry.coordinates
  if (geometry.type === 'MultiLineString') return geometry.coordinates.flat()
  return geometry.coordinates.flat(2)
}

function geometryLines(geometry: Geometry) {
  if (geometry.type === 'LineString') return [geometry.coordinates]
  if (geometry.type === 'Polygon') return geometry.coordinates
  if (geometry.type === 'MultiLineString') return geometry.coordinates
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flat()
  return []
}

function geometryPoints(geometry: Geometry) {
  if (geometry.type === 'Point') return [geometry.coordinates]
  if (geometry.type === 'MultiPoint') return geometry.coordinates
  return []
}

function boundsOf(features: ValueFeature[]): Bounds {
  const coordinates = features.flatMap((feature) => positions(feature.geometry))
  const xs = coordinates.map(([x]) => x)
  const ys = coordinates.map(([, y]) => y)
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }
}

function simplify(points: Position[], tolerance: number): Position[] {
  if (points.length < 3 || tolerance === 0) return points
  const first = points[0]
  const last = points.at(-1) as Position
  const distance = (point: Position) => {
    const dx = last[0] - first[0]
    const dy = last[1] - first[1]
    const denominator = dx * dx + dy * dy
    if (denominator === 0) return Math.hypot(point[0] - first[0], point[1] - first[1])
    const ratio = Math.max(0, Math.min(1, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / denominator))
    return Math.hypot(point[0] - (first[0] + ratio * dx), point[1] - (first[1] + ratio * dy))
  }
  let index = 0
  let maximum = 0
  points.slice(1, -1).forEach((point, pointIndex) => {
    const value = distance(point)
    if (value > maximum) {
      maximum = value
      index = pointIndex + 1
    }
  })
  return maximum > tolerance
    ? [...simplify(points.slice(0, index + 1), tolerance).slice(0, -1), ...simplify(points.slice(index), tolerance)]
    : [first, last]
}

const vertex = `#version 300 es
in vec2 a_position; in vec4 a_color; uniform float u_size; out vec4 v_color;
void main() { gl_Position = vec4(a_position, 0.0, 1.0); gl_PointSize = u_size; v_color = a_color; }`
const fragment = `#version 300 es
precision highp float; in vec4 v_color; out vec4 out_color;
void main() { out_color = v_color; }`

function program(gl: WebGL2RenderingContext) {
  const compile = (type: number, source: string) => {
    const shader = gl.createShader(type)
    if (!shader) throw new Error('WebGL shader allocation failed.')
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    return shader
  }
  const result = gl.createProgram()
  if (!result) throw new Error('WebGL program allocation failed.')
  gl.attachShader(result, compile(gl.VERTEX_SHADER, vertex))
  gl.attachShader(result, compile(gl.FRAGMENT_SHADER, fragment))
  gl.linkProgram(result)
  return result
}

function paletteColor(value: number | null, sortedValues: number[]) {
  if (value === null) return [.45, .45, .45, .45]
  let lower = 0
  let upper = sortedValues.length
  while (lower < upper) {
    const middle = Math.floor((lower + upper) / 2)
    if (sortedValues[middle] < value) lower = middle + 1
    else upper = middle
  }
  const color = continuousPalette[Math.round(lower / Math.max(sortedValues.length - 1, 1) * 255)]
  return [color.r / 255, color.g / 255, color.b / 255, .9]
}

interface Resources {
  gl: WebGL2RenderingContext
  program: WebGLProgram
  buffer: WebGLBuffer
  position: number
  color: number
  size: WebGLUniformLocation | null
}

export function MapCanvas({
  features,
  lineWidth,
  simplification,
}: {
  features: ValueFeature[]
  lineWidth: number
  simplification: number
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [camera, setCamera] = useState({ x: 0, y: 0, zoom: 1 })
  const drag = useRef<{ x: number; y: number } | null>(null)
  const resources = useRef<Resources | null>(null)
  const bounds = useMemo(() => (features.length ? boundsOf(features) : null), [features])
  const sortedValues = useMemo(
    () => features.flatMap((feature) => feature.value === null ? [] : [feature.value]).sort((left, right) => left - right),
    [features],
  )

  useEffect(() => () => {
    const current = resources.current
    if (!current) return
    current.gl.deleteBuffer(current.buffer)
    current.gl.deleteProgram(current.program)
    resources.current = null
  }, [])

  useEffect(() => {
    const element = canvas.current
    if (!element || !bounds) return
    const gl = element.getContext('webgl2', { antialias: true, alpha: true })
    if (!gl) return
    const resize = () => {
      const ratio = window.devicePixelRatio || 1
      element.width = Math.round(element.clientWidth * ratio)
      element.height = Math.round(element.clientHeight * ratio)
      gl.viewport(0, 0, element.width, element.height)
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    const render = () => {
      resize()
      const width = element.width
      const height = element.height
      const aspect = width / height
      const span = Math.max((bounds.maxX - bounds.minX) / aspect, bounds.maxY - bounds.minY, 1e-9) / camera.zoom
      const centreX = (bounds.minX + bounds.maxX) / 2 + camera.x
      const centreY = (bounds.minY + bounds.maxY) / 2 + camera.y
      const screen = ([x, y]: Position): Position => [
        ((x - centreX) / (span * aspect) + .5) * width,
        (.5 - (y - centreY) / span) * height,
      ]
      const clip = ([x, y]: Position): Position => [x / width * 2 - 1, 1 - y / height * 2]
      const vertices: number[] = []
      const append = (point: Position, color: number[]) => vertices.push(...clip(point), ...color)
      const colorOf = (value: number | null) => paletteColor(value, sortedValues)
      const diagonal = Math.hypot(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY)
      for (const feature of features) {
        const color = colorOf(feature.value)
        for (const line of geometryLines(feature.geometry)) {
          const points = simplify(line, diagonal * simplification).map(screen)
          for (let index = 0; index < points.length - 1; index += 1) {
            const [ax, ay] = points[index]
            const [bx, by] = points[index + 1]
            const length = Math.hypot(bx - ax, by - ay) || 1
            const nx = (by - ay) / length * lineWidth * (window.devicePixelRatio || 1) / 2
            const ny = (ax - bx) / length * lineWidth * (window.devicePixelRatio || 1) / 2
            const a: Position = [ax + nx, ay + ny]
            const b: Position = [ax - nx, ay - ny]
            const c: Position = [bx + nx, by + ny]
            const d: Position = [bx - nx, by - ny]
            append(a, color); append(b, color); append(c, color)
            append(b, color); append(d, color); append(c, color)
          }
        }
      }
      const draws = new Float32Array(vertices)
      let resource = resources.current
      if (!resource || resource.gl !== gl) {
        const activeProgram = program(gl)
        const activeBuffer = gl.createBuffer()
        if (!activeBuffer) throw new Error('WebGL buffer allocation failed.')
        resource = {
          gl,
          program: activeProgram,
          buffer: activeBuffer,
          position: gl.getAttribLocation(activeProgram, 'a_position'),
          color: gl.getAttribLocation(activeProgram, 'a_color'),
          size: gl.getUniformLocation(activeProgram, 'u_size'),
        }
        resources.current = resource
      }
      gl.clearColor(1, 1, 1, .7)
      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.useProgram(resource.program)
      gl.enable(gl.BLEND)
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
      gl.bindBuffer(gl.ARRAY_BUFFER, resource.buffer)
      gl.bufferData(gl.ARRAY_BUFFER, draws, gl.STREAM_DRAW)
      gl.enableVertexAttribArray(resource.position)
      gl.vertexAttribPointer(resource.position, 2, gl.FLOAT, false, 24, 0)
      gl.enableVertexAttribArray(resource.color)
      gl.vertexAttribPointer(resource.color, 4, gl.FLOAT, false, 24, 8)
      gl.uniform1f(resource.size, Math.max(5, lineWidth * 2) * (window.devicePixelRatio || 1))
      gl.drawArrays(gl.TRIANGLES, 0, draws.length / 6)
      const points: number[] = []
      for (const feature of features) {
        const colorValue = colorOf(feature.value)
        for (const point of geometryPoints(feature.geometry)) points.push(...clip(screen(point)), ...colorValue)
      }
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STREAM_DRAW)
      gl.drawArrays(gl.POINTS, 0, points.length / 6)
    }
    render()
    return () => observer.disconnect()
  }, [bounds, camera, features, lineWidth, simplification, sortedValues])

  if (!bounds) return <div className="empty-state">Load geometry and a matching table to render the map.</div>
  return (
    <canvas
      ref={canvas}
      className="map-canvas"
      aria-label="Interactive WebGL map"
      onWheel={(event) => {
        event.preventDefault()
        setCamera((current) => ({ ...current, zoom: Math.min(24, Math.max(.5, current.zoom * (event.deltaY > 0 ? .86 : 1.16))) }))
      }}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = { x: event.clientX, y: event.clientY }
      }}
      onPointerMove={(event) => {
        if (!drag.current || !bounds) return
        const dx = event.clientX - drag.current.x
        const dy = event.clientY - drag.current.y
        drag.current = { x: event.clientX, y: event.clientY }
        const span = Math.max((bounds.maxX - bounds.minX) / Math.max(event.currentTarget.clientWidth / event.currentTarget.clientHeight, 1), bounds.maxY - bounds.minY) / camera.zoom
        setCamera((current) => ({ ...current, x: current.x - dx / event.currentTarget.clientWidth * span * event.currentTarget.clientWidth / event.currentTarget.clientHeight, y: current.y + dy / event.currentTarget.clientHeight * span }))
      }}
      onPointerUp={() => { drag.current = null }}
    />
  )
}
