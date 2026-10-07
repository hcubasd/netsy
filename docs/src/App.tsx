import { useState, type CSSProperties, type DragEvent } from 'react'
import { MapCanvas } from './MapCanvas'
import { NicrainhaScene } from './NicrainhaScene'
import { continuousPalette, cssColor } from './palette'
import { parseFile, tableByName } from './loaders'
import type { Cell, DataTable, ValueFeature } from './types'
import './App.css'

type View = 'map' | 'diagram' | 'tables'
type Layer = 'supply' | 'demand' | 'capacities' | 'needs' | 'agents' | 'desire' | 'grade' | 'loads' | 'emissions'

interface LayerSpec {
  label: string
  geometry: string
  data?: string
  key: string
  direct?: boolean
  expectedValue?: boolean
}

const LAYERS: Record<Layer, LayerSpec> = {
  supply: { label: 'Zones · supply', geometry: 'zones.gpkg', data: 'supply.csv', key: 'zone_id' },
  demand: { label: 'Zones · demand', geometry: 'zones.gpkg', data: 'demand.csv', key: 'zone_id' },
  capacities: { label: 'Zones · capacities', geometry: 'zones.gpkg', data: 'capacities.csv', key: 'zone_id', expectedValue: true },
  needs: { label: 'Zones · needs', geometry: 'zones.gpkg', data: 'needs.csv', key: 'zone_id', expectedValue: true },
  agents: { label: 'Agents', geometry: 'agents.gpkg', key: 'agent_id', direct: true },
  desire: { label: 'Desire lines', geometry: 'desire_lines.gpkg', key: 'origin_agent_id', direct: true },
  grade: { label: 'Network · grade', geometry: 'network.gpkg', key: 'link_id', direct: true },
  loads: { label: 'Network · loads', geometry: 'network.gpkg', data: 'network_loads.csv', key: 'link_id' },
  emissions: { label: 'Network · emissions', geometry: 'network.gpkg', data: 'network_emissions.csv', key: 'link_id' },
}

const dimensions = ['resource', 'time_interval', 'vehicle', 'pollutant', 'source']
const numeric = (value: Cell | undefined) => typeof value === 'number' && Number.isFinite(value)
const titleCase = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const valueString = (value: Cell | undefined) => value === null || value === undefined ? '' : String(value)
const displayFilename = (value: string) => titleCase(value.replace(/\.[^.]+$/, ''))
const blur = (() => {
  const value = Number(new URLSearchParams(window.location.search).get('blur'))
  return Number.isFinite(value) && value >= 0 ? Math.min(value, 64) : 12
})()

function filename(table: DataTable) {
  return table.filename.toLowerCase()
}

function availableLayers(tables: DataTable[]) {
  return (Object.entries(LAYERS) as [Layer, LayerSpec][]).filter(([, layer]) =>
    Boolean(tableByName(tables, layer.geometry) && (!layer.data || tableByName(tables, layer.data))),
  )
}

function valuesFor(table: DataTable, layer: LayerSpec) {
  const excluded = new Set([...dimensions, 'forward', layer.key, 'resource_level'])
  if (layer.expectedValue) return ['expected_value']
  return table.columns.filter((column) => !excluded.has(column) && table.rows.some((row) => numeric(row[column])))
}

function featureValues(
  tables: DataTable[],
  layer: LayerSpec,
  measure: string,
  filters: Record<string, string>,
): ValueFeature[] {
  const geometry = tableByName(tables, layer.geometry)
  if (!geometry?.geometries) return []
  const source = layer.direct ? geometry : tableByName(tables, layer.data ?? '')
  if (!source) return []
  const byKey = new Map<string, number>()
  source.rows.forEach((row) => {
    if (!dimensions.every((dimension) => filters[dimension] === 'all' || !source.columns.includes(dimension) || valueString(row[dimension]) === filters[dimension])) return
    const key = valueString(row[layer.key])
    if (!key) return
    let amount: number | null = null
    if (layer.expectedValue) {
      const probability = row.probability
      const resourceLevel = row.resource_level
      if (numeric(probability) && numeric(resourceLevel)) amount = Number(probability) * Number(resourceLevel)
    } else if (numeric(row[measure])) {
      amount = row[measure] as number
    }
    if (amount !== null) byKey.set(key, (byKey.get(key) ?? 0) + amount)
  })
  return geometry.geometries.flatMap((shape, index) => {
    if (!shape) return []
    const row = geometry.rows[index]
    const key = valueString(row[layer.key])
    const directValue = layer.direct && numeric(row[measure]) ? row[measure] as number : null
    return [{ geometry: shape, value: directValue ?? byKey.get(key) ?? null, label: key || `${index + 1}` }]
  })
}

