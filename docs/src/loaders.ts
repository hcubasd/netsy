import { parquetMetadata, parquetReadObjects } from 'hyparquet'
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

// Reads WKB (ISO or extended), keeping x and y: Z and M coordinates, when
// present, are skipped.
function parseWkb(view: DataView, start: number): [Geometry | null, number] {
  const littleEndian = view.getUint8(start) === 1
  const rawType = view.getUint32(start + 1, littleEndian)
  // ISO: 1000 adds Z, 2000 M, 3000 both. Extended: high bits flag Z, M, SRID.
  const iso = rawType & 0xffff
  const type = iso % 1000
  const hasZ = Math.floor(iso / 1000) === 1 || Math.floor(iso / 1000) === 3 || (rawType & 0x80000000) !== 0
  const hasM = Math.floor(iso / 1000) === 2 || Math.floor(iso / 1000) === 3 || (rawType & 0x40000000) !== 0
  const stride = 16 + (hasZ ? 8 : 0) + (hasM ? 8 : 0)
  let offset = start + 5 + ((rawType & 0x20000000) !== 0 ? 4 : 0)
  const count = () => {
    const value = view.getUint32(offset, littleEndian)
    offset += 4
    return value
  }
  const position = (): Position => {
    const result: Position = [view.getFloat64(offset, littleEndian), view.getFloat64(offset + 8, littleEndian)]
    offset += stride
    return result
  }
  const positions = (length: number) => Array.from({ length }, position)
  if (type === 1) return [{ type: 'Point', coordinates: position() }, offset]
  if (type === 2) return [{ type: 'LineString', coordinates: positions(count()) }, offset]
  if (type === 3) return [{ type: 'Polygon', coordinates: Array.from({ length: count() }, () => positions(count())) }, offset]
  if (type === 4 || type === 5 || type === 6) {
    const children: Geometry[] = []
    const parts = count()
    for (let index = 0; index < parts; index += 1) {
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

async function parseGeoPackage(file: File): Promise<Omit<DataTable, 'filename'>> {
  const SQL = await initSqlJs({ locateFile: () => wasmUrl })
  const database = new SQL.Database(new Uint8Array(await file.arrayBuffer()))
  try {
    const contents = database.exec(
      "SELECT table_name, srs_id FROM gpkg_contents WHERE data_type = 'features' ORDER BY table_name",
    )[0]
    if (!contents || contents.values.length === 0) throw new Error(`${file.name}: no feature layer was found.`)
    if (contents.values.length > 1) throw new Error(`${file.name}: GeoPackages with several feature layers are not supported.`)
    const [tableName, srsId] = contents.values[0]
    const escapedName = String(tableName).replaceAll('"', '""')
    const result = database.exec(`SELECT * FROM "${escapedName}"`)[0]
    if (!result) throw new Error(`${file.name}: the layer has no rows.`)
    const index = geometryColumn(result.columns)
    if (index < 0) throw new Error(`${file.name}: the layer has no geom or geometry column.`)
    const columns = result.columns.filter((column, columnIndex) => columnIndex !== index && column.toLowerCase() !== 'fid')
    const rows = result.values.map((row) =>
      Object.fromEntries(columns.map((column) => [column, row[result.columns.indexOf(column)] as Cell])),
    )
    return {
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

// Parquet, as NetSy writes its large tables; 64-bit integers become numbers.
async function parseParquet(file: File): Promise<{ columns: string[]; rows: Record<string, Cell>[] }> {
  const buffer = await file.arrayBuffer()
  const metadata = parquetMetadata(buffer)
  const columns = metadata.schema.slice(1).map((element) => element.name)
  const records = (await parquetReadObjects({ file: buffer, metadata })) as Record<string, unknown>[]
  const rows = records.map((record) => {
    const row: Record<string, Cell> = {}
    for (const column of columns) {
      const value = record[column]
      row[column] = typeof value === 'bigint' ? Number(value) : value === undefined ? null : (value as Cell)
    }
    return row
  })
  return { columns, rows }
}

// Reads `file` as the NetSy file `name`, whatever the file itself is called:
// its format is the one `name` expects.
export async function parseFile(file: File, name: string): Promise<DataTable> {
  const table = name.endsWith('.gpkg') ? await parseGeoPackage(file)
    : name.endsWith('.parquet') ? await parseParquet(file) : parseCsv(await file.text())
  return { ...table, filename: name }
}
