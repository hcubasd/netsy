export function buildPermutation(seed: number) {
  const permutation = new Uint8Array(256)
  for (let index = 0; index < permutation.length; index += 1) permutation[index] = index
  let state = seed
  const random = () => {
    state = (state * 9301 + 49297) % 233280
    return state / 233280
  }
  for (let index = permutation.length - 1; index > 0; index -= 1) {
    const other = Math.floor(random() * (index + 1))
    const value = permutation[index]
    permutation[index] = permutation[other]
    permutation[other] = value
  }
  return permutation
}

const cells = 32
const fade = (value: number) => value * value * value * (value * (value * 6 - 15) + 10)
const interpolate = (left: number, right: number, value: number) => left + value * (right - left)

function gradient(hash: number, x: number, y: number, z: number) {
  const type = hash & 15
  const first = type < 8 ? x : y
  const second = type < 4 ? y : type === 12 || type === 14 ? x : z
  return (type & 1 ? -first : first) + (type & 2 ? -second : second)
}

export function perlin3(permutation: Uint8Array, x: number, y: number, z: number) {
  const permutationAt = (index: number) => permutation[index & 255]
  const integerX = Math.floor(x)
  const integerY = Math.floor(y)
  const integerZ = Math.floor(z)
  x -= integerX
  y -= integerY
  z -= integerZ
  const fadeX = fade(x)
  const fadeY = fade(y)
  const fadeZ = fade(z)
  const a = permutationAt(integerX) + integerY
  const aa = permutationAt(a) + integerZ
  const ab = permutationAt(a + 1) + integerZ
  const b = permutationAt(integerX + 1) + integerY
  const ba = permutationAt(b) + integerZ
  const bb = permutationAt(b + 1) + integerZ
  return interpolate(
    interpolate(
      interpolate(gradient(permutationAt(aa), x, y, z), gradient(permutationAt(ba), x - 1, y, z), fadeX),
      interpolate(gradient(permutationAt(ab), x, y - 1, z), gradient(permutationAt(bb), x - 1, y - 1, z), fadeX),
      fadeY,
    ),
    interpolate(
      interpolate(gradient(permutationAt(aa + 1), x, y, z - 1), gradient(permutationAt(ba + 1), x - 1, y, z - 1), fadeX),
      interpolate(gradient(permutationAt(ab + 1), x, y - 1, z - 1), gradient(permutationAt(bb + 1), x - 1, y - 1, z - 1), fadeX),
      fadeY,
    ),
    fadeZ,
  )
}

function climb(permutation: Uint8Array, depth: number, x: number, y: number, sign: number) {
  const valueAt = (sampleX: number, sampleY: number) => sign * perlin3(permutation, sampleX, sampleY, depth)
  const clampX = (value: number) => Math.min(Math.max(value, 0), 2)
  const clampY = (value: number) => Math.min(Math.max(value, 0), 1)
  let best = valueAt(x, y)
  for (let step = 1 / cells; step > 1e-7;) {
    let moved = false
    for (const [deltaX, deltaY] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nextX = clampX(x + deltaX * step)
      const nextY = clampY(y + deltaY * step)
      const value = valueAt(nextX, nextY)
      if (value > best) {
        best = value
        x = nextX
        y = nextY
        moved = true
      }
    }
    if (!moved) step /= 2
  }
  return best
}

export function fieldRange(permutation: Uint8Array, depth: number) {
  const columns = 2 * cells + 1
  const rows = cells + 1
  const grid = new Float64Array(columns * rows)
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      grid[row * columns + column] = perlin3(permutation, column / cells, row / cells, depth)
    }
  }
  let minimum = Infinity
  let maximum = -Infinity
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const value = grid[row * columns + column]
      let localMaximum = true
      let localMinimum = true
      for (let rowOffset = -1; rowOffset <= 1; rowOffset += 1) {
        for (let columnOffset = -1; columnOffset <= 1; columnOffset += 1) {
          const nextRow = row + rowOffset
          const nextColumn = column + columnOffset
          if ((rowOffset || columnOffset) && nextRow >= 0 && nextRow < rows && nextColumn >= 0 && nextColumn < columns) {
            const neighbor = grid[nextRow * columns + nextColumn]
            if (neighbor > value) localMaximum = false
            if (neighbor < value) localMinimum = false
          }
        }
      }
      if (localMaximum) maximum = Math.max(maximum, climb(permutation, depth, column / cells, row / cells, 1))
      if (localMinimum) minimum = Math.min(minimum, -climb(permutation, depth, column / cells, row / cells, -1))
    }
  }
  return { minimum, range: maximum - minimum || 1 }
}
