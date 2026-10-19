import { DEFAULT_LIGHTNESS, generatePalettes } from 'nicrainha'
import type { PaletteColor } from './types'

// Data drawn on white (the map and table sheets) uses nicrainha's default
// lightness, independently of the scene's: it is the most saturated circle.
// A ramp walks half the circle, so its two ends stay distinguishable.
const rotation = 37
export const ramp = (generatePalettes(256, { lightness: DEFAULT_LIGHTNESS })[rotation] as PaletteColor[]).slice(0, 128)

export function cssColor(color: PaletteColor, alpha = 1) {
  return `rgb(${color.r} ${color.g} ${color.b} / ${alpha})`
}
