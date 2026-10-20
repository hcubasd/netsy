import type { Cell, Column, DataTable } from './types'
export function column(values: Cell[]): Column {
  if (values.every(v => v === null || typeof v === 'number')) return { kind: 'number', values: Float64Array.from(values, v => v === null ? NaN : Number(v)) }
  if (values.every(v => v === null || typeof v === 'string')) {
    const dictionary: string[] = [], lookup = new Map<string, number>()
    const codes = Int32Array.from(values, v => {
      if (v === null) return -1
      const text = String(v)
      if (!lookup.has(text)) { lookup.set(text, dictionary.length); dictionary.push(text) }
      return lookup.get(text)!
    })
    return { kind: 'dictionary', dictionary, codes }
  }
  return { kind: 'mixed', values }
}
export function cell(table: DataTable, name: string, index: number): Cell {
  const col = table.data[name]
  if (!col) return null
  if (col.kind === 'dictionary') return col.codes[index] < 0 ? null : col.dictionary[col.codes[index]]
  const value = col.values[index]
  return typeof value === 'number' && Number.isNaN(value) ? null : value
}
export function unique(table: DataTable, name: string): string[] {
  const col = table.data[name]
  if (col.kind === 'dictionary') return col.dictionary.filter(Boolean).slice().sort()
  return [...new Set(Array.from(col.values, v => v === null ? '' : String(v)).filter(Boolean))].sort()
}
