import { useCallback, useEffect, useRef, useState } from 'react'
import { DataView } from './DataView'
import cat from './assets/rolling-cat.gif'
import type { LoadRequest, LoadResponse } from './loader.worker'
import LoaderWorker from './loader.worker?worker'
import { MapView } from './MapView'
import { Scene } from './scene/Scene'
import { background, onFrame } from './scene/frames'
import { TableView } from './TableView'
import type { DataTable } from './types'
import './App.css'

// Three views side by side, as in nicolle: Map, Data and Table. Moving
// between them slides the whole interface sideways and pans the background
// with it, in the same frame.

const VIEWS = ['map', 'data', 'table'] as const
type View = (typeof VIEWS)[number]
const SLIDE_MS = 650

// CSS `ease`, cubic-bezier(.25, .1, .25, 1): solve x(u) = time, then
// evaluate y(u).
function ease(time: number) {
  if (time <= 0) return 0
  if (time >= 1) return 1
  let lo = 0, hi = 1
  for (let i = 0; i < 20; i++) {
    const u = (lo + hi) / 2, v = 1 - u, x = 3 * v * v * u * 0.25 + 3 * v * u * u * 0.25 + u * u * u
    if (x < time) lo = u
    else hi = u
  }
  const u = (lo + hi) / 2, v = 1 - u
  return 3 * v * v * u * 0.1 + 3 * v * u * u + u * u * u
}

// One loader worker for the page, answering requests by id.
let worker: Worker | undefined
let requests = 0
const pending = new Map<number, (response: LoadResponse) => void>()
function loadInWorker(file: File, name: string) {
  if (!worker) {
    worker = new LoaderWorker()
    worker.onmessage = ({ data }: MessageEvent<LoadResponse>) => {
      pending.get(data.id)?.(data)
      pending.delete(data.id)
    }
  }
  const id = ++requests
  return new Promise<LoadResponse>((resolve) => {
    pending.set(id, resolve)
    worker!.postMessage({ id, file, name } satisfies LoadRequest)
  })
}

// While a file loads: the rolling cat over the window, which does not
// respond until it is done.
function Loading() {
  return (
    <div className="loading" role="status" aria-live="polite">
      <img src={cat} alt="" />
      <p>Loading<span>.</span><span>.</span><span>.</span></p>
    </div>
  )
}

export default function App() {
  const [tables, setTables] = useState<Record<string, DataTable>>({})
  const [selected, setSelected] = useState('')
  const [view, setView] = useState<View>('map')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(0)
  const track = useRef<HTMLDivElement>(null)
  const slide = useRef({ x: 0, from: 0, to: 0, elapsed: SLIDE_MS })

  // The track's position follows the view; a change of view slides there.
  useEffect(() => {
    const motion = slide.current
    motion.from = motion.x
    motion.to = VIEWS.indexOf(view)
    motion.elapsed = matchMedia('(prefers-reduced-motion: reduce)').matches ? SLIDE_MS : 0
  }, [view])
  useEffect(() => onFrame((dt) => {
    const motion = slide.current, element = track.current
    if (!element) return false
    const moving = motion.elapsed < SLIDE_MS
    if (moving) motion.elapsed = Math.min(SLIDE_MS, motion.elapsed + Math.min(32, dt))
    motion.x = motion.from + (motion.to - motion.from) * ease(motion.elapsed / SLIDE_MS)
    const width = element.clientWidth / VIEWS.length
    const transform = `translateX(${-motion.x * width}px)`
    if (element.style.transform !== transform) element.style.transform = transform
    background.x = motion.x * width
    return moving
  }), [])

  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(''), 6000)
    return () => clearTimeout(timer)
  }, [error])

  const load = useCallback(async (name: string, file: File) => {
    setLoading((count) => count + 1)
    try {
      const response = await loadInWorker(file, name)
      if ('error' in response) throw new Error(response.error)
      const { table } = response
      setTables((current) => {
        const srs = Object.values(current).filter((other) => other.filename !== name && other.srsId !== undefined).map((other) => other.srsId)
        if (table.srsId !== undefined && srs.some((other) => other !== table.srsId)) {
          setError(`${name} uses a different CRS from the GeoPackages already loaded.`)
          return current
        }
        return { ...current, [name]: table }
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${file.name} could not be read.`)
    } finally {
      setLoading((count) => count - 1)
    }
  }, [])

  const remove = (name: string) => {
    setTables(({ [name]: _removed, ...rest }) => rest)
    setView('data')
  }

  return (
    <>
      <Scene />
      <div className="viewport" inert={loading > 0}>
        <div className="track" ref={track}>
          <MapView tables={tables} active={view === 'map'} onData={() => setView('data')} />
          <DataView tables={tables} active={view === 'data'} onMap={() => setView('map')} onLoad={load}
            onOpen={(name) => { setSelected(name); setView('table') }} />
          <TableView table={tables[selected]} active={view === 'table'} onData={() => setView('data')} onRemove={() => remove(selected)} />
        </div>
      </div>
      {error && <p className="error glass" data-glass role="alert">{error}</p>}
      {loading > 0 && <Loading />}
    </>
  )
}
