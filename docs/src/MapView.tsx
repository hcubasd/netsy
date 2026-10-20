import { useMemo, useRef, useState } from 'react'
import { MapCanvas, type MapControls, type ZoomHistory } from './MapCanvas'
import type { Legend } from './map/scene'
import { cssColor } from './palette'
import type { Cell, DataTable } from './types'

// The map: NetSy's geometries, colored by a measure, in a white square.

type Layer = 'zones' | 'agents' | 'facilities' | 'shipments' | 'tours' | 'deliveries' | 'network' | 'loads' | 'emissions'

interface LayerSpec {
  label: string
  geometry: string
  data?: string
  key: string
  direct?: boolean
}

const LAYERS: Record<Layer, LayerSpec> = {
  zones: { label: 'Zones', geometry: 'zones.gpkg', key: 'zone_id', direct: true },
  agents: { label: 'Agents', geometry: 'agents.gpkg', key: 'agent_id', direct: true },
  facilities: { label: 'Facilities', geometry: 'facilities.gpkg', key: 'facility_id', direct: true },
  shipments: { label: 'Shipments', geometry: 'shipments.gpkg', key: 'transaction_id', direct: true },
  tours: { label: 'Tours', geometry: 'tours.gpkg', key: 'tour_id', direct: true },
  deliveries: { label: 'Delivery tours', geometry: 'delivery_tours.gpkg', key: 'tour_id', direct: true },
  network: { label: 'Network', geometry: 'network.gpkg', key: 'link_id', direct: true },
  loads: { label: 'Network · loads', geometry: 'network.gpkg', data: 'network_loads.csv', key: 'link_id' },
  emissions: { label: 'Network · emissions', geometry: 'network.gpkg', data: 'network_emissions.csv', key: 'link_id' },
}

const dimensions = ['resource', 'time_interval', 'vehicle', 'segment']
const numeric = (value: Cell | undefined) => typeof value === 'number' && Number.isFinite(value)
const label = (value: string) => value.replaceAll('_', ' ').replace(/^\w/, (letter) => letter.toUpperCase())
const valueString = (value: Cell | undefined) => value === null || value === undefined ? '' : String(value)

function valuesFor(table: DataTable, layer: LayerSpec) {
  const excluded = new Set([...dimensions, layer.key])
  return table.columns.filter((column) => !excluded.has(column) && !/(^|_)id$/.test(column) && table.rows.some((row) => numeric(row[column])))
}

// One value per geometry row (NaN where it has none): the measure itself on
// a file with geometry, or the matching rows of a table summed per key.
function rowValues(geometry: DataTable, source: DataTable, layer: LayerSpec, measure: string, filters: Record<string, string>) {
  const values = new Float64Array(geometry.rows.length).fill(Number.NaN)
  if (layer.direct) {
    if (!measure) return null
    geometry.rows.forEach((row, index) => { if (numeric(row[measure])) values[index] = row[measure] as number })
    return values
  }
  const byKey = new Map<string, number>()
  for (const row of source.rows) {
    if (!dimensions.every((dimension) => (filters[dimension] ?? 'all') === 'all' || !source.columns.includes(dimension) || valueString(row[dimension]) === filters[dimension])) continue
    const key = valueString(row[layer.key])
    if (key && numeric(row[measure])) byKey.set(key, (byKey.get(key) ?? 0) + (row[measure] as number))
  }
  geometry.rows.forEach((row, index) => { values[index] = byKey.get(valueString(row[layer.key])) ?? Number.NaN })
  return values
}

const format = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 4 })

export function MapView({ tables, active, onData }: { tables: Record<string, DataTable>; active: boolean; onData: () => void }) {
  const available = (Object.entries(LAYERS) as [Layer, LayerSpec][]).filter(([, layer]) => tables[layer.geometry] && (!layer.data || tables[layer.data]))
  const [layerName, setLayerName] = useState<Layer>('zones')
  const [measure, setMeasure] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [lineWidth, setLineWidth] = useState(1)
  const [legend, setLegend] = useState<Legend | null>(null)
  const [history, setHistory] = useState<ZoomHistory>({ prepared: null, views: [], zoomed: false })
  const controls = useRef<MapControls>(null)
  const activeLayer = available.find(([name]) => name === layerName)?.[0] ?? available[0]?.[0]
  const layer = activeLayer && LAYERS[activeLayer]
  const geometry = layer && tables[layer.geometry]
  const source = layer && (layer.direct ? geometry : tables[layer.data ?? ''])
  const measures = useMemo(() => (layer && source ? valuesFor(source, layer) : []), [layer, source])
  const activeMeasure = measures.includes(measure) ? measure : measures[0] ?? ''
  const prepared = geometry?.prepared ?? null
  const values = useMemo(() => (layer && geometry && source ? rowValues(geometry, source, layer, activeMeasure, filters) : null), [layer, geometry, source, activeMeasure, filters])
  const options = useMemo(() => Object.fromEntries(dimensions.filter((dimension) => source?.columns.includes(dimension))
    .map((dimension) => [dimension, [...new Set(source!.rows.map((row) => valueString(row[dimension])).filter(Boolean))].sort()])), [source])

  return (
    <section className="view map-view" inert={!active}>
      <header className="banner">
        <span className="wordmark">NetSy</span>
        <div className="bubbles">
          <button type="button" className="bubble glass" data-glass disabled={!prepared || history.prepared !== prepared || !history.views.length}
            onClick={() => controls.current?.back()}>Zoom out</button>
          <button type="button" className="bubble glass" data-glass disabled={!prepared || history.prepared !== prepared || !history.zoomed} onClick={() => controls.current?.reset()}>Reset zoom</button>
          <button type="button" className="bubble glass" data-glass onClick={onData}>Data</button>
        </div>
      </header>
      <div className="panels">
        <aside className="controls glass" data-glass>
          {layer && source && <>
            <label>Layer
              <select value={activeLayer} onChange={(event) => setLayerName(event.target.value as Layer)}>
                {available.map(([name, specification]) => <option key={name} value={name}>{specification.label}</option>)}
              </select>
            </label>
            {measures.length > 0 && <label>Measure
              <select value={activeMeasure} onChange={(event) => setMeasure(event.target.value)}>
                {measures.map((value) => <option key={value} value={value}>{label(value)}</option>)}
              </select>
            </label>}
            {Object.entries(options).map(([dimension, choices]) => (
              <label key={dimension}>{label(dimension)}
                <select value={filters[dimension] ?? 'all'} onChange={(event) => setFilters((current) => ({ ...current, [dimension]: event.target.value }))}>
                  <option value="all">All</option>
                  {choices.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
            ))}
            <label>Lines
              <input type="range" min="0" max="8" step="any" value={lineWidth} onChange={(event) => setLineWidth(Number(event.target.value))} />
            </label>
            {legend && <div className="legend">
              <div className="legend-scale" style={{ background: `linear-gradient(to top, ${legend.ramp.map((color) => cssColor(color)).join(', ')})` }} />
              <div className="legend-ticks">
                {legend.ticks.map(({ t, value }) => <span key={t} style={{ bottom: `${t * 100}%` }}>{format.format(value)}</span>)}
              </div>
            </div>}
          </>}
        </aside>
        <div className="map-panel glass" data-glass>
          <div className="map-sheet">
            {prepared && <MapCanvas ref={controls} active={active} prepared={prepared} values={values} lineWidth={lineWidth} onLegend={setLegend} history={history} onHistory={setHistory} />}
          </div>
        </div>
      </div>
    </section>
  )
}
