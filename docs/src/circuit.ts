import { commands, standalone } from './files'

// The data-flow graph as a top-down circuit. Every file is a bubble of the
// same size on a grid of columns that fits the available width. Files that a
// command makes are placed in order, each in the first row below all of its
// inputs; the files nothing makes are placed just in time, in the rows
// directly above the first file made from them, and files no command
// touches start the first row. A row may mix stages.
//
// Wires run only through the empty space of the grid: horizontal channels
// between rows and vertical gaps between columns, so no wire crosses a
// bubble. A file's outputs leave its bottom edge just right of the middle and
// its inputs arrive at its top edge just left of it, so the wires leaving a
// file never run into those arriving at the file below. Each goes through one
// bus:
//   - between consecutive rows, all of a file's inputs share one horizontal
//     track in the channel just above it;
//   - an input from further up leaves its file along a track in the channel
//     below that file, drops through a column gap on a lane of its own, and
//     joins the receiving file's track.
// Tracks in a channel and lanes in a gap are spread so that unrelated wires
// never overlap; where two wires of one bus meet there is a dot.

export const BUBBLE = { width: 232, height: 92 }
const MIN_GAP = 40      // between columns, and at both sides
const MAX_GAP = 96
const LANE = 10         // between lanes in a gap, at most
const TRACK = 10        // between tracks in a channel
const MIN_CHANNEL = 44  // between rows
const TRACK_MARGIN = 12 // between two tracks' ends on one line
const PAD = { top: 52, bottom: 64 }
const PORT = 14         // ports' offset from a bubble's middle

export interface CircuitNode { id: string; x: number; y: number }
export interface Wire { x1: number; y1: number; x2: number; y2: number }
export interface Circuit { nodes: CircuitNode[]; wires: Wire[]; dots: { x: number; y: number }[]; width: number; height: number }

interface Edge { from: string; to: string }

function graph() {
  const producer = new Map<string, string[]>()  // file → the files it is made from
  const edges: Edge[] = []
  for (const command of commands) {
    for (const output of command.outputs) {
      const inputs = [...command.inputs, ...(command.optional ?? [])]
      producer.set(output, inputs)
      inputs.forEach((input) => edges.push({ from: input, to: output }))
    }
  }
  // Rank: a made file sits one below its lowest input; a file nothing makes
  // sits just above the first file made from it.
  const rank = new Map<string, number>()
  for (const command of commands) {
    const inputs = [...command.inputs, ...(command.optional ?? [])]
    const below = 1 + Math.max(...inputs.map((file) => (producer.has(file) ? rank.get(file) ?? 0 : 0)))
    command.outputs.forEach((file) => rank.set(file, below))
  }
  for (const { from, to } of edges) {
    if (!producer.has(from)) rank.set(from, Math.min(rank.get(from) ?? Infinity, rank.get(to)! - 1))
  }
  const ranks: string[][] = []
  for (const [file, index] of rank) (ranks[index] ??= []).push(file)
  return { edges, ranks, producer }
}

// Orders each rank by the mean position of its neighbors (barycenter
// sweeps), to keep wires short and straight.
function order(ranks: string[][], edges: Edge[]) {
  const neighbors = new Map<string, string[]>()
  for (const { from, to } of edges) {
    neighbors.set(from, [...(neighbors.get(from) ?? []), to])
    neighbors.set(to, [...(neighbors.get(to) ?? []), from])
  }
  const position = new Map<string, number>()
  const measure = () => ranks.forEach((files) => files.forEach((file, index) => position.set(file, (index + 0.5) / files.length)))
  measure()
  for (let sweep = 0; sweep < 8; sweep++) {
    for (const files of ranks) {
      const center = new Map(files.map((file) => {
        const around = neighbors.get(file) ?? []
        return [file, around.length ? around.reduce((total, other) => total + position.get(other)!, 0) / around.length : position.get(file)!]
      }))
      files.sort((a, b) => center.get(a)! - center.get(b)!)
      measure()
    }
  }
  return neighbors
}

// Strictly increasing whole columns in [0, columns) as close as possible to
// increasing desired positions.
function slots(desired: number[], columns: number) {
  const result: number[] = []
  desired.forEach((value, index) => result.push(Math.max(Math.round(value), index ? result[index - 1] + 1 : 0)))
  for (let index = result.length - 1; index >= 0; index--) {
    result[index] = Math.min(result[index], index < result.length - 1 ? result[index + 1] - 1 : columns - 1)
  }
  return result
}

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

