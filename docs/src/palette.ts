import { generatePalettes } from 'nicrainha'
import type { PaletteColor } from './types'

const rotation = 37
export const continuousPalette = generatePalettes(256)[rotation] as PaletteColor[]
export const categoricalPalette = generatePalettes(12)[rotation] as PaletteColor[]

export function cssColor(color: PaletteColor, alpha = 1) {
  return `rgb(${color.r} ${color.g} ${color.b} / ${alpha})`
}

export function colorScale(value: number, values: number[]) {
  const ordered = [...values].sort((left, right) => left - right)
  const position = ordered.findIndex((candidate) => candidate >= value)
  const index = Math.round((Math.max(position, 0) / Math.max(ordered.length - 1, 1)) * 255)
  return continuousPalette[index]
}
