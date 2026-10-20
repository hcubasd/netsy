import { commands } from './files'

// The data-flow graph as a top-down circuit, laid out by hand. Down the
// spine (column 1) runs the chain of made files, agents to network
// emissions; each command's fresh inputs sit in the row of the file before
// it, to its right, and the first row's inputs are centered above agents.
// A command's output sits in the row below its inputs.
//
// Wires run only through empty space, so none crosses a bubble. A file's
// outputs leave its bottom edge just right of its middle and its inputs
// arrive at its top edge just left of it. Every made file has one bus, a
// horizontal track in the channel above it that all its inputs join: an
// input drops straight to it when the cells below that input are empty, or
// otherwise runs along a track of its own to an empty column and drops
// there.

export const BUBBLE = { width: 208, height: 88 }
const GAP = 40          // between columns, and at both sides
const TRACK = 10        // between tracks in a channel
const MIN_CHANNEL = 44  // between rows
const TRACK_MARGIN = 12 // between two tracks' ends on one line
const PAD = { top: 52, bottom: 64 }
const PORT = 14         // ports' offset from a bubble's middle

// Each row, top to bottom: [column, file].
const ROWS: [number, string][][] = [
  [[0, 'zones.gpkg'], [1, 'size_totals.csv'], [2, 'size_classes.csv']],
  [
    [1, 'agents.gpkg'], [2, 'skims.omx'], [3, 'facilities.gpkg'], [4, 'production_rates.csv'],
    [5, 'consumption_rates.csv'], [6, 'shipment_totals.csv'], [7, 'flow_types.csv'], [8, 'distance_decay.csv'],
    [9, 'shipment_sizes.csv'], [10, 'shipment_vehicles.csv'], [11, 'vehicle_choice.csv'],
    [12, 'delivery_windows.csv'], [13, 'delivery_choice.csv'],
  ],
  [[1, 'shipments.gpkg'], [2, 'facility_chain_steps.csv']],
  [
    [1, 'transaction_legs.gpkg'], [2, 'departures.csv'], [3, 'time_intervals.csv'], [4, 'dwell_times.csv'],
    [5, 'vehicle_velocities.csv'], [6, 'vehicle_capacities.csv'], [7, 'road_capacities.csv'],
    [8, 'alternative_specific_constants.csv'], [9, 'network.gpkg'], [10, 'vehicles.csv'],
  ],
  [[1, 'network_loads.csv'], [2, 'copert_v_coefficients.csv'], [3, 'emission_factors.csv']],
  [[1, 'network_emissions.csv']],
  [[0, 'productions.csv'], [1, 'attractions.csv'], [2, 'od_prior.csv']],
  [[1, 'od_flows.csv']],
]

export interface CircuitNode { id: string; x: number; y: number }
export interface Wire { x1: number; y1: number; x2: number; y2: number }
export interface Circuit { nodes: CircuitNode[]; wires: Wire[]; bubble: { width: number; height: number }; width: number; height: number }

interface Track { channel: number; a: number; b: number; y: number; line: number }

// Assigns intervals to the fewest lines such that intervals on one line keep
// `margin` apart; returns each interval's line and the number of lines.
function pack(intervals: { a: number; b: number }[], margin: number) {
  const ends: number[] = []
  const line = intervals.map(() => 0)
  intervals.map((interval, index) => ({ ...interval, index })).sort((p, q) => p.a - q.a).forEach(({ a, b, index }) => {
    let free = ends.findIndex((end) => a > end + margin)
    if (free < 0) free = ends.push(-Infinity) - 1
    ends[free] = b
    line[index] = free
  })
  return { line, count: ends.length }
}

