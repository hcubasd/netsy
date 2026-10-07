export type Cell = number | string | null

export type Position = [number, number]

export type Geometry =
  | { type: 'Point'; coordinates: Position }
  | { type: 'LineString'; coordinates: Position[] }
  | { type: 'Polygon'; coordinates: Position[][] }
  | { type: 'MultiPoint'; coordinates: Position[] }
  | { type: 'MultiLineString'; coordinates: Position[][] }
  | { type: 'MultiPolygon'; coordinates: Position[][][] }

export interface DataTable {
  filename: string
  columns: string[]
  rows: Record<string, Cell>[]
  geometries?: (Geometry | null)[]
  srsId?: number
}

export interface ValueFeature {
  geometry: Geometry
  value: number | null
  label: string
}

export interface PaletteColor {
  r: number
  g: number
  b: number
}
