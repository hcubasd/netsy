import { useCallback, useImperativeHandle, useLayoutEffect, useRef, useState, type Ref } from 'react'
import type { Bounds, Prepared } from './map/geometry'
import { MapRenderer, type View } from './map/renderer'
import { buildScene, type Legend } from './map/scene'

// The map in its white sheet, as in expert-succotash: drag a rectangle, in
// the sheet's own proportions, to zoom exactly into it; back() zooms out one
// step and reset() shows everything again (the banner's Zoom out and Reset
// zoom). There is
// no panning, and nothing is drawn except when the data, the view or a
// control changes.

const FIT_PADDING = 0.92
const MIN_DRAG_PX = 4

function fitView(bounds: Bounds, width: number, height: number, padding = FIT_PADDING): View {
  const worldWidth = Math.max(bounds.maxX - bounds.minX, 1e-9), worldHeight = Math.max(bounds.maxY - bounds.minY, 1e-9)
  // One scale for both axes, so the map never distorts.
  const scale = Math.min(width / worldWidth, height / worldHeight) * padding
  return { centerX: (bounds.minX + bounds.maxX) / 2, centerY: (bounds.minY + bounds.maxY) / 2, scaleX: (scale * 2) / width, scaleY: (scale * 2) / height }
}

// A view keeps the same ground in sight across a resize: its world extent
// is 1/scale, so only the aspect changes.
function refit(view: View, width: number, height: number): View {
  const extent = Math.min(1 / view.scaleX, 1 / view.scaleY)
  return fitView({ minX: view.centerX - extent, maxX: view.centerX + extent, minY: view.centerY - extent, maxY: view.centerY + extent }, width, height)
}

interface Drag { x0: number; y0: number; x1: number; y1: number }

const NO_ZOOMS: Zoom[] = []

export interface MapControls { back: () => void; reset: () => void }

// The zooms that Back undoes, newest last, for the geometry they were made
// on. Owned by the map's parent, which shows Back only when there are some.
export interface ZoomHistory { prepared: Prepared | null; views: Zoom[]; zoomed: boolean }

// A view Back can return to, and whether it was zoomed in.
interface Zoom { view: View; zoomed: boolean }