function MapView({ tables }: { tables: DataTable[] }) {
  const available = availableLayers(tables)
  const [layerName, setLayerName] = useState<Layer>('supply')
  const activeLayerName = available.some(([name]) => name === layerName) ? layerName : available[0]?.[0] ?? 'supply'
  const layer = LAYERS[activeLayerName]
  const geometry = tableByName(tables, layer.geometry)
  const source = layer.direct ? geometry : tableByName(tables, layer.data ?? '')
  const measures = source ? valuesFor(source, layer) : []
  const [measure, setMeasure] = useState('')
  const activeMeasure = measures.includes(measure) ? measure : measures[0] ?? ''
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [simplification, setSimplification] = useState(0)
  const [lineWidth, setLineWidth] = useState(2)
  const filtersForLayer = dimensions.filter((dimension) => source?.columns.includes(dimension))
  const features = featureValues(tables, layer, activeMeasure, filters)
  const values = features.flatMap((feature) => feature.value === null ? [] : [feature.value])
  const range = values.length ? `${Math.min(...values).toLocaleString()} — ${Math.max(...values).toLocaleString()}` : 'No matching values'
  return (
    <section className="map-view workspace">
      <aside className="controls glass-panel" data-glass-panel aria-label="Map controls">
        <label>Layer
          <select value={activeLayerName} onChange={(event) => setLayerName(event.target.value as Layer)}>
            {available.map(([name, specification]) => <option key={name} value={name}>{specification.label}</option>)}
          </select>
        </label>
        <label>Measure
          <select value={activeMeasure} onChange={(event) => setMeasure(event.target.value)}>
            {measures.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
          </select>
        </label>
        {filtersForLayer.map((dimension) => {
          const options = [...new Set(source?.rows.map((row) => valueString(row[dimension])).filter(Boolean))].sort()
          return <label key={dimension}>{titleCase(dimension)}
            <select value={filters[dimension] ?? 'all'} onChange={(event) => setFilters((current) => ({ ...current, [dimension]: event.target.value }))}>
              <option value="all">All</option>
              {options.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
        })}
        <label>Geometry simplification <output>{Math.round(simplification * 100)}% of map diagonal</output>
          <input type="range" min="0" max=".03" step=".001" value={simplification} onChange={(event) => setSimplification(Number(event.target.value))} />
        </label>
        <label>Layer thickness <output>{lineWidth}px</output>
          <input type="range" min="1" max="12" step="1" value={lineWidth} onChange={(event) => setLineWidth(Number(event.target.value))} />
        </label>
        <div className="legend">
          <span>{titleCase(activeMeasure || 'value')}</span>
          <div className="legend-scale" style={{ background: `linear-gradient(to top, ${continuousPalette.map((color) => cssColor(color)).join(', ')})` }} />
          <small>{range}</small>
        </div>
        <p className="hint">Drag to pan. Scroll to zoom. Values are equalized against the visible layer selection.</p>
      </aside>
      <div className="map-frame"><MapCanvas key={`${activeLayerName}-${activeMeasure}`} features={features} lineWidth={lineWidth} simplification={simplification} /></div>
    </section>
  )
}

const stages: [string, string[]][] = [
  ['Effects & Thresholds', ['supply_effects.csv', 'supply_thresholds.csv', 'demand_effects.csv', 'demand_thresholds.csv', 'capacity_effects.csv', 'capacity_thresholds.csv', 'need_effects.csv', 'need_thresholds.csv']],
  ['Stratified Synthesis', ['supply.csv', 'demand.csv', 'capacities.csv', 'needs.csv', 'zones.gpkg']],
  ['Agents & Flows', ['agents.gpkg', 'desire_lines.gpkg', 'network.gpkg']],
  ['Loads & Emissions', ['departures.csv', 'time_intervals.csv', 'dwell_times.csv', 'vehicles.csv', 'vehicle_velocities.csv', 'vehicle_capacities.csv', 'road_capacities.csv', 'alternative_specific_constants.csv', 'network_loads.csv', 'copert_v_coefficients.csv', 'emission_factors.csv', 'network_emissions.csv']],
]

function DiagramView({ tables }: { tables: DataTable[] }) {
  const loaded = new Set(tables.map(filename))
  return (
    <section className="diagram-view workspace">
      <div className="diagram-content">
        <div className="diagram-stages">
          {stages.map(([title, files], stageIndex) => (
            <section className="diagram-stage" key={title}>
              <span className="stage-index">0{stageIndex + 1}</span><h3>{title}</h3>
              <div className="diagram-cards">
                {files.map((file, index) => {
                  const isLoaded = loaded.has(file)
                  return <div className={`diagram-card glass-panel ${isLoaded ? 'loaded' : ''}`} data-glass-panel key={file} style={isLoaded ? { color: cssColor(continuousPalette[(stageIndex * 43 + index * 19) % 256]) } : undefined}>
                    <span className="status-dot" /><code>{displayFilename(file)}</code><small>{isLoaded ? 'Loaded' : 'Awaiting file'}</small>
                  </div>
                })}
              </div>
            </section>
          ))}
        </div>
      </div>
    </section>
  )
}

function TableView({ tables }: { tables: DataTable[] }) {
  const [selected, setSelected] = useState('')
  const [page, setPage] = useState(0)
  const [query, setQuery] = useState('')
  const [zoom, setZoom] = useState(0)
  const activeSelected = tables.some((table) => table.filename === selected) ? selected : tables[0]?.filename ?? ''
  const table = tables.find((candidate) => candidate.filename === activeSelected)
  const rows = table?.rows.filter((row) => Object.values(row).some((cell) => valueString(cell).toLowerCase().includes(query.toLowerCase()))) ?? []
  const pageSize = 100
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const visible = rows.slice(page * pageSize, (page + 1) * pageSize)
  return (
    <section className="table-view workspace">
      <header className="table-toolbar glass-panel" data-glass-panel>
        <label>Table <select value={activeSelected} onChange={(event) => { setSelected(event.target.value); setPage(0) }}>{tables.map((item) => <option key={item.filename} value={item.filename}>{displayFilename(item.filename)}</option>)}</select></label>
        <label>Filter <input value={query} placeholder="Match any value" onChange={(event) => { setQuery(event.target.value); setPage(0) }} /></label>
        <label>Text size <output>{Math.round(12 * 1.12 ** zoom)}px</output>
          <input type="range" min="-4" max="6" step="1" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />
        </label>
        <span>{rows.length.toLocaleString()} rows</span>
      </header>
      {table ? <div className="table-shell"><div className="table-scroll" style={{ '--table-font-size': `${Math.round(12 * 1.12 ** zoom)}px` } as CSSProperties}><table><thead><tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>
        {visible.map((row, index) => <tr key={index}>{table.columns.map((column) => <td key={column} className={numeric(row[column]) ? 'numeric' : ''}>{valueString(row[column])}</td>)}</tr>)}
      </tbody></table></div></div> : <div className="empty-state glass-panel" data-glass-panel>Load one or more CSV or GeoPackage files to inspect their records.</div>}
      {table && <footer className="pagination glass-panel" data-glass-panel><button data-glass-panel data-glass-shape="circle" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>←</button><span>Page {page + 1} of {pageCount}</span><button data-glass-panel data-glass-shape="circle" disabled={page + 1 === pageCount} onClick={() => setPage((current) => current + 1)}>→</button></footer>}
    </section>
  )
}

function FileLoader({ onFiles, busy }: { onFiles: (files: FileList | File[]) => void; busy: boolean }) {
  const drop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    onFiles(event.dataTransfer.files)
  }
  return <label className="file-loader glass-panel" data-glass-panel onDragOver={(event) => event.preventDefault()} onDrop={drop}>
    <input type="file" accept=".csv,.gpkg" multiple onChange={(event) => event.target.files && onFiles(event.target.files)} />
    <strong>{busy ? 'Loading files…' : 'Load NetSy outputs'}</strong><span>Drop CSV and GeoPackage files, or browse locally. Files stay in this browser.</span>
  </label>
}

function App() {
  const [tables, setTables] = useState<DataTable[]>([])
  const [view, setView] = useState<View>('map')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const onFiles = async (files: FileList | File[]) => {
    setBusy(true)
    setError('')
    try {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      const parsed: DataTable[] = []
      for (const file of files) {
        parsed.push(await parseFile(file))
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
      }
      const srs = parsed.filter((table) => table.srsId !== undefined).map((table) => table.srsId)
      if (new Set(srs).size > 1) throw new Error('Loaded GeoPackage overlays must use the same CRS.')
      setTables((current) => [...current.filter((table) => !parsed.some((next) => filename(next) === filename(table))), ...parsed])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load the selected files.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <NicrainhaScene />
      <main style={{ '--glass-blur': `${blur}px` } as CSSProperties}>
      <header className="site-header">
        <div className="brand glass-panel" data-glass-panel><h1>NetSy</h1></div>
        <nav className="glass-panel" data-glass-panel aria-label="Visualizer views">{(['map', 'diagram', 'tables'] as View[]).map((name) => <button className={view === name ? 'active' : ''} key={name} onClick={() => setView(name)}>{titleCase(name)}</button>)}</nav>
        <FileLoader onFiles={onFiles} busy={busy} />
      </header>
      {error && <p className="error glass-panel" data-glass-panel role="alert">{error}</p>}
      {view === 'map' && <MapView tables={tables} />}
      {view === 'diagram' && <DiagramView tables={tables} />}
      {view === 'tables' && <TableView tables={tables} />}
      </main>
    </>
  )
}

export default App