// The circuit, centered in `available` pixels when it is narrower.
export function layoutCircuit(available: number): Circuit {
  const W = BUBBLE.width, H = BUBBLE.height
  const place = new Map<string, { row: number; column: number }>()
  ROWS.forEach((files, row) => files.forEach(([column, file]) => place.set(file, { row, column })))
  const edges = commands.flatMap((command) => [...command.inputs, ...(command.optional ?? [])]
    .flatMap((from) => command.outputs.map((to) => ({ from, to }))))
  for (const { from, to } of edges) {
    for (const file of [from, to]) if (!place.has(file)) throw new Error(`circuit: ${file} has no place`)
  }

  const columns = Math.max(...ROWS.flat().map(([column]) => column)) + 1
  const width = columns * (W + GAP) + GAP
  const center = (column: number) => GAP + column * (W + GAP) + W / 2
  const out = (file: string) => center(place.get(file)!.column) + PORT
  const into = (file: string) => center(place.get(file)!.column) - PORT
  const empty = (column: number, from: number, to: number) => {
    for (let row = from; row <= to; row++) if (ROWS[row].some(([taken]) => taken === column)) return false
    return true
  }

  // Buses, and the tracks and lanes of inputs that cannot drop straight.
  const tracks = new Map<string, Track>()
  const attach = (key: string, channel: number, x: number) => {
    const track = tracks.get(key) ?? { channel, a: x, b: x, y: 0, line: 0 }
    track.a = Math.min(track.a, x)
    track.b = Math.max(track.b, x)
    tracks.set(key, track)
  }
  const drops = new Map<string, string[]>()   // file → the tracks its port drops to
  const lanes: { x: number; from: string; to: string }[] = []
  for (const { from, to } of edges) {
    const source = place.get(from)!, target = place.get(to)!
    const bus = `to|${to}`
    attach(bus, target.row - 1, into(to))
    if (empty(source.column, source.row + 1, target.row - 1)) {
      attach(bus, target.row - 1, out(from))
      drops.set(from, [...(drops.get(from) ?? []), bus])
      continue
    }
    // The empty column nearest the input's, left first.
    let column = -1
    for (let distance = 1; column < 0 && distance <= columns; distance++) {
      for (const candidate of [source.column - distance, source.column + distance]) {
        if (column < 0 && candidate >= 0 && candidate < columns && empty(candidate, source.row + 1, target.row - 1)) column = candidate
      }
    }
    if (column < 0) throw new Error(`circuit: no way from ${from} to ${to}`)
    const own = `from|${from}|${to}`
    attach(own, source.row, out(from))
    attach(own, source.row, center(column))
    attach(bus, target.row - 1, center(column))
    drops.set(from, [...(drops.get(from) ?? []), own])
    lanes.push({ x: center(column), from: own, to: bus })
  }

  const counts = ROWS.map((_, channel) => {
    const inChannel = [...tracks.values()].filter((track) => track.channel === channel)
    const { line, count } = pack(inChannel, TRACK_MARGIN)
    inChannel.forEach((track, index) => { track.line = line[index] })
    return count
  })
  const top: number[] = []
  let y = PAD.top
  ROWS.forEach((_, row) => {
    top.push(y)
    y += H + Math.max(MIN_CHANNEL, (counts[row] + 1) * TRACK)
  })
  const height = top.at(-1)! + H + PAD.bottom
  for (const track of tracks.values()) {
    const middle = (top[track.channel] + H + top[track.channel + 1]) / 2
    track.y = middle + (track.line - (counts[track.channel] - 1) / 2) * TRACK
  }

  const wires: Wire[] = []
  const vertical = (x: number, y1: number, y2: number) => wires.push({ x1: x, y1, x2: x, y2 })
  for (const track of tracks.values()) wires.push({ x1: track.a, y1: track.y, x2: track.b, y2: track.y })
  for (const [file, keys] of drops) {
    vertical(out(file), top[place.get(file)!.row] + H, Math.max(...keys.map((key) => tracks.get(key)!.y)))
  }
  for (const [key, track] of tracks) {
    if (key.startsWith('to|')) {
      const file = key.slice(3)
      vertical(into(file), track.y, top[place.get(file)!.row])
    }
  }
  for (const lane of lanes) vertical(lane.x, tracks.get(lane.from)!.y, tracks.get(lane.to)!.y)

  const offset = Math.max(0, (available - width) / 2)
  return {
    nodes: [...place].map(([id, { row, column }]) => ({ id, x: offset + center(column) - W / 2, y: top[row] })),
    wires: wires.map(({ x1, y1, x2, y2 }) => ({ x1: x1 + offset, y1, x2: x2 + offset, y2 })),
    bubble: { width: W, height: H },
    width: Math.max(width, available),
    height,
  }
}