export function MapCanvas({ active, prepared, values, lineWidth, onLegend, history, onHistory, ref }: {
  // The map draws only while its view is shown.
  active: boolean
  prepared: Prepared
  values: Float64Array | null
  lineWidth: number
  onLegend: (legend: Legend | null) => void
  history: ZoomHistory
  onHistory: (history: ZoomHistory) => void
  ref: Ref<MapControls>
}) {
  const renderer = useRef<MapRenderer | null>(null)
  const view = useRef<View | null>(null)
  const fitted = useRef<{ prepared: Prepared; width: number; height: number } | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0, ratio: 1 })
  const [version, setVersion] = useState(0)
  const own = history.prepared === prepared
  const past = own ? history.views : NO_ZOOMS
  // A new file starts at its full extent, which is not zoomed.
  const zoomed = own && history.zoomed
  const [drag, setDrag] = useState<Drag | null>(null)
  const [failed, setFailed] = useState('')

  // The canvas brings its renderer and its size with it.
  const attach = useCallback((element: HTMLCanvasElement | null) => {
    if (!element) return
    try {
      renderer.current = new MapRenderer(element)
    } catch (error) {
      setFailed(error instanceof Error ? error.message : String(error))
    }
    const measure = () => {
      const ratio = window.devicePixelRatio || 1
      const width = Math.max(1, Math.round(element.clientWidth * ratio)), height = Math.max(1, Math.round(element.clientHeight * ratio))
      if (element.width === width && element.height === height) return
      element.width = width
      element.height = height
      setSize({ width, height, ratio })
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => {
      observer.disconnect()
      renderer.current?.dispose()
      renderer.current = null
    }
  }, [])

  // Drawn whenever the data, a control, the view or the size changes. New
  // geometry starts at its full extent; a resize keeps what was in view.
  useLayoutEffect(() => {
    if (!active || !renderer.current || !size.width) return
    const last = fitted.current
    if (!view.current || last?.prepared !== prepared) view.current = fitView(prepared.bounds, size.width, size.height)
    else if (last.width !== size.width || last.height !== size.height) view.current = refit(view.current, size.width, size.height)
    fitted.current = { prepared, width: size.width, height: size.height }
    const { scene, legend } = buildScene(prepared, values, view.current, size.ratio, lineWidth)
    renderer.current.render(scene)
    onLegend(legend)
  }, [active, prepared, values, size, version, lineWidth, onLegend])

  // Drags are kept in CSS px from the canvas's top-left corner.
  const local = (event: React.PointerEvent) => {
    const box = event.currentTarget.getBoundingClientRect()
    return { x: event.clientX - box.left, y: event.clientY - box.top }
  }
  const toWorld = (x: number, y: number) => {
    const current = view.current!
    const scale = (current.scaleX * size.width) / 2
    const px = x * size.ratio - size.width / 2, py = y * size.ratio - size.height / 2
    return { x: current.centerX + px / scale, y: current.centerY - py / scale }
  }

  const zoom = (next: View) => {
    const previous = view.current
    onHistory({ prepared, views: previous ? [...past, { view: previous, zoomed }] : past, zoomed: true })
    view.current = next
    setVersion((value) => value + 1)
  }
  useImperativeHandle(ref, () => ({
    back: () => {
      if (!past.length) return
      const last = past[past.length - 1]
      view.current = last.view
      onHistory({ prepared, views: past.slice(0, -1), zoomed: last.zoomed })
      setVersion((value) => value + 1)
    },
    // Only a zoomed map has anything to reset, and resetting forgets the
    // zooms: there is nothing left to zoom out of.
    reset: () => {
      if (!size.width || !zoomed || !view.current) return
      onHistory({ prepared, views: [], zoomed: false })
      view.current = fitView(prepared.bounds, size.width, size.height)
      setVersion((value) => value + 1)
    },
  }), [past, zoomed, prepared, size, onHistory])

  // A drag grows in the sheet's own proportions from where it started, so
  // it zooms to exactly the rectangle drawn.
  const corner = (x0: number, y0: number, x: number, y: number) => {
    const aspect = size.width / size.height || 1
    const width = Math.max(Math.abs(x - x0), Math.abs(y - y0) * aspect)
    return { x1: x0 + Math.sign(x - x0 || 1) * width, y1: y0 + Math.sign(y - y0 || 1) * (width / aspect) }
  }

  return (
    <div className="map-frame">
      <canvas ref={attach} className="map-canvas"
        onPointerDown={(event) => {
          if (event.button !== 0) return
          event.currentTarget.setPointerCapture(event.pointerId)
          const { x, y } = local(event)
          setDrag({ x0: x, y0: y, x1: x, y1: y })
        }}
        onPointerMove={(event) => {
          const { x, y } = local(event)
          setDrag((current) => current && { ...current, ...corner(current.x0, current.y0, x, y) })
        }}
        onPointerUp={() => {
          const current = drag
          setDrag(null)
          if (!current || Math.abs(current.x1 - current.x0) < MIN_DRAG_PX || Math.abs(current.y1 - current.y0) < MIN_DRAG_PX) return
          const a = toWorld(current.x0, current.y0), b = toWorld(current.x1, current.y1)
          zoom(fitView({ minX: Math.min(a.x, b.x), maxX: Math.max(a.x, b.x), minY: Math.min(a.y, b.y), maxY: Math.max(a.y, b.y) }, size.width, size.height, 1))
        }}
        onPointerCancel={() => setDrag(null)}
      />
      {drag && <div className="zoom-box" style={{
        left: Math.min(drag.x0, drag.x1), top: Math.min(drag.y0, drag.y1),
        width: Math.abs(drag.x1 - drag.x0), height: Math.abs(drag.y1 - drag.y0),
      }} />}
      {failed && <p className="map-failed">{failed}</p>}
    </div>
  )
}
