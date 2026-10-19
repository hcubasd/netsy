import { useEffect, useMemo, useRef, useState } from 'react'
import { onFrame } from './scene/frames'
import { Pan } from './scene/pan'
import type { Cell, DataTable } from './types'

// A loaded file's rows in a white sheet, panned in both directions (drag,
// fling, wheel or arrow keys) with the header row pinned. Only the rows in
// view are rendered, so a file of any length pans smoothly. Cells are
// monospace, so a column's width is exact in characters.

const ROW = 28          // px, one row
const MAX_CHARS = 48    // widest column, in characters
const PAD_CHARS = 3     // a cell's padding, in characters
const valueString = (value: Cell | undefined) => value === null || value === undefined ? '' : String(value)
const numeric = (value: Cell | undefined) => typeof value === 'number' && Number.isFinite(value)

export function TableView({ table, active, onData, onRemove }: {
  table: DataTable | undefined
  active: boolean
  onData: () => void
  onRemove: () => void
}) {
  const frame = useRef<HTMLDivElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const head = useRef<HTMLDivElement>(null)
  const [pan] = useState(() => new Pan())
  const [first, setFirst] = useState(0)
  const [visible, setVisible] = useState(40)

  // Column widths, in characters: the widest of the header and every value.
  const widths = useMemo(() => table?.columns.map((column) => {
    let widest = column.length
    for (const row of table.rows) widest = Math.max(widest, valueString(row[column]).length)
    return Math.min(widest, MAX_CHARS) + PAD_CHARS
  }) ?? [], [table])
  const template = widths.map((width) => `${width}ch`).join(' ')
  const width = `${widths.reduce((total, value) => total + value, 0)}ch`

  useEffect(() => {
    const element = frame.current
    if (!element || !table) return
    pan.set(0, 0)
    pan.setBounds(() => ({
      minX: 0, maxX: (body.current?.offsetWidth ?? 0) - element.clientWidth,
      minY: 0, maxY: table.rows.length * ROW - (element.clientHeight - (head.current?.offsetHeight ?? 0)),
    }))
    const detach = pan.attach(element)
    const stop = onFrame((dt) => {
      const moved = pan.step(dt)
      if (!moved) return false
      if (body.current) body.current.style.transform = `translate(${-pan.x}px, ${-pan.y}px)`
      if (head.current) head.current.style.transform = `translateX(${-pan.x}px)`
      setFirst(Math.max(0, Math.floor(pan.y / ROW) - 10))
      setVisible(Math.ceil(element.clientHeight / ROW) + 20)
      // The table moves under its own sheet: no glass moved.
      return false
    })
    return () => {
      detach()
      stop()
    }
  }, [pan, table])

  const rows = table?.rows.slice(first, first + visible) ?? []
  return (
    <section className="view table-view" inert={!active}>
      <header className="banner">
        <button type="button" className="bubble glass" data-glass onClick={onData}>Data</button>
        {table && <button type="button" className="bubble glass" data-glass onClick={onRemove}>Remove</button>}
      </header>
      <div className="sheet glass" data-glass>
        <div className="paper" ref={frame} tabIndex={0} aria-label={table ? `${table.filename}, ${table.rows.length} rows` : undefined}>
          {table && <>
            <div className="table-head" ref={head} style={{ gridTemplateColumns: template, width }}>
              {table.columns.map((column) => <span key={column}>{column}</span>)}
            </div>
            <div className="table-clip">
              <div className="table-body" ref={body} style={{ height: table.rows.length * ROW, width }}>
                {rows.map((row, offset) => (
                  <div key={first + offset} className="table-row" style={{ top: (first + offset) * ROW, gridTemplateColumns: template }}>
                    {table.columns.map((column) => <span key={column} className={numeric(row[column]) ? 'numeric' : ''}>{valueString(row[column])}</span>)}
                  </div>
                ))}
              </div>
            </div>
          </>}
        </div>
      </div>
    </section>
  )
}
