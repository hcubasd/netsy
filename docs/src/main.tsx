import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/comfortaa/latin-400.css'
import '@fontsource/comfortaa/latin-500.css'
import '@fontsource/comfortaa/latin-600.css'
import '@fontsource/comfortaa/latin-700.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
