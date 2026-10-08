import { generatePalettes } from 'nicrainha'

export const defaultLightness = 86
export const lightnessRingRows = 128

export function buildLightnessRings(backgroundLightness: number) {
  const rings = new Uint8Array(lightnessRingRows * 256 * 3)
  for (let row = 0; row < lightnessRingRows; row += 1) {
    const lightness = backgroundLightness + (100 - backgroundLightness) * row / (lightnessRingRows - 1)
    generatePalettes(256, { lightness })[0].forEach(({ r, g, b }, vertex) => {
      rings.set([r, g, b], (row * 256 + vertex) * 3)
    })
  }
  return rings
}
