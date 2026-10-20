import { commands } from './files'

// The data-flow graph as a top-down circuit, laid out by hand. Down the
// spine (column 1) runs the freight chain, agents to tours, then network
// loads and emissions; the parcel chain runs down column 15 and van trips
// from column 19. Each command's fresh inputs sit in the row of the file
// before it, to its right, and the first row's inputs are centered above
// agents. A command's output sits in the row below its inputs.
//
// Wires run only through empty space, so none crosses a bubble. A file's
// outputs leave its bottom edge just right of its middle and its inputs
// arrive at its top edge just left of it. Every command has one bus, a
// horizontal track in the channel above its outputs that all its inputs
// join: an input drops straight to it when the cells below that input are
// empty, or otherwise runs along a track of its own to an empty column and
// drops there. The tracks of a channel are stacked in the order that
// crosses the fewest wires.

export const BUBBLE = { width: 208, height: 88 }
const GAP = 40          // between columns, and at both sides
const TRACK = 14        // between tracks in a channel
const MIN_CHANNEL = 44  // between rows
const PAD = { top: 52, bottom: 64 }
const PORT = 14         // ports' offset from a bubble's middle

// Each row, top to bottom: [column, file]. Files that later rows use again
// (zones, skims, facilities, vehicles) sit where the cells below them stay
// empty, so their wires drop straight.
const ROWS: [number, string][][] = [
  [[0, 'zones.gpkg'], [1, 'size_totals.csv'], [2, 'size_classes.csv']],
  [
    [1, 'agents.gpkg'], [2, 'skims.omx'], [3, 'facilities.gpkg'], [4, 'shipment_vehicles.csv'],
    [5, 'production_rates.csv'], [6, 'consumption_rates.csv'], [7, 'shipment_totals.csv'], [8, 'flow_types.csv'],
    [9, 'distance_decay.csv'], [10, 'shipment_sizes.csv'], [11, 'vehicle_choice.csv'],
    [12, 'delivery_windows.csv'], [13, 'delivery_choice.csv'],
    [15, 'parcel_attributes.csv'], [16, 'parcel_rates.csv'], [17, 'population.csv'], [18, 'order_levels.csv'],
    [19, 'order_utility.csv'], [20, 'operator_shares.csv'], [21, 'parcel_settings.csv'],
  ],
  [
    [1, 'shipments.gpkg'], [5, 'tour_settings.csv'], [6, 'end_tour_first.csv'], [7, 'end_tour_later.csv'],
    [9, 'facility_chain_steps.csv'], [15, 'parcel_demand.csv'], [16, 'delivery_settings.csv'],
    [17, 'delivery_departures.csv'], [19, 'trip_attributes.csv'], [20, 'trip_rates.csv'], [21, 'trip_decay.csv'],
  ],
  [
    [1, 'tours.gpkg'], [2, 'tour_shipments.csv'], [3, 'network.gpkg'], [4, 'assignment_vehicles.csv'],
    [5, 'link_speeds.csv'], [6, 'road_costs.csv'], [7, 'time_intervals.csv'], [8, 'matrix_assignment.csv'],
    [9, 'transaction_legs.gpkg'], [15, 'delivery_tours.gpkg'], [20, 'trip_matrices.omx'],
  ],
  [
    [1, 'network_loads.csv'], [5, 'emission_factors.csv'], [6, 'copert_vehicles.csv'], [7, 'copert_v_coefficients.csv'],
    [8, 'non_exhaust_factors.csv'],
  ],
  [[1, 'network_emissions.csv']],
  [[0, 'location_attributes.csv'], [1, 'marginal_coefficients.csv'], [2, 'od_prior.csv']],
  [[0, 'productions.csv'], [1, 'attractions.csv']],
  [[1, 'od_flows.csv']],
]

export interface CircuitNode { id: string; x: number; y: number }
export interface Wire { x1: number; y1: number; x2: number; y2: number }
export interface Circuit { nodes: CircuitNode[]; wires: Wire[]; bubble: { width: number; height: number }; width: number; height: number }

interface Track { channel: number; a: number; b: number; xs: Set<number>; y: number }
// A vertical wire: from the bottom of a row or a track, to the top of a row
// or the deepest of some tracks.
interface Vertical { x: number; from: { row: number } | { track: string }; to: { row: number } | { tracks: string[] } }

function* permutations<T>(items: T[]): Generator<T[]> {
  if (items.length <= 1) { yield items; return }
  for (let index = 0; index < items.length; index++) {
    for (const rest of permutations([...items.slice(0, index), ...items.slice(index + 1)])) yield [items[index], ...rest]
  }
}

