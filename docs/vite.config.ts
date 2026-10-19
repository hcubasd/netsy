import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { tables } from './scripts/tables.js'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tables()],
  base: './',
})
