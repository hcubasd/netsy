import { generatePalettes } from 'nicrainha'
import { defaultLightness } from './lightnessRings'
import type { PaletteColor } from './types'

const rotation = 37
const lightnessParameter = new URLSearchParams(window.location.search).get('lightness')
const requestedLightness = lightnessParameter === null ? Number.NaN : Number(lightnessParameter)
export const backgroundLightness = Number.isFinite(requestedLightness) && requestedLightness >= 0 && requestedLightness <= 100
  ? requestedLightness
  : defaultLightness
export const paletteOptions = { lightness: backgroundLightness }
export const continuousPalette = generatePalettes(256, paletteOptions)[rotation] as PaletteColor[]
export const categoricalPalette = generatePalettes(12, paletteOptions)[rotation] as PaletteColor[]

export function cssColor(color: PaletteColor, alpha = 1) {
  return `rgb(${color.r} ${color.g} ${color.b} / ${alpha})`
}
