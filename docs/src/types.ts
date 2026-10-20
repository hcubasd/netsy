export type Cell = number | string | null

export type Position = [number, number]

export type Geometry =
  | { type: 'Point'; coordinates: Position }
  | { type: 'LineString'; coordinates: Position[] }
  | { type: 'Polygon'; coordinates: Position[][] }
  | { type: 'MultiPoint'; coordinates: Position[] }
  | { type: 'MultiLineString'; coordinates: Position[][] }
  | { type: 'MultiPolygon'; coordinates: Position[][][] }

export type Column =
  | { kind: 'number'; values: Float64Array }
  | { kind: 'dictionary'; dictionary: string[]; codes: Int32Array }
  | { kind: 'mixed'; values: Cell[] }

export interface DataTable {
  filename: string
  columns: string[]
  rowCount: number
  data: Record<string, Column>
  geometries?: (Geometry | null)[]
  // The map's buffers for this file's geometry, prepared while it loaded.
  prepared?: import('./map/geometry').Prepared | null
  srsId?: number
}

export interface PaletteColor {
  r: number
  g: number
  b: number
}
