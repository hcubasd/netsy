import { DEFAULT_LIGHTNESS } from 'nicrainha'
import { ramp } from '../palette'
import type { PaletteColor } from '../types'
import { equalize, type Equalizer } from './equalize'
import type { Bounds, Prepared } from './geometry'
import type { Scene, View } from './renderer'

// One frame's worth of map, from prepared geometry and one value per row
// (NaN where a row has none), following expert-succotash's mapScene:
//   - colors are equalized over the rows on screen, so the ramp is spent on
//     what can be seen, and the legend labels its ticks with real values;
//   - every vertex and every point is drawn as it is in the file.

export const LEGEND_TICKS = 5
export interface Legend { ramp: PaletteColor[]; ticks: { t: number; value: number }[] }

// Neutral gray at the data lightness: a feature with nothing to color by.
const neutral = (() => {
  const y = ((DEFAULT_LIGHTNESS + 16) / 116) ** 3
  const v = Math.round(255 * (y <= 0.0031308 ? 12.92 * y : 1.055 * y ** (1 / 2.4) - 0.055))
  return { r: v, g: v, b: v }
})()
const black = { r: 0, g: 0, b: 0 }

export const viewportOf = (view: View): Bounds => ({
  minX: view.centerX - 1 / view.scaleX, maxX: view.centerX + 1 / view.scaleX,
  minY: view.centerY - 1 / view.scaleY, maxY: view.centerY + 1 / view.scaleY,
})

function visible(bounds: Float32Array, row: number, viewport: Bounds) {
  const minX = bounds[row * 4], minY = bounds[row * 4 + 1], maxX = bounds[row * 4 + 2], maxY = bounds[row * 4 + 3]
  return Number.isFinite(minX) && maxX >= viewport.minX && minX <= viewport.maxX && maxY >= viewport.minY && minY <= viewport.maxY
}

function colorer(values: Float64Array | null, prepared: Prepared, viewport: Bounds) {
  if (!values) return { color: () => null, equalizer: null }
  const onScreen: number[] = []
  for (let row = 0; row < prepared.rowCount; row++) if (Number.isFinite(values[row]) && visible(prepared.rowBounds, row, viewport)) onScreen.push(values[row])
  const equalizer = equalize(onScreen)
  const color = (row: number): PaletteColor | null => {
    const value = values[row]
    if (!Number.isFinite(value)) return null
    return ramp[Math.min(ramp.length - 1, Math.max(0, Math.round(equalizer.at(value) * (ramp.length - 1))))]
  }
  return { color, equalizer: equalizer.count ? equalizer : null }
}

function legendOf(equalizer: Equalizer | null): Legend | null {
  if (!equalizer) return null
  return { ramp, ticks: Array.from({ length: LEGEND_TICKS }, (_, i) => ({ t: i / (LEGEND_TICKS - 1), value: equalizer.valueAt(i / (LEGEND_TICKS - 1)) })) }
}

function write(target: Uint8Array, at: number, color: PaletteColor) {
  target[at * 3] = color.r
  target[at * 3 + 1] = color.g
  target[at * 3 + 2] = color.b
}

export function buildScene(prepared: Prepared, values: Float64Array | null, view: View, pixelRatio: number, lineWidth: number) {
  const viewport = viewportOf(view)
  const { color, equalizer } = colorer(values, prepared, viewport)
  const scene: Scene = { view, pixelRatio, fills: null, lines: null, points: null }

  if (prepared.kind === 'polygons') {
    const { fillPositions, fillRowIndex: fillRow, borderPositions } = prepared
    const fills = new Uint8Array(fillPositions.length / 2 * 3)
    for (let vertex = 0; vertex < fillPositions.length / 2; vertex++) write(fills, vertex, color(fillRow[vertex]) ?? neutral)
    scene.fills = { positions: fillPositions, colors: fills }
    scene.lines = { positions: borderPositions, colors: new Uint8Array(borderPositions.length / 4 * 3), jointColors: new Uint8Array(borderPositions.length / 2 * 3), widthCssPx: lineWidth }
  } else if (prepared.kind === 'segments') {
    const count = prepared.positions.length / 4
    const colors = new Uint8Array(count * 3), joints = new Uint8Array(count * 6)
    for (let segment = 0; segment < count; segment++) {
      const value = color(prepared.rowIndex[segment]) ?? black
      write(colors, segment, value)
      write(joints, segment * 2, value)
      write(joints, segment * 2 + 1, value)
    }
    scene.lines = { positions: prepared.positions, colors, jointColors: joints, widthCssPx: lineWidth }
  } else {
    // Every point, as a circle sized by the line width, with a black ring.
    const positions = prepared.positions, colors = new Uint8Array(prepared.rowCount * 3)
    for (let row = 0; row < prepared.rowCount; row++) write(colors, row, color(row) ?? neutral)
    scene.points = { positions, colors, radiusCssPx: 4 + lineWidth, borderCssPx: 1 }
  }
  return { scene, legend: legendOf(equalizer) }
}
