import { useEffect, useMemo, useRef, useState } from 'react'
import { layoutCircuit } from './circuit'
import { titleCase, viewable } from './files'
import { background, onFrame } from './scene/frames'
import { Pan } from './scene/pan'
import type { DataTable } from './types'

// The data-flow graph: one bubble per NetSy file, wired top to bottom as a
// circuit that pans both ways when it outgrows the window, fading under the
// banner. A loaded file opens its table; any other file asks for it.

const pan = new Pan()

export function DataView({ tables, active, onMap, onLoad, onOpen }: {
  tables: Record<string, DataTable>
  active: boolean
  onMap: () => void
  onLoad: (name: string, file: File) => void
  onOpen: (name: string) => void
}) {
  const region = useRef<HTMLDivElement>(null)
  const world = useRef<HTMLDivElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  const target = useRef('')
  const [width, setWidth] = useState(0)
  const circuit = useMemo(() => (width ? layoutCircuit(width) : null), [width])

  useEffect(() => {
    const element = region.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const element = region.current
    if (!element || !circuit) return
    pan.setBounds(() => ({ minX: 0, maxX: circuit.width - element.clientWidth, minY: 0, maxY: circuit.height - element.clientHeight }))
    const detach = pan.attach(element)
    const stop = onFrame((dt) => {
      const moved = pan.step(dt)
      if (moved && world.current) world.current.style.transform = `translate(${-pan.x}px, ${-pan.y}px)`
      background.x = pan.x
      background.y = pan.y
      return moved
    })
    return () => {
      detach()
      stop()
    }
  }, [circuit])

  const choose = (name: string) => {
    if (tables[name]) return onOpen(name)
    target.current = name
    const input = picker.current!
    input.accept = name.endsWith('.gpkg') ? '.gpkg' : '.csv'
    input.value = ''
    input.click()
  }

  return (
    <section className="view data-view" inert={!active}>
      <header className="banner">
        <button type="button" className="bubble glass" data-glass onClick={onMap}>Map</button>
      </header>
      <div className="data-region" ref={region} data-glass-clip tabIndex={0} aria-label="NetSy data files">
        {circuit && <div className="circuit" ref={world} style={{ width: circuit.width, height: circuit.height }}>
          <svg className="wires" width={circuit.width} height={circuit.height} aria-hidden="true">
            {circuit.wires.map((wire, index) => <line key={index} {...wire} />)}
          </svg>
          {circuit.nodes.map((node) => (
            <button key={node.id} type="button" className={`file glass ${tables[node.id] ? 'loaded' : ''}`} data-glass
              style={{ left: node.x, top: node.y, ...circuit.bubble }}
              disabled={!viewable(node.id)} aria-label={`${titleCase(node.id)} (${node.id})`} onClick={() => choose(node.id)}>
              <span>{titleCase(node.id)}</span>
            </button>
          ))}
        </div>}
      </div>
      <input ref={picker} type="file" hidden onChange={(event) => {
        const file = event.target.files?.[0]
        if (file) onLoad(target.current, file)
      }} />
    </section>
  )
}
