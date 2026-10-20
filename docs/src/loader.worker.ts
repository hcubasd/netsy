// Loads a file off the main thread, so the page (and the loading cat) keeps
// moving: parses it as the NetSy file it is loaded as and, for a GeoPackage,
// prepares its map geometry. The prepared buffers are transferred, not
// copied; the parsed geometry itself is not sent back, since only the map
// used it, and only to prepare it.

import { parseFile } from './loaders'
import { prepare, type Prepared } from './map/geometry'

export interface LoadRequest { id: number; file: File; name: string }
export type LoadResponse = { id: number; table: import('./types').DataTable } | { id: number; error: string }

function buffersOf(prepared: Prepared) {
  return Object.values(prepared).flatMap((value) => (ArrayBuffer.isView(value) ? [value.buffer as ArrayBuffer] : []))
}

self.onmessage = async ({ data }: MessageEvent<LoadRequest>) => {
  try {
    const { geometries, ...table } = await parseFile(data.file, data.name)
    const prepared = geometries ? prepare(geometries) : undefined
    const response: LoadResponse = { id: data.id, table: { ...table, prepared } }
    const transfers = prepared ? buffersOf(prepared) : []
    for (const column of Object.values(table.data)) {
      if (column.kind === 'number') transfers.push(column.values.buffer as ArrayBuffer)
      else if (column.kind === 'dictionary') transfers.push(column.codes.buffer as ArrayBuffer)
    }
    self.postMessage(response, { transfer: transfers })
  } catch (reason) {
    const response: LoadResponse = { id: data.id, error: reason instanceof Error ? reason.message : `${data.file.name} could not be read.` }
    self.postMessage(response)
  }
}
