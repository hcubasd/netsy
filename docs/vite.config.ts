import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { buildLightnessRings, defaultLightness, lightnessRingRows } from './src/lightnessRings.js'

function lightnessRings() {
  const rgb = Buffer.from(buildLightnessRings(defaultLightness)).toString('base64')
  const id = 'virtual:lightness-rings'
  return {
    name: 'lightness-rings',
    resolveId: (source: string) => source === id ? `\0${id}` : null,
    load: (resolved: string) => resolved === `\0${id}`
      ? `export const baseLightness = ${defaultLightness}; export const rows = ${lightnessRingRows}; export const rgb = "${rgb}";`
      : null,
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), lightnessRings()],
  base: './',
})
