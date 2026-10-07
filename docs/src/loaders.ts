import initSqlJs from 'sql.js'
import wasmUrl from 'sql.js/dist/sql-wasm.wasm?url'
import type { Cell, DataTable, Geometry, Position } from './types'

function toCell(value: string): Cell {
  const trimmed = value.trim()
  if (trimmed === '') return null
  const number = Number(trimmed)
  return Number.isFinite(number) ? number : trimmed
}

export function parseCsv(source: string): { columns: string[]; rows: Record<string, Cell>[] } {
  const records: string[][] = [[]]
  let field = ''
  let quoted = false
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index]
    const next = source[index + 1]
    if (character === '"' && quoted && next === '"') {
      field += '"'
      index += 1
    } else if (character === '"') {
      quoted = !quoted
    } else if (character === ',' && !quoted) {
      records.at(-1)?.push(field)
      field = ''
    } else if ((character === '\n' || character === '\r') && !quoted) {
      if (character === '\r' && next === '\n') index += 1
      records.at(-1)?.push(field)
      field = ''
      if (records.at(-1)?.some((item) => item !== '')) records.push([])
    } else {
      field += character
    }
  }
  records.at(-1)?.push(field)
  const [header = [], ...body] = records.filter((record) => record.length > 1 || record[0] !== '')
  const columns = header.map((column) => column.trim())
  return {
    columns,
    rows: body.map((record) =>
      Object.fromEntries(columns.map((column, index) => [column, toCell(record[index] ?? '')])),
    ),
  }
}

function geometryColumn(columns: string[]) {
  return columns.findIndex((column) => ['geom', 'geometry'].includes(column.toLowerCase()))
}

function readPosition(view: DataView, offset: number, littleEndian: boolean): [Position, number] {
  return [
    [view.getFloat64(offset, littleEndian), view.getFloat64(offset + 8, littleEndian)],
    offset + 16,
  ]
}

function parseWkb(view: DataView, start: number): [Geometry | null, number] {
  const littleEndian = view.getUint8(start) === 1
  const rawType = view.getUint32(start + 1, littleEndian)
  const type = rawType & 0xff
  let offset = start + 5
  const count = () => {
    const value = view.getUint32(offset, littleEndian)
    offset += 4
    return value
  }
  const positions = (length: number) => {
    const result: Position[] = []
    for (let index = 0; index < length; index += 1) {
      const [position, next] = readPosition(view, offset, littleEndian)
      result.push(position)
      offset = next
    }
    return result
  }
  if (type === 1) {
    const [coordinates, next] = readPosition(view, offset, littleEndian)
    return [{ type: 'Point', coordinates }, next]
  }
  if (type === 2) return [{ type: 'LineString', coordinates: positions(count()) }, offset]
  if (type === 3) {
    const rings = Array.from({ length: count() }, () => positions(count()))
    return [{ type: 'Polygon', coordinates: rings }, offset]
  }
  if (type === 4 || type === 5 || type === 6) {
    const children: Geometry[] = []
    for (let index = 0; index < count(); index += 1) {
      const [child, next] = parseWkb(view, offset)
      offset = next
      if (child) children.push(child)
    }
    if (type === 4) return [{ type: 'MultiPoint', coordinates: children.flatMap((child) => child.type === 'Point' ? [child.coordinates] : []) }, offset]
    if (type === 5) return [{ type: 'MultiLineString', coordinates: children.flatMap((child) => child.type === 'LineString' ? [child.coordinates] : []) }, offset]
    return [{ type: 'MultiPolygon', coordinates: children.flatMap((child) => child.type === 'Polygon' ? [child.coordinates] : []) }, offset]
  }
  return [null, offset]
}

function parseGeoPackageGeometry(value: Uint8Array): Geometry | null {
  if (value.length < 8 || value[0] !== 0x47 || value[1] !== 0x50) return null
  const envelope = (value[3] >> 1) & 0b111
  const envelopeBytes = [0, 32, 48, 48, 64][envelope]
  return parseWkb(new DataView(value.buffer, value.byteOffset, value.byteLength), 8 + envelopeBytes)[0]
}

export async function parseGeoPackage(file: File): Promise<DataTable> {
  const SQL = await initSqlJs({ locateFile: () => wasmUrl })
  const database = new SQL.Database(new Uint8Array(await file.arrayBuffer()))
  try {
    const contents = database.exec(
      "SELECT table_name, srs_id FROM gpkg_contents WHERE data_type = 'features' ORDER BY table_name",
    )[0]
    if (!contents || contents.values.length === 0) throw new Error('No feature layer was found in this GeoPackage.')
    if (contents.values.length > 1) throw new Error('GeoPackages with multiple feature layers are not supported.')
    const [tableName, srsId] = contents.values[0]
    const escapedName = String(tableName).replaceAll('"', '""')
    const result = database.exec(`SELECT * FROM "${escapedName}"`)[0]
    if (!result) throw new Error('The GeoPackage layer has no rows.')
    const index = geometryColumn(result.columns)
    if (index < 0) throw new Error('The GeoPackage layer has no geom or geometry column.')
    const columns = result.columns.filter((column, columnIndex) => columnIndex !== index && column.toLowerCase() !== 'fid')
    const rows = result.values.map((row) =>
      Object.fromEntries(columns.map((column) => [column, row[result.columns.indexOf(column)] as Cell])),
    )
    return {
      filename: file.name,
      columns,
      rows,
      geometries: result.values.map((row) => {
        const geometry = row[index]
        return geometry instanceof Uint8Array ? parseGeoPackageGeometry(geometry) : null
      }),
      srsId: typeof srsId === 'number' ? srsId : undefined,
    }
  } finally {
    database.close()
  }
}

export async function parseFile(file: File): Promise<DataTable> {
  if (file.name.toLowerCase().endsWith('.gpkg')) return parseGeoPackage(file)
  if (file.name.toLowerCase().endsWith('.csv')) {
    const parsed = parseCsv(await file.text())
    return { filename: file.name, ...parsed }
  }
  throw new Error(`${file.name}: only CSV and GeoPackage files are supported.`)
}

export function tableByName(tables: DataTable[], filename: string) {
  return tables.find((table) => table.filename.toLowerCase() === filename.toLowerCase())
}