// The circuit, centered in `available` pixels when it is narrower.
export function layoutCircuit(available: number): Circuit {
  const W = BUBBLE.width, H = BUBBLE.height
  const place = new Map<string, { row: number; column: number }>()
  ROWS.forEach((files, row) => files.forEach(([column, file]) => place.set(file, { row, column })))
  for (const command of commands) {
    for (const file of [...command.inputs, ...(command.optional ?? []), ...command.outputs]) {
      if (!place.has(file)) throw new Error(`circuit: ${file} has no place`)
    }
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

  // One bus per command, in the channel above its outputs, which every
  // input joins: straight down when the cells below the input are empty,
  // otherwise along a track of its own to an empty column and down there.
  const tracks = new Map<string, Track>()
  const attach = (key: string, channel: number, x: number) => {
    const track = tracks.get(key) ?? { channel, a: x, b: x, xs: new Set<number>(), y: 0 }
    track.a = Math.min(track.a, x)
    track.b = Math.max(track.b, x)
    track.xs.add(x)
    tracks.set(key, track)
  }
  const verticals: Vertical[] = []
  const drops = new Map<string, string[]>()   // file → the tracks its port drops to
  for (const command of commands) {
    const bus = `bus|${command.name}`
    const row = place.get(command.outputs[0])!.row
    for (const output of command.outputs) {
      attach(bus, row - 1, into(output))
      verticals.push({ x: into(output), from: { track: bus }, to: { row } })
    }
    for (const from of [...command.inputs, ...(command.optional ?? [])]) {
      const source = place.get(from)!
      if (empty(source.column, source.row + 1, row - 1)) {
        attach(bus, row - 1, out(from))
        drops.set(from, [...(drops.get(from) ?? []), bus])
        continue
      }
      // The empty column nearest the input's, left first.
      let column = -1
      for (let distance = 1; column < 0 && distance <= columns; distance++) {
        for (const candidate of [source.column - distance, source.column + distance]) {
          if (column < 0 && candidate >= 0 && candidate < columns && empty(candidate, source.row + 1, row - 1)) column = candidate
        }
      }
      if (column < 0) throw new Error(`circuit: no way from ${from} to ${command.name}`)
      const own = `own|${from}|${command.name}`
      attach(own, source.row, out(from))
      attach(own, source.row, center(column))
      attach(bus, row - 1, center(column))
      drops.set(from, [...(drops.get(from) ?? []), own])
      verticals.push({ x: center(column), from: { track: own }, to: { tracks: [bus] } })
    }
  }
  for (const [file, keys] of drops) verticals.push({ x: out(file), from: { row: place.get(file)!.row }, to: { tracks: keys } })

  // Rows, and channels with one line per track.
  const inChannel = ROWS.map((_, channel) => [...tracks.keys()].filter((key) => tracks.get(key)!.channel === channel))
  const top: number[] = []
  let y = PAD.top
  ROWS.forEach((_, row) => {
    top.push(y)
    y += H + Math.max(MIN_CHANNEL, (inChannel[row].length + 1) * TRACK)
  })
  const height = top.at(-1)! + H + PAD.bottom

  // In each channel, the order of its lines that crosses the fewest wires:
  // a vertical crosses a track it does not join where it runs through it.
  const span = (vertical: Vertical, channel: number): [number, number] | null => {
    const bandTop = top[channel] + H, bandBottom = top[channel + 1] ?? bandTop
    const start = 'row' in vertical.from ? top[vertical.from.row] + H : tracks.get(vertical.from.track)!.y
    const startChannel = 'row' in vertical.from ? vertical.from.row : tracks.get(vertical.from.track)!.channel
    const ends = 'row' in vertical.to ? null : vertical.to.tracks.map((key) => tracks.get(key)!)
    const endChannel = 'row' in vertical.to ? vertical.to.row - 1 : Math.max(...ends!.map((track) => track.channel))
    if (channel < startChannel || channel > endChannel) return null
    const y1 = channel === startChannel ? start : bandTop
    const y2 = channel !== endChannel ? bandBottom : 'row' in vertical.to ? top[vertical.to.row]
      : Math.max(...ends!.filter((track) => track.channel === channel).map((track) => track.y))
    return [y1, y2]
  }
  const joins = (vertical: Vertical, key: string) => ('track' in vertical.from && vertical.from.track === key) ||
    ('tracks' in vertical.to && vertical.to.tracks.includes(key))
  inChannel.forEach((keys, channel) => {
    const middle = (top[channel] + H + (top[channel + 1] ?? top[channel] + H)) / 2
    const stack = (order: string[]) => order.forEach((key, line) => { tracks.get(key)!.y = middle + (line - (order.length - 1) / 2) * TRACK })
    let best = keys, fewest = Infinity
    for (const order of keys.length <= 6 ? permutations(keys) : [keys]) {
      stack(order)
      let crossings = 0
      for (const vertical of verticals) {
        const range = span(vertical, channel)
        if (!range) continue
        for (const key of keys) {
          const track = tracks.get(key)!
          if (!joins(vertical, key) && vertical.x > track.a && vertical.x < track.b && track.y > range[0] && track.y < range[1]) crossings++
        }
      }
      if (crossings < fewest) { fewest = crossings; best = order }
    }
    stack(best)
  })

  const wires: Wire[] = []
  for (const track of tracks.values()) wires.push({ x1: track.a, y1: track.y, x2: track.b, y2: track.y })
  for (const vertical of verticals) {
    const y1 = 'row' in vertical.from ? top[vertical.from.row] + H : tracks.get(vertical.from.track)!.y
    const y2 = 'row' in vertical.to ? top[vertical.to.row] : Math.max(...vertical.to.tracks.map((key) => tracks.get(key)!.y))
    wires.push({ x1: vertical.x, y1, x2: vertical.x, y2 })
  }

  const offset = Math.max(0, (available - width) / 2)
  return {
    nodes: [...place].map(([id, { row, column }]) => ({ id, x: offset + center(column) - W / 2, y: top[row] })),
    wires: wires.map(({ x1, y1, x2, y2 }) => ({ x1: x1 + offset, y1, x2: x2 + offset, y2 })),
    bubble: { width: W, height: H },
    width: Math.max(width, available),
    height,
  }
}