export function layoutCircuit(available: number): Circuit {
  const { edges, ranks, producer } = graph()
  const neighbors = order(ranks, edges)
  const { width: W, height: H } = BUBBLE

  {
    // As many columns as fit with the narrowest gaps; the width left over
    // widens the gaps.
    const columns = Math.max(1, Math.floor((available - MIN_GAP) / (W + MIN_GAP)))
    const gap = Math.min(MAX_GAP, Math.max(MIN_GAP, (available - columns * W) / (columns + 1)))

    // Rows: each made file goes in the first row below its inputs where it,
    // and the rows directly above it, have room for it and for those of its
    // inputs not placed yet (nearest rows first).
    const rows: string[][] = []
    const at = new Map<string, number>()
    const free = (index: number) => columns - (rows[index]?.length ?? 0)
    const put = (file: string, index: number) => {
      while (rows.length <= index) rows.push([])
      rows[index].push(file)
      at.set(file, index)
    }
    for (const made of ranks.flat().filter((file) => producer.has(file))) {
      const inputs = producer.get(made)!
      const fresh = inputs.filter((file) => !producer.has(file) && !at.has(file))
      let index = Math.max(fresh.length ? 1 : 0, ...inputs.filter((file) => at.has(file)).map((file) => at.get(file)! + 1))
      for (; ; index++) {
        if (free(index) < 1) continue
        let room = 0
        for (let above = index - 1; above >= 0 && room < fresh.length; above--) room += free(above)
        if (room >= fresh.length) break
      }
      put(made, index)
      let above = index - 1
      for (const file of fresh) {
        while (free(above) < 1) above--
        put(file, above)
      }
    }
    for (let index = rows.length - 1; index >= 0; index--) if (!rows[index].length) rows.splice(index, 1)
    // Files no command touches go in the first row, or a row of their own
    // above it.
    for (const file of standalone) {
      if (rows[0] && rows[0].length < columns) rows[0].push(file)
      else rows.unshift([file])
    }
    const row = new Map<string, number>()
    rows.forEach((files, index) => files.forEach((file) => row.set(file, index)))

    // Columns: centered first, then each file moves toward the mean column of
    // its neighbors.
    const column = new Map<string, number>()
    rows.forEach((files) => files.forEach((file, index) => column.set(file, Math.floor((columns - files.length) / 2) + index)))
    for (let sweep = 0; sweep < 6; sweep++) {
      for (const files of sweep % 2 ? [...rows].reverse() : rows) {
        const desired = new Map(files.map((file) => {
          const around = neighbors.get(file) ?? []
          return [file, around.length ? around.reduce((total, other) => total + column.get(other)!, 0) / around.length : column.get(file)!]
        }))
        files.sort((a, b) => desired.get(a)! - desired.get(b)!)
        slots(files.map((file) => desired.get(file)!), columns).forEach((value, index) => column.set(files[index], value))
      }
    }

    const center = (file: string) => gap + column.get(file)! * (W + gap) + W / 2
    const out = (file: string) => center(file) + PORT
    const into = (file: string) => center(file) - PORT
    const gapCenter = (index: number) => index * (W + gap) + gap / 2

    // Lanes: an input from further up drops through the gap that keeps its
    // way shortest; one lane per input file per gap.
    const lanes = new Map<string, { gap: number; from: string; top: number; bottom: number; x: number }>()
    const laneOf = new Map<Edge, string>()
    for (const edge of edges) {
      const top = row.get(edge.from)!, bottom = row.get(edge.to)! - 1
      if (bottom === top) continue
      const xFrom = out(edge.from), xTo = into(edge.to)
      let best = 0
      for (let index = 0; index <= columns; index++) {
        const cost = (x: number) => Math.abs(x - xFrom) + Math.abs(x - xTo) + Math.abs(x - xFrom) * 1e-3
        if (cost(gapCenter(index)) < cost(gapCenter(best))) best = index
      }
      const key = `${best}|${edge.from}`
      const lane = lanes.get(key) ?? { gap: best, from: edge.from, top, bottom, x: 0 }
      lane.bottom = Math.max(lane.bottom, bottom)
      lanes.set(key, lane)
      laneOf.set(edge, key)
    }
    const gaps = Array.from({ length: columns + 1 }, (_, index) => {
      const inGap = [...lanes.values()].filter((lane) => lane.gap === index)
      return { inGap, ...pack(inGap.map((lane) => ({ a: lane.top, b: lane.bottom })), 0.5) }
    })
    const spacing = Math.min(LANE, gap / (Math.max(...gaps.map(({ count }) => count)) + 1))
    gaps.forEach(({ inGap, line, count }, index) => inGap.forEach((lane, at) => { lane.x = gapCenter(index) + (line[at] - (count - 1) / 2) * spacing }))

    // Tracks: one per receiving file in the channel above it, and one per
    // input file in the channel below it for inputs that drop through a gap.
    const tracks = new Map<string, { channel: number; a: number; b: number; y: number; line: number }>()
    const attach = (key: string, channel: number, x: number) => {
      const track = tracks.get(key) ?? { channel, a: x, b: x, y: 0, line: 0 }
      track.a = Math.min(track.a, x)
      track.b = Math.max(track.b, x)
      tracks.set(key, track)
    }
    for (const edge of edges) {
      const lane = laneOf.get(edge)
      if (!lane) {
        attach(`to|${edge.to}`, row.get(edge.from)!, out(edge.from))
        attach(`to|${edge.to}`, row.get(edge.from)!, into(edge.to))
      } else {
        const { x } = lanes.get(lane)!
        attach(`from|${edge.from}`, row.get(edge.from)!, out(edge.from))
        attach(`from|${edge.from}`, row.get(edge.from)!, x)
        attach(`to|${edge.to}`, row.get(edge.to)! - 1, into(edge.to))
        attach(`to|${edge.to}`, row.get(edge.to)! - 1, x)
      }
    }
    const channelTracks: number[] = rows.map(() => 0)
    rows.forEach((_, channel) => {
      const inChannel = [...tracks.values()].filter((track) => track.channel === channel)
      const { line, count } = pack(inChannel, TRACK_MARGIN)
      inChannel.forEach((track, at) => { track.line = line[at] })
      channelTracks[channel] = count
    })

    // Rows and channels, top to bottom.
    const top: number[] = []
    let y = PAD.top
    rows.forEach((_, index) => {
      top.push(y)
      y += H + Math.max(MIN_CHANNEL, (channelTracks[index] + 1) * TRACK)
    })
    const height = top.at(-1)! + H + PAD.bottom
    for (const track of tracks.values()) {
      const channelTop = top[track.channel] + H
      const channelHeight = top[track.channel + 1] - channelTop
      track.y = channelTop + channelHeight / 2 + (track.line - (channelTracks[track.channel] - 1) / 2) * TRACK
    }

    // Wires and dots. A dot marks where a wire meets a track anywhere but at
    // the track's end, where the two simply turn a corner.
    const offset = Math.max(0, (available - (columns * W + (columns + 1) * gap)) / 2)
    const wires: Wire[] = []
    const dots: { x: number; y: number }[] = []
    const vertical = (x: number, y1: number, y2: number) => wires.push({ x1: x, y1, x2: x, y2 })
    const meet = (x: number, track: { a: number; b: number; y: number }, ends: boolean) => {
      if (!ends || (x > track.a + 0.5 && x < track.b - 0.5)) dots.push({ x, y: track.y })
    }
    for (const track of tracks.values()) wires.push({ x1: track.a, y1: track.y, x2: track.b, y2: track.y })
    for (const files of rows) {
      for (const file of files) {
        const r = row.get(file)!
        // Down from the file to every track it feeds in the channel below.
        const below = [...tracks.entries()].filter(([key, track]) => track.channel === r && (key === `from|${file}` ||
          (key.startsWith('to|') && edges.some((edge) => edge.from === file && `to|${edge.to}` === key && !laneOf.get(edge)))))
          .map(([, track]) => track)
        if (below.length) {
          const deepest = Math.max(...below.map((track) => track.y))
          vertical(out(file), top[r] + H, deepest)
          below.forEach((track) => meet(out(file), track, track.y === deepest))
        }
        // Into the file from its own track.
        const own = tracks.get(`to|${file}`)
        if (own) {
          vertical(into(file), own.y, top[r])
          meet(into(file), own, true)
        }
      }
    }
    for (const lane of lanes.values()) {
      const start = tracks.get(`from|${lane.from}`)!
      const ends = edges.filter((edge) => laneOf.get(edge) === `${lane.gap}|${lane.from}`).map((edge) => tracks.get(`to|${edge.to}`)!)
      const deepest = Math.max(...ends.map((track) => track.y))
      vertical(lane.x, start.y, deepest)
      meet(lane.x, start, true)
      ends.forEach((track) => meet(lane.x, track, track.y === deepest))
    }

    const shift = (x: number) => x + offset
    return {
      nodes: rows.flatMap((files, index) => files.map((file) => ({ id: file, x: shift(center(file) - W / 2), y: top[index] }))),
      wires: wires.map(({ x1, y1, x2, y2 }) => ({ x1: shift(x1), y1, x2: shift(x2), y2 })),
      dots: [...new Map(dots.map((dot) => [`${dot.x},${dot.y}`, { x: shift(dot.x), y: dot.y }])).values()],
      width: available,
      height,
    }
  }
}
