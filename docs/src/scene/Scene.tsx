import { useEffect, useRef } from 'react'
import { createRenderer, type GlassPanel } from '../engine/renderer.js'
import { advance, background } from './frames'

// The scene's lightness: the background and every glass panel.
export const LIGHTNESS = 87

// The full-window nicrainha background, seen through every [data-glass]
// element, as in nicolle: panels are measured in page order (a later panel is
// on top), share the --radius corner radius, and a panel inside a
// [data-glass-clip] region is clipped to it and fades out under its top
// edge. A frame is drawn when something moved, and otherwise at the
// animation's own pace, capped at 30 fps.

const root = document.documentElement
const MAX_PANELS = 160  // the renderer's limit

function collectPanels(radius: number, into: GlassPanel[]) {
  into.length = 0
  const width = window.innerWidth, height = window.innerHeight
  for (const element of document.querySelectorAll<HTMLElement>('[data-glass]')) {
    const box = element.getBoundingClientRect()
    if (box.width <= 0 || box.height <= 0 || box.right < 0 || box.bottom < 0 || box.left > width || box.top > height) continue
    if (!element.checkVisibility({ visibilityProperty: true })) continue
    const region = element.parentElement?.closest<HTMLElement>('[data-glass-clip]')?.getBoundingClientRect()
    if (region && (box.bottom < region.top || box.top > region.bottom || box.right < region.left || box.left > region.right)) continue
    into.push({
      x: box.left + box.width / 2,
      y: box.top + box.height / 2,
      halfWidth: box.width / 2,
      halfHeight: box.height / 2,
      radius: Math.min(radius, box.width / 2, box.height / 2),
      clip: region && { x: region.left, y: region.top, width: region.width, height: region.height },
    })
    if (into.length === MAX_PANELS) break
  }
  return into
}


export function Scene() {
  const reference = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = reference.current
    if (!canvas) return
    let renderer: ReturnType<typeof createRenderer> | undefined
    try {
      renderer = createRenderer(canvas, LIGHTNESS)
      root.style.setProperty('--paper', renderer.themeColor)
      root.classList.remove('no-webgl')
    } catch (error) {
      root.classList.add('no-webgl')
      console.warn('WebGL fallback:', error)
    }
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const frozen = performance.now()
    // Animation alone redraws at most this often: the noise drifts slowly
    // enough that 30 fps is smooth. Moving content redraws every frame.
    const animationInterval = Math.max(renderer?.interval ?? 0, 1000 / 30)
    const panels: GlassPanel[] = []
    let frame = 0, lastFrame = performance.now(), lastDraw = -Infinity, lastPan = ''
    // Panels are measured only when something may have moved them: content
    // moved this frame, the page's structure or classes changed, or a size
    // or font changed. Styles moved by the frame loop itself are reported
    // through advance(), so style mutations are not watched.
    let stale = true, radius = 0, glassLength = 0
    const invalidate = () => { stale = true }
    const resize = new ResizeObserver(invalidate)
    resize.observe(canvas)
    resize.observe(document.body)
    const mutations = new MutationObserver(invalidate)
    mutations.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden', 'inert', 'data-glass'] })
    document.fonts?.addEventListener('loadingdone', invalidate)
    window.addEventListener('resize', invalidate)
    document.addEventListener('scroll', invalidate, true)
    const render = (now: number) => {
      const dt = Math.min(64, now - lastFrame)
      lastFrame = now
      const moved = advance(dt)
      if (moved) stale = true
      const pan = `${background.x},${background.y}`
      const remeasure = stale
      if (stale) {
        const style = getComputedStyle(root)
        radius = Number.parseFloat(style.getPropertyValue('--radius')) || 0
        glassLength = 8 * Number.parseFloat(style.fontSize)
        collectPanels(radius, panels)
        stale = false
      }
      const due = !reduced.matches && now - lastDraw >= animationInterval - dt / 2
      if (renderer && !document.hidden && (remeasure || pan !== lastPan || due)) {
        renderer.draw(reduced.matches ? frozen : now, { pan: background, panels, glassLength })
        lastDraw = now
        lastPan = pan
      }
      frame = requestAnimationFrame(render)
    }
    frame = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(frame)
      resize.disconnect()
      mutations.disconnect()
      document.fonts?.removeEventListener('loadingdone', invalidate)
      window.removeEventListener('resize', invalidate)
      document.removeEventListener('scroll', invalidate, true)
      renderer?.dispose()
    }
  }, [])
  return <canvas className="scene" ref={reference} aria-hidden="true" />
}
