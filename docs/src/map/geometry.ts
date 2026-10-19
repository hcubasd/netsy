import earcut from 'earcut'
import type { Geometry, Position } from '../types'

// Everything expensive about drawing a file happens here, once per loaded
// file (ported from expert-succotash's geometryMaker): polygons are
// triangulated, lines decomposed into segments, and every coordinate written
// into the flat typed arrays a GPU buffer takes. Zooming afterwards is only a
// change of transform.
//
// Coordinates are stored relative to an origin at the data's center,
// subtracted in float64: float32 has about seven significant digits, which a
// projected coordinate in the millions would otherwise spend on magnitude.

export interface Bounds { minX: number; minY: number; maxX: number; maxY: number }
export interface Origin { x: number; y: number }

// minX, minY, maxX, maxY per row: which features are on screen, without
// touching their geometry again.
export type RowBounds = Float32Array

export interface PolygonGeometry {
  kind: 'polygons'
  rowCount: number
  fillPositions: Float32Array
  fillRowIndex: Uint32Array
  // x1,y1,x2,y2 per ring edge.
  borderPositions: Float32Array
  rowBounds: RowBounds
}

export interface SegmentGeometry {
  kind: 'segments'
  rowCount: number
  // x1,y1,x2,y2 per segment; one row index per segment.
  positions: Float32Array
  rowIndex: Uint32Array
  rowBounds: RowBounds
}

export interface PointGeometry {
  kind: 'points'
  rowCount: number
  // x,y per row; NaN where a row has no point.
  positions: Float32Array
  rowBounds: RowBounds
}

export type Prepared = (PolygonGeometry | SegmentGeometry | PointGeometry) & { origin: Origin; bounds: Bounds }

function emptyRowBounds(rowCount: number) {
  const out = new Float32Array(rowCount * 4)
  for (let row = 0; row < rowCount; row++) out.set([Infinity, Infinity, -Infinity, -Infinity], row * 4)
  return out
}

function grow(bounds: RowBounds, row: number, x: number, y: number) {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return
  if (x < bounds[row * 4]) bounds[row * 4] = x
  if (y < bounds[row * 4 + 1]) bounds[row * 4 + 1] = y
  if (x > bounds[row * 4 + 2]) bounds[row * 4 + 2] = x
  if (y > bounds[row * 4 + 3]) bounds[row * 4 + 3] = y
}

function rawBounds(geometries: (Geometry | null)[]): Bounds | null {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  const visit = ([x, y]: Position) => {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  }
  for (const geometry of geometries) {
    if (!geometry) continue
    if (geometry.type === 'Point') visit(geometry.coordinates)
    else if (geometry.type === 'LineString' || geometry.type === 'MultiPoint') geometry.coordinates.forEach(visit)
    else if (geometry.type === 'Polygon' || geometry.type === 'MultiLineString') geometry.coordinates.forEach((line) => line.forEach(visit))
    else geometry.coordinates.forEach((polygon) => polygon.forEach((ring) => ring.forEach(visit)))
  }
  return minX > maxX ? null : { minX, minY, maxX, maxY }
}

function polygonParts(geometry: Geometry | null): Position[][][] {
  if (geometry?.type === 'Polygon') return [geometry.coordinates]
  if (geometry?.type === 'MultiPolygon') return geometry.coordinates
  return []
}

function lineStrings(geometry: Geometry | null): Position[][] {
  if (geometry?.type === 'LineString') return [geometry.coordinates]
  if (geometry?.type === 'MultiLineString') return geometry.coordinates
  return []
}

function makePolygons(geometries: (Geometry | null)[], origin: Origin): PolygonGeometry {
  const fill: number[] = [], fillRow: number[] = [], border: number[] = []
  const rowBounds = emptyRowBounds(geometries.length)
  geometries.forEach((geometry, row) => {
    for (const rings of polygonParts(geometry)) {
      if (rings.length === 0) continue
      const flat: number[] = [], holes: number[] = []
      rings.forEach((ring, r) => {
        if (r > 0) holes.push(flat.length / 2)
        for (const [x, y] of ring) {
          flat.push(x - origin.x, y - origin.y)
          grow(rowBounds, row, x - origin.x, y - origin.y)
        }
        for (let i = 0; i < ring.length; i++) {
          const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length]
          border.push(x1 - origin.x, y1 - origin.y, x2 - origin.x, y2 - origin.y)
        }
      })
      for (const index of earcut(flat, holes.length ? holes : undefined, 2)) {
        fill.push(flat[index * 2], flat[index * 2 + 1])
        fillRow.push(row)
      }
    }
  })
  return {
    kind: 'polygons',
    rowCount: geometries.length,
    fillPositions: new Float32Array(fill),
    fillRowIndex: new Uint32Array(fillRow),
    borderPositions: new Float32Array(border),
    rowBounds,
  }
}

function makeSegments(geometries: (Geometry | null)[], origin: Origin): SegmentGeometry {
  const positions: number[] = [], rowIndex: number[] = []
  const rowBounds = emptyRowBounds(geometries.length)
  geometries.forEach((geometry, row) => {
    for (const line of lineStrings(geometry)) {
      for (let i = 0; i + 1 < line.length; i++) {
        const [x1, y1] = line[i], [x2, y2] = line[i + 1]
        positions.push(x1 - origin.x, y1 - origin.y, x2 - origin.x, y2 - origin.y)
        rowIndex.push(row)
        grow(rowBounds, row, x1 - origin.x, y1 - origin.y)
        grow(rowBounds, row, x2 - origin.x, y2 - origin.y)
      }
    }
  })
  return { kind: 'segments', rowCount: geometries.length, positions: new Float32Array(positions), rowIndex: new Uint32Array(rowIndex), rowBounds }
}

function makePoints(geometries: (Geometry | null)[], origin: Origin): PointGeometry {
  const positions = new Float32Array(geometries.length * 2).fill(Number.NaN)
  const rowBounds = emptyRowBounds(geometries.length)
  geometries.forEach((geometry, row) => {
    const point = geometry?.type === 'Point' ? geometry.coordinates : geometry?.type === 'MultiPoint' ? geometry.coordinates[0] : null
    if (!point) return
    positions[row * 2] = point[0] - origin.x
    positions[row * 2 + 1] = point[1] - origin.y
    grow(rowBounds, row, point[0] - origin.x, point[1] - origin.y)
  })
  return { kind: 'points', rowCount: geometries.length, positions, rowBounds }
}

// One preparation per loaded geometry list: the same file object always
// maps to the same buffers, so nothing is rebuilt until a file is reloaded.
const cache = new WeakMap<(Geometry | null)[], Prepared | null>()

export function prepare(geometries: (Geometry | null)[]): Prepared | null {
  if (cache.has(geometries)) return cache.get(geometries)!
  const bounds = rawBounds(geometries)
  let prepared: Prepared | null = null
  if (bounds) {
    const origin = { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 }
    const relative = { minX: bounds.minX - origin.x, minY: bounds.minY - origin.y, maxX: bounds.maxX - origin.x, maxY: bounds.maxY - origin.y }
    const first = geometries.find(Boolean)?.type
    const made = first === 'Polygon' || first === 'MultiPolygon' ? makePolygons(geometries, origin)
      : first === 'LineString' || first === 'MultiLineString' ? makeSegments(geometries, origin)
        : makePoints(geometries, origin)
    prepared = { ...made, origin, bounds: relative }
  }
  cache.set(geometries, prepared)
  return prepared
}
